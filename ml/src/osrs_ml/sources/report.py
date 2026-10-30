"""Audit research partitions only; legacy/holdout observations are never loaded."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from .columnar import connect, summary
from .http import atomic_json
from .storage import external_root


def groups(root):
    patterns = {
        'ge-tracker-weekly': 'ge-tracker/*/weekly/items/*.parquet',
        'weirdgloop-all': 'weirdgloop-all/????-??-??/items/*.parquet',
        'weirdgloop-archive-only': 'weirdgloop-all/*archive-only/items/*.parquet',
        'weirdgloop-last90d': 'weirdgloop-last90d/*/items/*.parquet',
        'kaggle-5m': 'kaggle-5m/canonical-v2/main/**/*.parquet',
        'kaggle-5m-unclassified': 'kaggle-5m/canonical-v2/unclassified_legacy/**/*.parquet',
        'wiki-v2-5m': 'wiki-v2/bulk/5m/*/*.parquet',
        'wiki-v2-1h': 'wiki-v2/bulk/1h/*/*.parquet',
        'wiki-v2-timeseries-6h': 'wiki-v2/timeseries/6h/*/*.parquet',
        'wiki-v2-timeseries-7d': 'wiki-v2/timeseries/7d/*/*.parquet',
        'wiki-v2-latest': 'wiki-v2/latest-v2/main/*.parquet',
        'wiki-v2-latest-unclassified': 'wiki-v2/latest-v2/unclassified_legacy/*.parquet',
        'kaggle-daily': 'kaggle-other/osrs-ge-prices-snapshot-june-27-2026/canonical/*.parquet',
        'kaggle-bonds': 'kaggle-other/oldschool-runescape-bond-price-history/canonical/*.parquet',
        'academic-utk': 'academic-utk/canonical/*.parquet',
        'wayback-wiki': 'wayback/canonical/*.parquet',
        'jagex-guide': 'jagex-guide/daily/*.parquet',
    }
    for economy in ('deadman_reborn', 'fsw_2022', 'deadman_apocalypse',
                    'deadman_armageddon', 'deadman_annihilation'):
        patterns['seasonal-' + economy] = f'seasonal-dumps/{economy}/*.parquet'
    return {name: sorted(root.glob(pattern)) for name, pattern in patterns.items()}


def feature_groups(root):
    patterns = {
        'ge-tracker-items': 'ge-tracker/*/catalogue/*.parquet',
        'ge-tracker-details': 'ge-tracker/*/details/items/*.parquet',
        'ge-tracker-market-watch': 'ge-tracker/*/market-watch/*.parquet',
        'wiki-mapping': 'wiki-v2/mapping/*/*.parquet',
        'wiki-items': 'wiki-pages/????-??-??/items/*.parquet',
        'wiki-modules': 'wiki-pages/????-??-??/modules/*.parquet',
        'wiki-monsters': 'wiki-pages/*monsters/items/*.parquet',
        'wiki-shops': 'wiki-pages/*shops/items/*.parquet',
        'wiki-special': 'wiki-pages/*special/items/*.parquet',
        'mediawiki-revisions': 'mediawiki-revisions/*/*.parquet',
        'official-activity': 'official-activity/v2/*/*.parquet',
        'jagex-moving-average': 'jagex-guide/average/*.parquet',
        'kaggle-alch': 'kaggle-features/alch/canonical-v1.parquet',
        'kaggle-polls': 'kaggle-features/polls/canonical-v1.parquet',
        'wiki-feature-facts': 'wiki-feature-facts/*/*.parquet',
    }
    for source in ('osrsbox', 'osrsreboxed'):
        for kind in ('items', 'monsters', 'drops'):
            patterns[f'{source}-{kind}'] = f'{source}/*/{kind}.parquet'
    return {name: sorted(root.glob(pattern)) for name, pattern in patterns.items()}


def inventory(paths):
    entries = []
    for path in paths:
        meta = json.loads(path.with_suffix('.manifest.json').read_text())
        rows = pq.ParquetFile(path).metadata.num_rows
        if rows != meta['rows']:
            raise ValueError(f'Footer/manifest row mismatch: {path}')
        entries.append(dict(path=str(path), rows=rows, sha256=meta['sha256'],
                            exported_at=meta['exported_at']))
    return entries


def run(root, *, baseline_cutoff=None):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = root / ('coverage-' + stamp)
    output.mkdir()
    # Freeze the list of completed partitions before examining live collectors.
    price_paths, features = groups(root), feature_groups(root)
    selected = {k: inventory(v) for k, v in (price_paths | features).items()}
    atomic_json(output / 'inventory.json', selected)
    result = dict(generated_at=datetime.now(timezone.utc).isoformat(),
                  note='Physical canonical source rows; feeds and mirrors overlap. '
                       'Excludes raw copies, superseded conversions, features and moving averages. '
                       'Does not claim a cross-source deduplicated panel.', groups={}, features={})
    for name, paths in price_paths.items():
        if not paths:
            continue
        with connect() as db:
            db.read_parquet([str(p) for p in paths], hive_partitioning=False).create_view('observations')
            stats = summary(db, 'observations')
            stats['sample'] = db.execute('SELECT item_id, name, ts, avg_high_price, '
                'avg_low_price, high_price_volume, low_price_volume, mid_price, '
                'total_volume, economy FROM observations LIMIT 1').to_arrow_table().to_pylist()[0]
            stats['economies'] = [dict(economy=e, rows=n) for e, n in db.execute(
                'SELECT economy, count(*) FROM observations GROUP BY 1').fetchall()]
            item_path = output / (name + '-items.parquet')
            db.execute('''COPY (SELECT item_id, count(*) AS rows, min(ts) AS min_ts,
                max(ts) AS max_ts, min(ts) FILTER(WHERE total_volume IS NOT NULL)
                AS first_nonnull_volume_ts, count(total_volume) AS volume_rows,
                max(ts) FILTER(WHERE total_volume IS NULL) AS last_null_volume_ts
                FROM observations GROUP BY item_id) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)''',
                [str(item_path)])
        stats['files'] = len(paths)
        if stats['rows'] != sum(v['rows'] for v in selected[name]):
            raise ValueError(f'Inventory changed: {name}')
        result['groups'][name] = stats
        print(name, json.dumps(stats, default=str), flush=True)
        atomic_json(output / 'coverage.json', result)
    for name, paths in features.items():
        if not paths:
            continue
        rows = sum(v['rows'] for v in selected[name])
        # Small preview only; never open the original exports or sealed research panels.
        batch = next(pq.ParquetFile(paths[0]).iter_batches(batch_size=1), None)
        sample = batch.to_pylist()[0] if batch is not None else {}
        sample = {k: v for k, v in sample.items() if k not in ('wikitext', 'raw_json', 'source_extra')}
        result['features'][name] = dict(rows=rows, files=len(paths), sample=sample)
        print(name, rows, json.dumps(sample, default=str), flush=True)
    before = json.loads((root / 'before.json').read_text()) if (root / 'before.json').exists() else None
    if before:
        result['original_baseline_price_rows'] = before['total_price_rows']
        checks = []
        for entry in before['files']:
            stat = Path(entry['path']).stat()
            checks.append(stat.st_size == entry['bytes'] and stat.st_mtime_ns == entry['mtime_ns'])
        if not all(checks):
            raise ValueError('An original baseline file changed')
        result['preserved_original_files'] = len(checks)
        # Count only immutable legacy price archives, using footers, never row contents.
        legacy = [root.parent / 'prices.parquet',
                  root.parent / 'ge-tracker-weekly-v1/weekly.parquet']
        legacy += sorted((root.parent / 'forward/wiki/300s').glob('*/observations.parquet'))
        result['legacy_price_rows_now'] = sum(pq.ParquetFile(p).metadata.num_rows for p in legacy)
    result['canonical_source_rows'] = sum(v['rows'] for v in result['groups'].values())
    if baseline_cutoff is not None:
        result['finishing_pass_baseline_cutoff'] = baseline_cutoff.isoformat()
        result['source_rows_already_held_at_cutoff'] = sum(
            entry['rows'] for name in price_paths for entry in selected[name]
            if datetime.fromisoformat(entry['exported_at']) < baseline_cutoff)
        result['source_rows_added_after_cutoff'] = (result['canonical_source_rows']
                                                   - result['source_rows_already_held_at_cutoff'])
    result['positive_finite_price_rows'] = sum(v['positive_finite_price_rows']
                                               for v in result['groups'].values())
    result['total_physical_price_rows'] = (result['canonical_source_rows']
                                          + result.get('legacy_price_rows_now', 0))
    atomic_json(output / 'coverage.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('groups', 'features')}), flush=True)
    print('Coverage artifact:', output, flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/home/martin/osrs-data/sources'))
    parser.add_argument('--baseline-cutoff', type=datetime.fromisoformat)
    args = parser.parse_args()
    run(external_root(args.root), baseline_cutoff=args.baseline_cutoff)
