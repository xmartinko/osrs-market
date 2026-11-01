# Phase One development panel gate

2026-11-01. Implemented by a native Codex subagent. This document records the pipeline contract and synthetic checks, not an executed full archive audit or a predictive result. The lead executes the bounded panel build after review.

## Inspected evidence

Read existing `ml/src/osrs_ml/sources/columnar.py`, the Kaggle adapter, `docs/data-sources.md` and Phase Zero audit. No repository AGENTS.md was found in the inspected local root or scoped `ml`/`research` paths. Used the existing authorized Windows SSH client; no credentials were read.

On the VPS, inspected the schema, footer and two-row sample of existing `sources/kaggle-5m/canonical-v2/main/prices_5m/year=2024/month=10/data.parquet`. Canonical `ts`, `item_id` and directional volumes are int64; canonical prices are float64. Raw `timestamp` is int32 and is a **300-second bucket index**, not Unix seconds. Sample raw 5,759,136 mapped to Unix 1,727,740,800. The sidecar identifies `timestamp_scale=300`, source `kaggle-5m`, economy `main`, `item_filter=listed`, and upstream dataset version 1. There is no independent source-interval column. Resolution is supported by adapter provenance and the raw-index identity, not inferred from observed gaps.

The sample predates the development start. No held-out observations were inspected. Reading month footers can expose month-wide timestamp statistics; those are not model inputs or test outcomes.

## Frozen windows and eligibility

Defaults in `osrs_ml.probabilistic_data`:

| Purpose | UTC start, inclusive | UTC end, exclusive |
|---|---|---|
| Development panel | 2024-10-29 00:00 | 2026-07-26 00:00 |
| Initial universe selection | 2024-10-29 00:00 | 2025-10-29 00:00 |
| Validation fold 1 | 2025-10-29 00:00 | 2026-01-27 00:00 |
| Validation fold 2 | 2026-01-27 00:00 | 2026-04-27 00:00 |
| Validation fold 3 | 2026-04-27 00:00 | 2026-07-26 00:00 |

Validation and training splits remain the forecasting harness's responsibility: trailing 365-day training and a 24-hour label purge. The panel builder never reads the reserved holdout beginning `1785024300`; its default exclusive end is `1785024000`. It rejects requests extending past the holdout boundary and requires hour-aligned endpoints.

The source file list is assembled from explicit year/month paths **before** opening Parquet; no recursive wildcard scans future months. SQL independently filters canonical timestamps to the permitted window. A boundary-month file can physically contain later observations: predicate pushdown and SQL filtering prevent their admission, although physical row-group reads are not claimed to exclude every byte belonging to later rows. Later monthly partitions are never opened.

Eligibility uses at least 95% both-side usable hours over the entire first training period, including absent hours in the denominator. Rank eligible items by initial-period observed volume, break ties by item ID, divide into three rank-based liquidity terciles, and select deterministically in round-robin order across them up to 100 items. No future liquidity, price or coverage affects selection. Fewer than 100 eligible items is recorded honestly. The canonical `listed` classification depends on current mapping, so survivorship selection remains a limitation; this pipeline does not reconstruct a historical all-item universe.

**Timing caveat:** the last selection hour closes at 2025-10-29 00:00 and is assumed available at 00:05. Freeze the universe and begin forecasts no earlier than that availability time, or remove that final hour if the first forecast origin is exactly 00:00. The panel's first-validation timestamp alone is not evidence the corresponding information was available at midnight.

## Aggregation and missingness

The builder admits only the single qualified mirror; it never adds overlapping Wiki/guide/seasonal data. Sidecar provenance, required schema, raw-index multiplication, 300-second alignment, source/economy identity, positive item keys and nonnegative known volumes are checked. Duplicate `(item_id, ts)` keys fail the build, including exact duplicate records; overlap is never averaged away.

Hourly means are weighted separately by side-specific volume, with separate disjoint sums of each direction's units. A complete hour requires twelve distinct aligned five-minute buckets. A positive-volume side with any missing/nonfinite/nonpositive contributing price has an unknown hourly price and is unusable. A complete zero-volume side retains volume **0** and price **NULL**. A missing bucket or unknown volume makes the hourly total **NULL**. No price, volume or missing timestamp is forward-filled or interpolated.

