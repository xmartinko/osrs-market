"""University project snapshot: measured cadence only, unverified upstream methodology."""
import json
from collections import defaultdict

from ..data import manifest
from .columnar import connect, summary
from .storage import completed

URL = 'https://raw.githubusercontent.com/utkML/OSRS_GE_Forecasting/main/overall_avg_ge.csv'


def run(client, root, mapping):
    directory = root / 'academic-utk'
    raw = directory / 'raw/overall_avg_ge.csv'
    record = client.download(URL, raw)
    output = directory / 'canonical/observations.parquet'
    if completed(output):
        return [json.loads(output.with_suffix('.manifest.json').read_text())]
    historical, _ = client.json('https://raw.githubusercontent.com/osrsbox/osrsbox-db/master/docs/items-complete.json')
    names = defaultdict(set)
    for row in mapping:
        names[row['name'].replace('_', ' ').casefold()].add(int(row['id']))
    for row in historical.values():
        if row.get('tradeable_on_ge'):
            names[row['name'].replace('_', ' ').casefold()].add(int(row['id']))
    unique_names = [(name, next(iter(ids))) for name, ids in names.items() if len(ids) == 1]
    output.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.read_csv(str(raw)).create_view('wide')
        db.execute('CREATE TABLE names(name VARCHAR, item_id BIGINT)')
        db.executemany('INSERT INTO names VALUES (?, ?)', unique_names)
        db.execute('''CREATE VIEW cast_wide AS SELECT timestamp,
            COLUMNS(* EXCLUDE(timestamp))::VARCHAR FROM wide''')
        db.execute('''CREATE VIEW source_long AS SELECT * FROM cast_wide
            UNPIVOT INCLUDE NULLS (raw_price FOR raw_name IN
                                  (COLUMNS(* EXCLUDE(timestamp))))''')
        db.execute('''CREATE VIEW canonical AS SELECT source_long.*, names.item_id,
            replace(raw_name, '_', ' ') AS name, timestamp::BIGINT AS ts,
            NULL::DOUBLE AS avg_high_price, NULL::DOUBLE AS avg_low_price,
            NULL::BIGINT AS high_price_volume, NULL::BIGINT AS low_price_volume,
            try_cast(raw_price AS DOUBLE) AS mid_price, NULL::BIGINT AS total_volume,
            'academic-utk' AS source, 'osrs_unspecified' AS economy
            FROM source_long LEFT JOIN names ON lower(replace(raw_name, '_', ' '))=names.name''')
        stats = summary(db, 'canonical')
        unknown = db.execute('SELECT count(DISTINCT raw_name) FROM canonical WHERE item_id IS NULL').fetchone()[0]
        cadence = db.execute('''SELECT median(gap), min(gap), max(gap), count(*) FROM
            (SELECT timestamp - lag(timestamp) OVER (ORDER BY timestamp) AS gap FROM wide)''').fetchone()
        duplicate = db.execute('''SELECT raw_name, ts FROM canonical GROUP BY 1,2
                                 HAVING count(*) > 1 LIMIT 1''').fetchone()
        if duplicate:
            raise ValueError(f'Duplicate archive keys {duplicate}')
        pending = output.with_suffix('.partial')
        db.execute('COPY canonical TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(pending)])
    pending.rename(output)
    result = manifest(output, source='academic-utk', endpoint=URL,
                      fetched_at=record['fetched_at'], payload_sha256=record['sha256'],
                      unresolved_item_names=unknown, median_gap_seconds=cadence[0],
                      minimum_gap_seconds=cadence[1], maximum_gap_seconds=cadence[2],
                      price_methodology='Unknown upstream; do not call bid/ask or interval average',
                      licence_note='No repository licence found; private research only', **stats)
    print(json.dumps(result), flush=True)
    return [result]
