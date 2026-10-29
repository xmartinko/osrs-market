"""Accounting-sized fixtures test mechanics only; never used as market evidence."""

import json

import numpy as np
import pandas as pd
import pytest

from osrs_ml import reversal_fields as audit
from osrs_ml.data import sha256
from osrs_ml.uncertainty import block_indices
from osrs_ml.weekly_ingest import WEEK
from osrs_ml.weekly_research import epoch


def observations():
    return pd.DataFrame([
        dict(item_id=i, timestamp=epoch(2020) + t * WEEK,
             available_at=epoch(2020) + (t + 1) * WEEK + 300,
             overallPrice=100 + i * (t + 1), buyingPrice=202 + i * (t + 2),
             sellingPrice=198 + i * (t + 2), buyingCompleted=100, sellingCompleted=200)
        for i in range(1, 31) for t in range(15)
    ])


def test_exact_endpoint_fields_and_same_sample_without_outlier_removal():
    raw = observations()
    t = epoch(2020) + 4 * WEEK
    # One absent lag, one invalid future: neither item may enter any of the four cells.
    raw = raw[~((raw.item_id == 1) & (raw.timestamp == t - WEEK))].copy()
    raw.loc[(raw.item_id == 2) & (raw.timestamp == t + WEEK), 'sellingCompleted'] = 0
    # Positive but inconsistent overall and inverted sides must remain in the sample.
    raw.loc[(raw.item_id == 3) & (raw.timestamp == t), 'overallPrice'] = 1
    raw.loc[(raw.item_id == 3) & (raw.timestamp == t), 'sellingPrice'] = 1000
    paired = audit.endpoints(raw, 1, 1)
    part = paired[paired.timestamp == t].set_index('item_id')
    assert set(part.index) == set(range(3, 31))
    row = part.loc[4]
    assert row.score_O == pytest.approx(-(120 / 116 - 1))
    assert row.score_M == pytest.approx(-(224 / 220 - 1))
    assert row.label_O == pytest.approx(124 / 120 - 1)
    assert row.label_M == pytest.approx(228 / 224 - 1)
    assert row.label_end == t + 2 * WEEK + 300
    scores = audit.weekly_scores(paired, np.array([t]))
    assert len(scores) == 4 and scores.items_count.eq(28).all()
    assert set(zip(scores.signal_field, scores.label_field, strict=True)) == set(audit.CELLS)


def test_future_changes_never_change_past_scores_and_four_week_lag_is_exact():
    raw = observations()
    t = epoch(2020) + 5 * WEEK
    modified = raw.copy()
    modified.loc[modified.timestamp > t, 'overallPrice'] *= 13
    a, b = audit.endpoints(raw, 4, 4), audit.endpoints(modified, 4, 4)
    np.testing.assert_equal(a.loc[a.timestamp <= t, ['score_O', 'score_M']].to_numpy(),
                            b.loc[b.timestamp <= t, ['score_O', 'score_M']].to_numpy())
    missing = raw[~((raw.item_id == 1) & (raw.timestamp == t - 4 * WEEK))]
    result = audit.endpoints(missing, 4, 4)
    assert result[(result.item_id == 1) & (result.timestamp == t)].empty


@pytest.mark.parametrize('year', range(2020, 2027))
@pytest.mark.parametrize('horizon', [1, 4])
def test_era_grid_obeys_strict_label_boundary_and_inclusive_decision_start(year, horizon):
    offset = epoch(2020) % WEEK
    grid = audit.era_grid(offset, year, horizon)
    start, end = epoch(year), min(epoch(year + 1), audit.CUTOFF)
    assert np.all(np.diff(grid) == WEEK)
    assert grid[0] + WEEK + 300 >= start
    assert grid[0] - WEEK + WEEK + 300 < start
    assert grid[-1] + (horizon + 1) * WEEK + 300 < end
    assert grid[-1] + WEEK + (horizon + 1) * WEEK + 300 >= end


def test_bootstrap_centering_correction_and_shared_timestamps():
    x = np.array([.02, .09, .11, -.03, .06, .05] * 6)
    indices = block_indices(len(x), 4, draws=20000, seed=42)
    result = audit.inference(x, indices)
    means = x[indices].mean(axis=1)
    expected = (1 + np.count_nonzero(means - x.mean() >= x.mean())) / 20001
    assert result['p_raw'] == expected
    assert result['p_adj'] == min(1, audit.FAMILY * expected)
    assert result['lower'] == np.quantile(means, .025, method='inverted_cdf')
    negative = audit.inference(-x, indices)
    assert negative['p_raw'] > .5 and not negative['passed']


@pytest.mark.parametrize('x,reason', [
    (np.arange(23) / 100, 'insufficient_weeks'),
    (np.array([.1] * 24), 'constant_weekly_series'),
    (np.array([.01, .02, np.nan] * 10), 'missing_calendar_weeks'),
])
def test_missing_inadequate_or_constant_series_cannot_pass(x, reason):
    result = audit.inference(x, block_indices(len(x), 4, draws=20000))
    assert result['reason'] == reason
    assert result['p_raw'] == result['p_adj'] == 1 and not result['passed']


