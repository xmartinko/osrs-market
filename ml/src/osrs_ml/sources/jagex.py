"""Official public 180-day guide-price graphs; moving averages kept separate."""
import json

from .http import FetchError, atomic_json
from .storage import canonical, completed, publish

BASE = 'https://secure.runescape.com/m=itemdb_oldschool/api'


def adapt(payload, iid, name, metric):
    if not isinstance(payload.get(metric), dict):
        raise ValueError('Official graph schema changed')
    return [canonical(iid, name, int(ts)//1000, source='jagex-guide', mid=value,
                      extra=dict(metric=metric, timestamp_ms=ts, price=value,
                                 is_smoothed=metric == 'average'))
            for ts, value in payload[metric].items()]


def run(client, root, mapping):
    directory = root / 'jagex-guide'
    directory.mkdir(parents=True, exist_ok=True)
    checkpoint = directory / 'checkpoint.json'
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    for n, item in enumerate(sorted(mapping, key=lambda m: int(m['id'])), 1):
        iid = int(item['id'])
        paths = [directory / metric / f'{iid}.parquet' for metric in ('daily', 'average')]
        if all(completed(p) for p in paths):
            if state.get(str(iid), {}).get('status') != 'complete':
                meta = json.loads(paths[0].with_suffix('.manifest.json').read_text())
                state[str(iid)] = dict(status='complete', rows=meta['rows'])
                atomic_json(checkpoint, state)
            continue
        if state.get(str(iid), {}).get('status') in ('missing', 'empty'):
            continue
        url = f'{BASE}/graph/{iid}.json'
        try:
            body, record = client.fetch(url)
            if not body.strip():
                state[str(iid)] = dict(status='empty', http_status=record['status'], rows=0,
                                       endpoint=url, evidence=record, reason='HTTP 200 empty body')
                atomic_json(checkpoint, state)
                continue
            payload = json.loads(body)
            results = []
            for metric, path in zip(('daily', 'average'), paths, strict=True):
                rows = adapt(payload, iid, item['name'], metric)
                results.append(publish(path, rows, source='jagex-guide', record=record,
                                       metric=metric, price_observations=metric == 'daily',
                                       note='Guide price; no bid/ask or volume; average is smoothed'))
            state[str(iid)] = dict(status='complete', rows=results[0]['rows'])
        except (FetchError, ValueError) as exc:
            status = getattr(exc, 'status', None)
            state[str(iid)] = dict(status='missing' if status == 404 else 'error',
                                   http_status=status, error=str(exc), rows=0)
            atomic_json(checkpoint, state)
            if status != 404:
                raise
        atomic_json(checkpoint, state)
        if n % 100 == 0 or n == len(mapping):
            print(json.dumps(dict(source='jagex-guide', items=n, total=len(mapping),
                                  rows=sum(r['rows'] for r in state.values()))), flush=True)
    return dict(source='jagex-guide', items=len(state), rows=sum(r['rows'] for r in state.values()))
