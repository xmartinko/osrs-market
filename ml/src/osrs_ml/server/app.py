import asyncio
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from . import VERSION
from .chat import Busy, ChatRequest, ChatRunner
from .jobs import TERMINAL, JobRequest, Runner
from .search import Search
from .search_intent import Query as SearchQuery
from .search_intent import parse_intent
from .service import ML, Service
from .terminal import AlertRequest, ChartRequest, PanelRequest, Terminal
from .usage import Usage


def create_app(service=None, runner=None, chat=None, usage=None):
    service = service or Service()
    runner = runner or Runner(service.root, concurrency=int(os.getenv("OSRS_JOB_CONCURRENCY", "1")))

    chat = chat or ChatRunner(runner.store.path)
    usage = usage or Usage()
    terminal = Terminal(service)
    search = Search(service, terminal)

    @asynccontextmanager
    async def lifespan(app):
        await runner.start()
        await chat.start()

        async def alert_loop():
            while True:
                try:
                    await asyncio.to_thread(terminal.evaluate_alerts)
                except Exception:
                    import logging

                    logging.getLogger(__name__).exception("Alert evaluation failed")
                await asyncio.sleep(5)

        alert_task = asyncio.create_task(alert_loop())
        try:
            yield
        finally:
            alert_task.cancel()
            await asyncio.gather(alert_task, return_exceptions=True)
            await chat.close()
            await usage.close()
            await runner.close()
            service.client.close()

    app = FastAPI(title="OSRS research server", version=VERSION, lifespan=lifespan)
    app.state.runner = runner

    app.state.chat = chat
    app.state.usage = usage

    @app.get("/api/search/catalogue")
    def search_catalogue():
        return search.catalogue()

    @app.post("/api/search")
    def search_results(request: SearchQuery):
        try:
            return search.results(request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/search/parse")
    async def search_parse(request: SearchQuery):
        return await parse_intent(request.query)

    @app.get("/api/usage")
    async def credits():
        return await usage.get()

    @app.post("/api/chat", status_code=202)
    async def start_chat(request: ChatRequest):
        try:
            result = chat.submit(request)
            chat.task.add_done_callback(lambda _: usage.invalidate())
            return result
        except Busy as exc:
            raise HTTPException(409, dict(status="busy", error=str(exc))) from None
        except KeyError:
            raise HTTPException(404, "Unknown chat") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/chats")
    def chats():
        return dict(data=chat.store.list())

    @app.get("/api/chat/{chat_id}")
    def transcript(chat_id: str):
        result = chat.store.get(chat_id)
        if result is None:
            raise HTTPException(404, "Unknown chat")
        return result

    @app.post("/api/chat/{chat_id}/cancel")
    async def cancel_chat(chat_id: str):
        if chat.store.get(chat_id) is None:
            raise HTTPException(404, "Unknown chat")
        return await chat.cancel(chat_id)

    @app.websocket("/api/chat/{chat_id}/stream")
    async def chat_stream(socket: WebSocket, chat_id: str, after: int = 0):
        if chat.store.get(chat_id) is None:
            await socket.close(code=1008, reason="Unknown chat")
            return
        await socket.accept()
        try:
            while True:
                events = chat.store.events(chat_id, after)
                for event in events:
                    await socket.send_json(event)
                    after = event["seq"]
                if not events and chat.store.get(chat_id)["status"] != "running":
                    await socket.close()
                    return
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass

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

    @app.post("/api/terminal/chart")
    def terminal_chart(request: ChartRequest):
        try:
            return terminal.chart(request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/terminal/panel")
    def terminal_panel(request: PanelRequest):
        try:
            return terminal.panel(request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/terminal/alerts")
    def terminal_alerts():
        return terminal.alerts()

    @app.post("/api/terminal/alerts", status_code=201)
    def terminal_alert_add(request: AlertRequest):
        return terminal.add_alert(request)

    @app.delete("/api/terminal/alerts/{alert_id}")
    def terminal_alert_delete(alert_id: int):
        return terminal.delete_alert(alert_id)

    app.state.terminal = terminal
    app.state.service = service
    app.get("/api/health")(service.health)
    app.get("/api/items")(service.items)
    app.get("/api/prices/latest")(service.latest)
    app.get("/api/prices/movers")(service.movers)

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
