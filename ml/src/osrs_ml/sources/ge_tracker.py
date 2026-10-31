"""GE Tracker acquisition for private local research; never a product dependency.

owner permission obtained through direct contact with GE Tracker
Redistribution, publication of raw derived data and product integration are not allowed.
"""
import argparse
import fcntl
import json
import os
import random
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

from .http import Client, FetchError, atomic_json
from .storage import canonical, completed, external_root, publish, snapshot_name

BASE = 'https://www.ge-tracker.com/api'
CREDENTIAL_FILE = Path('/home/martin/.hermes/secrets/ge-tracker.env')
PERMISSION = 'owner permission obtained through direct contact with GE Tracker'
# Auth scheme is supplied explicitly by the account owner from provider instructions.
# No bearer/cookie/session convention is inferred by this collector.
CREDENTIAL_KEY = 'GE_TRACKER_HEADERS_JSON'
PRIVATE_FIELDS = re.compile(r'email|password|token|cookie|authorization|receipt|subscription|'
                            r'account|username|login|correspondence', re.I)
EMAIL = re.compile(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}')


def market_only(value):
    """Fail closed before publishing anything resembling identity or credentials."""
    if isinstance(value, dict):
        for key, child in value.items():
            if PRIVATE_FIELDS.search(key):
                raise ValueError('Non-market field rejected; payload not published')
            market_only(child)
    elif isinstance(value, list):
        for child in value:
            market_only(child)
    elif isinstance(value, str) and EMAIL.search(value):
        raise ValueError('Personal address rejected; payload not published')


