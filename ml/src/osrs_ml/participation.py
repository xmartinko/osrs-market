"""Frozen, development-only participation experiment. No fitting or selection."""

import argparse
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .backtest import PreparedObservations, simulate
from .cli import git_metadata
from .data import sha256
from .diagnostics import BASELINES, DAY, MODELS, atomic_json, scenarios, validate_fold
from .execution import PortfolioPolicy

SHARES_BPS = (0, 10, 50, 100, 200, 500, 2000, 5000, 10000)
RULES = ("mean_proxy", "moment_upper")
LABEL = "current_limits_sensitivity"


def policies(config):
    originals = scenarios(config)
    return {
        f"{rule}/{preset}/p{share:05d}": replace(
            originals[preset],
            name=f"{rule}/{preset}/p{share:05d}",
            fill_model="volume_bounded_v3",
            volume_qualification=rule,
            passive_prices=True,
            queue_fill_bps=10000,
            participation_bps=share,
        )
        for rule in RULES
        for preset in BASELINES
        for share in SHARES_BPS
    }


def frozen_inputs(panel, development_run, config_path):
    """Enumerate exact development files; never discover/read holdout paths."""
    metadata_path = development_run / "run.json"
    metadata = json.loads(metadata_path.read_text())
    config = json.loads(config_path.read_text())
    lock = Path(__file__).resolve().parents[2] / "uv.lock"
    panel_manifest = panel.with_suffix(".manifest.json")
    hashes = {"panel": sha256(panel), "config": sha256(config_path), "lock": sha256(lock)}
    if metadata["status"] not in ("development_complete", "complete"):
        raise ValueError("Completed development run required")
    if any(hashes[k] != metadata[f"{k}_sha256"] for k in hashes):
        raise ValueError("Frozen panel/config/lock changed")
    if metadata["config"] != config or config["horizon_seconds"] != DAY:
        raise ValueError("Frozen daily config required")
    if len(metadata["folds"]) != config["folds"] or config["folds"] != 3:
        raise ValueError("Require three complete development folds")
    if json.loads(panel_manifest.read_text())["sha256"] != hashes["panel"]:
        raise ValueError("Panel manifest checksum mismatch")
    for fold in metadata["folds"]:
        if (
            not fold["train_max_label_end"]
            < fold["start"]
            < fold["end"]
            <= metadata["holdout_start"]
        ):
            raise ValueError("Invalid or unpurged development boundary")
    inputs = {
        f"fold{i}/forecast/predictions.parquet": sha256(
            development_run / f"fold{i}/forecast/predictions.parquet"
        )
        for i in range(3)
    }
    hashes.update(development_manifest=sha256(metadata_path), panel_manifest=sha256(panel_manifest))
    return metadata, config, hashes, inputs


def summarize(results):
    """Sampled sign brackets; no monotonicity assumption or interpolation."""
    summaries, transitions = [], []
    keys = ["limits", "qualification", "preset", "fold", "model"]
    for identity, group in results.groupby(keys, sort=True):
        group = group.sort_values("participation_bps")
        positive_share = group[group.participation_bps > 0]
        profitable = group[
            (group.net_gp > 0) & (group.buy_units_filled > 0) & (group.sell_units_filled > 0)
        ]
        first = None if profitable.empty else int(profitable.iloc[0].participation_bps)
        previous = group[group.participation_bps < first] if first is not None else group.iloc[:0]
        summaries.append(
            {
                **dict(zip(keys, identity, strict=True)),
                "min_gp": int(positive_share.net_gp.min()),
                "max_gp": int(positive_share.net_gp.max()),
                "first_profitable_bps": first,
                "preceding_sample_bps": None
                if previous.empty
                else int(previous.iloc[-1].participation_bps),
                "profitable_samples": len(profitable),
                "active_samples": int((positive_share.buy_units_filled > 0).sum()),
                "cash_positive_samples": int((positive_share.cash_pnl_gp > 0).sum()),
            }
        )
        records = group.to_dict("records")
        for a, b in zip(records, records[1:], strict=False):
            sign_a = (a["net_gp"] > 0) - (a["net_gp"] < 0)
            sign_b = (b["net_gp"] > 0) - (b["net_gp"] < 0)
            if sign_a != sign_b:
                transitions.append(
                    {
                        **dict(zip(keys, identity, strict=True)),
                        "from_bps": a["participation_bps"],
                        "to_bps": b["participation_bps"],
                        "from_gp": a["net_gp"],
                        "to_gp": b["net_gp"],
                    }
                )
    return pd.DataFrame(summaries), pd.DataFrame(transitions)


