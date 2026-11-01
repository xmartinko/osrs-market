"""Read-only canonical mirror -> qualified development-only hourly panel.

No acquisition, source rewrites, guide-price mixing, or holdout observations.
Run with ``python -m osrs_ml.probabilistic_data --help``.
"""

import argparse
import hashlib
import json
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

HOLDOUT_START = 1785024300
DEFAULT_START = 1730160000  # 2024-10-29 00:00 UTC
DEFAULT_SELECTION_END = 1761696000  # 2025-10-29 00:00 UTC
DEFAULT_END = 1785024000  # 2026-07-26 00:00 UTC (exclusive)
SOURCE_VERSION = "kaggle-5m/datasetVersionNumber=1/canonical-v2/main"
REQUIRED = {
    "ts",
    "timestamp",
    "item_id",
    "avg_high_price",
    "avg_low_price",
    "high_price_volume",
    "low_price_volume",
    "source",
    "economy",
}


def _hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _footer_hash(path):
    """Fingerprint footer bytes only; does NOT verify the full payload hash."""
    with path.open("rb") as stream:
        stream.seek(-8, 2)
        tail = stream.read(8)
        if tail[4:] != b"PAR1":
            raise ValueError(f"Invalid Parquet trailer: {path}")
        length = struct.unpack("<I", tail[:4])[0]
        if length + 8 > path.stat().st_size:
            raise ValueError("Invalid footer length")
        stream.seek(-length - 8, 2)
        return hashlib.sha256(stream.read(length + 8)).hexdigest()


def source_files(root, start, end):
    """Enumerate month paths BEFORE opening Parquet, never glob future months."""
    root = Path(root).resolve()
    first = datetime.fromtimestamp(start, timezone.utc)
    last = datetime.fromtimestamp(end - 1, timezone.utc)
    year, month = first.year, first.month
    files = []
    while (year, month) <= (last.year, last.month):
        path = root / "prices_5m" / f"year={year}" / f"month={month:02d}" / "data.parquet"
        if path.exists():
            if not path.resolve().is_relative_to(root):
                raise ValueError("Source symlink escapes qualified root")
            files.append(path)
        month += 1
        if month == 13:
            year, month = year + 1, 1
    if not files:
        raise ValueError("No eligible source month partitions")
    return files


def _inventory(files):
    result = []
    for path in files:
        sidecar = path.with_suffix(".manifest.json")
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        expected = {
            "source": "kaggle-5m",
            "economy": "main",
            "timestamp_scale": 300,
            "item_filter": "listed",
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Unqualified source provenance: {path}")
        if "datasetVersionNumber=1" not in metadata.get("endpoint", ""):
            raise ValueError("Unverified source version")
        parquet = pq.ParquetFile(path)
        schema = parquet.schema_arrow
        if not REQUIRED <= set(schema.names):
            raise ValueError(f"Missing source fields: {path}")
        for column in ("ts", "item_id", "high_price_volume", "low_price_volume"):
            if str(schema.field(column).type) != "int64":
                raise ValueError(f"Expected int64 field {column}")
        result.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "rows_footer": parquet.metadata.num_rows,
                "schema": str(schema),
                "schema_sha256": hashlib.sha256(str(schema).encode()).hexdigest(),
                "footer_sha256": _footer_hash(path),
                "sidecar_sha256": _hash_file(sidecar),
                "declared_payload_sha256": metadata.get("sha256"),
                "payload_hash_verified": False,
            }
        )
    return result


def _raw_view(db, files, start, end, selected=False):
    # Explicit file list plus independent SQL guard: no recursive wildcard scan.
    db.read_parquet([str(path) for path in files], hive_partitioning=False).create_view(
        "source_rows", replace=True
    )
    selected_sql = "AND item_id IN (SELECT item_id FROM selected)" if selected else ""
    db.execute(f"""CREATE OR REPLACE TEMP VIEW raw AS SELECT * FROM source_rows
        WHERE ts >= {int(start)} AND ts < {int(end)} AND ts < {HOLDOUT_START}
        {selected_sql}""")
    row = db.execute("""SELECT count(*), count(*) FILTER (WHERE
        item_id IS NULL OR item_id <= 0 OR ts % 300 <> 0
        OR timestamp IS NULL OR ts <> timestamp::BIGINT * 300
        OR source IS DISTINCT FROM 'kaggle-5m' OR economy IS DISTINCT FROM 'main'
        OR high_price_volume < 0 OR low_price_volume < 0) FROM raw""").fetchone()
    if not row[0] or row[1]:
        raise ValueError("Empty scope or invalid source identity/timestamps/negative volumes")
    duplicate = db.execute("""SELECT item_id, ts FROM raw GROUP BY item_id, ts
        HAVING count(*) > 1 LIMIT 1""").fetchone()
    if duplicate:
        raise ValueError(f"Duplicate source keys; refusing overlap: {duplicate}")
    return row[0]


