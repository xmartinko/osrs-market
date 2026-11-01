# CODEX PARALLEL EXECUTION BRIEF — `osrs-market`

Paste this document directly into an autonomous Codex session. Follow every constraint literally. Another agent is actively running the Phase One `P1` economic backtest and updating `research/osrs-forecasting/phase_one/` and `ml/src/osrs_ml/probabilistic_*.py` in parallel.

---

## 1. State of Play

Across the 74-item, 3-fold purged walk-forward development panel (`2024-10-29` .. `2026-07-26`, `230,657` `complete_24h` pairs, sealed holdout `>= 1785024300` untouched, `68 / 72` neural fit slots used, `4 / 72` `E4` prospective slots reserved), `E1` (`21` statistical/tabular baselines) established `catboost_multiquantile_copula` as the calibrated non-neural benchmark (`primary_macro_scaled_crps_1_4_24 = 1.1607`, unbiased scaled variogram `99.24`, 90% coverage `89.4% / 89.9% / 89.6%`) and showed that `I(1)` random-walk baselines over-disperse to `97%–98.5%` 90% coverage at `h = 24` due to 4h–72h Grand Exchange mean reversion; `E2` (`54 / 54` GPU fits across `6` neural architectures × `3` seeds × `3` folds) proved no architecture cleared Gate A (`<= 1.1375` marginal CRPS, `-2.0%`), `5 / 6` architectures failed overall (`direct_marginal_student_t` reached `1.1508` CRPS `-0.85%` but `136.30` variogram `+37.33%`; `spline_flow` `campaign_v3` reached `1.1668` CRPS `+0.53%` and `94.38` variogram `-4.90%`), and **`recursive_student_t` was the sole architecture to clear the preregistered gate** via Gate B (`92.90` unbiased variogram `= -6.40% <= 94.28`, `1.1507` CRPS `= -0.86%`, `p_holm = 0.0030`, 90% coverage `89.4% / 89.6% / 88.8%`); `E3` (`9 / 9` GPU ablations) proved `13`-col `e3_price_only` (`1.1503` CRPS, `93.00` variogram, Gate B `PASS`) matches `19`-col `e2_matched` (`p_holm = 0.3258`), showing volume/imbalance/buy-ratio features add zero predictive value once gap-bridged returns and 4h/24h/72h EWMA price-anchor deviations are fed back closed-loop; and **`P1` (`0` `E4` slots consumed, `81 / 81` tests passing, policy preregistered at `ab9a736` before computing validation P/L) has just completed**: converting `recursive_student_t` into a sized `100M GP` GE policy via `osrs_ml.{costs,execution,backtest}` yields genuine gross forecast alpha (`+830,607 GP` gross mid P/L at `73.7%` gross hit rate on walk-forward; `+3.54M GP` gross and `p = 0.0025` vs `-2.35M GP` time-shuffled null on `H24h_edge0bps`), **but `-902,399 GP` in spread + slippage + `2%` GE tax + `79.1%` `h = 1` ceiling-expiry adverse selection turns walk-forward net P/L negative (`-71,792 GP = -0.0718%`, Sharpe `-0.086`, $p = 1.0000$) and leaves all `6 / 6` grid cells statistically indistinguishable from `0 GP` ($p \ge 0.1224$)**, making the **5-minute (`300s`) live `osrs-ml-forward` pipeline, FastAPI server, and `ratatui` TUI** the decisive engineering bottleneck.

---

## 2. Exact Branch, Base Commit, and Isolated Worktree Setup

- **Remote:** `devstash` (`https://git.devstash.tech/martinko/osrs-market.git`)
- **Upstream active branch:** `research/osrs-phase-one-2026-11-01`
- **Minimum verified base commit (`P1` completed):** `96d33eb9dbfbf0f293247cccf777f70a277c65e3` (always `git fetch devstash` first and branch from the tip of `devstash/research/osrs-phase-one-2026-11-01`).
- **Codex branch name (create your own):** `codex/forward-server-tui-2026-11-01`
- **Worktree isolation rule:** **DO NOT** run inside `/home/martin/osrs-phase-one-worktree`, `/home/xmart/osrs-research/code`, or `C:/Users/xmart/osrs-phase-one`. Create a dedicated Git worktree:

