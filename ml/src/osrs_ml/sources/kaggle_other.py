"""Small public mirrors; report overlap, retain nulls from the unfilled daily CSV."""
import csv
import json
import shutil
import zipfile
from datetime import datetime, timezone

from ..data import manifest
from .columnar import connect, summary
from .storage import canonical, completed, publish

REFS = {'kaggle-daily': 'felixgabay/osrs-ge-prices-snapshot-june-27-2026',
        'kaggle-bonds': 'doauinc/oldschool-runescape-bond-price-history'}


def run(client, root, mapping=None, *, source='kaggle-daily'):
    ref = REFS[source]
    directory = root / 'kaggle-other' / ref.split('/')[1]
    archive = directory / 'raw.zip'
    record = client.download('https://www.kaggle.com/api/v1/datasets/download/' + ref, archive)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            from pathlib import PurePosixPath
            parts = PurePosixPath(member.filename).parts
            if '..' in parts or member.filename.startswith('/'):
                raise ValueError('Unsafe archive member')
            path = directory / 'raw' / member.filename
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                pending = path.with_suffix('.partial')
                with z.open(member) as stream, pending.open('wb') as output:
                    shutil.copyfileobj(stream, output)
                pending.rename(path)
    output = directory / 'canonical' / 'observations.parquet'
    if completed(output):
        return [json.loads(output.with_suffix('.manifest.json').read_text())]
    if source == 'kaggle-bonds':
        rows = []
        with (directory / 'raw/osrs_old_school_bond_history.csv').open() as f:
            for row in csv.DictReader(f):
                ts = int(datetime.fromisoformat(row['Date']).replace(tzinfo=timezone.utc).timestamp())
                rows.append(canonical(13190, 'Old school bond', ts, source=source,
                                      mid=float(row['Price (GP)']), extra=row))
        return [publish(output, rows, source=source, record=record,
                        overlap_note='Mirror of Weird Gloop; not independent observations')]
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix('.partial')
    with connect() as db:
        db.read_csv(str(directory / 'raw/Upload/full_data.csv')).create_view('raw')
        db.read_csv(str(directory / 'raw/Upload/mapping.csv')).create_view('names')
        db.execute('''CREATE VIEW canonical AS SELECT raw.* EXCLUDE(item_id),
            raw.item_id::BIGINT AS item_id, names.name,
            raw.timestamp::BIGINT AS ts,
            raw.avgHighPrice::DOUBLE AS avg_high_price,
            raw.avgLowPrice::DOUBLE AS avg_low_price,
            raw.highPriceVolume::BIGINT AS high_price_volume,
            raw.lowPriceVolume::BIGINT AS low_price_volume,
            (raw.avgHighPrice + raw.avgLowPrice) / 2 AS mid_price,
            raw.highPriceVolume::BIGINT + raw.lowPriceVolume::BIGINT AS total_volume,
            'kaggle-daily' AS source, 'main' AS economy
            FROM raw LEFT JOIN names ON raw.item_id=names.id''')
        stats = summary(db, 'canonical')
        duplicate = db.execute('''SELECT item_id, ts FROM canonical GROUP BY 1,2
                                 HAVING count(*) > 1 LIMIT 1''').fetchone()
        if duplicate:
            raise ValueError(f'Duplicate source keys {duplicate}')
        db.execute('COPY canonical TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(pending)])
    pending.rename(output)
    result = manifest(output, source=source, fetched_at=record['fetched_at'],
                      endpoint=record['original_url'], payload_sha256=record['sha256'],
                      null_note='Use full_data.csv; enriched snapshot zero-fills missing prices', **stats)
    print(json.dumps(dict(source=source, **stats)), flush=True)
    return [result]
