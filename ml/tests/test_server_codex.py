"""Both executables are fakes on PATH; no real agents or billable requests."""

import json
import os
import sys
import time

import pytest
from test_server_chat import make_client, wait

from osrs_ml.server.chat import ChatRequest, codex_argv, parse_codex, route_target

pytest_plugins = ["test_server_chat"]

SID = "12345678-1234-4234-8234-123456789abc"


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    binary = tmp_path / "codex"
    binary.write_text(f'''#!{sys.executable}
import json, pathlib, subprocess, sys, time
args=sys.argv[1:]
assert args[0] == 'exec' and '--json' in args
assert '--dangerously-bypass-approvals-and-sandbox' not in args
assert '--last' not in args
assert args[-2] == '--'
assert args[args.index('-s')+1] in ('read-only','workspace-write')
assert pathlib.Path(args[args.index('-C')+1]).resolve() == pathlib.Path.cwd()
if 'resume' in args:
    assert args[args.index('resume')+1] == '{SID}'
with open({str(tmp_path / "argv.jsonl")!r},'a') as f: f.write(json.dumps(args)+'\\n')
prompt=args[-1]
if prompt == 'missing-session':
    print('{{"type":"turn.completed","usage":{{}}}}')
    sys.exit(0)
print(json.dumps({{"type":"thread.started","thread_id":"{SID}"}}),flush=True)
print('{{"type":"turn.started"}}',flush=True)
if prompt == 'slow':
    child=subprocess.Popen([sys.executable,'-c',"import time; time.sleep(30)"])
    pathlib.Path({str(tmp_path / "child.pid")!r}).write_text(str(child.pid))
    time.sleep(30)
print(json.dumps({{"type":"item.completed","item":{{"type":"agent_message","text":'resumed' if 'resume' in args else prompt}}}}))
print('{{"type":"turn.completed","usage":{{"input_tokens":21,"cached_input_tokens":10,"output_tokens":3}}}}')
''')
    binary.chmod(0o755)
    monkeypatch.setenv("OSRS_CODEX_BIN", "codex")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    return binary


def test_routing_and_argv():
    assert route_target(None) == ("hermes", False)
    assert route_target(None, {"target": "codex"}) == ("codex", False)
    assert route_target("codex", {"target": "hermes"}) == ("codex", True)
    for writes, mode in [(False, "read-only"), (True, "workspace-write")]:
        args = codex_argv("/tmp/a b", SID, writes, "$(id); `pwd` --last")
        assert args[args.index("-s") + 1] == mode
        assert args[-1] == "$(id); `pwd` --last" and args[-2] == "--"
    with pytest.raises(ValueError, match="missing"):
        parse_codex('{"type":"turn.completed"}')
    with pytest.raises(ValueError, match="Invalid"):
        parse_codex('{"type":"thread.started","thread_id":"oops"}')
    with pytest.raises(ValueError, match="different"):
        parse_codex(json.dumps(dict(type="thread.started", thread_id=SID)), "different")


def test_codex_resume_writes_switch_and_usage(tmp_path, fake_hermes, fake_codex):
    client, runner = make_client(tmp_path, fake_hermes)
    with client:
        prompt = "literal $(touch /tmp/CODEX_SHOULD_NOT_EXIST); `id` --last\nnext"
        response = client.post(
            "/api/chat", json=dict(text=prompt, target="codex", workdir=str(tmp_path))
        )
        assert response.status_code == 202
        first = wait(client, response.json()["id"])
        assert first["agent_session"] == SID and first["target"] == "codex"
        assert first["messages"][0]["text"].endswith("read-only")
        msg = first["messages"][-1]
        assert msg["text"] == prompt and msg["target"] == "codex"
        assert msg["workdir"] == str(tmp_path) and msg["sandbox"] == "read-only"
        assert msg["usage"] == dict(input_tokens=21, cached_input_tokens=10, output_tokens=3)
        assert first["cost"] is None and "cost" not in msg["usage"]
        response = client.post(
            "/api/chat", json=dict(chat_id=first["id"], text="again", allow_writes=True)
        )
        second = wait(client, response.json()["id"])
        assert second["agent_session"] == SID and second["messages"][-1]["text"] == "resumed"
        assert second["messages"][-1]["sandbox"] == "workspace-write"
        calls = [json.loads(x) for x in (tmp_path / "argv.jsonl").read_text().splitlines()]
        assert "resume" not in calls[0] and SID in calls[1]
        assert calls[1][calls[1].index("-s") + 1] == "workspace-write"
        switched = client.post(
            "/api/chat", json=dict(chat_id=first["id"], target="hermes", text="hello")
        ).json()
        hermes = wait(client, switched["id"])
        assert hermes["id"] != first["id"] and hermes["target"] == "hermes"
        assert hermes["agent_session"] == "20261030_010203_fake"
        assert hermes["messages"][-1]["usage"]["cost"] == 0.012
        assert client.get("/api/chat/" + first["id"]).json()["target"] == "codex"
        usage = client.get("/api/usage?target=codex").json()
        assert usage["plan"] == "ChatGPT Plus" and usage["billing_model"] == "subscription"
        assert "remaining" not in usage and "cost" not in usage
        assert any(e["type"] == "log" for e in runner.store.events(first["id"]))
    assert not os.path.exists("/tmp/CODEX_SHOULD_NOT_EXIST")


def test_missing_session_fails_visibly_and_cannot_silently_restart(
    tmp_path, fake_hermes, fake_codex
):
    client, _ = make_client(tmp_path, fake_hermes)
    with client:
        started = client.post("/api/chat", json=dict(target="codex", text="missing-session")).json()
        result = wait(client, started["id"])
        assert "session UUID missing" in result["messages"][-1]["error"]
        assert result["agent_session"] is None
        assert (
            client.post("/api/chat", json=dict(chat_id=result["id"], text="again")).status_code
            == 422
        )


@pytest.mark.parametrize("cancel", [True, False])
def test_codex_timeout_cancel_kills_process_group(
    tmp_path, fake_hermes, fake_codex, monkeypatch, cancel
):
    monkeypatch.setenv("OSRS_CODEX_TIMEOUT", "0.3" if not cancel else "5")
    client, _ = make_client(tmp_path, fake_hermes)
    with client:
        started = client.post("/api/chat", json=dict(target="codex", text="slow")).json()
        until = time.monotonic() + 2
        while not (tmp_path / "child.pid").exists() and time.monotonic() < until:
            time.sleep(0.01)
        pid = int((tmp_path / "child.pid").read_text())
        assert client.post("/api/chat", json=dict(target="hermes", text="busy")).status_code == 409
        if cancel:
            result = client.post(f"/api/chat/{started['id']}/cancel").json()
        else:
            result = wait(client, started["id"])
        msg = result["messages"][-1]
        assert msg["cancelled"] if cancel else msg["timed_out"]
        assert msg["error"] and msg["exit_code"] < 0
        status = __import__("pathlib").Path(f"/proc/{pid}/stat")
        assert not status.exists() or status.read_text().split()[2] == "Z"


def test_codex_validation():
    for kwargs in [dict(target="other"), dict(allow_writes="yes"), dict(workdir="a" * 4097)]:
        with pytest.raises(ValueError):
            ChatRequest(text="x", **kwargs)
