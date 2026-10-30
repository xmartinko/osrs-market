"""Small public feature snapshots, excluded from market observation totals."""
import csv
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone

import pyarrow as pa

from .storage import completed, publish

REFS = {'kaggle-polls': 'nikkynak/oldschool-runescape-polling-data',
        'kaggle-alch': 'itsandrewxd/oldschoolrunescape-itemvalues-and-alchprices'}
NS = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def workbook(data):
    """Read the recorded workbook without evaluating formulas or macros."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        strings = [''.join(node.itertext()) for node in
                   ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        rows = []
        for row in sheet.findall('.//x:sheetData/x:row', NS):
            cells = {}
            for cell in row:
                column = re.sub(r'\d+', '', cell.attrib['r'])
                value = cell.findtext('x:v', default='', namespaces=NS)
                if cell.attrib.get('t') == 's':
                    value = strings[int(value)]
                cells[column] = value
            rows.append(cells)
    headers = rows[0]
    return [{headers.get(k) or 'source_row_index': v for k, v in row.items()}
            for row in rows[1:] if any(row.values())]


def alchemy(rows):
    def integer(value):
        return int(float(value)) if value else None
    return [dict(item_id=int(r['item_id']), name=r['name'],
                 value=integer(r['value']), highalch=integer(r['highalch']),
                 lowalch=integer(r['lowalch']), buy_limit=integer(r['limit']),
                 source_extra=json.dumps(r, sort_keys=True)) for r in rows]


def polls(rows):
    results = []
    for index, row in enumerate(rows):
        date = datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=float(row['Date']))
        results.append(dict(question_index=index, poll_date_ts=int(date.timestamp()),
                            question=row['Question'], title=row['Title'],
                            total_votes=int(float(row['totalVotes'])),
                            peak_players_unverified=float(row['peakPlayers']) if row['peakPlayers'] else None,
                            source_extra=json.dumps(row, sort_keys=True)))
    return results


def run(client, root, mapping=None, *, source='kaggle-alch'):
    label = {'kaggle-alch': 'alch', 'kaggle-polls': 'polls'}[source]
    directory = root / 'kaggle-features' / label
    archive = directory / 'raw-v1.zip'
    record = client.download('https://www.kaggle.com/api/v1/datasets/download/'
                             + REFS[source] + '?datasetVersionNumber=1', archive)
    output = directory / 'canonical-v1.parquet'
    if completed(output):
        return json.loads(output.with_suffix('.manifest.json').read_text())
    with zipfile.ZipFile(archive) as z:
        if source == 'kaggle-alch':
            rows = alchemy(list(csv.DictReader(io.StringIO(z.read('item_mapping.csv').decode()))))
        else:
            rows = polls(workbook(z.read('runescapePollingData.xlsx')))
    schema = pa.Table.from_pylist(rows).schema
    return publish(output, rows, source=source, record=record, schema=schema,
                   price_observations=False,
                   note=('Historical feature snapshot; no market prices. Poll peakPlayers '
                         'are third-party estimates, not official telemetry. '
                         'totalVotes repeats across questions of the same poll; do not sum questions.'))
