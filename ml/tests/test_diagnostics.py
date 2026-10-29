"""Synthetic cases verify mechanics only; they are not market findings."""

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from osrs_ml.backtest import BacktestResult, simulate
from osrs_ml.data import manifest, sha256
from osrs_ml.diagnostics import (
    BASELINES,
    DAY,
    MODELS,
    diagnose,
    fixed_fill_repricing,
    scenarios,
    validate_fold,
)
from osrs_ml.execution import PortfolioPolicy

CONFIG_PATH = Path(__file__).resolve().parents[1] / "experiments/daily-v1.json"


def example():
    observations = pd.DataFrame(
        [
            dict(
                item_id=1,
                timestamp=t * DAY,
                available_at=(t + 1) * DAY + 300,
                avg_high_price=110,
                avg_low_price=100,
                high_price_volume=10000,
                low_price_volume=10000,
                buy_limit=None,
                buy_limit_current=100,
                high_freshness_seconds=300,
                low_freshness_seconds=300,
                source_interval_seconds=None,
                resolution_seconds=DAY,
                interval_unknown=True,
                inverted_spread=False,
                resolution_ambiguous=False,
                source="wiki",
            )
            for t in range(10)
        ]
    )
    predictions = observations[["item_id", "available_at"]].copy()
    for model in MODELS:
        predictions[model] = -np.inf if model in ("no_trade", "no_change") else 1.0
    fold = {"start": DAY + 300, "end": 11 * DAY + 300, "train_max_label_end": 300}
    return observations, predictions, fold


def test_fixed_quantities_repricing_tax_and_unsold_mark():
    observations, _, _ = example()
    # Buy 10 at 100, sell 7 at 110 (tax 2 each), mark remaining 3 at 98.
    # Original equity P&L = -1000 + 756 + 294 = 50.
    fills = [
        dict(
            item_id=1,
            timestamp=DAY + 300,
            side="buy",
            quantity=10,
            price_gp=100,
            cash_delta_gp=-1000,
            tax_gp=0,
        ),
        dict(
            item_id=1,
            timestamp=2 * DAY + 300,
            side="sell",
            quantity=7,
            price_gp=110,
            cash_delta_gp=756,
            tax_gp=14,
        ),
    ]
    result = BacktestResult(
        dict(
            execution={"passive_prices": True, "slippage_bps": 0},
            net_gp=50,
            end_inventory_mark_gp=294,
        ),
        fills,
        [],
        [],
    )
    summary, repriced = fixed_fill_repricing(observations, result)
    assert summary["buy_cash_change_gp"] == -100
    assert summary["sell_cash_change_gp"] == -70
    assert summary["crossed_net_gp_same_terminal_mark"] == -120
    assert summary["terminal_mark_gp_unchanged"] == 294
    assert repriced[1]["crossed_tax_gp"] == 14
    assert [f["quantity"] for f in repriced] == [10, 7]
    observations.loc[0, "avg_high_price"] = np.nan
    summary, _ = fixed_fill_repricing(observations, result)
    assert summary["missing_crossed_side_fills"] == 1
    assert summary["crossed_net_gp_same_terminal_mark"] is None


def test_fixed_fill_repricing_changes_tax_with_sale_price():
    observations, _, _ = example()
    observations["avg_low_price"] = 49
    result = BacktestResult(
        dict(
            execution={"passive_prices": True, "slippage_bps": 0},
            net_gp=58,
            end_inventory_mark_gp=0,
        ),
        [
            dict(
                item_id=1,
                timestamp=DAY + 300,
                side="sell",
                quantity=2,
                price_gp=50,
                cash_delta_gp=98,
                tax_gp=2,
            )
        ],
        [],
        [],
    )
    summary, ledger = fixed_fill_repricing(observations, result)
    assert ledger[0]["crossed_tax_gp"] == 0
    assert summary["crossed_net_gp_same_terminal_mark"] == 58


@pytest.mark.parametrize("failure", ["boundary", "duplicate", "coverage", "nan", "train_overlap"])
def test_reject_invalid_development_decisions(failure):
    observations, predictions, fold = example()
    cutoff = fold["end"]
    if failure == "boundary":
        predictions.loc[0, "available_at"] = cutoff
    elif failure == "duplicate":
        predictions = pd.concat([predictions, predictions.iloc[:1]])
    elif failure == "coverage":
        predictions = predictions.iloc[1:]
    elif failure == "nan":
        predictions.loc[0, "catboost"] = np.nan
    else:
        fold["train_max_label_end"] = fold["start"]
    with pytest.raises(ValueError):
        validate_fold(observations, predictions, fold, cutoff)


def test_ablation_changes_only_named_economics():
    policies = scenarios(json.loads(CONFIG_PATH.read_text()))
    base = asdict(policies["optimistic"])
    changed = asdict(policies["only_price_side"])
    assert {k for k in base if base[k] != changed[k]} == {"passive_prices"}
    assert policies["passive_slip_0bps"] == policies["optimistic"]
    assert policies["crossed_slip_0bps"] == policies["only_price_side"]
    assert policies["passive_slip_10bps"] == policies["only_slippage"]


