# OSRS financial model: implementation and orchestration

## Scope and data boundary

Branch: `ml/financial-model`, based on `main` at `8e03d49`. The existing C++ collectors, jobs, cache and PostgreSQL tables remain the source of truth. Python never calls the Wiki price or mapping endpoints and never writes to these tables. No frontend/auth changes are required for phase 1.

`ml/src/osrs_ml/data.py` exports `price_events` joined to the latest item revision **as of the observation**, using a bounded, repeatable-read, read-only PostgreSQL transaction and a server-side cursor. Rows go to an immutable Parquet file, with signed int64 prices/volumes/timestamps and a JSON provenance/checksum manifest; DuckDB reads the same file. Snapshot inputs are also supported. Credentials come only from `DATABASE_URL`, never from artifacts. Production should use a SELECT-only database role or replica.

Inspection found a real metadata gap: `TimeseriesClient.cpp` parses `TimeseriesResponse.timestep`, but `PriceBackfillJob.cpp` persists only `PricePoint`s; `002_create_price_events.sql` stores neither source interval nor per-side trade times. Mixed lookback resolutions can collide on `(item_id, timestamp)` with first-insert-wins. Timestamp differences cannot recover the returned interval. Historical metadata is therefore NULL, never invented; `observed_gap_seconds` is a separate diagnostic. Side freshness is a lower-bound estimate since the last positive-volume bucket, with an explicit unknown flag. The first snapshot row may have unknown freshness. Backfilled item metadata may also be unavailable as of old events; unknown buy limits disable buying. `created_at` is retained separately from event time.

A later, explicitly scoped C++ change is necessary to meet exact metadata hygiene: add nullable source/returned interval and last-side-trade timestamps when the upstream response supplies them, carry them through PricePoint and repository inserts, retain ingestion time and resolution provenance, and define conflict/overlap handling. Do not rebuild the collector or invent exact last-trade times for aggregate endpoints. Until then, real snapshots with missing interval metadata require an explicit simulation override and are unsuitable for claims about fills. Fixture timestamps represent completed buckets; real bucket availability needs verification before live research.

## Phase 1 — executable common foundation (this session)

Create:

- `ml/pyproject.toml`, `ml/uv.lock`, `ml/README.md`: Python 3.13 core environment, pinned resolution, CLI/run instructions. DuckDB, PyArrow, pandas, psycopg, CatBoost; no PyTorch install until a forecaster needs it.
- `ml/src/osrs_ml/data.py`: read-only Postgres export, validated Parquet contract, streaming export, manifest and DuckDB query path. `fixture.py`: deterministic multi-item, irregular/stale/illiquid observations spanning 2026-09-30, including a price above int32.
- `costs.py`: integer per-item tax and integer adverse slippage. This implementation follows the requested **above 50 gp** rule (50 is exempt), configurable via `TaxPolicy.exempt_through_gp`. The Wiki describes **below 50** as exempt; set this to 49 to reproduce that boundary instead. Tax floors per unit before multiplying quantity; cap is 5M per item. Tax exemptions are explicit item IDs, not inferred from category.
- `execution.py`, `backtest.py`: one chronological ledger for all adapters. Optimistic/moderate/conservative configurable volume participation, latency, slippage, stale rejection, order expiry and inventory haircut. Persistent partial buy/sell orders reserve cash and slots; buys count against item-specific 4-hour windows starting at first fill; sells do not restore limits. Buys use observed high, sells observed low; aggregate prints only support hypothetical execution, not proof of passive fills. Decisions execute only on later observations. Residual inventory is reported and marked conservatively after tax; never silently liquidated or omitted. Record both marked and cash P&L.
- `features.py`, `evaluation.py`, `models.py`: lagged within-item features, timestamp-based 1h/4h/24h return/volume/volatility/cost-adjusted targets; global CatBoost regression baseline used as a trade score, excluding cross-item/event features. Shared no-trade, no-change and spread+volume baselines. Expanding walk-forward folds, purge by label end, separate pre/post source-regime runs, reserve final recent holdout. Price-only and full-feature configurations share the same folds/executor. Phase 1 forecasts use a single selected horizon; multi-output foundation adapters/ranker arrive later.
- `cli.py`: `fixture`, `snapshot`, `run`; immutable run directories with snapshot hash, git revision/dirty status, package versions, seed, track, split boundaries, exact presets, model, forecast errors, fills/orders/equity and metrics. Aggregate comparison in DuckDB, ordered by net gp/hour with drawdown visible; no best-model declaration from fixture results.
- `ml/tests/`: tax boundaries/rounding/cap/int64, schema/metadata and export behavior, timestamp labels/purge/holdout, cash/slots/windows/partial fills/wait/staleness/terminal valuation and deterministic end-to-end checks.

Run tests and `osrs-ml fixture` + `osrs-ml run` on Python 3.13, save a small committed validation report with actual commands/output. Fit real CatBoost (no substitute masquerading as CatBoost). Do not report synthetic profit as evidence of a market edge. Commit plan, implementation, and verification in logical commits.

## Phase 2 — real-data qualification and research protocol

Validate a production snapshot's resolution provenance, item revision availability, NULLs, duplicate/overlapping intervals, coverage, gaps and side freshness. Add quality gates before fitting. Derive causal normalized returns/log-volume on a time grid with missing masks; never forward-fill volume or convert missing returns to zero. Fit transforms on training data only. Pin event publication times, related-item groups and tax policy versions; prevent revision/publication leakage. Audit real bucket timestamps and ingestion delay; compare event-time backtests with ingestion-time replay.

