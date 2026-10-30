import asyncio
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from . import VERSION
from .jobs import TERMINAL, JobRequest, Runner
from .service import ML, Service


def create_app(service=None, runner=None):
    service = service or Service()
    runner = runner or Runner(service.root, concurrency=int(os.getenv("OSRS_JOB_CONCURRENCY", "1")))

    @asynccontextmanager
    async def lifespan(app):
        await runner.start()
        yield
        await runner.close()
        service.client.close()

    app = FastAPI(title="OSRS research server", version=VERSION, lifespan=lifespan)
    app.state.runner = runner

    @app.post("/api/jobs", status_code=202)
    async def start_job(request: JobRequest):
        return runner.store.create(request, runner.output)

    @app.get("/api/jobs")
    def jobs():
        return dict(data=runner.store.list())

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        result = runner.store.get(job_id)
        if result is None:
            raise HTTPException(404, "Unknown job")
        return result

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel(job_id: str):
        if runner.store.get(job_id) is None:
            raise HTTPException(404, "Unknown job")
        return await runner.cancel(job_id)

    @app.websocket("/api/jobs/{job_id}/stream")
    async def stream(socket: WebSocket, job_id: str, after: int = 0):
        if runner.store.get(job_id) is None:
            await socket.close(code=1008, reason="Unknown job")
            return
        await socket.accept()
        try:
            while True:
                events = runner.store.events(job_id, after)
                for event in events:
                    await socket.send_json(event)
                    after = event["seq"]
                if (
                    not events
                    and job_id not in runner.active
                    and runner.store.get(job_id)["status"] in TERMINAL
                ):
                    await socket.close()
                    return
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass

    app.state.service = service
    app.get("/api/health")(service.health)
    app.get("/api/items")(service.items)
    app.get("/api/prices/latest")(service.latest)

    @app.get("/api/prices/{item_id}/history")
    def history(
        item_id: int, tf: Literal["5m", "1h", "1d"] = "5m", limit: int = Query(120, ge=1, le=1000)
    ):
        return service.history(item_id, tf, limit)

    app.get("/api/alch/gaps")(service.alch)

    @app.get("/api/research/battery")
    def battery():
        return service.research("battery")

    @app.get("/api/research/participation")
    def participation():
        return service.research("participation")

    app.get("/api/collector/health")(service.collector)
    app.get("/api/models/runs")(service.runs)

    @app.get("/api/config")
    def config():
        return dict(
            version=VERSION,
            data_dir=str(service.root),
            ml_dir=str(ML),
            flags=dict(holdout_jobs_enabled=False),
            feed_ttl_seconds=service.ttl,
        )

    return app
