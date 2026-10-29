import json
from pathlib import Path

import pandas as pd
import pytest
from osrs_ml.weekly_ingest import (
    FIELDS,
    SOURCE,
    WEEK,
    Archive,
    assemble,
    development_rows,
    external_directory,
)


def record(points):
    return dict(status="ok", source=SOURCE, schema_version=1,
                source_url="https://www.ge-tracker.com/api/graph/2/all",
                fetched_at="2026-10-29T00:00:00Z", payload=dict(source="runelite", data=points))


def point(ts=0):
    return dict(ts=ts * 1000, **dict.fromkeys(FIELDS, 100))


def test_requires_ack_and_external_resolved_path(tmp_path, monkeypatch):
    monkeypatch.setenv("OSRS_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="acknowledge"):
        external_directory(tmp_path / "archive", False)
    assert external_directory(tmp_path / "archive", True).is_dir()
    with pytest.raises(ValueError, match="outside"):
        external_directory(Path(__file__).parents[1] / "data/ge-tracker", True)
    (tmp_path / "link").symlink_to(Path(__file__).parents[1], target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        external_directory(tmp_path / "link", True)


def test_sealed_dates_are_filtered_before_reading_values_and_provenance_is_retained():
    sealed = dict(ts=WEEK * 1000, overallPrice="MUST NOT INSPECT")
    rows = development_rows(record([point(), sealed]), 2, WEEK + 301)
    assert len(rows) == 1
    assert rows[0]["source"] == SOURCE
    assert rows[0]["fetched_at"] == "2026-10-29T00:00:00Z"
    assert rows[0]["available_at"] < WEEK + 301
    with pytest.raises(ValueError, match="Duplicate"):
        development_rows(record([point(), point()]), 2, WEEK * 3)
    bad = point()
    bad["sellingCompleted"] = -1
    with pytest.raises(ValueError, match="negative"):
        development_rows(record([bad]), 2, WEEK * 3)


def test_coverage_preserves_sparse_empty_error_and_pending(tmp_path):
    (tmp_path / "graph-2.json").write_text(json.dumps(record([point(), point(3 * WEEK)])))
    (tmp_path / "graph-3.json").write_text(json.dumps(record([])))
    (tmp_path / "graph-4.json").write_text(json.dumps(dict(status="error", error="HTTP 404")))
    n, coverage = assemble(tmp_path, [2, 3, 4, 5], 10 * WEEK)
    assert n == 2
    assert [r["rows"] for r in coverage] == [2, 0, 0, 0]
    assert coverage[0]["gaps_over_8_days"] == 1
    assert coverage[-1]["status"] == "pending"
    assert set(pd.read_parquet(tmp_path / "weekly.parquet").source) == {SOURCE}


def test_cached_resume_never_requests_and_persistent_denial_stops(tmp_path, monkeypatch):
    import urllib.request

    def forbidden(*a, **k):
        pytest.fail("Cache hit made a network request")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    cached = record([])
    (tmp_path / "cached.json").write_text(json.dumps(cached))
    archive = Archive(tmp_path)
    assert archive.fetch("cached", cached["source_url"]) == cached
    cached.update(status="error", error="HTTP 429")
    (tmp_path / "cached.json").write_text(json.dumps(cached))
    with pytest.raises(RuntimeError, match="refusal"):
        archive.fetch("cached", cached["source_url"])
    with pytest.raises(ValueError, match="at least"):
        Archive(tmp_path, interval=1)


def test_polite_rate_limit_across_restart_and_http_refusal(tmp_path, monkeypatch):
    import urllib.error

    from osrs_ml import weekly_ingest as module

    times = iter([100.5, 102.0])
    sleeps = []
    monkeypatch.setattr(module.time, "time", lambda: next(times))
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    (tmp_path.parent / ".ge-tracker-last-request.json").write_text('{"unix":100}')

    def denied(*a, **k):
        raise urllib.error.HTTPError("https://example.org", 403, "denied", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", denied)
    with pytest.raises(RuntimeError, match="stop"):
        Archive(tmp_path).fetch("new", "https://example.org")
    assert sleeps == [1.5]
    assert json.loads((tmp_path / "new.json").read_text())["error"] == "HTTP 403"