def test_saved_undefined_scores_require_matching_missing_price_inputs():
    observations, predictions, fold = example()
    observations.loc[0, "avg_high_price"] = np.nan
    predictions.loc[0, ["no_change", "raw_spread", "spread_volume", "catboost"]] = np.nan
    validate_fold(observations, predictions, fold, fold["end"])
    # Matching is by item/time, independent of Arrow dtype or row order.
    validate_fold(observations.iloc[::-1], predictions, fold, fold["end"])
    observations.loc[0, "avg_high_price"] = 110
    with pytest.raises(ValueError, match="valid price inputs"):
        validate_fold(observations, predictions, fold, fold["end"])


@pytest.fixture
def frozen_run(tmp_path):
    observations, predictions, fold = example()
    config = json.loads(CONFIG_PATH.read_text())
    config["folds"] = 1
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    panel = tmp_path / "daily.parquet"
    # A poisoned future row must never enter any replay.
    future = observations.iloc[:1].copy()
    future["available_at"] = fold["end"]
    future["avg_low_price"] = 1000000000
    pd.concat([observations, future]).to_parquet(panel, index=False)
    manifest(panel, source="synthetic_test", rows=len(observations) + 1)
    development = tmp_path / "development"
    forecast = development / "fold0/forecast"
    forecast.mkdir(parents=True)
    predictions.to_parquet(forecast / "predictions.parquet", index=False)
    lock = CONFIG_PATH.parent.parent / "uv.lock"
    (development / "run.json").write_text(
        json.dumps(
            dict(
                status="development_complete",
                source="synthetic_test",
                config=config,
                panel_sha256=sha256(panel),
                config_sha256=sha256(config_path),
                lock_sha256=sha256(lock),
                folds=[fold],
                holdout_start=fold["end"],
            )
        )
    )
    (development / "holdout").mkdir()
    (development / "holdout/DO_NOT_READ").write_text("not development input")
    observations["buy_limit"] = observations.buy_limit_current
    portfolio = PortfolioPolicy(holding_seconds=DAY)
    policies = scenarios(config)
    for name in BASELINES:
        for model in MODELS:
            scores = {
                (1, int(r.available_at)): float(getattr(r, model)) for r in predictions.itertuples()
            }
            result = simulate(observations, scores, policies[name], portfolio)
            path = development / f"fold0/current_limits_sensitivity/{name}/{model}"
            path.mkdir(parents=True)
            (path / "metrics.json").write_text(json.dumps(result.metrics))
    return panel, development, tmp_path / "output", config_path


def test_complete_replay_controls_reproduction_and_immutability(frozen_run):
    panel, development, output, config_path = frozen_run
    before = {p: sha256(p) for p in development.rglob("*") if p.is_file()}
    results = diagnose(panel, development, output, config_path)
    assert len(results) == 95
    run = json.loads((output / "run.json").read_text())
    assert run["status"] == "complete"
    assert run["original_presets_reproduced"]
    assert run["holdout_read"] is False
    assert not any("holdout" in p for p in run["development_artifacts"])
    assert results[results.model == "no_trade"].net_gp.eq(0).all()
    assert results[results.model == "no_trade"].vacuous.all()
    assert (results.net_gp == results.end_cash_gp + results.end_inventory_mark_gp - 10000000).all()
    optimistic = results[results.scenario == "optimistic"].set_index("model")
    zero_slip = results[results.scenario == "passive_slip_0bps"].set_index("model")
    pd.testing.assert_series_equal(optimistic.net_gp, zero_slip.net_gp)
    for path in output.glob("fold*/optimistic/*/equity.parquet"):
        assert pd.read_parquet(path).timestamp.max() < run["holdout_start"]
    assert all(sha256(p) == value for p, value in before.items())
    with pytest.raises(FileExistsError):
        diagnose(panel, development, output, config_path)


def test_corrupt_inputs_and_baseline_drift_fail_closed(frozen_run):
    panel, development, output, config_path = frozen_run
    original = config_path.read_text()
    config_path.write_text(original + "\n")
    with pytest.raises(ValueError, match="Panel/config changed"):
        diagnose(panel, development, output, config_path)
    assert not output.exists()
    config_path.write_text(original)
    metric = development / "fold0/current_limits_sensitivity/optimistic/raw_spread/metrics.json"
    bad = json.loads(metric.read_text())
    bad["net_gp"] += 1
    metric.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="reproduction failed"):
        diagnose(panel, development, output, config_path)
    run = json.loads((output / "run.json").read_text())
    assert run["status"] == "failed"
    assert run["completed_scenarios"] == 2
    assert (output / "fold0/optimistic/no_trade/metrics.json").exists()
    assert not (output / "results.parquet").exists()
