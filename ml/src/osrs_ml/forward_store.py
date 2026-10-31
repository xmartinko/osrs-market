"""Rebuildable archive index and bounded cursors for prospective ledger replay.

The immutable Parquet archive remains authoritative. Each verified snapshot and its
checkpoint commit together; a killed import is retried. No ledger records are pruned.
"""

import hashlib
import json
from heapq import merge
from itertools import groupby

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .data import sha256


class ArchiveStore:
    def __init__(self, db, path):
        self.db = db
        db.execute("PRAGMA cache_size=-8192")
        db.execute("PRAGMA temp_store=FILE")
        db.execute("ATTACH DATABASE ? AS archive_cache", [str(path)])
        db.execute("PRAGMA archive_cache.cache_size=-8192")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS archive_cache.snapshots (
                path TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS archive_cache.observations (
                source TEXT NOT NULL, resolution_seconds INTEGER NOT NULL,
                item_id INTEGER NOT NULL, timestamp INTEGER NOT NULL,
                fetched_at INTEGER NOT NULL, available_at INTEGER NOT NULL,
                context_json TEXT NOT NULL,
                UNIQUE(source,resolution_seconds,item_id,timestamp));
            CREATE INDEX IF NOT EXISTS archive_cache.observations_available
                ON observations(available_at,item_id);
            CREATE INDEX IF NOT EXISTS archive_cache.observations_item_time
                ON observations(item_id,resolution_seconds,timestamp);
            CREATE INDEX IF NOT EXISTS predictions_replay
                ON predictions(model,model_hash,issued_at,item_id,horizon_seconds,id,score);
            CREATE INDEX IF NOT EXISTS predictions_horizon ON predictions(horizon_seconds);
            DROP INDEX IF EXISTS predictions_cohort_time;
        """)

    def refresh(self, root, resolution):
        from .forward import canonical, row_json

        for path in sorted(root.glob(f"{resolution}s/*/observations.parquet")):
            metadata = json.loads(path.with_suffix(".manifest.json").read_text())
            checksum = sha256(path)
            if checksum != metadata["sha256"]:
                raise ValueError("Archive checksum mismatch")
            previous = self.db.execute(
                "SELECT sha256 FROM archive_cache.snapshots WHERE path=?", [str(path)]
            ).fetchone()
            if previous:
                if previous[0] != checksum:
                    raise ValueError("Previously indexed immutable archive changed")
                continue
            with self.db:
                for batch in pq.ParquetFile(path).iter_batches(batch_size=4096):
                    frame = batch.to_pandas(types_mapper=pd.ArrowDtype)
                    self.db.executemany("""
                        INSERT INTO archive_cache.observations VALUES (?,?,?,?,?,?,?)
                        ON CONFLICT(source,resolution_seconds,item_id,timestamp) DO UPDATE SET
                            fetched_at=excluded.fetched_at, available_at=excluded.available_at,
                            context_json=excluded.context_json
                        WHERE excluded.fetched_at < observations.fetched_at
                        """, (
                        (r['source'], r['resolution_seconds'], r['item_id'], r['timestamp'],
                         r['fetched_at'], r['available_at'], canonical(r))
                        for r in (row_json(row) for row in frame.to_dict('records'))
                    ))
                self.db.execute("INSERT INTO archive_cache.snapshots VALUES (?,?)",
                                [str(path), checksum])

    def latest(self, now, resolution):
        future = self.db.execute("""SELECT 1 FROM archive_cache.observations
            WHERE available_at>? OR fetched_at>? LIMIT 1""", [now, now]).fetchone()
        if future:
            raise ValueError("Future context cannot issue a prediction")
        # issue() already rejects older decisions. Only materialize the eligible window.
        rows = self.db.execute("""SELECT context_json FROM (
            SELECT context_json, row_number() OVER (
                PARTITION BY item_id ORDER BY available_at DESC, rowid DESC) AS n
            FROM archive_cache.observations WHERE available_at>=?) WHERE n=1""",
            [now - 2 * resolution])
        records = [json.loads(r[0]) for r in rows]
        return (pa.Table.from_pylist(records).to_pandas(types_mapper=pd.ArrowDtype)
                if records else pd.DataFrame())

    def archive_hash(self):
        h = hashlib.sha256(b"[")
        separator = b""
        for row in self.db.execute("""SELECT context_json FROM archive_cache.observations
                                       ORDER BY item_id,timestamp"""):
            h.update(separator)
            h.update(row[0].encode())
            separator = b","
        h.update(b"]")
        return h.hexdigest()

    def settle(self, now):
        from .costs import sale_proceeds
        from .forward import canonical

        added = 0
        # Scan the small, ordered identity index rather than every large context.
        # The outcomes identity index is visited in the same order, limiting disk IO.
        pending = self.db.execute("""SELECT p.id FROM predictions p
            INDEXED BY sqlite_autoindex_predictions_1
            WHERE NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.prediction_id=p.id)""")
        for identity in pending:
            p = self.db.execute("""SELECT p.*,a.context_json AS observation
            FROM predictions p JOIN archive_cache.observations a ON a.rowid=(
                SELECT rowid FROM archive_cache.observations
                WHERE item_id=p.item_id AND resolution_seconds=p.resolution_seconds
                  AND timestamp>=p.issued_at+p.horizon_seconds
                  AND fetched_at<=? AND available_at<=?
                ORDER BY timestamp LIMIT 1)
            WHERE p.id=?""", [now, now, identity[0]]).fetchone()
            if p is None:
                continue
            row = json.loads(p['observation'])
            missing = row['avg_low_price'] is None or row['inverted_spread']
            late = row['timestamp'] > p['issued_at'] + p['horizon_seconds'] + 2 * p['resolution_seconds']
            status = 'missing_side' if missing else 'late_observation' if late else 'observed'
            net = (None if status != 'observed' else
                   sale_proceeds(row['avg_low_price'], 1, item_id=p['item_id']) - p['entry_gp'])
            self.db.execute('INSERT OR IGNORE INTO outcomes VALUES (?,?,?,?,?,?)',
                            [p['id'], now, row['timestamp'], status, net, canonical(row)])
            added += 1
        self.db.commit()
        return added

    def paper_events(self, cohorts, now):
        """Decode real observations once; keep synthetic decisions cohort-specific."""
        start = min(c['start'] for c in cohorts)

        def real_events():
            cursor = self.db.execute("""SELECT available_at,item_id,context_json
                FROM archive_cache.observations WHERE available_at BETWEEN ? AND ?
                ORDER BY available_at,item_id""", [start, now])
            for r in cursor:
                yield r['available_at'], None, r

        def decision_events(cohort):
            key = (cohort['model'], cohort['model_hash'])
            cursor = self.db.execute("""SELECT issued_at AS available_at,item_id,
                    context_json,data_cutoff FROM predictions p
                WHERE model=? AND model_hash=? AND NOT EXISTS (
                    SELECT 1 FROM archive_cache.observations a
                    WHERE a.item_id=p.item_id AND a.available_at=p.issued_at
                      AND a.available_at BETWEEN ? AND ?)
                GROUP BY issued_at,item_id HAVING rowid=min(rowid)
                ORDER BY issued_at,item_id""", [*key, cohort['start'], now])
            for r in cursor:
                yield r['available_at'], key, r

        streams = [real_events(), *(decision_events(c) for c in cohorts)]
        cursor = merge(*streams, key=lambda event: event[0])
        for timestamp, group in groupby(cursor, key=lambda event: event[0]):
            real, decisions = {}, {}
            for _, cohort, r in group:
                rows = real if cohort is None else decisions.setdefault(cohort, {})
                if r['item_id'] in rows:
                    raise ValueError('Duplicate item availability in archived replay')
                row = json.loads(r['context_json'])
                if cohort is not None:
                    row['available_at'] = timestamp
                    row['high_price_volume'] = row['low_price_volume'] = 0
                    for side in ['high', 'low']:
                        key = f'{side}_freshness_seconds'
                        if row[key] is not None:
                            row[key] += timestamp - r['data_cutoff']
                rows[r['item_id']] = row
            yield timestamp, real, decisions


class LedgerScores:
    """Keep just one timestamp's scores in memory, rather than a whole cohort."""

    def __init__(self, db, cohort):
        self.db, self.cohort = db, cohort
        self.timestamp, self.scores = None, {}

    def get(self, key, default):
        item, timestamp = key
        if timestamp != self.timestamp:
            self.timestamp = timestamp
            self.scores = dict(self.db.execute("""SELECT item_id,score FROM predictions
                WHERE model=? AND model_hash=? AND issued_at=? ORDER BY item_id,rowid""",
                [*self.cohort, timestamp]))
        return self.scores.get(item, default)