```sh
# On VPS (7 GB RAM, zero swap — preferred for forward/server/TUI work):
git -C /home/martin/src/osrs-market fetch devstash research/osrs-phase-one-2026-11-01
git -C /home/martin/src/osrs-market worktree add -b codex/forward-server-tui-2026-11-01 \
  /home/martin/osrs-codex-worktree devstash/research/osrs-phase-one-2026-11-01
cd /home/martin/osrs-codex-worktree

# Or on Windows (if running locally instead of VPS):
git -C C:/Users/xmart/osrs-phase-one fetch devstash research/osrs-phase-one-2026-11-01
git -C C:/Users/xmart/osrs-phase-one worktree add -b codex/forward-server-tui-2026-11-01 \
  C:/Users/xmart/osrs-codex-worktree devstash/research/osrs-phase-one-2026-11-01
```

---

## 3. Strict `DO NOT TOUCH` List

Violating any item below will corrupt active experiments, invalidate preregistered gates, or collide with parallel commits:

1. **Sealed Holdout `1785024300`:** NEVER read, query, test against, or pass `--holdout` on any data with `timestamp >= 1785024300` (`2026-07-26T00:00:00Z`), and NEVER create or enable `holdout_access.json`.
2. **Phase One Research Directory:** NEVER create, edit, or delete anything under `research/osrs-forecasting/phase_one/**` (including `P1_BACKTEST.md`, `p1_backtest_protocol.json`, `p1_backtest_results.json`, `E2_STATUS.md`, `CODEX_HANDOFF.md`, `HANDOFF.md`, `README.md`, and all `*.json`/`*.md` manifests).
3. **Probabilistic Modelling & `P1` Runner/Test Files:** NEVER modify:
   - `ml/src/osrs_ml/probabilistic_models.py`
   - `ml/src/osrs_ml/probabilistic_campaign.py`
   - `ml/src/osrs_ml/probabilistic_backtest.py`
   - `ml/src/osrs_ml/probabilistic_*.py` (all files matching this glob)
   - `ml/tests/test_probabilistic_*.py` (all files matching this glob)
4. **Shared `P1` Cost & Execution Core:** NEVER modify `ml/src/osrs_ml/costs.py`, `ml/src/osrs_ml/execution.py`, or `ml/src/osrs_ml/backtest.py` (`P1` imports and runs them directly; do all forward-pipeline optimizations inside `forward.py` and `forward_store.py`).
5. **Checkpoints & Run Artifacts Under `runs/`:** NEVER touch `/home/martin/osrs-data/phase-one-20261101/runs/**`, `/home/xmart/osrs-research/runs/**`, `/home/xmart/osrs-research/runs_thinkpad/**`, or `ml/runs/**`.
6. **Live Data & GPU Research Nodes:** NEVER modify raw archives under `/home/martin/osrs-data/sources/**`, NEVER open live `/home/martin/osrs-data/forward/*.sqlite` files in write mode from server/health scripts, NEVER restart live `systemd --user` timers/services without explicit operator instruction, and NEVER touch `/home/martin/osrs-research/**` on `root@thinkpad` (reserved for opportunistic Phase One GPU work and may be powered off at any moment).

---

## 4. Ranked Parallel Tasks (File-Disjoint, Non-Modelling)

Work through these tasks in rank order (`Task 1` -> `Task 5`). Commit after each task passes its exact test gate.

### Task 1 (Rank 1 — Highest Value): Forward & Daily Pipeline Memory/CPU Bounding + Live Checkout Drift Audit
- **Allowed files to modify:**
  - `ml/src/osrs_ml/forward.py`
  - `ml/src/osrs_ml/forward_store.py`
  - `ml/src/osrs_ml/collector.py`
  - `ml/tests/test_forward.py`
- **Why it matters (root causes):**
  - On the 7 GB zero-swap VPS, `osrs-ml-forward` previously OOM-killed at `2.1 GB` RSS and `osrs-ml-daily` failed with `_catboost.CatBoostError: Invalid cat_features[0] = 12 value: index must be < 12` (`net_return.cbm` trained on 13 features including legacy `history_rows` at index 9 and `item` at index 12 vs 12-feature `FEATURES`). An initial Oct 31 patch (`docs/prospective-pipeline-repair.md`) landed on this branch, **but three production bottlenecks remain in `forward.py` / `forward_store.py` (plus potential checkout drift on `/home/martin/src/osrs-market`):**
    1. **Unbounded daily archive load (`forward.py:395`):** When `model_dir is not None` (`osrs-ml-daily`), `forward()` still executes `f = archive_observations(archive, resolution=resolution)`, concatenating **every** archived daily Parquet snapshot into pandas under a strict `MemoryMax=384M` (`MemorySwapMax=0`) unit cap instead of querying a bounded `[now - 35 * 86400, now]` window from `ArchiveStore` (`ledger-86400.observations.sqlite`). Also `daily_predictions()` (`forward.py:42-61`) fails if `latest` is empty (`0` eligible rows) and relies on implicit Arrow string handling rather than coercing `x["item"] = x["item"].astype(str)` before constructing `Pool(x, cat_features=[x.columns.get_loc("item")])`.
    2. **Full-table SHA-256 rescan every 5 minutes (`forward_store.py:92-101`):** `ArchiveStore.archive_hash()` scans and hashes every `context_json` row across the entire `archive_cache.observations` table on every 5-minute run.
    3. **12-generator concurrent full-history replay (`forward.py:276-371`):** Because `run_id` depends on `archive_hash`, every new 5-minute snapshot invalidates all `12` (`4` cohorts × `3` presets) `paper_runs` and steps all `12` `simulation_steps` generators concurrently while each accumulates full-history `curve`, `order_log`, and `fills` lists in RAM (`369.6 MiB` RSS and `92.3s` CPU after just `546` snapshots = 1.9 days; guaranteed `>768 MiB` OOM or `>300s` cadence overrun across a 56-day prospective window).
