"""Development-only execution ablations. No fitting, selection or holdout access."""

import json
import os
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .backtest import simulate
from .cli import git_metadata
from .costs import sale_proceeds
from .data import sha256
from .execution import PRESETS, PortfolioPolicy

DAY = 86400
MODELS = ("no_trade", "no_change", "raw_spread", "spread_volume", "catboost")
KEYS = ["item_id", "available_at"]
BASELINES = ("optimistic", "moderate", "conservative")
COMPARABLE = (
    "net_gp",
    "realized_gp",
    "end_cash_gp",
    "end_inventory_mark_gp",
    "end_inventory_units",
    "buy_units_requested",
    "buy_units_filled",
    "sell_units_filled",
)


def atomic_json(path, value):
    temporary = path.with_suffix(".partial")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def scenarios(config):
    """Predeclared contrasts; names describe overrides, not measured realism."""
    policies = {
        name: replace(PRESETS[name], **config["execution"][name], allow_unknown_metadata=True)
        for name in BASELINES
    }
    optimistic, moderate = policies["optimistic"], policies["moderate"]
    factors = {
        "price_side": ("passive_prices",),
        "participation": ("participation_bps",),
        "queue": ("queue_fill_bps",),
        "slippage": ("slippage_bps",),
        "latency": ("latency_seconds",),
        "freshness": ("freshness_basis", "max_freshness_seconds"),
        "terminal_haircut": ("terminal_haircut_bps",),
    }
    for label, fields in factors.items():
        policies[f"only_{label}"] = replace(
            optimistic, **{field: getattr(moderate, field) for field in fields}
        )
    policies["moderate_passive"] = replace(moderate, passive_prices=True)
    for passive in (True, False):
        for bps in (0, 5, 10, 30):
            policies[f"{'passive' if passive else 'crossed'}_slip_{bps}bps"] = replace(
                optimistic, passive_prices=passive, slippage_bps=bps
            )
    return policies


def validate_fold(observations, predictions, fold, holdout_start):
    if not fold["start"] < fold["end"] <= holdout_start:
        raise ValueError("Fold overlaps holdout or has invalid boundaries")
    if not fold["train_max_label_end"] < fold["start"]:
        raise ValueError("Training labels overlap validation")
    for name, frame in (("Observations", observations), ("Predictions", predictions)):
        if frame.empty or frame[KEYS].isna().any().any():
            raise ValueError(f"{name} empty or NULL decision keys")
        if frame.duplicated(KEYS).any():
            raise ValueError(f"{name} duplicate decision keys")
        if not frame.available_at.between(fold["start"], fold["end"], inclusive="left").all():
            raise ValueError(f"{name} outside development fold")
    if (
        not pd.MultiIndex.from_frame(observations[KEYS].astype("int64"))
        .sort_values()
        .equals(pd.MultiIndex.from_frame(predictions[KEYS].astype("int64")).sort_values())
    ):
        raise ValueError("Missing or extra prediction coverage")
    context = observations.copy()
    context[KEYS] = context[KEYS].astype("int64")
    context = context.set_index(KEYS).reindex(
        pd.MultiIndex.from_frame(predictions[KEYS].astype("int64"))
    )
    for model in MODELS:
        # Saved scores can legitimately be NaN: the original executor excludes
        # nonfinite scores when the required price side is absent/inverted.
        undefined = context.avg_high_price.isna() | context.inverted_spread
        if model != "catboost":
            undefined = undefined | context.avg_low_price.isna()
        if (predictions[model].isna().to_numpy() & ~undefined.to_numpy(dtype=bool)).any():
            raise ValueError("Missing model scores with valid price inputs")
    if np.isposinf(predictions[list(MODELS)].to_numpy(dtype=float)).any():
        raise ValueError("Positive infinite score")
    if not predictions.no_trade.eq(-np.inf).all():
        raise ValueError("No-trade control must have no eligible scores")
    if (
        not observations.source.eq("wiki").all()
        or not observations.resolution_seconds.eq(DAY).all()
        or observations.resolution_ambiguous.any()
        or (observations.available_at < observations.timestamp + DAY).any()
    ):
        raise ValueError("Require strict completed Wiki daily observations")
    if observations.high_price_volume.isna().any() or observations.low_price_volume.isna().any():
        raise ValueError("Missing volume")


