"""Wiki v2 float-safe bulk history and explicit per-item timeseries snapshots."""
import json
from datetime import datetime, timezone

from .http import atomic_json
from .storage import canonical, completed, publish

BASE = 'https://prices.runescape.wiki/api/v2/osrs'
REGIME_BREAK = 1790726400  # 2026-09-30 00:00 UTC: RuneLite -> Jagex, all clients.


def point(item_id, raw, timestamp, name=None, *, endpoint):
    return canonical(item_id, name, timestamp, source='wiki-v2',
                     high=raw.get('avgHighPrice'), low=raw.get('avgLowPrice'),
                     hv=raw.get('highPriceVolume'), lv=raw.get('lowPriceVolume'),
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
        return [point(int(i), r, ts, names.get(int(i)), endpoint=endpoint)
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
    for n, ts in enumerate(range(start, end, step), 1):
        day = datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d')
        path = directory / day / f'{ts}.parquet'
        if completed(path):
            continue
        url = f'{BASE}/{resolution}?timestamp={ts}'
        payload, record = client.json(url)
        rows = adapt(payload, names, resolution, expected_timestamp=ts)
        metadata = publish(path, rows, source='wiki-v2', record=record,
                           requested_timestamp=ts, resolution_seconds=step)
        state[str(ts)] = {k: metadata[k] for k in ('rows', 'fetched_at', 'sha256')}
        atomic_json(checkpoint, state)
        if n % 100 == 0 or ts + step == end:
            print(json.dumps(dict(source='wiki-v2', endpoint=resolution, processed=n,
                                  requested=(end-start)//step, rows=sum(r['rows'] for r in state.values()),
                                  last_ts=ts)), flush=True)
    return dict(source='wiki-v2', endpoint=resolution, buckets=len(state),
                rows=sum(v['rows'] for v in state.values()))


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
    payload, record = client.json(f'{BASE}/latest', refresh=True)
    fetched = int(datetime.fromisoformat(record['fetched_at']).timestamp())
    names = {int(m['id']): m['name'] for m in mapping}
    rows = [canonical(int(i), names.get(int(i)), fetched, source='wiki-v2-latest',
                      high=p.get('high'), low=p.get('low'),
                      extra=dict(p, price_semantics='latest side trades, not bucket averages',
                                 observation_timestamp=fetched)) for i, p in payload['data'].items()]
    return [publish(root / 'wiki-v2/latest' / f'{fetched}.parquet', rows, source='wiki-v2-latest',
                    record=record, note='ts is snapshot observation; side trade times in source_extra')]
