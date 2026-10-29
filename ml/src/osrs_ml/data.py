"""Read existing tables only. Missing source metadata stays missing."""

import hashlib
import json
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
    if intervals.isna().any() and not allow_unknown_metadata:
        raise ValueError("Unknown source intervals; explicit --allow-unknown-metadata required")
    frame["available_at"] = frame.timestamp + intervals.fillna(unknown_interval_seconds)
    frame["interval_unknown"] = intervals.isna()
    frame["observed_gap_seconds"] = frame.groupby("item_id").timestamp.diff()
    previous_end = (frame.timestamp + intervals).groupby(frame.item_id).shift(1)
    if (frame.timestamp < previous_end).any():
        raise ValueError("Overlapping source buckets; qualify resolutions before evaluation")
    frame = frame.sort_values(["item_id", "available_at", "timestamp"]).reset_index(drop=True)
    for side in ("high", "low"):
        traded = (frame[f"{side}_price_volume"] > 0) & frame[f"avg_{side}_price"].notna()
        last_bucket = frame.available_at.where(traded).groupby(frame.item_id).ffill()
        frame[f"{side}_freshness_seconds"] = frame.available_at - last_bucket
    frame["regime"] = frame.timestamp.map(
        lambda t: "pre_2026_09_30" if t < REGIME_BREAK else "post_2026_09_30"
    )
    return frame