def _hourly_sql():
    expressions = []
    for side in ("high", "low"):
        price, volume = f"avg_{side}_price", f"{side}_price_volume"
        complete = f"count(*) = 12 AND count({volume}) = 12"
        valid = f"isfinite({price}) AND {price} > 0"
        expressions.extend(
            [
                f"CASE WHEN {complete} THEN sum({volume})::BIGINT END AS {volume}",
                f"CASE WHEN {complete} AND sum({volume}) > 0 AND "
                f"count(*) FILTER (WHERE {volume} > 0 AND NOT coalesce({valid}, false)) = 0 "
                f"THEN sum(CASE WHEN {volume}>0 THEN {price}*{volume} ELSE 0 END) "
                f"/sum({volume}) END AS {price}",
            ]
        )
    return (
        """SELECT (ts // 3600) * 3600 AS ts, item_id, count(*) AS source_rows,
        """
        + ", ".join(expressions)
        + " FROM raw GROUP BY 1, 2"
    )


def build_panel(
    source_root,
    output,
    *,
    start=DEFAULT_START,
    end=DEFAULT_END,
    selection_end=DEFAULT_SELECTION_END,
    max_items=100,
    min_coverage=0.95,
    delay_seconds=300,
    memory_limit="1GB",
    threads=2,
):
    """Select on the first training year; stream qualified selected-item hours.

    Missing subintervals => unknown hourly volume and unusable hour. Complete
    observed zero-volume sides retain zero volume and NULL price. No filling.
    """
    if not (0 < start < selection_end < end <= HOLDOUT_START):
        raise ValueError("Require ordered development windows before holdout")
    if any(value % 3600 for value in (start, selection_end, end)):
        raise ValueError("Windows must align to UTC hours")
    if not (1 <= max_items <= 100 and 0 < min_coverage <= 1 and delay_seconds >= 0):
        raise ValueError("Invalid item/coverage/delay settings")
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    if output.is_relative_to(source_root):
        raise ValueError("Output must be outside immutable source root")
    manifest_path = output.with_suffix(".manifest.json")
    if output.exists() or manifest_path.exists():
        raise FileExistsError(output)
    files = source_files(source_root, start, end)
    inventory = _inventory(files)
    initial_files = source_files(source_root, start, selection_end)
    output.parent.mkdir(parents=True, exist_ok=True)
    expected_hours = (selection_end - start) // 3600
    with tempfile.TemporaryDirectory(prefix="panel-build-", dir=output.parent) as temporary:
        temporary = Path(temporary)
        with duckdb.connect(
            config={
                "memory_limit": memory_limit,
                "threads": threads,
                "temp_directory": str(temporary),
                "preserve_insertion_order": False,
            }
        ) as db:
            selection_rows = _raw_view(db, initial_files, start, selection_end)
            # Aggregate inside DuckDB; never materialize source rows in Python.
            db.execute("CREATE TEMP TABLE selection_hours AS " + _hourly_sql())
            candidates = db.execute(
                """SELECT item_id,
                count(*) FILTER (WHERE avg_high_price > 0 AND avg_low_price > 0
                    AND avg_high_price >= avg_low_price)::DOUBLE
                    / ? AS coverage,
                coalesce(sum(high_price_volume + low_price_volume), 0)::DOUBLE AS volume
                FROM selection_hours GROUP BY item_id
                HAVING coverage >= ? ORDER BY volume DESC, item_id""",
                [expected_hours, min_coverage],
            ).fetchall()
            if not candidates:
                raise ValueError("No items meet frozen training coverage threshold")
            # Equal allocations across training-only volume terciles, deterministic ties.
            strata = [[], [], []]
            for rank, row in enumerate(candidates):
                strata[min(2, rank * 3 // len(candidates))].append(row)
            selected = []
            for offset in range(len(candidates)):
                for index, group in enumerate(strata):
                    if offset < len(group) and len(selected) < max_items:
                        item_id, coverage, volume = group[offset]
                        selected.append(
                            {
                                "item_id": item_id,
                                "coverage": coverage,
                                "observed_volume": volume,
                                "liquidity_stratum": ["high", "medium", "low"][index],
                            }
                        )
            db.execute("DROP TABLE selection_hours")
            db.execute("CREATE TEMP TABLE selected(item_id BIGINT)")
            db.executemany(
                "INSERT INTO selected VALUES (?)", [(row["item_id"],) for row in selected]
            )
            selected_rows = _raw_view(db, files, start, end, selected=True)
            db.execute("CREATE TEMP TABLE hours AS " + _hourly_sql())
            db.execute(f"""CREATE TEMP VIEW panel AS SELECT grid.ts::BIGINT AS ts,
                selected.item_id, h.avg_high_price, h.avg_low_price,
                h.high_price_volume, h.low_price_volume,
                (h.avg_high_price + h.avg_low_price)/2 AS mid_price,
                (grid.ts + 3600 + {int(delay_seconds)})::BIGINT AS available_at,
                coalesce(h.avg_high_price > 0 AND h.avg_low_price > 0
                         AND h.avg_high_price >= h.avg_low_price, false) AS usable
                FROM range({start}, {end}, 3600) AS grid(ts) CROSS JOIN selected
                LEFT JOIN hours h ON h.ts = grid.ts AND h.item_id = selected.item_id""")
            quality_row = db.execute("""SELECT count(*), count(*) FILTER (WHERE usable),
                count(*) FILTER (WHERE high_price_volume IS NULL),
                count(*) FILTER (WHERE low_price_volume IS NULL),
                count(*) FILTER (WHERE high_price_volume = 0),
                count(*) FILTER (WHERE low_price_volume = 0),
                count(*) FILTER (WHERE avg_high_price < avg_low_price), min(ts), max(ts)
                FROM panel""").fetchone()
            pending = temporary / "panel.parquet"
            db.execute(
                "COPY (SELECT * FROM panel ORDER BY item_id, ts) TO ? "
                "(FORMAT PARQUET, COMPRESSION ZSTD)",
                [str(pending)],
            )
        result = {
            "schema_version": 1,
            "source_version": SOURCE_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "start": start,
            "end_exclusive": end,
            "holdout_start": HOLDOUT_START,
            "selection_start": start,
            "selection_end_exclusive": selection_end,
            "selection_min_coverage": min_coverage,
            "selected_items": selected,
            "selected_ids": [row["item_id"] for row in selected],
            "availability_delay_seconds": delay_seconds,
            "availability_status": "assumed bucket-end plus delay; not observed ingestion",
            "source_interval_seconds": 300,
            "source_interval_evidence": "sidecar timestamp_scale and raw bucket-index identity",
            "source_files": inventory,
            "selection_source_rows": selection_rows,
            "selected_development_source_rows": selected_rows,
            "schema": str(pq.read_schema(pending)),
            "sha256": _hash_file(pending),
            "quality": dict(
                zip(
                    [
                        "rows",
                        "usable_rows",
                        "unknown_high_volume_hours",
                        "unknown_low_volume_hours",
                        "zero_high_volume_hours",
                        "zero_low_volume_hours",
                        "inverted_side_hours",
                        "min_ts",
                        "max_ts",
                    ],
                    quality_row,
                    strict=True,
                )
            ),
            "gates": {
                "duplicate_keys": "passed: zero duplicates in scanned scopes",
                "development_only": True,
                "source_identity_timestamp": "passed",
                "selection_frozen_first_training": True,
                "complete_hour_required": True,
                "rights": "private research only; broad reuse unresolved",
                "as_of_timing": "assumed latency, not empirically established",
            },
            "missingness_policy": "12 distinct 300s rows required; no interpolation; "
            "unknown totals NULL; observed complete zero volume stays zero",
            "survivorship_limit": "canonical-v2/main uses current listed-item classification",
        }
        metadata_pending = temporary / "manifest.json"
        metadata_pending.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        pending.rename(output)
        metadata_pending.rename(manifest_path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-items", type=int, default=100)
    parser.add_argument("--memory-limit", default="1GB")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    result = build_panel(
        args.source_root,
        args.output,
        max_items=args.max_items,
        memory_limit=args.memory_limit,
        threads=args.threads,
    )
    print(
        json.dumps(
            {
                "rows": result["quality"]["rows"],
                "items": len(result["selected_ids"]),
                "sha256": result["sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