- **Acceptance criteria:**
  1. Replace `archive_observations()` inside `forward()` (`model_dir is not None` path) with a bounded `ArchiveStore` query covering `[now - 35 * 86400, now]` for `context` feature lookback while passing only the freshness window (`store.latest(now, resolution)`) to `issue()`, preserving exact `model_scores` and `issue()` parity with the full-frame path.
  2. Guard `daily_predictions()` and `forward()` cleanly when `latest.empty` (return `0` issued rows without crashing CatBoost `Pool`), coerce `x["item"]` to plain `str`/`object` dtype, and keep regression coverage for both 12-feature and legacy 13-feature (`history_rows`, `cat_features=[12]`) CatBoost models.
  3. Cache canonical row/bucket digests or maintain an incremental `archive_hash` table in `ArchiveStore` (`observations.sqlite`) that produces **byte-for-byte identical** `archive_hash` digests to `paper()` without re-hashing unchanged historical rows when no retroactive revision occurred.
  4. Execute `paper_streamed()` cohort-by-cohort (at most `3` preset generators active in memory at once instead of `12`, releasing completed generator frames immediately via `gc.collect()`), preserving exact `paper_runs` and `paper_fills` SQLite table parity with `paper()`.
  5. If running on VPS, inspect (read-only: `systemctl --user show osrs-ml-forward.service osrs-ml-daily.service -p FragmentPath -p ExecStart -p Result -p ExecMainStatus -p MemoryPeak` and `git -C /home/martin/src/osrs-market rev-parse HEAD`) and document any live checkout commit drift in commit message notes without restarting live services.
- **Exact verification command:**
  ```sh
  cd ml && uv run --frozen pytest -q tests/test_forward.py && uv run --frozen ruff check src/osrs_ml/forward.py src/osrs_ml/forward_store.py src/osrs_ml/collector.py tests/test_forward.py
  ```

---

### Task 2 (Rank 2): FastAPI `/api/collector/health` & `Terminal.local` SQLite Fast-Path + Read-Only `/api/forward/summary`
- **Allowed files to modify:**
  - `ml/src/osrs_ml/server/service.py`
  - `ml/src/osrs_ml/server/terminal.py`
  - `ml/src/osrs_ml/server/app.py`
  - `ml/tests/test_server.py`
  - `ml/tests/test_terminal_server.py`
- **Why it matters (root causes):**
  1. `Service.collector()` (`service.py:276-308`) synchronously globs and `json.loads()` **every** `forward/wiki/*s/*/observations.manifest.json` file on disk and runs `SELECT count(*) FROM <table>` across multi-GB SQLite files (`ledger-300.sqlite` > `2.5 GiB`) every time its 15s cache expires.
  2. `Terminal.local()` (`terminal.py:109-124`) runs DuckDB `read_parquet('.../forward/wiki/300s/*/observations.parquet')` across thousands of 5-minute Parquet files on cold cache even when indexed `ledger-300.observations.sqlite` exists right beside `ledger-300.sqlite`.
  3. Neither FastAPI nor the TUI exposes prospective paper-trading & settlement metrics from `ledger-300.sqlite` / `ledger-86400.sqlite`.
