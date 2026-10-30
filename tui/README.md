# osrs-term

A ratatui window manager for the Python OSRS research server. Rust only renders
server data and manages input, layout and connections. Tax, alchemy, capacity,
returns, execution, training and evaluation remain in `osrs_ml`.

From the repository root:

```bash
export PATH="$HOME/.cargo/bin:$PATH"
(cd ml && uv sync --frozen && uv run --frozen python -m osrs_ml.server --host 127.0.0.1 --port 8787)
# In another terminal:
cargo run --release --locked --manifest-path tui/Cargo.toml -- --server http://127.0.0.1:8787
# Or start both (reuses an already running server):
./scripts/osrs-term
```

`--server` overrides `OSRS_TERM_SERVER`, default `http://127.0.0.1:8787`.
`--view market|alchemy|candles|jobs|movers|models|collector|metrics` opens a single
window for inspection. Without it, the saved layout is restored. Configuration
uses `$XDG_CONFIG_HOME/osrs-term` or `~/.config/osrs-term`; `layout.json` stores
window positions/z-order and `state.json` stores selected chart/job/settings.
Corrupt configuration falls back to defaults. Geometry is clamped on resize,
including very small terminals. The terminal uses raw mode, alternate screen,
mouse capture and panic/normal-exit restoration.

## Controls

| Input | Action |
|---|---|
| `/`, Ctrl+P | Fuzzy command palette; Up/Down and Enter choose |
| Palette `item 4151` | Open candles for an item ID |
| Palette `metric net_gp` | Open a selected job metric series (any numeric metric key) |
| Palette Dataset / Track / Preset / Horizon | Configure subsequent jobs |
| Palette Start benchmark / eval / train / backtest | Submit a typed server job |
| Click panel | Focus and raise |
| Drag title / bottom-right 2×2 corner | Move / resize |
| Click title × / Ctrl+W | Close window; its server job continues |
| Wheel | Scroll the window under cursor without changing focus |
| Tab | Cycle focus |
| Arrows / Shift+Arrows | Move / resize focused window |
| `m` | Maximize focused window |
| `j` / `k` | Scroll; in Jobs, select next / previous job |
| `f` | Table filter; Enter ends editing, Esc clears |
| `s` | Market sort: item ID, net spread descending, buy descending |
| Enter in Market | Chart the first visible item |
| `1` / `2` / `3` in Candles | 5m / 1h / 1d |
| Hover chart | Crosshair, timestamp, OHLC-ready values and volume |
| `c` in Jobs | Cancel selected queued/running job |
| q / Esc / Ctrl+C | Exit client; jobs stay on server |

The palette also opens movers, alchemy, model results, collector health, research
battery (71 rules × 3 participation assumptions), participation and log console.
Jobs contain a status/progress list, metric chart and live stdout/stderr tail.
Click a job row or use j/k to attach. Closing the TUI and reopening restores the
selected job and replays its persisted events. Network failures leave the UI
running, mark cached data stale and retry with exponential backoff (up to 30s).
HTTP and WebSocket connections retry independently. Errors appear in Log console.

## Data and chart meaning

The server uses the Wiki API with a descriptive User-Agent, configurable through
`OSRS_WIKI_USER_AGENT`. Latest prices are cached for 60s, bulk/history for 300s,
mapping for one day. Each feed response includes error, stale, fetch time and age.
Set `OSRS_DATA_DIR` to use another research directory (default
`/home/martin/osrs-data`). No market observations or job databases belong in Git.

Wiki history contains bucket averages, not trade OHLC. Candles are explicitly
labelled **mean envelopes**: close is the side midpoint, open the previous
midpoint, and the envelope includes both side means and open. These values are
prepared by the server. Volume bars use the sum of reported side volumes. The
movers screener uses the existing battery's exact 5m midpoint return, sorted by
absolute change; missing preceding buckets stay absent.

Market green/red spread is a hypothetical low purchase / high sale after the
existing per-item tax. It is not an instant executable round trip. Alchemy shows
the four frozen direct-alchemy candidates using the existing mechanical-ceiling
reference economics and capacity assumptions on completed 5m means. Capacity is
conditional and shares time, rune volume and capital; rows are not additive.

