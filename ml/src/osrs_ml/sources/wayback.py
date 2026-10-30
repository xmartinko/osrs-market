"""Recover only prices actually embedded in public archive captures; never interpolate."""
import html
import re

from .storage import canonical, publish

URL = ('https://web.archive.org/web/20190723163722id_/'
       'https://oldschool.runescape.wiki/w/Exchange:Abyssal_whip')


def adapt(text, *, item_id=4151, name='Abyssal whip', capture='20190723163722'):
    arrays = re.findall(r'<[^>]*class="GEdataprices"[^>]*data-data="([^"]*)"', text)
    rows = []
    seen = set()
    grouped = {}
    for data in arrays:
        for token in html.unescape(data).split('|'):
            grouped.setdefault(token.split(':')[0], set()).add(token)
    for data in arrays:
        for token in html.unescape(data).split('|'):
            if not token:
                continue
            fields = token.split(':')
            if len(fields) < 2 or not all(re.fullmatch(r'\d+', field) for field in fields):
                raise ValueError('Unrecognized archived chart token')
            timestamp, price = map(int, fields[:2])
            volume = int(fields[2]) if len(fields) == 3 else None
            if token in seen:
                continue  # exact repeated source token; raw HTML remains untouched
            seen.add(token)
            rows.append(canonical(item_id, name, timestamp, source='wayback-wiki', mid=price, volume=volume,
                                  extra=dict(capture=capture, literal=token,
                                             timestamp_conflict=len(grouped[str(timestamp)]) > 1,
                                             volume_status=('present' if volume is not None else
                                                            'ambiguous' if len(fields) > 3 else 'absent'))))
    if not rows:
        raise ValueError('No embedded historical prices; a captured page is not a dataset')
    return rows


def run(client, root, mapping=None):
    path = root / 'wayback' / 'snapshot-20190723163722.html'
    record = client.download(URL, path)
    rows = adapt(path.read_text())
    return [publish(root / 'wayback/canonical/4151-20190723163722.parquet', rows,
                    source='wayback-wiki', record=record,
                    note='Archived Wiki price chart; Volume only where a third chart field exists; capture time != price time')]
