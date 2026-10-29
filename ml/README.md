# OSRS ML research harness

This Python 3.13 research component runs alongside the existing C++ pipeline. Phase 2
added a daily experiment and a prospective Wiki archive/paper ledger with user timers.
The [post-phase-2 assessment](../docs/next-steps.md) defers the foundation-model tournament
until execution assumptions can be tested. There are no C++ schema changes or automatic trades.

## Diagnose execution on frozen development predictions

From the repository root, replay an existing completed daily experiment:

```bash
export OSRS_DATA_DIR=/home/martin/osrs-data
uv run --project ml --frozen osrs-ml diagnose-execution \
  --panel "$OSRS_DATA_DIR/assembled-v3/daily.parquet" \
  --development-run ml/runs/phase2-real-v1 \
  --output "$OSRS_DATA_DIR/execution-diagnostics-new"
```

Use a new output directory. The command reads only the saved development forecast/metric
paths and filters panel observations to each recorded development fold before loading them.
It trains no models and does not select parameters or open holdout artifacts. It checks
panel/config/dependency hashes, decision-key coverage and original-preset P&L/quantity
reproduction using quarantined `legacy_v1` arithmetic. Main results use
`integer_lots_v2`: positive whole-GP price lots, notional bps costs with an explicit
fractional-GP residual, and per-lot tax. Unrepresentable sale prices retain inventory
and log `untradeable_at_granularity`; zero terminal valuations are not fills.
`adverse_ticks` is a separate deterministic stress, default zero. The split into
adjacent integer lots is a hypothetical cost allocation, not evidence about actual
fill prices or fill probability. See the [price specification](../docs/execution-price-correction.md).
Undefined saved scores are retained only where required prices are missing
or inverted. They remain ineligible for trading, as in the original executor.

All five models face 19 fixed scenarios: the three original presets, seven one-factor
changes from optimistic to moderate, moderate with passive prices restored, and a grid
of 0/5/10/30 bps slippage per side under passive and crossed pricing. Some scenarios
intentionally duplicate policies as consistency checks. Factors interact: changes in
GP across one-factor replays are not an additive attribution of the preset difference.

`run.json` records input/code hashes, every policy, completion count and status.
Every completed replay publishes fills, orders, equity and metrics, so partial runs
retain evidence. Only `status=complete` certifies the full grid and original-preset
reproduction. Existing outputs cannot be overwritten; failed attempts remain visible.
`results.parquet`/`results.csv` report per-fold P&L, actual tax charged in the simulation,
fill lots, bought/sold units, terminal inventory and zero-buy/inventory-only status.
Two price lots can represent one fill opportunity; use `opportunity_id` or the
`buy_fill_opportunities`/`sell_fill_opportunities` metrics to compare opportunity counts.
Reference notionals, achieved bps, paid costs, tick costs and rounding residuals are
separate fields. Conservative offer reservations are not paid slippage.
`legacy_reproduction/` preserves the three original presets for each model/fold;
`preset_deltas.csv` gives their corrected P&L, cash, marks and exposure differences.
Input-gate counts overlap and do not attribute dynamic cash or slot rejections.

`fixed_fill_repricing.csv` and per-model repricing ledgers hold the optimistic quantities,
times and terminal inventory mark fixed while changing buys to high and sales to low,
recomputing per-item tax. This is an accounting counterfactual that can violate cash,
capacity and order ceilings; it is not another executable portfolio. Missing crossed
prices produce an incomplete diagnostic rather than invented prices.

Every output remains **current_limits_sensitivity**, with hypothetical aggregate fills
and historical capacity lookahead. Neither positive GP nor zero-buy GP demonstrates
live profitability. See the assessment for the calibration and prospective evaluation gates.

Audit a completed corrected replay independently:

```bash
uv run --project ml --frozen python -m osrs_ml.execution_audit \
  "$OSRS_DATA_DIR/execution-diagnostics-new" "$OSRS_DATA_DIR/assembled-v3/daily.parquet"
```

The audit loads only the manifest's development folds and verifies legal prices,
cash/inventory accounting, costs and residuals, tax, capacity, limits, timing,
offer ceilings, marks and no-trade invariants. It cannot establish achievable fills.

