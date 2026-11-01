"""Synthetic source-contract checks; no archive or holdout rows required."""

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from osrs_ml.probabilistic_data import (
    HOLDOUT_START,
    build_panel,
    source_files,
)

START = 1730160000


def write_source(root, rows):
    path = root / "prices_5m/year=2024/month=10/data.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema(
        [
            ("ts", pa.int64()),
            ("timestamp", pa.int32()),
            ("item_id", pa.int64()),
            ("avg_high_price", pa.float64()),
            ("avg_low_price", pa.float64()),
            ("high_price_volume", pa.int64()),
            ("low_price_volume", pa.int64()),
            ("source", pa.string()),
            ("economy", pa.string()),
        ]
    )
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    path.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "source": "kaggle-5m",
                "economy": "main",
                "timestamp_scale": 300,
                "item_filter": "listed",
                "endpoint": "test?datasetVersionNumber=1",
                "sha256": "declared-only-test-hash",
            }
        )
    )
    return path


def source_rows(items=(1,), hours=4):
    return [
        dict(
            ts=START + step * 300,
            timestamp=(START + step * 300) // 300,
            item_id=item,
            avg_high_price=100.0,
            avg_low_price=90.0,
            high_price_volume=1,
            low_price_volume=1,
            source="kaggle-5m",
            economy="main",
        )
        for item in items
        for step in range(hours * 12)
    ]


def run_build(tmp_path, rows, **kwargs):
    root = tmp_path / "immutable"
    source = write_source(root, rows)
    before = source.read_bytes()
    output = tmp_path / "derived/panel.parquet"
    result = build_panel(
        root,
        output,
        start=START,
        selection_end=START + 2 * 3600,
        end=START + 4 * 3600,
        memory_limit="128MB",
        threads=1,
        **kwargs,
    )
    assert source.read_bytes() == before
    return pq.read_table(output).to_pylist(), result, output


def test_weighted_sides_availability_and_manifest(tmp_path):
    rows = source_rows()
    rows[0].update(avg_high_price=200.0, high_price_volume=11)
    rows[0].update(avg_low_price=50.0, low_price_volume=3)
    panel, manifest, output = run_build(tmp_path, rows)
    assert panel[0]["avg_high_price"] == pytest.approx(150.0)
    assert panel[0]["avg_low_price"] == pytest.approx((50 * 3 + 90 * 11) / 14)
    assert panel[0]["high_price_volume"] == 22
    assert panel[0]["available_at"] == START + 3600 + 300
    assert panel[0]["usable"] is True
    assert manifest["selected_ids"] == [1]
    assert manifest["source_files"][0]["payload_hash_verified"] is False
    assert len(manifest["source_files"][0]["footer_sha256"]) == 64
    assert len(manifest["sha256"]) == 64
    assert output.with_suffix(".manifest.json").exists()


def test_duplicate_is_rejected_without_publishing(tmp_path):
    rows = source_rows()
    root = tmp_path / "immutable"
    write_source(root, rows + [rows[0]])
    output = tmp_path / "derived/panel.parquet"
    with pytest.raises(ValueError, match="Duplicate"):
        build_panel(
            root, output, start=START, selection_end=START + 7200, end=START + 14400, threads=1
        )
    assert not output.exists()


def test_missing_zero_volume_and_null_are_distinct(tmp_path):
    rows = source_rows()
    for row in rows[24:36]:
        row.update(high_price_volume=0, avg_high_price=0.0)
    rows[-1]["low_price_volume"] = None
    panel, _, _ = run_build(tmp_path, rows)
    assert panel[2]["high_price_volume"] == 0
    assert panel[2]["avg_high_price"] is None
    assert not panel[2]["usable"]
    assert panel[3]["low_price_volume"] is None
    assert not panel[3]["usable"]


def test_incomplete_and_absent_hours_are_dense_unusable(tmp_path):
    rows = source_rows()[:35]  # Two complete selection hours; one short, one absent.
    panel, _, _ = run_build(tmp_path, rows)
    assert len(panel) == 4
    assert panel[2]["high_price_volume"] is None
    assert panel[3]["avg_high_price"] is None
    assert not panel[2]["usable"] and not panel[3]["usable"]


@pytest.mark.parametrize(
    "change",
    [
        {"timestamp": 0},
        {"source": "wiki-v2"},
        {"economy": "seasonal"},
        {"high_price_volume": -1},
    ],
)
def test_provenance_and_raw_timestamp_identity_fail_closed(tmp_path, change):
    rows = source_rows()
    rows[0].update(change)
    with pytest.raises(ValueError, match="identity/timestamps/negative"):
        run_build(tmp_path, rows)


def test_selection_cannot_use_future_liquidity_or_coverage(tmp_path):
    rows = source_rows(items=(1, 2))
    for row in rows:
        if row["item_id"] == 2 and row["ts"] < START + 7200:
            row["avg_low_price"] = None
        if row["item_id"] == 2 and row["ts"] >= START + 7200:
            row["high_price_volume"] = 1000000
    _, manifest, _ = run_build(tmp_path, rows)
    assert manifest["selected_ids"] == [1]


def test_inverted_hour_is_unusable_and_cannot_establish_selection_coverage(tmp_path):
    rows = source_rows(items=(1, 2))
    for row in rows:
        if (row["item_id"] == 2 and row["ts"] < START + 7200) or (
            row["item_id"] == 1 and START + 7200 <= row["ts"] < START + 10800
        ):
            row["avg_high_price"] = 80.0  # Inverted against low = 90.
    panel, manifest, _ = run_build(tmp_path, rows)
    assert manifest["selected_ids"] == [1]
    assert panel[2]["avg_high_price"] == 80.0  # Preserve observation, mask the label.
    assert panel[2]["avg_low_price"] == 90.0
    assert panel[2]["usable"] is False
    assert manifest["quality"]["inverted_side_hours"] == 1


def test_holdout_and_source_output_guards_precede_io(tmp_path):
    with pytest.raises(ValueError, match="before holdout"):
        build_panel(tmp_path / "absent", tmp_path / "p.parquet", end=HOLDOUT_START + 1)
    root = tmp_path / "source"
    with pytest.raises(ValueError, match="immutable"):
        build_panel(root, root / "bad.parquet")


def test_paths_pruned_and_sql_window_ignores_later_same_month(tmp_path):
    rows = source_rows()
    later = rows[0].copy()
    later["ts"] = START + 5 * 3600
    later["timestamp"] = later["ts"] // 300
    # A deliberately invalid later row must not be admitted to the scan scope.
    later["source"] = "outside-window"
    panel, _, _ = run_build(tmp_path, rows + [later])
    assert max(row["ts"] for row in panel) == START + 3 * 3600
    root = tmp_path / "immutable"
    future = root / "prices_5m/year=2026/month=09/data.parquet"
    future.parent.mkdir(parents=True)
    future.write_bytes(b"not parquet; must never open")
    assert source_files(root, START, START + 14400) == [
        root.resolve() / "prices_5m/year=2024/month=10/data.parquet"
    ]