def run(panel: Path, development_run: Path, output: Path, config_path: Path):
    metadata, config, hashes, inputs = frozen_inputs(panel, development_run, config_path)
    assumptions_grid = policies(config)
    portfolio = PortfolioPolicy(
        initial_cash_gp=config["cash_gp"],
        offer_slots=config["offer_slots"],
        allocation_bps=config["allocation_bps"],
        holding_seconds=DAY,
    )
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git": git_metadata(),
        "input_hashes": hashes,
        "development_artifacts": inputs,
        "code_hashes": {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")},
        "limits": LABEL,
        "price_model": "integer_lots_v2",
        "holdout_read": False,
        "holdout_start": metadata["holdout_start"],
        "folds": metadata["folds"],
        "portfolio": asdict(portfolio),
        "models": MODELS,
        "scenarios": {name: asdict(p) for name, p in assumptions_grid.items()},
        "completed_scenarios": 0,
        "expected_scenarios": 810,
        "warning": "Conditional scenarios, not identified profit bounds or calibrated shares",
    }
    atomic_json(output / "run.json", manifest)
    rows = []
    try:
        for i, fold in enumerate(metadata["folds"]):
            observations = pq.read_table(
                panel,
                filters=[
                    ("available_at", ">=", fold["start"]),
                    ("available_at", "<", min(fold["end"], metadata["holdout_start"])),
                ],
            ).to_pandas(types_mapper=pd.ArrowDtype)
            predictions = pd.read_parquet(development_run / f"fold{i}/forecast/predictions.parquet")
            validate_fold(observations, predictions, fold, metadata["holdout_start"])
            observations["buy_limit"] = observations.buy_limit_current
            market = PreparedObservations(observations)
            scores = {
                model: dict(
                    zip(
                        zip(
                            predictions.item_id.astype(int),
                            predictions.available_at.astype(int),
                            strict=True,
                        ),
                        predictions[model].astype(float),
                        strict=True,
                    )
                )
                for model in MODELS
            }
            for name, assumptions in assumptions_grid.items():
                for model in MODELS:
                    result = simulate(market, scores[model], assumptions, portfolio)
                    path = output / f"fold{i}" / name / model
                    pending = path.with_name(model + ".partial")
                    pending.mkdir(parents=True)
                    for kind in ("fills", "orders", "equity"):
                        pd.DataFrame(getattr(result, kind)).to_parquet(
                            pending / f"{kind}.parquet", index=False
                        )
                    metrics = result.metrics
                    row = {
                        "limits": LABEL,
                        "qualification": assumptions.volume_qualification,
                        "preset": name.split("/")[1],
                        "participation_bps": assumptions.participation_bps,
                        "fold": i,
                        "model": model,
                        "evidence": "no_buys_inconclusive"
                        if not metrics["buy_units_filled"]
                        else (
                            "inventory_only"
                            if not metrics["sell_units_filled"]
                            else "hypothetical_sales"
                        ),
                        "tax_gp": sum(f["tax_gp"] for f in result.fills),
                        "fill_lots": len(result.fills),
                        **{
                            k: v
                            for k, v in metrics.items()
                            if k not in ("execution", "portfolio", "tax")
                        },
                    }
                    atomic_json(pending / "metrics.json", {**row, **metrics})
                    pending.rename(path)
                    rows.append(row)
                    manifest["completed_scenarios"] += 1
                    atomic_json(output / "run.json", manifest)
                    print(
                        f"{LABEL} fold={i} {name} {model}: {metrics['net_gp']:+,} GP; "
                        f"buy/sell={metrics['buy_units_filled']}/{metrics['sell_units_filled']}",
                        flush=True,
                    )
        results = pd.DataFrame(rows)
        results.to_parquet(output / "results.parquet", index=False)
        results.to_csv(output / "results.csv", index=False)
        summary, transitions = summarize(results)
        summary.to_csv(output / "break_even.csv", index=False)
        transitions.to_csv(output / "sign_changes.csv", index=False)
        ranks = results.copy()
        ranks["rank"] = (
            ranks.groupby(["qualification", "preset", "fold", "participation_bps"])
            .net_gp.rank(method="min", ascending=False)
            .astype(int)
        )
        ranks.to_csv(output / "ranks.csv", index=False)
        _, _, final_hashes, final_inputs = frozen_inputs(panel, development_run, config_path)
        if hashes != final_hashes or inputs != final_inputs:
            raise ValueError("Inputs changed during replay")
        manifest.update(status="complete", result_sha256=sha256(output / "results.parquet"))
        atomic_json(output / "run.json", manifest)
        print(summary[summary.model == "catboost"].to_string(index=False), flush=True)
        print(
            f"Completed {len(rows)} {LABEL} combinations; holdout NOT read. Artifacts: {output}",
            flush=True,
        )
        return results
    except Exception as error:
        manifest.update(status="failed", failure=str(error))
        atomic_json(output / "run.json", manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", required=True, type=Path)
    parser.add_argument("--development-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "experiments/daily-v1.json",
    )
    args = parser.parse_args()
    run(args.panel, args.development_run, args.output, args.config)


if __name__ == "__main__":
    main()
