"""Revision/page provenance. Lua and templates are archived as text, never executed."""
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

import pyarrow as pa

from .http import atomic_json
from .storage import completed, publish, snapshot_name

BASE = 'https://oldschool.runescape.wiki/api.php'
SCHEMA = pa.schema([('page_id', pa.int64()), ('title', pa.string()),
                    ('revision_id', pa.int64()), ('revision_ts', pa.int64()),
                    ('item_id', pa.int64()), ('price', pa.float64()), ('volume', pa.int64()),
                    ('price_date_literal', pa.string()), ('volume_date_literal', pa.string()),
                    ('wikitext', pa.string())])


def literal(text, field):
    match = re.search(r'^\s*' + re.escape(field) + r'\s*=\s*([^\n]+)', text, re.M)
    return match.group(1).strip().rstrip(',').strip() if match else None


def numeric(text, field):
    value = literal(text, field)
    return float(value) if value and re.fullmatch(r'-?\d+(?:\.\d+)?', value) else None


def adapt(payload):
    if 'error' in payload:
        raise ValueError(str(payload['error']))
    rows = []
    for page in payload.get('query', {}).get('pages', {}).values():
        for rev in page.get('revisions', []):
            text = rev['slots']['main'].get('*', '')
            iid, vol = numeric(text, 'itemId'), numeric(text, 'volume')
            rows.append(dict(page_id=page['pageid'], title=page['title'],
                             revision_id=rev['revid'],
                             revision_ts=int(datetime.fromisoformat(
                                 rev['timestamp'].replace('Z', '+00:00')).timestamp()),
                             item_id=int(iid) if iid is not None else None,
                             price=numeric(text, 'price'), volume=int(vol) if vol is not None else None,
                             price_date_literal=literal(text, 'date'),
                             volume_date_literal=literal(text, 'volumeDate'), wikitext=text))
    return rows


def revisions(client, root, mapping, *, ids=None):
    by_id = {int(m['id']): m for m in mapping}
    ids = [2, 561, 4151] if ids is None else ids
    results = []
    for iid in ids:
        continuation = {}
        while True:
            params = dict(action='query', format='json', prop='revisions',
                          titles=f"Module:Exchange/{by_id[iid]['name']}",
                          rvprop='timestamp|content|ids', rvslots='main', rvlimit=50,
                          rvdir='newer', **continuation)
            url = BASE + '?' + urlencode(params)
            key = continuation.get('rvcontinue', 'first').replace('|', '-')
            path = root / 'mediawiki-revisions' / str(iid) / f'{key}.parquet'
            payload, record = client.json(url)
            rows = adapt(payload)
            results.append(publish(path, rows, source='mediawiki-revisions', record=record,
                                   schema=SCHEMA, price_observations=False,
                                   price_rows=sum(r['price'] is not None for r in rows),
                                   min_revision_ts=min((r['revision_ts'] for r in rows), default=None),
                                   max_revision_ts=max((r['revision_ts'] for r in rows), default=None)))
            if 'continue' not in payload:
                break
            continuation = payload['continue']
    return results


def pages(client, root, mapping, *, modules=False, snapshot=None):
    snapshot = snapshot_name(snapshot or datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    kind = 'modules' if modules else 'items'
    directory = root / 'wiki-pages' / snapshot / kind
    results = []
    for offset in range(0, len(mapping), 25):
        titles = [m['name'] for m in mapping[offset:offset+25]]
        if modules:
            titles = ['Module:Exchange/' + name for name in titles]
        key = hashlib.sha256('|'.join(titles).encode()).hexdigest()[:16]
        path = directory / f'{offset:05}-{key}.parquet'
        legacy = directory / f'{offset:05}.parquet'
        if completed(legacy):
            old = json.loads(legacy.with_suffix('.manifest.json').read_text())
            if old.get('requested_titles') == titles:
                continue
        if completed(path):
            continue
        params = dict(action='query', format='json', prop='revisions',
                      titles='|'.join(titles), rvprop='timestamp|content|ids', rvslots='main')
        payload, record = client.json(BASE + '?' + urlencode(params), refresh=True)
        rows = adapt(payload)
        missing = [p['title'] for p in payload['query']['pages'].values() if 'missing' in p]
        results.append(publish(path, rows, source='wiki-pages', record=record, schema=SCHEMA,
                               price_observations=False, requested_titles=titles, missing_titles=missing))
    return results


def category_pages(client, root, *, category, suffix):
    """Archive the direct category's current pages with continuation and source text."""
    day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    snapshot = day+'-'+suffix
    inventory = root / 'wiki-pages' / snapshot / 'titles.json'
    if inventory.exists():
        titles = json.loads(inventory.read_text())['titles']
        return pages(client, root, [dict(name=t) for t in titles], snapshot=snapshot)
    previous = sorted((inventory.parent / 'items').glob('*.manifest.json'))
    if previous:
        titles = sorted({title for p in previous
                         for title in json.loads(p.read_text())['requested_titles']})
        atomic_json(inventory, dict(category=category, titles=titles))
        return pages(client, root, [dict(name=t) for t in titles], snapshot=snapshot)
    continuation = {}
    titles = set()
    while True:
        params = dict(action='query', format='json', list='categorymembers',
                      cmtitle=category, cmlimit=500, cmnamespace=0, **continuation)
        payload, _ = client.json(BASE + '?' + urlencode(params), refresh=True)
        if 'error' in payload:
            raise ValueError(str(payload['error']))
        titles.update(p['title'] for p in payload['query']['categorymembers'])
        if 'continue' not in payload:
            break
        continuation = payload['continue']
    inventory.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(inventory, dict(category=category, titles=sorted(titles)))
    return pages(client, root, [dict(name=t) for t in sorted(titles)], snapshot=snapshot)


def monsters(client, root, mapping=None):
    return category_pages(client, root, category='Category:Monsters', suffix='monsters')


def shops(client, root, mapping=None):
    return category_pages(client, root, category='Category:Shops', suffix='shops')
