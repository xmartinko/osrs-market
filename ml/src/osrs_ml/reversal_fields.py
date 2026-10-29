"""Preregistered matched-field weekly reversal diagnostic; no profit or fill claims."""

import argparse
import json
from itertools import product
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import uncertainty, weekly_research
from .data import sha256
from .diagnostics import atomic_json
from .uncertainty import block_indices, empirical_interval
from .weekly_ingest import WEEK, external_directory
from .weekly_research import correlation, epoch

CUTOFF = 1785024300
SEALED_HASH = '36b861ec5d7baa636a1eb70e9dea3fcbb73dd151ec603e6c9659feea91ea5208'
FAMILY, DRAWS, SEED = 112, 20000, 42
CELLS = tuple(product(('O', 'M'), repeat=2))
FIELDS = ('overallPrice', 'buyingPrice', 'sellingPrice', 'buyingCompleted', 'sellingCompleted')
KEYS = ['year', 'lookback_weeks', 'horizon_weeks', 'signal_field', 'label_field']


def validate_dates(dates):
    if dates.empty:
        raise ValueError('No development dates')
    for col in ('item_id', 'timestamp', 'available_at'):
        x = dates[col].to_numpy(dtype=float, na_value=np.nan)
        if not (np.isfinite(x) & (x == np.floor(x))).all():
            raise ValueError('Noninteger identifiers or dates')
    if not ((dates.available_at < CUTOFF) &
            (dates.available_at == dates.timestamp + WEEK + 300)).all():
        raise ValueError('Sealed or misdated dates')
    if dates.duplicated(['item_id', 'timestamp']).any():
        raise ValueError('Duplicate item/week')
    if dates.timestamp.mod(WEEK).nunique() != 1:
        raise ValueError('Inconsistent weekly grid')


def load_panel(source):
    """Verify bytes then dates before any market column is materialized."""
    manifest = json.loads((source / 'run.json').read_text())
    if (manifest['status'] != 'complete' or manifest['holdout_read'] is not False or
            manifest['holdout_start'] != CUTOFF):
        raise ValueError('Require complete sealed development archive')
    path = source / 'weekly.parquet'
    if manifest['panel_sha256'] != SEALED_HASH or sha256(path) != SEALED_HASH:
        raise ValueError('Sealed panel checksum mismatch')
    with duckdb.connect(':memory:') as con:
        dates = con.execute(
            'SELECT item_id, timestamp, available_at FROM read_parquet(?)', [str(path)]).df()
        validate_dates(dates)
        del dates
        panel = con.execute(
            'SELECT item_id, timestamp, available_at, ' + ', '.join(FIELDS) +
            ' FROM read_parquet(?) WHERE available_at < ?', [str(path), CUTOFF]).df()
    return panel, manifest


def endpoints(panel, lookback, horizon):
    """All four field cells share exactly the same valid endpoint observations."""
    f = panel[['item_id', 'timestamp', 'available_at', *FIELDS]].copy()
    validate_dates(f[['item_id', 'timestamp', 'available_at']])
    values = f[list(FIELDS)].to_numpy(dtype=float, na_value=np.nan)
    valid = np.isfinite(values).all(axis=1) & (values > 0).all(axis=1)
    f['O'] = np.where(valid, values[:, 0], np.nan)
    f['M'] = np.where(valid, (values[:, 1] + values[:, 2]) / 2, np.nan)
    observed = f.set_index(['item_id', 'timestamp'])[['O', 'M']]
    past = observed.reindex(pd.MultiIndex.from_arrays(
        [f.item_id, f.timestamp - lookback * WEEK])).to_numpy()
    future = observed.reindex(pd.MultiIndex.from_arrays(
        [f.item_id, f.timestamp + horizon * WEEK])).to_numpy()
    current = f[['O', 'M']].to_numpy()
    matched = (np.isfinite(past).all(axis=1) & np.isfinite(future).all(axis=1) &
               np.isfinite(current).all(axis=1))
    result = f.loc[matched, ['item_id', 'timestamp', 'available_at']].copy()
    for j, field in enumerate(('O', 'M')):
        result[f'score_{field}'] = -(current[matched, j] / past[matched, j] - 1)
        result[f'label_{field}'] = future[matched, j] / current[matched, j] - 1
    result['label_end'] = result.timestamp + (horizon + 1) * WEEK + 300
    return result


