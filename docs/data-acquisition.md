# Private research acquisition

Run from this checkout. All payload output is restricted to `/home/martin/osrs-data/sources/` (including symlink resolution). Do not point these tools at the exported prices, weekly archive, forward v1 archive, assembled panels, server data or holdout. Nothing in this package is imported by the shipped server. The existing v1 collector and its paper/evaluation workflow are unchanged; the separate research collector uses v2 and accepts fractional prices.

```bash
cd /home/martin/src/osrs-market
uv run --project ml --frozen python -m osrs_ml.sources --help
```

The registry is `ml/src/osrs_ml/sources/registry.py`. Adapters reuse the existing `data.manifest` checksum/provenance writer. `weekly_research.py` remains the adapter for the already-held weekly source; no duplicate weekly scraper was added. `data.py`'s integer-only legacy export loader is intentionally unchanged. New canonical research partitions use float64 price columns and nullable int64 volumes.

## Commands

These commands return nonzero on transport errors, schema errors or provenance/checksum failures. A successful HTTP response alone is insufficient: parsing and publishing must succeed. Commands below are rerunnable; the same completed item/bucket/snapshot is checked and skipped.

| Source / purpose | Command after `uv run --project ml --frozen python -m osrs_ml.sources` | Cold-run cost and storage |
|---|---|---|
| Priority daily guide archive, all mapping IDs | `weirdgloop-all` | 4,674 item requests; at least 82 minutes at 1.05 seconds/start, allow 1.5–3 hours. About 316 MiB canonical including manifests; raw HTTP evidence adds roughly 1–2 GiB with retained responses/caches. |
| Rolling intraday guide history | `weirdgloop-last90d` | Same item universe and minimum request time; tens of MiB canonical for a first snapshot. Daily polls add only previously unseen `(item_id, ts)` records. |
| Wiki five-minute recent forward archive | `wiki-v2-forward` | Current 5m bucket + 1h of 5m catch-up and 24h of hourly catch-up; already-held buckets skipped. Usually seconds, at most a few dozen requests per cold poll. |
| Explicit Wiki timestamp backfill | `wiki-v2-bulk --resolution 5m --start 2026-10-17T13:15:00Z --end 2026-10-30T21:00:00Z` | About 3,800 requests for this tail, roughly 70–100 minutes cold; a few hundred MiB. End is exclusive and all boundaries must align. |
| Wiki hourly recent history | `wiki-v2-bulk --resolution 1h --start 2026-08-01T00:00:00Z --end 2026-10-30T21:00:00Z` | 2,181 hourly buckets, about 40–60 minutes cold, depending on other requests to the same host. |
| Wiki earliest hourly history (optional extension) | `wiki-v2-bulk --resolution 1h --start 2021-03-08T07:00:00Z --end 2026-08-01T00:00:00Z` | Roughly 47,000 requests, **at least 14 hours**; not all acquired in this run. Existing 5m mirror covers most of that period at finer resolution. |
| Wiki per-item 6h timeseries | `wiki-v2-timeseries --lookback 6h --ids 2 561 4151` | Three requests, 72 rows/item when the source has a full window. Omit `--ids` for all mapping IDs (another 82+ minutes). |
| Wiki per-item 7d timeseries | `wiki-v2-timeseries --lookback 7d --ids 2 561 4151` | Three requests, up to 168 rows/item; the live nature-rune sample returned 167 in one snapshot, not a fabricated complete window. |
| Wiki latest trades | `wiki-v2-snapshots` | One live latest response; current and unclassified legacy IDs separated. Latest values retain highTime/lowTime and are not volume buckets. |
| Wiki mirror, pinned version | `kaggle-5m` | Public 4.44 GiB compressed download; 68 monthly input partitions. Normalization uses DuckDB, 1 GiB memory cap and two threads. Allow tens of minutes. About 33 GiB total currently retained, including raw ZIP, extracted input and both immutable conversion versions. |
| Repair every missing timestamp in that mirror | `wiki-v2-repair` | Requires the completed mirror. Enumerates its timestamps and requests all 2,986 holes; about one hour cold. Resumes from bucket manifests. **162** holes yielded **224,474** rows; **2,824** returned empty. |
| Sampled Exchange module revision histories | `wiki-revisions --ids 2 561 4151` | Three tested histories fit one request each; continuation supported. Not a daily historical backfill. |
| Current item text/stat templates | `wiki-items` | 187 batches of up to 25 mapping names; a few minutes and MiB. |
| Current Exchange module text | `wiki-modules` | Same batching; numeric Lua literals parsed, nonliteral references preserved as text. |
| Monster drop-table templates | `wiki-monsters` | Category inventory + 67 page batches in measured run; direct category only. |
| Shop stock/price templates | `wiki-shops` | Category inventory + 21 page batches in measured run. |
| Literal current Wiki feature facts | `wiki-feature-facts` | Local conversion of already archived item, monster and shop pages: **181,600** field literals in the initial conversion, including bonuses, weight, drops and stock parameters. No network or Lua execution; unparseable numeric values stay null and original literals remain. |
| Seasonal markets, physically separate | `seasonal-dumps` | Five public archives, around 773 MiB retained including extracted CSV and canonical data. Every economy has its own directory and `economy` value. |
| Item and monster/drop metadata | `osrsbox` and, separately, `osrsreboxed` | Two public JSON requests/source; 14 / 16 MiB canonical plus HTTP evidence. Snapshot ages differ and incompleteness flags survive in raw extras. |
| Official daily GE graphs | `jagex-guide` | 4,674 item requests checked, about 82+ minutes cold; only 1,368 nonempty. About 38 MiB canonical including separate provider moving averages. |
| Daily Wiki CSV mirror | `kaggle-daily` | Public 35.7 MiB ZIP; no auth. Normalize only `full_data.csv`, retaining nulls; directory includes larger unused enriched files. |
| Bond guide history mirror | `kaggle-bonds` | Public 28 KiB ZIP; redundant with Weird Gloop, no volume. |
| Academic 2020 capture | `academic-utk` | Public 32.4 MiB CSV; about 56 MiB raw + canonical. Many zeros/unknown names; not promoted into a main-economy panel. |
| Embedded archived Wiki chart | `wayback-wiki` | One public replay, about 56 KiB HTML; 1,521 chart tokens, including timestamp conflicts. No interpolation. |
| Official forward world populations | `official-activity` | One public world-list request/poll; a few KiB parquet plus HTML evidence. Counts special economies too; not DAU. |
| Historical alchemy metadata | `kaggle-alch` | Public 49 KiB ZIP; 4,246 feature rows. |
| Historical polling workbook | `kaggle-polls` | Public 205 KiB ZIP; 1,794 question rows. Peak-player estimates are third-party and unverified. |

