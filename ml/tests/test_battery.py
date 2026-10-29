"""Deterministic accounting fixtures only; no generated market evidence."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from osrs_ml.backtest import simulate
from osrs_ml.battery import (
    DAY,
    bootstrap_test,
    common_features,
    completed_positions,
    corrected,
    exact,
    sealed_read,
    strategy_scores,
)
from osrs_ml.execution import ExecutionAssumptions, PortfolioPolicy
from osrs_ml.mechanical import simulate_mechanical


def frame(steps=35, items=(1,), prices=None):
    return pd.DataFrame([
        dict(item_id=i, timestamp=t * DAY, available_at=(t + 1) * DAY + 300,
             avg_high_price=(prices or {}).get((i, t), 100),
             avg_low_price=(prices or {}).get((i, t), 100),
             high_price_volume=100000, low_price_volume=100000, buy_limit=10000,
             resolution_seconds=DAY, source_interval_seconds=DAY, interval_unknown=False,
             inverted_spread=False, high_freshness_seconds=300, low_freshness_seconds=300)
        for i in items for t in range(steps)])


def test_frozen_family_has_exactly_71_unique_rules_and_213_tests():
    config = json.loads((Path(__file__).parents[1] / "strategy-battery-v1.json").read_text())
    specs = config["hypotheses"]
    assert len({s["id"] for s in specs}) == len(specs) == 71
    assert len(specs) * len(config["participation_bps"]) == config["family_size"] == 213
    assert sorted({s["horizon"] for s in specs}) == [300, 3600, 14400, DAY, 7*DAY, 28*DAY]


def test_boundary_filter_excludes_market_sentinels_and_rejects_bad_bounds(tmp_path):
    f = frame(steps=4)
    f.loc[f.available_at >= 3 * DAY, "avg_high_price"] = 987654321
    path = tmp_path / "panel.parquet"
    f.to_parquet(path)
    sealed = sealed_read(path, 3 * DAY)
    assert len(sealed) == 2
    assert (sealed.available_at < 3 * DAY).all()
    assert 987654321 not in sealed.avg_high_price.to_list()
    with pytest.raises(ValueError, match="boundary"):
        sealed_read(path, 0)


def test_exact_lags_and_volatility_never_bridge_gaps():
    f = frame(steps=7).drop(index=3).reset_index(drop=True)
    prior = exact(f, f.avg_high_price, DAY)
    assert np.isnan(prior[f.timestamp.eq(4 * DAY)])[0]
    features = common_features(f, DAY)
    assert np.isnan(features.loc[features.timestamp.eq(4 * DAY), "ret"]).all()
    assert np.isnan(features.loc[features.timestamp.eq(6 * DAY), "vol"]).all()


def test_patient_uses_own_lags_and_throttles_without_future_selection():
    prices = {(i, t): 50 if t >= 8 else 100 for i in (1, 2) for t in range(35)}
    f = frame(items=(1, 2), prices=prices)
    spec = dict(rule="patient", horizon=7*DAY, resolution=DAY, holding=3*DAY, threshold=.1)
    scores, _, _ = strategy_scores(f, spec, 0, 36 * DAY)
    assert scores
    dates = [ts for _, ts in scores]
    assert len(dates) == len(set(dates))
    assert all(((ts - DAY - 300) // DAY) % 2 == 0 for ts in dates)
    assert all(item == 1 for item, _ in scores)  # stable ID tie, no outcome tie breaker
    assert max(dates) < 36 * DAY - 6 * DAY
    changed = f.copy()
    changed.loc[changed.timestamp >= 18 * DAY, ["avg_high_price", "avg_low_price"]] = 99999
    future_changed, _, _ = strategy_scores(changed, spec, 0, 36 * DAY)
    assert {k: v for k, v in scores.items() if k[1] < 18*DAY} == {
        k: v for k, v in future_changed.items() if k[1] < 18*DAY}


def test_cross_item_lead_signal_cannot_use_follower_future():
    prices = {(257, t): 110 if t >= 10 else 100 for t in range(35)}
    f = frame(items=(257, 2434), prices=prices)
    spec = dict(rule="lead", horizon=DAY, resolution=DAY, holding=DAY, family="herbs")
    scores, _, _ = strategy_scores(f, spec, 0, 36 * DAY)
    assert set(scores) == {(2434, 11 * DAY + 300)}
    assert scores[(2434, 11 * DAY + 300)] == pytest.approx(.1)


def test_search_adjustment_and_inadequate_data_are_not_significant():
    assert corrected(.01) == 1.
    assert corrected(.0001) == pytest.approx(.0213)
    with pytest.raises(ValueError):
        corrected(float("nan"))
    report = bootstrap_test(np.arange(20), [7, 14], completed=100, draws=100)
    assert not report["adequate"] and report["p"] == 1
    report = bootstrap_test(np.zeros(100), [7, 14], completed=100, draws=100)
    assert report["p"] == 1 and report["lower"] == 0


def test_bootstrap_is_centered_reproducible_and_uses_whole_increments():
    x = np.tile([10., 20., 30., 15.], 25)
    a = bootstrap_test(x, [7, 14], completed=20, draws=999)
    b = bootstrap_test(x, [7, 14], completed=20, draws=999)
    assert a == b and a["adequate"] and a["lower"] > 0
    assert a["p"] == .001
    assert bootstrap_test(-x, [7, 14], completed=20, draws=99)["p"] == 1.


def test_optional_allocation_changes_only_requested_budget_and_validates():
    f = frame(steps=10)
    assumptions = ExecutionAssumptions("test", 10000, 0, 0, 2 * DAY,
                                      buy_timeout_seconds=4 * DAY)
    portfolio = PortfolioPolicy(initial_cash_gp=10000, allocation_bps=1000, holding_seconds=DAY)
    scores = {(1, DAY + 300): 1.}
    normal = simulate(f, scores, assumptions, portfolio)
    identical = simulate(f, scores, assumptions, portfolio, allocation_bps={})
    assert normal == identical
    smaller = simulate(f, scores, assumptions, portfolio, allocation_bps={(1, DAY + 300): 500})
    assert smaller.metrics["buy_units_requested"] * 2 == normal.metrics["buy_units_requested"]
    with pytest.raises(ValueError, match="allocation"):
        simulate(f, scores, assumptions, portfolio, allocation_bps={(1, DAY + 300): 0})


def mechanical_mapping():
    return pd.DataFrame([dict(id=i, high_alch=a, buy_limit=10000)
                         for i, a in [(1, 400), (561, 0), (70, 0), (1777, 0), (859, 0),
                                      (66, 0), (855, 0)]])


def test_alchemy_consumes_owned_runes_and_charges_staff_and_active_time():
    f = frame(steps=24, items=(1, 561))
    result, count = simulate_mechanical(f, mechanical_mapping(), "alchemy", 100)
    assert count > 0
    production = [r for r in result.orders if r["event"] == "production"]
    assert all(0 < r["quantity"] <= 916 for r in production)
    assert all(r["coins_gp"] == r["quantity"] * 400 for r in production)
    assert result.metrics["fixed_cost_gp"] == 1500
    assert result.metrics["active_hours"] <= len(production)
    assert result.metrics["net_gp"] == result.equity[-1]["equity_gp"] - 10_000_000
    assert all(f["bucket_start"] >= f["submitted"] + 300 for f in result.fills)
    assert max(r["active_slots"] for r in result.equity) <= 8
    for p in production:
        for item in (1, 561):
            assert sum(f["quantity"] for f in result.fills
                       if f["item_id"] == item and f["timestamp"] < p["timestamp"]) >= p["quantity"]


def test_alchemy_cannot_manufacture_missing_rune_fills():
    f = frame(steps=24, items=(1, 561))
    f.loc[(f.item_id == 561) & (f.timestamp > 0), "high_price_volume"] = 0
    result, count = simulate_mechanical(f, mechanical_mapping(), "alchemy", 100)
    assert count == 0
    assert result.metrics["produced_units"] == 0
    assert result.metrics["end_inventory_units"] > 0
    assert not any(o["event"] == "production" for o in result.orders)


def test_processing_has_separate_input_legs_delayed_sale_and_tax():
    prices = {(859, t): 400 for t in range(28)}
    f = frame(steps=28, items=(70, 1777, 859), prices=prices)
    result, count = simulate_mechanical(f, mechanical_mapping(), "processing", 100)
    assert count > 0
    assert result.metrics["produced_units"] > 0
    sales = [r for r in result.fills if r["side"] == "sell"]
    assert all(r["item_id"] == 859 and r["tax_gp"] > 0 for r in sales)
    assert all(r["bucket_start"] >= r["submitted"] + 300 for r in sales)
    assert sum(r["quantity"] for r in sales) <= result.metrics["produced_units"]
    assert result.metrics["end_inventory_units"] >= 0
    with pytest.raises(ValueError, match="shop"):
        simulate_mechanical(f, mechanical_mapping(), "shop", 100)


def test_limit_and_participation_caps_apply_to_each_mechanical_leg():
    f = frame(steps=24, items=(1, 561))
    f["high_price_volume"] = 10000
    mapping = mechanical_mapping()
    mapping.loc[mapping.id == 1, "buy_limit"] = 3
    result, _ = simulate_mechanical(f, mapping, "alchemy", 10)
    assert result.fills
    fill_groups = pd.DataFrame(result.fills).groupby(["item_id", "timestamp"]).quantity.sum()
    assert fill_groups.max() <= 10
    assert fill_groups.loc[1].max() <= 3


def test_completion_counts_partial_sales_once():
    fills = [dict(item_id=1, side=s, quantity=q) for s, q in [("buy", 5), ("sell", 2),
                                                          ("sell", 3), ("buy", 1)]]
    assert completed_positions(fills) == 1


def test_default_tax_exemption_is_scoped_to_registered_low_tax_rule():
    f = frame(prices={(1, t): 100 for t in range(35)})
    f["avg_low_price"] = 99
    spec = dict(rule="low_tax", horizon=DAY, resolution=DAY, holding=DAY)
    assert not strategy_scores(f, spec, 0, 36*DAY)[0]
    from osrs_ml.costs import DEFAULT_TAX
    tax = replace(DEFAULT_TAX, exempt_item_ids=(1,))
    assert strategy_scores(f, spec, 0, 36*DAY, tax)[0]