def era_grid(offset, year, horizon):
    start, end = epoch(year), min(epoch(year + 1), CUTOFF)
    first = ((start - WEEK - 300 - offset + WEEK - 1) // WEEK) * WEEK + offset
    return np.arange(first, end - (horizon + 1) * WEEK - 300, WEEK, dtype=np.int64)


def weekly_scores(paired, grid):
    groups = {int(t): g for t, g in paired[paired.timestamp.isin(grid)].groupby('timestamp')}
    rows = []
    for timestamp in grid:
        part = groups.get(int(timestamp))
        n = len(part) if part is not None else 0
        agreement = correlation(part.score_O, part.score_M) if n >= 20 else np.nan
        for signal, label in CELLS:
            rho = (correlation(part[f'score_{signal}'], part[f'label_{label}'])
                   if n >= 20 else np.nan)
            rows.append(dict(timestamp=int(timestamp), signal_field=signal, label_field=label,
                             items_count=n, rank_correlation=rho, lag_rank_agreement=agreement))
    return pd.DataFrame(rows)


def inference(values, indices):
    x = np.asarray(values, dtype=float)
    n = int(np.isfinite(x).sum())
    reason = ('missing_calendar_weeks' if n != len(x) else
              'insufficient_weeks' if n < 24 else
              'constant_weekly_series' if np.ptp(x) == 0 else 'adequate')
    result = dict(weeks=n, calendar_weeks=len(x), adequate=reason == 'adequate', reason=reason,
                  mean=float(x.mean()) if n == len(x) and n else None,
                  lower=None, upper=None, p_raw=1., p_adj=1., passed=False)
    if reason != 'adequate':
        return result
    means = x[indices].mean(axis=1)
    lower, upper = empirical_interval(means)
    p = float((1 + np.count_nonzero(means - x.mean() >= x.mean())) / (len(indices) + 1))
    adjusted = min(1., FAMILY * p)
    result.update(lower=float(lower), upper=float(upper), p_raw=p, p_adj=adjusted,
                  passed=bool(adjusted < .05 and lower > 0))
    return result


def summarize(scores):
    """Shared calendar draws across field cells and lookbacks for each era/horizon."""
    blocks = []
    for (year, horizon), era in scores.groupby(['year', 'horizon_weeks'], sort=True):
        grid = np.sort(era.timestamp.unique())
        for block in (4, 8):
            indices = block_indices(len(grid), block, draws=DRAWS, seed=SEED)
            for (lookback, signal, label), part in era.groupby(
                    ['lookback_weeks', 'signal_field', 'label_field'], sort=True):
                series = part.set_index('timestamp').reindex(grid)
                blocks.append(dict(year=int(year), horizon_weeks=int(horizon),
                    lookback_weeks=int(lookback), signal_field=signal, label_field=label,
                    block_weeks=block, min_items=int(series.items_count.min()),
                    median_items=float(series.items_count.median()),
                    lag_rank_agreement=float(series.lag_rank_agreement.mean()),
                    **inference(series.rank_correlation.to_numpy(), indices)))
    block_table = pd.DataFrame(blocks)
    summary = []
    for identity, part in block_table.groupby(KEYS, sort=True):
        if set(part.block_weeks) != {4, 8} or len(part) != 2:
            raise ValueError('Incomplete block family')
        base = dict(zip(KEYS, identity, strict=True))
        reference = part.iloc[0]
        summary.append(dict(**base, mean=reference['mean'], weeks=int(reference.weeks),
            calendar_weeks=int(reference.calendar_weeks), adequate=bool(part.adequate.all()),
            reason=reference.reason, lower=part.lower.min(), upper=part.upper.max(),
            p_raw=part.p_raw.max(), p_adj=part.p_adj.max(), passed=bool(part.passed.all()),
            min_items=int(reference.min_items), median_items=reference.median_items,
            lag_rank_agreement=reference.lag_rank_agreement))
    table = pd.DataFrame(summary)
    expected = set(product(range(2020, 2027), (1, 4), (1, 4), ('O', 'M'), ('O', 'M')))
    if set(table[KEYS].itertuples(index=False, name=None)) != expected or len(table) != FAMILY:
        raise ValueError('Incomplete registered 112-test family')
    return table, block_table


def run(source, output, acknowledged):
    output = external_directory(output, acknowledged)
    if any(output.iterdir()):
        raise FileExistsError('Use a new field-audit output directory')
    repo = Path(__file__).resolve().parents[3]
    code_paths = [Path(__file__), Path(uncertainty.__file__), Path(weekly_research.__file__)]
    manifest = dict(status='running', holdout_read=False, holdout_start=CUTOFF,
        protocol_sha256=sha256(repo / 'docs/reversal-field-audit-protocol.md'),
        code_sha256={p.name: sha256(p) for p in code_paths},
        source_manifest_sha256=sha256(source / 'run.json'), panel_sha256=SEALED_HASH,
        family_size=FAMILY, draws=DRAWS, seed=SEED, blocks_weeks=[4, 8],
        qualification='Source-rank measurement diagnostic; no account, fill or profit inference')
    # Reserve this attempt durably even if validation or execution is interrupted.
    atomic_json(output / 'run.json', manifest)
    panel, _ = load_panel(source)
    manifest.update(source_rows=len(panel), max_available_at=int(panel.available_at.max()))
    offset = int(panel.timestamp.iloc[0]) % WEEK
    scores = []
    for lookback, horizon in product((1, 4), repeat=2):
        paired = endpoints(panel, lookback, horizon)
        for year in range(2020, 2027):
            grid = era_grid(offset, year, horizon)
            score = weekly_scores(paired, grid)
            score['year'], score['lookback_weeks'], score['horizon_weeks'] = year, lookback, horizon
            scores.append(score)
        print(f'Scored matched fields: lookback={lookback}w horizon={horizon}w', flush=True)
    weekly = pd.concat(scores, ignore_index=True)
    summary, blocks = summarize(weekly)
    paths = ['weekly-scores.parquet', 'summary.csv', 'block-tests.csv']
    weekly.to_parquet(output / paths[0], index=False)
    summary.to_csv(output / paths[1], index=False)
    blocks.to_csv(output / paths[2], index=False)
    consistency = []
    for (lookback, horizon), part in summary.query(
            "signal_field == 'M' and label_field == 'M'").groupby(
                ['lookback_weeks', 'horizon_weeks'], sort=True):
        consistency.append(dict(lookback_weeks=int(lookback), horizon_weeks=int(horizon),
            passing_eras=int(part.passed.sum()), eras=len(part),
            all_era_midpoint_consistency=bool(len(part) == 7 and part.passed.all())))
    manifest.update(status='complete', tests=len(summary), block_tests=len(blocks),
        weekly_score_rows=len(weekly), corrected_passes=int(summary.passed.sum()),
        midpoint_consistency=consistency,
        output_sha256={p: sha256(output / p) for p in paths})
    atomic_json(output / 'run.json', manifest)
    print(summary.groupby(['lookback_weeks', 'horizon_weeks', 'signal_field', 'label_field'])
          .agg(min_mean=('mean', 'min'), max_mean=('mean', 'max'),
               worst_p_adj=('p_adj', 'max'), passing_eras=('passed', 'sum')).to_string(), flush=True)
    print(f'COMPLETE: {len(summary)}/112 tests; {len(blocks)} block tests; '
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
