"""Unit tests for Phase One P1b 300s execution-resolution backtest."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from osrs_ml.backtest import PreparedObservations, simulate
from osrs_ml.costs import DEFAULT_TAX, TaxPolicy, sale_proceeds
from osrs_ml.probabilistic_backtest import (
    HOUR,
    build_backtest_observations,
    make_crossed_assumptions,
    make_passive_v3_assumptions,
    make_portfolio_policy,
)
from osrs_ml.probabilistic_backtest_p1b import (
    FIVE_MIN,
    CausalObsIndex,
    _vec_sale_proceeds_unit,
    analyze_backtest_result_p1b,
    build_backtest_observations_300s,
    load_verified_5m_execution_bars,
    make_crossed_300s_assumptions,
)
from osrs_ml.probabilistic_train import HOLDOUT_START, file_hash


def test_vec_sale_proceeds_matches_costs_exact_integer_arithmetic():
    prices = np.array(
        [1, 2, 48, 49, 50, 51, 99, 100, 101, 1_500_000, 250_000_000, 300_000_000],
        dtype=np.int64,
    )
    vec_std = _vec_sale_proceeds_unit(prices, DEFAULT_TAX, item_id=4151)
    ref_std = np.array([sale_proceeds(int(p), 1, DEFAULT_TAX, 4151) for p in prices])
    assert np.array_equal(vec_std, ref_std)

    exempt_pol = TaxPolicy(exempt_item_ids=(379,))
    vec_ex = _vec_sale_proceeds_unit(prices, exempt_pol, item_id=379)
    ref_ex = np.array([sale_proceeds(int(p), 1, exempt_pol, 379) for p in prices])
    assert np.array_equal(vec_ex, ref_ex)
    assert np.array_equal(vec_ex, prices)


def test_duckdb_5m_loader_enforces_holdout_pushdown_and_hash(tmp_path: Path):
    max_val_end = HOLDOUT_START - 300  # 1785024000
    raw = pd.DataFrame(
        [
            {
                "item_id": 4151,
                "name": "Whip",
                "ts": max_val_end - 600,
                "avg_high_price": 1500.0,
                "avg_low_price": 1490.0,
                "high_price_volume": 100,
                "low_price_volume": 100,
                "mid_price": 1495.0,
                "total_volume": 200,
            },
            {
                "item_id": 999999,
                "name": "Excluded",
                "ts": max_val_end - 600,
                "avg_high_price": 500.0,
                "avg_low_price": 490.0,
                "high_price_volume": 50,
                "low_price_volume": 50,
                "mid_price": 495.0,
                "total_volume": 100,
            },
            {
                "item_id": 4151,
                "name": "Whip",
                "ts": max_val_end,
                "avg_high_price": 1510.0,
                "avg_low_price": 1500.0,
                "high_price_volume": 100,
                "low_price_volume": 100,
                "mid_price": 1505.0,
                "total_volume": 200,
            },
            {
                "item_id": 4151,
                "name": "Whip",
                "ts": HOLDOUT_START,
                "avg_high_price": 1600.0,
                "avg_low_price": 1590.0,
                "high_price_volume": 100,
                "low_price_volume": 100,
                "mid_price": 1595.0,
                "total_volume": 200,
            },
        ]
    )
    pq_path = tmp_path / "mini_5m.parquet"
    raw.to_parquet(pq_path, index=False)
    sha = file_hash(pq_path)

    loaded = load_verified_5m_execution_bars(
        pq_path,
        [4151],
        min_ts=max_val_end - 3600,
        max_end_ts=max_val_end,
        expected_sha256=sha,
    )
    assert len(loaded) == 1
    assert int(loaded.iloc[0]["item_id"]) == 4151
    assert int(loaded.iloc[0]["ts"]) == max_val_end - 600
    assert (loaded["ts"] < max_val_end).all()
    assert (loaded["ts"] < HOLDOUT_START).all()

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_verified_5m_execution_bars(
            pq_path,
            [4151],
            min_ts=max_val_end - 3600,
            max_end_ts=max_val_end,
            expected_sha256="0" * 64,
        )

    with pytest.raises(ValueError, match="protected holdout"):
        load_verified_5m_execution_bars(
            pq_path,
            [4151],
            min_ts=max_val_end - 3600,
            max_end_ts=HOLDOUT_START + 300,
            expected_sha256=sha,
        )


def test_one_sided_bars_never_impute_mid_price_or_carry_volume():
    w_start = 1_760_000_400
    w_end = w_start + 3 * HOUR
    items_df = pd.DataFrame({"id": [100], "name": ["ItemA"], "buy_limit": [5000]})

    # Bar 0: both sides print. Bar 1: ask-only (mid_price=NaN). Bar 2: absent. Bar 3: bid-only.
    rows = [
        {
            "item_id": 100,
            "ts": w_start,
            "avg_high_price": 210.0,
            "avg_low_price": 200.0,
            "high_price_volume": 300,
            "low_price_volume": 300,
            "mid_price": 205.0,
        },
        {
            "item_id": 100,
            "ts": w_start + 300,
            "avg_high_price": 212.0,
            "avg_low_price": np.nan,
            "high_price_volume": 250,
            "low_price_volume": 0,
            "mid_price": np.nan,
        },
        {
            "item_id": 100,
            "ts": w_start + 900,
            "avg_high_price": np.nan,
            "avg_low_price": 202.0,
            "high_price_volume": 0,
            "low_price_volume": 400,
            "mid_price": np.nan,
        },
    ]
    obs = build_backtest_observations_300s(
        pd.DataFrame(rows),
        items_df,
        w_start,
        w_end,
        selected_item_ids=[100],
        delay_seconds=300,
        compact=False,
    )
    by_ts = obs.set_index("timestamp")

    # Bar 1 (ask-only): raw_mid_price remains NaN, low_price_volume is 0, bid carried with +300s age
    b1 = by_ts.loc[w_start + 300]
    assert pd.isna(b1["raw_mid_price"])
    assert int(b1["avg_high_price"]) == 212
    assert int(b1["avg_low_price"]) == 200
    assert int(b1["high_price_volume"]) == 250
    assert int(b1["low_price_volume"]) == 0
    assert int(b1["high_freshness_seconds"]) == 300
    assert int(b1["low_freshness_seconds"]) == 600

    # Bar 2 (absent at w_start + 600): both volumes 0, raw_mid_price NaN
    b2 = by_ts.loc[w_start + 600]
    assert pd.isna(b2["raw_mid_price"])
    assert int(b2["high_price_volume"]) == 0
    assert int(b2["low_price_volume"]) == 0
    assert int(b2["high_freshness_seconds"]) == 600
    assert int(b2["low_freshness_seconds"]) == 900


def test_compact_vs_dense_300s_grid_exact_simulation_and_analysis_equivalence():
    w_start = 1_761_696_000
    w_end = w_start + 12 * HOUR
    items_df = pd.DataFrame(
        {"id": [101, 102, 103], "name": ["A", "B", "C"], "buy_limit": [1000, 1000, 1000]}
    )

    rng = np.random.default_rng(77)
    rows = []
    for ts in range(w_start - 2 * HOUR, w_end, FIVE_MIN):
        for iid, base_px in ((101, 500.0), (102, 1200.0), (103, 3500.0)):
            # Deliberately drop ~55% of bars and make ~20% one-sided to stress sparse gaps.
            u = float(rng.random())
            if u < 0.40:
                continue
            ask = base_px + float(rng.integers(2, 12))
            bid = base_px - float(rng.integers(2, 10))
            if u < 0.55:
                rows.append(
                    {
                        "item_id": iid,
                        "ts": ts,
                        "avg_high_price": ask,
                        "avg_low_price": np.nan,
                        "high_price_volume": int(rng.integers(60, 400)),
                        "low_price_volume": 0,
                        "mid_price": np.nan,
                    }
                )
            elif u < 0.70:
                rows.append(
                    {
                        "item_id": iid,
                        "ts": ts,
                        "avg_high_price": np.nan,
                        "avg_low_price": bid,
                        "high_price_volume": 0,
                        "low_price_volume": int(rng.integers(60, 400)),
                        "mid_price": np.nan,
                    }
                )
            else:
                rows.append(
                    {
                        "item_id": iid,
                        "ts": ts,
                        "avg_high_price": ask,
                        "avg_low_price": bid,
                        "high_price_volume": int(rng.integers(60, 400)),
                        "low_price_volume": int(rng.integers(60, 400)),
                        "mid_price": 0.5 * (ask + bid),
                    }
                )
    frame_5m = pd.DataFrame(rows)

    scores = {
        (102, w_start + HOUR + 300): 2.5,
        (103, w_start + HOUR + 300): 1.8,
        (101, w_start + 2 * HOUR + 300): 3.1,
        (102, w_start + 6 * HOUR + 300): 2.0,
    }
    allocs = {k: 800 for k in scores}
    hquotes = {k: (1210, 1190) for k in scores}
    funnel = {"selected_signals": len(scores)}
    portfolio = make_portfolio_policy(4, initial_cash_gp=10_000_000)

    for delay_s in (300, 0):
        obs_compact = build_backtest_observations_300s(
            frame_5m,
            items_df,
            w_start,
            w_end,
            selected_item_ids=[101, 102, 103],
            delay_seconds=delay_s,
            compact=True,
        )
        obs_dense = build_backtest_observations_300s(
            frame_5m,
            items_df,
            w_start,
            w_end,
            selected_item_ids=[101, 102, 103],
            delay_seconds=delay_s,
            compact=False,
        )
        assert len(obs_compact) < len(obs_dense)

        for assump in (make_crossed_300s_assumptions(200), make_passive_v3_assumptions(200)):
            res_c = simulate(
                PreparedObservations(obs_compact),
                scores,
                assump,
                portfolio,
                DEFAULT_TAX,
                allocation_bps=allocs,
            )
            res_d = simulate(
                PreparedObservations(obs_dense),
                scores,
                assump,
                portfolio,
                DEFAULT_TAX,
                allocation_bps=allocs,
            )
            assert res_c.metrics == res_d.metrics
            assert res_c.fills == res_d.fills
            assert res_c.orders == res_d.orders
            assert res_c.equity == res_d.equity

            sum_c, inc_c, tr_c, _ = analyze_backtest_result_p1b(
                res_c,
                CausalObsIndex(obs_compact),
                hquotes,
                assumptions=assump,
                window_start=w_start,
                window_end=w_end,
                funnel=funnel,
            )
            sum_d, inc_d, tr_d, _ = analyze_backtest_result_p1b(
                res_d,
                CausalObsIndex(obs_dense),
                hquotes,
                assumptions=assump,
                window_start=w_start,
                window_end=w_end,
                funnel=funnel,
            )
            assert sum_c == sum_d
            assert np.allclose(inc_c, inc_d)
            assert tr_c == tr_d
            assert math.isclose(float(inc_c.sum()), float(res_c.metrics["net_gp"]), abs_tol=1e-6)


def test_300s_resolves_early_post_signal_fills_before_h2_rally_and_classifies_expiries():
    w_start = 1_761_696_000
    w_end = w_start + 10 * HOUR
    items_df = pd.DataFrame(
        {"id": [555, 556], "name": ["FastMove", "Low5mVol"], "buy_limit": [500, 500]}
    )

    # Signal arrives at sub_ts = w_start + 3900 (end of hour 0 + 300s).
    # Item 555: ask is 1000 in hour 0 and for first 25 mins of hour 1, then jumps to 1060 (+6%)
    # and stays at 1060 (bid 1052) through hour 9.
    # Item 556: ask stays 1000 everywhere, but each 5m bar has high_price_volume=10 (<50 at 200bps)
    # so 10*200//10_000 == 0 per 5m bar despite cumulative 220 units across 22 bars!
    rows_5m = []
    for ts in range(w_start, w_end, FIVE_MIN):
        rel = ts - w_start
        if rel < HOUR + 1500:
            ask_555, bid_555 = 1000.0, 996.0
        else:
            ask_555, bid_555 = 1060.0, 1052.0
        rows_5m.append(
            {
                "item_id": 555,
                "ts": ts,
                "avg_high_price": ask_555,
                "avg_low_price": bid_555,
                "high_price_volume": 500,
                "low_price_volume": 500,
                "mid_price": 0.5 * (ask_555 + bid_555),
            }
        )
        rows_5m.append(
            {
                "item_id": 556,
                "ts": ts,
                "avg_high_price": 1000.0,
                "avg_low_price": 996.0,
                "high_price_volume": 10,
                "low_price_volume": 10,
                "mid_price": 998.0,
            }
        )
    df_5m = pd.DataFrame(rows_5m)

    # Hourly aggregate of Item 555: hour 0 = 1000/996; hour 1 VWAP > 1030; hour 2+ = 1060/1052.
    rows_1h = []
    for h in range(10):
        ts_h = w_start + h * HOUR
        sub_h = df_5m[
            (df_5m["item_id"] == 555) & (df_5m["ts"] >= ts_h) & (df_5m["ts"] < ts_h + HOUR)
        ]
        ask_h = float(sub_h["avg_high_price"].mean())
        bid_h = float(sub_h["avg_low_price"].mean())
        rows_1h.append(
            {
                "ts": ts_h,
                "item_id": 555,
                "mid_price": 0.5 * (ask_h + bid_h),
                "avg_high_price": ask_h,
                "avg_low_price": bid_h,
                "high_price_volume": float(sub_h["high_price_volume"].sum()),
                "low_price_volume": float(sub_h["low_price_volume"].sum()),
                "available_at": ts_h + HOUR + 300,
                "usable": True,
            }
        )
    df_1h = pd.DataFrame(rows_1h)

    sub_ts = w_start + HOUR + 300
    scores = {(555, sub_ts): 3.0, (556, sub_ts): 2.0}
    allocs = {(555, sub_ts): 500, (556, sub_ts): 500}
    portfolio = make_portfolio_policy(4, initial_cash_gp=1_000_000)

    # Hourly (3600s) execution: Item 555 misses h=1 due to latency and expires unfilled at h=2!
    obs_1h = build_backtest_observations(df_1h, items_df, w_start, w_end)
    res_1h = simulate(
        PreparedObservations(obs_1h),
        {(555, sub_ts): 3.0},
        make_crossed_assumptions(200),
        portfolio,
        DEFAULT_TAX,
        allocation_bps={(555, sub_ts): 500},
    )
    assert res_1h.metrics["buy_units_filled"] == 0
    assert res_1h.metrics["net_gp"] == 0

    # 300s execution: Item 555 fills starting at sub_ts + 900s (before the +6% rally) and profits;
    # Item 556 expires unfilled and is classified under 5m integer-capacity quantization!
    obs_5m = build_backtest_observations_300s(
        df_5m, items_df, w_start, w_end, selected_item_ids=[555, 556], delay_seconds=300
    )
    assump_5m = make_crossed_300s_assumptions(200)
    res_5m = simulate(
        PreparedObservations(obs_5m),
        scores,
        assump_5m,
        portfolio,
        DEFAULT_TAX,
        allocation_bps=allocs,
    )
    assert res_5m.metrics["buy_units_filled"] > 0
    assert res_5m.metrics["net_gp"] > 0

    summary_5m, _, trades_5m, _ = analyze_backtest_result_p1b(
        res_5m,
        CausalObsIndex(obs_5m),
        {(555, sub_ts): (1000, 996), (556, sub_ts): (1000, 996)},
        assumptions=assump_5m,
        window_start=w_start,
        window_end=w_end,
        funnel={"selected_signals": 2},
    )
    assert len(trades_5m) == 1
    assert trades_5m[0]["item_id"] == 555
    assert trades_5m[0]["first_buy_wait_seconds"] == 900.0
    decomp = summary_5m["zero_fill_expiry_decomposition"]
    assert decomp["total_zero_fill_expiries"] == 1
    assert decomp["five_min_integer_capacity_floor_lt_1_despite_cum_ge_1"] == 1
