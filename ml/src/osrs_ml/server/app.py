from typing import Literal

from fastapi import FastAPI, Query

from . import VERSION
from .service import ML, Service


def create_app(service=None):
    service = service or Service()
    app = FastAPI(title="OSRS research server", version=VERSION)
    app.state.service = service
    app.get("/api/health")(service.health)
    app.get("/api/items")(service.items)
    app.get("/api/prices/latest")(service.latest)

    @app.get("/api/prices/{item_id}/history")
    def history(item_id: int, tf: Literal["5m", "1h", "1d"] = "5m",
                limit: int = Query(120, ge=1, le=1000)):
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
        return dict(version=VERSION, data_dir=str(service.root), ml_dir=str(ML),
                    flags=dict(holdout_jobs_enabled=False), feed_ttl_seconds=service.ttl)

    return app
