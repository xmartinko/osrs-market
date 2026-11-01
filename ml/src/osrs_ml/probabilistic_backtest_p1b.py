"""Phase One P1b causal 300s execution-resolution backtest for ``recursive_student_t``.

Tests the historical execution-latency hypothesis on the exact same three 90-day validation folds
(2025-10-29..2026-07-26) as P1, holding the preregistered policy, frozen ``recursive_student_t``
768-path predictive quantiles, and ``osrs_ml.{costs,execution,backtest}`` machinery strictly fixed
while resolving order execution on historical 300-second ``kaggle-5m`` bars instead of 3600-second
hourly bars.

Consumes 0 E4 slots and never reads rows at or after ``HOLDOUT_START = 1785024300``.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .backtest import BacktestResult, PreparedObservations, simulate
from .costs import DEFAULT_TAX, TaxPolicy, price_target
from .execution import ExecutionAssumptions
from .probabilistic_backtest import (
    DAY,
    INNER_TUNING_DAYS,
    LOBSTER_ITEM_ID,
    PRIMARY_CAPITAL_GP,
    SENSITIVITY_CAPITAL_GP,
    TUNING_HOLDING_HOURS,
    TUNING_MIN_EDGE_BPS,
    _block_bootstrap_pnl,
    _sharpe_from_equity,
    build_backtest_observations,
    build_policy_signals,
    distribution_summary,
    extract_or_load_fold_quantiles,
    make_crossed_assumptions,
    make_passive_v3_assumptions,
    make_portfolio_policy,
    paired_signal_vs_null_bootstrap,
    select_training_grid_cell,
    transform_quantiles_for_control,
    verify_holdout_untouched,
)
from .probabilistic_campaign import _code_tree_provenance
from .probabilistic_train import (
    HOLDOUT_START,
    HOUR,
    REGISTERED_FOLDS,
    _json,
    file_hash,
    load_verified_panel,
)

FIVE_MIN = 300
WARMUP_DAYS_5M = 3
MAX_VALIDATION_END = 1785024000
P1_FIXED_WALKFORWARD_CELLS: dict[int, str] = {
    1: "H4h_edge50bps",
    2: "H24h_edge50bps",
    3: "H24h_edge25bps",
}


def make_crossed_300s_assumptions(
    participation_bps: int = 200,
    *,
    buy_timeout_seconds: int = 7500,
    max_freshness_seconds: int = 7500,
    name_override: str | None = None,
) -> ExecutionAssumptions:
    """Ceteris-paribus crossed-spread assumptions resolved on 300s bars."""
    base = make_crossed_assumptions(participation_bps)
    name = (
        name_override
        if name_override is not None
        else f"p1b_crossed_300s_{participation_bps}bps_to{buy_timeout_seconds}s"
    )
    return ExecutionAssumptions(
        name=name,
        participation_bps=base.participation_bps,
        slippage_bps=base.slippage_bps,
        latency_seconds=base.latency_seconds,
        max_freshness_seconds=max_freshness_seconds,
        buy_timeout_seconds=buy_timeout_seconds,
        terminal_haircut_bps=base.terminal_haircut_bps,
        allow_unknown_metadata=base.allow_unknown_metadata,
        freshness_basis=base.freshness_basis,
        passive_prices=base.passive_prices,
        queue_fill_bps=base.queue_fill_bps,
        price_model=base.price_model,
        adverse_ticks=base.adverse_ticks,
        fill_model=base.fill_model,
    )


def load_verified_5m_execution_bars(
    parquet_5m_path: str | Path,
    selected_item_ids: list[int] | tuple[int, ...],
    *,
    min_ts: int,
    max_end_ts: int = MAX_VALIDATION_END,
    expected_sha256: str | None = None,
) -> pd.DataFrame:
    """Scan only the 74 Phase-One items and pre-holdout timestamps (< 1785024000 < 1785024300).

    Never imputes ``mid_price``, ``avg_high_price``, or ``avg_low_price``.
    """
    path = Path(parquet_5m_path)
    if not path.is_file():
        raise FileNotFoundError(f"5m execution parquet not found: {path}")
    if min_ts >= max_end_ts:
        raise ValueError(f"Invalid 5m scan bounds [{min_ts}, {max_end_ts})")
    if max_end_ts > HOLDOUT_START:
        raise ValueError(
            f"Requested max_end_ts {max_end_ts} exceeds protected holdout {HOLDOUT_START}"
        )
    if expected_sha256 is not None:
        actual_sha = file_hash(path)
        if actual_sha != expected_sha256:
            raise ValueError(
                f"5m parquet SHA-256 mismatch: expected {expected_sha256}, got {actual_sha}"
            )

    ids_sorted = sorted({int(i) for i in selected_item_ids})
    if not ids_sorted:
        raise ValueError("selected_item_ids must be non-empty")

    con = duckdb.connect(":memory:")
    try:
        df = con.execute(
            """
            SELECT
                CAST(item_id AS BIGINT) AS item_id,
                CAST(ts AS BIGINT) AS ts,
                CAST(avg_high_price AS DOUBLE) AS avg_high_price,
                CAST(avg_low_price AS DOUBLE) AS avg_low_price,
                CAST(high_price_volume AS BIGINT) AS high_price_volume,
                CAST(low_price_volume AS BIGINT) AS low_price_volume,
                CAST(mid_price AS DOUBLE) AS mid_price
            FROM read_parquet(?, hive_partitioning=false)
            WHERE item_id IN (SELECT UNNEST(?::BIGINT[]))
              AND ts >= ?
              AND ts < ?
              AND ts < ?
            ORDER BY item_id, ts
            """,
            [str(path), ids_sorted, int(min_ts), int(max_end_ts), int(HOLDOUT_START)],
        ).df()
    finally:
        con.close()

    if not df.empty:
        if (df["ts"] >= max_end_ts).any() or (df["ts"] >= HOLDOUT_START).any():
            raise ValueError("Holdout boundary violated in 5m execution scan")
        if (df["ts"] < min_ts).any():
            raise ValueError("5m scan returned rows prior to min_ts")
        if (df["ts"] % FIVE_MIN != 0).any():
            raise ValueError("Non-300s-aligned timestamp in 5m execution parquet")
        if df.duplicated(["item_id", "ts"]).any():
            raise ValueError("Duplicate (item_id, ts) rows in 5m execution parquet")
    return df


def build_backtest_observations_300s(
    frame_5m: pd.DataFrame,
    items_df: pd.DataFrame,
    window_start: int,
    window_end: int,
    *,
    selected_item_ids: list[int] | tuple[int, ...] | None = None,
    delay_seconds: int = 300,
    warmup_days: int = WARMUP_DAYS_5M,
    compact: bool = True,
) -> pd.DataFrame:
    """Build causal 300s observation bars in [window_start, window_end) for backtest.simulate.

    Tracks directional ask (``avg_high_price``) and bid (``avg_low_price``) independently via
    causal last-print prices and exact staleness ``delay_seconds + (ts - last_side_ts)`` while
    keeping current-bar directional volumes strictly uncarried (0 when absent/untraded) and leaving
    ``raw_mid_price`` unimputed (``NaN`` on one-sided or absent 300s buckets).
    """
    if window_start % FIVE_MIN != 0 or window_end % FIVE_MIN != 0:
        raise ValueError("300s window bounds must be multiples of 300s")
    if delay_seconds < 0 or delay_seconds % FIVE_MIN != 0:
        raise ValueError("delay_seconds must be a nonnegative multiple of 300s")
    verify_holdout_untouched(
        frame_5m if not frame_5m.empty else pd.DataFrame({"ts": np.array([window_start])}),
        window_start,
        window_end,
    )
    if "id" not in items_df.columns or "buy_limit" not in items_df.columns:
        raise ValueError("items_df must contain 'id' and 'buy_limit' columns")

    limit_map: dict[int, int | None] = {}
    for row in items_df[["id", "buy_limit"]].itertuples(index=False):
        iid = int(row.id)
        lim = row.buy_limit
        limit_map[iid] = int(lim) if pd.notna(lim) and float(lim) > 0 else None

    if selected_item_ids is not None:
        item_universe = sorted({int(i) for i in selected_item_ids})
    else:
        item_universe = sorted({int(i) for i in frame_5m["item_id"].unique()})
    if not item_universe:
        raise ValueError("Empty item universe for 300s observations")

    warmup_start = window_start - max(1, int(warmup_days)) * DAY
    if not frame_5m.empty:
        min_data_ts = int(frame_5m["ts"].min())
        warmup_start = min(window_start, max(warmup_start, (min_data_ts // FIVE_MIN) * FIVE_MIN))

    grid_ts = np.arange(warmup_start, window_end, FIVE_MIN, dtype=np.int64)
    g_len = len(grid_ts)
    if g_len == 0:
        raise ValueError(f"Empty 300s grid for [{window_start}, {window_end})")
    avail_grid = grid_ts + FIVE_MIN + int(delay_seconds)
    in_win_base = (
        (grid_ts >= window_start)
        & (grid_ts < window_end)
        & (avail_grid >= window_start)
        & (avail_grid < window_end)
        & (avail_grid < HOLDOUT_START)
    )
    in_win_indices = np.flatnonzero(in_win_base)
    if len(in_win_indices) == 0:
        raise ValueError(f"No in-window 300s ticks for [{window_start}, {window_end})")
    first_in_win_idx = int(in_win_indices[0])
    signal_tick_mask = (avail_grid % HOUR) == ((HOUR + 300) % HOUR)

    causal = frame_5m[(frame_5m["ts"] >= warmup_start) & (frame_5m["ts"] < window_end)].sort_values(
        ["item_id", "ts"], kind="mergesort"
    )
    grouped = {int(k): grp for k, grp in causal.groupby("item_id", sort=False)}
    anchor_item_id = item_universe[0]
    idx_arr = np.arange(g_len, dtype=np.int64)
    chunks: list[pd.DataFrame] = []

    for item_id in item_universe:
        g_high = np.full(g_len, np.nan, dtype=np.float64)
        g_low = np.full(g_len, np.nan, dtype=np.float64)
        g_mid = np.full(g_len, np.nan, dtype=np.float64)
        g_hvol = np.zeros(g_len, dtype=np.int64)
        g_lvol = np.zeros(g_len, dtype=np.int64)

        grp = grouped.get(item_id)
        if grp is not None and not grp.empty:
            ts_r = grp["ts"].to_numpy(dtype=np.int64)
            pos = (ts_r - warmup_start) // FIVE_MIN
            g_high[pos] = grp["avg_high_price"].to_numpy(dtype=np.float64)
            g_low[pos] = grp["avg_low_price"].to_numpy(dtype=np.float64)
            g_mid[pos] = grp["mid_price"].to_numpy(dtype=np.float64)
            rhv = grp["high_price_volume"].to_numpy(dtype=np.float64)
            rlv = grp["low_price_volume"].to_numpy(dtype=np.float64)
            g_hvol[pos] = np.where(np.isfinite(rhv) & (rhv > 0), np.rint(rhv), 0).astype(np.int64)
            g_lvol[pos] = np.where(np.isfinite(rlv) & (rlv > 0), np.rint(rlv), 0).astype(np.int64)

        valid_h = np.isfinite(g_high) & (g_high > 0) & (g_hvol > 0)
        valid_l = np.isfinite(g_low) & (g_low > 0) & (g_lvol > 0)

        last_h_idx = np.maximum.accumulate(np.where(valid_h, idx_arr, -1))
        last_l_idx = np.maximum.accumulate(np.where(valid_l, idx_arr, -1))
        has_h = last_h_idx >= 0
        has_l = last_l_idx >= 0

        round_h = np.maximum(1, np.rint(np.where(valid_h, g_high, 1.0))).astype(np.int64)
        round_l = np.maximum(1, np.rint(np.where(valid_l, g_low, 1.0))).astype(np.int64)
        safe_h_idx = np.maximum(0, last_h_idx)
        safe_l_idx = np.maximum(0, last_l_idx)

        last_h_gp = round_h[safe_h_idx]
        last_l_gp = round_l[safe_l_idx]
        h_fresh_vals = int(delay_seconds) + (grid_ts - grid_ts[safe_h_idx])
        l_fresh_vals = int(delay_seconds) + (grid_ts - grid_ts[safe_l_idx])
        inverted = has_h & has_l & (last_l_gp > last_h_gp)

        if compact and item_id != anchor_item_id:
            keep_mask = in_win_base & ((g_hvol > 0) | (g_lvol > 0) | signal_tick_mask)
            keep_mask[first_in_win_idx] = True
            sel = np.flatnonzero(keep_mask)
        else:
            sel = in_win_indices

        n_sel = len(sel)
        if n_sel == 0:
            continue

        high_col = pd.array(last_h_gp[sel], dtype="Int64")
        high_col[~has_h[sel]] = pd.NA
        low_col = pd.array(last_l_gp[sel], dtype="Int64")
        low_col[~has_l[sel]] = pd.NA
        h_fresh_col = pd.array(h_fresh_vals[sel], dtype="Int64")
        h_fresh_col[~has_h[sel]] = pd.NA
        l_fresh_col = pd.array(l_fresh_vals[sel], dtype="Int64")
        l_fresh_col[~has_l[sel]] = pd.NA

        buy_lim = limit_map.get(item_id)
        if buy_lim is not None:
            buy_lim_col = pd.array(np.full(n_sel, buy_lim, dtype=np.int64), dtype="Int64")
        else:
            buy_lim_col = pd.array([pd.NA] * n_sel, dtype="Int64")

        sub = pd.DataFrame(
            {
                "item_id": np.full(n_sel, item_id, dtype=np.int64),
                "timestamp": grid_ts[sel],
                "available_at": avail_grid[sel],
                "avg_high_price": high_col,
                "avg_low_price": low_col,
                "high_price_volume": pd.array(g_hvol[sel], dtype="Int64"),
                "low_price_volume": pd.array(g_lvol[sel], dtype="Int64"),
                "buy_limit": buy_lim_col,
                "source_interval_seconds": np.full(n_sel, FIVE_MIN, dtype=np.int64),
                "resolution_seconds": np.full(n_sel, FIVE_MIN, dtype=np.int64),
                "interval_unknown": np.zeros(n_sel, dtype=bool),
                "high_freshness_seconds": h_fresh_col,
                "low_freshness_seconds": l_fresh_col,
                "inverted_spread": inverted[sel],
                "raw_avg_high_price": g_high[sel],
                "raw_avg_low_price": g_low[sel],
                "raw_mid_price": g_mid[sel],
                "both_sides_active_now": (valid_h[sel] & valid_l[sel]),
            }
        )
        chunks.append(sub)

    if not chunks:
        raise ValueError(f"No 300s observations constructed for [{window_start}, {window_end})")
    out = pd.concat(chunks, ignore_index=True).sort_values(
        ["available_at", "item_id"], kind="mergesort"
    )
    return out.reset_index(drop=True)


def _vec_sale_proceeds_unit(
    sale_gp: np.ndarray, tax_policy: TaxPolicy = DEFAULT_TAX, item_id: int = 0
) -> np.ndarray:
    """Vectorized exact integer mirror of ``costs.sale_proceeds(px, 1, tax_policy, item_id)``."""
    px = np.asarray(sale_gp, dtype=np.int64)
    if int(item_id) in tax_policy.exempt_item_ids:
        return px.copy()
    raw_tax = (px * int(tax_policy.rate_bps)) // 10_000
    capped_tax = np.minimum(raw_tax, int(tax_policy.cap_gp))
    tax = np.where(px <= int(tax_policy.exempt_through_gp), 0, capped_tax)
    return px - tax


def compute_validation_market_wall_300s(
    frame_5m: pd.DataFrame,
    selected_item_ids: list[int] | tuple[int, ...],
    *,
    folds: dict[int, tuple[int, int, int]] = REGISTERED_FOLDS,
    tax_policy: TaxPolicy = DEFAULT_TAX,
) -> dict:
    """Measure empirical 300s spread, bar-sidedness, 4h/24h moves, and cost wall on val folds."""
    val_min = min(v[1] for v in folds.values())
    val_max = max(v[2] for v in folds.values())
    verify_holdout_untouched(frame_5m, val_min, val_max)

    ids_sorted = sorted({int(i) for i in selected_item_ids})
    grid = np.arange(val_min, val_max, FIVE_MIN, dtype=np.int64)
    g_len = len(grid)
    total_grid_cells = len(ids_sorted) * g_len

    sub = frame_5m[(frame_5m["ts"] >= val_min) & (frame_5m["ts"] < val_max)].sort_values(
        ["item_id", "ts"], kind="mergesort"
    )
    grouped = {int(k): grp for k, grp in sub.groupby("item_id", sort=False)}

    cont_spreads: list[np.ndarray] = []
    int_spreads: list[np.ndarray] = []
    rt_cost_walls: list[np.ndarray] = []
    abs_move_4h: list[np.ndarray] = []
    abs_move_24h: list[np.ndarray] = []
    clears_tax_24h: list[np.ndarray] = []
    clears_wall_24h: list[np.ndarray] = []
    clears_wall_slip_24h: list[np.ndarray] = []
    clears_wall_slip_4h: list[np.ndarray] = []

    n_both_sides = 0
    n_ask_only = 0
    n_bid_only = 0
    n_present_rows = int(len(sub))
    n_null_mid_in_present = int(sub["mid_price"].isna().sum())

    bars_4h = 4 * (HOUR // FIVE_MIN)  # 48 bars
    bars_24h = 24 * (HOUR // FIVE_MIN)  # 288 bars

    for item_id in ids_sorted:
        ask = np.full(g_len, np.nan, dtype=np.float64)
        bid = np.full(g_len, np.nan, dtype=np.float64)
        mid = np.full(g_len, np.nan, dtype=np.float64)
        hvol = np.zeros(g_len, dtype=np.int64)
        lvol = np.zeros(g_len, dtype=np.int64)

        grp = grouped.get(item_id)
        if grp is not None and not grp.empty:
            pos = (grp["ts"].to_numpy(dtype=np.int64) - val_min) // FIVE_MIN
            ask[pos] = grp["avg_high_price"].to_numpy(dtype=np.float64)
            bid[pos] = grp["avg_low_price"].to_numpy(dtype=np.float64)
            mid[pos] = grp["mid_price"].to_numpy(dtype=np.float64)
            rhv = grp["high_price_volume"].to_numpy(dtype=np.float64)
            rlv = grp["low_price_volume"].to_numpy(dtype=np.float64)
            hvol[pos] = np.where(np.isfinite(rhv) & (rhv > 0), np.rint(rhv), 0).astype(np.int64)
            lvol[pos] = np.where(np.isfinite(rlv) & (rlv > 0), np.rint(rlv), 0).astype(np.int64)

        has_ask = np.isfinite(ask) & (ask > 0) & (hvol > 0)
        has_bid = np.isfinite(bid) & (bid > 0) & (lvol > 0)
        n_both_sides += int(np.count_nonzero(has_ask & has_bid))
        n_ask_only += int(np.count_nonzero(has_ask & ~has_bid))
        n_bid_only += int(np.count_nonzero(~has_ask & has_bid))

        active = has_ask & has_bid & np.isfinite(mid) & (mid > 0) & (ask >= bid)
        if not np.any(active):
            continue

        ask_act = ask[active]
        bid_act = bid[active]
        mid_act = mid[active]
        cont_spreads.append((ask_act - bid_act) / mid_act)

        ask_gp = np.maximum(1, np.rint(ask_act)).astype(np.int64)
        bid_gp = np.maximum(1, np.rint(bid_act)).astype(np.int64)
        mid_gp = 0.5 * (ask_gp + bid_gp)
        int_spreads.append((ask_gp - bid_gp) / mid_gp)

        buy_c = np.maximum(1, np.ceil(ask_gp * 1.0010)).astype(np.int64)
        sell_f = np.maximum(1, np.floor(bid_gp * 0.9990)).astype(np.int64)
        proceeds_sf = _vec_sale_proceeds_unit(sell_f, tax_policy, item_id)
        walls = -(proceeds_sf.astype(np.float64) / buy_c.astype(np.float64) - 1.0)
        rt_cost_walls.append(walls)

        for step_bars, move_list, tax_list, wall_list, slip_list in (
            (bars_4h, abs_move_4h, None, None, clears_wall_slip_4h),
            (bars_24h, abs_move_24h, clears_tax_24h, clears_wall_24h, clears_wall_slip_24h),
        ):
            if g_len <= step_bars:
                continue
            pair_ok = active[:-step_bars] & active[step_bars:]
            if not np.any(pair_ok):
                continue
            m0 = mid[:-step_bars][pair_ok]
            m1 = mid[step_bars:][pair_ok]
            move_list.append(np.abs(m1 / m0 - 1.0))

            a0_gp = np.maximum(1, np.rint(ask[:-step_bars][pair_ok])).astype(np.int64)
            b1_gp = np.maximum(1, np.rint(bid[step_bars:][pair_ok])).astype(np.int64)
            m0_gp = np.maximum(1, np.rint(m0)).astype(np.int64)
            m1_gp = np.maximum(1, np.rint(m1)).astype(np.int64)

            if tax_list is not None:
                proc_m1 = _vec_sale_proceeds_unit(m1_gp, tax_policy, item_id)
                tax_list.append((proc_m1 > m0_gp).astype(np.float64))
            if wall_list is not None:
                proc_b1 = _vec_sale_proceeds_unit(b1_gp, tax_policy, item_id)
                wall_list.append((proc_b1 > a0_gp).astype(np.float64))
            bc_arr = np.maximum(1, np.ceil(a0_gp * 1.0010)).astype(np.int64)
            sf_arr = np.maximum(1, np.floor(b1_gp * 0.9990)).astype(np.int64)
            proc_sf = _vec_sale_proceeds_unit(sf_arr, tax_policy, item_id)
            slip_list.append((proc_sf > bc_arr).astype(np.float64))

    n_zero_both = total_grid_cells - n_both_sides - n_ask_only - n_bid_only
    return {
        "resolution_seconds": FIVE_MIN,
        "window_start_unix": val_min,
        "window_end_unix": val_max,
        "bar_sidedness_coverage": {
            "total_74item_300s_grid_cells": total_grid_cells,
            "present_parquet_rows_in_window": n_present_rows,
            "present_rows_with_null_mid_price": n_null_mid_in_present,
            "both_sides_printed_cells": n_both_sides,
            "both_sides_printed_pct": float(n_both_sides / total_grid_cells * 100.0),
            "ask_only_printed_cells": n_ask_only,
            "ask_only_printed_pct": float(n_ask_only / total_grid_cells * 100.0),
            "bid_only_printed_cells": n_bid_only,
            "bid_only_printed_pct": float(n_bid_only / total_grid_cells * 100.0),
            "neither_side_printed_cells": n_zero_both,
            "neither_side_printed_pct": float(n_zero_both / total_grid_cells * 100.0),
        },
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


class CausalObsIndex:
    """Fast per-item O(log N) causal lookup index over an observation DataFrame."""

    def __init__(self, obs_df: pd.DataFrame):
        self.by_item: dict[int, dict[str, np.ndarray]] = {}
        sorted_df = obs_df.sort_values(["item_id", "available_at"], kind="mergesort")
        for item_id_raw, grp in sorted_df.groupby("item_id", sort=False):
            iid = int(item_id_raw)
            self.by_item[iid] = {
                "avail": grp["available_at"].to_numpy(dtype=np.int64),
                "ts": grp["timestamp"].to_numpy(dtype=np.int64),
                "ask": grp["avg_high_price"].to_numpy(dtype=np.float64, na_value=np.nan),
                "bid": grp["avg_low_price"].to_numpy(dtype=np.float64, na_value=np.nan),
                "hvol": grp["high_price_volume"].to_numpy(dtype=np.int64, na_value=0),
                "lvol": grp["low_price_volume"].to_numpy(dtype=np.int64, na_value=0),
                "raw_ask": grp["raw_avg_high_price"].to_numpy(dtype=np.float64),
                "raw_bid": grp["raw_avg_low_price"].to_numpy(dtype=np.float64),
                "raw_mid": grp["raw_mid_price"].to_numpy(dtype=np.float64),
                "inverted": grp["inverted_spread"].to_numpy(dtype=bool),
                "h_fresh": grp["high_freshness_seconds"].to_numpy(
                    dtype=np.float64, na_value=np.nan
                ),
                "l_fresh": grp["low_freshness_seconds"].to_numpy(
                    dtype=np.float64, na_value=np.nan
                ),
                "src_int": grp["source_interval_seconds"].to_numpy(dtype=np.int64),
            }

    def causal_quote_at(
        self, item_id: int, query_avail: int
    ) -> tuple[float, float, float, float, float, int, int, bool] | None:
        """Return latest causal (ask, bid, raw_ask, raw_bid, raw_mid, hvol, lvol, exact_tick)."""
        rec = self.by_item.get(int(item_id))
        if rec is None:
            return None
        av = rec["avail"]
        k = int(np.searchsorted(av, int(query_avail), side="right")) - 1
        if k < 0:
            return None
        exact = int(av[k]) == int(query_avail)
        return (
            float(rec["ask"][k]),
            float(rec["bid"][k]),
            float(rec["raw_ask"][k]) if exact else float("nan"),
            float(rec["raw_bid"][k]) if exact else float("nan"),
            float(rec["raw_mid"][k]) if exact else float("nan"),
            int(rec["hvol"][k]) if exact else 0,
            int(rec["lvol"][k]) if exact else 0,
            exact,
        )


def build_hourly_origin_quote_map(origins_df: pd.DataFrame) -> dict[tuple[int, int], tuple[int, int]]:
    """Map (item_id, available_at) -> (hourly_ask_gp, hourly_bid_gp) for signal origins."""
    if origins_df.empty:
        return {}
    iids = origins_df["item_id"].to_numpy(dtype=np.int64)
    avails = origins_df["available_at"].to_numpy(dtype=np.int64)
    asks = origins_df["avg_high_price"].to_numpy(dtype=np.int64)
    bids = origins_df["avg_low_price"].to_numpy(dtype=np.int64)
    return {
        (int(iids[k]), int(avails[k])): (int(asks[k]), int(bids[k]))
        for k in range(len(origins_df))
    }


def _hourly_equity_series_window(
    result: BacktestResult,
    window_start: int,
    window_end: int,
    initial_cash_gp: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resample any simulation equity curve onto exact hourly boundaries in (window_start, window_end]."""
    hour_ends = np.arange(window_start + HOUR, window_end + 1, HOUR, dtype=np.int64)
    if not result.equity:
        eq = np.full(len(hour_ends), float(initial_cash_gp), dtype=np.float64)
        return hour_ends, eq, np.zeros(len(hour_ends), dtype=np.float64)

    eq_ts = np.array([int(r["timestamp"]) for r in result.equity], dtype=np.int64)
    eq_vals = np.array([float(r["equity_gp"]) for r in result.equity], dtype=np.float64)
    idx = np.searchsorted(eq_ts, hour_ends, side="left") - 1
    eq = np.where(idx >= 0, eq_vals[np.maximum(0, idx)], float(initial_cash_gp))
    inc = np.diff(eq, prepend=float(initial_cash_gp))
    return hour_ends, eq, inc