For a different explicit Wiki interval, replace the example end with an already completed aligned UTC timestamp. Keep the start `>=` the measured floor unless testing earlier empty coverage deliberately. A full direct five-minute crawl from March 2021 through October 2026 needs roughly **594,000 requests, over seven days at 1.05 seconds/start**, and duplicates almost all of the acquired mirror. The actual mirror plus tail plus repaired holes is the efficient acquisition route. Empty buckets remain recorded, not interpolated.

The supplied, already-verified v2 lookbacks are retained as the acquisition reference: `6h` → 72 × 300 seconds; `24h` → 288 × 300 seconds; `7d` → 168 × 3,600 seconds; `30d` → 120 × 6 hours; `6m` → 180 × one day; `1y` → 365 × one day. This improves on the prior v1 item-timeseries behavior of returning 365 points regardless. Those settings were not re-derived; the fresh 6h/7d pulls acquire current windows, and individual items can still have missing points.

## Checkpoints, identity and append-only storage

Weird Gloop daily progress is checkpointed after each item under `weirdgloop-all/<snapshot>/checkpoint.json`. The default resumes the existing dated backfill, even after a calendar rollover. It does not silently create a fresh copy of all history tomorrow. To request a deliberate separate snapshot, pass `--snapshot YYYY-MM-DD-new` and account for its overlapping history separately.

The rolling source uses a UTC day snapshot by default. Rerunning that day skips completed items; another day's poll omits timestamps already stored for each item. Raw responses and raw row counts remain available, so later source revisions are inspectable even where first-seen canonical rows are retained. Run once per day to preserve a rolling window. Missing results are checkpointed distinctly from zero-volume observations; denials and schema changes stop with a nonzero exit.

