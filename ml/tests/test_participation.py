"""Synthetic mechanics and safety checks, never market findings."""

import json
import shutil
from dataclasses import replace
from itertools import product
from pathlib import Path

import pandas as pd
import pytest
from osrs_ml.backtest import compatible_volume, simulate
from osrs_ml.data import sha256
from osrs_ml.execution_audit import audit
from osrs_ml.participation import SHARES_BPS, policies, run, summarize
from test_backtest import ASSUMPTIONS, PORTFOLIO, observations
from test_diagnostics import CONFIG_PATH

pytest_plugins = ["test_diagnostics"]

BOUNDED = replace(
    ASSUMPTIONS,
    fill_model="volume_bounded_v3",
    passive_prices=True,
    buy_timeout_seconds=1800,
)


def market(steps=16, volume=100):
    frame = observations(steps=steps, volume=volume)
    frame["resolution_seconds"] = 300
    frame["source_interval_seconds"] = 300
    frame["inverted_spread"] = False
    frame["avg_high_price"] = 110
    return frame


@pytest.mark.parametrize(
    "override",
    [
        {"price_model": "legacy_v1"},
        {"passive_prices": False},
        {"queue_fill_bps": 5000},
        {"fill_model": "unknown"},
        {"volume_qualification": "unknown"},
    ],
)
def test_invalid_policy_rejected(override):
    with pytest.raises(ValueError):
        replace(BOUNDED, **override)


def test_zero_share_is_only_valid_for_new_policy_and_cannot_trade():
    with pytest.raises(ValueError):
        replace(ASSUMPTIONS, participation_bps=0)
    result = simulate(market(), {(1, 300): 1.0}, replace(BOUNDED, participation_bps=0), PORTFOLIO)
    assert not result.fills
    assert result.metrics["net_gp"] == 0
    assert any(o["event"] == "buy_expired" for o in result.orders)


def test_moment_envelope_contains_exhaustive_small_integer_trade_distributions():
    # Actual compatible count must never exceed the independently computed ceiling.
    for prices in product(range(1, 7), repeat=3):
        mean = sum(prices) // len(prices)
        for threshold in range(1, 9):
            for buy in (False, True):
                count = sum(p <= threshold if buy else p >= threshold for p in prices)
                bound = compatible_volume(3, mean, threshold, buy=buy, rule="moment_upper")
                assert count <= bound <= 3
    assert compatible_volume(100, 100, 90, buy=True, rule="moment_upper") == 99
    assert compatible_volume(100, 100, 200, buy=False, rule="moment_upper") == 50
    assert compatible_volume(1, 100, 90, buy=True, rule="moment_upper") == 0
    assert compatible_volume(0, 1, 1, buy=False, rule="moment_upper") == 0
    with pytest.raises(ValueError):
        compatible_volume(1, 0, 100, buy=True, rule="mean_proxy")


def test_fixed_buy_price_and_average_qualification_do_not_follow_future_means():
    frame = market()
    frame.loc[1:, "avg_low_price"] = 90
    result = simulate(frame, {(1, 300): 1.0}, BOUNDED, PORTFOLIO)
    buys = [f for f in result.fills if f["side"] == "buy"]
    assert buys and {f["price_gp"] for f in buys} == {100}
    assert {f["bucket_mean_gp"] for f in buys} == {90}
    frame.loc[1:, "avg_low_price"] = 101
    assert not simulate(frame, {(1, 300): 1.0}, BOUNDED, PORTFOLIO).fills
    # An incompatible average does not rule out compatible trades in the envelope.
    frame.loc[1:, "avg_low_price"] = 103
    envelope = simulate(
        frame, {(1, 300): 1.0}, replace(BOUNDED, volume_qualification="moment_upper"), PORTFOLIO
    )
    assert envelope.fills[0]["quantity"] == 99


def test_fixed_sale_does_not_follow_future_high_average_and_waits_for_qualification():
    frame = market()
    frame.loc[3:, "avg_high_price"] = 109
    result = simulate(frame, {(1, 300): 1.0}, BOUNDED, PORTFOLIO)
    assert result.metrics["sell_units_filled"] == 0
    assert result.metrics["end_inventory_units"] == 100
    frame.loc[6:, "avg_high_price"] = 150
    result = simulate(frame, {(1, 300): 1.0}, BOUNDED, PORTFOLIO)
    sells = [f for f in result.fills if f["side"] == "sell"]
    assert sells and {f["price_gp"] for f in sells} == {110}
    assert min(f["timestamp"] for f in sells) == 2100


