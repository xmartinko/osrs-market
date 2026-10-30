import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_server import fixture_service

from osrs_ml.server.app import create_app
from osrs_ml.server.terminal import AlertRequest, ChartRequest, PanelRequest, Terminal


def terminal(tmp_path):
    service = fixture_service(tmp_path)
    path = tmp_path / "assembled-v3/daily.parquet"
    path.parent.mkdir()
    now = int(time.time()) // 86400 * 86400
    pd.DataFrame(
        [
            dict(
                item_id=855,
                timestamp=now - day * 86400,
                avg_high_price=100 + day,
                avg_low_price=90 + day,
                high_price_volume=10,
                low_price_volume=20,
            )
            for day in range(200)
        ]
    ).to_parquet(path)
    return Terminal(service)


@pytest.mark.parametrize("style", ["Line", "Area", "Heikin Ashi", "Renko", "Point & Figure"])
def test_real_local_history_and_honest_provenance(tmp_path, style):
    term = terminal(tmp_path)
    result = term.chart(ChartRequest(style=style))
    assert result["visible_bars"] > 80
    assert result["available_bars"] > 190
    assert "local daily means" in result["source"]
    if style == "Heikin Ashi":
        assert "mean-envelope" in result["provenance"]
        assert "NOT trade OHLC" in result["provenance"]


def test_range_zoom_pan_date_and_resolution_are_independent(tmp_path):
    term = terminal(tmp_path)
    full = term.chart(ChartRequest(range="6m"))
    zoom = term.chart(ChartRequest(range="6m", bars=20, offset=5))
    assert zoom["visible_bars"] == 20
    assert zoom["last"]["timestamp"] < full["last"]["timestamp"]
    assert zoom["tf"] == full["tf"] == "1d"
    jump = term.chart(ChartRequest(date="2026-01-01"))
    assert not jump["last"] or jump["last"]["timestamp"] <= 1767311999
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        term.chart(ChartRequest(date="garbage"))


def test_screener_composes_constraints(tmp_path):
    term = terminal(tmp_path)
    assert (
        len(
            term.panel(
                PanelRequest(
                    kind="EQS",
                    min_spread=8,
                    min_volume=1,
        
                    members=False,
                    limit_min=100,
                    limit_max=10000,
                )
            )["data"]
        )
        == 1
    )
    assert not term.panel(PanelRequest(kind="EQS", min_spread=9))["data"]
    assert not term.panel(PanelRequest(kind="EQS", members=True))["data"]


def test_all_panels_and_no_fabricated_trade_counts(tmp_path):
    term = terminal(tmp_path)
    for kind in ["TAS", "QM", "HCP", "HMAP", "MOST", "EQS", "COMP", "AL"]:
        result = term.panel(PanelRequest(kind=kind))
        assert "data" in result or "series" in result
    most = term.panel(PanelRequest(kind="MOST"))
    assert most["data"][0]["trade_count"] is None
    assert "unavailable" in most["basis"]
    tape = term.panel(PanelRequest(kind="TAS"))
    assert "NOT individual trades" in tape["basis"]
    assert len(tape["data"]) == 2
    assert len(term.panel(PanelRequest(kind="TAS"))["data"]) == 2


def test_alerts_persist_and_only_fire_on_fresh_quotes(tmp_path):
    term = terminal(tmp_path)
    term.add_alert(AlertRequest(item=855, field="spread", direction="above", threshold=7))
    term.evaluate_alerts()
    assert term.alerts()["data"][0]["triggered"] is None  # Fixture quotes are old.
    market = term.market()
    for r in market["data"]:
        r["bid_time"] = r["ask_time"] = int(time.time())
    term.evaluate_alerts()
    fired = term.alerts()["data"][0]
    assert fired["triggered"] and fired["value"] == 8
    restored = Terminal(term.service)
    assert restored.alerts()["data"][0] == fired
    restored.delete_alert(fired["id"])
    assert restored.alerts()["data"] == []


def test_alerts_skip_stale_response_and_missing_data(tmp_path):
    term = terminal(tmp_path)
    term.add_alert(AlertRequest(item=855, field="price", direction="below", threshold=200))
    market = term.market()
    market["stale"] = True
    market["data"][0]["bid_time"] = market["data"][0]["ask_time"] = time.time()
    term.evaluate_alerts()
    assert not term.alerts()["data"][0]["triggered"]


def test_terminal_endpoints_validation(tmp_path):
    term = terminal(tmp_path)
    with TestClient(create_app(term.service)) as client:
        assert client.post("/api/terminal/chart", json={"tf": "1m"}).status_code == 422
        assert client.post("/api/terminal/chart", json={"style": "fake"}).status_code == 422
        assert client.post("/api/terminal/chart", json={"date": "no"}).status_code == 422
        assert (
            client.post(
                "/api/terminal/panel", json={"kind": "COMP", "ids": list(range(6))}
            ).status_code
            == 422
        )
        assert client.post("/api/terminal/chart", json={}).status_code == 200
        result = client.post(
            "/api/terminal/alerts",
            json=dict(item=855, field="price", direction="above", threshold=99),
        )
        assert result.status_code == 201
        assert len(client.get("/api/terminal/alerts").json()["data"]) == 1
        assert client.delete("/api/terminal/alerts/1").status_code == 200