def fixed_fill_repricing(observations, result):
    """Change cash prices only; preserve quantities, dates and terminal mark.

    This can violate cash, price ceilings and capacity. It is an accounting
    counterfactual, never a second executable portfolio or realized market P&L.
    """
    policy = result.metrics["execution"]
    if not policy["passive_prices"] or policy["slippage_bps"]:
        raise ValueError("Fixed-fill repricing requires passive zero-slippage execution")
    lookup = observations.set_index(KEYS)
    ledger = []
    missing = 0
    for fill in result.fills:
        row = lookup.loc[(fill["item_id"], fill["timestamp"])]
        price = row["avg_high_price" if fill["side"] == "buy" else "avg_low_price"]
        if pd.isna(price):
            missing += 1
            ledger.append({**fill, "crossed_cash_delta_gp": None, "cash_change_gp": None})
            continue
        price, quantity = int(price), fill["quantity"]
        cash = (
            -price * quantity
            if fill["side"] == "buy"
            else sale_proceeds(price, quantity, item_id=fill["item_id"])
        )
        ledger.append(
            {
                **fill,
                "crossed_price_gp": price,
                "crossed_cash_delta_gp": cash,
                "cash_change_gp": cash - fill["cash_delta_gp"],
                "crossed_tax_gp": 0 if fill["side"] == "buy" else price * quantity - cash,
            }
        )
    changes = {
        side: sum(f["cash_change_gp"] or 0 for f in ledger if f["side"] == side)
        for side in ("buy", "sell")
    }
    total = sum(changes.values())
    summary = {
        "kind": "fixed_fill_accounting_counterfactual_not_execution",
        "original_net_gp": result.metrics["net_gp"],
        "crossed_net_gp_same_terminal_mark": None if missing else result.metrics["net_gp"] + total,
        "buy_cash_change_gp": None if missing else changes["buy"],
        "sell_cash_change_gp": None if missing else changes["sell"],
        "missing_crossed_side_fills": missing,
        "fill_events": len(ledger),
        "vacuous": not ledger,
        "terminal_mark_gp_unchanged": result.metrics["end_inventory_mark_gp"],
    }
    return summary, ledger


def decision_gates(observations, predictions, model, assumptions):
    """Overlapping input-gate counts, not attribution of dynamic slot/cash rejections."""
    scores = predictions.set_index(KEYS)[model].reindex(
        pd.MultiIndex.from_frame(observations[KEYS].astype("int64"))
    )
    positive = pd.Series(np.isfinite(scores) & (scores > 0)).to_numpy()
    side = "low" if assumptions.passive_prices else "high"
    age = observations[f"{side}_freshness_seconds"]
    uncertainty = observations.source_interval_seconds.astype("int64[pyarrow]").fillna(
        observations.resolution_seconds
    )
    if assumptions.freshness_basis == "lower_bound":
        uncertainty = 0
    return {
        "undefined_scores": int(predictions[model].isna().sum()),
        "positive_decisions": int(positive.sum()),
        "positive_missing_limit": int((positive & observations.buy_limit.isna()).sum()),
        "positive_nonpositive_limit": int((positive & (observations.buy_limit <= 0)).sum()),
        "positive_missing_buy_price": int(
            (positive & observations[f"avg_{side}_price"].isna()).sum()
        ),
        "positive_inverted_spread": int((positive & observations.inverted_spread).sum()),
        "positive_stale_or_missing_age": int(
            (
                positive & (age.isna() | (age + uncertainty > assumptions.max_freshness_seconds))
            ).sum()
        ),
        "unknown_interval_rows": int(observations.interval_unknown.sum()),
    }


