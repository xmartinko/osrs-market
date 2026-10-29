import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from osrs_ml.data import EXPORT_SQL, FIELDS, SCHEMA, export_postgres, load_snapshot, manifest
from osrs_ml.fixture import write_fixture


@pytest.fixture
def snapshot(tmp_path):
    path = tmp_path / "fixture.parquet"
    write_fixture(path)
    return path


def test_int64_freshness_and_irregular_gaps(snapshot):
    frame = load_snapshot(snapshot)
    assert frame.avg_high_price.max() > 2**31
    assert frame.avg_high_price.dtype == pd.ArrowDtype(pa.int64())
    assert frame.observed_gap_seconds.max() == 600
    assert frame.source_interval_seconds.eq(300).all()
    assert frame.low_freshness_seconds.max() >= 2400
    assert len(frame.regime.unique()) == 2


def test_manifest_integrity(snapshot):
    path = snapshot.with_suffix(".manifest.json")
    metadata = json.loads(path.read_text())
    metadata["sha256"] = "wrong"
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="checksum"):
        load_snapshot(snapshot)


def test_unknown_interval_is_not_inferred_from_gaps(snapshot):
    table = pq.read_table(snapshot)
    table = table.set_column(
        SCHEMA.get_field_index("source_interval_seconds"),
        SCHEMA.field("source_interval_seconds"),
        pa.array([None] * len(table), type=pa.int64()),
    )
    pq.write_table(table, snapshot)
    manifest(snapshot, source="postgres", rows=len(table))
    with pytest.raises(ValueError, match="Unknown source intervals"):
        load_snapshot(snapshot)
    frame = load_snapshot(snapshot, allow_unknown_metadata=True)
    assert frame.source_interval_seconds.isna().all()
    assert frame.interval_unknown.all()
    assert (frame.available_at - frame.timestamp).eq(300).all()


def test_duplicate_key_rejected(snapshot):
    table = pq.read_table(snapshot)
    table = pa.concat_tables([table, table.slice(0, 1)])
    pq.write_table(table, snapshot)
    manifest(snapshot, source="synthetic", rows=len(table))
    with pytest.raises(ValueError, match="duplicate"):
        load_snapshot(snapshot)


def test_postgres_export_is_streamed_read_only_and_parameterized(tmp_path):
    row = dict.fromkeys(FIELDS, 1)
    row.update(avg_high_price=3_200_000_000, source_interval_seconds=None)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchmany.side_effect = [[row], []]
    path = tmp_path / "export.parquet"
    with patch("osrs_ml.data.psycopg.connect", return_value=connection):
        result = export_postgres("unused-secret", path, 0, 100)
    connection.execute.assert_called_once_with(
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    )
    cursor.execute.assert_called_once_with(EXPORT_SQL, (0, 100))
    assert "created_at <= to_timestamp(p.timestamp)" in EXPORT_SQL
    assert result["rows"] == 1
    assert "unused-secret" not in path.with_suffix(".manifest.json").read_text()
    assert pq.read_table(path).to_pylist()[0]["avg_high_price"] == 3_200_000_000


def test_empty_export_does_not_publish(tmp_path):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value.fetchmany.return_value = []
    path = tmp_path / "empty.parquet"
    with patch("osrs_ml.data.psycopg.connect", return_value=connection):
        with pytest.raises(ValueError, match="Empty"):
            export_postgres("unused", path, 0, 100)
    assert not path.exists()
    assert not path.with_suffix(".partial").exists()


def test_variable_returned_intervals_and_overlap_gate(tmp_path):
    rows = []
    for timestamp, interval in [(0, 300), (300, 600), (900, 300)]:
        row = dict.fromkeys(FIELDS, 1)
        row.update(timestamp=timestamp, source_interval_seconds=interval)
        rows.append(row)
    path = tmp_path / "variable.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), path)
    manifest(path, source="synthetic", rows=3)
    frame = load_snapshot(path)
    assert list(frame.available_at) == [300, 900, 1200]
    assert list(frame.source_interval_seconds) == [300, 600, 300]
    rows[1]["source_interval_seconds"] = 900
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), path)
    manifest(path, source="synthetic", rows=3)
    with pytest.raises(ValueError, match="Overlapping source buckets"):
        load_snapshot(path)
