"""Bounded, durable agent conversations. Prompts are always single argv elements."""

import asyncio
import fcntl
import json
import math
import os
import re
import signal
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from .jobs import Store

SESSION = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["hermes", "codex"] | None = None
    workdir: str | None = Field(default=None, max_length=4096)
    allow_writes: StrictBool | None = None
    text: str = Field(min_length=1, max_length=16000)
    session: str | None = Field(default=None, pattern=f"^{SESSION}$")
    chat_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

    @field_validator("text")
    @classmethod
    def clean_text(cls, text):
        if not text.strip():
            raise ValueError("Prompt is empty")
        if any(
            (ord(c) < 32 and c not in "\n\t") or 127 <= ord(c) < 160 or 0xD800 <= ord(c) <= 0xDFFF
            for c in text
        ):
            raise ValueError("Prompt contains control characters or invalid Unicode")
        return text


def parse_usage(path):
    """Keep the original counters and report missing/malformed cost as unknown, never zero."""
    try:
        report = json.loads(Path(path).read_text())
        keys = (
            "estimated_cost_usd",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "total_tokens",
            "api_calls",
            "model",
        )
        result = {k: report.get(k) for k in keys}
        for k, value in result.items():
            if k != "model" and value is not None:
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid usage counter")
        # Newer Hermes includes title-generation spend in this aggregate.
        total = report.get("total_including_auxiliary", {})
        result["cost"] = total.get("estimated_cost_usd", result["estimated_cost_usd"])
        cost = result["cost"]
        if cost is not None and (
            not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0
        ):
            raise ValueError("Invalid total cost")
        return result, None
    except (OSError, ValueError, TypeError, AttributeError):
        return {}, "Hermes usage report missing or invalid"


def route_target(requested, existing=None):
    """A changed target always allocates a fresh conversation."""
    target = requested or (existing and existing["target"]) or "hermes"
    return target, bool(existing and existing["target"] != target)


def codex_argv(workdir, session, writes, prompt):
    args = [
        "exec",
        "--json",
        "--skip-git-repo-check",
        "-s",
        "workspace-write" if writes else "read-only",
        "-C",
        workdir,
    ]
    if session:
        args += ["resume", session]
    return args + ["--", prompt]


def parse_codex(output, expected=None):
    session, texts, usage = None, [], {}
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started":
            candidate = event.get("thread_id")
            try:
                candidate = str(uuid.UUID(candidate))
            except (ValueError, TypeError, AttributeError):
                raise ValueError("Invalid Codex session UUID") from None
            if session and session != candidate:
                raise ValueError("Conflicting Codex session UUIDs")
            session = candidate
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                texts.append(item.get("text", ""))
        if event.get("type") == "turn.completed":
            counters = event.get("usage", {})
            for key in (
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
                "reasoning_output_tokens",
                "total_tokens",
            ):
                value = counters.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    usage[key] = value
        if event.get("type") in ("turn.failed", "error"):
            raise ValueError(
                f"Codex reported failure: {str(event.get('error', event.get('message', 'unknown')))[:1000]}"
            )
    if not session:
        raise ValueError("Codex session UUID missing from JSON stream; cannot continue safely")
    if expected and session != expected:
        raise ValueError("Codex resumed a different session")
    return session, "\n".join(texts), usage


