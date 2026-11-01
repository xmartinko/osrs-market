"""Unit tests for Phase One P1 causal economic backtest (osrs_ml.probabilistic_backtest)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from osrs_ml.backtest import PreparedObservations, simulate
from osrs_ml.costs import DEFAULT_TAX, sale_proceeds
from osrs_ml.probabilistic_backtest import (
    HOUR,
    aggregate_fold_runs,
    analyze_backtest_result,
    build_backtest_observations,
    build_policy_signals,
    compute_validation_market_wall,
    make_crossed_assumptions,
    make_portfolio_policy,
    select_training_grid_cell,
    transform_quantiles_for_control,
    verify_holdout_untouched,
)
from osrs_ml.probabilistic_train import HOLDOUT_START


def _make_synthetic_panel(
    start_ts: int,
    n_hours: int,
    items: list[tuple[int, float, float, int, int]],
) -> pd.DataFrame:
    """Create a causal hourly panel with available_at = ts + 3900."""
    rows = []
    for h in range(n_hours):
        ts = start_ts + h * HOUR
        for item_id, ask, bid, hvol, lvol in items:
            mid = 0.5 * (ask + bid) if np.isfinite(ask) and np.isfinite(bid) else np.nan
            rows.append(
                {
                    "ts": ts,
                    "item_id": item_id,
                    "mid_price": mid,
                    "avg_high_price": ask,
                    "avg_low_price": bid,
                    "high_price_volume": float(hvol),
                    "low_price_volume": float(lvol),
                    "available_at": ts + HOUR + 300,
                    "usable": bool(hvol > 0 and lvol > 0 and ask >= bid > 0),
                }
            )
    return pd.DataFrame(rows)


def test_holdout_guard_blocks_sealed_timestamps_and_boundary_availability():
    w_start = HOLDOUT_START - 20 * HOUR
    w_end = HOLDOUT_START - 300  # 1785024000 (Fold 3 end)
    items_df = pd.DataFrame({"id": [4151], "name": ["Whip"], "buy_limit": [70]})

    # Last bucket ts = w_end - 3600 has available_at == HOLDOUT_START and must be excluded.
    frame = _make_synthetic_panel(w_start, 20, [(4151, 1_500_000.0, 1_480_000.0, 200, 200)])
    obs = build_backtest_observations(frame, items_df, w_start, w_end)
    assert (obs["timestamp"] < w_end).all()
    assert (obs["available_at"] < w_end).all()
    assert (obs["available_at"] < HOLDOUT_START).all()

    with pytest.raises(ValueError, match="holdout"):
        verify_holdout_untouched(frame, w_start, HOLDOUT_START + HOUR)

    tainted = frame.copy()
    tainted.loc[tainted.index[-1], "ts"] = HOLDOUT_START
    with pytest.raises(ValueError, match="holdout"):
        build_backtest_observations(tainted, items_df, w_start, w_end)


def test_causal_whole_bucket_latency_and_zero_volume_no_fill():
    w_start = 1_761_696_000
    w_end = w_start + 16 * HOUR
    items_df = pd.DataFrame(
        {"id": [100, 200], "name": ["LiquidItem", "UnknownLimit"], "buy_limit": [500, np.nan]}
    )
    spec_items = [(100, 1000.4, 990.2, 1000, 1000), (200, 500.0, 495.0, 1000, 1000)]
    frame = _make_synthetic_panel(w_start, 16, spec_items)
    # Make h=2 bucket zero-volume on high side so buy cannot fill inside 7500s timeout.
    mask_h2 = (frame["item_id"] == 100) & (frame["ts"] == w_start + 2 * HOUR)
    frame.loc[mask_h2, ["avg_high_price", "high_price_volume", "usable"]] = [np.nan, 0.0, False]

    obs = build_backtest_observations(frame, items_df, w_start, w_end)
    prep = PreparedObservations(obs)
    assump = make_crossed_assumptions(200)
    first_avail = w_start + HOUR + 300
    scores = {(100, first_avail): 2.0, (200, first_avail): 5.0}
    portfolio = make_portfolio_policy(4, initial_cash_gp=1_000_000)

    # Zero-volume h=2 never fills, and item 200 has NA buy_limit -> 0 filled units.
    res_zero_h2 = simulate(prep, scores, assump, portfolio, DEFAULT_TAX)
    assert res_zero_h2.metrics["buy_units_filled"] == 0

    # Restore positive volume at h=2 and make hold hour 5 zero-volume on low side.
    frame2 = _make_synthetic_panel(w_start, 16, spec_items)
    mask_h5 = (frame2["item_id"] == 100) & (frame2["ts"] == w_start + 5 * HOUR)
    frame2.loc[mask_h5, ["avg_low_price", "low_price_volume", "usable"]] = [np.nan, 0.0, False]
    obs2 = build_backtest_observations(frame2, items_df, w_start, w_end)
    res_ok = simulate(PreparedObservations(obs2), scores, assump, portfolio, DEFAULT_TAX)

    buy_fills = [f for f in res_ok.fills if f["side"] == "buy"]
    assert len(buy_fills) == 1
    assert buy_fills[0]["item_id"] == 100
    # h=1 (ts = w_start + 3600 < submitted + 300) is skipped; earliest fill is h=2!
    assert buy_fills[0]["timestamp"] == w_start + 2 * HOUR + HOUR + 300
    assert buy_fills[0]["quantity"] == 20
    assert res_ok.metrics["end_unpriceable_inventory_units"] == 0


def test_policy_signals_enforce_cost_wall_and_null_controls():
    w_start = 1_761_696_000
    w_end = w_start + 48 * HOUR
    origins_df = pd.DataFrame(
        {
            "item_id": [501, 501, 502],
            "timestamp": [w_start, w_start + HOUR, w_start],
            "available_at": [w_start + 3900, w_start + 7500, w_start + 3900],
            "avg_high_price": pd.array([1010, 1010, 1010], dtype="Int64"),
            "avg_low_price": pd.array([990, 990, 990], dtype="Int64"),
        }
    )
    quantiles = np.zeros((3, 3, 5), dtype=np.float64)
    # Row 0: +1.5% median move -> below ~4.2% cost wall -> rejected.
    quantiles[0, 0] = [-0.01, -0.005, 0.001, 0.006, 0.012]
    quantiles[0, 1] = [0.00, 0.005, 0.010, 0.015, 0.020]
    quantiles[0, 2] = [0.00, 0.008, 0.015, 0.022, 0.030]

    # Row 1: +6.5% median 24h move -> clears ~4.2% cost wall -> accepted.
    quantiles[1, 0] = [-0.012, -0.004, 0.001, 0.005, 0.010]
    quantiles[1, 1] = [-0.005, 0.005, 0.015, 0.025, 0.035]
    quantiles[1, 2] = [0.035, 0.050, 0.065, 0.080, 0.095]

    # Row 2: +6.5% 24h move but q10_h1 = -0.08 <= -0.05 -> blocked by h=1 crash gate.
    quantiles[2] = quantiles[1]
    quantiles[2, 0, 0] = -0.08

    scores, allocs, funnel = build_policy_signals(
        origins_df,
        quantiles,
        window_start=w_start,
        window_end=w_end,
        holding_hours=24,
        min_net_edge_bps=25,
    )
    assert list(scores.keys()) == [(501, w_start + 7500)]
    assert 100 <= allocs[(501, w_start + 7500)] <= 1250
    assert funnel["selected_signals"] == 1

    q_det = transform_quantiles_for_control(origins_df, quantiles, "null_detrended_zero_drift")
    assert np.allclose(q_det[:, :, 2], 0.0)
    scores_det, _, _ = build_policy_signals(
        origins_df,
        q_det,
        window_start=w_start,
        window_end=w_end,
        holding_hours=24,
        min_net_edge_bps=0,
    )
    assert scores_det == {}

    q_flip = transform_quantiles_for_control(origins_df, quantiles, "null_sign_flipped")
    assert np.allclose(q_flip[:, :, 2], -quantiles[:, :, 2])
    assert np.allclose(q_flip[:, :, 3] - q_flip[:, :, 1], quantiles[:, :, 3] - quantiles[:, :, 1])


def test_roundtrip_accounting_identity_spread_distributions_and_aggregation():
    w_start = 1_761_696_000
    n_hours = 36
    w_end = w_start + n_hours * HOUR
    items_df = pd.DataFrame(
        {"id": [301, 302], "name": ["ItemA", "ItemB"], "buy_limit": [1000, 1000]}
    )

    rows = []
    for h in range(n_hours):
        ts = w_start + h * HOUR
        mult_a = 1.08 if h >= 4 else 1.00
        rows.append(
            {
                "ts": ts,
                "item_id": 301,
                "mid_price": 1000.0 * mult_a,
                "avg_high_price": 1010.0 * mult_a,
                "avg_low_price": 990.0 * mult_a,
                "high_price_volume": 5000.0,
                "low_price_volume": 5000.0,
                "available_at": ts + HOUR + 300,
                "usable": True,
            }
        )
        rows.append(
            {
                "ts": ts,
                "item_id": 302,
                "mid_price": 2000.0,
                "avg_high_price": 2020.0,
                "avg_low_price": 1980.0,
                "high_price_volume": 5000.0,
                "low_price_volume": 5000.0,
                "available_at": ts + HOUR + 300,
                "usable": True,
            }
        )
    frame = pd.DataFrame(rows)
    obs = build_backtest_observations(frame, items_df, w_start, w_end)
    first_avail = w_start + HOUR + 300
    scores = {(301, first_avail): 3.0, (302, first_avail): 2.0}
    allocs = {(301, first_avail): 500, (302, first_avail): 500}
    assump = make_crossed_assumptions(200)
    portfolio = make_portfolio_policy(4, initial_cash_gp=10_000_000)

    res = simulate(
        PreparedObservations(obs), scores, assump, portfolio, DEFAULT_TAX, allocation_bps=allocs
    )
    summary, inc, trades, spreads = analyze_backtest_result(
        res,
        obs,
        window_start=w_start,
        window_end=w_end,
        funnel={"selected_signals": 2},
    )

    assert summary["completed_round_trips"] == 2
    assert summary["end_inventory_units"] == 0
    decomp = summary["cost_decomposition_completed_trades"]
    assert decomp["completed_net_pnl_gp"] == summary["realized_gp"] == summary["net_gp"]
    reconstructed = (
        decomp["completed_gross_mid_pnl_gp"]
        - decomp["completed_pure_half_spread_cost_gp"]
        - decomp["completed_explicit_slippage_cost_gp"]
        - decomp["completed_ge_tax_cost_gp"]
    )
    assert abs(reconstructed - decomp["completed_net_pnl_gp"]) < 1e-6
    assert summary["per_trade_sharpe"] is not None
    assert summary["annualised_sharpe_hourly"] is not None
    rt_sp = summary["spread_distributions"]["completed_realised_rt_spread_plus_slip_pct"]
    assert rt_sp["count"] == 2
    assert int(round(inc.sum())) == summary["net_gp"]

    agg = aggregate_fold_runs(
        {1: summary}, {1: inc}, {1: trades}, {1: spreads}, initial_cash_gp=10_000_000
    )
    assert agg["net_gp"] == summary["net_gp"]
    assert agg["completed_round_trips"] == 2

    wall = compute_validation_market_wall(frame, folds={1: (w_start, w_start, w_end)})
    assert wall["continuous_quoted_spread_pct"]["count"] > 0
    assert abs(wall["continuous_quoted_spread_pct"]["p50"] - 2.0) < 0.05

    selected = select_training_grid_cell(
        {
            "H4h_edge25bps": {
                "net_gp": 0,
                "turnover": 0.2,
                "holding_hours": 4,
                "min_net_edge_bps": 25,
            },
            "H24h_edge50bps": {
                "net_gp": 0,
                "turnover": 0.0,
                "holding_hours": 24,
                "min_net_edge_bps": 50,
            },
        }
    )
    assert selected == "H24h_edge50bps"
    assert sale_proceeds(50, 1, DEFAULT_TAX) == 49
