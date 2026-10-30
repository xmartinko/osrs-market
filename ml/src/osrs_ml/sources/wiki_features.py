"""Conservative literal facts from archived Wiki item, drop and shop templates.

No Lua/template execution, derived alchemy values, inferred drops or supply estimates.
The original wikitext remains authoritative for nested/conditional values.
"""
import json
import re

import pyarrow as pa
import pyarrow.parquet as pq

from .storage import completed, publish

SCHEMA = pa.schema([
    ('page_item_id', pa.int64()), ('title', pa.string()), ('revision_id', pa.int64()),
    ('revision_ts', pa.int64()), ('template', pa.string()), ('template_offset', pa.int64()),
    ('field', pa.string()), ('literal', pa.string()), ('numeric_literal', pa.float64()),
])
TEMPLATES = re.compile(r'\{\{\s*(Infobox Item|Infobox Bonuses|DropsLine|StoreLine)\s*(?=\||\n)', re.I)


def fields(text):
    """Split top-level parameters; pipes in nested templates and wikilinks are data."""
    braces = links = 0
    start = 0
    for token in re.finditer(r'\{\{|\}\}|\[\[|\]\]|\|', text):
        value = token.group()
        if value == '{{':
            braces += 1
        elif value == '}}':
            braces -= 1
        elif value == '[[':
            links += 1
        elif value == ']]':
            links -= 1
        elif not braces and not links:
            yield text[start:token.start()]
            start = token.end()
    yield text[start:]


def adapt(page, names):
    rows = []
    for match in TEMPLATES.finditer(page['wikitext']):
        depth = 1
        end = None
        for token in re.finditer(r'\{\{|\}\}', page['wikitext'][match.end():]):
            depth += 1 if token.group() == '{{' else -1
            if not depth:
                end = match.end() + token.start()
                break
        if end is None:
            continue  # Do not invent fields from a truncated template.
        for field in fields(page['wikitext'][match.end():end]):
            if '=' not in field:
                continue
            key, value = (p.strip() for p in field.split('=', 1))
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', key):
                continue
            numeric = float(value) if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value) else None
            rows.append(dict(page_item_id=names.get(page['title']), title=page['title'],
                             revision_id=page['revision_id'], revision_ts=page['revision_ts'],
                             template=match.group(1), template_offset=match.start(),
                             field=key, literal=value, numeric_literal=numeric))
    return rows


def run(client, root, mapping):
    names = {m['name']: int(m['id']) for m in mapping}
    results = []
    for path in sorted((root / 'wiki-pages').glob('*/items/*.parquet')):
        snapshot = path.parent.parent.name
        target = root / 'wiki-feature-facts' / snapshot / path.name
        if completed(target):
            continue
        meta = json.loads(path.with_suffix('.manifest.json').read_text())
        rows = [r for page in pq.read_table(path).to_pylist() for r in adapt(page, names)]
        record = dict(url=meta['endpoint'], fetched_at=meta['fetched_at'],
                      sha256=meta['payload_sha256'])
        results.append(publish(target, rows, source='wiki-feature-facts', record=record,
                               schema=SCHEMA, price_observations=False,
                               upstream_parquet_sha256=meta['sha256'],
                               min_revision_ts=min((r['revision_ts'] for r in rows), default=None),
                               max_revision_ts=max((r['revision_ts'] for r in rows), default=None),
                               note='Literal template parameters only; numeric null means nonliteral, '
                                    'not zero. Drops/stock templates are definitions, not realized flows.'))
    return dict(source='wiki-feature-facts', new_partitions=len(results),
                new_rows=sum(r['rows'] for r in results))
