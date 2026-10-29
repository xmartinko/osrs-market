"""Small deterministic mechanics fixtures, never research observations."""

from itertools import product

import numpy as np
import pandas as pd
import pytest

from osrs_ml import reversal_gap as gap
from osrs_ml.uncertainty import block_indices
from osrs_ml.weekly_ingest import WEEK
from osrs_ml.weekly_research import epoch


def observations():
    return pd.DataFrame([
        dict(item_id=i, timestamp=epoch(2020) + t * WEEK,
             available_at=epoch(2020) + (t + 1) * WEEK + 300,
             overallPrice=np.nan, buyingPrice=202 + i * (t + 2),
             sellingPrice=198 + i * (t + 2), buyingCompleted=100, sellingCompleted=200)
        for i in range(1, 31) for t in range(20)
    ])


def test_gap_endpoints_exact_and_intervening_bucket_unused():
    raw = observations()
    t = epoch(2020) + 5 * WEEK
    base = gap.endpoints(raw, 4, 4)
    row = base[(base.timestamp == t) & (base.item_id == 4)].iloc[0]
    assert row.score == pytest.approx(-(228 / 212 - 1))
    assert row.label == pytest.approx(252 / 236 - 1)
    assert row.label_start == t + 2 * WEEK
    assert row.label_end == t + 7 * WEEK + 300
    changed = raw[raw.timestamp != t + WEEK].copy()
    # Even a missing intervening bucket cannot alter this signal or label.
    same = gap.endpoints(changed, 4, 4)
    pd.testing.assert_frame_equal(base[base.timestamp == t].reset_index(drop=True),
                                  same[same.timestamp == t].reset_index(drop=True))
    for endpoint in (t - 4 * WEEK, t, t + 2 * WEEK, t + 6 * WEEK):
        missing = raw[~((raw.item_id == 4) & (raw.timestamp == endpoint))]
        paired = gap.endpoints(missing, 4, 4)
        assert paired[(paired.item_id == 4) & (paired.timestamp == t)].empty


def test_label_baseline_independent_from_signal_and_validity_uses_side_fields_only():
    raw = observations()
    t = epoch(2020) + 5 * WEEK
    changed = raw.copy()
    changed.loc[changed.timestamp == t, ['buyingPrice', 'sellingPrice']] *= 3
    a, b = gap.endpoints(raw, 1, 1), gap.endpoints(changed, 1, 1)
    np.testing.assert_equal(a.loc[a.timestamp == t, 'label'].to_numpy(),
                            b.loc[b.timestamp == t, 'label'].to_numpy())
    assert not np.array_equal(a.loc[a.timestamp == t, 'score'].to_numpy(),
                               b.loc[b.timestamp == t, 'score'].to_numpy())
    changed = raw.copy()
    changed.loc[changed.timestamp > t, ['buyingPrice', 'sellingPrice']] *= 7
    c = gap.endpoints(changed, 1, 1)
    np.testing.assert_equal(a.loc[a.timestamp == t, 'score'].to_numpy(),
                            c.loc[c.timestamp == t, 'score'].to_numpy())
    # Invalid overallPrice is deliberately irrelevant; positive inverted sides remain.
    raw.loc[(raw.timestamp == t) & (raw.item_id == 1), 'sellingPrice'] = 1000
    raw.loc[(raw.timestamp == t + 2 * WEEK) & (raw.item_id == 2), 'buyingCompleted'] = 0
    raw['sellingPrice'] = raw.sellingPrice.astype(float)
    raw.loc[(raw.timestamp == t + 3 * WEEK) & (raw.item_id == 3), 'sellingPrice'] = np.inf
    result = gap.endpoints(raw, 1, 1)
    assert set(result.loc[result.timestamp == t, 'item_id']) == {1, *range(4, 31)}


@pytest.mark.parametrize('year,horizon', list(product(range(2020, 2027), (1, 4))))
def test_grid_purges_full_delayed_label_and_includes_decision_start(year, horizon):
    grid = gap.era_grid(epoch(2020) % WEEK, year, horizon)
    start, end = epoch(year), min(epoch(year + 1), gap.CUTOFF)
    assert np.all(np.diff(grid) == WEEK)
    assert grid[0] + WEEK + 300 >= start
    assert grid[0] + 300 < start
    assert grid[-1] + (horizon + 3) * WEEK + 300 < end
    assert grid[-1] + (horizon + 4) * WEEK + 300 >= end
    assert len(grid) >= 23  # Calendar offsets can make development-2026 inadequate.


