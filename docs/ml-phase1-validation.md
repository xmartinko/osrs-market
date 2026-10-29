# Phase 1 execution record — 2026-10-29

**Legacy price arithmetic:** nonzero slippage/haircut figures below do not measure
their labelled bps costs. The [price correction](execution-price-correction-validation.md)
explains the defect and replaces the phase-2 development sensitivities. Phase 1
has not been rerun in that correction; no replacement phase-1 numbers are claimed.

Implemented code commit: `7a648877be429f529bc35801b88eed4c735f0dfd`, branch
`ml/financial-model`. The completed run records `dirty: false` at that commit.
No C++ collector, existing schema, frontend, auth or compose files changed.

## Executed checks

Python: CPython 3.13.5. Resolved and actually imported/executed: CatBoost 1.2.10,
DuckDB 1.5.6, pandas 2.3.3, PyArrow 23.0.1, NumPy 2.5.4. Dependencies and wheel
hashes are recorded in `ml/uv.lock`.

```console
$ uv run --project ml --frozen ruff check --config ml/pyproject.toml ml/src ml/tests
All checks passed!
$ uv run --project ml --frozen ruff format --config ml/pyproject.toml --check ml/src ml/tests
14 files already formatted
$ uv run --project ml --frozen pytest -q
......................................                                   [100%]
38 passed in 6.00s
```

Tests cover integer tax floors, the requested exempt-through-50 boundary and configurable
Wiki boundary, per-unit rounding/cap, int64 prices, checksums, streamed read-only export
with a mocked connection, unknown/variable source intervals, overlap rejection, freshness
uncertainty, cash reservations across slots, partial fills, latency, expiry, four-hour limits,
zero-volume/stale rejection, residual inventory, timestamp horizons, causal features,
purge/holdout/regime boundaries, real global CatBoost fitting and baseline forecasts.
The initial test run exposed three mixed pandas/Arrow timestamp arithmetic failures;
timestamp dtypes were made consistent and the final suite above passes without warnings.

## End-to-end execution

```bash
uv run --project ml --frozen osrs-ml fixture --output ml/data/synthetic.parquet
uv run --project ml --frozen osrs-ml run \
  --snapshot ml/data/synthetic.parquet --output ml/runs/phase1-verified
```

Fixture output (excluding its wall-clock export timestamp):

```json
{
  "schema_version": 1,
  "source": "synthetic",
  "rows": 13702,
  "sha256": "872a10804ef054bd72956b3cde44f5309b41a8ef6b7f06c33b30dcd01af8fca7",
  "seed": 0,
  "warning": "Periodic deterministic fixture; no financial inference"
}
```

Selected real console output from the completed all-preset run:

```text
        model        track       preset          regime  folds  net_gp_per_hour  worst_drawdown_pct  mean_fill_rate
     catboost full_feature     moderate post_2026_09_30      2           -15.42               0.004           0.002
spread_volume full_feature     moderate post_2026_09_30      2          -151.08               0.026           0.030
     catboost full_feature     moderate  pre_2026_09_30      2             7.82               0.006           0.002
     catboost   price_only     moderate  pre_2026_09_30      2             4.18               0.006           0.001
spread_volume full_feature     moderate  pre_2026_09_30      2          -141.85               0.037           0.021
Completed 96 model/track/fold/preset evaluations; holdout NOT evaluated.
Artifacts: /home/martin/src/osrs-market/ml/runs/phase1-verified
Synthetic results, when used, demonstrate execution only; they are not evidence of profit.
```

This is 4 models × 2 tracks × 4 folds × 3 presets. Each CatBoost track/fold fits four
global regressors. The 1h end-to-end path ran; 4h/24h label generation was tested,
but complete 4h/24h tournaments were not run. Final 20% holdout starts at Unix second
`1790934000`; no holdout features, labels or model metrics were constructed.

Further DuckDB queries of actual artifacts, CatBoost/full-feature/moderate only:

| Regime | Net gp/hour | Sum of independent fold net gp | Worst fold drawdown | Mean buy fill rate | Time-weighted mean capital tied | Return MAE | End inventory units summed across folds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| before 2026-09-30 | 7.8188 | 374 | 0.0056% | 0.222069% | 409,480.03 gp | 0.00844 | 0 |
| from 2026-09-30 | -15.4186 | -442 | 0.0042% | 0.221829% | 401,530.56 gp | 0.00815 | 12 |

Each fold starts with 10M gp; these are independent portfolios, not a continuous compounded
strategy. Net return on capital is available per fold in `results.parquet` and each metrics JSON.
Mean capital above is weighted by elapsed time; mean fill rate is an arithmetic mean across
the two folds, also matching the CLI summary. Error is a weighted MAE across valid labels.
Reported P&L includes residual inventory marks; separate cash and realized P&L are retained.
The no-trade comparator returned exactly zero in every scenario.

An additional artifact audit checked all 96 metric files for nonnegative cash,
`net_gp == end_cash + end_inventory_mark - initial_cash`, and
`buy_units_filled - sell_units_filled == end_inventory_units`. Real audit output:

```text
Artifact accounting audit: 96 scenario ledgers passed; no-trade P&L is zero
```

Generated Parquet/checkpoints/ledgers remain under ignored `ml/data/` and `ml/runs/` in
this workspace. This committed record and the deterministic generator make the run reviewable
without committing large model artifacts. Output paths must be new when reproducing it.

## Live database failure and remaining scope

`DATABASE_URL` was not configured. TCP localhost:5432 accepted connections, but probing the
development database with the credentials in the existing compose file failed with
`OperationalError`: **password authentication failed**. The actual `snapshot` CLI attempt
using those credentials exited 1:

```text
Snapshot failed (OperationalError); check DB connectivity/permissions
```

No source tables were queried, no live snapshot was published and no database was changed.
The exporter has unit coverage with a mocked psycopg connection; **successful live Postgres
export is not verified**. Use a read-only credential to test it against the existing source next.

Current source tables discard returned interval and exact trade-time metadata. Historical
snapshots preserve unknowns; simulation overrides are estimates. Bucket timestamp semantics,
as-of mapping coverage, mixed-resolution conflicts and actual ingestion delays need a real-data
audit. Exact freshness cannot be reconstructed from aggregate history.

This phase has global CatBoost regression baselines and a shared executable ledger. It does
not yet have any foundation-model adapter, multi-model environment, official weight/license
review, quantile forecasts, event/category/related-item features, a stacked trade ranker,
downside-aware portfolio optimizer, calibrated fills, scheduled jobs or live forward logging.
The orchestration schedule in the implementation plan is proposed, not installed. CatBoost's
cost-adjusted regression score is an initial surrogate; allocation and risk handling need further
research. Terminal inventory marks do not prove liquidation. Unknown foundation pretraining
overlap will require prospective predictions recorded before their outcomes.

Next concrete step: obtain a SELECT-only connection to the existing database, export a bounded
snapshot with this CLI, and qualify interval provenance, as-of buy limits and bucket availability
before adding an official-package forecaster in its own environment.
