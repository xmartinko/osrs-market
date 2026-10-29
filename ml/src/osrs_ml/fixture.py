"""Deliberately synthetic periodic dynamics; not evidence of an OSRS market edge."""

import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .data import REGIME_BREAK, SCHEMA, manifest


def write_fixture(path: Path) -> dict:
    if path.exists():
        raise FileExistsError(path)
    rows = []
    start = REGIME_BREAK - 4 * 86400
    for item in range(1, 7):
        base = [0, 1000, 10_000, 150_000, 2_000_000, 3_200_000_000, 75][item]
        for step in range(8 * 288):
            if item == 4 and step % 19 == 0:  # Irregular intervals/gaps.
                continue
            timestamp = start + step * 300
            wave = 0.05 * math.sin(step / 18 + item) + 0.008 * math.sin(step / 4 + item)
            mid = int(base * (1 + wave))
            stale = item == 3 and step % 40 < 9
            volume = 0 if stale else 500 + (step * 13 + item * 37) % 600
            rows.append(
                dict(
                    item_id=item,
                    timestamp=timestamp,
                    avg_high_price=mid + max(1, mid // 400),
                    avg_low_price=mid - max(1, mid // 400),
                    high_price_volume=volume,
                    low_price_volume=volume // 2,
                    buy_limit=100 if item == 5 else 2000,
                    source_interval_seconds=300,
                    ingested_at=timestamp + 300,
                )
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), path)
    return manifest(
        path,
        source="synthetic",
        rows=len(rows),
        seed=0,
        warning="Periodic deterministic fixture; no financial inference",
    )