Wiki bulk partitions use endpoint / UTC date / requested bucket timestamp. Canonical rows keep the exact returned float prices, volumes and raw source fields. A mismatched returned timestamp is an error. Empty buckets have zero-row parquet/manifests and are considered completed **for this acquisition**, not proof that the provider can never repair them. Use a separate research root under `sources/` for a deliberate future recheck. Monthly archive conversion keeps all source columns, records the timestamp scale and separates mapping-listed from unclassified IDs.

`completed()` verifies each partition checksum before a resume skip. Publication is serialized per partition, so forward collection and repair can meet safely; existing completed bytes are never replaced. A crash after parquet publication can recover its manifest only when the expected table matches exactly. Partial downloads use `Range` + `If-Range` with ETag/Last-Modified; changing entities restart the partial transfer rather than concatenate incompatible versions. Existing final downloads without provenance are refused. HTTP payload files are immutable; only checkpoint and URL lookup metadata are updated. No dataset is committed.

Guide-price-only sources leave both trade-side prices and side volumes null. Their guide value maps to `mid_price` as the canonical scalar field, **not a claim that it is an observed bid/ask midpoint**. No artificial side split is made. The usual columns are `item_id, name, ts, avg_high_price, avg_low_price, high_price_volume, low_price_volume, mid_price, total_volume`, with `source`, `economy` and `source_extra` (or retained raw archive columns). Features have separate schemas and are excluded from price totals. Metadata fetched today is not represented as available in the historical market at its price timestamp.

## Rolling services on this machine

The three research service/timer pairs are checked into `ml/scheduling/` and installed in `~/.config/systemd/user/`:

| Timer | Actual cadence | Target |
|---|---|---|
| `osrs-research-wiki.timer` | Every five minutes, up to 20 seconds jitter | Wiki v2 catch-up collector |
| `osrs-research-last90d.timer` | Daily at 07:00 UTC, up to five minutes jitter | Full mapping rolling Weird Gloop poll |
| `osrs-research-activity.timer` | Every five minutes, up to 20 seconds jitter | Official world populations |

They write research directories only. The prior v1 `osrs-ml-forward` service continues its existing independent behavior; none of its code, stored observations or paper ledger was changed by this work. The additional research host locks coordinate all **new research** requests; they do not control that pre-existing legacy service. The public endpoints remain separate from the shipped server.

```bash
cp ml/scheduling/osrs-research-* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now osrs-research-wiki.timer osrs-research-last90d.timer osrs-research-activity.timer
systemctl --user list-timers --all
```

This is a user systemd schedule; it follows that user's service-manager lifetime. A source-level process lock prevents an ad hoc backfill from racing its scheduled poll. The 90-day poll timeout is four hours; interruptions resume from per-item completion records.

## Reproduce coverage, policy audit and tests

```bash
uv run --project ml --frozen python -m osrs_ml.sources.report
uv run --project ml --frozen python -m osrs_ml.sources.request_audit \
  --require-ua-since 2026-10-30T21:04:00+00:00 \
  --output /home/martin/osrs-data/sources/verification-next-http-audit.json
cd ml
uv run --frozen pytest -q
cd ../tui
PATH="$HOME/.cargo/bin:$PATH" cargo test --release
```

Coverage freezes the completed partition inventory, checks footer rows against manifests and writes a **new** timestamped report directory. Per-source summaries include rows, items, timestamps, non-null/positive volume coverage by year, positive finite price counts and one real sample. Per-item parquet reports retain first non-null-volume dates and last null dates. The original baseline's 435 file sizes/mtimes are checked, and only legacy parquet **footers** are read for counts; sealed observation rows are never loaded. Mirrors, overlapping endpoint windows and alternative economies are reported explicitly rather than advertised as unique independent prices. Hashes are stored in manifests; this report checks row counts, while resume validates file hashes.

HTTP audit reads actual attempt records, excluding URL lookup indexes. It reports status counts, advertised quota headers, minimum start spacing where timestamps were recorded and all observed UAs. `--require-ua-since` makes a nonconforming UA after the chosen cutoff a failing command. Earlier pre-existing artifacts are not retroactively relabelled. Offline tests use recorded excerpts and mock transports; they do not contact these services.

See [source policy and gaps](data-sources.md) for licensing notes, exact missing/defunct endpoint evidence and the September 2026 structural break. Never retry an access denial by changing identity, login state, proxies or challenge-solving tools.
