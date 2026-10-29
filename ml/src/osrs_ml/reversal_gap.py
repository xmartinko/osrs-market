"""Frozen disjoint-endpoint reversal diagnostic; no account or profit inference."""

import argparse
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from . import reversal_fields as fields
from . import uncertainty, weekly_research
from .data import sha256
from .diagnostics import atomic_json
from .uncertainty import block_indices
from .weekly_ingest import WEEK, external_directory
from .weekly_research import correlation, epoch

CUTOFF = fields.CUTOFF
GAP, TESTS, FAMILY, DRAWS, SEED = 2, 28, 140, 20000, 42
KEYS = ['year', 'lookback_weeks', 'horizon_weeks']
SIDE_FIELDS = ('buyingPrice', 'sellingPrice', 'buyingCompleted', 'sellingCompleted')


def endpoints(panel, lookback, horizon):
    """One unused source bucket separates the signal and label baseline."""
    f = panel[['item_id', 'timestamp', 'available_at', *SIDE_FIELDS]].copy()
    fields.validate_dates(f[['item_id', 'timestamp', 'available_at']])
    values = f[list(SIDE_FIELDS)].to_numpy(dtype=float, na_value=np.nan)
    valid = np.isfinite(values).all(axis=1) & (values > 0).all(axis=1)
    f['mid'] = np.where(valid, (values[:, 0] + values[:, 1]) / 2, np.nan)
    observed = f.set_index(['item_id', 'timestamp'])['mid']

    def at(offset):
        return observed.reindex(pd.MultiIndex.from_arrays(
            [f.item_id, f.timestamp + offset * WEEK])).to_numpy()

    past, baseline, future = at(-lookback), at(GAP), at(GAP + horizon)
    current = f.mid.to_numpy()
    matched = np.isfinite(np.column_stack([past, current, baseline, future])).all(axis=1)
    result = f.loc[matched, ['item_id', 'timestamp', 'available_at']].copy()
    result['score'] = -(current[matched] / past[matched] - 1)
    result['label'] = future[matched] / baseline[matched] - 1
    result['label_start'] = result.timestamp + GAP * WEEK
    result['label_end'] = result.timestamp + (GAP + horizon + 1) * WEEK + 300
    return result