def test_partial_fills_expire_and_capacity_is_floored_per_bucket_without_carry():
    assumptions = replace(BOUNDED, participation_bps=100, buy_timeout_seconds=1200)
    result = simulate(market(volume=150), {(1, 300): 1.0}, assumptions, PORTFOLIO)
    buys = [f for f in result.fills if f["side"] == "buy"]
    assert [f["quantity"] for f in buys] == [1, 1, 1]
    assert result.metrics["end_open_buy_units"] == 0
    assert sum(f["quantity"] for f in buys) == 3
    assert all(f["participation_capacity"] == 1 for f in buys)
    assert not simulate(market(volume=99), {(1, 300): 1.0}, assumptions, PORTFOLIO).fills


def test_order_must_survive_entire_bucket_and_latency():
    frame = market()
    frame.loc[1:, "source_interval_seconds"] = 1800
    assumptions = replace(BOUNDED, buy_timeout_seconds=900, freshness_basis="lower_bound")
    assert not simulate(frame, {(1, 300): 1.0}, assumptions, PORTFOLIO).fills
    frame = market()
    result = simulate(frame, {(1, 300): 1.0}, replace(BOUNDED, latency_seconds=300), PORTFOLIO)
    assert result.fills[0]["bucket_start"] >= 600
    assert result.fills[0]["timestamp"] == 900


def test_buy_limit_not_multiplied_by_number_of_four_hour_windows_in_bucket():
    frame = market(steps=8, volume=10000)
    frame["timestamp"] *= 288
    frame["available_at"] *= 288
    frame["resolution_seconds"] = 86400
    frame["source_interval_seconds"] = 86400
    frame["buy_limit"] = 2
    assumptions = replace(BOUNDED, buy_timeout_seconds=345600, max_freshness_seconds=100000)
    result = simulate(frame, {(1, 86400): 1.0}, assumptions, PORTFOLIO)
    assert result.metrics["buy_units_filled"] == 2
    assert result.metrics["sell_units_filled"] == 2


def test_v3_retains_corrected_bps_lots_tax_and_least_permissive_edge():
    frame = market(volume=10000)
    assumptions = replace(BOUNDED, slippage_bps=100)
    result = simulate(frame, {(1, 300): 1.0}, assumptions, PORTFOLIO)
    # Fixed target buy 101, sale 108.9 allocated as adjacent legal integer lots.
    assert {f["price_gp"] for f in result.fills if f["side"] == "buy"} == {101}
    sells = [f for f in result.fills if f["side"] == "sell"]
    assert {f["price_gp"] for f in sells} == {108, 109}
    assert all(f["qualification_price_gp"] == 109 for f in sells)
    assert result.metrics["sell_slippage_cost_gp"] == 108
    assert sum(f["tax_gp"] for f in sells) == 198
    assert result.metrics["end_inventory_units"] == 0


@pytest.mark.parametrize("invalid", [0, 1.5])
def test_invalid_future_average_is_logged_without_filling(invalid):
    frame = market()
    frame["avg_low_price"] = frame.avg_low_price.astype(object)
    frame.loc[1:, "avg_low_price"] = invalid
    result = simulate(frame, {(1, 300): 1.0}, BOUNDED, PORTFOLIO)
    assert not result.fills
    assert any(o["event"] == "price_rejected" for o in result.orders)


def test_missing_or_untradeable_sale_reference_delays_submission():
    frame = market(volume=1000)
    frame["avg_high_price"] = frame.avg_high_price.astype("Int64")
    frame.loc[2:4, "avg_high_price"] = None
    result = simulate(frame, {(1, 300): 1.0}, BOUNDED, PORTFOLIO)
    sale = next(o for o in result.orders if o["event"] == "sell_submitted")
    assert sale["timestamp"] == 1800
    frame[["avg_high_price", "avg_low_price"]] = 1
    result = simulate(frame, {(1, 300): 1.0}, replace(BOUNDED, slippage_bps=5), PORTFOLIO)
    assert result.metrics["end_inventory_units"] > 0
    assert not any(o["event"] == "sell_submitted" for o in result.orders)
    assert result.metrics["end_unpriceable_inventory_units"] > 0


