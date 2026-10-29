import json

import numpy as np
import pandas as pd
from osrs_ml.research import DAY, FEATURES, daily_features, forecasts


def daily():
    return pd.DataFrame(
        [
            dict(
                item_id=i,
                timestamp=t * DAY,
                available_at=(t + 1) * DAY + 300,
                avg_high_price=100 + t,
                avg_low_price=95 + t,
                high_price_volume=1000,
                low_price_volume=1000,
                inverted_spread=False,
            )
            for i in range(1, 4)
            for t in range(100)
        ]
    )


def test_daily_causality_exact_horizon_and_inversions():
    f = daily()
    before = daily_features(f)
    f.loc[f.timestamp > 50 * DAY, "avg_high_price"] = 999999
    after = daily_features(f)
    mask = before.timestamp <= 50 * DAY
    pd.testing.assert_frame_equal(before.loc[mask, FEATURES], after.loc[mask, FEATURES])
    valid = before.label_end.notna()
    assert (before.loc[valid].label_end - before.loc[valid].available_at).eq(DAY).all()
    f = daily().drop(index=[2])
    f.loc[0, "inverted_spread"] = True
    features = daily_features(f)
    assert pd.isna(features.iloc[0].target)
    assert pd.isna(features.iloc[1].target)  # missing next calendar bucket
    assert pd.isna(features.iloc[0].log_price)
    assert daily_features(daily(), labels=False).columns.isin(["target", "label_end"]).sum() == 0


def test_real_catboost_quantiles_and_literal_spread_baselines(tmp_path):
    f = daily_features(daily())
    start = 75 * DAY + 300
    train = f[(f.available_at < start) & (f.label_end < start)]
    validation = f[f.available_at >= start]
    p, errors = forecasts(
        train,
        validation,
        {"catboost": {"iterations": 5, "depth": 3, "thread_count": 2}, "seed": 42},
        tmp_path / "fit",
    )
    assert np.isfinite(p.catboost).all()
    assert errors["n"] > 0
    assert errors["pinball_0.1"] >= 0
    assert p.no_trade.eq(-np.inf).all()
    assert (p.spread_volume == p.raw_spread * 1000).all()
    assert len(list((tmp_path / "fit").glob("*.cbm"))) == 2
    info = json.loads((tmp_path / "fit" / "training.json").read_text())
    assert info["max_label_end"] < start
    assert "buy_limit" not in info["features"]
