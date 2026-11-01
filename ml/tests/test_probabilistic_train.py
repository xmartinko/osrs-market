import hashlib
import json
import math
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from osrs_ml.probabilistic_train import (
    CONTEXT,
    FEATURES,
    HOLDOUT_START,
    HORIZON,
    HOUR,
    PILOT_FEATURES,
    TRAIN_START,
    VALIDATION_END,
    VALIDATION_START,
    bounded_subset,
    configure_device,
    eligible_origin_diagnostics,
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
    assert contexts.shape == (2, CONTEXT, len(FEATURES))
    assert labels.shape == (2, HORIZON)
    assert items.tolist() == [0, 0]

    pilot_panel = prepare_arrays(frame, feature_set="pilot_v1")
    assert pilot_panel.windows(validation[:2])[0].shape == (2, CONTEXT, len(PILOT_FEATURES))


def test_bridged_return_freshness_and_inverted_side_preserve_jumps_causally():
    frame = fixture_panel()
    inv_ts = VALIDATION_START + 10 * HOUR
    inv_row = frame["ts"] == inv_ts
    # Inverted hour: high < low, marked unusable; next hour jumps 2x in price.
    frame.loc[inv_row, "avg_high_price"] = 95.0
    frame.loc[inv_row, "avg_low_price"] = 105.0
    frame.loc[inv_row, "usable"] = False
    frame.loc[frame["ts"] > inv_ts, ["mid_price", "avg_high_price", "avg_low_price"]] *= 2.0

    panel = prepare_arrays(frame)
    inv_idx = int(np.flatnonzero(panel.times == inv_ts)[0])
    resume_idx = inv_idx + 1

    # Contiguous 1h scaled_return is 0 on both unusable hour and first resumed hour,
    # whereas bridged_scaled_return (index 8) captures the exact 2-hour jump on resume!
    assert panel.features[0, inv_idx, 0] == 0.0
    assert panel.features[0, resume_idx, 0] == 0.0
    assert panel.features[0, resume_idx, 3] == 1.0  # missing_return
    expected_jump = math.log(panel.prices[0, resume_idx]) - math.log(panel.prices[0, inv_idx - 1])
    expected_bridged = (expected_jump - 2.0 * panel.center[0]) / (math.sqrt(2.0) * panel.scale[0])
    assert panel.features[0, resume_idx, 8] == pytest.approx(expected_bridged, rel=1e-5)

    # Freshness age (index 9) is log1p(1) during the 1-hour outage and resets to 0 on resume.
    assert panel.features[0, inv_idx, 9] == pytest.approx(math.log1p(1.0), rel=1e-5)
    assert panel.features[0, resume_idx, 9] == 0.0

    # Inverted side (index 10) is 1.0 and crossed spread (index 2) is negative (-10 / 100 = -0.1).
    assert panel.features[0, inv_idx, 10] == 1.0
    assert panel.features[0, inv_idx, 2] == pytest.approx(-0.1, rel=1e-5)


def test_validation_end_cutoff_and_cohort_diagnostics():
    # Cover validation_end boundary so origin = val_end - 25*HOUR (final target bucket val_end - HOUR,
    # available at val_end + 300 < val_end + 3900) is retained while val_end - 24*HOUR is purged.
    val_end_local = VALIDATION_START + 60 * HOUR
    times = np.arange(VALIDATION_START - 250 * HOUR, val_end_local + 30 * HOUR, HOUR)
    price = 100.0 * np.exp(0.001 * np.sin(np.arange(len(times))))
    frame = pd.DataFrame(
        {
            "ts": times,
            "item_id": 42,
            "mid_price": price,
            "avg_high_price": price * 1.001,
            "avg_low_price": price * 0.999,
            "high_price_volume": 100,
            "low_price_volume": 100,
            "available_at": times + HOUR + 300,
            "usable": True,
        }
    )
    panel = prepare_arrays(frame)
    _, val = eligible_origins(
        panel, validation_start=VALIDATION_START, validation_end=val_end_local
    )
    last_val_ts = int(panel.times[val[-1, 1]])
    assert last_val_ts == val_end_local - (HORIZON + 1) * HOUR
    diag = eligible_origin_diagnostics(
        panel, validation_start=VALIDATION_START, validation_end=val_end_local
    )
    assert diag["validation_complete_24h_pairs"] == len(val)
    assert diag["validation_complete_24h_survival_vs_candidates"] == pytest.approx(1.0)
    assert VALIDATION_END > VALIDATION_START


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


def test_bare_cuda_resolves_current_index_before_memory_apis():
    # PyTorch memory APIs require an explicit device index even when model.to
    # accepts bare "cuda". Use a nonzero current GPU to catch hard-coded cuda:0.
    def device_factory(value, index=None):
        parts = value.split(":")
        return SimpleNamespace(type=parts[0], index=(int(parts[1]) if len(parts) == 2 else index))

    observed = []

    def memory_fraction(fraction, device):
        assert device.index is not None
        observed.append((fraction, device.index))

    def peak_reset(device):
        assert device.index is not None

    cuda = SimpleNamespace(
        is_available=lambda: True,
        current_device=Mock(return_value=2),
        set_per_process_memory_fraction=memory_fraction,
        reset_peak_memory_stats=peak_reset,
    )
    torch = SimpleNamespace(device=device_factory, cuda=cuda)
    assert configure_device(torch, "cuda").index == 2
    assert configure_device(torch, "cuda:1").index == 1
    assert observed == [(0.75, 2), (0.75, 1)]
    cuda.current_device.assert_called_once()
    assert configure_device(torch, "cpu").type == "cpu"
    assert len(observed) == 2
    cuda.is_available = lambda: False
    with pytest.raises(ValueError, match="no silent CPU fallback"):
        configure_device(torch, "cuda")