Freeze a common experiment manifest (`ml/experiments/tournament.toml`), folds and final holdout before selecting models. Use horizons 1h/4h/24h, purge every label with end >= validation start, and prevent validation labels from entering the holdout. Evaluate pre/post 2026-09-30 separately (the requested RuneLite/Jagex coverage break); mixed regime totals alone are insufficient. Final holdout is excluded from ordinary CLI runs and only unlocked after selection is recorded. Use net gp/hour, return on initial capital, drawdown, fill rate, mean/peak/end capital tied up, realized cash, terminal inventory and forecast error. Add quantile calibration, pinball loss, downside quantiles/CVaR and block-bootstrap uncertainty in phase 2. Specify capital and turnover constraints before optimizing.

## Phase 3 — official-package foundation tournament

Create `ml/adapters/{base,exaone,timesfm,timestral,t0,granite,chronos}.py` and per-family projects under `ml/environments/`. Freeze each official package version/commit, HF weights revision, code license **and weight license**, hardware/dtype, context limit and missing-data policy. Verify package APIs on first integration; do not force every model into Transformers. PyTorch lives in those environments, not the common executor. Start with Timestral 5M/28M and one verified CPU/small adapter, then measure resource budgets before larger models.

Model registry (user-specified candidates):

| Family | Weights / upstream |
| --- | --- |
| EXAONE Finance | `LG-AI-Research/EXAONE-Finance`, `LG-AI-Research/exaone-forecast`; `LGAI-Research/EXAONE-Forecast` |
| TimesFM-3 | `google/timesfm-3.0-pytorch`; check weights license separately |
| Timestral | `mistralai/Timestral-5M`, `Timestral-28M`, `Timestral-123M`, `Timestral-209M` |
| t0-beta | `theforecastingcompany/t0-beta` |
| Granite | `ibm-granite/granite-timeseries-patchtst-fm-r2` |
| Chronos-2 | `amazon/chronos-2` |

Adapters output a common forecast Parquet contract: model/revision, track, item, decision timestamp, context cutoff, horizon/label end, median return, lower/upper quantiles, volume, volatility, missing flags, run ID. The harness verifies no context after the decision. Price-only uses the common price history/masks and equal information cutoff; full-feature gives each architecture only supported causal inputs and records exactly which. All predictions enter the **same** shared executor using frozen signals/periods/presets, including no-trade, no-change, naive spread+volume and CatBoost without cross-item/events. Report context/input differences, runtime and memory instead of claiming perfect architecture isolation.

## Phase 4 — stacked CatBoost trade ranker

Generate out-of-fold foundation predictions only (never in-sample stacking features), then feed median/quantiles/forecast volatility/related-item forecasts into one global CatBoost ranker. Add tax, buy limit, spread, volume, freshness, categories, published upcoming-update events, then measured own-fill history. Labels estimate net gp/hour with holding time/capital and downside penalties; they do not merely reward direction. Tune risk and allocation on walk-forward validation; compare feature ablations and all execution presets. Open final recent holdout only after configuration/model selection is frozen and logged.

## Orchestration

Scheduled jobs (proposed UTC schedule, not installed by phase 1):

1. Existing C++ workers continue unchanged. At 00:15 daily, `snapshot` exports a bounded completed interval to a new immutable path with a manifest; fail on empty/invalid output. Retain overlapping raw snapshots for provenance, deduplicate before research.
2. At 00:45, quality gates and feature/label generation publish versioned artifacts. Labels arrive only after their horizon closes. At 02:00 weekly, create/update walk-forward experiments on the development period only.
3. A resource-limited queue runs adapter subprocesses with `uv run --project ml/environments/<family> --frozen ...`; each has an independent lock/cache and failure status. Each job consumes only a snapshot/experiment and emits forecast artifacts. Never import conflicting packages into the harness environment.
4. After forecast validation, the core environment invokes the shared backtester for every model, track, fold, regime and preset. Write results atomically under `ml/runs/<id>/`; JSON + Parquet are authoritative, DuckDB reads them for comparison. Resume by artifact hashes, not directory names. Phase 1 has CLI primitives and result artifacts; scheduler/queue/resume and cross-run comparison automation are later work.
5. Daily forward-test decisions append to a prediction log **before outcomes exist**, with timestamps, model/checkpoint hash and data cutoff. Later jobs append realized quotes and paper orders/fills; real own-fill logs require a separate authorized integration. No automatic trading is introduced. Track live results by model/preset and report pretraining contamination as unknown. Historical backtests are indicative, not proof.

Interactive work: inspect quality failures; choose split/holdout dates; review licenses and hardware; develop adapters; select models using development folds; freeze selection and authorize a one-time final holdout evaluation. Register repeated holdout access and require a new prospective period afterward. Live forward performance is the primary evidence against unknown foundation-model pretraining overlap.

Run records should include code/snapshot/config/dependency hashes, checkpoint revisions, feature schema, execution policy, availability policy, train/validation/holdout boundaries, label horizon, source regime, seed, metrics and artifacts. Reject comparisons when these differ outside the explicit model/track dimension. Optimistic/moderate/conservative fills are sensitivity scenarios until calibrated with real own fills.

## Sources and boundary decisions

- Existing repository: `backend/sql/001_create_items.sql`, `002_create_price_events.sql`, `backend/src/prices/{PricePoint.hpp,TimeseriesClient.cpp}`, `backend/src/jobs/PriceBackfillJob.cpp`.
- Tax reference: https://oldschool.runescape.wiki/w/GE (floor boundary discrepancy with the requested rule is explicit above).
- CatBoost official installation: https://catboost.ai/docs/en/concepts/python-installation . Python 3.13 compatibility is established by actual installation/execution, not assumed from all model packages.