def _classify_unfilled_buy_expiries(
    result: BacktestResult,
    obs_index: CausalObsIndex,
    assumptions: ExecutionAssumptions,
) -> tuple[dict, list[float]]:
    """Partition zero-fill buy expiries into price-above-ceiling vs 5m lot-floor vs zero-volume."""
    submitted_by_item: dict[int, list[dict]] = {}
    for o in result.orders:
        if o.get("event") == "buy_submitted":
            submitted_by_item.setdefault(int(o["item_id"]), []).append(o)

    unfilled_expiries = [
        o for o in result.orders if o.get("event") == "buy_expired" and int(o.get("filled", 0)) == 0
    ]

    counts = {
        "total_zero_fill_expiries": len(unfilled_expiries),
        "price_above_ceiling_all_prints": 0,
        "five_min_integer_capacity_floor_lt_1_despite_cum_ge_1": 0,
        "low_cumulative_compatible_volume_lt_1": 0,
        "no_fresh_prints_in_timeout_window": 0,
        "other_or_limit_blocked": 0,
    }
    first_eligible_ask_jumps_pct: list[float] = []
    side_is_low = bool(assumptions.passive_prices)

    for exp in unfilled_expiries:
        iid = int(exp["item_id"])
        exp_ts = int(exp["timestamp"])
        cands = [
            s
            for s in submitted_by_item.get(iid, [])
            if exp_ts - assumptions.buy_timeout_seconds - HOUR <= int(s["timestamp"]) < exp_ts
        ]
        if not cands:
            counts["other_or_limit_blocked"] += 1
            continue
        sub_o = cands[-1]
        sub_ts = int(sub_o["timestamp"])
        ceiling = int(sub_o["buy_ceiling_gp"])

        sub_q = obs_index.causal_quote_at(iid, sub_ts)
        rec = obs_index.by_item.get(iid)
        if rec is None:
            counts["no_fresh_prints_in_timeout_window"] += 1
            continue

        av = rec["avail"]
        ts = rec["ts"]
        elig_mask = (
            (av > sub_ts + assumptions.latency_seconds)
            & (ts >= sub_ts + assumptions.latency_seconds)
            & (av < exp_ts)
        )
        elig_idx = np.flatnonzero(elig_mask)
        if len(elig_idx) == 0:
            counts["no_fresh_prints_in_timeout_window"] += 1
            continue

        if sub_q is not None and math.isfinite(sub_q[0]) and sub_q[0] > 0:
            ask_sub = sub_q[0]
            bid_sub = sub_q[1] if math.isfinite(sub_q[1]) and sub_q[1] > 0 else ask_sub
            mid_sub = 0.5 * (ask_sub + bid_sub)
            first_ask = float(rec["ask"][elig_idx[0]])
            if math.isfinite(first_ask) and mid_sub > 0:
                first_eligible_ask_jumps_pct.append((first_ask - ask_sub) / mid_sub * 100.0)

        active_print_bars = 0
        compat_vol_sum = 0
        max_single_bar_cap = 0

        for k in elig_idx:
            vol_k = int(rec["lvol"][k] if side_is_low else rec["hvol"][k])
            if vol_k <= 0 or bool(rec["inverted"][k]):
                continue
            px_k = float(rec["bid"][k] if side_is_low else rec["ask"][k])
            fr_k = float(rec["l_fresh"][k] if side_is_low else rec["h_fresh"][k])
            unc = int(rec["src_int"][k]) if assumptions.freshness_basis == "upper_bound" else 0
            if not math.isfinite(px_k) or px_k < 1 or not math.isfinite(fr_k):
                continue
            if int(fr_k) + unc > assumptions.max_freshness_seconds:
                continue

            active_print_bars += 1
            if assumptions.fill_model == "volume_bounded_v3":
                if int(ts[k]) + int(rec["src_int"][k]) > sub_ts + assumptions.buy_timeout_seconds:
                    continue
                if int(round(px_k)) <= ceiling:
                    compat_vol_sum += vol_k
                    bar_cap = (vol_k * assumptions.participation_bps) // 10_000
                    max_single_bar_cap = max(max_single_bar_cap, bar_cap)
            else:
                tgt = price_target(
                    int(round(px_k)),
                    assumptions.slippage_bps,
                    buy=True,
                    ticks=assumptions.adverse_ticks,
                )
                exec_ask = (tgt + 9999) // 10_000
                if exec_ask <= ceiling:
                    compat_vol_sum += vol_k
                    bar_cap = (
                        vol_k * assumptions.participation_bps * assumptions.queue_fill_bps
                    ) // 100_000_000
                    max_single_bar_cap = max(max_single_bar_cap, bar_cap)

        if active_print_bars == 0:
            counts["no_fresh_prints_in_timeout_window"] += 1
        elif compat_vol_sum == 0:
            counts["price_above_ceiling_all_prints"] += 1
        elif max_single_bar_cap == 0:
            cum_cap = (
                (compat_vol_sum * assumptions.participation_bps) // 10_000
                if assumptions.fill_model == "volume_bounded_v3"
                else (
                    compat_vol_sum * assumptions.participation_bps * assumptions.queue_fill_bps
                )
                // 100_000_000
            )
            if cum_cap >= 1:
                counts["five_min_integer_capacity_floor_lt_1_despite_cum_ge_1"] += 1
            else:
                counts["low_cumulative_compatible_volume_lt_1"] += 1
        else:
            counts["other_or_limit_blocked"] += 1

    total_exp = counts["total_zero_fill_expiries"]
    counts["shares_of_zero_fill_expiries_pct"] = (
        {
            k: round(counts[k] / total_exp * 100.0, 3)
            for k in (
                "price_above_ceiling_all_prints",
                "five_min_integer_capacity_floor_lt_1_despite_cum_ge_1",
                "low_cumulative_compatible_volume_lt_1",
                "no_fresh_prints_in_timeout_window",
                "other_or_limit_blocked",
            )
        }
        if total_exp > 0
        else {}
    )
    return counts, first_eligible_ask_jumps_pct


