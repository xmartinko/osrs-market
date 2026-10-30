"""Summarize actual HTTP attempts, excluding mutable URL-cache indexes."""
import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .http import USER_AGENT, atomic_json


def audit(directory, *, require_ua_since=None):
    hosts = defaultdict(list)
    variants = Counter()
    for path in Path(directory).glob('*.json'):
        if not re.fullmatch(r'[0-9a-f]{64}-\d+\.json', path.name):
            continue
        record = json.loads(path.read_text())
        variants[record.get('user_agent', 'unrecorded')] += 1
        fetched = datetime.fromisoformat(record['fetched_at'])
        if (require_ua_since is not None and fetched >= require_ua_since
                and record.get('user_agent') != USER_AGENT):
            raise ValueError(f'Unexpected acquisition user agent after cutoff: {path}')
        hosts[urlsplit(record['url']).hostname].append(record)
    result = dict(required_user_agent=USER_AGENT, observed_user_agents=dict(variants), hosts={})
    for host, records in sorted(hosts.items()):
        starts = sorted(datetime.fromisoformat(r['started_at']).timestamp()
                        for r in records if 'started_at' in r)
        limits = []
        for r in records:
            headers = {k: v for k, v in r.get('headers', {}).items()
                       if 'ratelimit' in k.lower() or k.lower() == 'retry-after'}
            if headers and headers not in limits:
                limits.append(headers)
        result['hosts'][host] = dict(requests=len(records),
            status_counts=dict(Counter(str(r['status']) for r in records)),
            requests_with_start_timestamp=len(starts),
            minimum_start_spacing_seconds=min((b-a for a, b in zip(starts, starts[1:], strict=False)), default=None),
            rate_limit_headers=limits)
    result['requests'] = sum(v['requests'] for v in result['hosts'].values())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path,
                        default=Path('/home/martin/osrs-data/sources/evidence/http'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-ua-since', type=datetime.fromisoformat)
    args = parser.parse_args()
    result = audit(args.evidence, require_ua_since=args.require_ua_since)
    atomic_json(args.output, result)
    print(json.dumps(result, indent=2))
