"""Phase One E2-E3 GPU neural trajectory campaign runner, queue supervisor, and gate evaluator.

Executes preregistered neural trajectory fits across the 3 chronological 90-day development
folds using strictly causal past-only normalization and past-validation early stopping,
scores all 74 items identically to E1 (complete_24h, endpoint_marginal, stride_24h, strata),
and evaluates the preregistered promotion gate against ``catboost_multiquantile_copula``
without touching the sealed holdout (>= 1785024300).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.metadata
import json
import math
import os
import platform
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from .probabilistic_baselines import (
    _aggregate_item_summaries,
    compute_selection_strata,
    score_item_forecasts,
)
from .probabilistic_evaluation import (
    holm_adjust,
    paired_panel_block_bootstrap,
    sample_crps,
)
from .probabilistic_models import MODEL_NAMES, build_model
from .probabilistic_train import (
    CONTEXT,
    FEATURES,
    HOLDOUT_START,
    HORIZON,
    HOUR,
    PILOT_FEATURES,
    REGISTERED_FOLDS,
    TRAIN_START,
    VALIDATION_START,
    PanelArrays,
    _git_provenance,
    _json,
    configure_device,
    eligible_origin_diagnostics,
    eligible_origins,
    file_hash,
    load_verified_panel,
    prepare_arrays,
)

E2_MATCHED_FEATURES = FEATURES + (
    "dow_sin",
    "dow_cos",
    "spread_scaled",
    "volume_imbalance",
    "anchor_dev_4h",
    "anchor_dev_24h",
    "anchor_dev_72h",
    "realized_vol_24h",
)

E3_PRICE_ONLY_FEATURES = (
    "scaled_return",
    "missing_return",
    "missing_price",
    "hour_sin",
    "hour_cos",
    "bridged_scaled_return",
    "freshness_age_log1p",
    "dow_sin",
    "dow_cos",
    "anchor_dev_4h",
    "anchor_dev_24h",
    "anchor_dev_72h",
    "realized_vol_24h",
)

SUPPORTED_FEATURE_SETS = ("e2_matched", "campaign", "pilot_v1", "e3_price_only")


def build_campaign_panel(
    frame: pd.DataFrame,
    *,
    train_start: int = TRAIN_START,
    selection_end: int = VALIDATION_START,
    feature_set: str = "e2_matched",
    availability_delay_seconds: int = 300,
) -> PanelArrays:
    """Build strictly causal sequence features for E2/E3 neural models without mutating base code."""
    if feature_set not in SUPPORTED_FEATURE_SETS:
        raise ValueError(
            f"feature_set must be one of {SUPPORTED_FEATURE_SETS}, got {feature_set!r}"
        )
    base_mode = "pilot_v1" if feature_set == "pilot_v1" else "campaign"
    base = prepare_arrays(
        frame,
        train_start=train_start,
        selection_end=selection_end,
        feature_set=base_mode,
        availability_delay_seconds=availability_delay_seconds,
    )
    if feature_set in {"pilot_v1", "campaign"}:
        clipped = base.features.copy()
        clipped[:, :, 0] = np.clip(clipped[:, :, 0], -25.0, 25.0)
        if feature_set == "campaign":
            clipped[:, :, 8] = np.clip(clipped[:, :, 8], -25.0, 25.0)
        return PanelArrays(
            times=base.times,
            item_ids=base.item_ids,
            features=clipped,
            returns=base.returns,
            center=base.center,
            scale=base.scale,
            rw_scale=base.rw_scale,
            volume_center=base.volume_center,
            volume_scale=base.volume_scale,
            prices=base.prices,
            usable=base.usable,
            availability_delay_seconds=base.availability_delay_seconds,
            feature_names=PILOT_FEATURES if feature_set == "pilot_v1" else FEATURES,
        )

    n_items, n_times = base.prices.shape
    dow_angles = 2.0 * np.pi * ((base.times // HOUR) % 168) / 168.0
    dow_sin = np.sin(dow_angles).astype(np.float32)
    dow_cos = np.cos(dow_angles).astype(np.float32)

    sorted_frame = frame.sort_values(["item_id", "ts"], kind="mergesort")
    grouped = {int(k): grp for k, grp in sorted_frame.groupby("item_id", sort=False)}

    ext = np.zeros((n_items, n_times, len(E2_MATCHED_FEATURES)), dtype=np.float32)
    ext[:, :, :11] = base.features
    ext[:, :, 0] = np.clip(ext[:, :, 0], -25.0, 25.0)
    ext[:, :, 1] = np.clip(ext[:, :, 1], -10.0, 10.0)
    ext[:, :, 2] = np.clip(ext[:, :, 2], -1.0, 1.0)
    ext[:, :, 8] = np.clip(ext[:, :, 8], -25.0, 25.0)

    alphas_anc = (
        1.0 - math.exp(-1.0 / 4.0),
        1.0 - math.exp(-1.0 / 24.0),
        1.0 - math.exp(-1.0 / 72.0),
    )
    roots_anc = (2.0, math.sqrt(24.0), math.sqrt(72.0))
    alpha_v24 = 1.0 - math.exp(-1.0 / 24.0)

    for i, item_id in enumerate(base.item_ids):
        grp = grouped[int(item_id)].set_index("ts").reindex(base.times)
        high_vol = grp.high_price_volume.to_numpy(dtype=np.float64)
        low_vol = grp.low_price_volume.to_numpy(dtype=np.float64)
        valid_vol = (
            np.isfinite(high_vol) & np.isfinite(low_vol) & (high_vol >= 0.0) & (low_vol >= 0.0)
        )
        imbalance = np.zeros(n_times, dtype=np.float32)
        imbalance[valid_vol] = (
            (high_vol[valid_vol] - low_vol[valid_vol])
            / (high_vol[valid_vol] + low_vol[valid_vol] + 1.0)
        ).astype(np.float32)

        scale_i = float(base.scale[i])
        spread_raw = base.features[i, :, 2].astype(np.float64)
        spread_scaled = np.clip(spread_raw / scale_i, -20.0, 20.0).astype(np.float32)

        ext[i, :, 11] = dow_sin
        ext[i, :, 12] = dow_cos
        ext[i, :, 13] = spread_scaled
        ext[i, :, 14] = imbalance

        log_p = np.log(base.prices[i])
        bridged = ext[i, :, 8].astype(np.float64)
        anc = [0.0, 0.0, 0.0]
        anc_init = False
        v2 = 1.0
        norms = [scale_i * r for r in roots_anc]

        d4_col = np.zeros(n_times, dtype=np.float32)
        d24_col = np.zeros(n_times, dtype=np.float32)
        d72_col = np.zeros(n_times, dtype=np.float32)
        rv24_col = np.zeros(n_times, dtype=np.float32)

        for t in range(n_times):
            lp = float(log_p[t])
            b_sq = min(float(bridged[t] * bridged[t]), 36.0)
            if math.isfinite(lp):
                if not anc_init:
                    anc = [lp, lp, lp]
                    anc_init = True
                else:
                    for k in range(3):
                        anc[k] = (1.0 - alphas_anc[k]) * anc[k] + alphas_anc[k] * lp
                d4_col[t] = float(np.clip((lp - anc[0]) / norms[0], -20.0, 20.0))
                d24_col[t] = float(np.clip((lp - anc[1]) / norms[1], -20.0, 20.0))
                d72_col[t] = float(np.clip((lp - anc[2]) / norms[2], -20.0, 20.0))
                v2 = (1.0 - alpha_v24) * v2 + alpha_v24 * b_sq
            else:
                v2 = (1.0 - alpha_v24) * v2 + alpha_v24 * 1.0
            rv24_col[t] = float(math.sqrt(max(v2, 1e-4)) - 1.0)

        ext[i, :, 15] = d4_col
        ext[i, :, 16] = d24_col
        ext[i, :, 17] = d72_col
        ext[i, :, 18] = rv24_col

    if not np.isfinite(ext).all():
        raise ValueError("Nonfinite values in E2 causal sequence features")

    if feature_set == "e3_price_only":
        keep_cols = [0, 3, 5, 6, 7, 8, 9, 11, 12, 15, 16, 17, 18]
        sub_ext = ext[:, :, keep_cols].copy()
        names = E3_PRICE_ONLY_FEATURES
    else:
        sub_ext = ext
        names = E2_MATCHED_FEATURES

    return PanelArrays(
        times=base.times,
        item_ids=base.item_ids,
        features=sub_ext,
        returns=base.returns,
        center=base.center,
        scale=base.scale,
        rw_scale=base.rw_scale,
        volume_center=base.volume_center,
        volume_scale=base.volume_scale,
        prices=base.prices,
        usable=base.usable,
        availability_delay_seconds=base.availability_delay_seconds,
        feature_names=names,
    )


def extract_windows(panel: PanelArrays, origins: np.ndarray):
    """Vectorized [B, CONTEXT, F] context and [B, HORIZON] target extraction."""
    origins = np.asarray(origins, dtype=np.int64)
    items = origins[:, 0]
    orig_t = origins[:, 1]
    ctx_idx = orig_t[:, None] + np.arange(-CONTEXT + 1, 1, dtype=np.int64)[None, :]
    tgt_idx = orig_t[:, None] + np.arange(1, HORIZON + 1, dtype=np.int64)[None, :]
    contexts = np.ascontiguousarray(panel.features[items[:, None], ctx_idx], dtype=np.float32)
    raw_ret = panel.returns[items[:, None], tgt_idx]
    targets = np.ascontiguousarray(
        (raw_ret - panel.center[items, None]) / panel.scale[items, None], dtype=np.float32
    )
    return contexts, targets, np.ascontiguousarray(items, dtype=np.int64)


def split_inner_train_val(
    panel: PanelArrays,
    train_origins: np.ndarray,
    validation_start: int,
    *,
    inner_val_days: int = 21,
    max_inner_val_origins: int = 2048,
    seed: int = 11,
) -> tuple[np.ndarray, np.ndarray]:
    """Purged chronological split strictly inside the fold training window (< validation_start)."""
    if len(train_origins) == 0:
        raise ValueError("Empty train_origins passed to split_inner_train_val")
    delay = panel.availability_delay_seconds
    inner_val_start_ts = validation_start - inner_val_days * 24 * HOUR
    orig_ts = panel.times[train_origins[:, 1]]
    final_avail = panel.times[train_origins[:, 1] + HORIZON] + HOUR + delay
    inner_first_decision = inner_val_start_ts + HOUR + delay

    tr_mask = final_avail < inner_first_decision
    va_mask = orig_ts >= inner_val_start_ts
    inner_tr = train_origins[tr_mask]
    inner_va = train_origins[va_mask]

    if len(inner_tr) < 64 or len(inner_va) < 16:
        # Fallback for short synthetic test fixtures while preserving HORIZON-step purge.
        unique_t = np.unique(train_origins[:, 1])
        cut_t = int(np.quantile(unique_t, 0.80))
        inner_tr = train_origins[train_origins[:, 1] + HORIZON < cut_t]
        inner_va = train_origins[train_origins[:, 1] >= cut_t]
        if len(inner_tr) == 0 or len(inner_va) == 0:
            cut = max(1, int(0.8 * len(train_origins)))
            inner_tr = train_origins[:cut]
            inner_va = train_origins[cut:]

    if len(inner_va) > max_inner_val_origins:
        rng = np.random.default_rng(seed + 701)
        n_items = len(panel.item_ids)
        per_item = max(max_inner_val_origins // max(n_items, 1), 1)
        chosen = []
        for item_idx in range(n_items):
            rows = inner_va[inner_va[:, 0] == item_idx]
            if len(rows) == 0:
                continue
            if len(rows) <= per_item:
                chosen.append(rows)
            else:
                pick = np.sort(rng.choice(len(rows), per_item, replace=False))
                chosen.append(rows[pick])
        inner_va = np.vstack(chosen)

    return inner_tr, inner_va


def _build_item_index_pools(origins: np.ndarray, n_items: int) -> list[np.ndarray]:
    return [origins[origins[:, 0] == i] for i in range(n_items)]


def _sample_stratified_batch(
    item_pools: list[np.ndarray],
    active_item_indices: np.ndarray,
    fallback_origins: np.ndarray,
    batch_size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if len(active_item_indices) == 0:
        return fallback_origins[rng.integers(len(fallback_origins), size=batch_size)]
    chosen_items = active_item_indices[rng.integers(len(active_item_indices), size=batch_size)]
    out = np.empty((batch_size, 2), dtype=np.int64)
    for k, it in enumerate(chosen_items):
        pool = item_pools[int(it)]
        out[k] = pool[int(rng.integers(len(pool)))]
    return out


def _evaluate_inner_val_crps(
    torch,
    model,
    panel: PanelArrays,
    inner_val: np.ndarray,
    device,
    *,
    draws: int = 64,
    chunk_size: int = 128,
) -> tuple[float, float]:
    """Compute item-macro primary scaled CRPS (h=1,4,24) and normalized NLL on past inner_val."""
    model.eval()
    n_items = len(panel.item_ids)
    per_item_vals: list[list[float]] = [[] for _ in range(n_items)]
    nlls: list[float] = []
    with torch.no_grad():
        for start in range(0, len(inner_val), chunk_size):
            batch_orig = inner_val[start : start + chunk_size]
            ctx, tgt, items = extract_windows(panel, batch_orig)
            ctx_t = torch.as_tensor(ctx, device=device)
            tgt_t = torch.as_tensor(tgt, device=device)
            itm_t = torch.as_tensor(items, device=device)
            lp = -model.log_prob(ctx_t, tgt_t, itm_t).detach().cpu().numpy() / HORIZON
            nlls.extend(lp.tolist())
            samp = model.sample(ctx_t, itm_t, draws).detach().cpu().numpy()
            scale = panel.scale[items, None, None]
            center = panel.center[items, None, None]
            cum_samp = np.cumsum(samp * scale + center, axis=-1)
            cum_act = np.cumsum(tgt * panel.scale[items, None] + panel.center[items, None], axis=-1)
            crps_sub = (
                sample_crps(cum_samp[:, :, [0, 3, 23]], cum_act[:, [0, 3, 23]])
                / panel.scale[items, None]
            )
            prim = np.mean(crps_sub, axis=1)
            for b, it in enumerate(items):
                per_item_vals[int(it)].append(float(prim[b]))
    macro_means = [float(np.mean(v)) for v in per_item_vals if len(v) > 0]
    return float(np.mean(macro_means)), float(np.mean(nlls))


def run_campaign_fit(
    *,
    panel_path: str | Path,
    protocol_path: str | Path,
    experiment_id: str,
    fit_id: str,
    model_name: str,
    fold_id: int,
    seed: int,
    output_dir: str | Path,
    device_name: str = "cuda",
    feature_set: str = "e2_matched",
    spline_variant: str = "campaign_v3",
    width: int = 64,
    max_steps: int = 2400,
    batch_size: int = 256,
    lr: float = 1.5e-3,
    eval_every: int = 400,
    min_steps: int = 1200,
    patience_checks: int = 3,
    num_samples: int = 256,
    torch_threads: int = 4,
    score_threads: int = 4,
    preloaded_data: tuple[pd.DataFrame, dict, str, dict, PanelArrays] | None = None,
) -> dict:
    """Execute one preregistered campaign fit and full fold validation scoring."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    status = {
        "status": "running",
        "experiment_id": experiment_id,
        "fit_id": fit_id,
        "pilot_only": False,
        "fit_attempt_count": 1,
        "started_unix": started,
        "model": model_name,
        "spline_variant": spline_variant if model_name == "spline_flow" else None,
        "feature_set": feature_set,
        "fold": fold_id,
        "seed": seed,
        "max_steps": max_steps,
        "batch_size": batch_size,
        "lr": lr,
        "num_samples": num_samples,
    }
    _json(output / "status.json", status)
    try:
        return _execute_campaign_fit(
            panel_path=panel_path,
            protocol_path=protocol_path,
            experiment_id=experiment_id,
            fit_id=fit_id,
            model_name=model_name,
            fold_id=fold_id,
            seed=seed,
            output=output,
            started=started,
            status=status,
            device_name=device_name,
            feature_set=feature_set,
            spline_variant=spline_variant,
            width=width,
            max_steps=max_steps,
            batch_size=batch_size,
            lr=lr,
            eval_every=eval_every,
            min_steps=min_steps,
            patience_checks=patience_checks,
            num_samples=num_samples,
            torch_threads=torch_threads,
            score_threads=score_threads,
            preloaded_data=preloaded_data,
        )
    except BaseException as error:
        status.update(
            status="failed",
            elapsed_seconds=time.time() - started,
            error_type=type(error).__name__,
            error=str(error),
            traceback=traceback.format_exc(),
        )
        _json(output / "status.json", status)
        raise


