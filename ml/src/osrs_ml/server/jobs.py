"""Durable FIFO scheduler. Requests cannot supply paths, argv, config or holdout flags."""

import asyncio
import json
import os
import signal
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..alchemy import registration
from ..battery import sealed_read
from ..data import FIELDS, manifest
from ..fixture import write_fixture
from .service import ML


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    dataset: Literal["synthetic", "development"] = "synthetic"
    horizon_hours: Literal[1, 4, 24] = 1
    track: Literal["price_only", "full_feature", "frozen_daily"] = "price_only"
    preset: Literal["conservative", "moderate", "optimistic", "all"] = "conservative"
    cash_gp: int = Field(default=10_000_000, ge=1000, le=100_000_000)

    @model_validator(mode="after")
    def matching_resolution(self):
        if self.dataset == "development":
            if self.horizon_hours != 24 or self.track != "frozen_daily" or self.preset != "all":
                raise ValueError(
                    "Daily development requires horizon_hours=24, track=frozen_daily, preset=all"
                )
        elif self.track == "frozen_daily" or self.preset == "all":
            raise ValueError(
                "Synthetic jobs require a price_only/full_feature track and one execution preset"
            )
        return self


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["backtest", "eval", "train", "benchmark"]
    params: Params = Field(default_factory=Params)


@dataclass(frozen=True)
class Spec:
    timeout: float
    # A capability, not an input path: only synthetic or predicate-sealed development.
    datasets: tuple[str, ...] = ("synthetic", "development")
    holdout_access: Literal[False] = False