def diagnose(panel: Path, development_run: Path, output: Path, config_path: Path):
    metadata_path = development_run / "run.json"
    metadata = json.loads(metadata_path.read_text())
    config = json.loads(config_path.read_text())
    if metadata["status"] not in ("development_complete", "complete"):
        raise ValueError("Completed development run required")
    hashes = {"panel": sha256(panel), "config": sha256(config_path)}
    if hashes["panel"] != metadata["panel_sha256"] or hashes["config"] != metadata["config_sha256"]:
        raise ValueError("Panel/config changed since frozen development run")
    if metadata["config"] != config or config["horizon_seconds"] != DAY:
        raise ValueError("Frozen daily config required")
    if len(metadata["folds"]) != config["folds"]:
        raise ValueError("Incomplete development folds")
    lock = Path(__file__).resolve().parents[2] / "uv.lock"
    if sha256(lock) != metadata["lock_sha256"]:
        raise ValueError("Dependency lock changed since development run")
    panel_manifest = panel.with_suffix(".manifest.json")
    if json.loads(panel_manifest.read_text())["sha256"] != hashes["panel"]:
        raise ValueError("Panel manifest checksum mismatch")
    hashes.update(
        {
            "development_manifest": sha256(metadata_path),
            "panel_manifest": sha256(panel_manifest),
            "lock": sha256(lock),
        }
    )
    # Enumerate exact development paths. Never glob/read a holdout directory.
    inputs = {}
    for i in range(len(metadata["folds"])):
        relative = Path(f"fold{i}") / "forecast" / "predictions.parquet"
        inputs[str(relative)] = sha256(development_run / relative)
        for preset in BASELINES:
            for model in MODELS:
                relative = (
                    Path(f"fold{i}")
                    / "current_limits_sensitivity"
                    / preset
                    / model
                    / "metrics.json"
                )
                inputs[str(relative)] = sha256(development_run / relative)
    policies = scenarios(config)
    portfolio = PortfolioPolicy(
        initial_cash_gp=config["cash_gp"],
        offer_slots=config["offer_slots"],
        allocation_bps=config["allocation_bps"],
        holding_seconds=DAY,
    )
    output.mkdir(parents=True, exist_ok=False)
    run = {
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git": git_metadata(),
        "input_hashes": hashes,
        "development_artifacts": inputs,
        "code_hashes": {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")},
        "source": metadata["source"],
        "limits": "current_limits_sensitivity",
        "holdout_read": False,
        "holdout_start": metadata["holdout_start"],
        "folds": metadata["folds"],
        "portfolio": asdict(portfolio),
        "scenarios": {name: asdict(p) for name, p in policies.items()},
        "completed_scenarios": 0,
        "models": MODELS,
        "warning": "Development execution sensitivity; hypothetical fills, current limits lookahead. "
        "Grid points are not model selection or calibrated execution. Zero buys are inconclusive.",
    }
    atomic_json(output / "run.json", run)
    rows, matched = [], []
    try:
        for i, fold in enumerate(metadata["folds"]):
            # Predicate filtering keeps holdout observations out of the loaded frame.
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
            for name, assumptions in policies.items():
                for model in MODELS:
                    result = simulate(observations, scores[model], assumptions, portfolio)
                    if name in BASELINES:
                        reference = (
                            development_run
                            / f"fold{i}/current_limits_sensitivity/{name}/{model}/metrics.json"
                        )
                        expected = json.loads(reference.read_text())
                        if any(result.metrics[k] != expected[k] for k in COMPARABLE):
                            raise ValueError(
                                f"Original preset reproduction failed: fold{i}/{name}/{model}"
                            )
                    path = output / f"fold{i}" / name / model
                    pending = path.with_name(model + ".partial")
                    pending.mkdir(parents=True)
                    for kind in ("fills", "orders", "equity"):
                        pd.DataFrame(getattr(result, kind)).to_parquet(
                            pending / f"{kind}.parquet", index=False
                        )
                    metrics = result.metrics
                    bought = metrics["buy_units_filled"]
                    evidence = (
                        "no_buys_inconclusive"
                        if not bought
                        else (
                            "inventory_only"
                            if not metrics["sell_units_filled"]
                            else "hypothetical_sales"
                        )
                    )
                    row = {
                        "fold": i,
                        "scenario": name,
                        "model": model,
                        "limits": "current_limits_sensitivity",
                        "evidence": evidence,
                        "vacuous": bought == 0,
                        "fill_events": len(result.fills),
                        "tax_gp": sum(f["tax_gp"] for f in result.fills),
                        "buy_orders": sum(o["event"] == "buy_submitted" for o in result.orders),
                        **decision_gates(observations, predictions, model, assumptions),
                        **{
                            k: v
                            for k, v in metrics.items()
                            if k not in ("execution", "portfolio", "tax")
                        },
                    }
                    if name == "optimistic":
                        summary, ledger = fixed_fill_repricing(observations, result)
                        matched.append({"fold": i, "model": model, **summary})
                        atomic_json(pending / "fixed_fill_repricing.json", summary)
                        pd.DataFrame(ledger).to_parquet(
                            pending / "fixed_fill_repricing.parquet", index=False
                        )
                    atomic_json(pending / "metrics.json", {**row, **metrics})
                    pending.rename(path)
                    rows.append(row)
                    # Every completed replay is independently durable if interrupted.
                    run["completed_scenarios"] += 1
                    atomic_json(output / "run.json", run)
                    print(
                        f"fold={i} {name} {model}: {metrics['net_gp']:+,} gp; "
                        f"buy/sell units={bought}/{metrics['sell_units_filled']}; {evidence}",
                        flush=True,
                    )
        results = pd.DataFrame(rows)
        results.to_parquet(output / "results.parquet", index=False)
        results.to_csv(output / "results.csv", index=False)
        pd.DataFrame(matched).to_csv(output / "fixed_fill_repricing.csv", index=False)
        # Ensure no input changed during a potentially long replay.
        if sha256(panel) != hashes["panel"] or sha256(config_path) != hashes["config"]:
            raise ValueError("Panel/config changed during replay")
        if any(sha256(development_run / p) != value for p, value in inputs.items()):
            raise ValueError("Development artifacts changed during replay")
        run.update(
            status="complete",
            original_presets_reproduced=True,
            result_sha256=sha256(output / "results.parquet"),
        )
        atomic_json(output / "run.json", run)
        print(
            results[results.model == "catboost"]
            .pivot(index="scenario", columns="fold", values="net_gp")
            .to_string(),
            flush=True,
        )
        print(
            f"Completed {len(rows)} development sensitivities; original presets reproduced; "
            f"holdout NOT read. Artifacts: {output.resolve()}",
            flush=True,
        )
        return results
    except Exception as error:
        run.update(status="failed", failure=str(error))
        atomic_json(output / "run.json", run)
        raise