- **Acceptance criteria:**
  1. In `Service.collector()`, read snapshot counts/timestamps/gaps from `imported_snapshots` in `ledger-*.observations.sqlite` (`mode=ro`, `busy_timeout=2000`) when available (falling back to manifest globbing only for resolutions without an index DB), add `newest_age_seconds` and `stale: bool` (`> 600s` for `300s`, `> 90000s` for `86400s`), and use `MAX(rowid)` / indexed metadata where safe or increase ledger count TTL (`>= 60s`) so `/api/collector/health` completes in `< 50 ms` warm / `< 200 ms` cold on multi-thousand-snapshot archives.
  2. In `Terminal.local()`, query `ledger-300.observations.sqlite` (`mode=ro` indexed by `(item_id, timestamp)`) when present for `5m`/`15m`/`30m`/`1h` history, falling back to `read_parquet` when the SQLite observation index does not exist; preserve exact OHLCV/spread response schema.
  3. Add read-only `GET /api/forward/summary` (`Service.forward_summary()`, cached `30s`, strict `file:...?mode=ro` URI connections) returning per-ledger (`ledger-300.sqlite`, `ledger-86400.sqlite`): latest `issued_at`, pending vs matured `outcomes` count, per-model directional hit rate & MAE on matured outcomes, and latest `paper_runs` summary (`model`, `preset`, `net_gp`, `realized_net_gp`, `fill_rate`, `max_drawdown_gp`, `trade_count`).
  4. Add unit/integration tests in `tests/test_server.py` and `tests/test_terminal_server.py` covering SQLite-backed `collector()`, SQLite-backed `Terminal.local()` parity with Parquet fallback, and `/api/forward/summary` (including missing/empty ledger graceful handling).
- **Exact verification command:**
  ```sh
  cd ml && uv run --frozen pytest -q tests/test_server.py tests/test_terminal_server.py tests/test_terminal_charting.py && uv run --frozen ruff check src/osrs_ml/server/service.py src/osrs_ml/server/terminal.py src/osrs_ml/server/app.py tests/test_server.py tests/test_terminal_server.py
  ```

---

### Task 3 (Rank 3): FastAPI `jobs.py` / `chat.py` Subprocess Memory Hygiene & WebSocket Poll Efficiency
- **Allowed files to modify:**
  - `ml/src/osrs_ml/server/jobs.py`
  - `ml/src/osrs_ml/server/chat.py`
  - `ml/tests/test_server_jobs.py`
  - `ml/tests/test_server_chat.py`
- **Why it matters (root causes):**
  - On the 7 GB zero-swap box, `Runner` spawns worker subprocesses without bounding OpenMP/BLAS/Polars/Rayon thread pools (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `POLARS_MAX_THREADS`, `RAYON_NUM_THREADS`), risking memory/thread contention with `osrs-ml-forward`. Meanwhile, WebSocket streams (`/api/jobs/{job_id}/stream`, `/api/chat/{chat_id}/stream`) poll SQLite every `100 ms`, opening and closing a brand-new `sqlite3.connect()` `10–20` times/sec per client, and `Store.list()` loads unbounded historical job rows.
- **Acceptance criteria:**
  1. Inject conservative default thread-cap env vars (`OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=2`, `MKL_NUM_THREADS=2`, `NUMEXPR_MAX_THREADS=2`, `POLARS_MAX_THREADS=2`, `RAYON_NUM_THREADS=2`, via `setdefault` so explicit caller overrides still work) into spawned job subprocesses.
  2. Add bounded `limit: int = 100` pagination to `Store.list()` (preserving existing API list shape) and optimize read-side event polling (`mode=ro` persistent per-thread or context-reused SQLite connection during active WebSocket stream + adaptive `100 ms -> 500 ms` idle poll backoff when no new events arrive).
  3. Preserve all existing `holdout_access` blocks (`holdout` stays strictly rejected unless explicitly configured; never create `holdout_access.json`).
- **Exact verification command:**
  ```sh
  cd ml && uv run --frozen pytest -q tests/test_server_jobs.py tests/test_server_chat.py tests/test_server_codex.py && uv run --frozen ruff check src/osrs_ml/server/jobs.py src/osrs_ml/server/chat.py tests/test_server_jobs.py tests/test_server_chat.py
  ```

---

### Task 4 (Rank 4): `ratatui` TUI (`osrs-term`) Poll-Cadence Tiering, Forward-Ledger Panel, & Stale-Feed Alerting
- **Allowed files to modify:**
  - `tui/src/net.rs`
  - `tui/src/views.rs`
  - `tui/src/main.rs`
  - `tui/src/window.rs`
  - `tui/src/interaction.rs`
  - *(Do NOT add external crates to `tui/Cargo.toml`; use existing `ratatui`, `reqwest`, `tokio`, `serde`, `chrono`, `nucleo`.)*
- **Why it matters (root causes):**
  - `tui/src/net.rs:99-127` currently polls **all 13 HTTP routes every 3 seconds**, including re-downloading the full `search/catalogue` payload, writing `search-cache.json.tmp` + renaming it to disk, and rebuilding the `nucleo` index in `spawn_blocking` every 3 seconds, while also hammering `collector/health`, `models/runs`, `research/battery`, and `research/participation`. It also lacks visibility into `/api/forward/summary` and collector staleness.