## Frozen multi-horizon strategy battery

The [registered battery](../docs/strategy-battery-protocol.md) and
[executed results](../docs/strategy-battery-validation.md) cover 71 rules at three
participation shares. All 213 scenarios completed; none survives search correction.
The [alpha journal](../docs/alpha-journal.md) preserves continuation decisions.

```bash
export OSRS_DATA_DIR=/home/martin/osrs-data
ml/.venv/bin/python -m osrs_ml.battery \
  --output "$OSRS_DATA_DIR/strategy-battery-v1" --acknowledge-private-research
ml/.venv/bin/python -m osrs_ml.battery_audit "$OSRS_DATA_DIR/strategy-battery-v1"
```

The runner resumes unchanged completed scenarios and refuses changed provenance.
The independent audit checks source-priced fills, conversion inventory, cash,
limits, slots, timing, participation, marks and complete-family reporting.
All ledgers, the full aggregate CSVs and bootstrap diagnostics stay outside Git.

## Original harness usage

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

## Participation bounds on frozen development predictions

The [reasoning and frozen protocol](../docs/participation-bounds.md) distinguish
reported passive fills from our unknown queue allocation. Run the fixed grid with:

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  python -m osrs_ml.participation \
  --panel /home/martin/osrs-data/assembled-v3/daily.parquet \
  --development-run ml/runs/phase2-real-v1 \
  --output /home/martin/osrs-data/participation-bounds-v3
```

`volume_bounded_v3` freezes order prices, requires entire eligible buckets to occur
while the order is live, and caps each partial fill by the chosen share of
price-compatible reported volume, remaining quantity and buy allowance. It keeps
`integer_lots_v2` arithmetic. Existing `bucket_proxy_v1` policies remain the default
for reproduction. `mean_proxy` qualifies on the side average; `moment_upper` uses
a loose price-compatible volume ceiling under an explicit one-GP mean uncertainty.
Neither identifies queue priority or adverse selection. All three presets use
passive prices for this experiment, with their original cost/time settings.

The 810 development combinations include no-trade and zero participation.
`break_even.csv` reports sampled profit ranges and the first profitable sampled
share (requiring buys and sales); `sign_changes.csv` records all observed sign
reversals, and `ranks.csv` preserves model ordering at every share. Thresholds are
brackets, without interpolation or a monotonicity claim. Full ledgers and manifests
remain outside Git. Every result is `current_limits_sensitivity`, not calibrated
historical profitability. Audit completed output with:

```bash
uv run --project ml --frozen python -m osrs_ml.execution_audit \
  /home/martin/osrs-data/participation-bounds-v3 \
  /home/martin/osrs-data/assembled-v3/daily.parquet
```

## Private weekly breadth and time-invariance research

The frozen [deep-history protocol](../docs/deep-history-protocol.md) and
[executed validation](../docs/deep-history-validation.md) cover private GE Tracker
history, earlier-only weekly rank diagnostics and conditional participation CIs.
All source responses, panels, scores and ledgers belong under the external
`OSRS_DATA_DIR`, with explicit private-research acknowledgement; only aggregate
findings and methodology belong in Git.

`python -m osrs_ml.weekly_ingest` collects the complete frozen catalogue with eight
workers by default (maximum sixteen), cached responses, atomic checkpoints and
exponential backoff for 403/429/5xx or connection errors. There is no fixed request
delay. Persistent errors pause collection; resume honors saved server backoff.
`python -m osrs_ml.weekly_coverage` reports raw date-only spans, first years and
annual development missingness. `python -m osrs_ml.weekly_research` fits only the
six predeclared market features and evaluates annual later eras at exact one- and
four-week horizons, without calendar or age features. Four/eight-week empirical
blocks preserve cross-item dependence. Eligible per-item Gaussian mean intervals
require the frozen normality and lag screens. Weekly returns remain diagnostics,
not account profit claims. `python -m osrs_ml.uncertainty` uses the saved corrected
development ledgers and seven/fourteen-day paired empirical blocks to report
nonmonotone first-positive-grid intervals, including the no-positive infinity atom.
The linked validation document provides the exact command lines and limitations.
