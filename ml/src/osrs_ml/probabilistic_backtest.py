"""Phase One P1 causal economic backtest for ``recursive_student_t`` on E2/E3 validation folds.

Converts frozen ``recursive_student_t`` predictive trajectories (sole E2 Gate B survivor) into a
preregistered, sized Grand Exchange trading policy and evaluates net P/L across the three 90-day
development validation folds (2025-10-29..2026-07-26) without consuming E4 slots or touching the
sealed holdout (>= 1785024300).

Reuses ``osrs_ml.costs``, ``osrs_ml.execution``, and ``osrs_ml.backtest`` directly — no parallel
cost or fill model is permitted.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import BacktestResult, PreparedObservations, simulate
from .costs import DEFAULT_TAX, TaxPolicy, net_return, sale_proceeds
from .execution import ExecutionAssumptions, PortfolioPolicy
from .probabilistic_campaign import _code_tree_provenance, build_campaign_panel
from .probabilistic_models import build_model
from .probabilistic_train import (
    CONTEXT,
    HOLDOUT_START,
    HORIZON,
    HOUR,
    REGISTERED_FOLDS,
    PanelArrays,
    _json,
    configure_device,
    file_hash,
    load_verified_panel,
)

DAY = 86400
QUANTILE_TAUS = (0.10, 0.25, 0.50, 0.75, 0.90)
QUANTILE_HORIZONS = (1, 4, 24)
HORIZON_INDICES = (0, 3, 23)
INNER_TUNING_DAYS = 21
TUNING_HOLDING_HOURS = (4, 24)
TUNING_MIN_EDGE_BPS = (0, 25, 50)
PRIMARY_CAPITAL_GP = 100_000_000
SENSITIVITY_CAPITAL_GP = 10_000_000
OFFER_SLOTS = 8
MAX_ALLOCATION_BPS = 1250
MIN_ALLOCATION_BPS = 100
CAMPAIGN_SEEDS = (11, 23, 47)
SAMPLES_PER_SEED = 256
LOBSTER_ITEM_ID = 379


def make_crossed_assumptions(participation_bps: int = 200) -> ExecutionAssumptions:
    """Primary P1 crossed-spread hourly execution assumptions (charges both-side spread + tax)."""
    return ExecutionAssumptions(
        name=f"p1_crossed_moderate_{participation_bps}bps",
        participation_bps=participation_bps,
        slippage_bps=10,
        latency_seconds=300,
        max_freshness_seconds=7500,
        buy_timeout_seconds=7500,
        terminal_haircut_bps=100,
        allow_unknown_metadata=False,
        freshness_basis="upper_bound",
        passive_prices=False,
        queue_fill_bps=10_000,
        price_model="integer_lots_v2",
        adverse_ticks=0,
        fill_model="bucket_proxy_v1",
    )


def make_passive_v3_assumptions(participation_bps: int = 200) -> ExecutionAssumptions:
    """Secondary passive-limit contrast matching battery_v1 hourly volume_bounded_v3."""
    return ExecutionAssumptions(
        name=f"p1_passive_v3_{participation_bps}bps",
        participation_bps=participation_bps,
        slippage_bps=10,
        latency_seconds=300,
        max_freshness_seconds=7500,
        buy_timeout_seconds=11100,
        terminal_haircut_bps=100,
        allow_unknown_metadata=False,
        freshness_basis="upper_bound",
        passive_prices=True,
        queue_fill_bps=10_000,
        price_model="integer_lots_v2",
        adverse_ticks=0,
        fill_model="volume_bounded_v3",
        volume_qualification="mean_proxy",
    )


def make_portfolio_policy(
    holding_hours: int,
    *,
    initial_cash_gp: int = PRIMARY_CAPITAL_GP,
    offer_slots: int = OFFER_SLOTS,
    allocation_bps: int = MAX_ALLOCATION_BPS,
) -> PortfolioPolicy:
    return PortfolioPolicy(
        initial_cash_gp=initial_cash_gp,
        offer_slots=offer_slots,
        allocation_bps=allocation_bps,
        holding_seconds=int(holding_hours) * HOUR,
        minimum_score=0.0,
    )


def circular_block_indices(
    n: int, block: int, *, draws: int = 2000, seed: int = 42
) -> np.ndarray:
    """Circular moving-block bootstrap index matrix [draws, n] (matches uncertainty.py)."""
    if n < 1 or block < 1 or draws < 1:
        raise ValueError("Positive sample, block, and draw counts required")
    starts = np.random.default_rng(seed).integers(0, n, size=(draws, (n + block - 1) // block))
    return ((starts[..., None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]


def distribution_summary(values: np.ndarray | list[float]) -> dict:
    """Empirical summary (count, mean, std, p10, p25, p50, p75, p90) on finite observations."""
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "p10": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
        }
    q10, q25, q50, q75, q90 = np.quantile(arr, [0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "count": int(len(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) >= 2 else 0.0,
        "p10": float(q10),
        "p25": float(q25),
        "p50": float(q50),
        "p75": float(q75),
        "p90": float(q90),
    }


def verify_holdout_untouched(frame: pd.DataFrame, window_start: int, window_end: int) -> None:
    """Hard guard ensuring no observation or boundary ever touches HOLDOUT_START."""
    if window_start >= window_end:
        raise ValueError(f"Invalid window [{window_start}, {window_end})")
    if window_end > HOLDOUT_START:
        raise ValueError(
            f"Window end {window_end} exceeds protected holdout start {HOLDOUT_START}"
        )
    if (frame["ts"] >= HOLDOUT_START).any():
        raise ValueError("Input frame contains protected holdout timestamps")


def build_backtest_observations(
    frame: pd.DataFrame,
    items_df: pd.DataFrame,
    window_start: int,
    window_end: int,
    *,
    delay_seconds: int = 300,
) -> pd.DataFrame:
    """Convert causal hourly panel rows in [window_start, window_end) for backtest.simulate.

    Carries forward causal last-print side prices with exact staleness ``300 + (ts - last_ts)``
    while keeping current-bucket volumes strictly uncarried (0 when no side trades occurred), so
    zero-volume buckets never fill while held inventory marks at the latest causal bid.
    """
    verify_holdout_untouched(frame, window_start, window_end)
    if "id" not in items_df.columns or "buy_limit" not in items_df.columns:
        raise ValueError("items_df must contain 'id' and 'buy_limit' columns")

    limit_map: dict[int, int | None] = {}
    for row in items_df[["id", "buy_limit"]].itertuples(index=False):
        item_id = int(row.id)
        lim = row.buy_limit
        limit_map[item_id] = int(lim) if pd.notna(lim) and float(lim) > 0 else None

    causal = frame[frame["ts"] < window_end].sort_values(["item_id", "ts"], kind="mergesort")
    chunks: list[pd.DataFrame] = []

    for item_id_raw, grp in causal.groupby("item_id", sort=True):
        item_id = int(item_id_raw)
        ts = grp["ts"].to_numpy(dtype=np.int64)
        avail = grp["available_at"].to_numpy(dtype=np.int64)
        raw_high = grp["avg_high_price"].to_numpy(dtype=np.float64)
        raw_low = grp["avg_low_price"].to_numpy(dtype=np.float64)
        raw_mid = grp["mid_price"].to_numpy(dtype=np.float64)
        raw_hvol = grp["high_price_volume"].to_numpy(dtype=np.float64)
        raw_lvol = grp["low_price_volume"].to_numpy(dtype=np.float64)
        usable = grp["usable"].eq(True).to_numpy(dtype=bool)

        hvol_int = np.where(np.isfinite(raw_hvol) & (raw_hvol > 0), np.rint(raw_hvol), 0).astype(
            np.int64
        )
        lvol_int = np.where(np.isfinite(raw_lvol) & (raw_lvol > 0), np.rint(raw_lvol), 0).astype(
            np.int64
        )

        valid_high_now = np.isfinite(raw_high) & (raw_high > 0) & (hvol_int > 0)
        valid_low_now = np.isfinite(raw_low) & (raw_low > 0) & (lvol_int > 0)

        n = len(ts)
        high_gp: list[int | object] = [pd.NA] * n
        low_gp: list[int | object] = [pd.NA] * n
        high_fresh: list[int | object] = [pd.NA] * n
        low_fresh: list[int | object] = [pd.NA] * n
        inverted = np.zeros(n, dtype=bool)

        last_h_gp: int | None = None
        last_h_ts: int | None = None
        last_l_gp: int | None = None
        last_l_ts: int | None = None

        for idx in range(n):
            cur_ts = int(ts[idx])
            if valid_high_now[idx]:
                last_h_gp = max(1, int(round(float(raw_high[idx]))))
                last_h_ts = cur_ts
            if valid_low_now[idx]:
                last_l_gp = max(1, int(round(float(raw_low[idx]))))
                last_l_ts = cur_ts

            if last_h_gp is not None and last_h_ts is not None:
                high_gp[idx] = last_h_gp
                high_fresh[idx] = int(delay_seconds + (cur_ts - last_h_ts))
            if last_l_gp is not None and last_l_ts is not None:
                low_gp[idx] = last_l_gp
                low_fresh[idx] = int(delay_seconds + (cur_ts - last_l_ts))
            if last_h_gp is not None and last_l_gp is not None:
                inverted[idx] = bool(last_l_gp > last_h_gp)

        in_win = (
            (ts >= window_start)
            & (ts < window_end)
            & (avail >= window_start)
            & (avail < window_end)
            & (avail < HOLDOUT_START)
        )
        if not np.any(in_win):
            continue

        sel = np.flatnonzero(in_win)
        buy_lim = limit_map.get(item_id)
        buy_lim_col = pd.array(
            [buy_lim if buy_lim is not None else pd.NA] * len(sel), dtype="Int64"
        )
        sub = pd.DataFrame(
            {
                "item_id": np.full(len(sel), item_id, dtype=np.int64),
                "timestamp": ts[sel],
                "available_at": avail[sel],
                "avg_high_price": pd.array([high_gp[i] for i in sel], dtype="Int64"),
                "avg_low_price": pd.array([low_gp[i] for i in sel], dtype="Int64"),
                "high_price_volume": pd.array(hvol_int[sel], dtype="Int64"),
                "low_price_volume": pd.array(lvol_int[sel], dtype="Int64"),
                "buy_limit": buy_lim_col,
                "source_interval_seconds": np.full(len(sel), delay_seconds, dtype=np.int64),
                "resolution_seconds": np.full(len(sel), HOUR, dtype=np.int64),
                "interval_unknown": np.zeros(len(sel), dtype=bool),
                "high_freshness_seconds": pd.array([high_fresh[i] for i in sel], dtype="Int64"),
                "low_freshness_seconds": pd.array([low_fresh[i] for i in sel], dtype="Int64"),
                "inverted_spread": inverted[sel],
                "raw_avg_high_price": raw_high[sel],
                "raw_avg_low_price": raw_low[sel],
                "raw_mid_price": raw_mid[sel],
                "usable_origin": usable[sel],
                "both_sides_active_now": (valid_high_now[sel] & valid_low_now[sel]),
            }
        )
        chunks.append(sub)

    if not chunks:
        raise ValueError(f"No observations constructed for window [{window_start}, {window_end})")
    out = pd.concat(chunks, ignore_index=True).sort_values(
        ["available_at", "item_id"], kind="mergesort"
    )
    return out.reset_index(drop=True)


def compute_validation_market_wall(
    frame: pd.DataFrame,
    *,
    folds: dict[int, tuple[int, int, int]] = REGISTERED_FOLDS,
    tax_policy: TaxPolicy = DEFAULT_TAX,
) -> dict:
    """Measure empirical spread, 4h/24h moves, and round-trip cost wall on the 3 validation folds."""
    val_min = min(v[1] for v in folds.values())
    val_max = max(v[2] for v in folds.values())
    verify_holdout_untouched(frame, val_min, val_max)

    sub = frame[(frame["ts"] >= val_min) & (frame["ts"] < val_max)].sort_values(
        ["item_id", "ts"], kind="mergesort"
    )

    cont_spreads: list[np.ndarray] = []
    int_spreads: list[np.ndarray] = []
    abs_move_4h: list[np.ndarray] = []
    abs_move_24h: list[np.ndarray] = []
    rt_cost_walls: list[np.ndarray] = []
    clears_tax_24h: list[np.ndarray] = []
    clears_wall_24h: list[np.ndarray] = []
    clears_wall_slip_24h: list[np.ndarray] = []
    clears_wall_slip_4h: list[np.ndarray] = []

    for item_id_raw, grp in sub.groupby("item_id", sort=True):
        item_id = int(item_id_raw)
        ts = grp["ts"].to_numpy(dtype=np.int64)
        grid = np.arange(val_min, val_max, HOUR, dtype=np.int64)
        re = grp.set_index("ts").reindex(grid)

        ask = re["avg_high_price"].to_numpy(dtype=np.float64)
        bid = re["avg_low_price"].to_numpy(dtype=np.float64)
        mid = re["mid_price"].to_numpy(dtype=np.float64)
        hvol = re["high_price_volume"].to_numpy(dtype=np.float64)
        lvol = re["low_price_volume"].to_numpy(dtype=np.float64)
        usable = re["usable"].eq(True).to_numpy(dtype=bool)

        active = (
            usable
            & np.isfinite(ask)
            & np.isfinite(bid)
            & np.isfinite(mid)
            & (ask > 0)
            & (bid > 0)
            & (mid > 0)
            & (ask >= bid)
            & (hvol > 0)
            & (lvol > 0)
        )
        if not np.any(active) or len(ts) == 0:
            continue

        ask_act = ask[active]
        bid_act = bid[active]
        mid_act = mid[active]
        cont_spreads.append((ask_act - bid_act) / mid_act)

        ask_gp = np.maximum(1, np.rint(ask_act)).astype(np.int64)
        bid_gp = np.maximum(1, np.rint(bid_act)).astype(np.int64)
        mid_gp = 0.5 * (ask_gp + bid_gp)
        int_spreads.append((ask_gp - bid_gp) / mid_gp)

        walls = np.empty(len(ask_gp), dtype=np.float64)
        for k in range(len(ask_gp)):
            buy_c = max(1, math.ceil(int(ask_gp[k]) * 1.0010))
            sell_f = max(1, math.floor(int(bid_gp[k]) * 0.9990))
            walls[k] = -net_return(buy_c, sell_f, tax_policy, item_id)
        rt_cost_walls.append(walls)

        for horizon_h, move_list, tax_list, wall_list, slip_list in (
            (4, abs_move_4h, None, None, clears_wall_slip_4h),
            (24, abs_move_24h, clears_tax_24h, clears_wall_24h, clears_wall_slip_24h),
        ):
            if len(grid) <= horizon_h:
                continue
            pair_ok = active[:-horizon_h] & active[horizon_h:]
            if not np.any(pair_ok):
                continue
            m0 = mid[:-horizon_h][pair_ok]
            m1 = mid[horizon_h:][pair_ok]
            move_list.append(np.abs(m1 / m0 - 1.0))

            a0_gp = np.maximum(1, np.rint(ask[:-horizon_h][pair_ok])).astype(np.int64)
            b1_gp = np.maximum(1, np.rint(bid[horizon_h:][pair_ok])).astype(np.int64)
            m0_gp = np.maximum(1, np.rint(m0)).astype(np.int64)
            m1_gp = np.maximum(1, np.rint(m1)).astype(np.int64)

            c_tax = np.empty(len(a0_gp), dtype=np.float64)
            c_wall = np.empty(len(a0_gp), dtype=np.float64)
            c_slip = np.empty(len(a0_gp), dtype=np.float64)
            for k in range(len(a0_gp)):
                c_tax[k] = float(
                    sale_proceeds(int(m1_gp[k]), 1, tax_policy, item_id) > int(m0_gp[k])
                )
                c_wall[k] = float(
                    sale_proceeds(int(b1_gp[k]), 1, tax_policy, item_id) > int(a0_gp[k])
                )
                buy_c = max(1, math.ceil(int(a0_gp[k]) * 1.0010))
                sell_f = max(1, math.floor(int(b1_gp[k]) * 0.9990))
                c_slip[k] = float(net_return(buy_c, sell_f, tax_policy, item_id) > 0.0)
            if tax_list is not None:
                tax_list.append(c_tax)
            if wall_list is not None:
                wall_list.append(c_wall)
            slip_list.append(c_slip)

    return {
        "window_start_unix": val_min,
        "window_end_unix": val_max,
        "continuous_quoted_spread_pct": distribution_summary(
            np.concatenate(cont_spreads) * 100.0 if cont_spreads else []
        ),
        "integer_quoted_spread_pct": distribution_summary(
            np.concatenate(int_spreads) * 100.0 if int_spreads else []
        ),
        "roundtrip_cost_wall_incl_tax_and_20bps_slip_pct": distribution_summary(
            np.concatenate(rt_cost_walls) * 100.0 if rt_cost_walls else []
        ),
        "abs_4h_mid_move_pct": distribution_summary(
            np.concatenate(abs_move_4h) * 100.0 if abs_move_4h else []
        ),
        "abs_24h_mid_move_pct": distribution_summary(
            np.concatenate(abs_move_24h) * 100.0 if abs_move_24h else []
        ),
        "fraction_24h_clearing_tax_alone": (
            float(np.mean(np.concatenate(clears_tax_24h))) if clears_tax_24h else None
        ),
        "fraction_24h_clearing_spread_plus_tax": (
            float(np.mean(np.concatenate(clears_wall_24h))) if clears_wall_24h else None
        ),
        "fraction_24h_clearing_spread_tax_and_20bps_slip": (
            float(np.mean(np.concatenate(clears_wall_slip_24h)))
            if clears_wall_slip_24h
            else None
        ),
        "fraction_4h_clearing_spread_tax_and_20bps_slip": (
            float(np.mean(np.concatenate(clears_wall_slip_4h)))
            if clears_wall_slip_4h
            else None
        ),
    }


def resolve_checkpoint_dir(fit_id: str, checkpoint_roots: list[Path]) -> Path:
    for root in checkpoint_roots:
        cand = Path(root) / fit_id
        if (cand / "checkpoint.pt").is_file() and (cand / "status.json").is_file():
            return cand
    raise FileNotFoundError(
        f"Could not locate completed checkpoint {fit_id!r} in {[str(r) for r in checkpoint_roots]}"
    )


def enumerate_causal_signal_origins(
    panel: PanelArrays,
    obs_df: pd.DataFrame,
) -> pd.DataFrame:
    """Identify all causally eligible origins in obs_df without future complete_24h conditioning."""
    time_to_idx = {int(t): idx for idx, t in enumerate(panel.times)}
    item_to_idx = {int(it): idx for idx, it in enumerate(panel.item_ids)}

    cand = obs_df[
        obs_df["usable_origin"]
        & obs_df["both_sides_active_now"]
        & (~obs_df["inverted_spread"])
        & obs_df["buy_limit"].notna()
    ].copy()
    if cand.empty:
        return cand.assign(
            item_idx=np.empty(0, dtype=np.int64),
            origin_idx=np.empty(0, dtype=np.int64),
        )

    item_indices = np.array([item_to_idx[int(i)] for i in cand["item_id"]], dtype=np.int64)
    origin_indices = np.array([time_to_idx[int(t)] for t in cand["timestamp"]], dtype=np.int64)
    panel_usable = panel.usable[item_indices, origin_indices]
    keep = (origin_indices >= CONTEXT - 1) & panel_usable

    out = cand.loc[keep].copy().reset_index(drop=True)
    out["item_idx"] = item_indices[keep]
    out["origin_idx"] = origin_indices[keep]
    return out


def extract_or_load_fold_quantiles(
    *,
    fold_id: int,
    frame: pd.DataFrame,
    manifest: dict,
    items_df: pd.DataFrame,
    checkpoint_roots: list[Path],
    cache_dir: Path,
    device_name: str = "cuda",
    seeds: tuple[int, ...] = CAMPAIGN_SEEDS,
    samples_per_seed: int = SAMPLES_PER_SEED,
    batch_size: int = 512,
    torch_threads: int = 4,
) -> tuple[pd.DataFrame, np.ndarray, dict]:
    """Extract or load cached 768-path pooled quantiles [N, 3, 5] for inner-train + outer-val."""
    if fold_id not in REGISTERED_FOLDS:
        raise ValueError(f"Invalid fold_id {fold_id}")
    train_start, val_start, val_end = REGISTERED_FOLDS[fold_id]
    inner_start = val_start - INNER_TUNING_DAYS * DAY
    verify_holdout_untouched(frame, inner_start, val_end)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    npz_path = cache_dir / f"fold{fold_id}_quantiles.npz"
    meta_path = cache_dir / f"fold{fold_id}_quantiles_meta.json"

    ckpt_dirs = [
        resolve_checkpoint_dir(f"e2_recursive_student_t_f{fold_id}_s{s}", checkpoint_roots)
        for s in seeds
    ]
    expected_ckpt_hashes = {
        d.name: file_hash(d / "checkpoint.pt") for d in ckpt_dirs
    }

    obs_all = build_backtest_observations(
        frame,
        items_df,
        inner_start,
        val_end,
        delay_seconds=int(manifest["availability_delay_seconds"]),
    )
    panel = build_campaign_panel(
        frame,
        train_start=train_start,
        selection_end=val_start,
        feature_set="e2_matched",
        availability_delay_seconds=int(manifest["availability_delay_seconds"]),
    )
    origins_df = enumerate_causal_signal_origins(panel, obs_all)

    if npz_path.is_file() and meta_path.is_file():
        saved_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if (
            saved_meta.get("checkpoint_sha256") == expected_ckpt_hashes
            and saved_meta.get("panel_sha256") == manifest["sha256"]
            and saved_meta.get("origin_count") == len(origins_df)
            and file_hash(npz_path) == saved_meta.get("quantiles_npz_sha256")
        ):
            payload = np.load(npz_path)
            if (
                np.array_equal(payload["item_id"], origins_df["item_id"].to_numpy(dtype=np.int64))
                and np.array_equal(
                    payload["available_at"], origins_df["available_at"].to_numpy(dtype=np.int64)
                )
            ):
                return origins_df, payload["quantiles"].astype(np.float64), saved_meta

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    device = configure_device(torch, device_name)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_num_threads(torch_threads)

    t0 = time.time()
    n_orig = len(origins_df)
    item_idx_all = origins_df["item_idx"].to_numpy(dtype=np.int64)
    orig_idx_all = origins_df["origin_idx"].to_numpy(dtype=np.int64)
    quantiles_out = np.empty((n_orig, len(HORIZON_INDICES), len(QUANTILE_TAUS)), dtype=np.float32)

    models = []
    for seed, ckpt_dir in zip(seeds, ckpt_dirs, strict=True):
        st_json = json.loads((ckpt_dir / "status.json").read_text(encoding="utf-8"))
        meta_json = json.loads((ckpt_dir / "metadata.json").read_text(encoding="utf-8"))
        if st_json.get("status") != "completed":
            raise ValueError(f"Checkpoint {ckpt_dir.name} status is not completed")
        if (
            meta_json.get("model") != "recursive_student_t"
            or meta_json.get("fold") != fold_id
            or meta_json.get("seed") != seed
            or meta_json.get("feature_set") != "e2_matched"
            or meta_json.get("panel_sha256") != manifest["sha256"]
        ):
            raise ValueError(f"Checkpoint {ckpt_dir.name} metadata mismatch")
        ckpt = torch.load(ckpt_dir / "checkpoint.pt", map_location="cpu", weights_only=False)
        model = build_model(
            "recursive_student_t",
            len(panel.feature_names),
            HORIZON,
            int(meta_json.get("width", 64)),
            len(panel.item_ids),
        )
        model.load_state_dict(ckpt["model_state"], strict=True)
        model.to(device)
        model.eval()
        models.append((seed, model))

    ctx_offsets = np.arange(-CONTEXT + 1, 1, dtype=np.int64)[None, :]
    h_idx_arr = np.array(HORIZON_INDICES, dtype=np.int64)

    with torch.no_grad():
        for start in range(0, n_orig, batch_size):
            end = min(start + batch_size, n_orig)
            b_items = item_idx_all[start:end]
            b_origs = orig_idx_all[start:end]
            ctx_np = np.ascontiguousarray(
                panel.features[b_items[:, None], b_origs[:, None] + ctx_offsets],
                dtype=np.float32,
            )
            ctx_t = torch.as_tensor(ctx_np, device=device)
            itm_t = torch.as_tensor(b_items, dtype=torch.long, device=device)
            scales = panel.scale[b_items, None, None]
            centers = panel.center[b_items, None, None]

            seed_cum_h: list[np.ndarray] = []
            for seed, model in models:
                batch_seed = 900_000 + fold_id * 100_000 + seed * 1_000 + (start // batch_size)
                torch.manual_seed(batch_seed)
                if device.type == "cuda":
                    torch.cuda.manual_seed_all(batch_seed)
                samp = model.sample(ctx_t, itm_t, samples_per_seed).detach().cpu().numpy()
                if not np.isfinite(samp).all():
                    raise FloatingPointError(f"Nonfinite trajectory sample in fold {fold_id}")
                cum_all = np.cumsum(samp * scales + centers, axis=-1)
                seed_cum_h.append(cum_all[:, :, h_idx_arr])

            pooled = np.concatenate(seed_cum_h, axis=1)  # [B, 768, 3]
            q_batch = np.quantile(pooled, QUANTILE_TAUS, axis=1)  # [5, B, 3]
            quantiles_out[start:end] = np.transpose(q_batch, (1, 2, 0)).astype(np.float32)

    np.savez_compressed(
        npz_path,
        item_id=origins_df["item_id"].to_numpy(dtype=np.int64),
        timestamp=origins_df["timestamp"].to_numpy(dtype=np.int64),
        available_at=origins_df["available_at"].to_numpy(dtype=np.int64),
        quantiles=quantiles_out,
    )
    meta_out = {
        "fold": fold_id,
        "model": "recursive_student_t",
        "seeds": list(seeds),
        "samples_per_seed": samples_per_seed,
        "pooled_samples_per_origin": samples_per_seed * len(seeds),
        "horizons_hours": list(QUANTILE_HORIZONS),
        "tau_levels": list(QUANTILE_TAUS),
        "inner_start_unix": inner_start,
        "validation_start_unix": val_start,
        "validation_end_unix": val_end,
        "origin_count": int(n_orig),
        "panel_sha256": manifest["sha256"],
        "checkpoint_sha256": expected_ckpt_hashes,
        "quantiles_npz_sha256": file_hash(npz_path),
        "device": str(device),
        "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "elapsed_seconds": round(time.time() - t0, 3),
        "holdout_touched": False,
    }
    _json(meta_path, meta_out)
    return origins_df, quantiles_out.astype(np.float64), meta_out


def transform_quantiles_for_control(
    origins_df: pd.DataFrame,
    quantiles: np.ndarray,
    control: str,
    *,
    seed: int = 101,
    block_size: int = 168,
) -> np.ndarray:
    """Apply preregistered null-control transform to [N, 3, 5] cumulative return quantiles."""
    q = np.asarray(quantiles, dtype=np.float64)
    if q.ndim != 3 or q.shape[1:] != (3, 5) or len(origins_df) != len(q):
        raise ValueError(f"Expected quantiles shape [N, 3, 5] aligned to origins_df, got {q.shape}")
    if control == "signal":
        return q.copy()
    if control == "null_sign_flipped":
        return -q[:, :, ::-1].copy()
    if control == "null_detrended_zero_drift":
        return (q - q[:, :, [2]]).copy()
    if control == "null_time_shuffled":
        out = np.empty_like(q)
        item_ids = origins_df["item_id"].to_numpy(dtype=np.int64)
        for item_id in np.unique(item_ids):
            mask = np.flatnonzero(item_ids == item_id)
            n = len(mask)
            if n <= 1:
                out[mask] = q[mask]
                continue
            rng = np.random.default_rng(int(seed) * 100_003 + int(item_id) * 97)
            shift = int(rng.integers(max(1, n // 5), max(2, (4 * n) // 5 + 1))) % n
            if shift == 0:
                shift = 1
            rolled = np.roll(np.arange(n), shift)
            if n >= 2 * block_size:
                n_full = (n // block_size) * block_size
                blocks = rolled[:n_full].reshape(-1, block_size).copy()
                perm = rng.permutation(len(blocks))
                if len(blocks) > 1 and np.all(perm == np.arange(len(blocks))):
                    perm = np.roll(perm, 1)
                perm_idx = np.concatenate([blocks[perm].reshape(-1), rolled[n_full:]])
            else:
                perm_idx = rolled
            out[mask] = q[mask[perm_idx]]
        return out
    raise ValueError(f"Unknown control mode {control!r}")


def build_policy_signals(
    origins_df: pd.DataFrame,
    quantiles: np.ndarray,
    *,
    window_start: int,
    window_end: int,
    holding_hours: int,
    min_net_edge_bps: int,
    tax_policy: TaxPolicy = DEFAULT_TAX,
    max_allocation_bps: int = MAX_ALLOCATION_BPS,
    min_allocation_bps: int = MIN_ALLOCATION_BPS,
) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], int], dict]:
    """Convert predictive quantiles [N, 3, 5] into causal scores & dynamic allocation_bps."""
    if holding_hours not in (4, 24):
        raise ValueError(f"holding_hours must be 4 or 24, got {holding_hours}")
    if min_net_edge_bps < 0:
        raise ValueError("min_net_edge_bps must be nonnegative")
    verify_holdout_untouched(
        pd.DataFrame({"ts": origins_df["timestamp"].to_numpy(dtype=np.int64)})
        if len(origins_df)
        else pd.DataFrame({"ts": np.array([window_start], dtype=np.int64)}),
        window_start,
        window_end,
    )

    h_idx = 1 if holding_hours == 4 else 2
    min_edge = float(min_net_edge_bps) / 10_000.0
    cutoff_avail = int(window_end - (holding_hours + 3) * HOUR)

    scores: dict[tuple[int, int], float] = {}
    allocations: dict[tuple[int, int], int] = {}
    signal_records: list[dict] = []

    item_ids = origins_df["item_id"].to_numpy(dtype=np.int64)
    avails = origins_df["available_at"].to_numpy(dtype=np.int64)
    asks = origins_df["avg_high_price"].to_numpy(dtype=np.int64)
    bids = origins_df["avg_low_price"].to_numpy(dtype=np.int64)

    n_in_window = 0
    n_buffer_ok = 0
    n_median_pos = 0
    n_edge_ok = 0
    n_h1_ok = 0
    n_selected = 0

    for idx in range(len(origins_df)):
        now = int(avails[idx])
        if now < window_start or now >= window_end:
            continue
        n_in_window += 1
        if now >= cutoff_avail:
            continue
        n_buffer_ok += 1

        item_id = int(item_ids[idx])
        ask_t = int(asks[idx])
        bid_t = int(bids[idx])
        if ask_t < 1 or bid_t < 1 or bid_t > ask_t:
            continue

        q_h1 = quantiles[idx, 0]
        q_h4 = quantiles[idx, 1]
        q_h24 = quantiles[idx, 2]
        q_hold = quantiles[idx, h_idx]

        q10_h1 = float(q_h1[0])
        q50_h1 = float(q_h1[2])

        est_buy_gp = max(1, int(math.ceil(ask_t * math.exp(max(0.0, q50_h1)) * 1.0010)))
        sell_gps = [
            max(1, int(math.floor(bid_t * math.exp(float(q_tau)) * 0.9990)))
            for q_tau in q_hold
        ]
        tau_net_returns = [
            net_return(est_buy_gp, sell_gp, tax_policy, item_id) for sell_gp in sell_gps
        ]
        median_net = float(tau_net_returns[2])
        if median_net <= 0.0:
            continue
        n_median_pos += 1

        expected_net = float(sum(tau_net_returns) / 5.0)
        if expected_net <= min_edge:
            continue
        n_edge_ok += 1

        if not (-0.05 < q10_h1 <= 0.005):
            continue
        n_h1_ok += 1

        if holding_hours == 4:
            if float(q_h24[2]) < 0.0:
                continue
        else:
            if float(q_h4[2]) < -0.01:
                continue

        iqr_h = max(float(q_hold[3] - q_hold[1]), 0.005)
        score = float(expected_net / iqr_h)
        if not math.isfinite(score) or score <= 0.0:
            continue

        raw_alloc = math.floor(
            float(max_allocation_bps)
            * min(1.0, expected_net / 0.01)
            * min(1.0, 0.02 / iqr_h)
        )
        alloc = max(int(min_allocation_bps), min(int(max_allocation_bps), int(raw_alloc)))

        key = (item_id, now)
        scores[key] = score
        allocations[key] = alloc
        n_selected += 1
        mid_t = 0.5 * (ask_t + bid_t)
        signal_records.append(
            {
                "item_id": item_id,
                "available_at": now,
                "ask_gp": ask_t,
                "bid_gp": bid_t,
                "origin_quoted_spread_pct": (ask_t - bid_t) / mid_t * 100.0,
                "expected_net_return_pct": expected_net * 100.0,
                "median_net_return_pct": median_net * 100.0,
                "iqr_pct": iqr_h * 100.0,
                "score": score,
                "allocation_bps": alloc,
            }
        )

    funnel = {
        "eligible_origins_in_window": n_in_window,
        "after_end_buffer": n_buffer_ok,
        "after_median_net_gt_0": n_median_pos,
        "after_expected_net_gt_threshold": n_edge_ok,
        "after_h1_crash_and_fill_gate": n_h1_ok,
        "selected_signals": n_selected,
        "signal_rate_of_origins": (float(n_selected / n_in_window) if n_in_window else 0.0),
        "signal_expected_net_return_pct": distribution_summary(
            [r["expected_net_return_pct"] for r in signal_records]
        ),
        "signal_origin_quoted_spread_pct": distribution_summary(
            [r["origin_quoted_spread_pct"] for r in signal_records]
        ),
        "signal_allocation_bps": distribution_summary(
            [r["allocation_bps"] for r in signal_records]
        ),
    }
    return scores, allocations, funnel


def _hourly_equity_series(
    result: BacktestResult,
    window_start: int,
    window_end: int,
    initial_cash_gp: int,
    delay_seconds: int = 300,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Align equity curve onto contiguous hourly availability grid in [window_start, window_end)."""
    first_avail = window_start + HOUR + delay_seconds
    last_avail = window_end - HOUR + delay_seconds
    grid = np.arange(first_avail, last_avail + 1, HOUR, dtype=np.int64)
    if not result.equity:
        eq = np.full(len(grid), float(initial_cash_gp), dtype=np.float64)
        return grid, eq, np.zeros(len(grid), dtype=np.float64)
    curve_df = pd.DataFrame(result.equity)
    series = curve_df.set_index("timestamp")["equity_gp"].reindex(grid)
    if pd.isna(series.iloc[0]):
        series.iloc[0] = float(initial_cash_gp)
    eq = series.ffill().to_numpy(dtype=np.float64)
    inc = np.diff(eq, prepend=float(initial_cash_gp))
    return grid, eq, inc