class ChatStore(Store):
    def __init__(self, path):
        super().__init__(path)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, session TEXT, created_at REAL, updated_at REAL,
                    status TEXT NOT NULL DEFAULT 'idle');
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL,
                    role TEXT NOT NULL, text TEXT NOT NULL, created_at REAL,
                    started_at REAL, finished_at REAL, duration REAL, exit_code INTEGER,
                    timed_out INTEGER DEFAULT 0, cancelled INTEGER DEFAULT 0,
                    usage TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS chat_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL,
                    timestamp REAL, type TEXT, data TEXT);
                CREATE INDEX IF NOT EXISTS chat_event_id ON chat_events(chat_id, seq);
            """)

            for table, columns in {
                "chats": {
                    "target": "TEXT NOT NULL DEFAULT 'hermes'",
                    "workdir": "TEXT",
                    "agent_session": "TEXT",
                    "allow_writes": "INTEGER NOT NULL DEFAULT 0",
                },
                "chat_messages": {"target": "TEXT", "workdir": "TEXT", "sandbox": "TEXT"},
            }.items():
                present = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
                for name, spec in columns.items():
                    if name not in present:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")
            db.execute(
                "UPDATE chats SET agent_session=session WHERE agent_session IS NULL AND session IS NOT NULL"
            )

    def list(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM chats ORDER BY updated_at DESC")]

    def get(self, chat_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
            if row is None:
                return None
            messages = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM chat_messages WHERE chat_id=? ORDER BY id", (chat_id,)
                )
            ]
        for message in messages:
            message["usage"] = json.loads(message["usage"] or "{}")
        costs = [m["usage"].get("cost") for m in messages if m["role"] == "assistant"]
        return {
            **dict(row),
            "messages": messages,
            "cost": sum(c for c in costs if c is not None) if row["target"] == "hermes" else None,
            "cost_incomplete": row["target"] == "hermes" and any(c is None for c in costs),
        }

    def event(self, chat_id, kind, data):
        with self.db() as db:
            db.execute(
                "INSERT INTO chat_events(chat_id,timestamp,type,data) VALUES(?,?,?,?)",
                (chat_id, time.time(), kind, json.dumps(data, allow_nan=False)),
            )

    def events(self, chat_id, after=0):
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM chat_events WHERE chat_id=? AND seq>? ORDER BY seq LIMIT 1000",
                (chat_id, after),
            ).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    def finish(
        self,
        chat_id,
        text,
        started,
        code=None,
        timed_out=False,
        cancelled=False,
        usage=None,
        error=None,
    ):
        now = time.time()
        with self.db() as db:
            db.execute(
                """INSERT INTO chat_messages
                (chat_id,role,text,created_at,started_at,finished_at,duration,exit_code,
                 timed_out,cancelled,usage,error) VALUES(?,'assistant',?,?,?,?,?,?,?,?,?,?)""",
                (
                    chat_id,
                    text,
                    now,
                    started,
                    now,
                    now - started,
                    code,
                    timed_out,
                    cancelled,
                    json.dumps(usage or {}),
                    error,
                ),
            )
            db.execute(
                """UPDATE chat_messages SET target=(SELECT target FROM chats WHERE id=?),
                       workdir=(SELECT workdir FROM chats WHERE id=?),
                       sandbox=(SELECT CASE WHEN target='codex' THEN CASE WHEN allow_writes=1 THEN 'workspace-write' ELSE 'read-only' END ELSE NULL END FROM chats WHERE id=?)
                       WHERE id=last_insert_rowid()""",
                (chat_id, chat_id, chat_id),
            )
            db.execute("UPDATE chats SET status='idle',updated_at=? WHERE id=?", (now, chat_id))
        self.event(chat_id, "message", self.get(chat_id)["messages"][-1])
        self.event(
            chat_id,
            "done",
            {"status": "cancelled" if cancelled else "failed" if error else "succeeded"},
        )


class Busy(Exception):
    pass


class ChatRunner:
    def __init__(self, path, binary=None, timeout=None, session=None):
        self.store = ChatStore(path)
        self.binary = binary or os.getenv("OSRS_HERMES_BIN", "/home/martin/.local/bin/hermes")
        self.codex_binary = os.getenv("OSRS_CODEX_BIN", "codex")
        self.codex_timeout = float(os.getenv("OSRS_CODEX_TIMEOUT", "600"))
        if not math.isfinite(self.codex_timeout) or self.codex_timeout <= 0:
            raise ValueError("Codex timeout must be positive and finite")
        self.timeout = float(
            timeout if timeout is not None else os.getenv("OSRS_CHAT_TIMEOUT", "180")
        )
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Chat timeout must be positive and finite")
        self.session = session or os.getenv("OSRS_HERMES_SESSION")
        if self.session and not re.fullmatch(SESSION, self.session):
            raise ValueError("Invalid configured Hermes session ID")
        self.task = None
        self.chat_id = None
        self.process = None
        self.cancelled = False
        self.lock = None
        # Empty workspace: no repository rules or market input is passed to Hermes.
        self.workspace = Path(path).parent / "chat-workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def acquire(self):
        lock = open(self.store.path.with_suffix(".chat.lock"), "a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise Busy("Chat is busy: global cap of one turn is already running") from None
        return lock

    async def start(self):
        try:
            lock = self.acquire()
        except Busy:
            return
        try:
            for chat in self.store.list():
                if chat["status"] == "running":
                    messages = self.store.get(chat["id"])["messages"]
                    self.store.finish(
                        chat["id"],
                        "",
                        messages[-1]["created_at"],
                        error="Server restarted during turn; result unavailable",
                    )
        finally:
            lock.close()

    def submit(self, request):
        if self.task and not self.task.done():
            raise Busy("Chat is busy: global cap of one turn is already running")
        self.lock = self.acquire()
        try:
            chat = self.store.get(request.chat_id) if request.chat_id else None
            if request.chat_id and chat is None:
                raise KeyError("Unknown chat")
            target, switched = route_target(request.target, chat)
            previous = chat
            if switched:
                chat = None
            session = (
                request.session
                or (chat and chat["agent_session"])
                or (self.session if target == "hermes" else None)
            )
            if target == "codex" and request.session:
                raise ValueError("Codex session IDs are captured from its JSON stream")
            if chat and not session:
                raise ValueError("Session unresolved; supply a session ID before continuing")
            if chat and request.session and chat["agent_session"] not in (None, request.session):
                raise ValueError("Session differs from this conversation; start a new chat")
            workdir = None
            writes = False
            if target == "codex":
                workdir = str(
                    Path(
                        request.workdir
                        or (chat and chat["workdir"])
                        or os.getenv("OSRS_CODEX_WORKDIR", str(self.workspace))
                    ).resolve()
                )
                if not Path(workdir).is_dir():
                    raise ValueError("Codex workdir must be an existing directory")
                if chat and workdir != chat["workdir"]:
                    raise ValueError("Workdir differs; start a new conversation")
                writes = (
                    request.allow_writes
                    if request.allow_writes is not None
                    else bool(chat and chat["allow_writes"])
                )
            elif request.allow_writes or request.workdir:
                raise ValueError("Workdir and writes apply only to Codex")
            chat_id = chat["id"] if chat else uuid.uuid4().hex
            now = time.time()
            with self.store.db() as db:
                db.execute(
                    "INSERT OR IGNORE INTO chats(id,session,created_at,updated_at,target,workdir,agent_session,allow_writes) VALUES(?,?,?,?,?,?,?,?)",
                    (chat_id, session, now, now, target, workdir, session, writes),
                )
                db.execute(
                    "UPDATE chats SET status='running',session=?,agent_session=?,allow_writes=?,updated_at=? WHERE id=?",
                    (session, session, writes, now, chat_id),
                )
                if not chat and (request.target is not None or previous):
                    confirmation = f"new conversation with {target}"
                    if target == "codex":
                        confirmation += (
                            f", workdir {workdir}, {'workspace-write' if writes else 'read-only'}"
                        )
                    db.execute(
                        "INSERT INTO chat_messages(chat_id,role,text,created_at) VALUES(?,'system',?,?)",
                        (chat_id, confirmation, now),
                    )
                db.execute(
                    "INSERT INTO chat_messages(chat_id,role,text,created_at) VALUES(?,'user',?,?)",
                    (chat_id, request.text, now),
                )
            self.chat_id, self.cancelled = chat_id, False
            self.store.event(chat_id, "thinking", {"started_at": now})
            self.task = asyncio.create_task(self.run(chat_id, request.text, session, now))
            return self.store.get(chat_id)
        except BaseException:
            self.lock.close()
            self.lock = None
            raise

    async def terminate(self):
        process = self.process
        if process:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    await asyncio.wait_for(process.wait(), 3)
                finally:
                    # Descendants can outlive the parent or ignore SIGTERM.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            except (TimeoutError, ProcessLookupError):
                pass
            await process.wait()

    async def cancel(self, chat_id):
        if self.chat_id == chat_id and self.task and not self.task.done():
            self.cancelled = True
            await self.terminate()
            await self.task
        return self.store.get(chat_id)

    async def close(self):
        if self.task and not self.task.done():
            await self.cancel(self.chat_id)

    async def execute(self, argv, timeout, binary=None, cwd=None, stream_stdout=False):
        self.process = await asyncio.create_subprocess_exec(
            binary or self.binary,
            *argv,
            cwd=cwd or self.workspace,
            start_new_session=True,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if self.cancelled:
            await self.terminate()

        # Bound each captured channel to 1 MiB while still draining the pipes.
        async def drain(pipe, channel):
            kept = bytearray()
            while chunk := await pipe.read(4096):
                room = max(0, 1048576 - len(kept))
                kept.extend(chunk[:room])
                if (channel == "stderr" or stream_stdout) and room:
                    self.store.event(
                        self.chat_id,
                        "log",
                        {"channel": channel, "text": chunk.decode(errors="replace")[:4096]},
                    )
            return kept.decode(errors="replace")

        captures = asyncio.gather(
            drain(self.process.stdout, "stdout"), drain(self.process.stderr, "stderr")
        )
        timed_out = False
        completion = asyncio.gather(self.process.wait(), captures)
        try:
            await asyncio.wait_for(asyncio.shield(completion), timeout)
        except TimeoutError:
            timed_out = True
            await self.terminate()
        await completion
        stdout, stderr = await captures
        return stdout, stderr, self.process.returncode, timed_out

    async def run(self, chat_id, text, session, started):
        output, error, code, timed_out, usage = "", None, None, False, {}
        target = self.store.get(chat_id)["target"]
        try:
            if target == "codex":
                chat = self.store.get(chat_id)
                output, stderr, code, timed_out = await self.execute(
                    codex_argv(chat["workdir"], session, chat["allow_writes"], text),
                    self.codex_timeout,
                    binary=self.codex_binary,
                    cwd=chat["workdir"],
                    stream_stdout=True,
                )
                session, output, usage = parse_codex(output, session)
                with self.store.db() as db:
                    db.execute(
                        "UPDATE chats SET session=?,agent_session=? WHERE id=?",
                        (session, session, chat_id),
                    )
                if self.cancelled:
                    error = "Turn cancelled"
                elif timed_out:
                    error = f"Codex timed out after {self.codex_timeout:g}s"
                elif code != 0:
                    error = f"Codex exited with status {code}: {stderr.strip()[:2000]}"
                elif not output.strip():
                    error = "Codex returned an empty response"
                return
            with tempfile.TemporaryDirectory(prefix="osrs-chat-") as directory:
                usage_path = Path(directory) / "usage.json"
                # bot_room is Hermes v0.21.5's built-in empty toolset. Safe mode disables
                # plugins, MCP, hooks, rules and memories: no execution, delegation or file tools.
                argv = ["--safe-mode", "-t", "bot_room", "--no-restore-cwd"]
                model = os.getenv("OSRS_CHAT_MODEL")
                if model:
                    argv += ["--model", model]
                if session:
                    argv += ["--resume", session]
                argv += ["--usage-file", str(usage_path), "-z", text]
                output, stderr, code, timed_out = await self.execute(argv, self.timeout)
                usage, usage_error = parse_usage(usage_path)
                if self.cancelled:
                    error = "Turn cancelled"
                elif timed_out:
                    error = f"Hermes timed out after {self.timeout:g}s"
                elif code != 0:
                    error = f"Hermes exited with status {code}: {stderr.strip()[:2000]}"
                elif not output.strip():
                    error = "Hermes returned an empty response"
                if usage_error:
                    usage["error"] = usage_error
                if not session and not self.cancelled:
                    # Hermes list is ordered by last activity. Skip cron and decoration rows.
                    listing, _, list_code, list_timeout = await self.execute(
                        ["sessions", "list"], 15
                    )
                    if list_code == 0 and not list_timeout:
                        for line in listing.splitlines():
                            parts = line.split()
                            candidate = parts[-1] if parts else ""
                            if re.fullmatch(r"\d{8}_\d{6}_[A-Za-z0-9]+", candidate):
                                session = candidate
                                break
                    if not session:
                        error = (error + "; " if error else "") + "Session discovery failed"
                    else:
                        with self.store.db() as db:
                            db.execute(
                                "UPDATE chats SET session=?,agent_session=? WHERE id=?",
                                (session, session, chat_id),
                            )
        except Exception as exc:
            if target == "codex":
                output = ""
            error = f"{target} turn failed ({type(exc).__name__}): {exc}"
        finally:
            if self.cancelled:
                error = "Turn cancelled"
            self.store.finish(
                chat_id, output.strip(), started, code, timed_out, self.cancelled, usage, error
            )
            self.process = None
            self.chat_id = None
            self.lock.close()
            self.lock = None
