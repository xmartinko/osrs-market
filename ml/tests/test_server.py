import httpx
import pandas as pd
from fastapi.testclient import TestClient

from osrs_ml.server.app import create_app
from osrs_ml.server.service import Service


def fixture_service(tmp_path):
    pd.DataFrame(
        [
            dict(id=i, name=str(i), buy_limit=10000, high_alch=a, members=False)
            for i, a in [(561, 0), (855, 768), (859, 1536), (19580, 810), (19582, 1170)]
        ]
    ).to_parquet(tmp_path / "items.parquet")

    def respond(request):
        if "timeseries" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": [
                        dict(
                            timestamp=1,
                            avgHighPrice=110,
                            avgLowPrice=100,
                            highPriceVolume=10,
                            lowPriceVolume=20,
                        )
                    ]
                },
            )
        if request.url.path.endswith("latest"):
            return httpx.Response(
                200, json={"data": {"855": dict(high=110, low=100, highTime=1, lowTime=1)}}
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    str(i): dict(
                        avgHighPrice=100, avgLowPrice=90, highPriceVolume=1000, lowPriceVolume=1000
                    )
                    for i in [561, 855, 859, 19580, 19582]
                }
            },
        )

    return Service(tmp_path, httpx.Client(transport=httpx.MockTransport(respond)))


def test_reads(tmp_path):
    service = fixture_service(tmp_path)
    with TestClient(create_app(service)) as client:
        for path in [
            "health",
            "items",
            "prices/latest",
            "prices/855/history",
            "alch/gaps",
            "research/battery",
            "research/participation",
            "collector/health",
            "models/runs",
            "config",
        ]:
            assert client.get("/api/" + path).status_code == 200, path
        assert client.get("/api/prices/latest").json()["data"][0]["margin_gp"] == 8
        assert client.get("/api/alch/gaps").json()["data"][0]["net_gap_gp"] == 566
        assert client.get("/api/prices/855/history?tf=bad").status_code == 422
        assert client.get("/api/prices/855/history?limit=0").status_code == 422


def test_feed_failure_and_stale_cache(tmp_path):
    service = fixture_service(tmp_path)
    assert not service.latest()["stale"]

    def fail(request):
        raise httpx.ConnectError("offline")

    service.client = httpx.Client(transport=httpx.MockTransport(fail))
    service.cache["latest"]["attempted_at"] = 0
    result = service.latest()
    assert result["stale"] and result["error"] and result["data"]
    service.cache.clear()
    assert service.latest()["data"] == []
