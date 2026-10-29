import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from osrs_ml.assembly import DAY, assemble, union_observations
from osrs_ml.data import load_snapshot


def test_strict_panels_preserve_nulls_provenance_and_exclude_mixed_tail(tmp_path):
    times = [DAY, DAY * 2, DAY * 3, DAY * 3 + 3600, DAY * 4, DAY * 4 + 300]
    pd.DataFrame(
        [
            dict(
                item_id=1,
                ts=t,
                name="old",
                members=True,
                buy_limit=100,
                avg_high_price=100 if i != 1 else None,
                avg_low_price=110 if i == 0 else 90,
                high_price_volume=10,
                low_price_volume=20,
                mid_price=95,
                total_volume=30,
            )
            for i, t in enumerate(times)
        ]
    ).astype({"avg_high_price": "Int64"}).to_parquet(tmp_path / "prices.parquet")
    pd.DataFrame(
        [dict(id=1, name="now", members=True, low_alch=1, high_alch=2, value=3)]
    ).to_parquet(tmp_path / "items.parquet")
    (tmp_path / "EXPORT_METADATA.json").write_text(
        json.dumps({"generated_at_utc": "2026-10-29T00:00:00Z"})
    )
    out = tmp_path / "panels"
    report = assemble(tmp_path, out)
    assert report["panels"]["daily"]["rows"] == 3
    assert report["panels"]["daily"]["inverted_spreads"] == 1
    assert report["panels"]["daily"]["usable_rows"] == 1
    # Nullable integer prices and IDs stay exact.
    assert pq.read_schema(out / "daily.parquet").field("item_id").type == pa.int64()
    frame = load_snapshot(out / "daily.parquet", allow_unknown_metadata=True)
    assert frame.source_interval_seconds.isna().all()
    assert frame.buy_limit.isna().all()
    assert frame.buy_limit_current.eq(100).all()
    assert frame.avg_high_price.isna().sum() == 1
    assert frame.available_at.eq(frame.timestamp + DAY + 300).all()
    assert frame.interval_unknown.all()
    with pytest.raises(ValueError, match="Unknown source intervals"):
        load_snapshot(out / "daily.parquet")
    with pytest.raises(ValueError, match="unambiguous"):
        load_snapshot(out / "daily_candidates.parquet", allow_unknown_metadata=True)
    assert len(union_observations([out / "daily.parquet"])) == 3
    with pytest.raises(FileExistsError):
        assemble(tmp_path, out)
