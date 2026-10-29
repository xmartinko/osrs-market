import numpy as np
import pandas as pd
import pytest

from osrs_ml.data import load_snapshot
from osrs_ml.evaluation import split_fold, walk_forward_folds
from osrs_ml.features import FULL_FEATURES, build_features
from osrs_ml.fixture import write_fixture
from osrs_ml.models import predict


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    path = tmp_path_factory.mktemp("evaluation") / "fixture.parquet"
    write_fixture(path)
    return load_snapshot(path)


@pytest.mark.parametrize("horizon", [3600, 14400, 86400])
def test_timestamp_horizons_not_row_offsets(data, horizon):
    features = build_features(data, horizon)
    valid = features.label_end.notna()
    elapsed = features.loc[valid, "label_end"] - features.loc[valid, "available_at"]
    assert elapsed.ge(horizon).all()
    assert elapsed.le(horizon + 600).all()
    assert features.target_log_volume.notna().any()
    assert features.target_volatility.notna().any()


def test_purge_holdout_and_regime_separation(data):
    folds = walk_forward_folds(data)
    assert len(folds) == 4
    holdout = folds[0].holdout_start
    features = build_features(data[data.available_at < holdout], 14400)
    for fold in folds:
        train, validation = split_fold(features, fold)
        assert train.label_end.max() < fold.validation_start
        assert train.available_at.max() < fold.validation_start
        assert validation.available_at.max() < holdout
        assert train.regime.eq(fold.regime).all()
        assert validation.regime.eq(fold.regime).all()
        assert (
            validation.loc[validation.label_end >= fold.validation_end, "target_return"]
            .isna()
            .all()
        )


def test_features_do_not_change_when_future_changes(data):
    sample = data[data.item_id == 1].copy()
    cutoff = int(sample.available_at.iloc[100])
    before = build_features(sample, 3600)
    sample.loc[sample.available_at > cutoff, "avg_high_price"] = 999_999
    sample.loc[sample.available_at > cutoff, "high_price_volume"] = 999_999
    after = build_features(sample, 3600)
    pd.testing.assert_frame_equal(
        before.loc[before.available_at <= cutoff, FULL_FEATURES],
        after.loc[after.available_at <= cutoff, FULL_FEATURES],
    )


def test_actual_global_catboost_and_all_baselines(data, tmp_path):
    fold = walk_forward_folds(data)[0]
    features = build_features(data[data.available_at < fold.holdout_start], 3600)
    train, validation = split_fold(features, fold)
    # More than one item enters a single shared estimator.
    assert train.item.nunique() == 6
    forecasts = predict(train, validation, "full_feature", "catboost", 3600, tmp_path)
    assert np.isfinite(forecasts.predicted_return).all()
    assert len(list(tmp_path.glob("*.cbm"))) == 4
    for model in ["no_trade", "no_change", "spread_volume"]:
        baseline = predict(train, validation, "price_only", model, 3600)
        assert len(baseline) == len(validation)
    assert predict(train, validation, "price_only", "no_change", 3600).predicted_return.eq(0).all()