The final dense item/hour grid contains exactly:

`ts, item_id, avg_high_price, avg_low_price, high_price_volume, low_price_volume, mid_price, available_at, usable`.

`ts` is Unix hour-start UTC, midpoint is the arithmetic mean of the two weighted side means, and `available_at = ts + 3600 + 300`. The 300-second publication delay is an **assumption**, not measured historical ingestion. `usable` requires positive valid means on both sides and `avg_high_price >= avg_low_price`; the same criterion defines initial selection coverage. Inverted hourly observations are preserved and counted separately but excluded from usable labels and eligibility coverage. This conservative validity screen prevents learning apparent crossed-side opportunities; it does not imply asynchronous transaction aggregates are live quotes. Neither side is an executable bid/ask. No missing source hour becomes a synthetic zero-return observation.

## Reproducibility and bounded resources

The JSON sidecar stores source version, exact source paths, schema strings and schema SHA256, SHA256 of each Parquet footer and source-manifest bytes, declared source-payload SHA256, selected IDs/coverage/volumes/strata, windows, delay and gate/quality results. **Declared full-source payload hashes are not independently recomputed**; `payload_hash_verified=false` makes that distinction explicit. The generated panel receives a newly computed full SHA256. A footer fingerprint detects footer/schema changes, not arbitrary payload corruption; full payload verification is a separate diagnostic if needed.

DuckDB reads Parquet directly and aggregates within its configured memory limit, with temporary spill space outside the source. No source-sized Python/pandas frame is created. Initial selection scans all eligible items only in the first training year. Later aggregation filters to frozen selected IDs. Source validation and duplicate checks entail additional projected scans; runtime and spill volume are unmeasured. Defaults are two threads and a 1 GB DuckDB limit. Allow enough output filesystem space for temporary grouped hourly data; monitor the first build rather than assuming the memory limit bounds disk use.

The output must live outside the immutable source root and must not already exist. Temporary files are cleaned after completion/failure. Source files and manifests are opened read-only. The output is published only after successful qualification, aggregation, quality counts and hashing. No acquisition, service changes, GPU code, archive rewrite or holdout training is implemented.

Proposed invocation on VPS, using a new approved derived-output directory:

```bash
cd /home/martin/src/osrs-market/ml
.venv/bin/python -m osrs_ml.probabilistic_data \
  --source-root /home/martin/osrs-data/sources/kaggle-5m/canonical-v2/main \
  --output /home/martin/osrs-phase-one-artifacts/development-hourly.parquet \
  --memory-limit 1GB --threads 2
```

This command is documentation, not a claim it ran. Review emitted quality counts, frozen eligibility and timing assumptions before fitting. A failed source gate must not be waived silently.

## Verification performed

Twelve synthetic tests passed in the existing VPS Python environment (pytest 9.2.0), in an automatically removed temporary directory. They cover directional weighted means, availability, manifest fingerprint fields, immutable source bytes, duplicate refusal without publishing, zero versus null volume, incomplete/absent dense hours, provenance/raw-timestamp/negative-volume rejection, future-independent selection, inverted-hour exclusion from labels and selection, holdout/output guards, month pruning and same-month SQL filtering. No new dependencies were installed. These small synthetic tests say nothing about full archive performance.

Full-development counts, eligible item count, continuity, duplicate rate and source corruption rates remain **unmeasured by this new builder** until the lead executes it. Historical publication latency and real fills remain unobserved.

## Source terms and claim limits

Existing source documentation reports Kaggle version 1 as “Other (specified in description)” with an empty description; broad reuse rights remain unresolved. User authorization covers private research on the already held archive and does not establish redistribution rights. Keep source and derived market data private; commit code, tests, protocol and aggregate diagnostics only. No new acquisition is included. See [existing source inventory](../../../docs/data-sources.md), [upstream dataset](https://www.kaggle.com/datasets/antonygarand/osrs-ge-5m), [Wiki feed documentation](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices) and [Jagex terms](https://legal.jagex.com/docs/terms).

This panel can support probabilistic forecasts of reported transaction aggregates under declared latency/missingness rules. It cannot establish all-client pre-break volume, historical order-book depth, continuous intrahour barrier order or attainable paper-trade fills.
