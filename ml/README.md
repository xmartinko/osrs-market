# OSRS ML research harness

Phase 1 is an executable Python 3.13 research component alongside the existing C++ pipeline.
The [implementation and orchestration plan](../docs/ml-implementation-plan.md) describes the
foundation-model tournament, separate model environments and live forward evaluation.
There is no new collector, database schema, scheduler or automatic trading integration.

From the repository root, with `uv` installed:

```bash
uv sync --project ml --frozen
uv run --project ml --frozen pytest -q
uv run --project ml --frozen ruff check --config ml/pyproject.toml ml/src ml/tests
uv run --project ml --frozen osrs-ml fixture --output ml/data/synthetic.parquet
uv run --project ml --frozen osrs-ml run \
  --snapshot ml/data/synthetic.parquet --output ml/runs/demo
```

Output paths must be new. The fixture contains 13,702 deterministic rows across six items,
eight days spanning 2026-09-30, prices above int32, irregular gaps and zero-volume/stale buckets.
It intentionally contains predictable periodic patterns. Profit on it has no market significance.

Set `DATABASE_URL` outside the command line (a SELECT-only role is recommended), then export
a **bounded** time range from the existing tables; times are Unix seconds, end exclusive:

```bash
uv run --project ml --frozen osrs-ml snapshot \
  --start 1790294400 --end 1790985600 --output ml/data/research.parquet
uv run --project ml --frozen osrs-ml run \
  --snapshot ml/data/research.parquet --output ml/runs/research \
  --allow-unknown-metadata
```

The existing source schema does **not** persist returned intervals or exact side-trade timestamps.
The export keeps intervals NULL. Running these data requires the explicit override above,
which assumes 300-second buckets for event availability, but does not manufacture source metadata.
Exact last-trade freshness remains unknown; the loader computes a lower bound from positive-volume
bucket ends. Optimistic execution uses that lower bound; moderate/conservative add one source
interval as an upper-bound estimate. These estimates and interval diagnostics are persisted in
each fold's context Parquet. As-of metadata absent from `item_revisions` remains unknown;
unknown buy limits prohibit trades. A historical mapping revision inserted only during a recent
backfill is not evidence that its buy limit was known historically.

Data are read using psycopg in a read-only repeatable-read transaction, streamed into int64
Parquet and queried through DuckDB. Snapshot manifests contain row counts, source and SHA-256.
The data loader checks the checksum/schema/keys/values. Credentials are not written to artifacts.
Real event-time research still needs an audit of overlapping source resolutions, timestamps and
ingestion delays. `ingested_at` is retained; phase 1 simulates event availability at bucket end,
not ingestion-time availability. No live OSRS database is required for the fixture path.

The command evaluates four comparators: no trade, no-change/random walk, spread+volume and
global CatBoost without cross-item/event features. Each CatBoost track fits four global regressors
(return, log-volume, volatility and tax-aware hourly net return used as the score), not one per item.
`price_only` uses own-item returns/volatility; `full_feature` adds spread, volume, freshness, buy limit,
tax fraction and item identity. Fixed comparator inputs remain the same across both tracks.
The spread heuristic assumes a passive margin when ranking, then faces the same high-buy/low-sell
executor as every model; it cannot claim that a passive offer filled.

Choose `--horizon-hours 1`, `4` or `24`. Targets use timestamps, reject endpoints more than ten
minutes late and reject labels crossing the source regime boundary. The most recent 20% of
timestamps is reserved before constructing features/labels. Two expanding development folds per
regime train only on labels ending strictly before validation starts. Forecast errors exclude labels
ending outside the validation period. Each fold starts with fresh cash, no inventory and unused
buy limits. Fold results are independent portfolios; their equity curves must not be concatenated.
The CLI cannot evaluate the final holdout.

Every model uses `backtest.simulate`, the same long-only cash/slot/limit/partial-fill ledger. Orders
reserve cash and one slot through the final sale. Buy windows start on the first buy fill and last
four hours per item. Buys use subsequent observed high prices up to a fixed ceiling; sells use
subsequent low prices with adverse slippage. An execution bucket must start after order latency;
the order cannot consume its decision bucket. Buy orders expire; sell orders wait until filled or
the period ends. Unsold inventory stays on the ledger and receives a tax/slippage/haircut mark,
which is not a guaranteed liquidation value. No queue position or passive-fill proof is inferred.

| Preset | Side volume participation | Adverse slippage per side | Latency | Maximum freshness | Inventory haircut |
| --- | ---: | ---: | ---: | ---: | ---: |
| optimistic | 10% | 0 bps | 0s | 1800s, lower bound | 0% |
| moderate | 2% | 10 bps | 300s | 900s, upper estimate | 1% |
| conservative | 0.5% | 30 bps | 600s | 300s, upper estimate | 3% |

Buy expiry is 1800s. Participation rounds down to whole units, so low volume may mean no fills.
Use `--presets moderate`, `--cash-gp`, `--offer-slots`, `--allocation-bps`, or provide
`--execution-config custom.json` containing overrides, for example:

```json
{"moderate": {"participation_bps": 100, "buy_timeout_seconds": 3600}}
```

Every `ExecutionAssumptions` field is configurable and recorded. An unknown-interval override
must agree across scenarios. In Python, `TaxPolicy` also configures the rate, floor, cap and explicit
item exemptions. The default follows this task's **above 50 gp** rule: 50 is exempt. The
[Wiki rule](https://oldschool.runescape.wiki/w/GE) exempts **below 50**; use
`TaxPolicy(exempt_through_gp=49)` for that boundary. Tax is floored/capped per unit, then multiplied.
Changing tax for a research run also requires generating targets and scores with that policy;
the phase 1 CLI deliberately uses the single default policy throughout.

Run directories contain `run.json`, `results.json`, `results.parquet`, fold context,
forecast Parquet, CatBoost checkpoints and scenario-specific metrics/orders/fills/equity.
The run manifest records code revision/dirty status, dependency lock hash, versions, seed,
snapshot hash, holdout/folds and policies. Metrics include net gp/hour, return on initial capital,
drawdown, requested/filled units, buy fill rate, cash P&L, realized P&L, wait time, remaining
inventory and time-weighted/peak/end capital tied up, plus return/log-volume/volatility/net-score MAE.
Net P&L includes marked inventory. Cash P&L and realized P&L are reported separately.

For analysis, query results directly without mutating them:

```python
import duckdb
result = duckdb.sql("""
    SELECT model, track, regime, preset,
           sum(net_gp) / sum(elapsed_hours) AS gp_per_hour,
           max(max_drawdown) AS worst_fold_drawdown
    FROM read_parquet('ml/runs/demo/results.parquet')
    GROUP BY ALL ORDER BY regime, preset, gp_per_hour DESC
""").df()
print(result)
```

Compare only runs with matching snapshot, code, fold, horizon, execution and portfolio policies.
Larger cross-run registry/scheduler, downside-aware portfolio optimization, quantile calibration,
foundation adapters, stacked CatBoost ranker, event/category features and an append-only live
prediction log are planned, not implemented. Historical foundation-model evaluation may overlap
unknown pretraining data; a prospective forward test is required before believing an edge.