def _sharpe_from_equity(eq: np.ndarray, initial_cash_gp: int) -> tuple[float | None, float | None]:
    """Compute annualised Sharpe from hourly equity (sqrt(8760)) and 24h daily chunks (sqrt(365))."""
    if len(eq) < 2:
        return None, None
    prev = np.r_[float(initial_cash_gp), eq[:-1]]
    ret_h = (eq - prev) / prev
    std_h = float(np.std(ret_h, ddof=1))
    sharpe_h = float(np.mean(ret_h) / std_h * math.sqrt(8760.0)) if std_h > 1e-15 else 0.0

    n_days = len(eq) // 24
    if n_days >= 2:
        day_end_eq = eq[23 : n_days * 24 : 24]
        day_prev = np.r_[float(initial_cash_gp), day_end_eq[:-1]]
        ret_d = (day_end_eq - day_prev) / day_prev
        std_d = float(np.std(ret_d, ddof=1))
        sharpe_d = float(np.mean(ret_d) / std_d * math.sqrt(365.0)) if std_d > 1e-15 else 0.0
    else:
        sharpe_d = None
    return sharpe_h, sharpe_d


def _block_bootstrap_pnl(
    increments: np.ndarray,
    initial_cash_gp: int,
    *,
    block_hours: int = 168,
    draws: int = 2000,
    seed: int = 42,
) -> dict:
    """168h circular moving-block bootstrap CI and one-sided centered p-value on hourly P/L."""
    x = np.asarray(increments, dtype=np.float64)
    if len(x) == 0:
        return {
            "block_hours": block_hours,
            "draws": draws,
            "lower_gp": 0.0,
            "upper_gp": 0.0,
            "lower_return_pct": 0.0,
            "upper_return_pct": 0.0,
            "p_one_sided_gt_0": 1.0,
        }
    idx = circular_block_indices(len(x), min(block_hours, len(x)), draws=draws, seed=seed)
    boot_samples = x[idx]
    totals = boot_samples.sum(axis=1)
    observed = float(x.sum())
    if observed <= 0.0 or np.ptp(x) == 0.0:
        p_val = 1.0
    else:
        centered = totals - observed
        p_val = float((1 + np.count_nonzero(centered >= observed)) / (draws + 1))
    lo, hi = np.quantile(totals, [0.025, 0.975], method="inverted_cdf")
    return {
        "block_hours": int(block_hours),
        "draws": int(draws),
        "lower_gp": float(lo),
        "upper_gp": float(hi),
        "lower_return_pct": float(lo / initial_cash_gp * 100.0),
        "upper_return_pct": float(hi / initial_cash_gp * 100.0),
        "p_one_sided_gt_0": p_val,
    }


