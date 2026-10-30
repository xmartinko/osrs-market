"""Wiki v2 float-safe bulk history and explicit per-item timeseries snapshots."""
import fcntl
import json
from datetime import datetime, timezone

from .http import atomic_json
from .storage import canonical, completed, publish

BASE = 'https://prices.runescape.wiki/api/v2/osrs'
REGIME_BREAK = 1790726400  # 2026-09-30 00:00 UTC: RuneLite -> Jagex, all clients.


def point(item_id, raw, timestamp, name=None, *, endpoint, economy='main'):
    return canonical(item_id, name, timestamp, source='wiki-v2',
                     high=raw.get('avgHighPrice'), low=raw.get('avgLowPrice'),
                     hv=raw.get('highPriceVolume'), lv=raw.get('lowPriceVolume'), economy=economy,
                     extra=dict(raw, endpoint=endpoint,
                                regime='runelite_only' if timestamp < REGIME_BREAK
                                else 'jagex_all_clients'))


def adapt(payload, names, endpoint, *, item_id=None, expected_timestamp=None):
    if not isinstance(payload, dict) or 'data' not in payload:
        raise ValueError(f'Unexpected Wiki schema: {str(payload)[:300]}')
    if item_id is None:
        ts = payload['timestamp']
        if expected_timestamp is not None and ts != expected_timestamp:
            raise ValueError('Wiki returned a different bucket than requested')
        return [point(int(i), r, ts, names.get(int(i)), endpoint=endpoint,
                      economy='main' if int(i) in names else 'unclassified_legacy')
                for i, r in payload['data'].items()]
    return [point(item_id, r, r['timestamp'], names.get(item_id), endpoint=endpoint)
            for r in payload['data']]


