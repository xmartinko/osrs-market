import argparse
import importlib.metadata
import json
import os
import subprocess
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from .backtest import simulate
from .data import export_postgres, load_snapshot, sha256
from .evaluation import split_fold, walk_forward_folds
from .execution import PRESETS, PortfolioPolicy
from .features import build_features
from .fixture import write_fixture
from .models import BASELINES, forecast_errors, predict


def git_metadata() -> dict:
    def git(*args):
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else "unavailable"

    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def write_json(path: Path, content):
    path.write_text(json.dumps(content, indent=2, allow_nan=False) + "\n")


def run(args):
    overrides = json.loads(Path(args.execution_config).read_text()) if args.execution_config else {}
    unknown_presets = set(overrides) - set(PRESETS)
    if unknown_presets:
        raise ValueError(f"Unknown execution presets: {sorted(unknown_presets)}")
    policies = {name: replace(PRESETS[name], **overrides.get(name, {})) for name in args.presets}
    policies = {
        name: replace(policy, allow_unknown_metadata=args.allow_unknown_metadata)
        for name, policy in policies.items()
    }
    fallback_intervals = {policy.unknown_interval_seconds for policy in policies.values()}
    if len(fallback_intervals) != 1:
        raise ValueError("All scenarios must share the same unknown source interval assumption")
    portfolio = PortfolioPolicy(
        initial_cash_gp=args.cash_gp,
        offer_slots=args.offer_slots,
        allocation_bps=args.allocation_bps,
        holding_seconds=args.horizon_hours * 3600,
    )
    snapshot = Path(args.snapshot).resolve()
    frame = load_snapshot(
        snapshot,
        allow_unknown_metadata=args.allow_unknown_metadata,
        unknown_interval_seconds=fallback_intervals.pop(),
    )
    folds = walk_forward_folds(frame)
    holdout = folds[0].holdout_start
    # Only timestamps were inspected to freeze the holdout. Never construct its features/labels.
    development = frame[frame.available_at < holdout]
    features = build_features(development, args.horizon_hours * 3600)
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    lock = Path(__file__).resolve().parents[2] / "uv.lock"
    metadata = {
        "schema_version": 1,
        "snapshot": str(snapshot),
        "snapshot_sha256": sha256(snapshot),
        "snapshot_manifest": json.loads(snapshot.with_suffix(".manifest.json").read_text()),
        "git": git_metadata(),
        "seed": 42,
        "horizon_hours": args.horizon_hours,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "holdout_start": holdout,
        "holdout_evaluated": False,
        "folds": [f.metadata() for f in folds],
        "tracks": args.tracks,
        "presets": args.presets,
        "execution": {name: asdict(policy) for name, policy in policies.items()},
        "portfolio": asdict(portfolio),
        "lock_sha256": sha256(lock),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ["osrs-ml", "catboost", "duckdb", "pandas", "pyarrow", "numpy"]
        },
        "status": "running",
        "limitations": [
            "Hypothetical fills from aggregate observations, not a live book",
            "Unknown pretraining overlap for future foundation adapters",
            "Fixed terminal inventory haircut is not a guaranteed liquidation",
        ],
    }
    write_json(root / "run.json", metadata)
    rows = []
    for fold in folds:
        train, validation = split_fold(features, fold)
        # Preserve per-observation interval/freshness diagnostics and causal inputs.
        validation.to_parquet(
            root / f"{fold.regime}_fold{fold.number}_context.parquet", index=False
        )
        for track in args.tracks:
            for model in BASELINES:
                prefix = f"{fold.regime}_fold{fold.number}_{track}_{model}"
                artifact = root / prefix
                artifact.mkdir()
                predictions = predict(
                    train,
                    validation,
                    track,
                    model,
                    args.horizon_hours * 3600,
                    artifact / "model" if model == "catboost" else None,
                )
                predictions.to_parquet(artifact / "predictions.parquet", index=False)
                errors = forecast_errors(validation, predictions)
                for preset in args.presets:
                    assumptions = policies[preset]
                    # Scores estimate tax-aware net return/hour. Deduct the round-trip
                    # adverse slippage allowance for this scenario before admitting a trade.
                    scores = {
                        (int(row.item_id), int(row.available_at)): float(row.score)
                        - 2 * assumptions.slippage_bps / 10_000 / args.horizon_hours
                        for row in predictions.itertuples()
                    }
                    result = simulate(
                        validation,
                        scores,
                        assumptions,
                        portfolio,
                    )
                    result_path = artifact / preset
                    result_path.mkdir()
                    write_json(result_path / "metrics.json", {**result.metrics, **errors})
                    for name, values in [
                        ("fills", result.fills),
                        ("orders", result.orders),
                        ("equity", result.equity),
                    ]:
                        pd.DataFrame(values).to_parquet(
                            result_path / f"{name}.parquet", index=False
                        )
                    rows.append(
                        {
                            "model": model,
                            "track": track,
                            "regime": fold.regime,
                            "fold": fold.number,
                            "preset": preset,
                            **errors,
                            **{
                                k: v
                                for k, v in result.metrics.items()
                                if k not in ("execution", "portfolio", "tax")
                            },
                        }
                    )
    pd.DataFrame(rows).to_parquet(root / "results.parquet", index=False)
    write_json(root / "results.json", rows)
    metadata["status"] = "complete"
    metadata["result_rows"] = len(rows)
    write_json(root / "run.json", metadata)
    with duckdb.connect() as connection:
        summary = connection.execute(
            """
            SELECT model, track, preset, regime, count(*) AS folds,
                   round(sum(net_gp) / sum(elapsed_hours), 2) AS net_gp_per_hour,
                   round(max(max_drawdown) * 100, 3) AS worst_drawdown_pct,
                   round(avg(fill_rate), 3) AS mean_fill_rate
            FROM read_parquet(?) GROUP BY model, track, preset, regime
            ORDER BY preset, regime, net_gp_per_hour DESC, model, track
        """,
            [str(root / "results.parquet")],
        ).fetchdf()
    print(summary.to_string(index=False))
    print(f"Completed {len(rows)} model/track/fold/preset evaluations; holdout NOT evaluated.")
    print(f"Artifacts: {root.resolve()}")
    print(
        "Synthetic results, when used, demonstrate execution only; they are not evidence of profit."
    )