def era_grid(offset, year, horizon):
    start, end = epoch(year), min(epoch(year + 1), CUTOFF)
    first = ((start - WEEK - 300 - offset + WEEK - 1) // WEEK) * WEEK + offset
    return np.arange(first, end - (GAP + horizon + 1) * WEEK - 300, WEEK, dtype=np.int64)


def weekly_scores(paired, grid):
    groups = {int(t): g for t, g in paired[paired.timestamp.isin(grid)].groupby('timestamp')}
    rows = []
    for timestamp in grid:
        part = groups.get(int(timestamp))
        n = len(part) if part is not None else 0
        rho = correlation(part.score, part.label) if n >= 20 else np.nan
        rows.append(dict(timestamp=int(timestamp), items_count=n, rank_correlation=rho))
    return pd.DataFrame(rows)


def inference(values, indices):
    # The preceding field audit implements the identical frozen bootstrap/gates.
    # Recalculate its correction with the larger sequential family, without changing it.
    result = fields.inference(values, indices)
    adjusted = min(1., FAMILY * result['p_raw'])
    result.update(p_adj=adjusted, passed=bool(result['adequate'] and adjusted < .05 and
                                            result['lower'] > 0))
    return result


def summarize(scores):
    if scores.duplicated([*KEYS, 'timestamp']).any():
        raise ValueError('Duplicate hypothesis/week')
    expected = set(product(range(2020, 2027), (1, 4), (1, 4)))
    if set(scores[KEYS].itertuples(index=False, name=None)) != expected:
        raise ValueError('Incomplete registered 28-test family')
    offsets = scores.timestamp.mod(WEEK).unique()
    if len(offsets) != 1:
        raise ValueError('Inconsistent calendar offsets')
    blocks = []
    for (year, horizon), era in scores.groupby(['year', 'horizon_weeks'], sort=True):
        grid = era_grid(int(offsets[0]), int(year), int(horizon))
        for _lookback, part in era.groupby('lookback_weeks', sort=True):
            if not np.array_equal(np.sort(part.timestamp.to_numpy()), grid):
                raise ValueError('Incomplete calendar family')
        for block in (4, 8):
            indices = block_indices(len(grid), block, draws=DRAWS, seed=SEED)
            for lookback, part in era.groupby('lookback_weeks', sort=True):
                series = part.set_index('timestamp').reindex(grid)
                blocks.append(dict(year=int(year), horizon_weeks=int(horizon),
                    lookback_weeks=int(lookback), block_weeks=block,
                    min_items=int(series.items_count.min()),
                    median_items=float(series.items_count.median()),
                    **inference(series.rank_correlation.to_numpy(), indices)))
    block_table = pd.DataFrame(blocks)
    rows = []
    for identity, part in block_table.groupby(KEYS, sort=True):
        if set(part.block_weeks) != {4, 8} or len(part) != 2:
            raise ValueError('Incomplete block family')
        reference = part.iloc[0]
        rows.append(dict(zip(KEYS, identity, strict=True)) | dict(
            mean=reference['mean'], weeks=int(reference.weeks),
            calendar_weeks=int(reference.calendar_weeks), adequate=bool(part.adequate.all()),
            reason=reference.reason, lower=part.lower.min(), upper=part.upper.max(),
            p_raw=part.p_raw.max(), p_adj=part.p_adj.max(), passed=bool(part.passed.all()),
            min_items=int(reference.min_items), median_items=reference.median_items))
    return pd.DataFrame(rows), block_table


def run(source, output, acknowledged):
    output = external_directory(output, acknowledged)
    if any(output.iterdir()):
        raise FileExistsError('Use a new gap-audit output directory')
    repo = Path(__file__).resolve().parents[3]
    code_paths = [Path(__file__), Path(fields.__file__), Path(uncertainty.__file__),
                  Path(weekly_research.__file__)]
    manifest = dict(status='running', holdout_read=False, holdout_start=CUTOFF,
        protocol_sha256=sha256(repo / 'docs/reversal-gap-protocol.md'),
        code_sha256={p.name: sha256(p) for p in code_paths},
        source_manifest_sha256=sha256(source / 'run.json'), panel_sha256=fields.SEALED_HASH,
        new_tests=TESTS, family_size=FAMILY, prior_reserved_tests=112,
        baseline_offset_weeks=GAP, intervening_buckets=1,
        draws=DRAWS, seed=SEED, blocks_weeks=[4, 8],
        qualification='Disjoint-endpoint source-rank diagnostic; no profit or fill inference')
    atomic_json(output / 'run.json', manifest)
    panel, _ = fields.load_panel(source)
    manifest.update(source_rows=len(panel), max_available_at=int(panel.available_at.max()))
    offset = int(panel.timestamp.iloc[0]) % WEEK
    frames = []
    for lookback, horizon in product((1, 4), repeat=2):
        paired = endpoints(panel, lookback, horizon)
        for year in range(2020, 2027):
            grid = era_grid(offset, year, horizon)
            score = weekly_scores(paired, grid)
            score['year'], score['lookback_weeks'], score['horizon_weeks'] = year, lookback, horizon
            frames.append(score)
        print(f'Scored fixed gap: lookback={lookback}w horizon={horizon}w', flush=True)
    weekly = pd.concat(frames, ignore_index=True)
    summary, blocks = summarize(weekly)
    paths = ['weekly-scores.parquet', 'summary.csv', 'block-tests.csv']
    weekly.to_parquet(output / paths[0], index=False)
    summary.to_csv(output / paths[1], index=False)
    blocks.to_csv(output / paths[2], index=False)
    consistency = []
    for (lookback, horizon), part in summary.groupby(['lookback_weeks', 'horizon_weeks']):
        consistency.append(dict(lookback_weeks=int(lookback), horizon_weeks=int(horizon),
            passing_eras=int(part.passed.sum()), eras=len(part),
            all_era_persistence=bool(len(part) == 7 and part.passed.all())))
    manifest.update(status='complete', tests=len(summary), block_tests=len(blocks),
        weekly_score_rows=len(weekly), corrected_passes=int(summary.passed.sum()),
        consistency=consistency, output_sha256={p: sha256(output / p) for p in paths})
    atomic_json(output / 'run.json', manifest)
    print(summary.to_string(index=False), flush=True)
    print(f'COMPLETE: {len(summary)}/28 tests; {len(blocks)} block tests; '
          f'corrected diagnostic passes={summary.passed.sum()}; holdout NOT read', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--acknowledge-private-research', action='store_true')
    args = parser.parse_args()
    run(args.source, args.output, args.acknowledge_private_research)


if __name__ == '__main__':
    main()
