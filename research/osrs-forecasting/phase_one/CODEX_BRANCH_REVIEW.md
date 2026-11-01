# Independent Reviewer Verdict — Codex Branch `codex/forward-server-tui-2026-11-01` (`891ed2a`)

- **Reviewed Branch:** `devstash/codex/forward-server-tui-2026-11-01`
- **Commit Range Audited:** `ab9a7364e3a066a8454498b1ef28651ca39e3914..891ed2ab732d5adfca96656e8f3ce5d2d6466356` (`6` linear commits, `22` files changed, `+2,274 / -352`)
- **Disposition Today:** **Left unmerged and undeployed** per operator instruction; live VPS services, `/home/martin/src/osrs-market`, and `research/osrs-phase-one-2026-11-01` remain untouched.
- **Overall Merge Verdict:** **SAFE TO MERGE LATER WITH ONE TARGETED SERVER FIX RECOMMENDED BEFORE PRODUCTION DEPLOY**
  - **Safe to merge as-is:** **Task 1** (`forward.py`, `forward_store.py`), **Task 3** (`server/jobs.py`, `server/chat.py`), **Task 4** (`tui/src/*.rs`), and **Task 5** (`scripts/check_forward_health.py`).
  - **Fix before deploying FastAPI + TUI against the `2.5+ GiB` live `ledger-300.sqlite`:** **Task 2** (`ml/src/osrs_ml/server/service.py`) executes unbudgeted full-table SQLite scans (`predictions LEFT JOIN outcomes` in `_forward_summary()` and `SELECT count(*)` in `_collector_counts()`) **while holding `Service`'s single global `self.lock`** (`_local_cached()`, lines `288–296`). On the `2.5+ GiB` live `ledger-300.sqlite` (`1.48M+` wide `predictions` rows), Codex's own `check_forward_health.py` audit proved that `predictions`/`outcomes` full scans exceed `5.0s`, which will stall every `3s` fast-tier `/api/prices/*` request whenever the `30s`/`60s` slow-tier cache expires.
  - **Stated Limits Verdict:** **Both explicitly stated limits are engineering-sound and acceptable** (detailed in Section 4).

---

## 1. Boundary, `DO NOT TOUCH`, & Git Hygiene Audit — **PASS (`0` Violations)**

| Constraint | Requirement | Audit Result (`ab9a736..891ed2a`) |
|---|---|---|
| **Sealed Holdout `1785024300`** | Never read, query, pass `--holdout`, or alter `holdout_access.json`; preserve `jobs.py` holdout rejection | **PASS** — Zero holdout accesses; `jobs.prepare()` `holdout` rejection untouched. |
| **`research/osrs-forecasting/phase_one/**`** | Zero creates/edits/deletes under `research/**` | **PASS** — `0` files touched under `research/`. |
| **Probabilistic & `P1` Files** | Zero edits to `ml/src/osrs_ml/probabilistic_*.py` or `ml/tests/test_probabilistic_*.py` | **PASS** — `0` files touched. |
| **Shared Cost / Execution / Backtest Core** | Zero edits to `costs.py`, `execution.py`, `backtest.py` | **PASS** — `0` files touched; all replay optimizations confined to `forward.py` + `forward_store.py`. |
| **`runs/`, `data/`, & Cargo Lockfiles** | Zero binary/data commits, zero `runs/` edits, zero `Cargo.toml`/`Cargo.lock` edits | **PASS** — `0` data/checkpoint/manifest files touched. |
| **Git & Identity Hygiene** | Linear follow-up commits on `codex/forward-server-tui-2026-11-01`, no force-push, neutral commit identity, no live restarts | **PASS** — All `6` commits authored/committed as `codex-agent <codex-agent@localhost>`; zero live DB mutations or service restarts. |

*Minor scope note:* Commit `b1b658e` touched `5` additional TUI modules (`tui/src/{chat,profile,search,search_ui,terminal}.rs`) strictly for `17` mechanical Rust-2024 `if let ... && let ...` Clippy `collapsible_if` folds (plus `1` duplicate match-arm cleanup in `tui/src/main.rs`) required to pass `cargo clippy --all-targets -- -D warnings`. Behavior is preserved.

---

## 2. Technical Sanity Check of Core Claims