Model results show saved development metrics and exclude holdout directories.
The metrics chart connects evaluation artifact events, not optimizer iterations.
Artifact progress is an estimate until the subprocess finishes. There is no new
fine-tuning algorithm or optimizer telemetry: `train` saves the CatBoost models
from the existing comparison harness.

## Server and jobs

```bash
curl -s http://127.0.0.1:8787/api/health
curl -s http://127.0.0.1:8787/api/alch/gaps
curl -s -X POST http://127.0.0.1:8787/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"kind":"benchmark","params":{"dataset":"synthetic","horizon_hours":1}}'
```

Interactive endpoint schemas: `http://127.0.0.1:8787/docs`. Reads include health,
items, latest/history/movers, alchemy, battery, participation, collector, models
and config. Jobs expose POST/GET `/api/jobs`, GET `/api/jobs/{id}`, POST
`/api/jobs/{id}/cancel`, and WS `/api/jobs/{id}/stream?after=SEQUENCE`.
Events carry a global monotonically increasing `seq`, job ID, timestamp, type
(`log`, `metric`, `status`) and data. Cursors replay stdout/stderr and metrics
without dependence on a connected client. Logs and metrics are retained in
`$OSRS_DATA_DIR/server/jobs.sqlite`; outputs live under `ml/runs/server/`.

Only four registered job kinds are accepted. All invoke an existing comparison harness: synthetic jobs use
`uv run --frozen osrs-ml run`; development jobs use `osrs-ml research` on a
predicate-sealed copy. Both fit saved CatBoost models, evaluate forecasts and
backtest the existing baselines. A benchmark is
one timed invocation of that suite; it is not a separate hardware benchmark.
Parameters are strictly typed with unknown fields rejected:

- `dataset`: `synthetic` (default) or `development`.
- `horizon_hours`: 1 (default), 4, 24. Daily development requires 24. Choosing that
  dataset in the palette sets horizon=24, track=frozen_daily and preset=all.
- `track`: `price_only` (default), `full_feature`; development requires `frozen_daily`.
- `preset`: `conservative` (default), `moderate`, `optimistic`; development requires `all`.
- `cash_gp`: integer 1,000–100,000,000 (default 10,000,000).

Synthetic is the deterministic existing fixture and only demonstrates execution.
Development always reads the fixed `assembled-v3/daily.parquet` through the
existing predicate-sealed reader, with the frozen research start/cutoff from
`alchemy.registration()`. It preserves availability and provenance. The existing daily research harness acknowledges unknown
source intervals and reports both strict unknown-limit and current-limit
sensitivity scenarios. The server copies the existing daily experiment config
with two 14-day development folds, cash from the request, and zero additional
holdout days because the snapshot is already sealed. It compares the frozen
daily feature/model suite across all three execution presets. These settings
are explicit in the typed request; incompatible intraday track/preset settings
are rejected for daily data. Current-limit sensitivity is labelled by the
existing harness and is not historical point-in-time metadata. There are no path, shell, arbitrary
CLI, config or holdout request fields. The worker receives only the sealed
snapshot, never the source panel. Models cannot request the holdout.

Concurrency is `OSRS_JOB_CONCURRENCY` (default 1), FIFO. Kind timeouts are 30m
backtest, 1h eval/benchmark and 2h train, including input preparation. Cancellation
sends SIGTERM to the subprocess group, then SIGKILL after 3s if needed. Queued
jobs and history survive a restart. Graceful server shutdown cancels active jobs;
an interrupted running record after abrupt restart is marked failed explicitly.
A TUI disconnect does not stop a job. The convenience script owns and stops only
the server it started, so use a separately managed server for persistent jobs
after exiting that script. The API is intended for a trusted local connection.

## Verification

```bash
uv run --project ml --frozen pytest ml/tests -q
uv run --project ml --frozen ruff check ml/src/osrs_ml/server ml/tests/test_server*.py
cargo test --locked --manifest-path tui/Cargo.toml
cargo build --release --locked --manifest-path tui/Cargo.toml
```

Window hit regions, topmost targeting, drag/resize clamping, fuzzy search and
chart cursor arithmetic have pure unit tests. Server tests use fixture data,
mocked Wiki HTTP and real short subprocesses for success, failure, disconnect,
replay, cancellation, queueing, timeout, restart and sealed-input guardrails.

## Hermes chat