def credential_headers(path=CREDENTIAL_FILE):
    """Read a 0600, owner-only regular file without evaluating shell expressions."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        raise ValueError('Credential file cannot be opened securely') from None
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 \
                or info.st_uid != os.getuid():
            raise ValueError('Credential file must be an owner-held regular file with mode 0600')
        try:
            content = stream.read(65537)
            if len(content) > 65536:
                raise ValueError
            lines = [line.strip() for line in content.splitlines()
                     if line.strip() and not line.lstrip().startswith('#')]
            if len(lines) != 1 or not lines[0].startswith(CREDENTIAL_KEY + '='):
                raise ValueError
            value = lines[0].split('=', 1)[1].strip()
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            headers = json.loads(value)
            if not isinstance(headers, dict) or not headers:
                raise ValueError
            for key, value in headers.items():
                if not re.fullmatch(r'[A-Za-z0-9-]+', key) or key.lower() in \
                        ('user-agent', 'host', 'content-length', 'connection') \
                        or not isinstance(value, str) or not value \
                        or any(ord(c) < 32 or ord(c) > 126 for c in value):
                    raise ValueError
            return headers
        except (ValueError, TypeError, UnicodeError):
            raise ValueError('Invalid credential file; use provider-specified headers JSON') from None


def data(payload, expected):
    market_only(payload)
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), expected):
        raise ValueError('Unexpected GE Tracker market response schema')
    return payload['data']


def adapt_graph(payload, item_id, name=None):
    rows, seen = [], set()
    points = data(payload, list)
    envelope = {k: v for k, v in payload.items() if k != 'data'}
    for point in points:
        timestamp = point['ts']
        if type(timestamp) is not int or timestamp % 1000:
            raise ValueError('Expected integer millisecond timestamps')
        ts = timestamp // 1000
        if ts in seen:
            raise ValueError('Duplicate item/week timestamp')
        seen.add(ts)
        # GE Tracker's overall count can differ from the sum of the two sides.
        # Preserve all three reported counts, including nulls and zeroes.
        row = canonical(item_id, name, ts, source='ge-tracker-weekly',
                        high=point.get('buyingPrice'), low=point.get('sellingPrice'),
                        mid=point.get('overallPrice'), hv=point.get('buyingCompleted'),
                        lv=point.get('sellingCompleted'), volume=point.get('overallCompleted'),
                        extra={'point': point, 'envelope': envelope,
                               'granularity': 'weekly', 'bucket_may_be_incomplete': True})
        row['mid_price'] = point.get('overallPrice')
        row['total_volume'] = point.get('overallCompleted')
        rows.append(row)
    return sorted(rows, key=lambda r: r['ts'])


def adapt_item(item, fetched_at, *, source):
    market_only(item)
    # This is observation time, not a claim that both trade sides occurred together.
    ts = int(datetime.fromisoformat(fetched_at.replace('Z', '+00:00')).timestamp())
    row = canonical(item['itemId'], item.get('name'), ts, source=source,
                    high=item.get('buying'), low=item.get('selling'), mid=item.get('overall'),
                    extra={'item': item, 'timestamp_kind': 'fetched_at',
                           'quantity_semantics': 'reported snapshot; not bucket turnover'})
    row['mid_price'] = item.get('overall')
    # Quantity fields are retained as extras; their aggregation interval is unverified.
    return row


def route_probe(client, directory):
    """Always make real anonymous requests on the first run of a snapshot."""
    path = directory / 'routes.json'
    routes = json.loads(path.read_text()) if path.exists() else {}
    for route in ('/items', '/items/4151', '/graph/4151/all', '/market-watch'):
        if routes.get(route, {}).get('status') in (200, 401, 403):
            continue
        url = BASE + route
        try:
            payload, record = client.json(url, refresh=True)
            market_only(payload)
            routes[route] = dict(status=record['status'], evidence=record,
                                credential_requirement='none for this response')
        except FetchError as exc:
            routes[route] = dict(status=exc.status,
                                credential_requirement=('authentication required'
                                                        if exc.status in (401, 403)
                                                        else 'unavailable'))
            if exc.status not in (401, 403):
                atomic_json(path, routes)
                raise
        atomic_json(path, routes)
    atomic_json(path, routes)
    return routes


def collect_authenticated(client, directory, routes, headers):
    route = routes['/market-watch']
    result = dict(anonymous_status=route['status'])
    if headers is None:
        result['state'] = 'credentials not supplied'
    else:
        try:
            payload, record = client.json(BASE + '/market-watch', headers=headers, private=True)
            items = data(payload, list)
            if any(not isinstance(item, dict) or 'itemId' not in item for item in items):
                raise ValueError('Unsupported authenticated market schema; no payload published')
            rows = [adapt_item(item, record['fetched_at'], source='ge-tracker-market-watch')
                    for item in items]
            metadata = publish(directory / 'market-watch' / 'snapshot.parquet', rows,
                               source='ge-tracker-market-watch', record=record,
                               permission=PERMISSION, private_research_only=True)
            result.update(state='complete', status=200, **metadata)
        except FetchError as exc:
            result.update(state='authentication denied' if exc.status in (401, 403)
                          else 'unavailable', status=exc.status)
        except ValueError:
            result.update(state='schema unavailable; private payload not archived')
    atomic_json(directory / 'authenticated-routes.json', {'/market-watch': result})
    return result


def run(client, root, mapping=None, *, snapshot=None, ids=None, limit=None,
        credentials=CREDENTIAL_FILE):
    root = Path(root) / 'ge-tracker'
    root.mkdir(parents=True, exist_ok=True)
    # One writer across snapshots; resume the original snapshot by default.
    with (root / '.collector.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = sorted(root.glob('*/checkpoint.json'))
        snapshot = snapshot_name(snapshot or (existing[0].parent.name if existing else
                                 datetime.now(timezone.utc).strftime('%Y-%m-%d')))
        directory = root / snapshot
        directory.mkdir(parents=True, exist_ok=True)
        headers = credential_headers(credentials)
        routes = route_probe(client, directory)
        auth = collect_authenticated(client, directory, routes, headers)
        checkpoint = directory / 'checkpoint.json'
        progress = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        if not checkpoint.exists():
            atomic_json(checkpoint, progress)
        # Shared HTTP archive fixes catalogue/observation times across a resumed run.
        payload, record = client.json(BASE + '/items')
        items = data(payload, list)
        entries = {int(item['itemId']): item for item in items}
        if len(entries) != len(items):
            raise ValueError('Duplicate catalogue item ID')
        publish(directory / 'catalogue' / 'snapshot.parquet',
                [adapt_item(item, record['fetched_at'], source='ge-tracker-items') for item in items],
                source='ge-tracker-items', record=record,
                permission=PERMISSION, private_research_only=True)
        if ids:
            if set(ids) - entries.keys():
                raise ValueError('Unknown GE Tracker catalogue ID')
            entries = {i: entries[i] for i in ids}
        selected = sorted(entries)
        if limit is not None:
            selected = selected[:limit]
        for n, item_id in enumerate(selected, 1):
            state = progress.setdefault(str(item_id), {})
            recovered = False
            for kind, route in (('weekly', f'/graph/{item_id}/all'),
                                ('details', f'/items/{item_id}')):
                path = directory / kind / 'items' / f'{item_id}.parquet'
                if completed(path):
                    saved = dict(status='complete', **json.loads(
                        path.with_suffix('.manifest.json').read_text()))
                    if state.get(kind) != saved:
                        state[kind] = saved
                        recovered = True
                    continue
                prior = state.get(kind, {})
                application_retry = prior.get('status') == 'application error'
                if application_retry and time.time() < prior['retry_not_before']:
                    continue
                try:
                    response, evidence = client.json(BASE + route, refresh=application_retry)
                    if isinstance(response, dict) and response.get('status') == 'error':
                        market_only(response)
                        # HTTP 200 is not proof of data. The recorded service error
                        # asks for a minute; defer this item while collecting others.
                        fetched = datetime.fromisoformat(evidence['fetched_at'].replace('Z', '+00:00'))
                        state[kind] = dict(status='application error', rows=0, http_status=200,
                                           retry_not_before=fetched.timestamp() + 60 + random.random(),
                                           evidence=evidence)
                        atomic_json(checkpoint, progress)
                        recovered = False
                        continue
                    if kind == 'weekly':
                        rows = adapt_graph(response, item_id, entries[item_id].get('name'))
                    else:
                        item = data(response, dict)
                        if int(item['itemId']) != item_id:
                            raise ValueError('Response item mismatch')
                        rows = [adapt_item(item, evidence['fetched_at'], source='ge-tracker-details')]
                    metadata = publish(path, rows, source=f'ge-tracker-{kind}', record=evidence,
                                       permission=PERMISSION, private_research_only=True)
                    state[kind] = dict(status='complete', **metadata)
                except FetchError as exc:
                    state[kind] = dict(status='credentials not supplied' if exc.status in (401, 403)
                                       and headers is None else 'unavailable', http_status=exc.status)
                    atomic_json(checkpoint, progress)
                    if exc.status not in (401, 403, 404):
                        raise
                    # Do not repeat denials against more IDs in this route family.
                    if exc.status in (401, 403):
                        raise
                except (ValueError, KeyError, TypeError):
                    state[kind] = dict(status='schema error; inspect local anonymous evidence')
                    atomic_json(checkpoint, progress)
                    raise
                atomic_json(checkpoint, progress)
                recovered = False
            # Also repair checkpoint state when both partitions predate a crash.
            # Completed items must not rewrite the whole multi-megabyte checkpoint.
            if recovered:
                atomic_json(checkpoint, progress)
            if n % 100 == 0 or n == len(selected):
                current = summary(directory, progress, len(items), auth)
                atomic_json(directory / 'summary.json', current)
                print(json.dumps(current), flush=True)
        result = summary(directory, progress, len(items), auth)
        result['selection_complete'] = all(
            progress[str(i)].get(kind, {}).get('status') == 'complete'
            for i in selected for kind in ('weekly', 'details'))
        atomic_json(directory / 'summary.json', result)
        return result


def summary(directory, progress, catalogue_rows, auth):
    return dict(path=str(directory), items=len(progress), catalogue_rows=catalogue_rows,
                complete_items=sum(all(s.get(k, {}).get('status') == 'complete'
                                       for k in ('weekly', 'details')) for s in progress.values()),
                pending_items=[int(i) for i, s in progress.items()
                               if any(s.get(k, {}).get('status') != 'complete'
                                      for k in ('weekly', 'details'))],
                weekly_rows=sum(s.get('weekly', {}).get('rows', 0) for s in progress.values()),
                detail_rows=sum(s.get('details', {}).get('rows', 0) for s in progress.values()),
                authenticated=auth, permission=PERMISSION,
                permission_evidence='pending archive; correspondence must not be archived',
                private_research_only=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/home/martin/osrs-data/sources'))
    parser.add_argument('--snapshot')
    parser.add_argument('--ids', type=int, nargs='+')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--credentials', type=Path, default=CREDENTIAL_FILE)
    args = parser.parse_args()
    root = external_root(args.root)
    # Use the standard evidence location to share host locks with every source.
    client = Client(root / 'ge-tracker' / 'evidence' / 'http',
                    host_locks=root / 'evidence' / '.http-hosts')
    result = run(client, root, snapshot=args.snapshot, ids=args.ids, limit=args.limit,
                 credentials=args.credentials)
    print(json.dumps(result), flush=True)
    if not result['selection_complete']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
