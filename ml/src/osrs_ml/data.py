"""Read existing tables only. Missing source metadata stays missing."""

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from psycopg.rows import dict_row

FIELDS = [
    "item_id",
    "timestamp",
    "avg_high_price",
    "avg_low_price",
    "high_price_volume",
    "low_price_volume",
    "buy_limit",
    "source_interval_seconds",
    "ingested_at",
]
SCHEMA = pa.schema([(f, pa.int64()) for f in FIELDS])
REGIME_BREAK = int(datetime(2026, 9, 30, tzinfo=timezone.utc).timestamp())

EXPORT_SQL = """
SELECT p.item_id::bigint, p.timestamp, p.avg_high_price, p.avg_low_price,
       p.high_price_volume, p.low_price_volume, r.buy_limit,
       NULL::bigint AS source_interval_seconds,
       EXTRACT(EPOCH FROM p.created_at)::bigint AS ingested_at
FROM price_events p
LEFT JOIN LATERAL (
    SELECT buy_limit FROM item_revisions
    WHERE item_id = p.item_id AND created_at <= to_timestamp(p.timestamp)
    ORDER BY created_at DESC, id DESC LIMIT 1
) r ON TRUE
WHERE p.timestamp >= %s AND p.timestamp < %s
ORDER BY p.item_id, p.timestamp
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(path: Path, *, source: str, rows: int, **metadata):
    value = {
        "schema_version": 1,
        "source": source,
        "rows": rows,
        "sha256": sha256(path),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        **metadata,
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(value, indent=2) + "\n")
    return value


def export_postgres(dsn: str, output: Path, start: int, end: int) -> dict:
    if end <= start:
        raise ValueError("End must follow start")
    if output.exists() or output.with_suffix(".manifest.json").exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".partial")
    count = 0
    try:
        with psycopg.connect(dsn, connect_timeout=3) as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                with connection.cursor(name="ml_snapshot", row_factory=dict_row) as cursor:
                    cursor.execute(EXPORT_SQL, (start, end))
                    with pq.ParquetWriter(temporary, SCHEMA) as writer:
                        while rows := cursor.fetchmany(10_000):
                            writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMA))
                            count += len(rows)
        if not count:
            raise ValueError("Empty snapshot")
        temporary.rename(output)
        return manifest(
            output,
            source="postgres",
            rows=count,
            start=start,
            end=end,
            interval_status="unknown: not persisted by existing collector",
            freshness_status="lower-bound bucket estimates, not exact trade times",
        )
    finally:
        temporary.unlink(missing_ok=True)


def load_snapshot(
    path: Path, *, allow_unknown_metadata: bool = False, unknown_interval_seconds: int = 300
) -> pd.DataFrame:
    metadata_path = path.with_suffix(".manifest.json")
    if not metadata_path.exists():
        raise ValueError("Snapshot manifest required")
    metadata = json.loads(metadata_path.read_text())
    if metadata["sha256"] != sha256(path):
        raise ValueError("Snapshot checksum mismatch")
    schema = pq.read_schema(path)
    if any(schema.field(f).type != pa.int64() for f in FIELDS):
        raise ValueError("Snapshot columns must be signed int64")
    with duckdb.connect() as connection:
        # Arrow-backed pandas keeps nullable int64 prices exact (no float conversion).
        frame = (
            connection.execute(
                "SELECT * FROM read_parquet(?) ORDER BY item_id, timestamp", [str(path)]
            )
            .to_arrow_table()
            .to_pandas(types_mapper=pd.ArrowDtype)
        )
    if frame.empty or len(frame) != metadata["rows"]:
        raise ValueError("Empty snapshot or manifest row-count mismatch")
    required = ["item_id", "timestamp", "high_price_volume", "low_price_volume"]
    if frame[required].isna().any().any() or frame.duplicated(["item_id", "timestamp"]).any():
        raise ValueError("NULL keys/volumes or duplicate observations")
    nonnegative = [f for f in FIELDS if f != "ingested_at"]
    if (frame[nonnegative] < 0).any().any():
        raise ValueError("Negative source data")
    if (frame[["avg_high_price", "avg_low_price"]] == 0).any().any():
        raise ValueError("Zero price; use NULL for missing")
    intervals = frame.source_interval_seconds
    if (intervals <= 0).any():
        raise ValueError("Nonpositive source interval")
    if (
        intervals.isna().any() or frame.get("interval_unknown", pd.Series(False)).any()
    ) and not allow_unknown_metadata:
        raise ValueError("Unknown source intervals; explicit --allow-unknown-metadata required")
    if "available_at" not in frame:
        frame["available_at"] = frame.timestamp + intervals.fillna(unknown_interval_seconds)
    if "interval_unknown" not in frame:
        frame["interval_unknown"] = intervals.isna()
    if "resolution_seconds" in frame:
        if (
            frame.resolution_seconds.nunique() != 1
            or frame.get("resolution_ambiguous", pd.Series(False)).any()
        ):
            raise ValueError("Select one strict, unambiguous resolution panel")
        intervals = intervals.fillna(frame.resolution_seconds)
        if (frame.available_at < frame.timestamp + intervals).any():
            raise ValueError("Availability precedes bucket completion")
    frame["observed_gap_seconds"] = frame.groupby("item_id").timestamp.diff()
    previous_end = (frame.timestamp + intervals).groupby(frame.item_id).shift(1)
    if (frame.timestamp < previous_end).any():
        raise ValueError("Overlapping source buckets; qualify resolutions before evaluation")
    frame = frame.sort_values(["item_id", "available_at", "timestamp"]).reset_index(drop=True)
    for side in ("high", "low"):
        if f"{side}_freshness_seconds" in frame:
            continue
        traded = (frame[f"{side}_price_volume"] > 0) & frame[f"avg_{side}_price"].notna()
        last_bucket = frame.available_at.where(traded).groupby(frame.item_id).ffill()
        frame[f"{side}_freshness_seconds"] = frame.available_at - last_bucket
    frame["regime"] = frame.timestamp.map(
        lambda t: "pre_2026_09_30" if t < REGIME_BREAK else "post_2026_09_30"
    )
    return frame


def load_daily_history(path: Path, *, now: int, lookback: int = 30) -> pd.DataFrame:
    """Validate the full daily panel on disk; materialize only inference inputs."""
    if lookback <= 0:
        raise ValueError("Positive history lookback required")
    metadata = json.loads(path.with_suffix('.manifest.json').read_text())
    if metadata['sha256'] != sha256(path):
        raise ValueError('Snapshot checksum mismatch')
    schema = pq.read_schema(path)
    if any(schema.field(f).type != pa.int64() for f in FIELDS):
        raise ValueError('Snapshot columns must be signed int64')
    count = pq.ParquetFile(path).metadata.num_rows
    if not count or count != metadata['rows']:
        raise ValueError('Empty snapshot or manifest row-count mismatch')
    columns = ['item_id', 'timestamp', 'available_at', 'avg_high_price', 'avg_low_price',
               'high_price_volume', 'low_price_volume', 'inverted_spread']
    if not set(columns + ['resolution_seconds']) <= set(schema.names):
        raise ValueError('Daily history requires an assembled availability panel')
    negative = ' OR '.join(f'{col}<0' for col in FIELDS if col != 'ingested_at')
    ambiguous = 'resolution_ambiguous' if 'resolution_ambiguous' in schema.names else 'false'
    with tempfile.TemporaryDirectory(prefix='osrs-forward-history-') as temporary:
        with duckdb.connect(config={'memory_limit': '32MB', 'threads': 1,
                                    'preserve_insertion_order': False,
                                    'temp_directory': temporary}) as connection:
            connection.read_parquet(str(path)).create_view('history')
            bad = connection.execute(f"""SELECT
                bool_or(item_id IS NULL OR timestamp IS NULL OR high_price_volume IS NULL
                        OR low_price_volume IS NULL),
                bool_or({negative}),
                bool_or(avg_high_price=0 OR avg_low_price=0),
                bool_or(source_interval_seconds<=0),
                bool_or(resolution_seconds IS NULL OR resolution_seconds<>86400 OR {ambiguous}),
                bool_or(available_at IS NULL OR available_at < timestamp +
                        coalesce(source_interval_seconds,resolution_seconds))
                FROM history""").fetchone()
            errors = ['NULL keys/volumes', 'Negative source data', 'Zero price',
                      'Nonpositive source interval', 'Select one strict daily resolution panel',
                      'Availability precedes bucket completion']
            for invalid, error in zip(bad, errors, strict=True):
                if invalid:
                    raise ValueError(error)
            duplicate, overlap = connection.execute("""SELECT
                bool_or(timestamp=previous), bool_or(timestamp<previous_end) FROM (
                    SELECT timestamp,
                        lag(timestamp) OVER w AS previous,
                        lag(timestamp+coalesce(source_interval_seconds,resolution_seconds))
                            OVER w AS previous_end
                    FROM history WINDOW w AS (PARTITION BY item_id ORDER BY timestamp))""").fetchone()
            if duplicate or overlap:
                raise ValueError('Duplicate observations or overlapping source buckets')
            # Project before the window sort: spill narrow keys/prices, not string metadata.
            return connection.execute(f"""SELECT {','.join(columns)} FROM history
                WHERE available_at<=? QUALIFY row_number() OVER (
                    PARTITION BY item_id ORDER BY available_at DESC,timestamp DESC)<=?
                ORDER BY item_id,available_at,timestamp""", [now, lookback]).to_arrow_table().to_pandas(
                    types_mapper=pd.ArrowDtype)
