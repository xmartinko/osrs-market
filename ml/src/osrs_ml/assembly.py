"""Versioned, conservative resolution qualification for the lossy C++ export.

Timestamp phase is evidence, never recovered source metadata. Midnight candidates
in the mixed tail are retained separately, but excluded from the strict panel.
"""

import json
import os
from pathlib import Path

import duckdb
import pandas as pd

from .data import manifest, sha256

ASSEMBLY_VERSION = 3
DAY = 86_400


def data_dir() -> Path:
    return Path(os.environ.get("OSRS_DATA_DIR", "/home/martin/osrs-data"))


def assemble(root: Path | None = None, output: Path | None = None) -> dict:
    root = root or data_dir()
    output = output or root / "assembled-v3"
    output.mkdir(parents=True, exist_ok=False)
    prices, items = root / "prices.parquet", root / "items.parquet"
    export = json.loads((root / "EXPORT_METADATA.json").read_text())
    fetched = int(pd.Timestamp(export["generated_at_utc"]).timestamp())
    with duckdb.connect() as db:
        db.read_parquet(str(prices)).create_view("raw")
        db.read_parquet(str(items)).create_view("mapping")
        # Global starts deliberately avoid using an item's eventual survival/coverage.
        hourly_start, fine_start = db.execute("""
            SELECT min(ts) FILTER(WHERE ts % 86400 != 0),
                   min(ts) FILTER(WHERE ts % 3600 != 0) FROM raw
        """).fetchone()
        if db.execute("SELECT count(*) != count(DISTINCT id) FROM mapping").fetchone()[0]:
            raise ValueError("Duplicate mapping IDs")
        db.execute(
            """CREATE TABLE qualified AS
            SELECT r.* EXCLUDE(ts, name, members, buy_limit, item_id),
                   r.item_id::BIGINT AS item_id, ts::BIGINT AS timestamp,
                   r.buy_limit::BIGINT AS buy_limit_current,
                   m.name AS current_name, m.members AS current_members,
                   m.low_alch AS current_low_alch, m.high_alch AS current_high_alch,
                   m.value AS current_value,
                   'wiki' AS source, 'cpp_export' AS source_dataset,
                   ?::BIGINT AS fetched_at, NULL::BIGINT AS ingested_at,
                   'current_revision_not_point_in_time' AS metadata_status,
                   (avg_low_price > avg_high_price) IS TRUE AS inverted_spread,
                   ts - lag(ts) OVER(PARTITION BY item_id ORDER BY ts) AS observed_gap_seconds
            FROM raw r LEFT JOIN mapping m ON r.item_id=m.id
        """,
            [fetched],
        )
        # Never resample overlapping bucket volumes by summing them.
        specs = {
            "daily_candidates": ("timestamp % 86400 = 0", DAY),
            "daily": (f"timestamp % 86400 = 0 AND timestamp < {hourly_start or 2**62}", DAY),
            "intraday_1h": (
                f"timestamp >= {hourly_start or 2**62} AND timestamp < {fine_start or 2**62} "
                "AND timestamp % 3600 = 0 AND timestamp % 86400 != 0",
                3600,
            ),
            "intraday_5m": (
                f"timestamp >= {fine_start or 2**62} AND timestamp % 300 = 0 "
                "AND timestamp % 3600 != 0",
                300,
            ),
        }
        panels = {}
        for name, (condition, seconds) in specs.items():
            db.execute(f"""CREATE OR REPLACE VIEW panel AS
                SELECT *, {seconds}::BIGINT AS resolution_seconds,
                    NULL::BIGINT AS source_interval_seconds,
                    TRUE AS interval_unknown, 'timestamp_phase_inference' AS resolution_basis,
                    timestamp + {seconds} + 300 AS available_at,
                    timestamp >= {hourly_start or 2**62} AND timestamp % 86400=0
                        AS resolution_ambiguous,
                    NULL::BIGINT AS buy_limit,
                    CASE WHEN high_price_volume>0 AND avg_high_price IS NOT NULL THEN 300 END
                        AS high_freshness_seconds,
                    CASE WHEN low_price_volume>0 AND avg_low_price IS NOT NULL THEN 300 END
                        AS low_freshness_seconds
                FROM qualified WHERE {condition} ORDER BY item_id, timestamp
            """)
            # SQL/Arrow keep nullable integers exact and avoid a huge object dataframe.
            path = output / f"{name}.parquet"
            db.execute("COPY panel TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(path)])
            db.execute(f"""CREATE OR REPLACE VIEW coverage AS
                SELECT item_id, count(*) AS rows, min(timestamp) AS first,
                    max(timestamp) AS last, count(avg_high_price) AS valid_high_rows,
                    count(avg_low_price) AS valid_low_rows, sum(inverted_spread::INT) AS inverted,
                    count(*) FILTER(WHERE avg_high_price IS NOT NULL
                        AND avg_low_price IS NOT NULL AND NOT inverted_spread) AS usable_rows,
                    count(DISTINCT timestamp // {DAY}) AS days_covered,
                    (max(timestamp)-min(timestamp)) // {seconds} + 1 AS span_expected_buckets,
                    span_expected_buckets - count(*) AS missing_buckets
                FROM panel GROUP BY item_id""")
            db.execute(
                "COPY coverage TO ? (FORMAT PARQUET)", [str(output / f"{name}_coverage.parquet")]
            )
            stats = db.execute("""SELECT count(*), count(DISTINCT item_id),
                count(DISTINCT timestamp // 86400),
                count(*) FILTER(WHERE avg_high_price IS NOT NULL AND avg_low_price IS NOT NULL
                    AND NOT inverted_spread), coalesce(sum(inverted_spread::INT),0),
                min(timestamp), max(timestamp),
                avg((avg_high_price IS NULL)::INT), avg((avg_low_price IS NULL)::INT),
                avg((mid_price IS NULL)::INT), avg((buy_limit_current IS NULL)::INT)
                FROM panel""").fetchone()
            cov = db.execute("""SELECT count(*) FILTER(WHERE days_covered>=300),
                count(*) FILTER(WHERE usable_rows>=300), coalesce(sum(missing_buckets),0)
                FROM coverage""").fetchone()
            info = manifest(
                path,
                source="wiki",
                rows=stats[0],
                assembly_version=ASSEMBLY_VERSION,
                panel=name,
                resolution_seconds=seconds,
                interval_status="inferred, not recovered",
                availability_delay_seconds=300,
            )
            panels[name] = dict(
                zip(
                    [
                        "rows",
                        "items",
                        "days",
                        "usable_rows",
                        "inverted_spreads",
                        "min_timestamp",
                        "max_timestamp",
                    ],
                    stats[:7],
                    strict=True,
                )
            )
            panels[name].update(
                dict(
                    zip(
                        [
                            "items_ge_300_days",
                            "items_ge_300_usable_rows",
                            "missing_buckets_within_lifetimes",
                        ],
                        cov,
                        strict=True,
                    )
                )
            )
            panels[name]["null_rates"] = dict(
                zip(
                    ["avg_high_price", "avg_low_price", "mid_price", "buy_limit"],
                    stats[7:],
                    strict=True,
                )
            )
            panels[name]["sha256"] = info["sha256"]
        nulls = db.execute("""SELECT
            avg((avg_high_price IS NULL)::INT), avg((avg_low_price IS NULL)::INT),
            avg((mid_price IS NULL)::INT), avg((buy_limit_current IS NULL)::INT)
            FROM qualified""").fetchone()
        gaps = db.execute("""SELECT observed_gap_seconds, count(*) AS rows FROM qualified
            WHERE observed_gap_seconds IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchdf()
        gaps.to_csv(output / "gap_counts.csv", index=False)
        report = {
            "assembly_version": ASSEMBLY_VERSION,
            "export_metadata": export,
            "source_sha256": sha256(prices),
            "items_sha256": sha256(items),
            "export_metadata_sha256": sha256(root / "EXPORT_METADATA.json"),
            "hourly_start": hourly_start,
            "fine_start": fine_start,
            "null_rates": dict(
                zip(
                    ["avg_high_price", "avg_low_price", "mid_price", "buy_limit"],
                    nulls,
                    strict=True,
                )
            ),
            "jitter_gaps": int(
                gaps.loc[~gaps.observed_gap_seconds.isin([300, 3600, DAY]), "rows"].sum()
            ),
            "panels": panels,
            "limitations": [
                "Daily candidates are midnight observations, not verified daily source buckets.",
                "Strict daily excludes the mixed tail; hourly excludes midnight; 5m excludes hourly boundaries.",
                "Gaps are missing, never forward-filled; excluded boundary volumes are not reconstructed.",
                "Source resolution/last trade time and historical metadata were lost upstream.",
                "available_at assumes bucket start plus inferred duration plus 300s publication delay.",
                "Current item attributes are audit columns only; historical buy_limit remains NULL.",
                "Rows with inverted spreads remain flagged, never tradable or labelled as alpha.",
            ],
        }
    (output / "quality.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def union_observations(paths: list[Path], *, wiki_only: bool = True) -> pd.DataFrame:
    """Union canonical archives without erasing source, resolution or fetch time.

    This is an audit union. Evaluation must select ONE resolution, and deduplicate
    repeated fetches point-in-time, rather than spending the same volume twice.
    """
    frames = [pd.read_parquet(path) for path in paths]
    result = pd.concat(frames, ignore_index=True, sort=False)
    required = {"source", "timestamp", "item_id", "resolution_seconds", "fetched_at"}
    if not required.issubset(result):
        raise ValueError("Canonical provenance/resolution columns required")
    return result[result.source == "wiki"].copy() if wiki_only else result
