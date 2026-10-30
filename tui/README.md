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
`--view market|alchemy|candles|jobs|movers|models|collector|metrics|chat|TAS|QM|HCP|HMAP|MOST|EQS|COMP|AL` opens a single
window for inspection. Without it, the saved layout is restored. Configuration
uses `$XDG_CONFIG_HOME/osrs-term` or `~/.config/osrs-term`; `layout.json` stores
window positions/z-order and `state.json` stores selected chart/job/settings.
Corrupt configuration falls back to defaults. Geometry is clamped on resize,
including very small terminals. The terminal uses raw mode, alternate screen,
mouse capture and panic/normal-exit restoration.

## Controls

F1 opens the complete, scrollable help overlay. Commands are entered in the palette.

| Input | Action |
|---|---|
| `` ` ``, `/`, Ctrl+P | Command palette; arrows and Enter choose |
| F1 | Help; Esc dismisses; j/k, arrows and PageUp/PageDown scroll |
| Tab / Shift+Tab | Cycle focus forward / backward |
| Arrows / Shift+arrows | Move focused window |
| Alt+arrows | Resize focused window |
| Ctrl+Shift+arrows | Snap focused window to an edge |
| Alt+Shift+arrows | Resize focused window to an edge |
| Drag title / bottom-right corner | Move / resize |
| Ctrl+W / title × / double Esc | Close focused window |
| Ctrl+Z | Undo last close, including ticker, links, geometry and studies |
| `m` | Fullscreen |
| `q` / Ctrl+C | Exit client; server jobs continue |
| `f`, Enter, Esc | Edit table name filter, finish, clear |
| `s` | Cycle table rank; HMAP toggles net margin / 1d change colour |
| `j` / `k`, wheel | Scroll tables; select Jobs; chart j/k pans buckets |
| Enter in market / TAS / QM / HCP / MOST / EQS | Chart selected row and update linked ticker |
| **C / S / I / R** in chart | Style / scale / indicator / range picker |
| Right click chart | Scale menu |
| Wheel / `+` / `-` in chart | Zoom time axis |
| Drag chart body | Pan time axis |
| Hover chart | Mean, UTC timestamp and volume cursor |
| `1` / `2` / `3` / `4` / `5` / `6` | 5m / 15m / 30m / 1h / 1d / 1w |
| `c` in Jobs | Cancel selected job |

Palette commands:

```text
G / GP / GPL             Line chart
GIP                      5m intraday chart
GPO / GPC / GPF           Bars / Candles / Area
Style: Heikin Ashi        Any of the eleven named styles
Scale: percent           linear / percent / indexed / logarithmic
Scale: invert            Toggle scale inversion
Scale: axis left         Toggle price-axis position
Scale: auto fit          Toggle visible-range fit / frozen vertical bounds
Scale: lock ratio        Lock price-to-bar geometry
Scale: price only        Exclude/include overlays in auto-fit bounds
Range: 5y                5y / 1y / 6m / 3m / 1m / 5d / 1d
Resolution: 1w           Independent of the range
Indicator: MACD          Toggle SMA / EMA / BOLL / RSI / MACD / VWAP
item 4151                Change focused ticker and same-colour windows
Link: red                red / green / blue / yellow / magenta / none
date 2025-01-15          End the chart range at this UTC date
box 100                  Fixed Renko / P&F box; Kagi reverses at 3 boxes
TAS / QM / HCP / HMAP / MOST / EQS / COMP / AL
watch 855,561,4151        Open/set QM watchlist
compare 855,859,4151      Open/set comparison of up to five items
screen spread=10 volume=100 alch=0 members=free limit=1:10000
screen reset             Clear EQS constraints; s changes ranking
alert price above 1000   Save one-shot threshold for focused ticker
alert spread below 10    Also supports alch_gap; comparisons are inclusive
alert delete 1           Remove an alert, armed or fired
metric net_gp            Open a selected server job metric
```

Each window persists its own ticker, link colour and settings in `layout.json`.
Joining a colour group publishes the focused ticker to that group. Changing a
linked ticker updates other charts, makes TAS follow that item, includes it in
QM, and replaces COMP's first item. Market-wide ranking and heatmap panels keep
their universe while retaining the linked selection. Unlinked windows stay
independent. A newly opened window inherits the focused ticker and colour.

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

All eleven styles work with observed means: Line, Area, Baseline, Bars,
Renko, Kagi, Point & Figure, Line Break, Candles, Hollow Candles and Heikin Ashi.
Bars use close ticks. Renko uses two-box reversals, Kagi a three-box absolute
reversal, P&F three-box reversals, and Line Break three preceding lines. The
initial automatic box is max(visible price range / 30, first price × 0.002,
0.01); `box N` fixes it. Event styles use event positions on their price axis.

**No source contains trade-level OHLC.** Candles, Hollow Candles and Heikin Ashi
therefore display **mean-envelope; NOT trade OHLC**. The 15m/30m/1h resolutions
aggregate genuine 5m means using first/last/min/max; these are **OHLC of 5m
means**, never labelled real trade OHLC. Open/high/low cannot be recovered from
daily/weekly means or from a single 5m mean. There is no 1m mode or invented
interpolation. Every chart header shows resolution and provenance; its footer
shows actual observed bounds and source, including inferred/unknown intervals.

Charts combine local `assembled-v3/daily.parquet`, weekly
`ge-tracker-weekly-v1/weekly.parquet`, archived `forward/wiki/300s` observations,
and recent Wiki timeseries as appropriate. Weekly history reaches back to 2017
where available; selecting a long range at a finer resolution never fabricates
older fine buckets. Ranges end at the latest available observation, or the UTC
jump date. Gaps remain absent. The header reports the last loaded **mean**, change
across the visible range and visible volume; it does not claim a last trade or
session total. The countdown shows the next scheduled UTC bucket boundary and
marks historical series.

Python computes scales, transforms, indicator warmup from all loaded history,
axis bounds, label collision groups and treemap rectangles. Rust renders that
geometry. SMA/EMA use 20 observations; Bollinger uses 20 and two population
standard deviations; RSI uses Wilder's 14-period recurrence; MACD is 12/26/9.
RSI/MACD render in independent sub-panes. VWAP is cumulative volume-weighted
**bucket mean** from the loaded start, not trade VWAP. Comparison uses exact
common timestamps and rebases at the first visible common observation; it is
mean-price change, without dividends or filled missing values.

TAS contains aggregated 5m side events with side mean price and item quantity,
not individual trades or market-centre information. The server deduplicates
observed events and retains a day's tape in memory. QM's bid/ask are latest Wiki
instant-sell/instant-buy proxies, with separate side ages, not order-book quotes.
HCP compares against local daily means or Wiki 24h snapshots within two days of
the requested lookback; absent references stay absent. HMAP sizes its top 32
items by completed 5m quantity and colours by net spread or 1d change. MOST ranks
item quantity and explicitly marks trade counts unavailable. EQS combines
spread, quantity, alch gap, membership and buy-limit constraints; unknown values
fail active constraints. Its alch cash gap assumes a fire staff and subtracts
instant-buy and nature-rune cost; it excludes casting time and is distinct from
the existing research alchemy panel's adverse-price assumptions.

AL stores thresholds and one-shot trigger records in
`$OSRS_DATA_DIR/server/terminal.sqlite`. A server task evaluates every five
seconds even without clients, and skips stale responses or side quotes older
than 15 minutes. Triggered alerts remain in AL and flash in the status line for
60 seconds. No notifications leave the server. Alert state survives client and
server restarts; the tape and close-undo stack are session-local.

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

Chart mathematics, indicators, close-only transforms, comparisons, scales, label
collisions and treemap tiling have pure Python unit tests. Historical adapters,
composable filters, missing data, endpoints and durable alerts have integration
tests. Rust tests cover hit regions, clamping, edge operations, linked tickers,
undo restoration, chart geometry rendering and tiny terminals. Server tests use fixture data,
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