def _execute_campaign_fit(
    *,
    panel_path: str | Path,
    protocol_path: str | Path,
    experiment_id: str,
    fit_id: str,
    model_name: str,
    fold_id: int,
    seed: int,
    output: Path,
    started: float,
    status: dict,
    device_name: str,
    feature_set: str,
    spline_variant: str,
    width: int,
    max_steps: int,
    batch_size: int,
    lr: float,
    eval_every: int,
    min_steps: int,
    patience_checks: int,
    num_samples: int,
    torch_threads: int,
    score_threads: int,
    preloaded_data: tuple[pd.DataFrame, dict, str, dict, PanelArrays] | None,
) -> dict:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    import torch

    if model_name not in MODEL_NAMES:
        raise ValueError(f"Unknown model {model_name!r}; expected one of {MODEL_NAMES}")
    if fold_id not in REGISTERED_FOLDS:
        raise ValueError(f"Invalid fold {fold_id!r}; expected 1, 2, or 3")
    if not (
        1 <= max_steps <= 25_000
        and 1 <= batch_size <= 512
        and 2 <= num_samples <= 2048
        and 1 <= torch_threads <= 4
    ):
        raise ValueError("Campaign parameter bounds violated")

    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    protocol_hash = file_hash(protocol_path)
    if protocol.get("protected_holdout_start") != HOLDOUT_START:
        raise ValueError("Protocol holdout start mismatch")

    train_start, val_start, val_end = REGISTERED_FOLDS[fold_id]
    if preloaded_data is not None:
        frame, manifest, manifest_hash, strata_info, panel = preloaded_data
    else:
        frame, manifest, manifest_hash = load_verified_panel(panel_path)
        strata_info = compute_selection_strata(frame, manifest)
        panel = build_campaign_panel(
            frame,
            train_start=train_start,
            selection_end=val_start,
            feature_set=feature_set,
            availability_delay_seconds=int(manifest["availability_delay_seconds"]),
        )
    if manifest["sha256"] != protocol["panel_sha256"]:
        raise ValueError("Panel SHA256 does not match frozen campaign protocol")
    delay_seconds = int(manifest["availability_delay_seconds"])

    train_all, val_all = eligible_origins(
        panel,
        train_start=train_start,
        validation_start=val_start,
        validation_end=val_end,
        delay_seconds=delay_seconds,
    )
    cohort_diag = eligible_origin_diagnostics(
        panel,
        train_start=train_start,
        validation_start=val_start,
        validation_end=val_end,
        delay_seconds=delay_seconds,
    )
    inner_train, inner_val = split_inner_train_val(panel, train_all, val_start, seed=seed)

    torch.manual_seed(seed)
    np.random.seed(seed)
    device = configure_device(torch, device_name)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_num_threads(torch_threads)

    model = build_model(
        model_name,
        len(panel.feature_names),
        HORIZON,
        width,
        len(panel.item_ids),
        spline_variant=spline_variant,
    ).to(device)
    param_count = sum(p.numel() for p in model.parameters())

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    warmup_steps = min(160, max(1, max_steps // 10))

    def _lr_at(step_zero_idx: int) -> float:
        s = step_zero_idx + 1
        if s <= warmup_steps:
            return lr * (s / warmup_steps)
        if max_steps <= warmup_steps:
            return lr
        prog = (s - warmup_steps) / (max_steps - warmup_steps)
        return lr * (0.1 + 0.9 * 0.5 * (1.0 + math.cos(math.pi * min(prog, 1.0))))

    code_commit, git_dirty = _git_provenance()
    package_freeze = sorted(
        f"{dist.metadata['Name']}=={dist.version}" for dist in importlib.metadata.distributions()
    )
    (output / "environment.txt").write_text("\n".join(package_freeze) + "\n", encoding="utf-8")

    metadata = {
        "experiment_id": experiment_id,
        "fit_id": fit_id,
        "pilot_only": False,
        "fold": fold_id,
        "seed": seed,
        "model": model_name,
        "spline_variant": spline_variant if model_name == "spline_flow" else None,
        "feature_set": feature_set,
        "features": list(panel.feature_names),
        "panel_sha256": manifest["sha256"],
        "panel_manifest_sha256": manifest_hash,
        "protocol_sha256": protocol_hash,
        "code_commit": code_commit,
        "git_dirty": git_dirty,
        "train_start": train_start,
        "validation_start": val_start,
        "validation_end_exclusive": val_end,
        "holdout_start": HOLDOUT_START,
        "holdout_touched": False,
        "availability_delay_seconds": delay_seconds,
        "train_eligible_count": int(len(train_all)),
        "inner_train_count": int(len(inner_train)),
        "inner_val_count": int(len(inner_val)),
        "validation_complete_24h_count": int(len(val_all)),
        "cohort_diagnostics": cohort_diag,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "python": platform.python_version(),
        "host": platform.node(),
        "precision": "FP32; TF32 disabled; deterministic algorithms required",
        "parameters": int(param_count),
        "max_steps": max_steps,
        "batch_size": batch_size,
        "learning_rate": lr,
        "eval_every": eval_every,
        "min_steps": min_steps,
        "patience_checks": patience_checks,
        "num_samples": num_samples,
    }
    _json(output / "metadata.json", metadata)

    item_pools = _build_item_index_pools(inner_train, len(panel.item_ids))
    active_items = np.array([i for i, p in enumerate(item_pools) if len(p) > 0], dtype=np.int64)
    batch_rng = np.random.default_rng(seed)

    best_inner_crps = float("inf")
    best_step = 0
    best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    stale_checks = 0
    steps_run = 0
    inner_history: list[dict] = []

    train_t0 = time.time()
    with (output / "progress.jsonl").open("x", encoding="utf-8") as progress:
        for step in range(max_steps):
            model.train()
            cur_lr = _lr_at(step)
            for pg in optimizer.param_groups:
                pg["lr"] = cur_lr

            batch_orig = _sample_stratified_batch(
                item_pools, active_items, inner_train, batch_size, batch_rng
            )
            ctx, tgt, items = extract_windows(panel, batch_orig)
            ctx_t = torch.as_tensor(ctx, device=device)
            tgt_t = torch.as_tensor(tgt, device=device)
            itm_t = torch.as_tensor(items, device=device)

            optimizer.zero_grad(set_to_none=True)
            loss = model.loss(ctx_t, tgt_t, itm_t)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"Nonfinite training loss at step {step + 1}")
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(
                model.parameters(), 5.0, error_if_nonfinite=True
            )
            optimizer.step()
            steps_run = step + 1

            if steps_run == 1 or steps_run % 50 == 0 or steps_run == max_steps:
                progress.write(
                    json.dumps(
                        {
                            "step": steps_run,
                            "lr": round(cur_lr, 7),
                            "loss": float(loss.detach().cpu()),
                            "gradient_norm": float(grad_norm.detach().cpu()),
                            "elapsed_seconds": round(time.time() - started, 3),
                        }
                    )
                    + "\n"
                )
                progress.flush()

            if steps_run % eval_every == 0 or steps_run == max_steps:
                inner_crps, inner_nll = _evaluate_inner_val_crps(
                    torch, model, panel, inner_val, device, draws=64
                )
                improved = inner_crps < (best_inner_crps - 1e-5)
                if improved:
                    best_inner_crps = inner_crps
                    best_step = steps_run
                    best_state = {
                        k: v.detach().cpu().clone() for k, v in model.state_dict().items()
                    }
                    stale_checks = 0
                else:
                    stale_checks += 1
                rec = {
                    "step": steps_run,
                    "inner_val_macro_scaled_crps": inner_crps,
                    "inner_val_normalized_nll": inner_nll,
                    "best_so_far": improved,
                }
                inner_history.append(rec)
                progress.write(json.dumps({"event": "inner_val", **rec}) + "\n")
                progress.flush()
                if steps_run >= min_steps and stale_checks >= patience_checks:
                    break

    train_elapsed = time.time() - train_t0
    model.load_state_dict({k: v.to(device) for k, v in best_state.items()})
    model.eval()

    torch.save(
        {
            "model_state": best_state,
            "best_step": best_step,
            "best_inner_val_macro_scaled_crps": best_inner_crps,
            "steps_completed": steps_run,
            "inner_history": inner_history,
            "metadata": metadata,
        },
        output / "checkpoint.pt",
    )

    # Score full validation fold identically to E1 (probabilistic_baselines.py).
    eval_t0 = time.time()
    cand_origins = np.arange(CONTEXT - 1, len(panel.times) - HORIZON, dtype=np.int64)
    cand_ts = panel.times[cand_origins]
    final_avail = panel.times[cand_origins + HORIZON] + HOUR + delay_seconds
    val_cutoff = min(val_end + HOUR + delay_seconds, HOLDOUT_START)
    val_grid_mask = (cand_ts >= val_start) & (cand_ts < val_end) & (final_avail < val_cutoff)
    val_grid_origins = cand_origins[val_grid_mask]
    origin_to_grid_pos = {int(o): idx for idx, o in enumerate(val_grid_origins)}
    n_grid = len(val_grid_origins)
    n_items = len(panel.item_ids)

    valid_returns = np.isfinite(panel.returns)
    bad_prefix = np.concatenate(
        [np.zeros((n_items, 1), dtype=np.int64), np.cumsum(~valid_returns, axis=1)], axis=1
    )

    fold_eval_seed = seed + fold_id * 1000
    torch.manual_seed(fold_eval_seed + 9001)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(fold_eval_seed + 9001)

    crps_panel = np.full((n_grid, n_items), np.nan, dtype=np.float64)
    var_panel = np.full((n_grid, n_items), np.nan, dtype=np.float64)
    per_item_records: list[dict | None] = [None] * n_items
    val_norm_nlls: list[float] = []
    val_raw_nlls: list[float] = []

    sample_chunk = 256 if model_name != "recursive_student_t" else 128

    def _generate_item_paths(item_idx: int, eval_origins: np.ndarray, comp_eval: np.ndarray):
        if len(eval_origins) == 0:
            return np.empty((0, num_samples, HORIZON), dtype=np.float64)
        scale_i = float(panel.scale[item_idx])
        center_i = float(panel.center[item_idx])
        chunks = []
        with torch.no_grad():
            for st in range(0, len(eval_origins), sample_chunk):
                sub_orig = eval_origins[st : st + sample_chunk]
                sub_comp = comp_eval[st : st + sample_chunk]
                ctx_np = np.ascontiguousarray(
                    panel.features[
                        item_idx,
                        sub_orig[:, None] + np.arange(-CONTEXT + 1, 1, dtype=np.int64)[None, :],
                    ],
                    dtype=np.float32,
                )
                ctx_t = torch.as_tensor(ctx_np, device=device)
                itm_t = torch.full((len(sub_orig),), item_idx, dtype=torch.long, device=device)
                inc_samp = model.sample(ctx_t, itm_t, num_samples).detach().cpu().numpy()
                if not np.isfinite(inc_samp).all():
                    raise FloatingPointError(f"Nonfinite samples generated for item {item_idx}")
                cum_paths = np.cumsum(inc_samp * scale_i + center_i, axis=-1)
                chunks.append(cum_paths.astype(np.float64, copy=False))

                if np.any(sub_comp):
                    comp_o = sub_orig[sub_comp]
                    comp_pairs = np.column_stack(
                        [np.full(len(comp_o), item_idx, dtype=np.int64), comp_o]
                    )
                    _, tgt_np, _ = extract_windows(panel, comp_pairs)
                    tgt_t = torch.as_tensor(tgt_np, device=device)
                    lp = (
                        -model.log_prob(
                            ctx_t[torch.as_tensor(sub_comp, device=device)],
                            tgt_t,
                            itm_t[torch.as_tensor(sub_comp, device=device)],
                        )
                        .detach()
                        .cpu()
                        .numpy()
                        / HORIZON
                    )
                    val_norm_nlls.extend(lp.tolist())
                    val_raw_nlls.extend((lp + math.log(scale_i)).tolist())
        return np.concatenate(chunks, axis=0)

    # Stream GPU generation -> parallel CPU scoring in waves to keep RAM low and saturate both GPU & CPU.
    wave_size = max(score_threads * 2, 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=score_threads) as pool:
        for w_start in range(0, n_items, wave_size):
            futures = []
            for item_idx in range(w_start, min(w_start + wave_size, n_items)):
                usable_at_grid = panel.usable[item_idx, val_grid_origins]
                eval_origins = val_grid_origins[usable_at_grid]
                comp_eval = (
                    bad_prefix[item_idx, eval_origins + HORIZON + 1]
                    - bad_prefix[item_idx, eval_origins + 1]
                ) == 0
                paths = _generate_item_paths(item_idx, eval_origins, comp_eval)
                log_price_item = np.log(panel.prices[item_idx])
                price_item = panel.prices[item_idx]
                item_scale = float(panel.scale[item_idx])
                fut = pool.submit(
                    score_item_forecasts,
                    paths,
                    log_price_item,
                    price_item,
                    item_scale,
                    eval_origins,
                    val_grid_origins,
                    origin_to_grid_pos,
                    comp_eval,
                    11 + fold_id * 1000 + item_idx * 31,
                )
                futures.append((item_idx, fut))
            for item_idx, fut in futures:
                rec = fut.result()
                crps_panel[:, item_idx] = rec.pop("panel_crps_col")
                var_panel[:, item_idx] = rec.pop("panel_var_col")
                per_item_records[item_idx] = rec

    eval_elapsed = time.time() - eval_t0
    clean_recs = [r for r in per_item_records if r is not None]
    agg_summary = _aggregate_item_summaries(clean_recs, panel.item_ids, strata_info)
    agg_summary["likelihood_complete_24h"] = {
        "normalized_nll_per_increment": float(np.mean(val_norm_nlls)),
        "raw_return_nll_per_increment": float(np.mean(val_raw_nlls)),
    }
    agg_summary["training_summary"] = {
        "steps_completed": steps_run,
        "best_step": best_step,
        "best_inner_val_macro_scaled_crps": best_inner_crps,
        "train_elapsed_seconds": train_elapsed,
        "eval_elapsed_seconds": eval_elapsed,
        "parameters": int(param_count),
    }

    _json(output / "fold_eval_summary.json", agg_summary)
    np.savez_compressed(
        output / "loss_panel.npz",
        val_grid_origin_ts=panel.times[val_grid_origins],
        item_ids=panel.item_ids,
        item_scales=panel.scale,
        crps_panel=crps_panel,
        var_panel=var_panel,
    )

    if device.type == "cuda":
        torch.cuda.synchronize(device)
    peak_alloc = int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0
    peak_res = int(torch.cuda.max_memory_reserved(device)) if device.type == "cuda" else 0
    try:
        import resource

        peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except ImportError:
        peak_rss = None

    total_elapsed = time.time() - started
    status.update(
        status="completed",
        elapsed_seconds=total_elapsed,
        train_elapsed_seconds=train_elapsed,
        eval_elapsed_seconds=eval_elapsed,
        steps_completed=steps_run,
        best_step=best_step,
        best_inner_val_macro_scaled_crps=best_inner_crps,
        primary_macro_scaled_crps_1_4_24=agg_summary["macro_complete_24h"][
            "primary_scaled_crps_1_4_24"
        ],
        scaled_variogram_p05_unbiased=agg_summary["macro_complete_24h"][
            "scaled_variogram_p05_unbiased"
        ],
        coverage90_h1=agg_summary["macro_complete_24h"]["coverage90_h1"],
        coverage90_h4=agg_summary["macro_complete_24h"]["coverage90_h4"],
        coverage90_h24=agg_summary["macro_complete_24h"]["coverage90_h24"],
        peak_cuda_memory_bytes=peak_alloc,
        peak_cuda_reserved_bytes=peak_res,
        peak_host_rss_kib_linux=peak_rss,
        artifacts_sha256={
            p.name: file_hash(p)
            for p in output.iterdir()
            if p.is_file() and p.name != "status.json"
        },
    )
    _json(output / "status.json", status)
    return status


def run_node_queue(
    *,
    panel_path: str | Path,
    protocol_path: str | Path,
    runs_root: str | Path,
    queue_name: str,
    device_name: str = "cuda",
    torch_threads: int = 4,
    score_threads: int = 4,
) -> dict:
    """Run all preregistered fits assigned to ``queue_name`` sequentially on one GPU."""
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    queues = protocol["queues"]
    if queue_name not in queues:
        raise ValueError(f"Unknown queue {queue_name!r}; available: {sorted(queues)}")
    fit_specs = queues[queue_name]
    runs_dir = Path(runs_root)
    runs_dir.mkdir(parents=True, exist_ok=True)
    queue_status_path = runs_dir / f"{queue_name}_queue_status.json"

    frame, manifest, manifest_hash = load_verified_panel(panel_path)
    strata_info = compute_selection_strata(frame, manifest)
    delay_seconds = int(manifest["availability_delay_seconds"])

    panel_cache: dict[tuple[int, str], PanelArrays] = {}
    results = []
    q_started = time.time()

    for idx, spec in enumerate(fit_specs):
        fit_id = spec["fit_id"]
        fit_out = runs_dir / fit_id
        status_file = fit_out / "status.json"
        if status_file.exists():
            existing = json.loads(status_file.read_text(encoding="utf-8"))
            if existing.get("status") == "completed":
                results.append(
                    {"fit_id": fit_id, "action": "skipped_already_completed", **existing}
                )
                continue
            # Never overwrite an existing directory; record and move to next independent fit.
            results.append(
                {
                    "fit_id": fit_id,
                    "action": "skipped_existing_incomplete_dir",
                    "existing_status": existing.get("status"),
                }
            )
            continue

        fold_id = int(spec["fold"])
        feat_set = spec.get("feature_set", "e2_matched")
        cache_key = (fold_id, feat_set)
        if cache_key not in panel_cache:
            # Keep at most 1 cached panel in RAM at a time to preserve host headroom.
            panel_cache.clear()
            tr_s, va_s, _ = REGISTERED_FOLDS[fold_id]
            panel_cache[cache_key] = build_campaign_panel(
                frame,
                train_start=tr_s,
                selection_end=va_s,
                feature_set=feat_set,
                availability_delay_seconds=delay_seconds,
            )

        _json(
            queue_status_path,
            {
                "queue_name": queue_name,
                "status": "running",
                "current_index": idx + 1,
                "total_fits": len(fit_specs),
                "current_fit_id": fit_id,
                "completed_or_processed": len(results),
                "elapsed_seconds": time.time() - q_started,
            },
        )
        try:
            fit_res = run_campaign_fit(
                panel_path=panel_path,
                protocol_path=protocol_path,
                experiment_id=spec["experiment_id"],
                fit_id=fit_id,
                model_name=spec["model"],
                fold_id=fold_id,
                seed=int(spec["seed"]),
                output_dir=fit_out,
                device_name=device_name,
                feature_set=feat_set,
                spline_variant=spec.get("spline_variant", "campaign_v3"),
                width=int(spec.get("width", 64)),
                max_steps=int(spec.get("max_steps", 2400)),
                batch_size=int(spec.get("batch_size", 256)),
                lr=float(spec.get("lr", 1.5e-3)),
                eval_every=int(spec.get("eval_every", 400)),
                min_steps=int(spec.get("min_steps", 1200)),
                patience_checks=int(spec.get("patience_checks", 3)),
                num_samples=int(spec.get("num_samples", 256)),
                torch_threads=torch_threads,
                score_threads=score_threads,
                preloaded_data=(
                    frame,
                    manifest,
                    manifest_hash,
                    strata_info,
                    panel_cache[cache_key],
                ),
            )
            results.append(fit_res)
            print(
                json.dumps(
                    {
                        "event": "fit_completed",
                        "queue": queue_name,
                        "index": f"{idx + 1}/{len(fit_specs)}",
                        "fit_id": fit_id,
                        "elapsed_s": round(fit_res["elapsed_seconds"], 2),
                        "primary_crps": round(fit_res["primary_macro_scaled_crps_1_4_24"], 4),
                        "var_unbiased": round(fit_res["scaled_variogram_p05_unbiased"], 2),
                        "cov90_h24": round(fit_res["coverage90_h24"], 4),
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            # Rule 2: record blocked/failed item cleanly and continue to next independent item.
            err_rec = {
                "fit_id": fit_id,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            results.append(err_rec)
            print(json.dumps({"event": "fit_failed", "queue": queue_name, **err_rec}), flush=True)

    final_q = {
        "queue_name": queue_name,
        "status": "completed",
        "total_fits": len(fit_specs),
        "succeeded": sum(1 for r in results if r.get("status") == "completed"),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
        "elapsed_seconds": time.time() - q_started,
        "results": results,
    }
    _json(queue_status_path, final_q)
    return final_q


def evaluate_campaign_gates(
    *,
    protocol_path: str | Path,
    runs_roots: list[str | Path],
    e1_runs_dir: str | Path,
    e1_results_json: str | Path,
    output_json_path: str | Path | None = None,
    experiment_filter: str = "E2",
    repetitions: int = 2000,
    base_seed: int = 11,
) -> dict:
    """Aggregate completed 3-fold neural candidates and compute exact E1 gate verdicts."""
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    e1_report = json.loads(Path(e1_results_json).read_text(encoding="utf-8"))
    winner_name = e1_report["strongest_calibrated_baseline"]["selected_model"]
    winner_summary = e1_report["three_fold_mean_summary"][winner_name]
    winner_crps_3fold = float(winner_summary["macro_complete_24h"]["primary_scaled_crps_1_4_24"])
    winner_var_3fold = float(winner_summary["macro_complete_24h"]["scaled_variogram_p05_unbiased"])

    e1_dir = Path(e1_runs_dir)
    e1_crps_folds = {}
    e1_var_folds = {}
    for fold_id in (1, 2, 3):
        with np.load(e1_dir / f"fold{fold_id}_loss_panels.npz") as npz:
            e1_crps_folds[fold_id] = np.asarray(npz[f"crps__{winner_name}"], dtype=np.float64)
            e1_var_folds[fold_id] = np.asarray(npz[f"var__{winner_name}"], dtype=np.float64)
    winner_stacked_crps = np.vstack([e1_crps_folds[f] for f in (1, 2, 3)])
    winner_stacked_var = np.vstack([e1_var_folds[f] for f in (1, 2, 3)])

    # Locate run directories across supplied roots.
    all_specs = []
    for q_specs in protocol["queues"].values():
        for spec in q_specs:
            if spec["experiment_id"] == experiment_filter:
                all_specs.append(spec)

    def _find_run_dir(fit_id: str) -> Path | None:
        for root in runs_roots:
            cand = Path(root) / fit_id
            if (cand / "status.json").exists():
                return cand
        return None

    # Group specs by candidate_id (e.g., model architecture in E2, or ablation_id in E3).
    grouped_specs: dict[str, list[dict]] = {}
    for spec in all_specs:
        cid = spec["candidate_id"]
        grouped_specs.setdefault(cid, []).append(spec)

    candidate_summaries: dict[str, dict] = {}
    candidate_stacked_crps: dict[str, np.ndarray] = {}
    candidate_stacked_var: dict[str, np.ndarray] = {}
    slot_records = []

    for cid, specs in grouped_specs.items():
        by_fold_seed: dict[tuple[int, int], tuple[dict, dict, np.ndarray, np.ndarray]] = {}
        incomplete_reasons = []
        for spec in specs:
            fid = spec["fit_id"]
            rdir = _find_run_dir(fid)
            if rdir is None:
                incomplete_reasons.append(f"{fid}:not_found")
                continue
            st = json.loads((rdir / "status.json").read_text(encoding="utf-8"))
            slot_records.append(
                {
                    "fit_id": fid,
                    "candidate_id": cid,
                    "fold": int(spec["fold"]),
                    "seed": int(spec["seed"]),
                    "status": st.get("status"),
                    "elapsed_seconds": st.get("elapsed_seconds"),
                    "steps_completed": st.get("steps_completed"),
                    "best_step": st.get("best_step"),
                    "peak_cuda_memory_bytes": st.get("peak_cuda_memory_bytes"),
                }
            )
            if st.get("status") != "completed":
                incomplete_reasons.append(f"{fid}:{st.get('status')}")
                continue
            ev = json.loads((rdir / "fold_eval_summary.json").read_text(encoding="utf-8"))
            with np.load(rdir / "loss_panel.npz") as lp:
                c_pan = np.asarray(lp["crps_panel"], dtype=np.float64)
                v_pan = np.asarray(lp["var_panel"], dtype=np.float64)
            f_idx = int(spec["fold"])
            if not np.array_equal(np.isnan(c_pan), np.isnan(e1_crps_folds[f_idx])):
                raise ValueError(
                    f"Cohort mask mismatch between {fid} and E1 fold {f_idx} loss panel"
                )
            by_fold_seed[(f_idx, int(spec["seed"]))] = (st, ev, c_pan, v_pan)

        folds_present = sorted({k[0] for k in by_fold_seed})
        if folds_present != [1, 2, 3]:
            candidate_summaries[cid] = {
                "candidate_id": cid,
                "complete_all_folds": False,
                "incomplete_reasons": incomplete_reasons,
            }
            continue

        # Aggregate across available seeds per fold, then equal-average across the 3 folds.
        fold_crps_means = []
        fold_var_means = []
        fold_macro_dicts = []
        fold_ep_dicts = []
        fold_stride_dicts = []
        fold_pooled_dicts = []
        fold_gp_strata = []
        fold_man_strata = []
        fold_sub12 = []
        fold_lik = []
        per_seed_3fold: dict[int, list[float]] = {}

        for f_idx in (1, 2, 3):
            f_entries = [v for (ff, _), v in sorted(by_fold_seed.items()) if ff == f_idx]
            for (ff, ss), v in sorted(by_fold_seed.items()):
                if ff == f_idx:
                    per_seed_3fold.setdefault(ss, []).append(
                        float(v[1]["macro_complete_24h"]["primary_scaled_crps_1_4_24"])
                    )
            fold_crps_means.append(np.mean([v[2] for v in f_entries], axis=0))
            fold_var_means.append(np.mean([v[3] for v in f_entries], axis=0))

            m_keys = list(f_entries[0][1]["macro_complete_24h"].keys())
            fold_macro_dicts.append(
                {
                    k: float(np.mean([v[1]["macro_complete_24h"][k] for v in f_entries]))
                    for k in m_keys
                }
            )
            ep_keys = [
                k for k in f_entries[0][1]["endpoint_marginal_macro"] if not k.startswith("total_")
            ]
            fold_ep_dicts.append(
                {
                    k: float(np.mean([v[1]["endpoint_marginal_macro"][k] for v in f_entries]))
                    for k in ep_keys
                }
            )
            st_keys = [k for k in f_entries[0][1]["stride_24h_macro"] if not k.startswith("total_")]
            fold_stride_dicts.append(
                {
                    k: float(np.mean([v[1]["stride_24h_macro"][k] for v in f_entries]))
                    for k in st_keys
                }
            )
            p_keys = list(f_entries[0][1]["pooled_unscaled_complete_24h"].keys())
            fold_pooled_dicts.append(
                {
                    k: float(np.mean([v[1]["pooled_unscaled_complete_24h"][k] for v in f_entries]))
                    for k in p_keys
                }
            )
            fold_gp_strata.append(
                {
                    lbl: {
                        k: float(
                            np.mean([v[1]["by_gp_notional_stratum"][lbl][k] for v in f_entries])
                        )
                        for k in f_entries[0][1]["by_gp_notional_stratum"][lbl]
                        if k != "item_count"
                    }
                    for lbl in ("high", "medium", "low")
                }
            )
            fold_man_strata.append(
                {
                    lbl: {
                        k: float(
                            np.mean(
                                [v[1]["by_manifest_unit_volume_stratum"][lbl][k] for v in f_entries]
                            )
                        )
                        for k in f_entries[0][1]["by_manifest_unit_volume_stratum"][lbl]
                        if k != "item_count"
                    }
                    for lbl in ("high", "medium", "low")
                }
            )
            fold_sub12.append(
                {
                    k: float(np.mean([v[1]["subset_12_items_macro"][k] for v in f_entries]))
                    for k in f_entries[0][1]["subset_12_items_macro"]
                    if k != "item_count"
                }
            )
            fold_lik.append(
                {
                    k: float(np.mean([v[1]["likelihood_complete_24h"][k] for v in f_entries]))
                    for k in f_entries[0][1]["likelihood_complete_24h"]
                }
            )

        macro_3fold = {
            k: float(np.mean([fd[k] for fd in fold_macro_dicts])) for k in fold_macro_dicts[0]
        }
        ep_3fold = {k: float(np.mean([fd[k] for fd in fold_ep_dicts])) for k in fold_ep_dicts[0]}
        stride_3fold = {
            k: float(np.mean([fd[k] for fd in fold_stride_dicts])) for k in fold_stride_dicts[0]
        }
        pooled_3fold = {
            k: float(np.mean([fd[k] for fd in fold_pooled_dicts])) for k in fold_pooled_dicts[0]
        }
        lik_3fold = {k: float(np.mean([fd[k] for fd in fold_lik])) for k in fold_lik[0]}
        gp_3fold = {
            lbl: {
                k: float(np.mean([fd[lbl][k] for fd in fold_gp_strata]))
                for k in fold_gp_strata[0][lbl]
            }
            for lbl in ("high", "medium", "low")
        }
        man_3fold = {
            lbl: {
                k: float(np.mean([fd[lbl][k] for fd in fold_man_strata]))
                for k in fold_man_strata[0][lbl]
            }
            for lbl in ("high", "medium", "low")
        }
        sub12_3fold = {k: float(np.mean([fd[k] for fd in fold_sub12])) for k in fold_sub12[0]}

        seed_3fold_means = {
            str(s): float(np.mean(vals))
            for s, vals in sorted(per_seed_3fold.items())
            if len(vals) == 3
        }
        seed_std = (
            float(np.std(list(seed_3fold_means.values()))) if len(seed_3fold_means) >= 2 else 0.0
        )

        candidate_stacked_crps[cid] = np.vstack(fold_crps_means)
        candidate_stacked_var[cid] = np.vstack(fold_var_means)
        candidate_summaries[cid] = {
            "candidate_id": cid,
            "complete_all_folds": True,
            "completed_fit_count": len(by_fold_seed),
            "incomplete_reasons": incomplete_reasons,
            "macro_complete_24h": macro_3fold,
            "likelihood_complete_24h": lik_3fold,
            "seed_3fold_primary_crps": seed_3fold_means,
            "seed_primary_crps_std": seed_std,
            "fold_primary_crps": [
                float(fd["primary_scaled_crps_1_4_24"]) for fd in fold_macro_dicts
            ],
            "fold_primary_crps_std": float(
                np.std([fd["primary_scaled_crps_1_4_24"] for fd in fold_macro_dicts])
            ),
            "endpoint_marginal_macro": ep_3fold,
            "stride_24h_macro": stride_3fold,
            "pooled_unscaled_complete_24h": pooled_3fold,
            "by_gp_notional_stratum": gp_3fold,
            "by_manifest_unit_volume_stratum": man_3fold,
            "subset_12_items_macro": sub12_3fold,
        }

    # Paired 168h moving-block bootstrap + Holm adjustment across all complete candidates.
    complete_cids = [cid for cid, s in candidate_summaries.items() if s.get("complete_all_folds")]
    boot_crps_map: dict[str, dict] = {}
    boot_var_map: dict[str, dict] = {}
    boot_sensitivity: dict[str, dict] = {}
    raw_p_crps = []
    raw_p_var = []

    for idx, cid in enumerate(complete_cids):
        b_c = paired_panel_block_bootstrap(
            candidate_stacked_crps[cid],
            winner_stacked_crps,
            block_length=168,
            repetitions=repetitions,
            seed=base_seed + 10_000 + idx,
            scheme="moving",
        )
        b_v = paired_panel_block_bootstrap(
            candidate_stacked_var[cid],
            winner_stacked_var,
            block_length=168,
            repetitions=repetitions,
            seed=base_seed + 11_000 + idx,
            scheme="moving",
        )
        boot_crps_map[cid] = b_c
        boot_var_map[cid] = b_v
        raw_p_crps.append(b_c["centered_two_sided_tail"])
        raw_p_var.append(b_v["centered_two_sided_tail"])

        boot_sensitivity[cid] = {
            "moving_72h_crps": paired_panel_block_bootstrap(
                candidate_stacked_crps[cid],
                winner_stacked_crps,
                block_length=72,
                repetitions=repetitions,
                seed=base_seed + 12_000 + idx,
                scheme="moving",
            ),
            "moving_336h_crps": paired_panel_block_bootstrap(
                candidate_stacked_crps[cid],
                winner_stacked_crps,
                block_length=336,
                repetitions=repetitions,
                seed=base_seed + 13_000 + idx,
                scheme="moving",
            ),
            "stationary_168h_crps": paired_panel_block_bootstrap(
                candidate_stacked_crps[cid],
                winner_stacked_crps,
                block_length=168,
                repetitions=repetitions,
                seed=base_seed + 14_000 + idx,
                scheme="stationary",
            ),
        }

    holm_p_crps = holm_adjust(raw_p_crps).tolist() if raw_p_crps else []
    holm_p_var = holm_adjust(raw_p_var).tolist() if raw_p_var else []

    verdicts = {}
    crps_threshold = 0.98 * winner_crps_3fold
    var_threshold = 0.95 * winner_var_3fold

    for cid, p_c_adj, p_v_adj in zip(complete_cids, holm_p_crps, holm_p_var, strict=True):
        boot_crps_map[cid]["holm_adjusted_two_sided_tail"] = float(p_c_adj)
        boot_var_map[cid]["holm_adjusted_two_sided_tail"] = float(p_v_adj)
        m = candidate_summaries[cid]["macro_complete_24h"]
        c_val = float(m["primary_scaled_crps_1_4_24"])
        v_val = float(m["scaled_variogram_p05_unbiased"])
        covs = (float(m["coverage90_h1"]), float(m["coverage90_h4"]), float(m["coverage90_h24"]))

        cov_pass = all(0.87 <= c <= 0.93 for c in covs)
        rel_crps_reduction = (winner_crps_3fold - c_val) / winner_crps_3fold
        rel_var_reduction = (winner_var_3fold - v_val) / winner_var_3fold

        marginal_gate_pass = (
            c_val <= crps_threshold
            and boot_crps_map[cid]["mean_difference"] < 0.0
            and float(p_c_adj) < 0.05
        )
        joint_gate_pass = (
            v_val <= var_threshold
            and boot_var_map[cid]["mean_difference"] < 0.0
            and float(p_v_adj) < 0.05
            and c_val <= winner_crps_3fold
        )
        overall_pass = bool(cov_pass and (marginal_gate_pass or joint_gate_pass))

        verdicts[cid] = {
            "candidate_id": cid,
            "overall_gate_pass": overall_pass,
            "passes_coverage90_gate": cov_pass,
            "passes_marginal_crps_gate": marginal_gate_pass,
            "passes_joint_variogram_gate": joint_gate_pass,
            "primary_macro_scaled_crps_1_4_24": c_val,
            "relative_crps_reduction_vs_catboost": rel_crps_reduction,
            "scaled_variogram_p05_unbiased": v_val,
            "relative_variogram_reduction_vs_catboost": rel_var_reduction,
            "coverage90_h1_h4_h24": list(covs),
            "holm_p_primary_crps": float(p_c_adj),
            "holm_p_unbiased_variogram": float(p_v_adj),
            "bootstrap_crps_diff_95ci": boot_crps_map[cid]["difference_interval"],
            "bootstrap_var_diff_95ci": boot_var_map[cid]["difference_interval"],
        }

    code_commit, git_dirty = _git_provenance()
    report = {
        "experiment_id": experiment_filter,
        "evaluated_at_unix": time.time(),
        "code_commit": code_commit,
        "git_dirty": git_dirty,
        "protected_holdout_start": HOLDOUT_START,
        "holdout_touched": False,
        "reference_baseline": {
            "model": winner_name,
            "primary_macro_scaled_crps_1_4_24": winner_crps_3fold,
            "scaled_variogram_p05_unbiased": winner_var_3fold,
            "marginal_crps_gate_threshold_minus_2pct": crps_threshold,
            "joint_variogram_gate_threshold_minus_5pct": var_threshold,
            "coverage90_gate_bounds": [0.87, 0.93],
        },
        "fit_slots_inspected": len(slot_records),
        "fit_slots_completed": sum(1 for r in slot_records if r["status"] == "completed"),
        "fit_slots_failed": sum(1 for r in slot_records if r["status"] == "failed"),
        "any_candidate_cleared_gate": any(v["overall_gate_pass"] for v in verdicts.values()),
        "gate_verdicts": verdicts,
        "candidates": candidate_summaries,
        "paired_bootstrap_vs_catboost_168h": {
            cid: {"primary_crps": boot_crps_map[cid], "unbiased_variogram": boot_var_map[cid]}
            for cid in complete_cids
        },
        "bootstrap_sensitivity_checks": boot_sensitivity,
        "slot_accounting": slot_records,
    }
    if output_json_path is not None:
        _json(Path(output_json_path), report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fit = sub.add_parser("run-fit")
    p_fit.add_argument("--panel", required=True)
    p_fit.add_argument("--protocol", required=True)
    p_fit.add_argument("--experiment", default="E2")
    p_fit.add_argument("--fit-id", required=True)
    p_fit.add_argument("--model", required=True, choices=MODEL_NAMES)
    p_fit.add_argument("--spline-variant", default="campaign_v3")
    p_fit.add_argument("--feature-set", default="e2_matched", choices=SUPPORTED_FEATURE_SETS)
    p_fit.add_argument("--fold", type=int, required=True, choices=(1, 2, 3))
    p_fit.add_argument("--seed", type=int, required=True)
    p_fit.add_argument("--device", default="cuda")
    p_fit.add_argument("--max-steps", type=int, default=2400)
    p_fit.add_argument("--batch-size", type=int, default=256)
    p_fit.add_argument("--lr", type=float, default=1.5e-3)
    p_fit.add_argument("--eval-every", type=int, default=400)
    p_fit.add_argument("--min-steps", type=int, default=1200)
    p_fit.add_argument("--patience-checks", type=int, default=3)
    p_fit.add_argument("--num-samples", type=int, default=256)
    p_fit.add_argument("--torch-threads", type=int, default=4)
    p_fit.add_argument("--score-threads", type=int, default=4)
    p_fit.add_argument("--output", required=True)

    p_queue = sub.add_parser("run-queue")
    p_queue.add_argument("--panel", required=True)
    p_queue.add_argument("--protocol", required=True)
    p_queue.add_argument("--runs-root", required=True)
    p_queue.add_argument("--queue-name", required=True)
    p_queue.add_argument("--device", default="cuda")
    p_queue.add_argument("--torch-threads", type=int, default=4)
    p_queue.add_argument("--score-threads", type=int, default=4)

    p_agg = sub.add_parser("evaluate-gates")
    p_agg.add_argument("--protocol", required=True)
    p_agg.add_argument("--runs-roots", nargs="+", required=True)
    p_agg.add_argument("--e1-runs-dir", required=True)
    p_agg.add_argument("--e1-results-json", required=True)
    p_agg.add_argument("--experiment", default="E2")
    p_agg.add_argument("--output-json", default=None)

    args = parser.parse_args()
    if args.cmd == "run-fit":
        res = run_campaign_fit(
            panel_path=args.panel,
            protocol_path=args.protocol,
            experiment_id=args.experiment,
            fit_id=args.fit_id,
            model_name=args.model,
            fold_id=args.fold,
            seed=args.seed,
            output_dir=args.output,
            device_name=args.device,
            feature_set=args.feature_set,
            spline_variant=args.spline_variant,
            max_steps=args.max_steps,
            batch_size=args.batch_size,
            lr=args.lr,
            eval_every=args.eval_every,
            min_steps=args.min_steps,
            patience_checks=args.patience_checks,
            num_samples=args.num_samples,
            torch_threads=args.torch_threads,
            score_threads=args.score_threads,
        )
        print(json.dumps(res))
    elif args.cmd == "run-queue":
        res = run_node_queue(
            panel_path=args.panel,
            protocol_path=args.protocol,
            runs_root=args.runs_root,
            queue_name=args.queue_name,
            device_name=args.device,
            torch_threads=args.torch_threads,
            score_threads=args.score_threads,
        )
        print(
            json.dumps(
                {"queue": args.queue_name, "status": res["status"], "succeeded": res["succeeded"]}
            )
        )
    elif args.cmd == "evaluate-gates":
        res = evaluate_campaign_gates(
            protocol_path=args.protocol,
            runs_roots=args.runs_roots,
            e1_runs_dir=args.e1_runs_dir,
            e1_results_json=args.e1_results_json,
            output_json_path=args.output_json,
            experiment_filter=args.experiment,
        )
        print(json.dumps(res["gate_verdicts"], indent=2))


if __name__ == "__main__":
    main()
