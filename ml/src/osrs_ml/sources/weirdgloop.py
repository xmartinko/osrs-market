"""Daily archive and rolling 90-day exchange history; never invent trade sides."""
import json
from datetime import datetime, timezone

from .http import FetchError, atomic_json
from .storage import canonical, completed, publish

BASE = 'https://api.weirdgloop.org/exchange'


def adapt(payload, item_id, name=None, kind='all', economy='main'):
    if not isinstance(payload, dict) or str(item_id) not in payload:
        raise ValueError(f'Application error for {item_id}: {str(payload)[:300]}')
    rows, seen = [], set()
    for point in payload[str(item_id)]:
        if int(point['id']) != int(item_id):
            raise ValueError('Response item mismatch')
        timestamp = point['timestamp']
        if not isinstance(timestamp, int) or timestamp % 1000:
            raise ValueError('Expected integer millisecond timestamps')
        ts = timestamp // 1000
        if ts in seen:
            raise ValueError('Duplicate source timestamp')
        seen.add(ts)
        rows.append(canonical(item_id, name, ts, source=f'weirdgloop-{kind}',
                              mid=point['price'], volume=point.get('volume'), economy=economy, extra=point))
    return sorted(rows, key=lambda r: r['ts'])


def run(client, root, mapping, *, kind='all', limit=None, snapshot=None):
    if kind not in ('all', 'last90d'):
        raise ValueError(kind)
    # Explicit snapshot allows rolling polls while rerunning the same snapshot resumes.
    if snapshot is None and kind == 'all':
        existing = sorted((root / 'weirdgloop-all').glob('????-??-??/checkpoint.json'))
        if not existing:
            existing = sorted((root / 'weirdgloop-all').glob('*/checkpoint.json'),
                              key=lambda p: -len(json.loads(p.read_text())))
        snapshot = existing[0].parent.name if existing else None
    snapshot = snapshot or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    directory = root / f'weirdgloop-{kind}' / snapshot
    directory.mkdir(parents=True, exist_ok=True)
    checkpoint = directory / 'checkpoint.json'
    progress = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    entries = sorted(mapping, key=lambda r: int(r['id']))
    if limit is not None:
        entries = entries[:limit]
    for n, item in enumerate(entries, 1):
        item_id = int(item['id'])
        path = directory / 'items' / f'{item_id}.parquet'
        if completed(path):
            if progress.get(str(item_id), {}).get('status') != 'complete':
                metadata = json.loads(path.with_suffix('.manifest.json').read_text())
                progress[str(item_id)] = dict(status='complete', **metadata)
                atomic_json(checkpoint, progress)
            continue
        if progress.get(str(item_id), {}).get('status') == 'empty':
            continue
        url = f'{BASE}/history/osrs/{kind}?id={item_id}'
        try:
            payload, record = client.json(url, refresh=kind == 'last90d')
            if payload == {'success': False, 'error': 'No results returned'}:
                progress[str(item_id)] = dict(status='empty', rows=0, endpoint=url,
                                              fetched_at=record['fetched_at'], evidence=record)
            else:
                rows = adapt(payload, item_id, item['name'], kind, economy=item.get('economy', 'main'))
                raw_rows = len(rows)
                if kind == 'last90d':
                    import pyarrow.parquet as pq
                    seen = set()
                    for prior in (root / 'weirdgloop-last90d').glob(f'*/items/{item_id}.parquet'):
                        if prior != path:
                            seen.update(pq.read_table(prior, columns=['ts'])['ts'].to_pylist())
                    rows = [r for r in rows if r['ts'] not in seen]
                metadata = publish(path, rows, source=f'weirdgloop-{kind}', record=record,
                                   raw_rows=raw_rows, duplicate_rows_omitted=raw_rows-len(rows))
                progress[str(item_id)] = dict(status='complete', **metadata)
        except (FetchError, ValueError) as exc:
            progress[str(item_id)] = dict(status='error', error=str(exc))
            atomic_json(checkpoint, progress)
            # A transport denial stops collection; do not keep hammering a blocked host.
            raise
        atomic_json(checkpoint, progress)
        if n % 100 == 0 or n == len(entries):
            print(json.dumps(dict(source=f'weirdgloop-{kind}', completed=n,
                                  total=len(entries), rows=sum(v['rows'] for v in progress.values()),
                                  last_item=item_id)), flush=True)
    return dict(source=f'weirdgloop-{kind}', items=len(progress),
                rows=sum(v['rows'] for v in progress.values()), path=str(directory))


def archive_only(client, root, mapping=None, *, snapshot=None):
    """Inspect the frozen mirror's unclassified IDs without assigning a main market."""
    import pyarrow.parquet as pq

    from .columnar import connect

    paths = sorted((root / 'kaggle-5m/canonical-v2/unclassified_legacy').rglob('*.parquet'))
    if len(paths) != 68:
        raise ValueError('Complete classified mirror conversion required')
    with connect() as db:
        ids = [row[0] for row in db.execute('SELECT DISTINCT item_id FROM read_parquet(?)',
                                           [[str(p) for p in paths]]).fetchall()]
    names = {r['itemId']: r['name'] for r in
             pq.read_table(root / 'kaggle-5m/raw/items.parquet').to_pylist()}
    items = [dict(id=i, name=names.get(i), economy='unclassified_legacy') for i in sorted(ids)]
    snapshot = snapshot or datetime.now(timezone.utc).strftime('%Y-%m-%d')+'-archive-only'
    return run(client, root, items, snapshot=snapshot)