def test_missing_week_and_constant_cross_section_remain_visible():
    raw = observations()
    raw.overallPrice = 100
    paired = audit.endpoints(raw, 1, 1)
    scores = audit.weekly_scores(paired, np.array([epoch(2020), epoch(2020) + WEEK]))
    assert len(scores) == 8
    assert scores[scores.timestamp == epoch(2020)].items_count.eq(0).all()
    assert scores[scores.signal_field == 'O'].rank_correlation.isna().all()


def make_source(tmp_path, monkeypatch, raw):
    path = tmp_path / 'source'
    path.mkdir()
    raw.to_parquet(path / 'weekly.parquet', index=False)
    digest = sha256(path / 'weekly.parquet')
    monkeypatch.setattr(audit, 'SEALED_HASH', digest)
    (path / 'run.json').write_text(json.dumps(dict(status='complete', holdout_read=False,
        holdout_start=audit.CUTOFF, panel_sha256=digest)))
    return path


def test_source_provenance_rejected_before_market_materialization(tmp_path, monkeypatch):
    path = make_source(tmp_path, monkeypatch, observations())
    monkeypatch.setattr(audit, 'SEALED_HASH', 'wrong')
    monkeypatch.setattr(audit.duckdb, 'connect', lambda *a, **k: pytest.fail('read before hash'))
    with pytest.raises(ValueError, match='checksum'):
        audit.load_panel(path)


@pytest.mark.parametrize('defect', ['holdout', 'misdated', 'duplicate', 'grid', 'fractional'])
def test_dates_fail_closed_before_market_query(tmp_path, monkeypatch, defect):
    raw = observations()
    if defect == 'holdout':
        raw.loc[0, 'timestamp'] = audit.CUTOFF
        raw.loc[0, 'available_at'] = audit.CUTOFF + WEEK + 300
    elif defect == 'misdated':
        raw.loc[0, 'available_at'] += 1
    elif defect == 'duplicate':
        raw = pd.concat([raw, raw.iloc[:1]])
    elif defect == 'fractional':
        raw['timestamp'] = raw.timestamp.astype(float)
        raw.loc[0, 'timestamp'] += .5
    else:
        raw.loc[0, ['timestamp', 'available_at']] += 1
    path = make_source(tmp_path, monkeypatch, raw)
    with pytest.raises(ValueError, match='dates|Duplicate|grid|integer'):
        audit.load_panel(path)


def test_valid_sealed_projection(tmp_path, monkeypatch):
    raw = observations()
    path = make_source(tmp_path, monkeypatch, raw)
    panel, manifest = audit.load_panel(path)
    pd.testing.assert_frame_equal(panel, raw)
    assert manifest['holdout_read'] is False


def test_full_family_preserved_and_worse_block_selected(monkeypatch):
    # Fewer resamples keep this bookkeeping test small; production draws stay frozen.
    monkeypatch.setattr(audit, 'DRAWS', 499)
    frames = []
    for year in range(2020, 2027):
        for horizon in (1, 4):
            grid = audit.era_grid(epoch(2020) % WEEK, year, horizon)
            for lookback in (1, 4):
                for signal, label in audit.CELLS:
                    frames.append(pd.DataFrame(dict(year=year, horizon_weeks=horizon,
                        lookback_weeks=lookback, signal_field=signal, label_field=label,
                        timestamp=grid, rank_correlation=.01 + .1 * np.sin(np.arange(len(grid))),
                        items_count=30, lag_rank_agreement=.3)))
    scores = pd.concat(frames, ignore_index=True)
    summary, blocks = audit.summarize(scores)
    assert len(summary) == 112 and len(blocks) == 224
    assert summary.adequate.all() and not summary.passed.any()
    for _, row in summary.iterrows():
        part = blocks
        for key in audit.KEYS:
            part = part[part[key] == row[key]]
        assert row.p_raw == part.p_raw.max()
        assert row.p_adj == min(1, 112 * row.p_raw)
        assert row.passed == part.passed.all()
    incomplete = scores[~((scores.year == 2020) & (scores.lookback_weeks == 1) &
                         (scores.horizon_weeks == 1) & (scores.signal_field == 'O') &
                         (scores.label_field == 'O'))]
    with pytest.raises(ValueError, match='112-test family'):
        audit.summarize(incomplete)


def test_output_overwrite_refused_without_source_read(tmp_path, monkeypatch):
    monkeypatch.setenv('OSRS_DATA_DIR', str(tmp_path))
    output = tmp_path / 'existing'
    output.mkdir()
    (output / 'run.json').write_text('{}')
    monkeypatch.setattr(audit, 'load_panel', lambda *a: pytest.fail('source read on overwrite'))
    with pytest.raises(FileExistsError, match='new field-audit'):
        audit.run(tmp_path / 'missing-source', output, True)