def parser():
    value = argparse.ArgumentParser(description="OSRS execution-aware model research")
    commands = value.add_subparsers(dest="command", required=True)
    fixture = commands.add_parser("fixture", help="Generate deterministic synthetic Parquet")
    fixture.add_argument("--output", required=True)
    snapshot = commands.add_parser(
        "snapshot", help="Read existing pipeline data; never collect prices"
    )
    snapshot.add_argument("--output", required=True)
    snapshot.add_argument("--start", required=True, type=int, help="Unix seconds inclusive")
    snapshot.add_argument("--end", required=True, type=int, help="Unix seconds exclusive")
    experiment = commands.add_parser("run", help="Purged development evaluation; no holdout access")
    experiment.add_argument("--snapshot", required=True)
    experiment.add_argument("--output", required=True, help="New immutable run directory")
    experiment.add_argument(
        "--tracks",
        nargs="+",
        choices=["price_only", "full_feature"],
        default=["price_only", "full_feature"],
    )
    experiment.add_argument("--presets", nargs="+", choices=list(PRESETS), default=list(PRESETS))
    experiment.add_argument("--horizon-hours", choices=[1, 4, 24], type=int, default=1)
    experiment.add_argument("--cash-gp", type=int, default=10_000_000)
    experiment.add_argument("--offer-slots", type=int, default=8)
    experiment.add_argument("--allocation-bps", type=int, default=1000)
    experiment.add_argument(
        "--execution-config", help="JSON mapping preset names to field overrides"
    )
    experiment.add_argument(
        "--allow-unknown-metadata",
        action="store_true",
        help="Assume unknown intervals are 300s; freshness stays an estimate",
    )
    return value


def main():
    args = parser().parse_args()
    if args.command == "fixture":
        print(json.dumps(write_fixture(Path(args.output)), indent=2))
    elif args.command == "snapshot":
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise SystemExit(
                "Set DATABASE_URL to a SELECT-only connection; no collector is started"
            )
        try:
            result = export_postgres(dsn, Path(args.output), args.start, args.end)
        except Exception as error:
            # Do not echo credentials or driver connection strings into scheduler logs.
            raise SystemExit(
                f"Snapshot failed ({type(error).__name__}); check DB connectivity/permissions"
            ) from None
        print(json.dumps(result, indent=2))
    else:
        run(args)


if __name__ == "__main__":
    main()