REGISTRY = {
    "backtest": Spec(1800),
    "eval": Spec(3600),
    "train": Spec(7200),
    "benchmark": Spec(3600),
}
TERMINAL = {"succeeded", "failed", "cancelled"}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, params TEXT NOT NULL,
                    status TEXT NOT NULL, created_at REAL, started_at REAL, finished_at REAL,
                    exit_code INTEGER, progress REAL DEFAULT 0, error TEXT, output TEXT);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    timestamp REAL NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_job ON events(job_id, seq);
            """)

    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def create(self, request, output):
        job_id = uuid.uuid4().hex
        with self.db() as db:
            db.execute(
                "INSERT INTO jobs(id,kind,params,status,created_at,output) VALUES(?,?,?,'queued',?,?)",
                (
                    job_id,
                    request.kind,
                    request.params.model_dump_json(),
                    time.time(),
                    str(output / job_id),
                ),
            )
        self.event(job_id, "status", {"status": "queued"})
        return self.get(job_id)

    def update(self, job_id, **values):
        allowed = {"status", "started_at", "finished_at", "exit_code", "progress", "error"}
        assert set(values) <= allowed
        with self.db() as db:
            db.execute(
                "UPDATE jobs SET " + ",".join(k + "=?" for k in values) + " WHERE id=?",
                (*values.values(), job_id),
            )

    def list(self):
        with self.db() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [self.decode(r) for r in rows]

    def decode(self, row):
        result = dict(row)
        result["params"] = json.loads(result["params"])
        return result

    def get(self, job_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        result = self.decode(row)
        result["metrics_history"] = self.events(job_id, event_type="metric")
        return result

    def event(self, job_id, kind, data):
        with self.db() as db:
            db.execute(
                "INSERT INTO events(job_id,timestamp,type,data) VALUES(?,?,?,?)",
                (job_id, time.time(), kind, json.dumps(data, allow_nan=False)),
            )

    def events(self, job_id, after=0, event_type=None):
        with self.db() as db:
            sql = "SELECT * FROM events WHERE job_id=? AND seq>?"
            args = [job_id, after]
            if event_type:
                sql += " AND type=?"
                args.append(event_type)
            rows = db.execute(sql + " ORDER BY seq LIMIT 1000", args).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]


def prepare(root, request, output):
    """Only this adapter can choose inputs. No request field becomes a source path."""
    spec = REGISTRY[request.kind]
    if request.params.dataset not in spec.datasets or spec.holdout_access:
        raise ValueError("Disallowed dataset capability")
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "input.parquet"
    if request.params.dataset == "synthetic":
        write_fixture(snapshot)
    else:
        cfg = registration()
        # Predicate pushed into DuckDB before any market fields are materialized.
        frame = sealed_read(
            root / "assembled-v3/daily.parquet", cfg["holdout_start"], start=cfg["start"]
        )
        if frame.empty or frame.available_at.max() >= cfg["holdout_start"]:
            raise ValueError("No admissible development observations")
        # Preserve source interval and provenance; this is an adapter, not a resampler.
        table = pa.Table.from_pandas(frame, preserve_index=False)
        arrays = [
            table[f].cast(pa.int64())
            if f in table.column_names
            else pa.nulls(len(frame), type=pa.int64())
            for f in FIELDS
        ]
        # Retain availability, unknown-interval flags and all provenance columns.
        for name, array in zip(FIELDS, arrays, strict=True):
            if name in table.column_names:
                table = table.set_column(table.column_names.index(name), name, array)
            else:
                table = table.append_column(name, array)
        pq.write_table(table, snapshot)
        manifest(
            snapshot,
            source="sealed_development",
            rows=len(frame),
            holdout_read=False,
            holdout_start=cfg["holdout_start"],
        )
    # Each dataset uses its existing audited CLI, without a holdout capability.
    if request.params.dataset == "development":
        config = json.loads((ML / "experiments/daily-v1.json").read_text())
        # Input is already sealed to development. Reserve no further holdout; use two
        # 14-day folds inside the frozen 84-day development window. No research code changes.
        config.update(holdout_days=0, folds=2, fold_days=14, cash_gp=request.params.cash_gp)
        config_path = output / "daily.json"
        config_path.write_text(json.dumps(config))
        return [
            "uv",
            "run",
            "--frozen",
            "osrs-ml",
            "research",
            "--panel",
            str(snapshot),
            "--output",
            str(output / "run"),
            "--config",
            str(config_path),
        ]
    return [
        "uv",
        "run",
        "--frozen",
        "osrs-ml",
        "run",
        "--snapshot",
        str(snapshot),
        "--output",
        str(output / "run"),
        "--tracks",
        request.params.track,
        "--presets",
        request.params.preset,
        "--horizon-hours",
        str(request.params.horizon_hours),
        "--cash-gp",
        str(request.params.cash_gp),
    ]


class Runner:
    def __init__(self, root, store=None, concurrency=1, command_factory=None, timeouts=None):
        self.root = Path(root)
        self.store = store or Store(self.root / "server/jobs.sqlite")
        self.output = ML / "runs/server"
        self.concurrency = max(1, concurrency)
        self.command_factory = command_factory or prepare
        self.timeouts = timeouts or {k: s.timeout for k, s in REGISTRY.items()}
        self.active = {}
        self.processes = {}
        self.cancelled = set()
        self.stopping = False

    async def start(self):
        for job in self.store.list():
            if job["status"] == "succeeded":
                self.store.update(job["id"], progress=1)
            if job["status"] == "running":
                self.store.update(
                    job["id"],
                    status="failed",
                    finished_at=time.time(),
                    error="server restarted during execution",
                )
                self.store.event(
                    job["id"],
                    "status",
                    {"status": "failed", "error": "server restarted during execution"},
                )
        self.scheduler = asyncio.create_task(self.schedule())

    async def close(self):
        self.stopping = True
        self.scheduler.cancel()
        await asyncio.gather(self.scheduler, return_exceptions=True)
        for job_id in list(self.active):
            await self.cancel(job_id)
        await asyncio.gather(*self.active.values(), return_exceptions=True)

    async def schedule(self):
        while not self.stopping:
            for job in reversed(self.store.list()):
                if len(self.active) >= self.concurrency:
                    break
                if job["status"] == "queued" and job["id"] not in self.active:
                    self.active[job["id"]] = asyncio.create_task(self.execute(job))
            await asyncio.sleep(0.1)

    async def terminate(self, process):
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            await asyncio.wait_for(process.wait(), 3)
        except asyncio.TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        except ProcessLookupError:
            pass

    async def cancel(self, job_id):
        job = self.store.get(job_id)
        if not job or job["status"] in TERMINAL:
            return job
        self.cancelled.add(job_id)
        if job_id in self.processes:
            await self.terminate(self.processes[job_id])
        elif job["status"] == "queued":
            self.store.update(job_id, status="cancelled", finished_at=time.time())
            self.store.event(job_id, "status", {"status": "cancelled"})
        return self.store.get(job_id)

    async def read(self, job_id, stream, channel):
        while line := await stream.readline():
            line = line.decode(errors="replace").rstrip()
            self.store.event(job_id, "log", {"channel": channel, "line": line})
            try:
                value = json.loads(line)
                if isinstance(value, dict) and value.get("type") == "metric":
                    self.store.event(job_id, "metric", value)
                    if "progress" in value:
                        self.store.update(job_id, progress=max(0, min(1, float(value["progress"]))))
            except (ValueError, TypeError):
                pass

    async def collect_metrics(self, job_id, output):
        # CLI emits metrics artifacts as each evaluation finishes. Stream them immediately.
        seen = set()
        while True:
            for path in sorted((output / "run").glob("**/metrics.json")):
                if path in seen:
                    continue
                try:
                    values = json.loads(path.read_text())
                    self.store.event(
                        job_id,
                        "metric",
                        {"artifact": str(path.relative_to(output)), "values": values},
                    )
                    seen.add(path)
                    if self.store.get(job_id)["status"] not in TERMINAL:
                        self.store.update(job_id, progress=min(0.95, len(seen) / 16))
                except (ValueError, OSError):
                    continue
            job = self.store.get(job_id)
            if job["status"] in TERMINAL:
                break
            await asyncio.sleep(0.3)

    async def execute(self, job):
        job_id = job["id"]
        process = None
        collector = None
        try:
            if job_id in self.cancelled:
                return
            self.store.update(job_id, status="running", started_at=time.time())
            self.store.event(job_id, "status", {"status": "running"})
            request = JobRequest(kind=job["kind"], params=job["params"])
            output = Path(job["output"])

            async def work():
                nonlocal process, collector
                command = await asyncio.to_thread(self.command_factory, self.root, request, output)
                if job_id in self.cancelled:
                    return None
                self.store.event(
                    job_id,
                    "log",
                    {
                        "channel": "server",
                        "line": f"{job['kind']} {request.params.dataset}: audited development harness; sealed holdout unavailable",
                    },
                )
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=ML,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                    limit=1024 * 1024,
                )
                self.processes[job_id] = process
                collector = asyncio.create_task(self.collect_metrics(job_id, output))
                await asyncio.gather(
                    self.read(job_id, process.stdout, "stdout"),
                    self.read(job_id, process.stderr, "stderr"),
                )
                return await process.wait()

            code = await asyncio.wait_for(work(), self.timeouts[job["kind"]])
            status = (
                "cancelled" if job_id in self.cancelled else "succeeded" if code == 0 else "failed"
            )
            self.store.update(
                job_id,
                status=status,
                finished_at=time.time(),
                exit_code=code,
                progress=1 if status == "succeeded" else self.store.get(job_id)["progress"],
                error=f"process exited {code}" if status == "failed" else None,
            )
        except Exception as exc:
            if process:
                await self.terminate(process)
            message = (
                "job timed out"
                if isinstance(exc, asyncio.TimeoutError)
                else f"{type(exc).__name__}: {exc}"
            )
            self.store.event(job_id, "log", {"channel": "server", "line": message})
            self.store.update(
                job_id,
                status="cancelled" if job_id in self.cancelled else "failed",
                finished_at=time.time(),
                exit_code=process.returncode if process else None,
                error=message,
            )
        finally:
            self.store.event(job_id, "status", {"status": self.store.get(job_id)["status"]})
            if collector:
                await collector
            self.processes.pop(job_id, None)
            self.active.pop(job_id, None)
            self.cancelled.discard(job_id)