def analyze_backtest_result(
    result: BacktestResult,
    obs_df: pd.DataFrame,
    *,
    window_start: int,
    window_end: int,
    funnel: dict,
    bootstrap_seed: int = 42,
) -> tuple[dict, np.ndarray, list[dict], dict[str, list[float]]]:
    """Reconstruct exact round-trip lifecycles, P/L bridge, Sharpe ratios, and spread distributions."""
    m = result.metrics
    initial_cash = int(m["portfolio"]["initial_cash_gp"])
    obs_lookup: dict[tuple[int, int], dict] = {}
    for row in obs_df[
        [
            "item_id",
            "available_at",
            "avg_high_price",
            "avg_low_price",
            "raw_avg_high_price",
            "raw_avg_low_price",
            "raw_mid_price",
        ]
    ].to_dict("records"):
        obs_lookup[(int(row["item_id"]), int(row["available_at"]))] = row

    buy_submitted_orders = [o for o in result.orders if o.get("event") == "buy_submitted"]
    buy_expired_unfilled = [
        o for o in result.orders if o.get("event") == "buy_expired" and int(o.get("filled", 0)) == 0
    ]

    submitted_origin_spreads: list[float] = []
    expired_adverse_ask_jumps: list[float] = []
    avail_sorted = np.sort(obs_df["available_at"].unique())

    for o in buy_submitted_orders:
        item_id = int(o["item_id"])
        sub_ts = int(o["timestamp"])
        orow = obs_lookup.get((item_id, sub_ts))
        if orow is not None and pd.notna(orow["avg_high_price"]) and pd.notna(orow["avg_low_price"]):
            ask_o = float(orow["avg_high_price"])
            bid_o = float(orow["avg_low_price"])
            mid_o = 0.5 * (ask_o + bid_o)
            if mid_o > 0:
                submitted_origin_spreads.append((ask_o - bid_o) / mid_o * 100.0)

    for exp in buy_expired_unfilled:
        item_id = int(exp["item_id"])
        exp_ts = int(exp["timestamp"])
        # Approximate h=2 bucket at exp_ts (since buy_timeout=7500 expires at sub_ts + 7200..10800)
        sub_cands = [
            o
            for o in buy_submitted_orders
            if int(o["item_id"]) == item_id and exp_ts - 14_400 <= int(o["timestamp"]) < exp_ts
        ]
        if not sub_cands:
            continue
        sub_o = sub_cands[-1]
        sub_ts = int(sub_o["timestamp"])
        orow = obs_lookup.get((item_id, sub_ts))
        next_avails = avail_sorted[(avail_sorted >= sub_ts + 7200) & (avail_sorted <= exp_ts)]
        if orow is not None and len(next_avails) > 0 and pd.notna(orow["avg_high_price"]):
            ask_o = float(orow["avg_high_price"])
            bid_o = float(orow["avg_low_price"]) if pd.notna(orow["avg_low_price"]) else ask_o
            mid_o = 0.5 * (ask_o + bid_o)
            frow = obs_lookup.get((item_id, int(next_avails[0])))
            if frow is not None and pd.notna(frow["avg_high_price"]) and mid_o > 0:
                expired_adverse_ask_jumps.append(
                    (float(frow["avg_high_price"]) - ask_o) / mid_o * 100.0
                )

    open_pos: dict[int, dict] = {}
    completed_trades: list[dict] = []

    fill_bucket_int_spreads: list[float] = []
    fill_bucket_cont_spreads: list[float] = []

    for f in result.fills:
        item_id = int(f["item_id"])
        side = str(f["side"])
        qty = int(f["quantity"])
        price_gp = int(f["price_gp"])
        fill_ts = int(f["timestamp"])
        sub_ts = int(f["submitted"])

        frow = obs_lookup.get((item_id, fill_ts))
        f_ask = (
            float(frow["avg_high_price"])
            if frow and pd.notna(frow["avg_high_price"])
            else float(price_gp)
        )
        f_bid = (
            float(frow["avg_low_price"])
            if frow and pd.notna(frow["avg_low_price"])
            else float(price_gp)
        )
        f_mid = 0.5 * (f_ask + f_bid)
        if f_mid > 0 and f_ask >= f_bid:
            fill_bucket_int_spreads.append((f_ask - f_bid) / f_mid * 100.0)
        if (
            frow
            and pd.notna(frow["raw_avg_high_price"])
            and pd.notna(frow["raw_avg_low_price"])
            and float(frow["raw_avg_high_price"]) >= float(frow["raw_avg_low_price"]) > 0
        ):
            ra = float(frow["raw_avg_high_price"])
            rb = float(frow["raw_avg_low_price"])
            fill_bucket_cont_spreads.append((ra - rb) / (0.5 * (ra + rb)) * 100.0)

        pos = open_pos.get(item_id)
        if pos is None:
            orow = obs_lookup.get((item_id, sub_ts))
            o_ask = (
                float(orow["avg_high_price"])
                if orow and pd.notna(orow["avg_high_price"])
                else f_ask
            )
            o_bid = (
                float(orow["avg_low_price"])
                if orow and pd.notna(orow["avg_low_price"])
                else f_bid
            )
            pos = {
                "item_id": item_id,
                "buy_submitted": sub_ts,
                "origin_ask_gp": o_ask,
                "origin_bid_gp": o_bid,
                "origin_mid_gp": 0.5 * (o_ask + o_bid),
                "inv_units": 0,
                "bought_units": 0,
                "sold_units": 0,
                "buy_cost_gp": 0,
                "buy_mid_notional": 0.0,
                "buy_slippage_gp": 0,
                "sell_gross_gp": 0,
                "sell_net_gp": 0,
                "sell_mid_notional": 0.0,
                "sell_slippage_gp": 0,
                "sell_tax_gp": 0,
                "sell_submitted": None,
                "sell_submit_bid_gp": None,
                "sell_submit_mid_gp": None,
                "last_sell_ts": None,
            }
            open_pos[item_id] = pos

        if side == "buy":
            pos["inv_units"] += qty
            pos["bought_units"] += qty
            pos["buy_cost_gp"] += price_gp * qty
            pos["buy_mid_notional"] += f_mid * qty
            pos["buy_slippage_gp"] += int(f["slippage_cost_gp"])
        else:
            if pos["sell_submitted"] is None:
                pos["sell_submitted"] = sub_ts
                srow = obs_lookup.get((item_id, sub_ts))
                s_ask = (
                    float(srow["avg_high_price"])
                    if srow and pd.notna(srow["avg_high_price"])
                    else f_ask
                )
                s_bid = (
                    float(srow["avg_low_price"])
                    if srow and pd.notna(srow["avg_low_price"])
                    else f_bid
                )
                pos["sell_submit_bid_gp"] = s_bid
                pos["sell_submit_mid_gp"] = 0.5 * (s_ask + s_bid)
            pos["inv_units"] -= qty
            pos["sold_units"] += qty
            pos["sell_gross_gp"] += price_gp * qty
            pos["sell_net_gp"] += int(f["cash_delta_gp"])
            pos["sell_mid_notional"] += f_mid * qty
            pos["sell_slippage_gp"] += int(f["slippage_cost_gp"])
            pos["sell_tax_gp"] += int(f["tax_gp"])
            pos["last_sell_ts"] = fill_ts

            if pos["inv_units"] == 0:
                b_cost = pos["buy_cost_gp"]
                b_mid_n = pos["buy_mid_notional"]
                s_gross = pos["sell_gross_gp"]
                s_net = pos["sell_net_gp"]
                s_mid_n = pos["sell_mid_notional"]
                o_mid = pos["origin_mid_gp"]
                o_ask = pos["origin_ask_gp"]
                o_bid = pos["origin_bid_gp"]
                units = pos["bought_units"]

                net_pnl = s_net - b_cost
                gross_mid_pnl = s_mid_n - b_mid_n
                buy_half_spread_pct = (
                    ((b_cost - b_mid_n) / b_mid_n * 100.0) if b_mid_n > 0 else 0.0
                )
                sell_half_spread_pct = (
                    ((s_mid_n - s_gross) / s_mid_n * 100.0) if s_mid_n > 0 else 0.0
                )
                realised_rt_spread_slip_pct = buy_half_spread_pct + sell_half_spread_pct
                realised_tax_pct = (pos["sell_tax_gp"] / s_mid_n * 100.0) if s_mid_n > 0 else 0.0

                origin_spread_pct = ((o_ask - o_bid) / o_mid * 100.0) if o_mid > 0 else 0.0
                modelled_rt_spread_slip_pct = (
                    ((o_ask * 1.0010 - o_bid * 0.9990) / o_mid * 100.0) if o_mid > 0 else 0.0
                )
                buy_vwap = b_cost / units
                sell_vwap = s_gross / units
                buy_lat_shortfall_pct = (
                    ((buy_vwap - o_ask) / o_mid * 100.0) if o_mid > 0 else 0.0
                )
                s_sub_bid = pos["sell_submit_bid_gp"] or o_bid
                s_sub_mid = pos["sell_submit_mid_gp"] or o_mid
                sell_lat_shortfall_pct = (
                    ((s_sub_bid - sell_vwap) / s_sub_mid * 100.0) if s_sub_mid > 0 else 0.0
                )

                completed_trades.append(
                    {
                        "item_id": item_id,
                        "buy_submitted": pos["buy_submitted"],
                        "last_sell_ts": pos["last_sell_ts"],
                        "units": units,
                        "buy_cost_gp": b_cost,
                        "sell_gross_gp": s_gross,
                        "sell_net_gp": s_net,
                        "tax_gp": pos["sell_tax_gp"],
                        "slippage_gp": pos["buy_slippage_gp"] + pos["sell_slippage_gp"],
                        "net_pnl_gp": net_pnl,
                        "gross_mid_pnl_gp": gross_mid_pnl,
                        "net_return": net_pnl / b_cost,
                        "gross_mid_return": (s_mid_n / b_mid_n - 1.0) if b_mid_n > 0 else 0.0,
                        "origin_quoted_spread_pct": origin_spread_pct,
                        "modelled_rt_spread_plus_slip_pct": modelled_rt_spread_slip_pct,
                        "realised_rt_spread_plus_slip_pct": realised_rt_spread_slip_pct,
                        "realised_total_cost_incl_tax_pct": (
                            realised_rt_spread_slip_pct + realised_tax_pct
                        ),
                        "buy_latency_shortfall_vs_origin_ask_pct": buy_lat_shortfall_pct,
                        "sell_latency_shortfall_vs_submit_bid_pct": sell_lat_shortfall_pct,
                    }
                )
                del open_pos[item_id]

    _, eq_grid, increments = _hourly_equity_series(
        result, window_start, window_end, initial_cash
    )
    sharpe_h, sharpe_d = _sharpe_from_equity(eq_grid, initial_cash)
    boot = _block_bootstrap_pnl(increments, initial_cash, seed=bootstrap_seed)

    trade_rets = np.array([t["net_return"] for t in completed_trades], dtype=np.float64)
    gross_rets = np.array([t["gross_mid_return"] for t in completed_trades], dtype=np.float64)
    n_comp = len(completed_trades)
    if n_comp >= 2 and float(np.std(trade_rets, ddof=1)) > 1e-15:
        per_trade_sharpe: float | None = float(
            np.mean(trade_rets) / np.std(trade_rets, ddof=1)
        )
    else:
        per_trade_sharpe = None

    peak_eq = np.maximum.accumulate(np.r_[float(initial_cash), eq_grid])
    dd_gp_arr = peak_eq[1:] - eq_grid
    max_dd_gp = float(np.max(dd_gp_arr)) if len(dd_gp_arr) else 0.0

    total_tax_gp = int(sum(int(f["tax_gp"]) for f in result.fills))
    total_slip_gp = int(sum(int(f["slippage_cost_gp"]) for f in result.fills))
    buy_gross_gp = int(sum(-int(f["cash_delta_gp"]) for f in result.fills if f["side"] == "buy"))
    comp_gross_mid_gp = float(sum(t["gross_mid_pnl_gp"] for t in completed_trades))
    comp_net_gp = int(sum(t["net_pnl_gp"] for t in completed_trades))
    comp_tax_gp = int(sum(t["tax_gp"] for t in completed_trades))
    comp_slip_gp = int(sum(t["slippage_gp"] for t in completed_trades))
    comp_pure_half_spread_gp = float(comp_gross_mid_gp - comp_net_gp - comp_tax_gp - comp_slip_gp)

    raw_spread_vectors = {
        "submitted_origin_quoted_spread_pct": submitted_origin_spreads,
        "expired_unfilled_ask_jump_pct": expired_adverse_ask_jumps,
        "fill_bucket_integer_quoted_spread_pct": fill_bucket_int_spreads,
        "fill_bucket_continuous_quoted_spread_pct": fill_bucket_cont_spreads,
        "completed_origin_quoted_spread_pct": [
            t["origin_quoted_spread_pct"] for t in completed_trades
        ],
        "completed_modelled_rt_spread_plus_slip_pct": [
            t["modelled_rt_spread_plus_slip_pct"] for t in completed_trades
        ],
        "completed_realised_rt_spread_plus_slip_pct": [
            t["realised_rt_spread_plus_slip_pct"] for t in completed_trades
        ],
        "completed_realised_total_cost_incl_tax_pct": [
            t["realised_total_cost_incl_tax_pct"] for t in completed_trades
        ],
        "completed_buy_latency_shortfall_pct": [
            t["buy_latency_shortfall_vs_origin_ask_pct"] for t in completed_trades
        ],
        "completed_sell_latency_shortfall_pct": [
            t["sell_latency_shortfall_vs_submit_bid_pct"] for t in completed_trades
        ],
    }

    summary = {
        "window_start_unix": window_start,
        "window_end_unix": window_end,
        "elapsed_hours": float(m["elapsed_hours"]),
        "initial_cash_gp": initial_cash,
        "net_gp": int(m["net_gp"]),
        "return_on_capital_pct": float(m["return_on_capital"] * 100.0),
        "realized_gp": int(m["realized_gp"]),
        "cash_pnl_gp": int(m["cash_pnl_gp"]),
        "end_inventory_units": int(m["end_inventory_units"]),
        "end_inventory_mark_gp": int(m["end_inventory_mark_gp"]),
        "cost_decomposition_completed_trades": {
            "completed_gross_mid_pnl_gp": round(comp_gross_mid_gp, 2),
            "completed_pure_half_spread_cost_gp": round(comp_pure_half_spread_gp, 2),
            "completed_explicit_slippage_cost_gp": comp_slip_gp,
            "completed_ge_tax_cost_gp": comp_tax_gp,
            "completed_net_pnl_gp": comp_net_gp,
        },
        "total_tax_gp": total_tax_gp,
        "total_explicit_slippage_gp": total_slip_gp,
        "turnover": float(m["turnover"]),
        "one_way_buy_turnover": float(buy_gross_gp / initial_cash),
        "mean_capital_tied_gp": float(m["mean_capital_tied_gp"]),
        "mean_capital_tied_pct": float(m["mean_capital_tied_gp"] / initial_cash * 100.0),
        "peak_capital_tied_pct": float(m["peak_capital_tied_gp"] / initial_cash * 100.0),
        "signal_funnel": funnel,
        "buy_orders_submitted": len(buy_submitted_orders),
        "buy_orders_expired_unfilled": len(buy_expired_unfilled),
        "positions_opened": n_comp + len(open_pos),
        "completed_round_trips": n_comp,
        "open_positions_at_end": len(open_pos),
        "buy_units_requested": int(m["buy_units_requested"]),
        "buy_units_filled": int(m["buy_units_filled"]),
        "sell_units_filled": int(m["sell_units_filled"]),
        "unit_fill_rate_pct": float(m["fill_rate"] * 100.0),
        "net_hit_rate_pct": (
            float(np.mean(trade_rets > 0.0) * 100.0) if n_comp > 0 else None
        ),
        "gross_mid_hit_rate_pct": (
            float(np.mean(gross_rets > 0.0) * 100.0) if n_comp > 0 else None
        ),
        "mean_trade_net_return_pct": (
            float(np.mean(trade_rets) * 100.0) if n_comp > 0 else None
        ),
        "median_trade_net_return_pct": (
            float(np.median(trade_rets) * 100.0) if n_comp > 0 else None
        ),
        "mean_trade_gross_mid_return_pct": (
            float(np.mean(gross_rets) * 100.0) if n_comp > 0 else None
        ),
        "per_trade_sharpe": per_trade_sharpe,
        "annualised_sharpe_hourly": sharpe_h,
        "annualised_sharpe_daily": sharpe_d,
        "max_drawdown_pct": float(m["max_drawdown"] * 100.0),
        "max_drawdown_gp": max_dd_gp,
        "block_bootstrap_168h": boot,
        "spread_distributions": {
            k: distribution_summary(v) for k, v in raw_spread_vectors.items()
        },
    }
    return summary, increments, completed_trades, raw_spread_vectors