def test_frozen_grid_and_nonmonotonic_break_even_brackets():
    grid = policies(json.loads(CONFIG_PATH.read_text()))
    assert len(grid) == 54
    assert {p.participation_bps for p in grid.values()} == set(SHARES_BPS)
    assert all(
        p.price_model == "integer_lots_v2" and p.queue_fill_bps == 10000 for p in grid.values()
    )
    frame = pd.DataFrame(
        [
            dict(
                limits="current_limits_sensitivity",
                qualification="mean_proxy",
                preset="optimistic",
                fold=0,
                model="catboost",
                participation_bps=p,
                net_gp=gp,
                buy_units_filled=int(p > 0),
                sell_units_filled=int(p > 0),
                cash_pnl_gp=gp,
            )
            for p, gp in [(0, 0), (10, -2), (50, 3), (100, -1), (200, 5)]
        ]
    )
    summary, transitions = summarize(frame)
    assert summary.iloc[0].first_profitable_bps == 50
    assert summary.iloc[0].preceding_sample_bps == 10
    assert len(transitions) == 4
    frame["sell_units_filled"] = 0
    summary, _ = summarize(frame)
    assert summary.iloc[0].first_profitable_bps is None


def three_fold_run(frozen_run):
    panel, development, output, config_path = frozen_run
    config = json.loads(config_path.read_text())
    config["folds"] = 3
    config_path.write_text(json.dumps(config))
    metadata_path = development / "run.json"
    metadata = json.loads(metadata_path.read_text())
    metadata.update(config=config, config_sha256=sha256(config_path), folds=metadata["folds"] * 3)
    metadata_path.write_text(json.dumps(metadata))
    for i in (1, 2):
        shutil.copytree(development / "fold0/forecast", development / f"fold{i}/forecast")
    return panel, development, output, config_path


def test_full_replay_seals_holdout_audits_ledgers_and_refuses_overwrite(frozen_run, monkeypatch):
    panel, development, output, config_path = three_fold_run(frozen_run)
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert "holdout" not in path.parts
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    result = run(panel, development, output, config_path)
    assert len(result) == 810
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["status"] == "complete"
    assert manifest["holdout_read"] is False
    assert result[result.participation_bps == 0].net_gp.eq(0).all()
    assert result[result.model == "no_trade"].net_gp.eq(0).all()
    assert audit(output, panel)["scenarios"] == 810
    with pytest.raises(FileExistsError):
        run(panel, development, output, config_path)
    fills_path = output / "fold0/mean_proxy/optimistic/p10000/catboost/fills.parquet"
    fills = pd.read_parquet(fills_path)
    fills.loc[0, "participation_capacity"] += 1
    fills.to_parquet(fills_path, index=False)
    with pytest.raises(ValueError, match="Qualification/capacity"):
        audit(output, panel)


def test_changed_inputs_and_invalid_fold_fail_before_output(frozen_run):
    panel, development, output, config_path = three_fold_run(frozen_run)
    config_path.write_text(config_path.read_text() + "\n")
    with pytest.raises(ValueError, match="changed"):
        run(panel, development, output, config_path)
    assert not output.exists()


def test_first_fill_starts_buy_limit_and_sales_do_not_reset_it():
    frame = market(steps=70, volume=10000)
    frame["buy_limit"] = 2
    scores = {(1, int(t)): 1.0 for t in frame.available_at}
    result = simulate(frame, scores, BOUNDED, PORTFOLIO)
    buys = [f for f in result.fills if f["side"] == "buy"]
    assert buys[0]["timestamp"] == 600
    assert sum(f["quantity"] for f in buys if f["timestamp"] < 15000) == 2
    assert buys[1]["timestamp"] >= 15000


def test_failed_replay_keeps_completed_results_and_failure_manifest(frozen_run, monkeypatch):
    import osrs_ml.participation as participation

    panel, development, output, config_path = three_fold_run(frozen_run)
    original = participation.simulate
    calls = 0

    def interrupted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(participation, "simulate", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        run(panel, development, output, config_path)
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["completed_scenarios"] == 1
    assert (output / "fold0/mean_proxy/optimistic/p00000/no_trade/metrics.json").exists()
    assert not (output / "results.parquet").exists()
