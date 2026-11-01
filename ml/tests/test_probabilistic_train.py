import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from osrs_ml.probabilistic_train import (
    CONTEXT,
    HOLDOUT_START,
    HORIZON,
    HOUR,
    TRAIN_START,
    VALIDATION_START,
    bounded_subset,
    eligible_origins,
    load_verified_panel,
    prepare_arrays,
)


def fixture_panel():
    times = np.arange(VALIDATION_START - 500 * HOUR, VALIDATION_START + 100 * HOUR, HOUR)
    changes = 0.002 * np.sin(np.arange(len(times)) / 3) + 0.0001
    price = 100 * np.exp(np.cumsum(changes))
    return pd.DataFrame(
        {
            "ts": times,
            "item_id": 42,
            "mid_price": price,
            "avg_high_price": price * 1.001,
            "avg_low_price": price * 0.999,
            "high_price_volume": 200 + np.arange(len(times)) % 24,
            "low_price_volume": 100,
            "available_at": times + HOUR + 300,
            "usable": True,
        }
    )


def test_future_perturbations_cannot_change_fitted_statistics_or_prior_context():
    original = fixture_panel()
    altered = original.copy()
    future = altered.ts >= VALIDATION_START
    altered.loc[future, ["mid_price", "avg_high_price", "avg_low_price"]] *= 1000
    altered.loc[future, ["high_price_volume", "low_price_volume"]] *= 1_000_000
    first, second = prepare_arrays(original), prepare_arrays(altered)
    for attribute in ("center", "scale", "rw_scale", "volume_center", "volume_scale"):
        np.testing.assert_array_equal(getattr(first, attribute), getattr(second, attribute))
    historical = first.times < VALIDATION_START
    np.testing.assert_array_equal(first.features[:, historical], second.features[:, historical])
    train_first, _ = eligible_origins(first)
    train_second, _ = eligible_origins(second)
    np.testing.assert_array_equal(train_first, train_second)
    np.testing.assert_array_equal(
        first.windows(train_first[:3])[0], second.windows(train_second[:3])[0]
    )


def test_purge_removes_overlapping_labels_and_missing_prices_break_returns():
    frame = fixture_panel()
    # Missing bucket, not a zero price and not a carry-forward observation.
    gap_timestamp = VALIDATION_START + 30 * HOUR
    frame = frame[frame.ts != gap_timestamp]
    panel = prepare_arrays(frame)
    gap = int(np.flatnonzero(panel.times == gap_timestamp)[0])
    assert np.isnan(panel.returns[0, gap : gap + 2]).all()
    assert panel.features[0, gap, 5] == 1
    assert panel.features[0, gap, 0] == 0
    train, validation = eligible_origins(panel)
    assert len(train) and len(validation)
    first_decision = VALIDATION_START + HOUR + 300
    assert np.all(panel.times[train[:, 1] + HORIZON] + HOUR + 300 < first_decision)
    assert not np.any(panel.times[train[:, 1] + HORIZON] >= VALIDATION_START)
    for _, origin in np.vstack([train, validation]):
        assert panel.returns[0, origin + 1 : origin + HORIZON + 1].shape == (HORIZON,)
        assert np.isfinite(panel.returns[0, origin + 1 : origin + HORIZON + 1]).all()
    assert not any(origin < gap <= origin + HORIZON for _, origin in validation)
    contexts, labels, items = panel.windows(validation[:2])
    assert contexts.shape == (2, CONTEXT, 8)
    assert labels.shape == (2, HORIZON)
    assert items.tolist() == [0, 0]


def test_payload_hash_checked_before_parquet_parse(tmp_path, monkeypatch):
    path = tmp_path / "panel.parquet"
    path.write_bytes(b"deliberately not valid parquet")
    manifest = {
        "holdout_start": HOLDOUT_START,
        "selection_end_exclusive": VALIDATION_START,
        "start": TRAIN_START,
        "end_exclusive": HOLDOUT_START - 300,
        "quality": {"max_ts": HOLDOUT_START - 3600},
        "availability_delay_seconds": 300,
        "gates": {"development_only": True},
        "sha256": hashlib.sha256(b"different payload").hexdigest(),
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest))

    def forbidden_parser(*args, **kwargs):
        pytest.fail("Parquet parser called before payload verification")

    monkeypatch.setattr(pd, "read_parquet", forbidden_parser)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_verified_panel(path)
    manifest["quality"]["max_ts"] = HOLDOUT_START
    manifest["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="holdout gate"):
        load_verified_panel(path)


def test_bounded_subsets_are_deterministic_unique_and_do_not_change_values():
    origins = np.column_stack([np.arange(100) % 3, np.arange(100)])
    first, second = bounded_subset(origins, 20, 11), bounded_subset(origins, 20, 11)
    np.testing.assert_array_equal(first, second)
    assert len(first) == len(np.unique(first[:, 1])) == 20
    assert set(map(tuple, first)) <= set(map(tuple, origins))
