import httpx
import pandas as pd
import pytest
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
            "prices/movers",
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


def test_movers_existing_features(tmp_path):
    service = fixture_service(tmp_path)

    def respond(request):
        before = "timestamp=" in str(request.url)
        return httpx.Response(
            200,
            json={
                "timestamp": 300 if before else 600,
                "data": {
                    "855": dict(
                        avgHighPrice=100 if before else 110,
                        avgLowPrice=100 if before else 110,
                        highPriceVolume=100,
                        lowPriceVolume=200,
                    )
                },
            },
        )

    service.client = httpx.Client(transport=httpx.MockTransport(respond))
    result = service.movers()
    assert result["data"][0]["change_pct"] == pytest.approx(10)
    assert result["data"][0]["volume"] == 100


def test_collector_research_fixture(tmp_path):
    import json
    import sqlite3

    service = fixture_service(tmp_path)
    for timestamp in [300, 1200]:
        path = tmp_path / f"forward/wiki/300s/{timestamp}/observations.manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(timestamp=timestamp, resolution_seconds=300)))
    with sqlite3.connect(tmp_path / "forward/ledger.sqlite") as db:
        db.execute("CREATE TABLE predictions (id INTEGER)")
        db.execute("INSERT INTO predictions VALUES (1)")
    value = service.collector()
    assert value["snapshot_count"] == 2
    assert value["buckets"][0]["gaps"] == 2
    assert value["ledger_rows"]["ledger.sqlite"]["predictions"] == 1
    path = tmp_path / "strategy-battery-v1/results.csv"
    path.parent.mkdir()
    pd.DataFrame(
        [dict(id="rule", p_raw=0.01, p_adjusted=0.9, survives=False, status="tested")]
    ).to_csv(path, index=False)
    value = service.research("battery")["data"][0]
    assert value["p_raw"] == 0.01 and value["p_adjusted"] == 0.9
    assert value["verdict"] == "rejected"


def test_malformed_feed_is_data_not_500(tmp_path):
    service = fixture_service(tmp_path)
    service.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": None}))
    )
    with TestClient(create_app(service)) as client:
        response = client.get("/api/prices/latest")
        assert response.status_code == 200
        assert response.json()["stale"] and response.json()["data"] == []
        assert response.json()["error"] == "Unexpected Wiki response shape"
