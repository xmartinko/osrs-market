"""Research acquisition CLI; transport/schema failures propagate as nonzero exits."""
import argparse
import fcntl
import json
from datetime import datetime
from pathlib import Path

from .http import Client
from .registry import SOURCES
from .storage import external_root
from .wiki import bulk, mapping_snapshot, timeseries


def timestamp(value):
    try:
        return int(value)
    except ValueError:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise argparse.ArgumentTypeError('Timestamp must have a UTC offset') from None
        return int(parsed.timestamp())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', choices=sorted(SOURCES) + ['wiki-v2-bulk', 'wiki-v2-timeseries'])
    parser.add_argument('--root', type=Path, default=Path('/home/martin/osrs-data/sources'))
    parser.add_argument('--resolution', choices=['5m', '1h'], default='5m')
    parser.add_argument('--start', type=timestamp)
    parser.add_argument('--end', type=timestamp)
    parser.add_argument('--lookback', choices=['6h', '24h', '7d', '30d', '6m', '1y'], default='6h')
    parser.add_argument('--ids', type=int, nargs='+')
    parser.add_argument('--snapshot')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    root = external_root(args.root)
    client = Client(root / ('ge-tracker/evidence/http' if args.source == 'ge-tracker'
                          else 'evidence/http'), host_locks=root / 'evidence/.http-hosts')
    with (root / f'.{args.source}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.source == 'ge-tracker':
            result = SOURCES[args.source](client, root, snapshot=args.snapshot,
                                         ids=args.ids, limit=args.limit)
            print(json.dumps(result), flush=True)
            if not result['selection_complete']:
                raise SystemExit(2)
            return
        mapping = mapping_snapshot(client, root)
        bulk_sources = ('wiki-v2-bulk', 'wiki-v2-forward', 'wiki-v2-repair', 'wiki-v2-snapshots')
        if args.ids and args.source not in bulk_sources:
            mapping = [m for m in mapping if int(m['id']) in set(args.ids)]
            if len(mapping) != len(set(args.ids)):
                raise ValueError('Unknown mapping identifier')
        if args.limit is not None and args.source not in bulk_sources:
            mapping = sorted(mapping, key=lambda m: int(m['id']))[:args.limit]
        if args.source == 'wiki-v2-bulk':
            result = bulk(client, root, mapping, resolution=args.resolution,
                          start=args.start, end=args.end)
        elif args.source == 'wiki-v2-timeseries':
            result = timeseries(client, root, mapping, lookback=args.lookback, snapshot=args.snapshot)
        elif args.source in ('weirdgloop-all', 'weirdgloop-last90d'):
            result = SOURCES[args.source](client, root, mapping, snapshot=args.snapshot)
        elif args.source == 'wiki-revisions':
            result = SOURCES[args.source](client, root, mapping, ids=args.ids)
        else:
            result = SOURCES[args.source](client, root, mapping)
        print(json.dumps(result, default=str), flush=True)


if __name__ == '__main__':
    main()