def bulk(client, root, mapping, *, resolution='5m', start=None, end=None):
    step = {'5m': 300, '1h': 3600}[resolution]
    names = {int(m['id']): m['name'] for m in mapping}
    directory = root / 'wiki-v2' / 'bulk' / resolution
    directory.mkdir(parents=True, exist_ok=True)
    if start is None:
        payload, _ = client.json(f'{BASE}/{resolution}', refresh=True)
        start = payload['timestamp']
        end = start + step
    if end is None or start % step or end % step or end <= start:
        raise ValueError('Require aligned start/end, end exclusive')
    checkpoint = directory / 'checkpoint.json'
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    window_rows = 0
    for n, ts in enumerate(range(start, end, step), 1):
        day = datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d')
        path = directory / day / f'{ts}.parquet'
        if completed(path):
            window_rows += json.loads(path.with_suffix('.manifest.json').read_text())['rows']
            continue
        url = f'{BASE}/{resolution}?timestamp={ts}'
        payload, record = client.json(url)
        rows = adapt(payload, names, resolution, expected_timestamp=ts)
        metadata = publish(path, rows, source='wiki-v2', record=record,
                           requested_timestamp=ts, resolution_seconds=step)
        window_rows += metadata['rows']
        # Independent forward/backfill processes merge the progress index under a lock.
        # Immutable per-bucket manifests are the authoritative resume checkpoints.
        with (directory / '.checkpoint.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
            state[str(ts)] = {k: metadata[k] for k in ('rows', 'fetched_at', 'sha256')}
            atomic_json(checkpoint, state)
        if n % 100 == 0 or ts + step == end:
            print(json.dumps(dict(source='wiki-v2', endpoint=resolution, processed=n,
                                  requested=(end-start)//step, rows=window_rows,
                                  last_ts=ts)), flush=True)
    return dict(source='wiki-v2', endpoint=resolution, buckets=(end-start)//step,
                rows=window_rows, start=start, end=end)


def timeseries(client, root, mapping, *, ids=None, lookback='6h', snapshot=None):
    names = {int(m['id']): m['name'] for m in mapping}
    ids = sorted(names) if ids is None else ids
    snapshot = snapshot or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    results = []
    for item_id in ids:
        path = root / 'wiki-v2' / 'timeseries' / lookback / snapshot / f'{item_id}.parquet'
        if completed(path):
            continue
        url = f'{BASE}/timeseries?lookback={lookback}&id={item_id}'
        payload, record = client.json(url, refresh=True)
        rows = adapt(payload, names, f'timeseries-{lookback}', item_id=item_id)
        results.append(publish(path, rows, source='wiki-v2', record=record, lookback=lookback))
    return results


def mapping_snapshot(client, root):
    """One immutable current mapping per UTC day; refresh new item coverage daily."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    path = root / 'wiki-v2' / 'mapping' / day / 'items.parquet'
    if completed(path):
        return pq.read_table(path).to_pylist()
    mapping, record = client.json(f'{BASE}/mapping', refresh=True)
    keys = sorted(set().union(*(r.keys() for r in mapping)))
    normalized = [{key: row.get(key) for key in keys} for row in mapping]
    schema = pa.Table.from_pylist(normalized).schema
    publish(path, normalized, source='wiki-v2-mapping', record=record, schema=schema,
            price_observations=False, table='mapping', note='Metadata available at fetch, not historically')
    return normalized


def snapshots(client, root, mapping):
    import pyarrow.parquet as pq

    names = {int(m['id']): m['name'] for m in mapping}
    results = []

    def split_publish(rows, record, fetched):
        for economy in ('main', 'unclassified_legacy'):
            selected = [dict(row, economy=economy) for row in rows
                        if (row['item_id'] in names) == (economy == 'main')]
            path = root / 'wiki-v2/latest-v2' / economy / f'{fetched}.parquet'
            results.append(publish(path, selected, source='wiki-v2-latest', record=record,
                                   note='ts is snapshot observation; side trade times in source_extra',
                                   economy=economy))

    # Retain and qualify the original snapshot without modifying the first conversion.
    for old in (root / 'wiki-v2/latest').glob('*.parquet'):
        metadata = json.loads(old.with_suffix('.manifest.json').read_text())
        if not completed(old):
            raise ValueError('Incomplete original latest snapshot')
        record = dict(url=metadata['endpoint'], fetched_at=metadata['fetched_at'],
                      sha256=metadata['payload_sha256'])
        split_publish(pq.read_table(old).to_pylist(), record, int(old.stem))
    payload, record = client.json(f'{BASE}/latest', refresh=True)
    fetched = int(datetime.fromisoformat(record['fetched_at']).timestamp())
    rows = [canonical(int(i), names.get(int(i)), fetched, source='wiki-v2-latest',
                      high=p.get('high'), low=p.get('low'),
                      extra=dict(p, price_semantics='latest side trades, not bucket averages',
                                 observation_timestamp=fetched)) for i, p in payload['data'].items()]
    split_publish(rows, record, fetched)
    return results


def repair_archive_gaps(client, root, mapping):
    """Enumerate and request every missing bucket in the fixed Kaggle v1 archive span."""
    from .columnar import connect

    archive = root / 'kaggle-5m' / 'canonical' / 'prices_5m'
    partitions = sorted(archive.rglob('*.parquet'))
    if len(partitions) != 68:
        raise ValueError('Complete 68-month Kaggle v1 archive required before gap enumeration')
    with connect() as db:
        observed = {r[0] for r in db.execute(
            'SELECT DISTINCT ts FROM read_parquet(?, hive_partitioning=false)',
            [[str(p) for p in partitions]]).fetchall()}
    start, end = min(observed), max(observed) + 300
    gaps = sorted(set(range(start, end, 300)) - observed)
    inventory = dict(archive_buckets=len(observed), expected_buckets=(end-start)//300,
                     missing_buckets=len(gaps), start=start, end=end, timestamps=gaps)
    atomic_json(root / 'kaggle-5m' / 'gap-inventory.json', inventory)
    for n, ts in enumerate(gaps, 1):
        bulk(client, root, mapping, resolution='5m', start=ts, end=ts+300)
        if n % 100 == 0 or n == len(gaps):
            print(json.dumps(dict(source='wiki-v2-repair', processed=n, total=len(gaps))), flush=True)
    return inventory | {'timestamps': 'see external gap-inventory.json'}
