import json

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from osrs_ml.uncertainty import (
    block_indices,
    daily_uncertainty,
    empirical_interval,
    first_positive,
    mean_interval,
    normality,
    threshold_summary,
)


def test_block_resampling_only_uses_real_indices_preserves_local_order_and_pairing():
    indices = block_indices(28, 7)
    assert indices.shape == (2000, 28)
    assert indices.min() == 0 and indices.max() == 27
    assert np.array_equal(indices, block_indices(28, 7))
    assert np.all(np.diff(indices.reshape(2000, 4, 7), axis=-1) % 28 == 1)
    values = np.column_stack([np.arange(28), -np.arange(28)])
    assert np.all(values[indices].sum(axis=1).sum(axis=1) == 0)
    with pytest.raises(ValueError):
        block_indices(0, 7)


def test_nonmonotone_threshold_has_infinity_mass_and_no_interpolation():
    totals = np.array([[0, 1, -2, 3], [0, -1, -2, -3], [0, -1, 2, -3]])
    shares = [0, 10, 500, 10000]
    values = first_positive(totals, shares, [False, True, True, True])
    np.testing.assert_equal(values, [10, np.inf, 500])
    summary = threshold_summary(values)
    assert summary["upper_infinite"] and summary["upper_bps"] is None
    assert summary["no_positive_sample_fraction"] == pytest.approx(1 / 3)
    assert empirical_interval(np.full(100, np.inf)).tolist() == [np.inf, np.inf]
    assert np.isinf(first_positive(totals[:1], shares, [False] * 4)[0])


def test_normality_gates_and_actual_gaussian_branch_without_generated_training_samples():
    assert normality([1] * 50)["reason"] == "insufficient_or_constant"
    assert not normality(range(10))["gaussian_eligible"]
    # Deterministic distribution quantiles are a unit fixture, never market evidence or training.
    values = stats.norm.ppf((np.arange(200) + .5) / 200)
    values = values[np.random.default_rng(42).permutation(200)]
    assert mean_interval(values)["method"].startswith("gaussian_mean")
    fat = np.r_[np.arange(99) / 1000, 100]
    result = mean_interval(fat)
    assert result["p_value"] < .05
    assert result["method"] == "empirical_circular_block_4"
    assert mean_interval([1])["method"] == "insufficient"
    assert not normality(np.arange(200))["gaussian_eligible"]


def test_daily_rejects_holdout_or_incomplete_source_before_opening_ledgers(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setenv("OSRS_DATA_DIR", str(tmp_path))
    (source / "run.json").write_text(json.dumps(dict(status="complete", completed_scenarios=810,
                                                   holdout_read=True, price_model="integer_lots_v2")))
    with pytest.raises(ValueError, match="corrected development"):
        daily_uncertainty(source, tmp_path / "output", True)


def test_strict_daily_features_invariant_to_date_translation_and_no_age_proxy():
    from osrs_ml.research import DAY, FEATURES, daily_features, matrix

    frame = pd.DataFrame([dict(item_id=2, timestamp=i * DAY, available_at=i * DAY + 300,
                               avg_high_price=100 + i, avg_low_price=98 + i,
                               high_price_volume=1000 + i, low_price_volume=500 + i,
                               inverted_spread=False) for i in range(40)])
    shifted = frame.copy()
    shifted[["timestamp", "available_at"]] += 1137 * DAY + 12345
    pd.testing.assert_frame_equal(matrix(daily_features(frame)), matrix(daily_features(shifted)))
    assert not set(FEATURES) & {"timestamp", "available_at", "regime", "history_rows", "year", "weekday"}
