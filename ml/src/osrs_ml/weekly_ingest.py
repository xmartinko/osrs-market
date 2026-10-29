"""Private, concurrent, resumable GE Tracker archive. Never imported by the product."""

import argparse
import fcntl
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Event

import pandas as pd

from .data import sha256
from .diagnostics import atomic_json

SOURCE = "ge-tracker-private-research"
VERSION = 1
BASE = "https://www.ge-tracker.com/api"
FIELDS = (
    "overallPrice", "buyingPrice", "sellingPrice",
    "overallCompleted", "buyingCompleted", "sellingCompleted",
)
WEEK = 604800


def external_directory(path, acknowledged):
    if not acknowledged:
        raise ValueError("Requires --acknowledge-private-research; see docs/deep-history-protocol.md")
    root = Path(os.environ["OSRS_DATA_DIR"]).resolve()
    repo = Path(__file__).resolve().parents[3]
    path = Path(path).resolve()
    if path.is_relative_to(repo) or root.is_relative_to(repo) or not path.is_relative_to(root):
        raise ValueError("Private research data must be under OSRS_DATA_DIR outside the repository")
    path.mkdir(parents=True, exist_ok=True)
    return path


def retryable(record):
    error = record.get("error", "")
    return (record.get("retryable", False) or error in ("HTTP 403", "HTTP 429")
            or any(error == f"HTTP {code}" for code in range(500, 600)))


class Archive:
    def __init__(self, root, *, retries=4, backoff=1.0):
        if retries < 0 or backoff <= 0:
            raise ValueError("Nonnegative retries and positive backoff required")
        self.root, self.retries, self.backoff = root, retries, backoff
        self.stopped = Event()

    def fetch(self, key, url):
        path = self.root / f"{key}.json"
        previous_attempts = []
        if path.exists():
            record = json.loads(path.read_text())
            if record["source_url"] != url or record["schema_version"] != VERSION:
                raise ValueError("Cache provenance mismatch")
            if not retryable(record):
                return record
            previous_attempts = record.get("attempts", [])
            remaining = max(0, record.get("retry_not_before", 0) - time.time())
            if remaining:
                print(f"Cached transient error at {url}; honoring remaining backoff={remaining:.1f}s",
                      flush=True)
                time.sleep(remaining)
        for attempt in range(self.retries + 1):
            if self.stopped.is_set():
                raise RuntimeError("Collection paused after persistent source/network errors; resume later")
            record = {
                "source": SOURCE, "schema_version": VERSION, "source_url": url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "attempts": previous_attempts.copy(),
            }
            retry_after = 0
            try:
                request = urllib.request.Request(url, headers={
                    "Accept": "application/x.getracker.v2.1+json",
                    "User-Agent": "osrs-market-private-research/1.1 (cached research)",
                })
                with urllib.request.urlopen(request, timeout=45) as response:
                    record.update(status="ok", payload=json.load(response), retryable=False)
            except urllib.error.HTTPError as error:
                record.update(status="error", error=f"HTTP {error.code}",
                              retryable=error.code in (403, 429) or 500 <= error.code < 600)
                record["http_status"] = error.code
                record["response_headers"] = {k: error.headers[k] for k in (
                    "Date", "Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining",
                    "X-RateLimit-Reset", "Server") if error.headers and k in error.headers}
                header = record["response_headers"].get("Retry-After", "0")
                try:
                    retry_after = max(0, float(header))
                except (ValueError, TypeError):
                    try:
                        retry_after = max(0, parsedate_to_datetime(header).timestamp() - time.time())
                    except (ValueError, TypeError, OverflowError):
                        pass
            except (OSError, http.client.HTTPException) as error:
                record.update(status="error", error=str(error), retryable=True)
            except ValueError as error:
                record.update(status="error", error=str(error), retryable=False)
            if retryable(record):
                record["retry_not_before"] = time.time() + max(retry_after, self.backoff * 2 ** attempt)
            record["attempts"].append({k: record[k] for k in (
                "fetched_at", "status", "retryable", "error", "http_status", "response_headers",
                "retry_not_before") if k in record})
            previous_attempts = record["attempts"]
            atomic_json(path, record)
            if not retryable(record):
                return record
            if attempt == self.retries:
                self.stopped.set()
                raise RuntimeError(f"Persistent {record['error']} at {url}; collection paused, "
                                   "cached and resumable (source not declared forbidden)")
            delay = max(retry_after, self.backoff * 2 ** attempt)
            print(f"Retry {attempt + 1}/{self.retries} {url}: {record['error']}; "
                  f"backoff={delay:g}s", flush=True)
            time.sleep(delay)
        raise AssertionError("Unreachable")


