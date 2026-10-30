import json
import os
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from test_server import fixture_service

from osrs_ml.server.app import create_app
from osrs_ml.server.chat import ChatRunner, ChatStore, parse_usage
from osrs_ml.server.usage import Usage


@pytest.fixture
def fake_hermes(tmp_path, monkeypatch):
    """Absolute interpreter in stub; PATH contains ONLY our fake Hermes choice."""
    binary = tmp_path / "hermes"
    binary.write_text(f"""#!{sys.executable}
import json, pathlib, sys, time
args = sys.argv[1:]
if args == ["sessions", "list"]:
    print("Title Workspace Last Active ID")
    print("Cron — now cron_20261030_000000_abc")
    print("Fake chat workspace now 20261030_010203_fake")
    sys.exit(0)
assert args[args.index("-t") + 1] == "bot_room"
assert "--safe-mode" in args
prompt = args[args.index("-z") + 1]
if "--resume" in args:
    assert args.index("--resume") < args.index("-z")
    assert args[args.index("--resume") + 1] == "20261030_010203_fake"
report = {{"estimated_cost_usd":0.012,"input_tokens":100,"output_tokens":5,
          "total_tokens":105,"api_calls":1,"model":"fake-model"}}
pathlib.Path(args[args.index("--usage-file") + 1]).write_text(json.dumps(report))
if prompt == "slow":
    print("working", file=sys.stderr, flush=True)
    time.sleep(10)
elif prompt == "fail":
    print("known failure", file=sys.stderr)
    sys.exit(7)
else:
    time.sleep(0.05)
    print("remembered" if "--resume" in args else "known reply: " + prompt)
""")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.delenv("OSRS_HERMES_SESSION", raising=False)
    return binary


def make_client(tmp_path, fake_hermes, timeout=2, session=None):
    chat = ChatRunner(
        tmp_path / "server/jobs.sqlite", binary="hermes", timeout=timeout, session=session
    )
    # Usage never contacts the network, even if the production key is installed.
    usage = Usage(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))),
        env_path=tmp_path / "absent.env",
    )
    return TestClient(create_app(fixture_service(tmp_path), chat=chat, usage=usage)), chat


def wait(client, chat_id):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        result = client.get(f"/api/chat/{chat_id}").json()
        if result["status"] == "idle":
            return result
        time.sleep(0.01)
    pytest.fail(str(result))


def test_success_resume_late_ws_reload_and_argv(tmp_path, fake_hermes):
    client, chat = make_client(tmp_path, fake_hermes)
    prompt = "literal $(touch /tmp/SHOULD_NOT_EXIST) `id`; --resume nope\nsecond line"
    with client:
        response = client.post("/api/chat", json={"text": prompt})
        assert response.status_code == 202
        chat_id = response.json()["id"]
        result = wait(client, chat_id)
        assert result["session"] == "20261030_010203_fake"
        assistant = result["messages"][-1]
        assert assistant["text"] == "known reply: " + prompt
        assert assistant["exit_code"] == 0 and assistant["duration"] > 0
        assert assistant["usage"]["cost"] == 0.012
        assert assistant["usage"]["api_calls"] == 1
        assert assistant["usage"]["total_tokens"] == 105
        with client.websocket_connect(f"/api/chat/{chat_id}/stream") as ws:
            events = []
            while not events or events[-1]["type"] != "done":
                events.append(ws.receive_json())
        assert [e["type"] for e in events] == ["thinking", "message", "done"]
        assert events[-2]["data"]["text"] == assistant["text"]
        cursor = events[-2]["seq"]
        with client.websocket_connect(f"/api/chat/{chat_id}/stream?after={cursor}") as ws:
            assert ws.receive_json()["type"] == "done"
        assert (
            client.post("/api/chat", json={"text": "again", "chat_id": chat_id}).status_code == 202
        )
        result = wait(client, chat_id)
        assert result["messages"][-1]["text"] == "remembered"
        assert result["cost"] == 0.024
        assert client.get("/api/chats").json()["data"][0]["id"] == chat_id
    assert ChatStore(chat.store.path).get(chat_id)["messages"] == result["messages"]
    assert not os.path.exists("/tmp/SHOULD_NOT_EXIST")


def test_failure_timeout_busy_cancel(tmp_path, fake_hermes):
    client, _ = make_client(tmp_path, fake_hermes, timeout=0.25)
    with client:
        failed = client.post("/api/chat", json={"text": "fail"}).json()["id"]
        message = wait(client, failed)["messages"][-1]
        assert message["exit_code"] == 7 and "known failure" in message["error"]
        assert message["usage"]["cost"] == 0.012
        slow = client.post("/api/chat", json={"text": "slow"}).json()["id"]
        busy = client.post("/api/chat", json={"text": "no"})
        assert busy.status_code == 409 and busy.json()["detail"]["status"] == "busy"
        message = wait(client, slow)["messages"][-1]
        assert message["timed_out"] and "timed out" in message["error"]
        assert message["exit_code"] < 0
        cancelled = client.post("/api/chat", json={"text": "slow"}).json()["id"]
        time.sleep(0.05)
        result = client.post(f"/api/chat/{cancelled}/cancel").json()
        message = result["messages"][-1]
        assert message["cancelled"] and message["error"] == "Turn cancelled"
        assert client.post("/api/chat/missing/cancel").status_code == 404
        assert client.get("/api/chat/missing").status_code == 404


