from dataclasses import replace

import pandas as pd
from osrs_ml.backtest import simulate
from osrs_ml.execution import ExecutionAssumptions, PortfolioPolicy

ASSUMPTIONS = ExecutionAssumptions(
    "test", 10_000, 0, 0, 900, buy_timeout_seconds=600, terminal_haircut_bps=0
)
PORTFOLIO = PortfolioPolicy(
    initial_cash_gp=10_000, allocation_bps=10_000, offer_slots=1, holding_seconds=300
)


def observations(steps=12, items=(1,), volume=3, buy_limit=1000):
    return pd.DataFrame(
        [
            dict(
                item_id=item,
                timestamp=step * 300,
                available_at=(step + 1) * 300,
                avg_high_price=100,
                avg_low_price=100,
                high_price_volume=volume,
                low_price_volume=volume,
                buy_limit=buy_limit,
                high_freshness_seconds=0,
                low_freshness_seconds=0,
                interval_unknown=False,
            )
            for step in range(steps)
            for item in items
        ]
    )


def signals(frame):
    return {(int(r.item_id), int(r.available_at)): 0.1 for r in frame.itertuples()}


def test_no_trade_has_exactly_zero_return():
    result = simulate(observations(), {}, ASSUMPTIONS, PORTFOLIO)
    assert result.metrics["net_gp"] == 0
    assert result.metrics["max_drawdown"] == 0
    assert result.metrics["fill_rate"] == 0
    assert result.fills == []


def test_partial_fill_expiry_tax_and_wait():
    frame = observations()
    # One order, filled only once before expiry: rest of reservation is released.
    result = simulate(frame, {(1, 300): 0.1}, ASSUMPTIONS, PORTFOLIO)
    assert [f["quantity"] for f in result.fills] == [3, 3]
    assert [f["timestamp"] for f in result.fills] == [600, 1200]
    assert result.metrics["fill_rate"] == 0.03
    assert result.metrics["mean_buy_wait_seconds"] == 300
    assert result.metrics["realized_gp"] == -6
    assert result.metrics["net_gp"] == -6
    assert result.metrics["end_inventory_units"] == 0
    assert any(o["event"] == "buy_expired" for o in result.orders)


def test_reservation_slots_and_cash_conservation():
    frame = observations(items=(1, 2))
    result = simulate(frame, signals(frame), ASSUMPTIONS, PORTFOLIO)
    assert max(p["active_slots"] for p in result.equity) <= 1
    assert min(p["cash_gp"] for p in result.equity) >= 0
    assert result.metrics["end_cash_gp"] == (10_000 + sum(f["cash_delta_gp"] for f in result.fills))


def test_buy_limit_starts_at_first_fill_and_sales_do_not_reset():
    frame = observations(steps=60, volume=1000, buy_limit=2)
    result = simulate(frame, signals(frame), ASSUMPTIONS, PORTFOLIO)
    buys = [f for f in result.fills if f["side"] == "buy"]
    assert buys[0]["timestamp"] == 600
    assert sum(f["quantity"] for f in buys if f["timestamp"] < 15_000) == 2
    assert buys[1]["timestamp"] >= 15_000


def test_unsold_inventory_is_marked_after_tax_and_haircut():
    frame = observations(steps=3, volume=10)
    result = simulate(
        frame, {(1, 300): 0.1}, replace(ASSUMPTIONS, terminal_haircut_bps=1000), PORTFOLIO
    )
    assert result.metrics["end_inventory_units"] == 10
    assert result.metrics["end_cash_gp"] == 9000
    assert result.metrics["end_inventory_mark_gp"] == 890  # 90 - floor(1.8) per item
    assert result.metrics["net_gp"] == -110
    assert result.metrics["cash_pnl_gp"] == -1000
    assert result.metrics["end_capital_tied_gp"] == 1000


def test_zero_volume_and_stale_prices_do_not_fill():
    frame = observations(volume=0)
    assert not simulate(frame, signals(frame), ASSUMPTIONS, PORTFOLIO).fills
    frame = observations()
    frame["high_freshness_seconds"] = 10000
    assert not simulate(frame, signals(frame), ASSUMPTIONS, PORTFOLIO).fills


def test_latency_and_no_same_bucket_fills():
    frame = observations(volume=1000)
    assumptions = replace(ASSUMPTIONS, latency_seconds=300, buy_timeout_seconds=1200)
    result = simulate(frame, {(1, 300): 0.1}, assumptions, PORTFOLIO)
    assert result.fills[0]["timestamp"] == 900
    sells = [f for f in result.fills if f["side"] == "sell"]
    sell_submission = next(o["timestamp"] for o in result.orders if o["event"] == "sell_submitted")
    assert sells[0]["timestamp"] > sell_submission + 300


def test_missing_limits_and_unknown_intervals_disable_buying():
    frame = observations()
    frame["buy_limit"] = None
    assert not simulate(frame, signals(frame), ASSUMPTIONS, PORTFOLIO).orders
    frame = observations()
    frame["interval_unknown"] = True
    assert not simulate(frame, signals(frame), ASSUMPTIONS, PORTFOLIO).orders


def test_reservations_prevent_overcommitting_across_slots():
    frame = observations(steps=2, items=(1, 2))
    portfolio = replace(PORTFOLIO, offer_slots=2)
    result = simulate(frame, signals(frame), ASSUMPTIONS, portfolio)
    submitted = [o for o in result.orders if o["event"] == "buy_submitted"]
    assert len(submitted) == 1
    assert result.equity[0]["capital_tied_gp"] == 10_000


