"""Streaming canonical adapters for large public archives; retain every raw column."""
import json
from pathlib import Path

import duckdb

from ..data import manifest
from .storage import completed


def connect():
    db = duckdb.connect()
    db.execute("SET memory_limit='1GB'")
    db.execute('SET threads=2')
    db.execute("SET temp_directory='/home/martin/osrs-data/sources/scratch'")
    return db


def summary(db, relation):
    row = db.execute(f'''SELECT count(*), count(DISTINCT item_id), min(ts), max(ts),
        min(ts) FILTER(WHERE total_volume IS NOT NULL), count(total_volume),
        count(DISTINCT ts) FROM {relation}''').fetchone()
    annual = db.execute(f'''SELECT year(to_timestamp(ts)) AS year, count(*) AS rows,
        count(total_volume) AS volume_rows FROM {relation} GROUP BY 1 ORDER BY 1''').fetchall()
    return dict(rows=row[0], items=row[1], min_ts=row[2], max_ts=row[3],
                first_nonnull_volume_ts=row[4], volume_rows=row[5], buckets=row[6],
                volume_by_year=[dict(year=r[0], rows=r[1], volume_rows=r[2]) for r in annual])


def normalize(raw, output, *, record, source, economy='main', timestamp='timestamp',
              mapping=None, format='parquet', timestamp_scale=1):
    raw, output = Path(raw), Path(output)
    if completed(output):
        return json.loads(output.with_suffix('.manifest.json').read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix('.partial')
    with connect() as db:
        if format == 'parquet':
            db.read_parquet(str(raw)).create_view('raw')
        else:
            db.sql("SELECT * FROM read_csv_auto(?, nullstr=['', 'NULL', 'null'])",
                   params=[str(raw)]).create_view('raw')
        # Values are SQL parameters where possible; identifiers come only from adapter code.
        db.execute('CREATE TABLE names(item_id BIGINT, name VARCHAR)')
        if mapping:
            db.executemany('INSERT INTO names VALUES (?, ?)',
                           [(int(r['id']), r['name']) for r in mapping])
        safe_source = source.replace("'", "''")
        safe_economy = economy.replace("'", "''")
        db.execute(f'''CREATE VIEW canonical AS SELECT raw.*,
            itemId::BIGINT AS item_id, names.name, "{timestamp}"::BIGINT * {int(timestamp_scale)} AS ts,
            avgHighPrice::DOUBLE AS avg_high_price, avgLowPrice::DOUBLE AS avg_low_price,
            highPriceVolume::BIGINT AS high_price_volume,
            lowPriceVolume::BIGINT AS low_price_volume,
            (avgHighPrice::DOUBLE + avgLowPrice::DOUBLE) / 2 AS mid_price,
            highPriceVolume::BIGINT + lowPriceVolume::BIGINT AS total_volume,
            '{safe_source}'::VARCHAR AS source, '{safe_economy}'::VARCHAR AS economy
            FROM raw LEFT JOIN names ON raw.itemId=names.item_id''')
        stats = summary(db, 'canonical')
        if stats['rows'] and stats['min_ts'] < 1356998400:
            raise ValueError('Timestamp predates OSRS; archive needs investigation')
        duplicate = db.execute('''SELECT item_id, ts FROM canonical GROUP BY 1,2
                                HAVING count(*) > 1 LIMIT 1''').fetchone()
        if duplicate:
            raise ValueError(f'Duplicate source keys: {duplicate}')
        db.execute("COPY canonical TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(pending)])
    if output.exists():
        raise FileExistsError(output)
    pending.rename(output)
    result = manifest(output, source=source, endpoint=record['original_url']
                      if 'original_url' in record else record['url'],
                      fetched_at=record['fetched_at'], payload_sha256=record['sha256'],
                      economy=economy, raw_file=str(raw), timestamp_scale=timestamp_scale, **stats)
    print(json.dumps(dict(source=source, economy=economy, file=str(output), **stats)), flush=True)
    return result