def test_weekly_coverage_and_constant_cross_sections_retained():
    raw = observations()
    paired = gap.endpoints(raw, 1, 1)
    t = epoch(2020) + 3 * WEEK
    paired.loc[paired.timestamp == t, 'score'] = 0
    paired = paired[~((paired.timestamp == t + WEEK) & (paired.item_id > 19))]
    scores = gap.weekly_scores(paired, np.array([epoch(2020), t, t + WEEK, t + 2 * WEEK]))
    assert list(scores.items_count) == [0, 30, 19, 30]
    assert scores.rank_correlation.iloc[:3].isna().all()
    assert np.isfinite(scores.rank_correlation.iloc[3])


def test_inference_uses_sequential_family_and_centered_empirical_blocks():
    x = np.array([.01, .12, .1, -.02, .03, .05] * 6)
    indices = block_indices(len(x), 8, draws=20000, seed=42)
    result = gap.inference(x, indices)
    means = x[indices].mean(axis=1)
    p = (1 + np.count_nonzero(means - x.mean() >= x.mean())) / 20001
    assert result['p_raw'] == p
    assert result['p_adj'] == min(1, 140 * p)
    assert result['lower'] == np.quantile(means, .025, method='inverted_cdf')
    assert result['passed'] == (140 * p < .05 and result['lower'] > 0)
    assert not gap.inference(-x, indices)['passed']


@pytest.mark.parametrize('x,reason', [
    (np.arange(23) / 100, 'insufficient_weeks'),
    (np.array([.1] * 24), 'constant_weekly_series'),
    (np.array([.01, .02, np.nan] * 10), 'missing_calendar_weeks'),
])
def test_inadequate_series_stays_in_family(x, reason):
    result = gap.inference(x, block_indices(len(x), 4, draws=499))
    assert result['reason'] == reason
    assert result['p_raw'] == result['p_adj'] == 1 and not result['passed']


def test_complete_family_worse_block_and_missing_or_duplicate_row_rejected(monkeypatch):
    monkeypatch.setattr(gap, 'DRAWS', 499)
    frames = []
    for year, horizon, lookback in product(range(2020, 2027), (1, 4), (1, 4)):
        grid = gap.era_grid(epoch(2020) % WEEK, year, horizon)
        frames.append(pd.DataFrame(dict(year=year, horizon_weeks=horizon,
            lookback_weeks=lookback, timestamp=grid,
            rank_correlation=.01 + .1 * np.sin(np.arange(len(grid))), items_count=30)))
    scores = pd.concat(frames, ignore_index=True)
    summary, blocks = gap.summarize(scores)
    assert len(summary) == 28 and len(blocks) == 56
    assert summary.adequate.eq(summary.calendar_weeks >= 24).all()
    for _, row in summary.iterrows():
        part = blocks
        for key in gap.KEYS:
            part = part[part[key] == row[key]]
        assert row.p_raw == part.p_raw.max()
        assert row.p_adj == min(1, 140 * row.p_raw)
        assert row.passed == part.passed.all()
    with pytest.raises(ValueError, match='calendar|family'):
        gap.summarize(scores.iloc[1:])
    with pytest.raises(ValueError, match='Duplicate'):
        gap.summarize(pd.concat([scores, scores.iloc[:1]]))
    with pytest.raises(ValueError, match='family'):
        gap.summarize(scores[~((scores.year == 2020) & (scores.lookback_weeks == 1) &
                             (scores.horizon_weeks == 1))])


def test_overwrite_refused_before_source_read(tmp_path, monkeypatch):
    monkeypatch.setenv('OSRS_DATA_DIR', str(tmp_path))
    out = tmp_path / 'existing'
    out.mkdir()
    (out / 'run.json').write_text('{}')
    monkeypatch.setattr(gap.fields, 'load_panel', lambda *a: pytest.fail('source opened'))
    with pytest.raises(FileExistsError, match='new gap'):
        gap.run(tmp_path / 'source', out, True)


def test_interrupted_attempt_is_reserved_and_cannot_be_overwritten(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv('OSRS_DATA_DIR', str(tmp_path))
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'run.json').write_text('{}')
    out = tmp_path / 'attempt'

    def fail_load(*args):
        assert (out / 'run.json').exists()
        raise ValueError('invalid source')

    monkeypatch.setattr(gap.fields, 'load_panel', fail_load)
    with pytest.raises(ValueError, match='invalid source'):
        gap.run(source, out, True)
    manifest = json.loads((out / 'run.json').read_text())
    assert manifest['status'] == 'running'
    assert manifest['holdout_read'] is False
    assert manifest['new_tests'] == 28 and manifest['family_size'] == 140
    assert manifest['baseline_offset_weeks'] == 2
    with pytest.raises(FileExistsError, match='new gap'):
        gap.run(source, out, True)
