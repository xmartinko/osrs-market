"""Official public world population observations. No claimed historical activity API."""
import html
import re
from datetime import datetime, timezone

import pyarrow as pa

from .storage import completed, publish

URL = 'https://oldschool.runescape.com/slu'
SCHEMA = pa.schema([('world_id', pa.int64()), ('ts', pa.int64()), ('players', pa.int64()),
                    ('population_literal', pa.string()), ('location', pa.string()),
                    ('membership', pa.string()), ('activity', pa.string())])


def adapt(text, ts):
    rows = []
    for match in re.finditer(r'<tr\b[^>]*class=[\'\"][^\'\"]*\bserver-list__row\b[^\'\"]*[\'\"][^>]*>(.*?)</tr>', text, re.S):
        block = match.group(1)
        world = re.search(r'slu-world-(\d+)', block)
        cells = [html.unescape(re.sub('<[^>]+>', '', cell)).strip() for cell in
                 re.findall(r'<td\b[^>]*>(.*?)</td>', block, re.S)]
        if world is None or len(cells) != 5:
            raise ValueError('World table schema changed')
        count = re.fullmatch(r'([\d,]+) players', cells[1])
        rows.append(dict(world_id=int(world.group(1)), ts=ts,
                         players=int(count.group(1).replace(',', '')) if count else None,
                         population_literal=cells[1], location=cells[2],
                         membership=cells[3], activity=cells[4]))
    if not rows or len({r['world_id'] for r in rows}) != len(rows):
        raise ValueError('Empty or duplicate official world list')
    return rows


def run(client, root, mapping=None):
    now = datetime.now(timezone.utc)
    path = root / 'official-activity' / 'v2' / now.strftime('%Y-%m-%d') / (now.strftime('%H-%M')+'.parquet')
    if completed(path):
        return []
    body, record = client.fetch(URL, refresh=True)
    ts = int(datetime.fromisoformat(record['fetched_at']).timestamp())
    rows = adapt(body.decode(), ts)
    return [publish(path, rows, source='official-activity', record=record, schema=SCHEMA,
                    price_observations=False, parser_version=2, population_sum=sum(r['players'] or 0 for r in rows),
                    unknown_world_populations=sum(r['players'] is None for r in rows),
                    note='Current public world list; includes special economies; not historical DAU')]