def aggregate_fold_runs(
    fold_summaries: dict[int, dict],
    fold_increments: dict[int, np.ndarray],
    fold_trades: dict[int, list[dict]],
    fold_spreads: dict[int, dict[str, list[float]]],
    *,
    initial_cash_gp: int,
    bootstrap_seed: int = 777,
) -> dict:
    """Aggregate 3 non-overlapping 90-day validation folds into pooled 270-day metrics."""
    ordered_folds = sorted(fold_summaries.keys())
    concat_inc = np.concatenate([fold_increments[f] for f in ordered_folds])
    pooled_eq = float(initial_cash_gp) + np.cumsum(concat_inc)
    sharpe_h, sharpe_d = _sharpe_from_equity(pooled_eq, initial_cash_gp)
    boot = _block_bootstrap_pnl(concat_inc, initial_cash_gp, seed=bootstrap_seed)

    peak = np.maximum.accumulate(np.r_[float(initial_cash_gp), pooled_eq])
    dd_frac = (peak[1:] - pooled_eq) / peak[1:]
    dd_gp = peak[1:] - pooled_eq
    max_dd_pct = float(np.max(dd_frac) * 100.0) if len(dd_frac) else 0.0
    max_dd_gp = float(np.max(dd_gp)) if len(dd_gp) else 0.0

    all_trades = [t for f in ordered_folds for t in fold_trades[f]]
    n_comp = len(all_trades)
    trade_rets = np.array([t["net_return"] for t in all_trades], dtype=np.float64)
    gross_rets = np.array([t["gross_mid_return"] for t in all_trades], dtype=np.float64)
    if n_comp >= 2 and float(np.std(trade_rets, ddof=1)) > 1e-15:
        per_trade_sharpe: float | None = float(
            np.mean(trade_rets) / np.std(trade_rets, ddof=1)
        )
    else:
        per_trade_sharpe = None

    spread_keys = list(next(iter(fold_spreads.values())).keys())
    pooled_spreads = {
        k: distribution_summary([v for f in ordered_folds for v in fold_spreads[f][k]])
        for k in spread_keys
    }

    net_gp = int(sum(fold_summaries[f]["net_gp"] for f in ordered_folds))
    realized_gp = int(sum(fold_summaries[f]["realized_gp"] for f in ordered_folds))
    total_hours = float(sum(fold_summaries[f]["elapsed_hours"] for f in ordered_folds))
    buy_req = int(sum(fold_summaries[f]["buy_units_requested"] for f in ordered_folds))
    buy_fill = int(sum(fold_summaries[f]["buy_units_filled"] for f in ordered_folds))
    sell_fill = int(sum(fold_summaries[f]["sell_units_filled"] for f in ordered_folds))

    comp_gross_mid_gp = float(sum(t["gross_mid_pnl_gp"] for t in all_trades))
    comp_net_gp = int(sum(t["net_pnl_gp"] for t in all_trades))
    comp_tax_gp = int(sum(t["tax_gp"] for t in all_trades))
    comp_slip_gp = int(sum(t["slippage_gp"] for t in all_trades))

    return {
        "folds_included": ordered_folds,
        "total_elapsed_hours": total_hours,
        "initial_cash_gp": initial_cash_gp,
        "net_gp": net_gp,
        "return_on_capital_pct": float(net_gp / initial_cash_gp * 100.0),
        "realized_gp": realized_gp,
        "end_inventory_units_sum": int(
            sum(fold_summaries[f]["end_inventory_units"] for f in ordered_folds)
        ),
        "cost_decomposition_completed_trades": {
            "completed_gross_mid_pnl_gp": round(comp_gross_mid_gp, 2),
            "completed_pure_half_spread_cost_gp": round(
                comp_gross_mid_gp - comp_net_gp - comp_tax_gp - comp_slip_gp, 2
            ),
            "completed_explicit_slippage_cost_gp": comp_slip_gp,
            "completed_ge_tax_cost_gp": comp_tax_gp,
            "completed_net_pnl_gp": comp_net_gp,
        },
        "total_tax_gp": int(sum(fold_summaries[f]["total_tax_gp"] for f in ordered_folds)),
        "total_explicit_slippage_gp": int(
            sum(fold_summaries[f]["total_explicit_slippage_gp"] for f in ordered_folds)
        ),
        "turnover": float(sum(fold_summaries[f]["turnover"] for f in ordered_folds)),
        "one_way_buy_turnover": float(
            sum(fold_summaries[f]["one_way_buy_turnover"] for f in ordered_folds)
        ),
        "mean_capital_tied_pct": float(
            np.mean([fold_summaries[f]["mean_capital_tied_pct"] for f in ordered_folds])
        ),
        "selected_signals": int(
            sum(fold_summaries[f]["signal_funnel"]["selected_signals"] for f in ordered_folds)
        ),
        "buy_orders_submitted": int(
            sum(fold_summaries[f]["buy_orders_submitted"] for f in ordered_folds)
        ),
        "buy_orders_expired_unfilled": int(
            sum(fold_summaries[f]["buy_orders_expired_unfilled"] for f in ordered_folds)
        ),
        "completed_round_trips": n_comp,
        "open_positions_at_end": int(
            sum(fold_summaries[f]["open_positions_at_end"] for f in ordered_folds)
        ),
        "buy_units_requested": buy_req,
        "buy_units_filled": buy_fill,
        "sell_units_filled": sell_fill,
        "unit_fill_rate_pct": (float(buy_fill / buy_req * 100.0) if buy_req > 0 else 0.0),
        "net_hit_rate_pct": (
            float(np.mean(trade_rets > 0.0) * 100.0) if n_comp > 0 else None
        ),
        "gross_mid_hit_rate_pct": (
            float(np.mean(gross_rets > 0.0) * 100.0) if n_comp > 0 else None
        ),
        "mean_trade_net_return_pct": (
            float(np.mean(trade_rets) * 100.0) if n_comp > 0 else None
        ),
        "median_trade_net_return_pct": (
            float(np.median(trade_rets) * 100.0) if n_comp > 0 else None
        ),
        "mean_trade_gross_mid_return_pct": (
            float(np.mean(gross_rets) * 100.0) if n_comp > 0 else None
        ),
        "per_trade_sharpe": per_trade_sharpe,
        "annualised_sharpe_hourly": sharpe_h,
        "annualised_sharpe_daily": sharpe_d,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_gp": max_dd_gp,
        "block_bootstrap_168h": boot,
        "spread_distributions": pooled_spreads,
        "per_fold": {str(f): fold_summaries[f] for f in ordered_folds},
    }