def analyze_backtest_result_p1b(
    result: BacktestResult,
    obs_index: CausalObsIndex,
    hourly_origin_quotes: dict[tuple[int, int], tuple[int, int]],
    *,
    assumptions: ExecutionAssumptions,
    window_start: int,
    window_end: int,
    funnel: dict,
    bootstrap_seed: int = 42,
) -> tuple[dict, np.ndarray, list[dict], dict[str, list[float]]]:
    """Reconstruct round-trip lifecycles, P/L bridge, wait latencies, expiry causes, and spreads."""
    m = result.metrics
    initial_cash = int(m["portfolio"]["initial_cash_gp"])

    buy_submitted_orders = [o for o in result.orders if o.get("event") == "buy_submitted"]
    buy_expired_unfilled = [
        o for o in result.orders if o.get("event") == "buy_expired" and int(o.get("filled", 0)) == 0
    ]

    submitted_300s_spreads: list[float] = []
    submitted_hourly_spreads: list[float] = []
    for o in buy_submitted_orders:
        iid = int(o["item_id"])
        sub_ts = int(o["timestamp"])
        sq = obs_index.causal_quote_at(iid, sub_ts)
        if sq is not None and math.isfinite(sq[0]) and math.isfinite(sq[1]) and sq[0] >= sq[1] > 0:
            mid_s = 0.5 * (sq[0] + sq[1])
            submitted_300s_spreads.append((sq[0] - sq[1]) / mid_s * 100.0)
        hq = hourly_origin_quotes.get((iid, sub_ts))
        if hq is not None and hq[0] >= hq[1] > 0:
            mid_h = 0.5 * (hq[0] + hq[1])
            submitted_hourly_spreads.append((hq[0] - hq[1]) / mid_h * 100.0)

    expiry_decomp, expired_adverse_ask_jumps = _classify_unfilled_buy_expiries(
        result, obs_index, assumptions
    )

    open_pos: dict[int, dict] = {}
    completed_trades: list[dict] = []
    fill_bucket_int_spreads: list[float] = []
    fill_bucket_cont_spreads: list[float] = []
    first_buy_wait_secs: list[float] = []
    n_fills_both_sides_printed = 0

    for f in result.fills:
        iid = int(f["item_id"])
        side = str(f["side"])
        qty = int(f["quantity"])
        price_gp = int(f["price_gp"])
        fill_ts = int(f["timestamp"])
        sub_ts = int(f["submitted"])

        fq = obs_index.causal_quote_at(iid, fill_ts)
        f_ask = fq[0] if fq is not None and math.isfinite(fq[0]) else float(price_gp)
        f_bid = fq[1] if fq is not None and math.isfinite(fq[1]) else float(price_gp)
        f_mid = 0.5 * (f_ask + f_bid)
        if f_mid > 0 and f_ask >= f_bid:
            fill_bucket_int_spreads.append((f_ask - f_bid) / f_mid * 100.0)
        if fq is not None and fq[5] > 0 and fq[6] > 0 and math.isfinite(fq[4]) and fq[4] > 0:
            n_fills_both_sides_printed += 1
            if math.isfinite(fq[2]) and math.isfinite(fq[3]) and fq[2] >= fq[3] > 0:
                fill_bucket_cont_spreads.append((fq[2] - fq[3]) / (0.5 * (fq[2] + fq[3])) * 100.0)

        pos = open_pos.get(iid)
        if pos is None:
            sq = obs_index.causal_quote_at(iid, sub_ts)
            o_ask = sq[0] if sq is not None and math.isfinite(sq[0]) else f_ask
            o_bid = sq[1] if sq is not None and math.isfinite(sq[1]) else f_bid
            hq = hourly_origin_quotes.get((iid, sub_ts))
            h_ask = float(hq[0]) if hq is not None else o_ask
            h_bid = float(hq[1]) if hq is not None else o_bid
            pos = {
                "item_id": iid,
                "buy_submitted": sub_ts,
                "first_buy_fill_ts": None,
                "origin_ask_gp": o_ask,
                "origin_bid_gp": o_bid,
                "origin_mid_gp": 0.5 * (o_ask + o_bid),
                "hourly_origin_ask_gp": h_ask,
                "hourly_origin_bid_gp": h_bid,
                "hourly_origin_mid_gp": 0.5 * (h_ask + h_bid),
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
            open_pos[iid] = pos

        if side == "buy":
            if pos["first_buy_fill_ts"] is None:
                pos["first_buy_fill_ts"] = fill_ts
                first_buy_wait_secs.append(float(fill_ts - sub_ts))
            pos["inv_units"] += qty
            pos["bought_units"] += qty
            pos["buy_cost_gp"] += price_gp * qty
            pos["buy_mid_notional"] += f_mid * qty
            pos["buy_slippage_gp"] += int(f["slippage_cost_gp"])
        else:
            if pos["sell_submitted"] is None:
                pos["sell_submitted"] = sub_ts
                ssq = obs_index.causal_quote_at(iid, sub_ts)
                s_ask = ssq[0] if ssq is not None and math.isfinite(ssq[0]) else f_ask
                s_bid = ssq[1] if ssq is not None and math.isfinite(ssq[1]) else f_bid
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
                h_mid = pos["hourly_origin_mid_gp"]
                h_ask = pos["hourly_origin_ask_gp"]
                h_bid = pos["hourly_origin_bid_gp"]
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
                hourly_origin_spread_pct = ((h_ask - h_bid) / h_mid * 100.0) if h_mid > 0 else 0.0
                hourly_modelled_rt_spread_slip_pct = (
                    ((h_ask * 1.0010 - h_bid * 0.9990) / h_mid * 100.0) if h_mid > 0 else 0.0
                )

                buy_vwap = b_cost / units
                sell_vwap = s_gross / units
                buy_lat_shortfall_pct = (
                    ((buy_vwap - o_ask) / o_mid * 100.0) if o_mid > 0 else 0.0
                )
                buy_lat_vs_hourly_ask_pct = (
                    ((buy_vwap - h_ask) / h_mid * 100.0) if h_mid > 0 else 0.0
                )
                s_sub_bid = pos["sell_submit_bid_gp"] or o_bid
                s_sub_mid = pos["sell_submit_mid_gp"] or o_mid
                sell_lat_shortfall_pct = (
                    ((s_sub_bid - sell_vwap) / s_sub_mid * 100.0) if s_sub_mid > 0 else 0.0
                )
                first_wait = (
                    float(pos["first_buy_fill_ts"] - pos["buy_submitted"])
                    if pos["first_buy_fill_ts"] is not None
                    else 0.0
                )

                completed_trades.append(
                    {
                        "item_id": iid,
                        "buy_submitted": pos["buy_submitted"],
                        "first_buy_fill_ts": pos["first_buy_fill_ts"],
                        "first_buy_wait_seconds": first_wait,
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
                        "hourly_origin_quoted_spread_pct": hourly_origin_spread_pct,
                        "hourly_modelled_rt_spread_plus_slip_pct": (
                            hourly_modelled_rt_spread_slip_pct
                        ),
                        "realised_rt_spread_plus_slip_pct": realised_rt_spread_slip_pct,
                        "realised_total_cost_incl_tax_pct": (
                            realised_rt_spread_slip_pct + realised_tax_pct
                        ),
                        "buy_latency_shortfall_vs_origin_ask_pct": buy_lat_shortfall_pct,
                        "buy_latency_shortfall_vs_hourly_ask_pct": buy_lat_vs_hourly_ask_pct,
                        "sell_latency_shortfall_vs_submit_bid_pct": sell_lat_shortfall_pct,
                    }
                )
                del open_pos[iid]

    _, eq_grid, increments = _hourly_equity_series_window(
        result, window_start, window_end, initial_cash
    )
    sharpe_h, sharpe_d = _sharpe_from_equity(eq_grid, initial_cash)
    boot = _block_bootstrap_pnl(increments, initial_cash, seed=bootstrap_seed)

    trade_rets = np.array([t["net_return"] for t in completed_trades], dtype=np.float64)
    gross_rets = np.array([t["gross_mid_return"] for t in completed_trades], dtype=np.float64)
    n_comp = len(completed_trades)
    if n_comp >= 2 and float(np.std(trade_rets, ddof=1)) > 1e-15:
        per_trade_sharpe: float | None = float(np.mean(trade_rets) / np.std(trade_rets, ddof=1))
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

    n_sub = len(buy_submitted_orders)
    n_exp0 = len(buy_expired_unfilled)
    zero_fill_exp_pct = float(n_exp0 / n_sub * 100.0) if n_sub > 0 else 0.0

    raw_spread_vectors = {
        "submitted_origin_quoted_spread_pct": submitted_300s_spreads,
        "submitted_hourly_origin_quoted_spread_pct": submitted_hourly_spreads,
        "expired_unfilled_ask_jump_pct": expired_adverse_ask_jumps,
        "fill_bucket_integer_quoted_spread_pct": fill_bucket_int_spreads,
        "fill_bucket_continuous_quoted_spread_pct": fill_bucket_cont_spreads,
        "first_buy_fill_wait_seconds": first_buy_wait_secs,
        "completed_origin_quoted_spread_pct": [
            t["origin_quoted_spread_pct"] for t in completed_trades
        ],
        "completed_modelled_rt_spread_plus_slip_pct": [
            t["modelled_rt_spread_plus_slip_pct"] for t in completed_trades
        ],
        "completed_hourly_origin_quoted_spread_pct": [
            t["hourly_origin_quoted_spread_pct"] for t in completed_trades
        ],
        "completed_hourly_modelled_rt_spread_plus_slip_pct": [
            t["hourly_modelled_rt_spread_plus_slip_pct"] for t in completed_trades
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
        "completed_buy_latency_shortfall_vs_hourly_ask_pct": [
            t["buy_latency_shortfall_vs_hourly_ask_pct"] for t in completed_trades
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
        "mean_buy_wait_seconds": float(m["mean_buy_wait_seconds"]),
        "signal_funnel": funnel,
        "buy_orders_submitted": n_sub,
        "buy_orders_expired_unfilled": n_exp0,
        "zero_fill_expiry_rate_pct": zero_fill_exp_pct,
        "order_any_fill_rate_pct": (float((n_sub - n_exp0) / n_sub * 100.0) if n_sub > 0 else 0.0),
        "zero_fill_expiry_decomposition": expiry_decomp,
        "positions_opened": n_comp + len(open_pos),
        "completed_round_trips": n_comp,
        "open_positions_at_end": len(open_pos),
        "buy_units_requested": int(m["buy_units_requested"]),
        "buy_units_filled": int(m["buy_units_filled"]),
        "sell_units_filled": int(m["sell_units_filled"]),
        "unit_fill_rate_pct": float(m["fill_rate"] * 100.0),
        "fills_total_events": len(result.fills),
        "fills_both_sides_printed_in_bar_pct": (
            float(n_fills_both_sides_printed / len(result.fills) * 100.0)
            if result.fills
            else None
        ),
        "net_hit_rate_pct": (float(np.mean(trade_rets > 0.0) * 100.0) if n_comp > 0 else None),
        "gross_mid_hit_rate_pct": (
            float(np.mean(gross_rets > 0.0) * 100.0) if n_comp > 0 else None
        ),
        "mean_trade_net_return_pct": (float(np.mean(trade_rets) * 100.0) if n_comp > 0 else None),
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
        "spread_distributions": {k: distribution_summary(v) for k, v in raw_spread_vectors.items()},
    }
    return summary, increments, completed_trades, raw_spread_vectors


def aggregate_fold_runs_p1b(
    fold_summaries: dict[int, dict],
    fold_increments: dict[int, np.ndarray],
    fold_trades: dict[int, list[dict]],
    fold_spreads: dict[int, dict[str, list[float]]],
    *,
    initial_cash_gp: int,
    bootstrap_seed: int = 777,
) -> dict:
    """Aggregate 3 non-overlapping 90-day validation folds into pooled 270-day P1b metrics."""
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
        per_trade_sharpe: float | None = float(np.mean(trade_rets) / np.std(trade_rets, ddof=1))
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
    n_sub = int(sum(fold_summaries[f]["buy_orders_submitted"] for f in ordered_folds))
    n_exp0 = int(sum(fold_summaries[f]["buy_orders_expired_unfilled"] for f in ordered_folds))

    exp_keys = (
        "total_zero_fill_expiries",
        "price_above_ceiling_all_prints",
        "five_min_integer_capacity_floor_lt_1_despite_cum_ge_1",
        "low_cumulative_compatible_volume_lt_1",
        "no_fresh_prints_in_timeout_window",
        "other_or_limit_blocked",
    )
    pooled_exp = {
        k: int(sum(fold_summaries[f]["zero_fill_expiry_decomposition"][k] for f in ordered_folds))
        for k in exp_keys
    }
    tot_exp = pooled_exp["total_zero_fill_expiries"]
    pooled_exp["shares_of_zero_fill_expiries_pct"] = (
        {
            k: round(pooled_exp[k] / tot_exp * 100.0, 3)
            for k in exp_keys[1:]
        }
        if tot_exp > 0
        else {}
    )

    weighted_wait_num = sum(
        fold_summaries[f]["mean_buy_wait_seconds"] * fold_summaries[f]["buy_units_filled"]
        for f in ordered_folds
    )
    pooled_mean_buy_wait = float(weighted_wait_num / buy_fill) if buy_fill > 0 else 0.0

    comp_gross_mid_gp = float(sum(t["gross_mid_pnl_gp"] for t in all_trades))
    comp_net_gp = int(sum(t["net_pnl_gp"] for t in all_trades))
    comp_tax_gp = int(sum(t["tax_gp"] for t in all_trades))
    comp_slip_gp = int(sum(t["slippage_gp"] for t in all_trades))

    h_orig_med = pooled_spreads["completed_hourly_origin_quoted_spread_pct"]["p50"]
    sub_300s_med = pooled_spreads["completed_origin_quoted_spread_pct"]["p50"]
    real_rt_med = pooled_spreads["completed_realised_rt_spread_plus_slip_pct"]["p50"]

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
        "mean_buy_wait_seconds": pooled_mean_buy_wait,
        "selected_signals": int(
            sum(fold_summaries[f]["signal_funnel"]["selected_signals"] for f in ordered_folds)
        ),
        "buy_orders_submitted": n_sub,
        "buy_orders_expired_unfilled": n_exp0,
        "zero_fill_expiry_rate_pct": (float(n_exp0 / n_sub * 100.0) if n_sub > 0 else 0.0),
        "order_any_fill_rate_pct": (
            float((n_sub - n_exp0) / n_sub * 100.0) if n_sub > 0 else 0.0
        ),
        "zero_fill_expiry_decomposition": pooled_exp,
        "completed_round_trips": n_comp,
        "open_positions_at_end": int(
            sum(fold_summaries[f]["open_positions_at_end"] for f in ordered_folds)
        ),
        "buy_units_requested": buy_req,
        "buy_units_filled": buy_fill,
        "sell_units_filled": sell_fill,
        "unit_fill_rate_pct": (float(buy_fill / buy_req * 100.0) if buy_req > 0 else 0.0),
        "net_hit_rate_pct": (float(np.mean(trade_rets > 0.0) * 100.0) if n_comp > 0 else None),
        "gross_mid_hit_rate_pct": (
            float(np.mean(gross_rets > 0.0) * 100.0) if n_comp > 0 else None
        ),
        "mean_trade_net_return_pct": (float(np.mean(trade_rets) * 100.0) if n_comp > 0 else None),
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
        "realised_minus_hourly_origin_spread_median_delta_pp": (
            round(real_rt_med - h_orig_med, 4)
            if real_rt_med is not None and h_orig_med is not None
            else None
        ),
        "realised_minus_300s_submission_spread_median_delta_pp": (
            round(real_rt_med - sub_300s_med, 4)
            if real_rt_med is not None and sub_300s_med is not None
            else None
        ),
        "spread_distributions": pooled_spreads,
        "per_fold": {str(f): fold_summaries[f] for f in ordered_folds},
    }


def _parse_cell_id(cell_id: str) -> tuple[int, int]:
    """Parse 'H{4|24}h_edge{0|25|50}bps' -> (holding_hours, min_net_edge_bps)."""
    left, right = cell_id.split("_edge")
    hold_h = int(left.removeprefix("H").removesuffix("h"))
    edge_bps = int(right.removesuffix("bps"))
    return hold_h, edge_bps


def evaluate_falsifiable_predictions(
    *,
    p1b_walkforward: dict,
    p1b_fixed_p1_cells: dict,
    p1b_h24_edge0: dict,
    p1_ref_walkforward: dict,
    p1_ref_h24_edge0: dict,
    paired_vs_p1_walkforward: dict,
    paired_vs_p1_fixed_cells: dict,
    paired_vs_p1_h24_edge0: dict,
) -> dict:
    """Evaluate the 4 preregistered falsifiable predictions (P_fill, P_expiry, P_spread, P_pnl)."""

    def _eval_arm(p1b_arm: dict, p1_arm: dict, paired_boot: dict) -> dict:
        fill_p1b = float(p1b_arm["unit_fill_rate_pct"])
        fill_p1 = float(p1_arm["unit_fill_rate_pct"])
        exp_p1b = float(p1b_arm["zero_fill_expiry_rate_pct"])
        exp_p1 = float(p1_arm["zero_fill_expiry_rate_pct"])
        sp_p1b = p1b_arm["spread_distributions"]["completed_realised_rt_spread_plus_slip_pct"][
            "p50"
        ]
        sp_p1 = p1_arm["spread_distributions"]["completed_realised_rt_spread_plus_slip_pct"]["p50"]
        net_p1b = int(p1b_arm["net_gp"])
        net_p1 = int(p1_arm["net_gp"])
        p_gt0 = float(p1b_arm["block_bootstrap_168h"]["p_one_sided_gt_0"])

        p_fill_pass = fill_p1b >= 15.0
        p_exp_pass = exp_p1b <= 50.0
        p_spread_pass = sp_p1b is not None and float(sp_p1b) < 2.00
        p_pnl_pos = net_p1b > 0
        p_pnl_sig = net_p1b > 0 and p_gt0 < 0.05

        if p_fill_pass and p_exp_pass and p_spread_pass and p_pnl_sig:
            verdict_case = "case_1_latency_confirmed_and_monetisable"
        elif (fill_p1b > fill_p1 or exp_p1b < exp_p1) and not p_pnl_sig:
            verdict_case = "case_2_latency_improves_fills_but_spread_wall_still_kills_net_pnl"
        elif sp_p1b is not None and sp_p1 is not None and float(sp_p1b) >= float(sp_p1):
            verdict_case = "case_3_300s_spread_wider_or_unimproved_vs_hourly_vwap"
        else:
            verdict_case = "mixed_partial_latency_relief_without_statistical_profitability"

        return {
            "unit_fill_rate_pct": {
                "p1_3600s": round(fill_p1, 4),
                "p1b_300s": round(fill_p1b, 4),
                "delta_pp": round(fill_p1b - fill_p1, 4),
                "target_ge_15pct_met": p_fill_pass,
            },
            "zero_fill_expiry_rate_pct": {
                "p1_3600s": round(exp_p1, 4),
                "p1b_300s": round(exp_p1b, 4),
                "delta_pp": round(exp_p1b - exp_p1, 4),
                "target_le_50pct_met": p_exp_pass,
            },
            "realised_rt_spread_plus_slip_median_pct": {
                "p1_3600s": round(float(sp_p1), 4) if sp_p1 is not None else None,
                "p1b_300s": round(float(sp_p1b), 4) if sp_p1b is not None else None,
                "delta_pp": (
                    round(float(sp_p1b) - float(sp_p1), 4)
                    if sp_p1b is not None and sp_p1 is not None
                    else None
                ),
                "target_lt_2pct_met": p_spread_pass,
            },
            "net_pnl_gp": {
                "p1_3600s": net_p1,
                "p1b_300s": net_p1b,
                "delta_gp": net_p1b - net_p1,
                "p1b_p_one_sided_gt_0": p_gt0,
                "positive_net_gp": p_pnl_pos,
                "statistically_significant_p_lt_0_05": p_pnl_sig,
                "paired_p1b_minus_p1_block_bootstrap_168h": paired_boot,
            },
            "classified_case": verdict_case,
        }

    return {
        "walkforward_p1b_selected": _eval_arm(
            p1b_walkforward, p1_ref_walkforward, paired_vs_p1_walkforward
        ),
        "walkforward_p1_fixed_cells_ceteris_paribus": _eval_arm(
            p1b_fixed_p1_cells, p1_ref_walkforward, paired_vs_p1_fixed_cells
        ),
        "unfiltered_H24h_edge0bps": _eval_arm(
            p1b_h24_edge0, p1_ref_h24_edge0, paired_vs_p1_h24_edge0
        ),
    }


def run_p1b_backtest_campaign(
    *,
    panel_path: str | Path,
    parquet_5m_path: str | Path,
    items_path: str | Path,
    protocol_path: str | Path,
    checkpoint_roots: list[str | Path],
    p1_quantile_cache_dir: str | Path,
    run_output_dir: str | Path,
    summary_json_path: str | Path,
    device_name: str = "cuda",
    require_clean_git: bool = False,
) -> dict:
    """Execute the full preregistered P1b 300s execution-resolution backtest."""
    t0 = time.time()
    prov_start = _code_tree_provenance()
    if require_clean_git and prov_start.get("git_dirty"):
        raise RuntimeError(
            "Refusing to run P1b with git_dirty=True (--require-clean-git enforced)"
        )

    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    if protocol.get("protected_holdout_start") != HOLDOUT_START:
        raise ValueError("Protocol holdout start mismatch")
    if protocol.get("e4_slots_consumed") != 0 or protocol.get("holdout_access_permitted"):
        raise ValueError("P1b protocol must consume 0 E4 slots and forbid holdout access")

    frame_hourly, manifest, manifest_sha = load_verified_panel(panel_path)
    items_path = Path(items_path)
    items_sha = file_hash(items_path)
    if manifest["sha256"] != protocol["inputs"]["hourly_panel_parquet_sha256"]:
        raise ValueError("Hourly panel SHA-256 does not match preregistered P1b protocol")
    if items_sha != protocol["inputs"]["items_metadata_parquet_sha256"]:
        raise ValueError("Items metadata SHA-256 does not match preregistered P1b protocol")

    selected_ids = sorted(int(i) for i in manifest["selected_ids"])
    earliest_inner = min(v[1] for v in REGISTERED_FOLDS.values()) - INNER_TUNING_DAYS * DAY
    min_scan_ts = earliest_inner - WARMUP_DAYS_5M * DAY
    max_scan_ts = max(v[2] for v in REGISTERED_FOLDS.values())

    expected_5m_sha = protocol["inputs"]["staged_5m_execution_parquet"]["sha256"]
    frame_5m = load_verified_5m_execution_bars(
        parquet_5m_path,
        selected_ids,
        min_ts=min_scan_ts,
        max_end_ts=max_scan_ts,
        expected_sha256=expected_5m_sha,
    )

    items_df = pd.read_parquet(items_path, columns=["id", "name", "buy_limit", "high_alch"])
    roots = [Path(r) for r in checkpoint_roots]
    run_dir = Path(run_output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(p1_quantile_cache_dir)

    market_wall_300s = compute_validation_market_wall_300s(frame_5m, selected_ids)

    # 1. Load frozen P1 quantiles and construct 300s + 3600s reference observation bundles.
    fold_bundles: dict[int, dict] = {}
    expected_q_hashes = protocol["inputs"]["frozen_p1_quantile_caches_sha256"]

    for fold_id in (1, 2, 3):
        _, val_start, val_end = REGISTERED_FOLDS[fold_id]
        inner_start = val_start - INNER_TUNING_DAYS * DAY
        origins_df, quantiles, q_meta = extract_or_load_fold_quantiles(
            fold_id=fold_id,
            frame=frame_hourly,
            manifest=manifest,
            items_df=items_df,
            checkpoint_roots=roots,
            cache_dir=cache_dir,
            device_name=device_name,
        )
        if q_meta.get("quantiles_npz_sha256") != expected_q_hashes[str(fold_id)]:
            raise ValueError(
                f"Fold {fold_id} quantile cache SHA-256 mismatch against P1b protocol"
            )

        obs_inner_300s = build_backtest_observations_300s(
            frame_5m,
            items_df,
            inner_start,
            val_start,
            selected_item_ids=selected_ids,
            delay_seconds=300,
        )
        obs_val_300s = build_backtest_observations_300s(
            frame_5m,
            items_df,
            val_start,
            val_end,
            selected_item_ids=selected_ids,
            delay_seconds=300,
        )
        obs_val_300s_d0 = build_backtest_observations_300s(
            frame_5m,
            items_df,
            val_start,
            val_end,
            selected_item_ids=selected_ids,
            delay_seconds=0,
        )
        obs_val_3600s = build_backtest_observations(frame_hourly, items_df, val_start, val_end)

        inner_mask = (origins_df["available_at"] >= inner_start) & (
            origins_df["available_at"] < val_start
        )
        val_mask = (origins_df["available_at"] >= val_start) & (
            origins_df["available_at"] < val_end
        )
        orig_in = origins_df.loc[inner_mask].reset_index(drop=True)
        orig_va = origins_df.loc[val_mask].reset_index(drop=True)

        fold_bundles[fold_id] = {
            "inner_start": inner_start,
            "val_start": val_start,
            "val_end": val_end,
            "quantile_meta": q_meta,
            "prep_inner": PreparedObservations(obs_inner_300s),
            "idx_inner": CausalObsIndex(obs_inner_300s),
            "prep_val": PreparedObservations(obs_val_300s),
            "idx_val": CausalObsIndex(obs_val_300s),
            "prep_val_d0": PreparedObservations(obs_val_300s_d0),
            "idx_val_d0": CausalObsIndex(obs_val_300s_d0),
            "prep_val_3600s": PreparedObservations(obs_val_3600s),
            "idx_val_3600s": CausalObsIndex(obs_val_3600s),
            "origins_inner": orig_in,
            "hquotes_inner": build_hourly_origin_quote_map(orig_in),
            "quantiles_inner": quantiles[inner_mask.to_numpy()],
            "origins_val": orig_va,
            "hquotes_val": build_hourly_origin_quote_map(orig_va),
            "quantiles_val": quantiles[val_mask.to_numpy()],
            "obs_rows_val_300s": int(len(obs_val_300s)),
        }

    def _eval_single(
        fold_id: int,
        split: str,
        holding_hours: int,
        min_edge_bps: int,
        *,
        assumptions: ExecutionAssumptions,
        obs_mode: str = "300s_d300",
        initial_cash_gp: int = PRIMARY_CAPITAL_GP,
        tax_policy: TaxPolicy = DEFAULT_TAX,
        control: str = "signal",
        shuffle_seed: int = 101,
    ) -> tuple[dict, np.ndarray, list[dict], dict[str, list[float]], BacktestResult]:
        b = fold_bundles[fold_id]
        if split == "inner":
            w_start, w_end = b["inner_start"], b["val_start"]
            prep, o_idx = b["prep_inner"], b["idx_inner"]
            orig_df, h_quotes, q_raw = (
                b["origins_inner"],
                b["hquotes_inner"],
                b["quantiles_inner"],
            )
        else:
            w_start, w_end = b["val_start"], b["val_end"]
            orig_df, h_quotes, q_raw = b["origins_val"], b["hquotes_val"], b["quantiles_val"]
            if obs_mode == "300s_d300":
                prep, o_idx = b["prep_val"], b["idx_val"]
            elif obs_mode == "300s_d0":
                prep, o_idx = b["prep_val_d0"], b["idx_val_d0"]
            elif obs_mode == "3600s_ref":
                prep, o_idx = b["prep_val_3600s"], b["idx_val_3600s"]
            else:
                raise ValueError(f"Unknown obs_mode {obs_mode!r}")

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
        summary, inc, trades, spreads = analyze_backtest_result_p1b(
            res,
            o_idx,
            h_quotes,
            assumptions=assumptions,
            window_start=w_start,
            window_end=w_end,
            funnel=funnel,
            bootstrap_seed=400 + fold_id * 17 + holding_hours + min_edge_bps,
        )
        summary["holding_hours"] = holding_hours
        summary["min_net_edge_bps"] = min_edge_bps
        summary["control"] = control
        summary["execution_name"] = assumptions.name
        summary["obs_mode"] = obs_mode
        return summary, inc, trades, spreads, res

    primary_assumptions = make_crossed_300s_assumptions(200)

    # 2. Evaluate all 6 cells of the 2x3 grid on 21d inner-training AND 90d outer-validation (300s).
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

            agg_in = aggregate_fold_runs_p1b(
                in_sum, in_inc, in_tr, in_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
            )
            agg_in["holding_hours"] = hold_h
            agg_in["min_net_edge_bps"] = edge_bps
            inner_grid[cell_id] = agg_in

            agg_va = aggregate_fold_runs_p1b(
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

    # 2b. Causal 21d inner-training selection on 300s bars + P1-fixed-cells pure execution contrast.
    per_fold_selected_cells: dict[int, str] = {}
    wf_sum, wf_inc, wf_tr, wf_sp = {}, {}, {}, {}
    p1fix_sum, p1fix_inc, p1fix_tr, p1fix_sp = {}, {}, {}, {}

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

        p1_cid = P1_FIXED_WALKFORWARD_CELLS[fold_id]
        p1fix_sum[fold_id] = val_cell_cache[p1_cid]["sum"][fold_id]
        p1fix_inc[fold_id] = val_cell_cache[p1_cid]["inc"][fold_id]
        p1fix_tr[fold_id] = val_cell_cache[p1_cid]["tr"][fold_id]
        p1fix_sp[fold_id] = val_cell_cache[p1_cid]["sp"][fold_id]

        f_ledger_dir = run_dir / f"walkforward_fold{fold_id}_{chosen_cid}"
        f_ledger_dir.mkdir(parents=True, exist_ok=True)
        res_obj = val_cell_cache[chosen_cid]["res"][fold_id]
        pd.DataFrame(res_obj.fills).to_parquet(f_ledger_dir / "fills.parquet", index=False)
        pd.DataFrame(res_obj.orders).to_parquet(f_ledger_dir / "orders.parquet", index=False)
        pd.DataFrame(res_obj.equity).to_parquet(f_ledger_dir / "equity.parquet", index=False)
        pd.DataFrame(wf_tr[fold_id]).to_parquet(
            f_ledger_dir / "completed_trades.parquet", index=False
        )

    walkforward_selected_val = aggregate_fold_runs_p1b(
        wf_sum, wf_inc, wf_tr, wf_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
    )
    walkforward_selected_val["per_fold_selected_cell"] = {
        str(k): v for k, v in per_fold_selected_cells.items()
    }
    walkforward_concat_inc = np.concatenate([wf_inc[f] for f in (1, 2, 3)])

    p1_fixed_cells_val = aggregate_fold_runs_p1b(
        p1fix_sum, p1fix_inc, p1fix_tr, p1fix_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
    )
    p1_fixed_cells_val["per_fold_selected_cell"] = {
        str(k): v for k, v in P1_FIXED_WALKFORWARD_CELLS.items()
    }
    p1_fixed_concat_inc = np.concatenate([p1fix_inc[f] for f in (1, 2, 3)])

    pooled_inner_selected_cid = select_training_grid_cell(inner_grid)
    pooled_inner_selected_val = val_grid[pooled_inner_selected_cid]
    active_inner = {cid: s for cid, s in inner_grid.items() if s["completed_round_trips"] >= 10}
    most_active_cid = (
        select_training_grid_cell(active_inner) if active_inner else "H24h_edge0bps"
    )

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

    # 2c. Exact 3600s reference replays on the identical 6480-hour grid for paired P1b-vs-P1 tests
    # and identical 5-way expiry classification on 3600s bars!
    p1_3600s_assumptions = make_crossed_assumptions(200)

    def _eval_3600s_spec(spec_cells: dict[int, tuple[int, int]]) -> tuple[dict, np.ndarray]:
        r_sum, r_inc, r_tr, r_sp = {}, {}, {}, {}
        for fold_id in (1, 2, 3):
            h_h, e_b = spec_cells[fold_id]
            s_r, inc_r, tr_r, sp_r, _ = _eval_single(
                fold_id,
                "val",
                h_h,
                e_b,
                assumptions=p1_3600s_assumptions,
                obs_mode="3600s_ref",
            )
            r_sum[fold_id], r_inc[fold_id], r_tr[fold_id], r_sp[fold_id] = s_r, inc_r, tr_r, sp_r
        agg = aggregate_fold_runs_p1b(
            r_sum, r_inc, r_tr, r_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
        )
        return agg, np.concatenate([r_inc[f] for f in (1, 2, 3)])

    p1_fixed_spec_map = {f: _parse_cell_id(P1_FIXED_WALKFORWARD_CELLS[f]) for f in (1, 2, 3)}
    p1_ref_wf_agg, p1_ref_wf_inc = _eval_3600s_spec(p1_fixed_spec_map)
    p1_ref_h24_agg, p1_ref_h24_inc = _eval_3600s_spec({1: (24, 0), 2: (24, 0), 3: (24, 0)})
    p1_ref_h4_agg, p1_ref_h4_inc = _eval_3600s_spec({1: (4, 0), 2: (4, 0), 3: (4, 0)})

    # 3. Null Controls on P1b walk-forward, P1-fixed-cells walk-forward (if distinct), and base cells.
    def _run_null_suite_for_spec(
        spec_cells_by_fold: dict[int, tuple[int, int]],
        ref_concat_inc: np.ndarray,
        assumptions: ExecutionAssumptions,
        *,
        obs_mode: str = "300s_d300",
    ) -> dict:
        out_nulls: dict = {}
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
                    obs_mode=obs_mode,
                    control="null_time_shuffled",
                    shuffle_seed=1000 + rep * 101,
                )
                r_sum[fold_id], r_inc[fold_id], r_tr[fold_id], r_sp[fold_id] = (
                    s_n,
                    inc_n,
                    tr_n,
                    sp_n,
                )
            agg_rep = aggregate_fold_runs_p1b(
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
            "mean_unit_fill_rate_pct": float(
                np.mean([r["unit_fill_rate_pct"] for r in rep_aggregates])
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
                    obs_mode=obs_mode,
                    control=ctrl_name,
                )
                c_sum[fold_id], c_inc[fold_id], c_tr[fold_id], c_sp[fold_id] = (
                    s_c,
                    inc_c,
                    tr_c,
                    sp_c,
                )
            agg_ctrl = aggregate_fold_runs_p1b(
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

    wf_spec_map = {f: _parse_cell_id(per_fold_selected_cells[f]) for f in (1, 2, 3)}
    null_controls_walkforward = _run_null_suite_for_spec(
        wf_spec_map, walkforward_concat_inc, primary_assumptions
    )
    if wf_spec_map == p1_fixed_spec_map:
        null_controls_p1_fixed_cells = null_controls_walkforward
    else:
        null_controls_p1_fixed_cells = _run_null_suite_for_spec(
            p1_fixed_spec_map, p1_fixed_concat_inc, primary_assumptions
        )

    null_controls_base_cells: dict[str, dict] = {}
    for base_h in (4, 24):
        base_cid = f"H{base_h}h_edge0bps"
        base_inc = np.concatenate([val_cell_cache[base_cid]["inc"][f] for f in (1, 2, 3)])
        null_controls_base_cells[base_cid] = _run_null_suite_for_spec(
            {1: (base_h, 0), 2: (base_h, 0), 3: (base_h, 0)},
            base_inc,
            primary_assumptions,
        )

    # 4. Registered sensitivities (participation 50/200/500, tight 1800s timeout, delay 0s,
    # 10M GP, Lobster 379, passive_v3_200bps).
    def _run_sensitivities_for_spec(spec_map: dict[int, tuple[int, int]]) -> dict:
        out_sens: dict[str, dict] = {}
        for part_bps in (50, 200, 500):
            assump = make_crossed_300s_assumptions(part_bps)
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
            out_sens[f"crossed_participation_{part_bps}bps"] = aggregate_fold_runs_p1b(
                p_sum, p_inc, p_tr, p_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
            )

        tight_assump = make_crossed_300s_assumptions(
            200,
            buy_timeout_seconds=1800,
            max_freshness_seconds=1800,
            name_override="p1b_crossed_300s_200bps_tight1800s",
        )
        t_sum, t_inc, t_tr, t_sp = {}, {}, {}, {}
        for fold_id in (1, 2, 3):
            h_h, e_b = spec_map[fold_id]
            s_t, inc_t, tr_t, sp_t, _ = _eval_single(
                fold_id, "val", h_h, e_b, assumptions=tight_assump
            )
            t_sum[fold_id], t_inc[fold_id], t_tr[fold_id], t_sp[fold_id] = s_t, inc_t, tr_t, sp_t
        out_sens["tight_intraday_timeout_1800s_freshness_1800s"] = aggregate_fold_runs_p1b(
            t_sum, t_inc, t_tr, t_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
        )

        d0_sum, d0_inc, d0_tr, d0_sp = {}, {}, {}, {}
        for fold_id in (1, 2, 3):
            h_h, e_b = spec_map[fold_id]
            s_d, inc_d, tr_d, sp_d, _ = _eval_single(
                fold_id,
                "val",
                h_h,
                e_b,
                assumptions=primary_assumptions,
                obs_mode="300s_d0",
            )
            d0_sum[fold_id], d0_inc[fold_id], d0_tr[fold_id], d0_sp[fold_id] = (
                s_d,
                inc_d,
                tr_d,
                sp_d,
            )
        out_sens["availability_delay_0s_ts_plus_300"] = aggregate_fold_runs_p1b(
            d0_sum, d0_inc, d0_tr, d0_sp, initial_cash_gp=PRIMARY_CAPITAL_GP
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
        out_sens["capital_10m_gp"] = aggregate_fold_runs_p1b(
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
        out_sens["lobster_tax_exempt_379"] = aggregate_fold_runs_p1b(
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
        passive_val = aggregate_fold_runs_p1b(
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
        "p1_fixed_cells": (
            _run_sensitivities_for_spec(p1_fixed_spec_map)
            if wf_spec_map != p1_fixed_spec_map
            else None
        ),
        "H24h_edge0bps": _run_sensitivities_for_spec({1: (24, 0), 2: (24, 0), 3: (24, 0)}),
        "H4h_edge0bps": _run_sensitivities_for_spec({1: (4, 0), 2: (4, 0), 3: (4, 0)}),
    }
    if sensitivities["p1_fixed_cells"] is None:
        sensitivities["p1_fixed_cells"] = sensitivities["walkforward_selected"]

    h24_300s_inc = np.concatenate([val_cell_cache["H24h_edge0bps"]["inc"][f] for f in (1, 2, 3)])
    h4_300s_inc = np.concatenate([val_cell_cache["H4h_edge0bps"]["inc"][f] for f in (1, 2, 3)])
    paired_vs_p1_wf = paired_signal_vs_null_bootstrap(
        walkforward_concat_inc, p1_ref_wf_inc, PRIMARY_CAPITAL_GP, seed=2101
    )
    paired_vs_p1_fixed = paired_signal_vs_null_bootstrap(
        p1_fixed_concat_inc, p1_ref_wf_inc, PRIMARY_CAPITAL_GP, seed=2102
    )
    paired_vs_p1_h24 = paired_signal_vs_null_bootstrap(
        h24_300s_inc, p1_ref_h24_inc, PRIMARY_CAPITAL_GP, seed=2103
    )
    paired_vs_p1_h4 = paired_signal_vs_null_bootstrap(
        h4_300s_inc, p1_ref_h4_inc, PRIMARY_CAPITAL_GP, seed=2104
    )

    falsification_verdict = evaluate_falsifiable_predictions(
        p1b_walkforward=walkforward_selected_val,
        p1b_fixed_p1_cells=p1_fixed_cells_val,
        p1b_h24_edge0=val_grid["H24h_edge0bps"],
        p1_ref_walkforward=p1_ref_wf_agg,
        p1_ref_h24_edge0=p1_ref_h24_agg,
        paired_vs_p1_walkforward=paired_vs_p1_wf,
        paired_vs_p1_fixed_cells=paired_vs_p1_fixed,
        paired_vs_p1_h24_edge0=paired_vs_p1_h24,
    )

    prov = _code_tree_provenance()
    src_self = Path(__file__).resolve()
    src_p1 = src_self.parent / "probabilistic_backtest.py"
    prov["source_module_sha256"]["probabilistic_backtest.py"] = file_hash(src_p1)
    prov["source_module_sha256"]["probabilistic_backtest_p1b.py"] = file_hash(src_self)
    for core_mod in ("costs.py", "execution.py", "backtest.py"):
        prov["source_module_sha256"][core_mod] = file_hash(src_self.parent / core_mod)

    if require_clean_git and prov.get("git_dirty"):
        raise RuntimeError("Git working tree became dirty during P1b execution")

    payload = {
        "experiment_id": "P1B_RECURSIVE_STUDENT_T_300S_EXECUTION_BACKTEST",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": file_hash(protocol_path),
        "generated_at_unix": time.time(),
        "elapsed_seconds": round(time.time() - t0, 3),
        "e4_slots_consumed": 0,
        "holdout_start": HOLDOUT_START,
        "holdout_touched": False,
        "provenance": {
            **prov,
            "hourly_panel_sha256": manifest["sha256"],
            "hourly_panel_manifest_sha256": manifest_sha,
            "staged_5m_parquet_sha256": expected_5m_sha,
            "staged_5m_scanned_rows_pre_holdout": int(len(frame_5m)),
            "staged_5m_scanned_min_ts": int(frame_5m["ts"].min()),
            "staged_5m_scanned_max_ts": int(frame_5m["ts"].max()),
            "items_metadata_sha256": items_sha,
            "fold_quantile_extraction": {
                str(f): fold_bundles[f]["quantile_meta"] for f in (1, 2, 3)
            },
            "fold_compact_300s_val_observation_rows": {
                str(f): fold_bundles[f]["obs_rows_val_300s"] for f in (1, 2, 3)
            },
        },
        "validation_market_wall_300s_benchmark": market_wall_300s,
        "inner_training_21d_grid_300s": inner_grid,
        "outer_validation_full_6cell_grid_300s": val_grid,
        "training_selected_policy_300s": {
            "walkforward_per_fold_selected_cells": {
                str(k): v for k, v in per_fold_selected_cells.items()
            },
            "p1_fixed_walkforward_cells": {
                str(k): v for k, v in P1_FIXED_WALKFORWARD_CELLS.items()
            },
            "pooled_inner_selected_cell": pooled_inner_selected_cid,
            "most_active_inner_cell_ge10_trades": most_active_cid,
            "walkforward_outer_validation": walkforward_selected_val,
            "p1_fixed_cells_outer_validation": p1_fixed_cells_val,
            "pooled_inner_selected_outer_validation": pooled_inner_selected_val,
        },
        "p1_3600s_reference_replays_with_5way_expiry": {
            "walkforward_p1_cells": p1_ref_wf_agg,
            "H24h_edge0bps": p1_ref_h24_agg,
            "H4h_edge0bps": p1_ref_h4_agg,
            "paired_p1b_minus_p1_H4h_edge0bps_bootstrap_168h": paired_vs_p1_h4,
        },
        "falsifiable_hypothesis_evaluation": falsification_verdict,
        "null_controls_walkforward_policy_300s": null_controls_walkforward,
        "null_controls_p1_fixed_cells_300s": null_controls_p1_fixed_cells,
        "null_controls_base_edge0bps_cells_300s": null_controls_base_cells,
        "sensitivities_300s": sensitivities,
    }

    _json(run_dir / "p1b_backtest_results.json", payload)
    _json(Path(summary_json_path), payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--panel",
        default="/home/xmart/osrs-research/data/hourly.parquet",
        help="Verified Phase One hourly panel parquet",
    )
    parser.add_argument(
        "--parquet-5m",
        default="/home/xmart/osrs-research/data/p1b_5m/prices_5m_p1b.parquet",
        help="Verified staged 300s execution parquet",
    )
    parser.add_argument(
        "--items",
        default="/home/xmart/osrs-research/data/items.parquet",
        help="Verified items metadata parquet",
    )
    parser.add_argument(
        "--protocol",
        default=(
            "/home/xmart/osrs-research/code/research/osrs-forecasting/"
            "phase_one/p1b_backtest_protocol.json"
        ),
        help="Preregistered P1b protocol JSON",
    )
    parser.add_argument(
        "--checkpoint-root",
        action="append",
        dest="checkpoint_roots",
        help="Root directory containing completed e2_recursive_student_t_f*_s* run dirs",
    )
    parser.add_argument(
        "--p1-quantile-cache-dir",
        default="/home/xmart/osrs-research/runs/p1_backtest_recursive_student_t/quantile_cache",
        help="Directory containing verified P1 fold{1,2,3}_quantiles.npz caches",
    )
    parser.add_argument(
        "--run-output-dir",
        default="/home/xmart/osrs-research/runs/p1b_backtest_recursive_student_t",
        help="Directory outside Git to store ledgers and full results",
    )
    parser.add_argument(
        "--summary-json",
        default="/tmp/p1b_backtest_results.json",
        help="Summary JSON output path (defaults outside Git so working tree stays clean)",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--require-clean-git",
        action="store_true",
        help="Abort if git working tree has modified or untracked files",
    )
    args = parser.parse_args(argv)

    roots = args.checkpoint_roots or [
        "/home/xmart/osrs-research/runs/rtx5080_e2",
        "/home/xmart/osrs-research/runs/rtx3070_e2",
    ]
    res = run_p1b_backtest_campaign(
        panel_path=args.panel,
        parquet_5m_path=args.parquet_5m,
        items_path=args.items,
        protocol_path=args.protocol,
        checkpoint_roots=roots,
        p1_quantile_cache_dir=args.p1_quantile_cache_dir,
        run_output_dir=args.run_output_dir,
        summary_json_path=args.summary_json,
        device_name=args.device,
        require_clean_git=args.require_clean_git,
    )
    wf = res["training_selected_policy_300s"]["walkforward_outer_validation"]
    p1fix = res["training_selected_policy_300s"]["p1_fixed_cells_outer_validation"]
    h24 = res["outer_validation_full_6cell_grid_300s"]["H24h_edge0bps"]
    print(
        json.dumps(
            {
                "status": "completed",
                "git_dirty": res["provenance"]["git_dirty"],
                "code_commit": res["provenance"]["code_commit"],
                "walkforward_300s_selected_cells": res["training_selected_policy_300s"][
                    "walkforward_per_fold_selected_cells"
                ],
                "walkforward_300s_net_gp": wf["net_gp"],
                "walkforward_300s_unit_fill_rate_pct": round(wf["unit_fill_rate_pct"], 3),
                "walkforward_300s_zero_fill_expiry_pct": round(wf["zero_fill_expiry_rate_pct"], 3),
                "p1_fixed_cells_300s_net_gp": p1fix["net_gp"],
                "p1_fixed_cells_300s_unit_fill_rate_pct": round(p1fix["unit_fill_rate_pct"], 3),
                "p1_fixed_cells_300s_zero_fill_expiry_pct": round(
                    p1fix["zero_fill_expiry_rate_pct"], 3
                ),
                "H24h_edge0bps_300s_net_gp": h24["net_gp"],
                "H24h_edge0bps_300s_unit_fill_rate_pct": round(h24["unit_fill_rate_pct"], 3),
                "H24h_edge0bps_300s_zero_fill_expiry_pct": round(
                    h24["zero_fill_expiry_rate_pct"], 3
                ),
                "falsification_verdict": res["falsifiable_hypothesis_evaluation"],
                "elapsed_seconds": res["elapsed_seconds"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
