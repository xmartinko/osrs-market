"""Mechanics fixtures only: no fixture is research/training/profit evidence."""

import numpy as np
import pandas as pd
import pytest

from osrs_ml.weekly_ingest import WEEK
from osrs_ml.weekly_research import (
    FEATURES,
    RULES,
    features,
    fit_rank,
    labels,
    matrix,
    summarize_era,
    weekly_scores,
)


def observations():
    return pd.DataFrame([
        dict(item_id=item, timestamp=t * WEEK, available_at=(t + 1) * WEEK + 300,
             overallPrice=100 + t * item, buyingPrice=102 + t * item,
             sellingPrice=98 + t * item, buyingCompleted=100, sellingCompleted=200)
        for item in (1, 2, 3) for t in range(10)
    ])


def test_exact_lags_labels_gaps_and_causality():
    raw = observations()
    before = features(raw)
    modified = raw.copy()
    modified.loc[modified.timestamp > 5 * WEEK, "overallPrice"] = 99999
    after = features(modified)
    np.testing.assert_equal(matrix(before[before.timestamp <= 5 * WEEK]),
                            matrix(after[after.timestamp <= 5 * WEEK]))
    missing = raw.drop(raw[(raw.item_id == 1) & (raw.timestamp == WEEK)].index)
    gapped = labels(features(missing), 4).query("item_id == 1")
    assert gapped.iloc[0].target == pytest.approx(.04)  # exact week 4 exists
    assert pd.isna(gapped[gapped.timestamp == 4 * WEEK].iloc[0].volatility_4w)
    assert pd.isna(gapped[gapped.timestamp == 2 * WEEK].iloc[0].return_1w)
    assert gapped[gapped.timestamp == 4 * WEEK].iloc[0].return_4w == pytest.approx(.04)
    labeled = labels(before, 1)
    assert labeled.iloc[0].target == pytest.approx(.01)
    assert labeled.iloc[0].target_tax == pytest.approx(-.01)
    assert labeled.iloc[0].label_end == 2 * WEEK + 300
    assert labeled.groupby("item_id").tail(1).target.isna().all()


def test_date_translation_does_not_change_features_labels_or_rank_fit():
    raw = observations()
    shift = raw.copy()
    shift[["timestamp", "available_at"]] += 1193 * 86400 + 123
    a, b = labels(features(raw), 1), labels(features(shift), 1)
    np.testing.assert_equal(matrix(a), matrix(b))
    np.testing.assert_equal(a.target.to_numpy(), b.target.to_numpy())
    train_a, test_a = a[a.timestamp < 7 * WEEK], a[a.timestamp == 7 * WEEK]
    train_b, test_b = b.loc[train_a.index], b.loc[test_a.index]
    pred_a, model_a = fit_rank(train_a, test_a)
    pred_b, model_b = fit_rank(train_b, test_b)
    np.testing.assert_equal(pred_a, pred_b)
    assert model_a == model_b
    assert model_a["features"] == list(FEATURES)
    assert not set(FEATURES) & {"item_id", "timestamp", "available_at", "year", "history_rows"}
    with pytest.raises(ValueError, match="Duplicate"):
        features(pd.concat([raw, raw.iloc[:1]]))


def test_ties_and_missing_rule_eras_are_preserved_as_inconclusive():
    n = 30
    test = pd.DataFrame(dict(timestamp=[0] * n, target=np.arange(n) / 100,
                             target_tax=np.arange(n) / 100 - .02, return_1w=[0.] * n,
                             return_4w=[np.nan] * n, spread_fraction=[.01] * n,
                             log_volume=np.arange(n)))
    scored = weekly_scores(test, np.arange(n))
    tied = scored[scored.rule == "momentum_1w"].iloc[0]
    assert tied.top_items == n and tied.top_excess == 0
    result = pd.DataFrame(summarize_era(scored, 2020, 1, np.arange(25) * WEEK))
    assert set(result.rule) == set(RULES)
    assert not result.adequate.any()
    assert result[result.rule == "momentum_4w"].weeks.eq(0).all()