def paired_signal_vs_null_bootstrap(
    signal_inc: np.ndarray,
    null_inc: np.ndarray,
    initial_cash_gp: int,
    *,
    block_hours: int = 168,
    draws: int = 2000,
    seed: int = 999,
) -> dict:
    """Paired 168h block bootstrap on hourly P/L difference (signal - null)."""
    if len(signal_inc) != len(null_inc):
        raise ValueError("Unpaired hourly equity increment arrays")
    diff = np.asarray(signal_inc, dtype=np.float64) - np.asarray(null_inc, dtype=np.float64)
    boot = _block_bootstrap_pnl(
        diff, initial_cash_gp, block_hours=block_hours, draws=draws, seed=seed
    )
    return {
        "paired_delta_gp": float(diff.sum()),
        "paired_delta_return_pct": float(diff.sum() / initial_cash_gp * 100.0),
        **boot,
    }


def select_training_grid_cell(cell_summaries: dict[str, dict]) -> str:
    """Preregistered training-only selection rule: max net_gp, tie-break lower turnover, H, edge."""

    def _key(item: tuple[str, dict]) -> tuple[int, float, int, int]:
        _, s = item
        return (
            int(s["net_gp"]),
            -float(s["turnover"]),
            int(s["holding_hours"]),
            int(s["min_net_edge_bps"]),
        )

    return max(cell_summaries.items(), key=_key)[0]


