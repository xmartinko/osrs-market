# Codex Branch Review Verdict — `codex/forward-server-tui-2026-11-01` (`891ed2a`)

- **Reviewed Branch:** `devstash/codex/forward-server-tui-2026-11-01` (`ab9a7364e3a066a8454498b1ef28651ca39e3914..891ed2ab732d5adfca96656e8f3ce5d2d6466356`, `6` linear commits, `22` files, `+2,274 / -352`)
- **Current Disposition:** **Left unmerged and undeployed** per Martin's instruction; live VPS services, `/home/martin/src/osrs-market`, and `research/osrs-phase-one-2026-11-01` remain untouched.
- **Merge Verdict:** **SAFE TO MERGE LATER WITH ONE TARGETED `service.py` FIX BEFORE PRODUCTION SERVER DEPLOY**
  - **Safe as-is:** **Task 1** (`ml/src/osrs_ml/forward.py`, `ml/src/osrs_ml/forward_store.py`), **Task 3** (`ml/src/osrs_ml/server/{jobs,chat}.py`), **Task 4** (`tui/src/*.rs`), and **Task 5** (`scripts/check_forward_health.py`).
  - **Fix before deploying FastAPI + TUI against the `2.5+ GiB` live `ledger-300.sqlite`:** **Task 2** (`ml/src/osrs_ml/server/service.py`) holds `Service`'s single global `self.lock` inside `_local_cached()` (`lines 288–296`) while executing unbudgeted full-B-tree scans (`predictions LEFT JOIN outcomes` in `_forward_summary()`, `TTL = 30s`, and `SELECT count(*)` in `_collector_counts()`, `TTL = 60s`). On the `2.5+ GiB` live `ledger-300.sqlite` (`1.48M+` wide `predictions` rows), Codex's own `check_forward_health.py` audit proved full `predictions`/`outcomes` scans exceed `5.0s` — which would stall every `3s` fast-tier `/api/prices/*` request whenever the `30s` slow-tier cache expires.

---

## 1. Boundary & Git Hygiene Check — **PASS (`0` Violations)**

- **Protected Paths Untouched:** Zero edits to `research/**`, `ml/src/osrs_ml/probabilistic_*.py`, `ml/tests/test_probabilistic_*.py`, `costs.py`, `execution.py`, `backtest.py`, `Cargo.toml`/`Cargo.lock`, `runs/`, `data/`, or sealed holdout `1785024300` (`jobs.prepare()` holdout guard preserved).
- **Commit & Operational Hygiene:** Linear commits authored as `codex-agent <codex-agent@localhost>`; zero data/binary files committed; zero live DB writes or `systemd` restarts. *(Commit `b1b658e` touched `5` extra `tui/src/*.rs` modules strictly for `17` mechanical Clippy `collapsible_if` folds required by `--all-targets -- -D warnings`.)*

---

## 2. Core Engineering Sanity Checks

1. **Bounded Forward & Daily Memory (`forward.py`, `forward_store.py` — `0650ffa`):**
   - **Daily OOM & `cat_features` fix:** `forward()` removes the full-archive `archive_observations()` load when `model_dir` is set, short-circuits on empty `store.latest(now, resolution)`, pulls a bounded `35`-day SQLite context plus `<= 30` sparse predecessor rows per item via `daily_context()` (preserving `return_30obs` lag exactness), reconstructs cumulative `history_rows` counts via `history_counts()` without JSON decoding, and coerces `x["item"] = x["item"].astype(str).astype(object)` in `daily_predictions()`. *(Live `osrs-ml-daily` only still shows `oom-kill/137` in the healthcheck because live `/home/martin/src/osrs-market` remains on `4f281ba`.)*
   - **Intraday replay RSS (`~4x` lower peak):** `paper_streamed()` replays one model cohort at a time (`<= 3` live `simulation_steps()` generators instead of `12`), closing generators and calling `gc.collect()` after each cohort.
   - *Deploy note:* First open of `ledger-300.observations.sqlite` populates `archive_cache.hash_chunks` (`(item_id, day)` JSON BLOBs), roughly doubling `.observations.sqlite` disk size once — check `df -h` headroom on VPS before first run.
2. **Read-Only API, Worker Hygiene, & Healthcheck (`server/*.py`, `scripts/check_forward_health.py` — `c036a50`, `4b57c15`, `14d845d`, `891ed2a`):**
   - **Verified good:** All SQLite readers enforce `?mode=ro` URIs + `PRAGMA query_only=ON` + `busy_timeout=2000` without creating missing files; `Terminal.local()` uses `ledger-300.observations.sqlite` for `5m/15m/30m/1h` candles; `jobs.subprocess_env()` caps `OMP/OPENBLAS/MKL/NUMEXPR/POLARS/RAYON` threads at `2` via `setdefault`; `Store.pending()` decouples queue/restart recovery from `100`-row public pagination; `check_forward_health.py` interrupts `>5s` checks via progress callback + watchdog timer and reports `unknown` (`WARN`) rather than corruption.
   - **Pre-deploy fix needed in `service.py` (~25 LOC):** (a) Run `load()` outside global `self.lock` in `Service._local_cached()` (per-key lock or stale-while-revalidate); (b) replace `SELECT count(*)` in `_collector_counts()` with `SELECT COALESCE(MAX(rowid), 0)` ($O(1)$ B-tree right-edge lookup on append-only tables); and (c) window (`WHERE p.issued_at >= ?`) or progress-budget `_forward_summary()` (plus optional `ORDER BY timestamp, fetched_at` in `terminal.py:102`).
3. **TUI Poll Cadence & Freshness (`tui/src/{net,views,main}.rs` — `b1b658e`):**
   - Clean `Fast` (`3s`), `Slow` (`30s`), and `Rare` (`120s`) Tokio poll tasks (`MissedTickBehavior::Skip`); `CatalogueCache` preloads `search-cache.json` on startup and skips disk writes + `spawn_blocking` `SearchUi` rebuilds when canonical JSON bytes are unchanged; `App::feed_status()` combines server `newest_age_seconds` + client elapsed time to render `FEED LIVE` / `FEED STALE` / `FEED UNKNOWN` cleanly.

---

## 3. Verdict on Codex's Two Explicitly Stated Limits — **Both Acceptable**

1. **Changed archives still stream cached `hash_chunks` bytes through SHA-256 (`forward_store.py:189–243`):** **Acceptable.** Legacy `paper()` defines `archive_hash` sequentially in `(item_id, timestamp)` **item-major order**, so every new `300s` snapshot inserts bytes at `~3,700` *interior* positions of the SHA-256 byte stream. Merkle–Damgård SHA-256 cannot resume across interior insertions without changing the digest definition and breaking historical `paper_runs.id` continuity; caching `(item_id, day)` BLOBs and returning `hash_digest` in $O(1)$ on unchanged archives is optimal under exact legacy compatibility.
2. **Idle SQL polling backs off `100ms -> 500ms` while `app.py`'s WebSocket loop wakes at `100ms` (`jobs.py:145–182`):** **Acceptable.** Respects Task 3's file boundary by leaving `app.py` untouched and gating SQLite reads per async subscriber (`WeakKeyDictionary`) in `Store._poll_query()`. The `10 Hz` in-memory `time.monotonic()` check performs zero SQLite/OS I/O when idle (`<0.05%` CPU), delivers local writes within `<=100ms` via `self._generation`, and observes external writers within `<=500ms`.
