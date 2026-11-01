# Archive audit — bounded reconnaissance

2026-11-01. This is a real but partial audit. Only documentation, metadata, manifests, Parquet footers and two-row samples were inspected. No full-table scans, source acquisition, collector changes, model fits or holdout observation reads occurred. Previously generated summaries are explicitly reported, not replicated.

## Locations and repository

Observed VPS hostname v2202605360246461845. Repository /home/martin/src/osrs-market, branch ml/financial-model, HEAD 4f281ba at reconnaissance; initially clean. Remote devstash is https://git.devstash.tech/martinko/osrs-market.git; origin is GitHub xmartinko/osrs-market. devstash main HEAD was 8e03d49; devstash ml/financial-model was 0bf062b. Do not reset or replace these histories.

Repository contains C++ backend/sql/migrations, React frontend, auth/auth-service, Rust tui, ml Python research harness, docs and scripts/research. No repository AGENTS.md was found by scoped find. Existing ml README, docs/data-coverage.md, docs/data-sources.md, docs/deliberation-after-null.md and docs/prospective-pipeline-repair.md materially constrain this design. ml uses Python >=3.13,<3.14, uv lock, CatBoost, DuckDB, NumPy, pandas and PyArrow. Do not replace it automatically with a new stack.

Archive /home/martin/osrs-data occupies **48G** by live du -sh (rounded; includes raw copies and research artifacts). Live PostgreSQL collection exists per repository docs; no live DB credentials or rows were queried. forward/ contains SQLite observation and prediction ledgers for 300s/86400s; schemas and contents not inspected. server/, sources/, assembled-v2/v3/, execution diagnostics, weekly history and prior runs exist.

## Physical source inventory

Existing report: sources/coverage-20261030T214757409995Z/coverage.json, generated 2026-10-30T21:48:04Z. Read its group counts this session; did not independently recount partitions. Reported acquired canonical rows 935,898,166; with legacy 941,059,501. These overlap and include seasonal economies. **They are neither unique training examples nor independent samples.**

| Source | Reported rows / item IDs | Reported span UTC | Meaning / limitation |
|---|---:|---|---|
| Kaggle main 5m | 876,507,211 / 4,513 | 2021-03-08 07:35 to 2026-10-17 13:10 | Wiki-derived mirror, not independent corroborating trades |
| Wiki v2 5m | 7,174,028 / 4,497 | 2021-03-08 07:35 to 2026-10-30 21:40 | Direct bulk repairs plus recent tail; not exhaustive direct historical collection |
| Wiki v2 1h | 6,880,619 / 4,530 | 2021-03-08 07:00 to 2026-10-30 20:00 | Recent Aug–Oct hourly window verified by prior completion report; earliest probes do not imply contiguous coverage |
| Weird Gloop all | 16,494,792 / 4,674 | 2015-02-27 to 2026-10-30 | Guide-price history; not equivalent to trade-side averages; volume begins unevenly in 2018 |
| Weird Gloop last90d | 1,358,437 / 4,577 | 2026-08-02 to 2026-10-30 | Overlap; 298 bond rows lack volume |
| Jagex guide | 246,240 / 1,368 | 2026-05-04 to 2026-10-30 | Guide prices, not quotes; many requested IDs empty/missing |
| Academic UTK | 10,378,566 / 3,525 | 2020-02-03 to 2020-02-07 | Very short, zeros/nulls, unspecified economy; quarantine |
| Kaggle daily | 1,550,485 / 4,420 | 2021-03-08 to 2026-06-27 | Derivation overlaps 5m; not extra independent evidence |
| Wiki latest | 9,048 / 4,524 | 2026-10-30 snapshots | Side transaction timestamps differ from observation timestamp |
| Private GE Tracker weekly | 1,803,631 (existing docs) | not re-audited here | No new automated acquisition; prior terms review prohibits it; exclude default reproducible/public track |

Separate seasonal partitions: Deadman Reborn 1,816,933; FSW2022 4,611,444; Apocalypse 2,321,831; Armageddon 2,289,672; Annihilation 3,998,094. Exclude all from main economy. Unclassified legacy IDs also remain separate: 26 Kaggle IDs/247,494 rows and 27 latest IDs/54 rows. Today's mapping does not establish historical identity.

## Directly inspected schemas / samples

prices.parquet: 30,458,813 bytes, **2,502,566 rows**, 3 row groups, ZSTD. item_id int32; name string; members bool; buy_limit int32; ts int64; side prices/volumes int64; mid_price double; total_volume int64. items.parquet: 163,811 bytes, **4,524 rows**, ZSTD, IDs/names/examine/members/alchemy/store value/buy limit/icon mapping. Metadata catalog count is not the number of eligible tradeable series.

Original first sampled item2 rows: ts1761696000 and1761782400; high207/208, low201/201. These are daily backfill entries, not proof of five-minute cadence. Metadata is current revision. Names/limits/members must not be used as historical facts without dated revisions.

Sample canonical Kaggle partition: sources/kaggle-5m/canonical-v2/main/prices_5m/year=2021/month=11/data.parquet, 10,969,245 rows, 150,417,190 bytes, 90 groups, ZSTD. Retains raw int32 columns plus canonical int64 ts, float64 prices, int64 volumes, source/economy. Sample item530 raw timestamp5456720 maps to ts1637016000; next raw5456721 maps to1637016300. **Raw timestamp is a 300-second bucket index, not Unix seconds.** Prior timestamp-validation.json corroborates ×300 against three Wiki responses; October2026 prices are rounded in mirror versus v2 decimals despite matching volumes. Three checks do not validate every partition.

