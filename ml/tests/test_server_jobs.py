import asyncio
import sys
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_server import fixture_service

from osrs_ml.server.app import create_app
from osrs_ml.server.jobs import REGISTRY, JobRequest, Runner, Store, prepare


def fake(root, request, output):
    code = {
        "benchmark": 'import json; print(json.dumps({"type":"metric","progress":0.5,"value":7}),flush=True); print("done",flush=True)',
        "eval": 'import sys; print("expected failure",file=sys.stderr,flush=True); sys.exit(7)',
        "train": 'import time; print("training",flush=True); time.sleep(20)',
        "backtest": "import time; time.sleep(20)",
    }[request.kind]
    return [sys.executable, "-u", "-c", code]


def make_runner(tmp_path, **kw):
    runner = Runner(tmp_path, command_factory=fake, **kw)
    runner.output = tmp_path / "outputs"
    return runner


def wait(client, job_id, statuses):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        job = client.get("/api/jobs/" + job_id).json()
        if job["status"] in statuses:
            return job
        time.sleep(0.02)
    pytest.fail(str(job))


def test_success_failure_ws_persistence(tmp_path):
    runner = make_runner(tmp_path)
    with TestClient(create_app(fixture_service(tmp_path), runner)) as client:
        job_id = client.post("/api/jobs", json={"kind": "benchmark"}).json()["id"]
        with client.websocket_connect("/api/jobs/" + job_id + "/stream") as ws:
            messages = []
            while True:
                event = ws.receive_json()
                messages.append(event)
                if event["type"] == "status" and event["data"]["status"] == "succeeded":
                    break
        job = wait(client, job_id, {"succeeded"})
        assert job["exit_code"] == 0 and job["progress"] == 1
        assert job["metrics_history"][0]["data"]["value"] == 7
        assert any(m["data"].get("line") == "done" for m in messages)
        failed = client.post("/api/jobs", json={"kind": "eval"}).json()["id"]
        assert wait(client, failed, {"failed"})["exit_code"] == 7
        assert any(e["data"].get("line") == "expected failure" for e in runner.store.events(failed))
    assert Store(runner.store.path).get(job_id)["status"] == "succeeded"


def test_cancel_queue_disconnect_timeout_and_restart(tmp_path):
    runner = make_runner(tmp_path, timeouts={k: 0.7 if k == "backtest" else 5 for k in REGISTRY})
    with TestClient(create_app(fixture_service(tmp_path), runner)) as client:
        first = client.post("/api/jobs", json={"kind": "train"}).json()["id"]
        wait(client, first, {"running"})
        second = client.post("/api/jobs", json={"kind": "benchmark"}).json()["id"]
        assert client.get("/api/jobs/" + second).json()["status"] == "queued"
        assert client.post("/api/jobs/" + second + "/cancel").json()["status"] == "cancelled"
        with client.websocket_connect("/api/jobs/" + first + "/stream") as ws:
            ws.receive_json()
        assert client.get("/api/jobs/" + first).json()["status"] == "running"
        client.post("/api/jobs/" + first + "/cancel")
        assert wait(client, first, {"cancelled"})["status"] == "cancelled"
        timed = client.post("/api/jobs", json={"kind": "backtest"}).json()["id"]
        assert wait(client, timed, {"failed"})["error"] == "job timed out"
        assert client.get("/api/jobs/missing").status_code == 404
    queued = runner.store.create(JobRequest(kind="benchmark"), runner.output)
    interrupted = runner.store.create(JobRequest(kind="train"), runner.output)
    runner.store.update(interrupted["id"], status="running")

    async def restart():
        r = make_runner(tmp_path)
        await r.start()
        assert r.store.get(interrupted["id"])["status"] == "failed"
        for _ in range(100):
            if r.store.get(queued["id"])["status"] == "succeeded":
                break
            await asyncio.sleep(0.03)
        assert r.store.get(queued["id"])["status"] == "succeeded"
        await r.close()

    asyncio.run(restart())


def test_registry_rejects_paths_commands_holdout(tmp_path):
    for request in [
        dict(kind="shell", params={}),
        dict(kind="eval", params={"snapshot": "/sealed"}),
        dict(kind="train", params={"holdout": True}),
        dict(kind="benchmark", params={"command": "id"}),
        dict(kind="eval", params={"dataset": "holdout"}),
        dict(kind="eval", params={"preset": "other"}),
    ]:
        with pytest.raises(ValidationError):
            JobRequest(**request)
    assert all(s.holdout_access is False for s in REGISTRY.values())
    command = prepare(tmp_path, JobRequest(kind="benchmark"), tmp_path / "out")
    assert "--holdout" not in command and command[:4] == ["uv", "run", "--frozen", "osrs-ml"]
    assert str(tmp_path / "out/input.parquet") in command


def test_development_predicate_before_cli(tmp_path):
    import pandas as pd

    from osrs_ml.alchemy import registration

    cutoff = registration()["holdout_start"]
    path = tmp_path / "assembled-v3/daily.parquet"
    path.parent.mkdir()
    pd.DataFrame(
        [
            dict(
                item_id=1,
                timestamp=t - 86400,
                available_at=t,
                avg_high_price=marker,
                avg_low_price=1,
                high_price_volume=1,
                low_price_volume=1,
                source_interval_seconds=86400,
                buy_limit=10,
                ingested_at=t,
            )
            for t, marker in [(cutoff - 1, 10), (cutoff, 999), (cutoff + 1, 999)]
        ]
    ).to_parquet(path)
    prepare(
        tmp_path,
        JobRequest(
            kind="eval",
            params={
                "dataset": "development",
                "horizon_hours": 24,
                "track": "frozen_daily",
                "preset": "all",
            },
        ),
        tmp_path / "safe",
    )
    result = pd.read_parquet(tmp_path / "safe/input.parquet")
    assert result.avg_high_price.tolist() == [10]
    assert result.timestamp.max() + 86400 < cutoff


def test_late_artifact_keeps_completed_progress_and_replays_after_cursor(tmp_path):
    import json

    def artifact(root, request, output):
        metrics = output / "run/x/metrics.json"
        code = f"import pathlib; p=pathlib.Path({str(metrics)!r}); p.parent.mkdir(parents=True); p.write_text('{json.dumps({'net_gp': 12})}'); print(\"artifact ready\")"
        return [sys.executable, "-u", "-c", code]

    runner = make_runner(tmp_path)
    runner.command_factory = artifact
    with TestClient(create_app(fixture_service(tmp_path), runner)) as client:
        job_id = client.post("/api/jobs", json={"kind": "benchmark"}).json()["id"]
        with client.websocket_connect(f"/api/jobs/{job_id}/stream") as ws:
            while True:
                try:
                    ws.receive_json()
                except Exception as exc:
                    from starlette.websockets import WebSocketDisconnect

                    assert isinstance(exc, WebSocketDisconnect)
                    break
        job = client.get("/api/jobs/" + job_id).json()
        assert job["status"] == "succeeded" and job["progress"] == 1
        assert job["metrics_history"][0]["data"]["values"]["net_gp"] == 12
        events = runner.store.events(job_id)
        cursor = events[1]["seq"]
        with client.websocket_connect(f"/api/jobs/{job_id}/stream?after={cursor}") as ws:
            assert ws.receive_json()["seq"] > cursor