def test_aggregate_freshness_uncertainty_is_explicit():
    frame = observations()
    frame["source_interval_seconds"] = 3600
    upper = simulate(frame, signals(frame), ASSUMPTIONS, PORTFOLIO)
    lower = simulate(
        frame, signals(frame), replace(ASSUMPTIONS, freshness_basis="lower_bound"), PORTFOLIO
    )
    assert not upper.orders
    assert lower.fills


def test_cheap_bps_lots_preserve_quantity_cash_and_measure_costs():
    frame = observations(volume=1000)
    frame[["avg_high_price", "avg_low_price"]] = 3
    assumptions = replace(ASSUMPTIONS, slippage_bps=5)
    result = simulate(frame, {(1, 300): 1.0}, assumptions, PORTFOLIO)
    assert result.metrics["buy_units_filled"] == 1000
    assert result.metrics["sell_units_filled"] == 1000
    assert result.metrics["buy_slippage_cost_gp"] == 1
    assert result.metrics["sell_slippage_cost_gp"] == 1
    assert result.metrics["buy_cost_rounding_gp"] == 0.5
    assert result.metrics["sell_cost_rounding_gp"] == 0.5
    assert result.metrics["net_gp"] == -2
    assert result.metrics["end_cash_gp"] == 9998
    assert all(f["price_gp"] >= 1 for f in result.fills)
    # Reserve at 4, pay almost entirely at 3: reservation is not a paid cost.
    assert result.orders[0]["buy_ceiling_gp"] == 4
    assert result.equity[0]["capital_tied_gp"] == 1000 * 4


def test_untradeable_sale_retains_inventory_slot_and_has_no_proceeds():
    frame = observations(volume=1000)
    frame["avg_high_price"] = 3
    frame["avg_low_price"] = 1
    assumptions = replace(ASSUMPTIONS, slippage_bps=5)
    result = simulate(frame, {(1, 300): 1.0}, assumptions, PORTFOLIO)
    assert result.metrics["sell_units_filled"] == 0
    assert result.metrics["end_inventory_units"] == 1000
    assert result.metrics["end_unpriceable_inventory_units"] == 1000
    assert result.metrics["untradeable_at_granularity"] > 0
    assert result.equity[-1]["active_slots"] == 1
    assert result.metrics["end_cash_gp"] == 6999
    assert result.metrics["end_inventory_mark_gp"] == 0
    assert result.metrics["realized_gp"] == 0
    assert all(f["side"] == "buy" for f in result.fills)
    legacy = simulate(
        frame, {(1, 300): 1.0}, replace(assumptions, price_model="legacy_v1"), PORTFOLIO
    )
    assert any(f["price_gp"] == 0 and f["side"] == "sell" for f in legacy.fills)


def test_invalid_reference_is_logged_without_truncation_or_zero_division():
    for invalid in (0, -1, 1.5):
        frame = observations()
        frame["avg_high_price"] = invalid
        result = simulate(frame, signals(frame), ASSUMPTIONS, PORTFOLIO)
        assert not result.fills
        assert result.metrics["invalid_reference_price"] == len(frame)
        assert all(o["event"] == "price_rejected" for o in result.orders)


def test_tax_is_per_actual_integer_lot_not_fractional_mean():
    frame = observations(volume=1000)
    frame[["avg_high_price", "avg_low_price"]] = 50
    result = simulate(frame, {(1, 300): 1.0}, replace(ASSUMPTIONS, slippage_bps=100), PORTFOLIO)
    # Portfolio reserves 51 GP per unit, buys 196 units at 50/51, sells at 49/50.
    assert result.metrics["buy_units_filled"] == 196
    assert result.metrics["sell_units_filled"] == 196
    sells = [f for f in result.fills if f["side"] == "sell"]
    assert [(f["price_gp"], f["quantity"]) for f in sells] == [(49, 98), (50, 98)]
    assert sum(f["tax_gp"] for f in sells) == 98
    assert result.metrics["net_gp"] == -294


def test_compose_terminal_costs_before_rounding_and_do_not_liquidate():
    frame = observations(steps=3, volume=1000)
    frame[["avg_high_price", "avg_low_price"]] = 3
    result = simulate(
        frame,
        {(1, 300): 1.0},
        replace(ASSUMPTIONS, slippage_bps=5, terminal_haircut_bps=100),
        PORTFOLIO,
    )
    # Target mark is 3 * .9995 * .99 = 2.968515; ceil(2968.515) = 2969.
    assert result.metrics["end_inventory_mark_gp"] == 2969
    assert result.metrics["end_inventory_units"] == 1000
    assert result.metrics["end_cash_gp"] == 6999
    assert result.metrics["sell_units_filled"] == 0
    assert result.metrics["net_gp"] == -32


def test_explicit_tick_stress_is_recorded_separately_from_bps():
    frame = observations(volume=1000)
    frame[["avg_high_price", "avg_low_price"]] = 3
    result = simulate(frame, {(1, 300): 1.0}, replace(ASSUMPTIONS, adverse_ticks=1), PORTFOLIO)
    assert result.metrics["buy_tick_cost_gp"] == 1000
    assert result.metrics["sell_tick_cost_gp"] == 1000
    assert result.metrics["buy_slippage_cost_gp"] == 0
    assert result.metrics["sell_slippage_cost_gp"] == 0
    assert result.metrics["net_gp"] == -2000
