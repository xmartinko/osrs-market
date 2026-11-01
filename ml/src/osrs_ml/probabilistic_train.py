"""Bounded development-only pilot runner; not the full registered campaign.

python -m osrs_ml.probabilistic_train --panel panel.parquet --model gaussian_diag
    --device cuda --output new-run-directory
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .probabilistic_evaluation import (
    energy_score,
    interval_scores,
    sample_crps,
    variogram_score,
)

HOUR = 3600
HOLDOUT_START = 1785024300
TRAIN_START = int(pd.Timestamp("2024-10-29", tz="UTC").timestamp())
VALIDATION_START = int(pd.Timestamp("2025-10-29", tz="UTC").timestamp())
VALIDATION_END = int(pd.Timestamp("2026-01-27", tz="UTC").timestamp())
CONTEXT = 168
HORIZON = 24
FEATURES = (
    "scaled_return",
    "scaled_log_volume",
    "relative_side_price_difference",
    "missing_return",
    "missing_volume",
    "missing_price",
    "hour_sin",
    "hour_cos",
)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_verified_panel(path):
    """Verify payload hash and declared scope BEFORE opening the Parquet parser."""
    path = Path(path)
    manifest_path = path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("holdout_start") != HOLDOUT_START
        or manifest.get("selection_end_exclusive") != VALIDATION_START
        or manifest.get("start") != TRAIN_START
        or manifest.get("end_exclusive", HOLDOUT_START + 1) > HOLDOUT_START
        or manifest.get("quality", {}).get("max_ts", HOLDOUT_START) >= HOLDOUT_START
        or manifest.get("availability_delay_seconds") != 300
        or not manifest.get("gates", {}).get("development_only")
    ):
        raise ValueError("Unqualified panel manifest scope, selection, timing or holdout gate")
    if file_hash(path) != manifest.get("sha256"):
        raise ValueError("Panel SHA256 mismatch; Parquet was not parsed")
    frame = pd.read_parquet(path)
    needed = {
        "ts",
        "item_id",
        "mid_price",
        "avg_high_price",
        "avg_low_price",
        "high_price_volume",
        "low_price_volume",
        "available_at",
        "usable",
    }
    if not needed <= set(frame.columns) or frame.empty:
        raise ValueError("Panel fields missing or panel empty")
    if (
        frame[["ts", "item_id", "available_at"]].isna().any().any()
        or (frame.ts >= HOLDOUT_START).any()
        or (frame.ts < TRAIN_START).any()
        or (frame.ts % HOUR != 0).any()
        or (frame.available_at != frame.ts + HOUR + 300).any()
        or frame.duplicated(["item_id", "ts"]).any()
        or set(frame.item_id.unique()) != set(manifest["selected_ids"])
    ):
        raise ValueError("Parsed panel violates identity, timing, grid or duplicate gate")
    # An aggregate can become available exactly at the reserved boundary; it is
    # excluded from every eligible window even though its bucket start predates it.
    return frame, manifest, file_hash(manifest_path)


@dataclass
class PanelArrays:
    times: np.ndarray
    item_ids: np.ndarray
    features: np.ndarray
    returns: np.ndarray
    center: np.ndarray
    scale: np.ndarray
    rw_scale: np.ndarray
    volume_center: np.ndarray
    volume_scale: np.ndarray

    def windows(self, origins):
        """Materialize only the requested minibatch, never all context windows."""
        contexts, targets = [], []
        for item, origin in origins:
            contexts.append(self.features[item, origin - CONTEXT + 1 : origin + 1])
            targets.append(
                (self.returns[item, origin + 1 : origin + HORIZON + 1] - self.center[item])
                / self.scale[item]
            )
        return (
            np.asarray(contexts, dtype=np.float32),
            np.asarray(targets, dtype=np.float32),
            np.asarray(origins[:, 0], dtype=np.int64),
        )


def prepare_arrays(frame, *, selection_end=VALIDATION_START):
    """Create an hourly grid; every fitted statistic uses the initial year only."""
    item_ids = np.sort(frame.item_id.unique())
    times = np.arange(int(frame.ts.min()), int(frame.ts.max()) + HOUR, HOUR)
    if len(times) < CONTEXT + HORIZON:
        raise ValueError("Insufficient hourly history")
    shape = (len(item_ids), len(times))
    features, returns = np.zeros((*shape, len(FEATURES)), dtype=np.float32), np.full(shape, np.nan)
    centers, scales, rw_scales, volume_centers, volume_scales = [], [], [], [], []
    train_mask = (times >= TRAIN_START) & (times < selection_end)
    for position, item_id in enumerate(item_ids):
        group = frame[frame.item_id == item_id].set_index("ts").reindex(times)
        price = group.mid_price.to_numpy(dtype=float).copy()
        usable = group.usable.eq(True).to_numpy(dtype=bool)
        price[~usable | ~np.isfinite(price) | (price <= 0)] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            increments = np.r_[np.nan, np.diff(np.log(price))]
        returns[position] = increments
        initial = increments[train_mask & np.isfinite(increments)]
        if len(initial) < 48:
            raise ValueError(f"Insufficient training-only returns for item {item_id}")
        center = float(np.median(initial))
        scale = max(float(1.4826 * np.median(np.abs(initial - center))), 1e-4)
        high_volume = group.high_price_volume.to_numpy(dtype=float)
        low_volume = group.low_price_volume.to_numpy(dtype=float)
        valid_volume = (
            np.isfinite(high_volume)
            & np.isfinite(low_volume)
            & (high_volume >= 0)
            & (low_volume >= 0)
        )
        volume = np.full(len(times), np.nan)
        volume[valid_volume] = np.log1p(high_volume[valid_volume] + low_volume[valid_volume])
        initial_volume = volume[train_mask & np.isfinite(volume)]
        if not len(initial_volume):
            raise ValueError("No observed training volumes")
        volume_center = float(np.median(initial_volume))
        volume_scale = max(float(1.4826 * np.median(np.abs(initial_volume - volume_center))), 1e-3)
        high = group.avg_high_price.to_numpy(dtype=float)
        low = group.avg_low_price.to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            spread = (high - low) / price
        values = features[position]
        values[:, 0] = np.where(np.isfinite(increments), (increments - center) / scale, 0)
        values[:, 1] = np.where(np.isfinite(volume), (volume - volume_center) / volume_scale, 0)
        values[:, 2] = np.where(np.isfinite(spread), spread, 0)
        values[:, 3] = ~np.isfinite(increments)
        values[:, 4] = ~valid_volume
        values[:, 5] = ~np.isfinite(price)
        angles = 2 * np.pi * ((times // HOUR) % 24) / 24
        values[:, 6], values[:, 7] = np.sin(angles), np.cos(angles)
        centers.append(center)
        scales.append(scale)
        rw_scales.append(max(float(np.std(initial, ddof=1)), 1e-4))
        volume_centers.append(volume_center)
        volume_scales.append(volume_scale)
    if not np.isfinite(features).all():
        raise ValueError("Nonfinite or overflowing context features")
    return PanelArrays(
        times,
        item_ids,
        features,
        returns,
        np.array(centers),
        np.array(scales),
        np.array(rw_scales),
        np.array(volume_centers),
        np.array(volume_scales),
    )


def eligible_origins(panel, *, validation_start=VALIDATION_START, validation_end=VALIDATION_END):
    """Train targets must be available strictly before the first validation decision."""
    train, validation = [], []
    first_validation_decision = validation_start + HOUR + 300
    for item in range(len(panel.item_ids)):
        valid = np.isfinite(panel.returns[item])
        for origin in range(CONTEXT - 1, len(panel.times) - HORIZON):
            timestamp = panel.times[origin]
            final_timestamp = panel.times[origin + HORIZON]
            final_available = final_timestamp + HOUR + 300
            if (
                not valid[origin + 1 : origin + HORIZON + 1].all()
                or final_available >= HOLDOUT_START
            ):
                continue
            if timestamp < validation_start and final_available < first_validation_decision:
                train.append((item, origin))
            elif (
                validation_start <= timestamp < validation_end and final_available < validation_end
            ):
                validation.append((item, origin))
    return (
        np.asarray(train, dtype=np.int64).reshape(-1, 2),
        np.asarray(validation, dtype=np.int64).reshape(-1, 2),
    )


def bounded_subset(origins, limit, seed):
    if len(origins) <= limit:
        return origins
    indices = np.sort(np.random.default_rng(seed).choice(len(origins), limit, replace=False))
    return origins[indices]


def _json(path, value):
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _summarize(samples, targets):
    # Both arguments are already cumulative, unscaled log returns.
    marginal = sample_crps(samples, targets)
    intervals = interval_scores(samples, targets)
    result = {
        "energy": float(energy_score(samples, targets).mean()),
        "variogram_p05": float(variogram_score(samples, targets).mean()),
    }
    for hour in (1, 4, 24):
        index = hour - 1
        result[f"crps_h{hour}"] = float(marginal[:, index].mean())
        result[f"wis_h{hour}"] = float(intervals["wis"][:, index].mean())
        result[f"coverage90_h{hour}"] = float(intervals["coverage"][0, :, index].mean())
        result[f"width90_h{hour}"] = float(intervals["width"][0, :, index].mean())
    return result


def run_pilot(args):
    """Run exactly one bounded fit. Output directory is exclusively created."""
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    status = {
        "status": "running",
        "started_unix": started,
        "pilot_only": True,
        "fit_attempt_count": 1,
        "arguments": vars(args).copy(),
    }
    _json(output / "status.json", status)
    try:
        return _run_pilot(args, output, started, status)
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


def _run_pilot(args, output, started, status):
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    from .probabilistic_models import build_model

    if not (
        1 <= args.max_steps <= 256
        and 1 <= args.batch_size <= 256
        and 2 <= args.num_samples <= 2048
        and 1 <= args.torch_threads <= 4
    ):
        raise ValueError("Pilot limits: steps1..256, batch1..256, sample draws2..2048")
    frame, manifest, manifest_hash = load_verified_panel(args.panel)
    panel = prepare_arrays(frame)
    train_all, validation_all = eligible_origins(panel)
    train = bounded_subset(train_all, 20_000, args.seed)
    validation = bounded_subset(validation_all, 512, args.seed + 1)
    if not len(train) or not len(validation):
        raise ValueError("No valid purged training or pilot validation windows")
    del frame
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise ValueError("Requested CUDA device is unavailable; no silent CPU fallback")
    device = torch.device(args.device)
    if device.type == "cuda":
        torch.cuda.set_per_process_memory_fraction(0.75, device)
        torch.cuda.manual_seed_all(args.seed)
        torch.cuda.reset_peak_memory_stats(device)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_num_threads(args.torch_threads)
    model = build_model(args.model, len(FEATURES), HORIZON, 64, len(panel.item_ids)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    generator = np.random.default_rng(args.seed)
    try:
        code_version = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        code_version = "unavailable"
    package_freeze = sorted(
        f"{distribution.metadata['Name']}=={distribution.version}"
        for distribution in importlib.metadata.distributions()
    )
    (output / "environment.txt").write_text("\n".join(package_freeze) + "\n", encoding="utf-8")
    metadata = {
        "pilot_only": True,
        "panel_sha256": manifest["sha256"],
        "panel_manifest_sha256": manifest_hash,
        "code_commit": code_version,
        "runner_sha256": file_hash(__file__),
        "features": FEATURES,
        "model_source_sha256": file_hash(Path(__file__).with_name("probabilistic_models.py")),
        "evaluation_source_sha256": file_hash(
            Path(__file__).with_name("probabilistic_evaluation.py")
        ),
        "train_start": TRAIN_START,
        "validation_start": VALIDATION_START,
        "validation_end_exclusive": VALIDATION_END,
        "holdout_start": HOLDOUT_START,
        "universe_available_at": VALIDATION_START + 300,
        "first_validation_decision": VALIDATION_START + HOUR + 300,
        "timing_assumption": "bucket start +3900s; source ingestion latency is unobserved",
        "purge_rule": "last training target available strictly before first validation decision",
        "train_eligible_count": len(train_all),
        "train_retained_count": len(train),
        "validation_eligible_count": len(validation_all),
        "validation_retained_count": len(validation),
        "subset_rule": "seeded uniform origin subsets, without replacement; not full validation",
        "context": CONTEXT,
        "horizon": HORIZON,
        "seed": args.seed,
        "item_ids": panel.item_ids.tolist(),
        "return_center": panel.center.tolist(),
        "return_scale": panel.scale.tolist(),
        "rw_scale": panel.rw_scale.tolist(),
        "volume_center": panel.volume_center.tolist(),
        "volume_scale": panel.volume_scale.tolist(),
        "normalization": "initial-training-year per-item median,1.4826*MAD; floors return1e-4 volume1e-3",
        "device": str(device),
        "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "python": platform.python_version(),
        "host": platform.node(),
        "precision": "FP32; TF32 disabled; deterministic algorithms required",
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "steps_limit": args.max_steps,
        "batch_size": args.batch_size,
        "torch_threads": args.torch_threads,
        "cuda_memory_fraction": 0.75,
        "num_samples": args.num_samples,
        "wis_alphas": [0.1, 0.2, 0.5],
        "crps_estimator": "fair iid U-statistic",
        "no_confirmatory_claim": True,
    }
    _json(output / "metadata.json", metadata)
    np.savez_compressed(output / "origins.npz", train=train, validation=validation)
    model.train()
    with (output / "progress.jsonl").open("x", encoding="utf-8") as progress:
        for step in range(args.max_steps):
            origins = train[generator.integers(len(train), size=args.batch_size)]
            context, target, items = panel.windows(origins)
            context, target, items = [
                torch.as_tensor(value, device=device) for value in (context, target, items)
            ]
            optimizer.zero_grad(set_to_none=True)
            loss = model.loss(context, target, items)
            if not torch.isfinite(loss):
                raise FloatingPointError("Nonfinite training loss")
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 5, error_if_nonfinite=True)
            optimizer.step()
            progress.write(
                json.dumps(
                    {
                        "step": step + 1,
                        "loss": float(loss.detach().cpu()),
                        "gradient_norm": float(norm.cpu()),
                        "elapsed_seconds": time.time() - started,
                    }
                )
                + "\n"
            )
            progress.flush()
    model.eval()
    scores = {name: [] for name in ("model", "gaussian_rw", "no_change")}
    nlls, origin_scores = [], []
    evaluation_rng = np.random.default_rng(args.seed + 101)
    with torch.no_grad():
        for left in range(0, len(validation), 16):
            origins = validation[left : left + 16]
            context, target, items = panel.windows(origins)
            context_tensor, target_tensor, item_tensor = [
                torch.as_tensor(value, device=device) for value in (context, target, items)
            ]
            samples = model.sample(context_tensor, item_tensor, args.num_samples).cpu().numpy()
            if not np.isfinite(samples).all():
                raise FloatingPointError("Nonfinite forecast samples")
            nlls.extend(
                (
                    -model.log_prob(context_tensor, target_tensor, item_tensor).cpu().numpy()
                    / HORIZON
                ).tolist()
            )
            scale, center = panel.scale[items, None, None], panel.center[items, None, None]
            cumulative_samples = np.cumsum(samples * scale + center, axis=-1)
            actual = np.cumsum(
                target * panel.scale[items, None] + panel.center[items, None], axis=-1
            )
            rw = np.cumsum(
                evaluation_rng.normal(size=samples.shape) * panel.rw_scale[items, None, None],
                axis=-1,
            )
            forecasts = {
                "model": cumulative_samples,
                "gaussian_rw": rw,
                "no_change": np.zeros_like(cumulative_samples),
            }
            for name, paths in forecasts.items():
                scores[name].append((len(origins), _summarize(paths, actual)))
            crps = sample_crps(cumulative_samples, actual)
            for row, (item, origin) in enumerate(origins):
                origin_scores.append(
                    {
                        "item_id": int(panel.item_ids[item]),
                        "origin_bucket_ts": int(panel.times[origin]),
                        "decision_at": int(panel.times[origin] + HOUR + 300),
                        "crps_h1": float(crps[row, 0]),
                        "crps_h4": float(crps[row, 3]),
                        "crps_h24": float(crps[row, 23]),
                    }
                )
    metrics = {
        name: {
            key: float(sum(count * summary[key] for count, summary in chunks) / len(validation))
            for key in chunks[0][1]
        }
        for name, chunks in scores.items()
    }
    metrics["model"]["normalized_nll_per_increment"] = float(np.mean(nlls))
    if not all(np.isfinite(value) for summary in metrics.values() for value in summary.values()):
        raise FloatingPointError("Nonfinite evaluation metric")
    _json(output / "metrics.json", metrics)
    _json(output / "origin_metrics.json", origin_scores)
    torch.save(
        {
            "model_state": {key: value.cpu() for key, value in model.state_dict().items()},
            "optimizer_state": optimizer.state_dict(),
            "metadata": metadata,
            "torch_rng_state": torch.get_rng_state(),
            "cuda_rng_state": torch.cuda.get_rng_state_all() if device.type == "cuda" else [],
            "numpy_generator_state": generator.bit_generator.state,
        },
        output / "checkpoint.pt",
    )
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    status.update(
        status="completed",
        elapsed_seconds=time.time() - started,
        steps_completed=args.max_steps,
        validation_origins_scored=len(validation),
        peak_cuda_memory_bytes=torch.cuda.max_memory_allocated(device)
        if device.type == "cuda"
        else 0,
        artifacts_sha256={
            path.name: file_hash(path)
            for path in output.iterdir()
            if path.is_file() and path.name != "status.json"
        },
    )
    try:
        import resource

        status["peak_host_rss_kib_linux"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        status["peak_host_rss_kib_linux"] = None
    _json(output / "status.json", status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", required=True)
    parser.add_argument(
        "--model",
        required=True,
        choices=("gaussian_diag", "gaussian_lowrank", "student_t", "spline_flow"),
    )
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--max-steps", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--num-samples", type=int, default=256)
    parser.add_argument("--torch-threads", type=int, default=4)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run_pilot(args)))


if __name__ == "__main__":
    main()
