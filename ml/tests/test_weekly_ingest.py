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


def test_cached_success_never_requests(tmp_path, monkeypatch):
    from osrs_ml import weekly_ingest as module

    def forbidden(*a, **k):
        pytest.fail("Cache hit made a network request")

    monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
    cached = record([])
    (tmp_path / "cached.json").write_text(json.dumps(cached))
    assert Archive(tmp_path).fetch("cached", cached["source_url"]) == cached
    with pytest.raises(ValueError, match="backoff"):
        Archive(tmp_path, backoff=0)


@pytest.mark.parametrize("code", [403, 429, 503])
def test_transient_failure_backoff_and_resume(tmp_path, monkeypatch, code):
    import io
    import urllib.error

    from osrs_ml import weekly_ingest as module

    calls, sleeps = [], []
    def transient(*a, **k):
        calls.append(1)
        if len(calls) <= 2:
            raise urllib.error.HTTPError("https://example.org", code, "transient", {}, None)
        return io.BytesIO(b'{"data": []}')

    monkeypatch.setattr(module.urllib.request, "urlopen", transient)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    archive = Archive(tmp_path, retries=1)
    with pytest.raises(RuntimeError, match="paused"):
        archive.fetch("new", "https://example.org")
    assert sleeps == [1.0]
    cached = json.loads((tmp_path / "new.json").read_text())
    assert cached["error"] == f"HTTP {code}"
    assert len(cached["attempts"]) == 2
    resumed = Archive(tmp_path).fetch("new", "https://example.org")
    assert resumed["status"] == "ok"
    assert len(resumed["attempts"]) == 3
    assert sleeps == [1.0]  # No inter-request delay on success or resume.


def test_connection_retry_but_no_retry_on_404_or_bad_json(tmp_path, monkeypatch):
    import io
    import urllib.error

    from osrs_ml import weekly_ingest as module

    sleeps = []
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    def missing(*a, **k):
        raise urllib.error.HTTPError("https://example.org", 404, "missing", {}, None)
    monkeypatch.setattr(module.urllib.request, "urlopen", missing)
    assert Archive(tmp_path).fetch("missing", "https://example.org")["status"] == "error"
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b'bad'))
    assert not Archive(tmp_path).fetch("bad", "https://example.org")["retryable"]
    def connection(*a, **k):
        raise urllib.error.URLError("connection reset")
    monkeypatch.setattr(module.urllib.request, "urlopen", connection)
    with pytest.raises(RuntimeError, match="paused"):
        Archive(tmp_path, retries=2).fetch("connection", "https://example.org")
    assert sleeps == [1.0, 2.0]


def test_full_universe_bounded_concurrency_and_cached_resume(tmp_path, monkeypatch):
    import io
    from threading import Barrier, Lock

    from osrs_ml import weekly_ingest as module

    monkeypatch.setenv("OSRS_DATA_DIR", str(tmp_path))
    dev = tmp_path / "development"
    dev.mkdir()
    (dev / "run.json").write_text(json.dumps({"holdout_start": WEEK * 10}))
    gate, mutex = Barrier(2), Lock()
    active, maximum, calls = 0, 0, []
    def response(request, **kwargs):
        nonlocal active, maximum
        calls.append(request.full_url)
        if request.full_url.endswith("/items"):
            return io.BytesIO(json.dumps({"data": [{"itemId": i} for i in (2, 3, 4, 5)]}).encode())
        with mutex:
            active += 1
            maximum = max(maximum, active)
        gate.wait(timeout=5)
        with mutex:
            active -= 1
        return io.BytesIO(b'{"data": []}')
    monkeypatch.setattr(module.urllib.request, "urlopen", response)
    root = tmp_path / "archive"
    module.run(root, True, dev, workers=2)
    assert maximum == 2 and len(calls) == 5
    manifest = json.loads((root / "run.json").read_text())
    assert manifest["status"] == "complete" and manifest["completed"] == 4
    assert not manifest["holdout_read"]
    module.run(root, True, dev, workers=2)
    assert len(calls) == 5
    assert pd.read_csv(root / "coverage.csv").item_id.tolist() == [2, 3, 4, 5]