def test_validation_fixed_session_restart(tmp_path, fake_hermes):
    client, chat = make_client(tmp_path, fake_hermes, session="20261030_010203_fake")
    with client:
        for request in (
            {"text": "\x00"},
            {"text": "\x1b"},
            {"text": "\r"},
            {"text": "x" * 16001},
            {"text": " "},
            {"text": "ok", "session": "--bad"},
            {"text": "ok", "command": "id"},
        ):
            assert client.post("/api/chat", json=request).status_code == 422
        result = client.post("/api/chat", json={"text": "fixed"}).json()
        assert wait(client, result["id"])["messages"][-1]["text"] == "remembered"
        assert (
            client.post(
                "/api/chat", json={"text": "x", "chat_id": result["id"], "session": "different"}
            ).status_code
            == 422
        )
    with chat.store.db() as db:
        db.execute("UPDATE chats SET status='running' WHERE id=?", (result["id"],))
    client, _ = make_client(tmp_path, fake_hermes)
    with client:
        last = client.get("/api/chat/" + result["id"]).json()["messages"][-1]
        assert "Server restarted" in last["error"]


def test_usage_parser(tmp_path):
    path = tmp_path / "usage.json"
    assert parse_usage(path)[1]
    path.write_text(
        json.dumps(
            dict(
                estimated_cost_usd=0.12,
                api_calls=2,
                input_tokens=12,
                output_tokens=3,
                model="stub",
                total_tokens=15,
                total_including_auxiliary={"estimated_cost_usd": 0.13},
            )
        )
    )
    usage, error = parse_usage(path)
    assert error is None and usage["cost"] == 0.13 and usage["input_tokens"] == 12
    path.write_text('{"estimated_cost_usd": "secret"}')
    assert parse_usage(path)[1]


def test_credits_success_cache_stale_and_missing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    env = tmp_path / "hermes.env"
    env.write_text('OPENROUTER_API_KEY="test-private-key"\n')
    calls = []
    broken = False

    def respond(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer test-private-key"
        assert "test-private-key" not in str(request.url)
        if broken:
            raise httpx.ConnectError("upstream secret test-private-key", request=request)
        data = (
            dict(total_credits=70, total_usage=62.25)
            if request.url.path.endswith("credits")
            else dict(limit=None, usage_daily=0.07, usage_weekly=1.1, usage_monthly=12.25)
        )
        return httpx.Response(200, json={"data": data})

    usage = Usage(httpx.AsyncClient(transport=httpx.MockTransport(respond)), env_path=env)
    with TestClient(create_app(fixture_service(tmp_path), usage=usage)) as client:
        result = client.get("/api/usage").json()
        assert result["remaining"] == 7.75 and not result["stale"]
        assert result["percent_remaining"] == pytest.approx(100 * 7.75 / 70)
        assert result["usage_daily"] == 0.07 and result["hard_key_limit_set"] is False
        assert client.get("/api/usage").json() == result and len(calls) == 2
        broken = True
        usage.invalidate()
        stale = client.get("/api/usage").json()
        assert stale["stale"] and stale["remaining"] == 7.75
        assert stale["timestamp"] == result["timestamp"]
        assert "test-private-key" not in json.dumps(stale) and stale["error"]
        env.unlink()
        usage.invalidate()
        missing = client.get("/api/usage").json()
        assert missing["stale"] and missing["error"] == "OPENROUTER_API_KEY is unavailable"
        usage.reading = None
        usage.invalidate()
        missing = client.get("/api/usage").json()
        assert missing["remaining"] is None and missing["timestamp"] is None


def test_shared_store_lock_and_immediate_cancel(tmp_path, fake_hermes):
    from osrs_ml.server.chat import Busy, ChatRequest

    client, chat = make_client(tmp_path, fake_hermes)
    with client:
        other = ChatRunner(chat.store.path, binary="hermes")
        result = client.post("/api/chat", json={"text": "slow"}).json()
        with pytest.raises(Busy):
            other.submit(ChatRequest(text="must not spawn"))
        cancelled = client.post(f"/api/chat/{result['id']}/cancel").json()
        assert cancelled["messages"][-1]["cancelled"]
        assert cancelled["messages"][-1]["error"] == "Turn cancelled"
        assert (
            client.post("/api/chat", json={"chat_id": result["id"], "text": "retry"}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/chat",
                json={"chat_id": result["id"], "text": "retry", "session": "20261030_010203_fake"},
            ).status_code
            == 202
        )
        assert wait(client, result["id"])["messages"][-1]["text"] == "remembered"


def test_credits_key_limit_and_invalid_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-key")
    invalid = False

    def respond(request):
        data = (
            dict(total_credits="NaN" if invalid else 70, total_usage=62)
            if request.url.path.endswith("credits")
            else dict(limit=0, usage_daily=0.1, usage_weekly=1, usage_monthly=2)
        )
        return httpx.Response(200, json={"data": data})

    usage = Usage(httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    with TestClient(create_app(fixture_service(tmp_path), usage=usage)) as client:
        reading = client.get("/api/usage").json()
        assert reading["hard_key_limit_set"] is True and reading["hard_key_limit"] == 0
        invalid = True
        usage.invalidate()
        response = client.get("/api/usage")
        assert response.status_code == 200
        assert response.json()["stale"] and response.json()["remaining"] == 8