Open **Hermes chat** in the command palette or launch `./scripts/osrs-term --view chat`.
The pane restores its selected conversation after restart; **Chat: new conversation**
starts another and **Chat: next conversation** cycles the server's saved conversations.
`OSRS_TERM_CHAT_ID` can select a particular saved chat on launch. Multiple chat
windows show the selected conversation, like the existing job/chart windows.

Type in the bordered input, press Enter to send, Alt+Enter or Ctrl+J for a newline,
and Esc to leave input (the panel stays open). Enter or `i` re-enters input; clicking
the panel also enters input. Left/Right, Up/Down, Home/End, Backspace and Delete edit
multiline text. Mouse wheel scrolls the transcript while the credit display and
input stay fixed. Ctrl+X or Ctrl+C cancels a turn while editing; the UI stays live
throughout the run. Esc then Ctrl+P opens the palette. The session ID is displayed
above the transcript; this conversation is separate from other Hermes chats.

The Python server invokes `/home/martin/.local/bin/hermes` using argv, with
`--resume ID` **before** `-z PROMPT`. On the first turn it resolves the newest
non-cron ID from `hermes sessions list`. A failed discovery is visible and blocks
continuation until a session is supplied, avoiding an accidental fresh conversation.
Server configuration:

- `OSRS_HERMES_BIN`: trusted executable path (default above).
- `OSRS_HERMES_SESSION`: fixed existing Hermes session ID for new conversations.
- `OSRS_CHAT_TIMEOUT`: turn timeout in seconds (default 180).
- `OSRS_CHAT_MODEL`: optional Hermes model override; otherwise Hermes safe-mode
  defaults / `HERMES_INFERENCE_MODEL` apply.
- `OSRS_TERM_PORT`: local server port for the launcher (default 8787).

Chat uses Hermes v0.21.5's empty `bot_room` toolset with `--safe-mode` in an empty
workspace, disabling file/terminal tools, delegation, plugins, MCP, hooks and rule
injection. It is a text conversation with the agent; it cannot run commands or
read research inputs. Safe mode skips the normal Hermes config, so set the model
explicitly to retain your usual choice. For example, start both server and TUI:

```bash
OSRS_TERM_PORT=8788 OSRS_CHAT_MODEL='~deepseek/deepseek-flash-latest' ./scripts/osrs-term --view chat
```

POST `/api/chat` accepts `text`, optional `session`, and optional `chat_id` for a
subsequent turn in a persisted conversation. GET `/api/chat/{id}` reloads the full
transcript; GET `/api/chats` lists conversations. WS `/api/chat/{id}/stream?after=N`
replays durable `thinking`, `log` (when Hermes emits stderr), `message`, and `done`
events, including results produced before attachment. POST `/api/chat/{id}/cancel`
terminates the process group. The server rejects overlapping turns with HTTP 409
`detail.status=busy`; there is no automatic queue or retry of a prompt. Prompts
are limited to 16,000 characters and reject control characters other than newline
and tab. Output capture is bounded to 1 MiB per channel. Abrupt restart records an
interrupted turn as failed; normal shutdown cancels it.

Chats, messages, timings, exit status, timeout/cancel flags and Hermes usage reports
live in the existing `$OSRS_DATA_DIR/server/jobs.sqlite`, outside Git. Estimated
per-turn cost, token counters, API calls and model come from a private temporary
`--usage-file`; an absent report is marked unknown. Newer reports' aggregate cost
includes auxiliary work such as title generation. The chat total is marked
incomplete when any turn lacks usage.

GET `/api/usage` reads OpenRouter `/api/v1/credits` and `/api/v1/key`, with a Bearer
key loaded privately from `OPENROUTER_API_KEY` or `~/.hermes/.env`. It returns total,
used, remaining, percentage, daily/weekly/monthly spend, key-limit information and
the reading timestamp. The server caches it for 60 seconds and invalidates after
chat completion. Failures return the last reading with `stale=true` and a visible
error, or null balances if none was fetched. The pane marks stale/offline readings
explicitly, uses green/amber (<25%)/red (<10%) and shows today's spend, this chat's
estimated cost and the last turn's cost. No credential or credential fragment is
returned or displayed.

Chat/usage tests use an executable fake Hermes on PATH and mocked OpenRouter HTTP;
they never invoke the real agent or billing API:

```bash
cd ml && uv run --frozen pytest tests/test_server_chat.py -q
```