- **Acceptance criteria:**
  1. Tier polling in `tui/src/net.rs`: fast tier (`3s`: `health`, `prices/latest`, `prices/movers`, `alch/gaps`, `jobs`, `terminal/alerts`) vs slow tier (`30s`: `collector/health`, `forward/summary`, `models/runs`, `usage`, `chats`; `120s` or unchanged-bytes skip for `search/catalogue`, `research/battery`, `research/participation`). Skip rewriting `search-cache.json` and rebuilding `nucleo` when serialized `search/catalogue` bytes match the previous digest/bytes.
  2. Extend `App::collector` (`tui/src/views.rs:202-243`) (or add a dedicated `Forward` tab/window alongside `Collector`) to render `/api/forward/summary` (`ledger-300` & `ledger-86400` latest `issued_at`, matured outcomes, model hit-rate/MAE, paper `net_gp` / `fill_rate` / `max_drawdown_gp`) and highlight `stale == true` buckets in `Color::Red` / `Color::Yellow` in both the Collector view and top status bar.
  3. Add Rust unit tests covering poll-tier scheduling / catalogue deduplication and degraded/stale JSON rendering in `tui/src/`.
- **Exact verification command:**
  ```sh
  cd tui && cargo test --release && cargo clippy --all-targets -- -D warnings
  ```

---

### Task 5 (Rank 5): Read-Only Forward-Pipeline & Systemd Healthcheck CLI
- **Allowed files to modify / create:**
  - `scripts/check_forward_health.py`
  - `ml/tests/test_forward_healthcheck.py`
- **Why it matters:**
  - Operators need a single zero-mutation command on the 7 GB no-swap VPS to verify collector lag, SQLite WAL/quick-check health, unsettled prediction backlog, and `systemd --user` memory-guard properties (`MemoryAccounting=yes`, `MemoryMax`, `MemorySwapMax=0`, `OOMPolicy=stop`, last `Result`/`ExecMainStatus`/`MemoryPeak`) without touching live writer locks.
- **Acceptance criteria:**
  1. `python3 scripts/check_forward_health.py --data-root /home/martin/osrs-data --json` opens all SQLite files strictly via `file:...?mode=ro` (`busy_timeout=2000`), checks newest `300s` (`<= 600s` warn, `<= 1200s` crit) and `86400s` (`<= 93600s` warn) snapshot ages, `paper_runs` freshness, optional `--check-systemd` (`systemctl --user show` read-only), and exits `0` (`OK`), `1` (`WARN`), or `2` (`CRITICAL`).
  2. Unit tests in `ml/tests/test_forward_healthcheck.py` verify healthy, stale-snapshot, missing-ledger, and mocked `systemctl --user show` (`Result=oom-kill`, `MemorySwapMax!=0`) failure classifications using temporary fixtures.
- **Exact verification command:**
  ```sh
  cd ml && uv run --frozen pytest -q tests/test_forward_healthcheck.py && uv run --frozen ruff check ../scripts/check_forward_health.py tests/test_forward_healthcheck.py
  ```

---

## 5. Git & Hygiene Protocol for Codex

1. **Own branch & worktree only:** Work exclusively on `codex/forward-server-tui-2026-11-01` inside your isolated worktree (`/home/martin/osrs-codex-worktree` or `C:/Users/xmart/osrs-codex-worktree`).
2. **Follow-up commits only — NEVER force-push:** Push incremental commits with `git push devstash codex/forward-server-tui-2026-11-01`. Never run `git push --force`, `git push --force-with-lease`, `git reset --hard` on pushed refs, or rebase shared history.
3. **Merge-only integration:** If syncing upstream changes from `devstash/research/osrs-phase-one-2026-11-01`, use `git merge --no-ff` (never rebase published commits) and verify `git diff --name-only` contains **zero** files from Section 3 (`DO NOT TOUCH`).
4. **Zero data or binary artifacts in Git:** Never stage `.parquet`, `.sqlite`, `.sqlite-wal`, `.sqlite-shm`, `.cbm`, `.pt`, `.npz`, `.tar.gz`, or anything under `runs/`. Verify with `git status --short` before every commit.
5. **No personal identity in commits or code:** Set repo-local neutral commit identity inside your worktree before committing:
   ```sh
   git config user.name "codex-agent"
   git config user.email "codex-agent@localhost"
   ```
   Never include personal names, emails, host credentials, or private keys in commit messages, comments, tests, or docs.