def run_p1_backtest_campaign(
    *,
    panel_path: str | Path,
    items_path: str | Path,
    protocol_path: str | Path,
    checkpoint_roots: list[str | Path],
    run_output_dir: str | Path,
    summary_json_path: str | Path,
    device_name: str = "cuda",
) -> dict:
    """Execute the full preregistered P1 economic backtest on RTX 5080 and write artifacts."""
    t0 = time.time()
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    if protocol.get("protected_holdout_start") != HOLDOUT_START:
        raise ValueError("Protocol holdout start mismatch")
    if protocol.get("e4_slots_consumed") != 0 or protocol.get("holdout_access_permitted"):
        raise ValueError("P1 protocol must consume 0 E4 slots and forbid holdout access")

    frame, manifest, manifest_sha = load_verified_panel(panel_path)
    items_path = Path(items_path)
    items_sha = file_hash(items_path)
    if manifest["sha256"] != protocol["inputs"]["panel_parquet_sha256"]:
        raise ValueError("Panel SHA-256 does not match preregistered P1 protocol")
    if items_sha != protocol["inputs"]["items_metadata_parquet_sha256"]:
        raise ValueError("Items metadata SHA-256 does not match preregistered P1 protocol")

    items_df = pd.read_parquet(items_path, columns=["id", "name", "buy_limit", "high_alch"])
    roots = [Path(r) for r in checkpoint_roots]
    run_dir = Path(run_output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = run_dir / "quantile_cache"

    market_wall = compute_validation_market_wall(frame)

    # 1. Extract / load causal quantiles for all 3 folds (inner-training + outer-validation).
    fold_bundles: dict[int, dict] = {}
    for fold_id in (1, 2, 3):
        _, val_start, val_end = REGISTERED_FOLDS[fold_id]
        inner_start = val_start - INNER_TUNING_DAYS * DAY
        origins_df, quantiles, q_meta = extract_or_load_fold_quantiles(
            fold_id=fold_id,
            frame=frame,
            manifest=manifest,
            items_df=items_df,
            checkpoint_roots=roots,
            cache_dir=cache_dir,
            device_name=device_name,
        )
        obs_inner = build_backtest_observations(frame, items_df, inner_start, val_start)
        obs_val = build_backtest_observations(frame, items_df, val_start, val_end)
        inner_mask = (origins_df["available_at"] >= inner_start) & (
            origins_df["available_at"] < val_start
        )
        val_mask = (origins_df["available_at"] >= val_start) & (
            origins_df["available_at"] < val_end
        )
        fold_bundles[fold_id] = {
            "inner_start": inner_start,
            "val_start": val_start,
            "val_end": val_end,
            "quantile_meta": q_meta,
            "obs_inner": obs_inner,
            "prep_inner": PreparedObservations(obs_inner),
            "obs_val": obs_val,
            "prep_val": PreparedObservations(obs_val),
            "origins_inner": origins_df.loc[inner_mask].reset_index(drop=True),
            "quantiles_inner": quantiles[inner_mask.to_numpy()],
            "origins_val": origins_df.loc[val_mask].reset_index(drop=True),
            "quantiles_val": quantiles[val_mask.to_numpy()],
        }

    def _eval_single(
        fold_id: int,
        split: str,
        holding_hours: int,
        min_edge_bps: int,
        *,
        assumptions: ExecutionAssumptions,
        initial_cash_gp: int = PRIMARY_CAPITAL_GP,
        tax_policy: TaxPolicy = DEFAULT_TAX,
        control: str = "signal",
        shuffle_seed: int = 101,
    ) -> tuple[dict, np.ndarray, list[dict], dict[str, list[float]], BacktestResult]:
        b = fold_bundles[fold_id]
        w_start = b["inner_start"] if split == "inner" else b["val_start"]
        w_end = b["val_start"] if split == "inner" else b["val_end"]
        obs_df = b["obs_inner"] if split == "inner" else b["obs_val"]
        prep = b["prep_inner"] if split == "inner" else b["prep_val"]
        orig_df = b["origins_inner"] if split == "inner" else b["origins_val"]
        q_raw = b["quantiles_inner"] if split == "inner" else b["quantiles_val"]

        q_used = transform_quantiles_for_control(
            orig_df, q_raw, control, seed=shuffle_seed + fold_id * 13
        )
        scores, allocs, funnel = build_policy_signals(
            orig_df,
            q_used,
            window_start=w_start,
            window_end=w_end,
            holding_hours=holding_hours,
            min_net_edge_bps=min_edge_bps,
            tax_policy=tax_policy,
        )
        portfolio = make_portfolio_policy(holding_hours, initial_cash_gp=initial_cash_gp)
        res = simulate(prep, scores, assumptions, portfolio, tax_policy, allocation_bps=allocs)
        summary, inc, trades, spreads = analyze_backtest_result(
            res,
            obs_df,
            window_start=w_start,
            window_end=w_end,
            funnel=funnel,
            bootstrap_seed=400 + fold_id * 17 + holding_hours + min_edge_bps,
        )
        summary["holding_hours"] = holding_hours
        summary["min_net_edge_bps"] = min_edge_bps
        summary["control"] = control
        summary["execution_name"] = assumptions.name
        return summary, inc, trades, spreads, res

    primary_assumptions = make_crossed_assumptions(200)

    # 2. Evaluate EVERY cell of the 2x3=6 preregistered grid on inner-training AND outer-validation.
    inner_grid: dict[str, dict] = {}
    val_grid: dict[str, dict] = {}
    val_cell_cache: dict[str, dict] = {}

    for hold_h in TUNING_HOLDING_HOURS:
        for edge_bps in TUNING_MIN_EDGE_BPS:
            cell_id = f"H{hold_h}h_edge{edge_bps}bps"
            in_sum, in_inc, in_tr, in_sp = {}, {}, {}, {}
            va_sum, va_inc, va_tr, va_sp = {}, {}, {}, {}
            va_res = {}
            for fold_id in (1, 2, 3):
                s_i, inc_i, tr_i, sp_i, _ = _eval_single(
                    fold_id, "inner", hold_h, edge_bps, assumptions=primary_assumptions
                )
                in_sum[fold_id], in_inc[fold_id], in_tr[fold_id], in_sp[fold_id] = (
                    s_i,
                    inc_i,
                    tr_i,
                    sp_i,
                )
                s_v, inc_v, tr_v, sp_v, res_v = _eval_single(
                    fold_id, "val", hold_h, edge_bps, assumptions=primary_assumptions
                )
                va_sum[fold_id], va_inc[fold_id], va_tr[fold_id], va_sp[fold_id] = (
                    s_v,
                    inc_v,
                    tr_v,
                    sp_v,
                )
                va_res[fold_id] = res_v

            agg_in = aggregate_fold_runs(
                in_sum, in_inc, in_tr, in_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
            )
            agg_in["holding_hours"] = hold_h
            agg_in["min_net_edge_bps"] = edge_bps
            inner_grid[cell_id] = agg_in

            agg_va = aggregate_fold_runs(
                va_sum, va_inc, va_tr, va_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
            )
            agg_va["holding_hours"] = hold_h
            agg_va["min_net_edge_bps"] = edge_bps
            val_grid[cell_id] = agg_va
            val_cell_cache[cell_id] = {
                "sum": va_sum,
                "inc": va_inc,
                "tr": va_tr,
                "sp": va_sp,
                "res": va_res,
            }

    # Training-only selection: per-fold walk-forward AND pooled inner-training selection.
    per_fold_selected_cells: dict[int, str] = {}
    wf_sum, wf_inc, wf_tr, wf_sp = {}, {}, {}, {}
    for fold_id in (1, 2, 3):
        fold_in_cells = {
            cid: {
                "net_gp": inner_grid[cid]["per_fold"][str(fold_id)]["net_gp"],
                "turnover": inner_grid[cid]["per_fold"][str(fold_id)]["turnover"],
                "holding_hours": inner_grid[cid]["holding_hours"],
                "min_net_edge_bps": inner_grid[cid]["min_net_edge_bps"],
            }
            for cid in inner_grid
        }
        chosen_cid = select_training_grid_cell(fold_in_cells)
        per_fold_selected_cells[fold_id] = chosen_cid
        wf_sum[fold_id] = val_cell_cache[chosen_cid]["sum"][fold_id]
        wf_inc[fold_id] = val_cell_cache[chosen_cid]["inc"][fold_id]
        wf_tr[fold_id] = val_cell_cache[chosen_cid]["tr"][fold_id]
        wf_sp[fold_id] = val_cell_cache[chosen_cid]["sp"][fold_id]

        # Persist primary walk-forward validation ledgers outside Git in run_dir.
        f_ledger_dir = run_dir / f"walkforward_fold{fold_id}_{chosen_cid}"
        f_ledger_dir.mkdir(parents=True, exist_ok=True)
        res_obj = val_cell_cache[chosen_cid]["res"][fold_id]
        pd.DataFrame(res_obj.fills).to_parquet(f_ledger_dir / "fills.parquet", index=False)
        pd.DataFrame(res_obj.orders).to_parquet(f_ledger_dir / "orders.parquet", index=False)
        pd.DataFrame(res_obj.equity).to_parquet(f_ledger_dir / "equity.parquet", index=False)
        pd.DataFrame(wf_tr[fold_id]).to_parquet(
            f_ledger_dir / "completed_trades.parquet", index=False
        )

    walkforward_selected_val = aggregate_fold_runs(
        wf_sum, wf_inc, wf_tr, wf_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
    )
    walkforward_selected_val["per_fold_selected_cell"] = {
        str(k): v for k, v in per_fold_selected_cells.items()
    }
    walkforward_concat_inc = np.concatenate([wf_inc[f] for f in (1, 2, 3)])

    pooled_inner_selected_cid = select_training_grid_cell(inner_grid)
    pooled_inner_selected_val = val_grid[pooled_inner_selected_cid]
    # Also select best *active* cell (>= 10 inner trades) if inner max picked a near-inactive cell,
    # purely as a transparent diagnostic alongside the strict preregistered selection.
    active_inner = {
        cid: s for cid, s in inner_grid.items() if s["completed_round_trips"] >= 10
    }
    most_active_cid = (
        select_training_grid_cell(active_inner) if active_inner else "H24h_edge0bps"
    )
    # Persist ledgers for base H4h_edge0bps and H24h_edge0bps cells in run_dir as well.
    for ref_cid in ("H4h_edge0bps", "H24h_edge0bps"):
        for fold_id in (1, 2, 3):
            ref_dir = run_dir / f"grid_fold{fold_id}_{ref_cid}"
            ref_dir.mkdir(parents=True, exist_ok=True)
            r_obj = val_cell_cache[ref_cid]["res"][fold_id]
            pd.DataFrame(r_obj.fills).to_parquet(ref_dir / "fills.parquet", index=False)
            pd.DataFrame(r_obj.orders).to_parquet(ref_dir / "orders.parquet", index=False)
            pd.DataFrame(r_obj.equity).to_parquet(ref_dir / "equity.parquet", index=False)
            pd.DataFrame(val_cell_cache[ref_cid]["tr"][fold_id]).to_parquet(
                ref_dir / "completed_trades.parquet", index=False
            )

    # 3. Null Controls on BOTH walk-forward selected cells AND H4h_edge0bps / H24h_edge0bps!
    def _run_null_suite_for_spec(
        spec_cells_by_fold: dict[int, tuple[int, int]],
        ref_concat_inc: np.ndarray,
        assumptions: ExecutionAssumptions,
    ) -> dict:
        out_nulls: dict = {}
        # 3a. 5 deterministic time-shuffled replicates
        rep_aggregates = []
        rep_concat_incs = []
        for rep in range(5):
            r_sum, r_inc, r_tr, r_sp = {}, {}, {}, {}
            for fold_id in (1, 2, 3):
                h_h, e_b = spec_cells_by_fold[fold_id]
                s_n, inc_n, tr_n, sp_n, _ = _eval_single(
                    fold_id,
                    "val",
                    h_h,
                    e_b,
                    assumptions=assumptions,
                    control="null_time_shuffled",
                    shuffle_seed=1000 + rep * 101,
                )
                r_sum[fold_id], r_inc[fold_id], r_tr[fold_id], r_sp[fold_id] = (
                    s_n,
                    inc_n,
                    tr_n,
                    sp_n,
                )
            agg_rep = aggregate_fold_runs(
                r_sum, r_inc, r_tr, r_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
            )
            rep_aggregates.append(agg_rep)
            rep_concat_incs.append(np.concatenate([r_inc[f] for f in (1, 2, 3)]))

        mean_null_inc = np.mean(np.stack(rep_concat_incs, axis=0), axis=0)
        out_nulls["null_time_shuffled"] = {
            "replicates": 5,
            "mean_net_gp": float(np.mean([r["net_gp"] for r in rep_aggregates])),
            "std_net_gp": float(np.std([r["net_gp"] for r in rep_aggregates], ddof=1)),
            "min_net_gp": int(min(r["net_gp"] for r in rep_aggregates)),
            "max_net_gp": int(max(r["net_gp"] for r in rep_aggregates)),
            "mean_return_on_capital_pct": float(
                np.mean([r["return_on_capital_pct"] for r in rep_aggregates])
            ),
            "mean_completed_round_trips": float(
                np.mean([r["completed_round_trips"] for r in rep_aggregates])
            ),
            "mean_net_hit_rate_pct": (
                float(
                    np.mean(
                        [
                            r["net_hit_rate_pct"]
                            for r in rep_aggregates
                            if r["net_hit_rate_pct"] is not None
                        ]
                    )
                )
                if any(r["net_hit_rate_pct"] is not None for r in rep_aggregates)
                else None
            ),
            "mean_gross_mid_hit_rate_pct": (
                float(
                    np.mean(
                        [
                            r["gross_mid_hit_rate_pct"]
                            for r in rep_aggregates
                            if r["gross_mid_hit_rate_pct"] is not None
                        ]
                    )
                )
                if any(r["gross_mid_hit_rate_pct"] is not None for r in rep_aggregates)
                else None
            ),
            "mean_annualised_sharpe_hourly": float(
                np.mean([r["annualised_sharpe_hourly"] or 0.0 for r in rep_aggregates])
            ),
            "paired_signal_minus_mean_shuffled": paired_signal_vs_null_bootstrap(
                ref_concat_inc, mean_null_inc, PRIMARY_CAPITAL_GP, seed=1201
            ),
            "per_replicate": rep_aggregates,
        }

        for ctrl_name in ("null_sign_flipped", "null_detrended_zero_drift"):
            c_sum, c_inc, c_tr, c_sp = {}, {}, {}, {}
            for fold_id in (1, 2, 3):
                h_h, e_b = spec_cells_by_fold[fold_id]
                s_c, inc_c, tr_c, sp_c, _ = _eval_single(
                    fold_id,
                    "val",
                    h_h,
                    e_b,
                    assumptions=assumptions,
                    control=ctrl_name,
                )
                c_sum[fold_id], c_inc[fold_id], c_tr[fold_id], c_sp[fold_id] = (
                    s_c,
                    inc_c,
                    tr_c,
                    sp_c,
                )
            agg_ctrl = aggregate_fold_runs(
                c_sum, c_inc, c_tr, c_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
            )
            agg_ctrl["paired_signal_minus_control"] = paired_signal_vs_null_bootstrap(
                ref_concat_inc,
                np.concatenate([c_inc[f] for f in (1, 2, 3)]),
                PRIMARY_CAPITAL_GP,
                seed=1301,
            )
            out_nulls[ctrl_name] = agg_ctrl
        return out_nulls

    wf_spec_map = {
        f: (
            val_grid[per_fold_selected_cells[f]]["holding_hours"],
            val_grid[per_fold_selected_cells[f]]["min_net_edge_bps"],
        )
        for f in (1, 2, 3)
    }
    null_controls_walkforward = _run_null_suite_for_spec(
        wf_spec_map, walkforward_concat_inc, primary_assumptions
    )

    # Also run null controls on unfiltered base edge0bps cells (H=4h and H=24h) so active
    # trade-count null comparisons are reported even if training selects a sparse threshold.
    null_controls_base_cells: dict[str, dict] = {}
    for base_h in (4, 24):
        base_cid = f"H{base_h}h_edge0bps"
        base_inc = np.concatenate([val_cell_cache[base_cid]["inc"][f] for f in (1, 2, 3)])
        null_controls_base_cells[base_cid] = _run_null_suite_for_spec(
            {1: (base_h, 0), 2: (base_h, 0), 3: (base_h, 0)},
            base_inc,
            primary_assumptions,
        )

    # 4. Secondary execution and capital sensitivities (participation, 10M GP, Lobster, passive_v3)
    def _run_sensitivities_for_spec(spec_map: dict[int, tuple[int, int]]) -> dict:
        out_sens: dict[str, dict] = {}
        for part_bps in (50, 200, 500):
            assump = make_crossed_assumptions(part_bps)
            p_sum, p_inc, p_tr, p_sp = {}, {}, {}, {}
            for fold_id in (1, 2, 3):
                h_h, e_b = spec_map[fold_id]
                s_p, inc_p, tr_p, sp_p, _ = _eval_single(
                    fold_id, "val", h_h, e_b, assumptions=assump
                )
                p_sum[fold_id], p_inc[fold_id], p_tr[fold_id], p_sp[fold_id] = (
                    s_p,
                    inc_p,
                    tr_p,
                    sp_p,
                )
            out_sens[f"crossed_participation_{part_bps}bps"] = aggregate_fold_runs(
                p_sum, p_inc, p_tr, p_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
            )

        cap_sum, cap_inc, cap_tr, cap_sp = {}, {}, {}, {}
        for fold_id in (1, 2, 3):
            h_h, e_b = spec_map[fold_id]
            s_k, inc_k, tr_k, sp_k, _ = _eval_single(
                fold_id,
                "val",
                h_h,
                e_b,
                assumptions=primary_assumptions,
                initial_cash_gp=SENSITIVITY_CAPITAL_GP,
            )
            cap_sum[fold_id], cap_inc[fold_id], cap_tr[fold_id], cap_sp[fold_id] = (
                s_k,
                inc_k,
                tr_k,
                sp_k,
            )
        out_sens["capital_10m_gp"] = aggregate_fold_runs(
            cap_sum, cap_inc, cap_tr, cap_sp, initial_cash_gp=SENSITIVITY_CAPITAL_GP
        )

        lobster_tax = TaxPolicy(exempt_item_ids=(LOBSTER_ITEM_ID,))
        lob_sum, lob_inc, lob_tr, lob_sp = {}, {}, {}, {}
        for fold_id in (1, 2, 3):
            h_h, e_b = spec_map[fold_id]
            s_l, inc_l, tr_l, sp_l, _ = _eval_single(
                fold_id,
                "val",
                h_h,
                e_b,
                assumptions=primary_assumptions,
                tax_policy=lobster_tax,
            )
            lob_sum[fold_id], lob_inc[fold_id], lob_tr[fold_id], lob_sp[fold_id] = (
                s_l,
                inc_l,
                tr_l,
                sp_l,
            )
        out_sens["lobster_tax_exempt_379"] = aggregate_fold_runs(
            lob_sum, lob_inc, lob_tr, lob_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
        )

        passive_assumptions = make_passive_v3_assumptions(200)
        pas_sum, pas_inc, pas_tr, pas_sp = {}, {}, {}, {}
        for fold_id in (1, 2, 3):
            h_h, e_b = spec_map[fold_id]
            s_pv, inc_pv, tr_pv, sp_pv, _ = _eval_single(
                fold_id, "val", h_h, e_b, assumptions=passive_assumptions
            )
            pas_sum[fold_id], pas_inc[fold_id], pas_tr[fold_id], pas_sp[fold_id] = (
                s_pv,
                inc_pv,
                tr_pv,
                sp_pv,
            )
        passive_val = aggregate_fold_runs(
            pas_sum, pas_inc, pas_tr, pas_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
        )
        passive_concat_inc = np.concatenate([pas_inc[f] for f in (1, 2, 3)])
        passive_null = _run_null_suite_for_spec(spec_map, passive_concat_inc, passive_assumptions)
        out_sens["passive_v3_200bps_contrast"] = {
            "signal": passive_val,
            "null_controls": passive_null,
        }
        return out_sens

    sensitivities = {
        "walkforward_selected": _run_sensitivities_for_spec(wf_spec_map),
        "H24h_edge0bps": _run_sensitivities_for_spec({1: (24, 0), 2: (24, 0), 3: (24, 0)}),
        "H4h_edge0bps": _run_sensitivities_for_spec({1: (4, 0), 2: (4, 0), 3: (4, 0)}),
    }

    prov = _code_tree_provenance()
    src_self = Path(__file__).resolve()
    prov["source_module_sha256"]["probabilistic_backtest.py"] = file_hash(src_self)

    payload = {
        "experiment_id": "P1_RECURSIVE_STUDENT_T_ECONOMIC_BACKTEST",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": file_hash(protocol_path),
        "generated_at_unix": time.time(),
        "elapsed_seconds": round(time.time() - t0, 3),
        "e4_slots_consumed": 0,
        "holdout_start": HOLDOUT_START,
        "holdout_touched": False,
        "provenance": {
            **prov,
            "panel_sha256": manifest["sha256"],
            "panel_manifest_sha256": manifest_sha,
            "items_metadata_sha256": items_sha,
            "fold_quantile_extraction": {
                str(f): fold_bundles[f]["quantile_meta"] for f in (1, 2, 3)
            },
        },
        "validation_market_wall_benchmark": market_wall,
        "inner_training_21d_grid": inner_grid,
        "outer_validation_full_6cell_grid": val_grid,
        "training_selected_policy": {
            "walkforward_per_fold_selected_cells": {
                str(k): v for k, v in per_fold_selected_cells.items()
            },
            "pooled_inner_selected_cell": pooled_inner_selected_cid,
            "most_active_inner_cell_ge10_trades": most_active_cid,
            "walkforward_outer_validation": walkforward_selected_val,
            "pooled_inner_selected_outer_validation": pooled_inner_selected_val,
        },
        "null_controls_walkforward_policy": null_controls_walkforward,
        "null_controls_base_edge0bps_cells": null_controls_base_cells,
        "sensitivities": sensitivities,
    }

    _json(run_dir / "p1_backtest_results.json", payload)
    _json(Path(summary_json_path), payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, action="append", required=True)
    parser.add_argument("--run-output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--device", type=str, default="cuda")
    args = parser.parse_args()

    res = run_p1_backtest_campaign(
        panel_path=args.panel,
        items_path=args.items,
        protocol_path=args.protocol,
        checkpoint_roots=args.checkpoint_root,
        run_output_dir=args.run_output,
        summary_json_path=args.summary_json,
        device_name=args.device,
    )
    wf = res["training_selected_policy"]["walkforward_outer_validation"]
    print(
        f"P1 COMPLETE: selected={wf['per_fold_selected_cell']} "
        f"trades={wf['completed_round_trips']} net_gp={wf['net_gp']} "
        f"ret={wf['return_on_capital_pct']:.4f}% "
        f"sharpe_h={wf['annualised_sharpe_hourly']} "
        f"holdout_touched={res['holdout_touched']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