### 2.1 Bounded Forward & Daily Memory Behaviour (`forward.py`, `forward_store.py` — Commit `0650ffa`)
- **Daily OOM & `cat_features` hardening (`forward.py:48-65, 397-425`, `forward_store.py:144-187`) — VERIFIED:**
  - `forward()` no longer calls `archive_observations(archive, resolution)` when `model_dir is not None`. Instead it queries `f = store.latest(now, resolution)`, short-circuits before importing `CatBoostRegressor` or loading `history.parquet` when `f.empty`, fetches a bounded `35`-day SQLite context window plus at most `31 - len(rows)` older rows per sparse item via `ArchiveStore.daily_context()` (preserving `return_30obs` observation-count lag parity), and reconstructs exact cumulative `history_rows` counts via `ArchiveStore.history_counts()` without decoding historical `context_json` blobs.
  - `daily_predictions()` explicitly coerces `x["item"] = x["item"].astype(str).astype(object)` before `Pool(..., cat_features=categorical)` and guards empty frames (`if latest.empty: return []`).
  - *(Operational context: Codex's live `check_forward_health.py` run still observed `osrs-ml-daily.service` in `oom-kill` / exit `137` at `384 MiB` with `17,905` overdue daily outcomes because live `/home/martin/src/osrs-market` is still checked out at `4f281ba`, pre-dating `0650ffa`.)*
- **Intraday forward replay RSS reduction (`forward.py:295-375`) — VERIFIED (`~4x` lower peak simulator state):**
  - `paper_streamed()` previously kept `12` concurrent `simulation_steps` generators (`4` model cohorts × `3` execution presets) alive simultaneously across a single `store.paper_events` pass. Commit `0650ffa` serializes replay **one cohort at a time** (`<= 3` live preset generators), explicitly calling `job["steps"].close()`, `del result`, clearing `jobs`/`cohort_jobs`, and running `gc.collect()` after each cohort. Because live `osrs-ml-forward` had already reached `MemoryPeak=768 MiB` against its `768 MiB` `MemoryMax` cap on `4f281ba`, cutting live simulator memory by `~4x` directly relieves the immediate OOM ceiling.
- **Non-blocking scale notes for future multi-month operation:**
  1. **Sequential CPU vs RSS trade-off (`forward.py:345`):** Cohort-by-cohort replay calls `store.paper_events([cohort], now)` once per active cohort (`4` sequential SQLite index scans + JSON decodes of `observations` instead of `1` shared pass). Within a single cohort, `backtest.simulation_steps()` (frozen during `P1`) still accumulates `curve` and `order_log` lists in RAM for its `3` presets; once `backtest.py` is unfrozen later, adding an optional `retain_history=False` summary mode to `simulation_steps()` will drop per-cohort memory from $O(\text{buckets})$ to $O(\text{open positions})$.
  2. **One-time cold migration disk footprint (`forward_store.py:85-96, 209-225`):** First opening an existing `.observations.sqlite` populates `archive_cache.hash_chunks` (`(item_id, day)` canonical JSON BLOBs), roughly doubling `.observations.sqlite` disk size once during initial chunk build. Verify free VPS disk space before first deployment.

### 2.2 Read-Only APIs, Terminal Index, Worker Hygiene, & Healthcheck (`server/*.py`, `scripts/check_forward_health.py` — Commits `c036a50`, `4b57c15`, `14d845d`, `891ed2a`)
- **Read-only SQLite invariants — VERIFIED:**
  - `service.readonly_db()` (`service.py:24-32`), `jobs.Store.read_db()` (`jobs.py:131-143`), and `check_forward_health.readonly_db()` (`check_forward_health.py:42-81`) all open `Path(path).resolve().as_uri() + "?mode=ro"` with `uri=True`, `timeout=2`, `PRAGMA busy_timeout=2000`, and `PRAGMA query_only=ON`. Missing files/directories fail cleanly without creating empty SQLite files (`test_missing_ledger_is_critical_and_never_created`, `test_missing_all_data_does_not_create_directories`).
  - `Terminal.local()` (`terminal.py:97-113`) reads `5m/15m/30m/1h` candle inputs from `ledger-300.observations.sqlite` (`observations_item_time` index) before falling back to scanning `forward/wiki/300s/*/observations.parquet`, matching Parquet output identically (`test_intraday_sqlite_index_matches_parquet_fallback`). *(Minor polish nit: `ORDER BY timestamp` on line `102` should ideally be `ORDER BY timestamp, fetched_at` so `values.setdefault(...)` deterministically retains earliest fetch if duplicate revisions ever occur.)*
- **Worker thread caps & pagination (`jobs.py:71-90, 196-211, 356-380`, `chat.py`) — VERIFIED:**
  - `subprocess_env()` caps `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_MAX_THREADS`, `POLARS_MAX_THREADS`, and `RAYON_NUM_THREADS` to `"2"` via `setdefault` without clobbering caller overrides.
  - Public `Store.list(limit=100, offset=0)` is bounded (`1..1000`), while `Runner.start()` and `Runner.schedule()` query `Store.pending()` so `>100` historical jobs never hide old `queued` jobs or orphan interrupted `running` jobs on restart.
- **Healthcheck SQLite watchdog (`scripts/check_forward_health.py:42-81` — Commit `891ed2a`) — VERIFIED:**
  - Combines `db.set_progress_handler(..., 10_000)` with a `threading.Timer` watchdog calling `db.interrupt()` (and joining the timer before `db.close()`), cleanly separating `quick_check = ["unknown"]` + `check_incomplete` (`WARN`) from genuine database corruption (`CRITICAL`).
- **REQUIRED FIX BEFORE PRODUCTION SERVER DEPLOY (`ml/src/osrs_ml/server/service.py:288-296, 364-389, 407-477`):**
  - **Issue — Global `self.lock` held across multi-second unbudgeted scans on `2.5+ GiB` `ledger-300.sqlite`:**
    1. `Service._local_cached(self, key, ttl, load)` (`service.py:288-296`) executes `result = load()` **inside `with self.lock:`** — the same `threading.Lock()` guarding `Service.cached()` for `/api/prices/latest`, `/api/prices/movers`, and `/api/alch/gaps`.
    2. `_forward_summary()` (`TTL = 30s`, lines `424-437`) runs an unbudgeted `SELECT p.model, count(*) ... FROM predictions p LEFT JOIN outcomes o ON o.prediction_id=p.id GROUP BY p.model`, and `_collector_counts()` (`TTL = 60s`, lines `384-385`) runs `SELECT count(*) FROM "predictions"` and `"paper_fills"`. Because `predictions` stores wide `context_json` payloads inline in its table B-tree (`2.5+ GiB`, `1.48M+` rows on the live VPS), full B-tree scans take **>5 seconds** (which is why `check_forward_health.py` timed out at `5.0s` on `ledger-300.sqlite` during Codex's live audit).
    3. When the TUI `Slow` poller (`30s`) hits `/api/collector/health` and `/api/forward/summary`, every cache miss will hold `Service.lock` for `5–10+ seconds`, serializing FastAPI worker threads and stalling `3s` fast-tier `/api/prices/*` polls.
  - **Targeted remediation before server deploy (~25 LOC in `service.py`):**
    1. Do not hold global `self.lock` while running `load()` in `_local_cached()` (use per-key locks or compute outside `self.lock` with stale-while-revalidate).
    2. Replace `SELECT count(*) FROM "..."` in `_collector_counts()` with `SELECT COALESCE(MAX(rowid), 0)` (an $O(1)$ B-tree right-edge lookup for append-only ledger tables) or a budgeted count.
    3. Bound `_forward_summary()` with either a rolling evaluation window (`WHERE p.issued_at >= ?` using `predictions_replay` / `issued_at` index) or a `sqlite3` progress-handler budget matching `check_forward_health.py`.

### 2.3 Tiered TUI Polling, Catalogue Cache, & Stale-Feed Banner (`tui/src/{net,views,main}.rs` — Commit `b1b658e`)
- **Tiered poll cadence (`tui/src/net.rs:30-60, 173-239`) — VERIFIED:**
  - Replaces the monolithic `3s` 14-endpoint loop with three independent Tokio tasks (`MissedTickBehavior::Skip` + exponential error backoff `1..10`):
    - `Fast` (`3s`): `health`, `prices/latest`, `prices/movers`, `alch/gaps`, `jobs`, `terminal/alerts`
    - `Slow` (`30s`): `collector/health`, `forward/summary`, `models/runs`, `usage`, `chats`
    - `Rare` (`120s`): `search/catalogue`, `research/battery`, `research/participation`
- **Zero-churn `CatalogueCache` (`tui/src/net.rs:62-74, 129-171, 180-189`) — VERIFIED:**
  - Preloads existing `search-cache.json` canonical bytes on `Rare` poller startup and short-circuits before temp-file writes, `spawn_blocking` `SearchUi` rebuilds, or `Message::Catalogue` UI wakeups whenever canonical JSON bytes match.
- **Feed freshness & forward summary UI (`tui/src/main.rs:297-339`, `tui/src/views.rs`) — VERIFIED:**
  - `App::feed_status()` combines server-reported `newest_age_seconds` (`300s` preferred, `86400s` fallback) plus client-side `Instant::elapsed()` since last `collector/health` receipt, flagging `FEED STALE` (`>600s` for `5m`, `>90,000s` for `1d`) in red, `FEED UNKNOWN` in warning yellow, and `FEED LIVE` in accent green without panicking on missing/partial JSON.

---

## 3. Verdict on Codex's Two Explicitly Stated Limits

1. **Limit 1 — *"Changed archives still require hashing cached bytes (`hash_chunks`) for legacy digest compatibility"* (`forward_store.py:189-243`):**
   - **Verdict: ACCEPTABLE.**
   - **Why:** Legacy `paper()` defines `archive_hash` as SHA-256 over `[row_json, ...]` ordered by `(item_id, timestamp)` (**item-major order**). Every new `300s` snapshot inserts new bytes at `~3,700` *interior* positions of that byte stream (at the tail of each `item_id`'s partition). Because Merkle–Damgård SHA-256 state is strictly sequential, interior byte insertions invalidate downstream block state; making changed-run hashing $O(\Delta)$ would require changing the digest definition (e.g., to a Merkle/XOR tree or snapshot-major chain), which would break historical `paper_runs.id` continuity. Rebuilding only dirty `(item_id, day)` JSON BLOBs via SQLite triggers and streaming pre-encoded BLOBs through C `hashlib.sha256` (while returning `hash_digest` in $O(1)$ on unchanged archives) is the exact optimum that preserves legacy digest parity.
2. **Limit 2 — *"Idle SQL polling backs off `100ms -> 500ms` while `app.py` WebSocket wakeups remain at `100ms`"* (`server/jobs.py:145-182`):**
   - **Verdict: ACCEPTABLE.**
   - **Why:** Codex respected Task 3's strict file-scope boundary by leaving `app.py`'s `await asyncio.sleep(0.1)` WebSocket loop untouched and gating SQLite execution per async subscriber (`weakref.WeakKeyDictionary`) inside `Store._poll_query()`. Checking `time.monotonic() < state["due"]` in pure Python at `10 Hz` performs zero SQLite calls, zero syscalls, and `<0.05%` CPU when idle, while local writes bump `self._generation` for immediate (`<=100ms`) delivery and external writers are observed within `<=500ms`.

---

## 4. Merge & Deployment Checklist (When Ready Later)

1. **Do nothing today:** Keep `codex/forward-server-tui-2026-11-01` (`891ed2a`) unmerged while Phase One research/review settles.
2. **Before merging & deploying to VPS `/home/martin/src/osrs-market`:**
   - Check `df -h /home/martin/osrs-data/forward` to confirm headroom (~`1–2 GiB`) for one-time `archive_cache.hash_chunks` population in `ledger-300.observations.sqlite`.
   - Apply the small `ml/src/osrs_ml/server/service.py` patch removing `load()` from global `self.lock` in `_local_cached()` and bounding/indexing `_collector_counts()` + `_forward_summary()` on `2.5+ GiB` `ledger-300.sqlite` (plus optional `ORDER BY timestamp, fetched_at` in `terminal.py:102`).
   - Fast-forward/merge cleanly (no `--force`), deploy `osrs-ml-daily` / `osrs-ml-forward` first to clear the `4f281ba` daily OOM backlog, and re-run `python3 scripts/check_forward_health.py --data-root /home/martin/osrs-data --systemd --json`.