def development_rows(record, item_id, cutoff):
    """Inspect dates first; never analyze fields from reserved or incomplete weeks."""
    if record["status"] != "ok":
        return []
    payload = record["payload"]
    if isinstance(payload, dict) and payload.get("status") == "error":
        return []  # HTTP 200 provider failures are retained, never retried as network errors.
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Unexpected graph API schema")
    rows, seen = [], set()
    for point in payload["data"]:
        ts = point["ts"]
        if not isinstance(ts, int) or ts % 1000:
            raise ValueError("Expected integer millisecond timestamps")
        timestamp = ts // 1000
        if timestamp + WEEK + 300 >= cutoff:
            continue
        if timestamp in seen:
            raise ValueError("Duplicate item/week")
        seen.add(timestamp)
        values = {field: point.get(field) for field in FIELDS}
        if any(v is not None and (type(v) is not int or v < 0) for v in values.values()):
            raise ValueError("Non-integer or negative API observation")
        rows.append({
            "item_id": item_id, "timestamp": timestamp,
            "available_at": timestamp + WEEK + 300, **values,
            **{k: record[k] for k in ("source", "source_url", "fetched_at", "schema_version")},
            "provider_source": payload.get("source", "unknown"),
        })
    return rows


def assemble(root, universe, cutoff):
    """No sparse-item filtering. One coverage row per requested identifier."""
    rows, coverage = [], []
    for item_id in universe:
        path = root / f"graph-{item_id}.json"
        record = json.loads(path.read_text()) if path.exists() else {"status": "pending"}
        part = development_rows(record, item_id, cutoff) if path.exists() else []
        rows.extend(part)
        times = sorted(row["timestamp"] for row in part)
        payload = record.get("payload", {})
        application_error = payload.get("status") == "error"
        raw_times = [p["ts"] // 1000 for p in (payload.get("data") or [])]
        coverage.append({
            "item_id": item_id,
            "status": "application_error" if application_error else record["status"], "rows": len(part),
            "first_timestamp": min(times) if times else None,
            "last_timestamp": max(times) if times else None,
            "gaps_over_8_days": sum(b - a > 8 * 86400 for a, b in zip(times, times[1:], strict=False)),
            "error": payload.get("msg", "Provider application error") if application_error
            else record.get("error"),
            "raw_rows": len(raw_times),
            "raw_first_timestamp": min(raw_times) if raw_times else None,
            "raw_last_timestamp": max(raw_times) if raw_times else None,
            "full_9_7_year_span": bool(raw_times and
                                      max(raw_times) - min(raw_times) >= 9.7 * 365.25 * 86400),
        })
    panel = pd.DataFrame(rows, columns=[
        "item_id", "timestamp", "available_at", *FIELDS, "source", "source_url",
        "fetched_at", "schema_version", "provider_source",
    ])
    if not panel.empty:
        for col in FIELDS:
            panel[col] = pd.array(panel[col], dtype="int64[pyarrow]")
    temporary = root / "weekly.partial.parquet"
    panel.to_parquet(temporary, index=False)
    temporary.replace(root / "weekly.parquet")
    pd.DataFrame(coverage).to_csv(root / "coverage.csv", index=False)
    annual = []
    if not panel.empty:
        years = pd.to_datetime(panel.timestamp, unit="s", utc=True).dt.year
        for year, group in panel.groupby(years):
            annual.append({
                "year": int(year), "items": int(group.item_id.nunique()), "rows": len(group),
                "universe": len(universe),
                "positive_two_side_rows": int(((group.buyingPrice > 0) &
                                              (group.sellingPrice > 0) &
                                              (group.buyingCompleted > 0) &
                                              (group.sellingCompleted > 0)).sum()),
            })
    pd.DataFrame(annual).to_csv(root / "annual-coverage.csv", index=False)
    return len(panel), coverage


def run(output, acknowledged, development_run, *, checkpoint=250, workers=8):
    if not 1 <= workers <= 16:
        raise ValueError("Use between 1 and 16 workers")
    root = external_directory(output, acknowledged)
    lock = (root.parent / ".ge-tracker.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        metadata = json.loads((development_run / "run.json").read_text())
        cutoff = metadata["holdout_start"]
        archive = Archive(root)
        catalogue = archive.fetch("items", BASE + "/items")
        if catalogue["status"] != "ok":
            raise ValueError("Cannot establish item universe")
        universe = sorted({int(item["itemId"]) for item in catalogue["payload"]["data"]})
        manifest_path = root / "run.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest["universe"] != universe or manifest["holdout_start"] != cutoff:
                raise ValueError("Frozen universe or holdout boundary changed")
        else:
            manifest = {
                "schema_version": VERSION, "source": SOURCE, "universe": universe,
                "holdout_start": cutoff, "holdout_read": False,
                "acknowledged": "private research; no public tool/publication/redistribution; UK database right",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "catalogue_sha256": sha256(root / "items.json"),
                "code_sha256": sha256(Path(__file__)),
                "development_manifest_sha256": sha256(development_run / "run.json"),
            }
        manifest.update(status="running")
        atomic_json(manifest_path, manifest)
        try:
            manifest.update(workers=workers, ingest_code_sha256=sha256(Path(__file__)))
            atomic_json(manifest_path, manifest)
            started = time.monotonic()
            iterator = iter(universe)
            completed = 0
            # Bound queued work as well as live requests; pause scheduling on persistent errors.
            with ThreadPoolExecutor(max_workers=workers) as pool:
                pending = set()
                def submit_one():
                    item_id = next(iterator, None)
                    if item_id is not None:
                        pending.add(pool.submit(archive.fetch, f"graph-{item_id}",
                                                f"{BASE}/graph/{item_id}/all"))
                for _ in range(workers):
                    submit_one()
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        future.result()
                        completed += 1
                        if completed % checkpoint == 0 or completed == len(universe):
                            manifest.update(completed=completed,
                                            updated_at=datetime.now(timezone.utc).isoformat())
                            atomic_json(manifest_path, manifest)
                            print(f"Archived {completed}/{len(universe)} items; "
                                  f"elapsed={time.monotonic() - started:.1f}s; "
                                  "holdout NOT analyzed", flush=True)
                        submit_one()
            n, coverage = assemble(root, universe, cutoff)
            manifest.update(rows=n, statuses=pd.Series([r["status"] for r in coverage])
                            .value_counts().to_dict(), elapsed_seconds=time.monotonic() - started)
            manifest.update(status="complete", panel_sha256=sha256(root / "weekly.parquet"))
            atomic_json(manifest_path, manifest)
        except BaseException as error:
            manifest.update(status="interrupted", failure=str(error))
            atomic_json(manifest_path, manifest)
            raise
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--development-run", type=Path, required=True)
    parser.add_argument("--acknowledge-private-research", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    run(args.output, args.acknowledge_private_research, args.development_run, workers=args.workers)


if __name__ == "__main__":
    main()