Sample Wiki latest file1793381862.parquet: 4,551 rows, ZSTD. Canonical ts is observation time, while source_extra retains highTime1793381803 and lowTime1793381771 for item2. Generic avg_high_price/avg_low_price columns hold latest transaction prices in this source; **column names alone do not define semantics**.

## Field contract

| Field | Established / source-qualified meaning | Unknown or prohibited assumption |
|---|---|---|
| item_id + economy | Source item identity, main/seasonal classification | Numeric ID lifetime and reuse need dated mapping |
| ts | Canonical Unix seconds UTC; bucket start for bulk 5m/1h; snapshot observation time for sampled latest | Not universally availability time, period end or last trade |
| avg_high_price | Average instant-buy transaction price for aggregate feeds | Not live ask, passive sell fill, or all-client history before break |
| avg_low_price | Average instant-sell transaction price for aggregate feeds | Not live bid or guaranteed aggressive sale |
| side volume | Reported traded units in that direction/window | Not queue depth, our fill allocation, or pre-break complete market volume |
| mid_price | Arithmetic side mean where both present, or scalar guide price in some sources | Not executable midpoint; source-specific type required |
| total_volume | Side sum for compatible aggregate source | Never add overlapping mirrors or forward-fill interval volume |
| buy_limit, name, members | Current metadata in original export; revision archives exist | Historical limits/lifecycle not reconstructed |
| fetched/available time | Raw HTTP evidence retained for some sources; forward ledgers exist | Historical publication/ingestion latency not generally established |

No complete order book, queue position, personal order IDs or real transaction execution ledger was established in inspected sources. README lists opt-in completed trade synchronization as planned. This does not prove no private fills exist elsewhere.

## Quality and continuity

Original EXPORT_METADATA.json explicitly describes mixed daily/hourly/5m change-based events. Unchanged state may be omitted by collector. Database uniqueness(item_id,timestamp) cannot resolve different source/window collisions. Preserve source, economy, resolution, price type, observation identity and payload hash in any future derived panel.

Existing assembled-v3 quality.json reports original high null12.92%, low12.76%, midpoint25.68%, current limit6.87%; 231,792 jitter gaps. Inferred daily panel1,466,390 rows/4,523 items/359 dates, 124,974 inverted side spreads, 107,882 missing buckets within lifetimes. 1h450,822 rows/7 dates; 5m481,052/2 dates, midpoint null60.86%. These are properties of the old reconstruction, **not** the much larger later acquired mirror. Manifests explicitly mark interval_status='inferred, not recovered', availability delay300s assumed; they exclude mixed boundaries. Do not train high-frequency models on this reconstruction merely because a broader archive exists.

Later coverage report says union591,201 nonempty 5m buckets and2,825 missing grid buckets; 2,986 mirror holes requested,162 yielded data,2,824 remained empty. Empty upstream response does not identify an outage versus no reports. Exact outage list, duplicate/conflict rate and per-item null/zero-volume rates of the broad canonical archive were **not recomputed here**. Cross-source deduplication, integer overflow screens, chronology, corrupt partitions, dated lifecycle and latency validation remain Phase One gates.

## Measurement break and rights

[Wiki real-time API documentation](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices) confirms RuneLite-only history before2026-09-30 and Jagex all-client reporting thereafter; v2 supports decimal averages and prices above signed32-bit. Partition by provider regime and numeric representation. Do not infer constant volume scale or causal economic change from that boundary. Concurrent GE rule changes confound attribution (06).

Existing docs/data-sources.md records mirror redistribution restrictions/uncertain upstream rights, terms evidence, and a GE Tracker acquisition prohibition. No rights were newly granted here. Review source-specific permissions before public derivative datasets; Git contains only methodology/aggregate audit facts. [Jagex terms](https://legal.jagex.com/docs/terms), [Weird Gloop licensing](https://meta.weirdgloop.org/w/Licensing). No game-account automation authorized.

## Readiness verdict

Worth a bounded forecasting study: years of 5m aggregate history appear available. 5m/15m/1h/4h/24h/7d are potentially supportable after source-specific canonicalization. Seven-day labels need ≥7d future coverage and much longer histories; interpolated daily guide history cannot support intraday labels. Current evidence supports research on reported aggregates, not executable profitability or continuous intrabucket barrier events.

Immediate missing observations: immutable historical source/resolution lineage; trustworthy publication times; dated mapping/limit changes; source-overlap conflict audits; independently logged prospective forecasts; and, for execution validation, voluntarily recorded own order/fill/cancellation histories with timestamps. No acquisition is initiated by this proposal.

## Reproduction commands (read only)

From Windows use ssh.exe hermes-netcup and run these in remote bash; avoid nested Windows quoting by piping a reviewed script. Access requires the existing authorized Windows SSH identity, not any copied private key.

```bash
cd /home/martin/src/osrs-market
git status --short
git remote -v
cat /home/martin/osrs-data/EXPORT_METADATA.json
cat /home/martin/osrs-data/assembled-v3/quality.json
cat /home/martin/osrs-data/sources/coverage-20261030T214757409995Z/coverage.json
cat /home/martin/osrs-data/sources/kaggle-5m/timestamp-validation.json
du -sh /home/martin/osrs-data
# Existing venv: use ParquetFile(...).metadata/schema_arrow and iter_batches(batch_size=2)
# on pre-holdout historical source partitions only; do not scan held-out observations.
```
