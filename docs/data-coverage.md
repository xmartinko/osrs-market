# Measured acquisition coverage

Report generated **2026-10-30T21:48:04.193279+00:00** from the completed partition inventory in `/home/martin/osrs-data/sources/coverage-20261030T214757409995Z/coverage.json`. Full payloads and per-item coverage parquet stay outside git. This finishing pass resumed an acquisition already present on disk; it did not download every reported row afresh.

| Count | Physical price-observation rows |
|---|---:|
| Original acquisition baseline (`before.json`, original export + weekly + existing forward archive) | 5,053,476 |
| Source rows already held before finishing-pass cutoff 2026-10-30T21:04:00+00:00 | 928,739,335 |
| Additional canonical source rows acquired in this finishing pass | **7,158,831** |
| All acquired canonical source partitions now | **935,898,166** |
| Of those, rows with a positive finite price on at least one side or scalar field | 930,091,844 |
| Legacy price rows at the report's footer count | 5,161,335 |
| Total physical price rows now (legacy + acquired source partitions) | **941,059,501** |

These are **physical observations, not a count of unique independent item-times**. Wiki mirrors, direct bulk windows, timeseries snapshots, Weird Gloop/official guide prices and archived charts overlap. Counts exclude raw ZIP/CSV/HTTP copies, superseded conversions, metadata, drop definitions, world populations, revision archives, provider moving averages and report tables. Separate seasonal economies and unclassified IDs remain explicitly identified. The academic capture contains many zeros/nulls and is qualified separately; positive-price rows are reported to avoid treating every converted cell as useful.

The original export alone remains **2,502,566** rows. **435 original files** have unchanged sizes and mtimes against the acquisition baseline. Only legacy parquet footers were read for row counts; sealed observation rows were not loaded. Existing background legacy collectors continued adding new files independently, which explains any legacy-row increase beyond the original baseline.

## Source coverage

| Source/partition | Rows | IDs | First price timestamp UTC | Last price timestamp UTC | Non-null volume rows | First non-null volume UTC |
|---|---:|---:|---|---|---:|---|
| weirdgloop-all | 16,494,792 | 4,674 | 2015-02-27T00:00:00+00:00 | 2026-10-30T16:47:44+00:00 | 12,250,154 | 2018-02-19T00:00:00+00:00 |
| weirdgloop-archive-only | 6,691 | 15 | 2015-03-07T00:00:00+00:00 | 2024-02-14T10:22:11+00:00 | 4,012 | 2018-12-26T00:00:00+00:00 |
| weirdgloop-last90d | 1,358,437 | 4,577 | 2026-08-02T15:27:47+00:00 | 2026-10-30T20:03:35+00:00 | 1,358,139 | 2026-08-02T15:27:47+00:00 |
| kaggle-5m | 876,507,211 | 4,513 | 2021-03-08T07:35:00+00:00 | 2026-10-17T13:10:00+00:00 | 876,507,211 | 2021-03-08T07:35:00+00:00 |
| kaggle-5m-unclassified | 247,494 | 26 | 2021-03-08T07:35:00+00:00 | 2026-09-24T09:40:00+00:00 | 247,494 | 2021-03-08T07:35:00+00:00 |
| wiki-v2-5m | 7,174,028 | 4,497 | 2021-03-08T07:35:00+00:00 | 2026-10-30T21:40:00+00:00 | 7,174,028 | 2021-03-08T07:35:00+00:00 |
| wiki-v2-1h | 6,880,619 | 4,530 | 2021-03-08T07:00:00+00:00 | 2026-10-30T20:00:00+00:00 | 6,880,619 | 2021-03-08T07:00:00+00:00 |
| wiki-v2-timeseries-6h | 432 | 3 | 2026-10-30T11:15:00+00:00 | 2026-10-30T21:05:00+00:00 | 432 | 2026-10-30T11:15:00+00:00 |
| wiki-v2-timeseries-7d | 1,007 | 3 | 2026-10-23T17:00:00+00:00 | 2026-10-30T20:00:00+00:00 | 1,007 | 2026-10-23T17:00:00+00:00 |
| wiki-v2-latest | 9,048 | 4,524 | 2026-10-30T17:37:42+00:00 | 2026-10-30T18:39:30+00:00 | 0 | none |
| wiki-v2-latest-unclassified | 54 | 27 | 2026-10-30T17:37:42+00:00 | 2026-10-30T18:39:30+00:00 | 0 | none |
| kaggle-daily | 1,550,485 | 4,420 | 2021-03-08T00:00:00+00:00 | 2026-06-27T00:00:00+00:00 | 1,550,485 | 2021-03-08T00:00:00+00:00 |
| kaggle-bonds | 3,567 | 1 | 2015-03-28T00:00:00+00:00 | 2025-04-07T06:37:12+00:00 | 0 | none |
| academic-utk | 10,378,566 | 3,525 | 2020-02-03T04:47:01+00:00 | 2020-02-07T03:10:01+00:00 | 0 | none |
| wayback-wiki | 1,521 | 1 | 2015-03-27T00:00:00+00:00 | 2019-07-16T00:00:00+00:00 | 290 | 2018-09-25T00:00:00+00:00 |
| jagex-guide | 246,240 | 1,368 | 2026-05-04T00:00:00+00:00 | 2026-10-30T00:00:00+00:00 | 0 | none |
| seasonal-deadman_reborn | 1,816,933 | 2,799 | 2021-08-25T14:00:00+00:00 | 2021-09-16T20:55:00+00:00 | 1,816,933 | 2021-08-25T14:00:00+00:00 |
| seasonal-fsw_2022 | 4,611,444 | 2,932 | 2022-10-19T15:20:00+00:00 | 2023-04-18T10:55:00+00:00 | 4,611,444 | 2022-10-19T15:20:00+00:00 |
| seasonal-deadman_apocalypse | 2,321,831 | 3,251 | 2023-08-25T17:00:00+00:00 | 2023-09-16T17:00:00+00:00 | 2,321,831 | 2023-08-25T17:00:00+00:00 |
| seasonal-deadman_armageddon | 2,289,672 | 3,373 | 2024-07-19T16:10:00+00:00 | 2024-08-03T19:25:00+00:00 | 2,289,672 | 2024-07-19T16:10:00+00:00 |
| seasonal-deadman_annihilation | 3,998,094 | 3,789 | 2026-01-30T17:00:00+00:00 | 2026-02-28T17:55:00+00:00 | 3,998,094 | 2026-01-30T17:00:00+00:00 |

## Weird Gloop daily archive: annual volume coverage

| Year | Rows | Non-null volume rows | Coverage |
|---|---:|---:|---:|
| 2015 | 821,564 | 0 | 0.00% |
| 2016 | 1,047,097 | 0 | 0.00% |
| 2017 | 1,140,823 | 0 | 0.00% |
| 2018 | 1,218,140 | 170,364 | 13.99% |
| 2019 | 1,304,524 | 1,279,934 | 98.12% |
| 2020 | 1,364,216 | 1,355,607 | 99.37% |
| 2021 | 1,404,285 | 1,268,677 | 90.34% |
| 2022 | 1,425,451 | 1,408,471 | 98.81% |
| 2023 | 1,393,596 | 1,393,244 | 99.97% |
| 2024 | 1,490,336 | 1,489,975 | 99.98% |
| 2025 | 1,566,596 | 1,566,231 | 99.98% |
| 2026 | 2,318,164 | 2,317,651 | 99.98% |

The earliest non-null volume, **2018-02-19**, is not a universal availability date. For steel cannonballs (2) and the whip (4151), it begins **2018-09-25**; for nature runes (561), **2018-02-19**. Many items begin only in December 2018 or when they are introduced later. Nulls continue after these dates. The rolling source also has an exception: **all 298 bond (13190) rows lack volume**; 1,358,139 of its 1,358,437 rows have non-null volume. Ninety-seven requested IDs returned no rolling observations. The per-item files beside `coverage.json` retain first non-null volume dates, volume-row counts and last null dates. Daily guide history is mostly daily, but includes irregular recent observations; the row total is not asserted to be a strictly regular daily panel.

## Five-minute bucket coverage and completion gates

The acquired mirror contains **587,194 distinct nonempty five-minute timestamps** across a 590,180-bucket grid. Every one of its 2,986 holes was requested from Wiki v2: **162 yielded 224,474 rows**, and **2,824 remained empty**. The direct archive also fills the post-mirror tail and stores empty responses honestly. An additional empty bucket exists in that tail on 2026-10-27 at 09:10 UTC.

Actual completion-gate output (assertions fail with a nonzero process exit):

```text
{
  "checked_at": "2026-10-30T21:47:46.593452+00:00",
  "weirdgloop-all": {
    "identifiers_completed": 4674,
    "rows": 16494792,
    "empty_identifiers": 0,
    "errors": 0,
    "partition_checksums_verified": true
  },
  "weirdgloop-last90d": {
    "identifiers_completed": 4674,
    "rows": 1358437,
    "empty_identifiers": 97,
    "errors": 0,
    "partition_checksums_verified": true
  },
  "jagex-guide": {
    "identifiers_checked": 4674,
    "statuses": {
      "complete": 1368,
      "empty": 3268,
      "missing": 38
    },
    "daily_rows": 246240
  },
  "wiki-hourly-window": {
    "start": 1785542400,
    "end_exclusive": 1793394000,
    "requested_buckets": 2181,
    "completed_buckets": 2181,
    "partition_checksums_verified": true
  },
  "mirror-repair": {
    "requested": 2986,
    "completed": 2986,
    "nonempty": 162,
    "still_empty": 2824,
    "recovered_rows": 224474
  },
  "five-minute-coverage": {
    "mirror_nonempty_buckets": 587194,
    "direct_nonempty_buckets": 4013,
    "direct_empty_buckets": 2826,
    "nonoverlapping_direct_buckets": 4007,
    "union_nonempty_buckets": 591201,
    "first_ts": 1615188900,
    "last_ts": 1793396400,
    "missing_grid_buckets": 2825
  },
  "unchanged_original_files": 435
}
```

The union bucket count is an inventory fact, not a claim that every mirrored historical timestamp was re-requested from today's live API. Direct retrieval counts and the mirror count are shown separately. No prices were interpolated. The measured first nonempty live API boundaries are **2021-03-08 07:35 UTC** (5m) and **07:00 UTC** (1h); nearby earlier buckets and probes in 2013, 2015, 2018 and 2020 were empty. Older hourly buckets remain accessible in probes but were not exhaustively acquired; the recent August–October 2026 hourly window is verified by completion gates.

## Actual source proof

The report command read the completed canonical parquet partitions and emitted the following counts and records. `source-proof.txt` in the verification directory contains this same compact output. Feature tables have snapshot/revision dates rather than a market time axis; their sample records retain those dates where present.

```text
weirdgloop-all: rows=16494792 items=4674 min=2015-02-27T00:00:00+00:00 max=2026-10-30T16:47:44+00:00
sample={"avg_high_price": null, "avg_low_price": null, "economy": "main", "high_price_volume": null, "item_id": 10, "low_price_volume": null, "mid_price": 174710.0, "name": "Cannon barrels", "total_volume": null, "ts": 1427500800}
weirdgloop-archive-only: rows=6691 items=15 min=2015-03-07T00:00:00+00:00 max=2024-02-14T10:22:11+00:00
sample={"avg_high_price": null, "avg_low_price": null, "economy": "unclassified_legacy", "high_price_volume": null, "item_id": 26247, "low_price_volume": null, "mid_price": 1.0, "name": "Pumpkin pie", "total_volume": null, "ts": 1634684400}
weirdgloop-last90d: rows=1358437 items=4577 min=2026-08-02T15:27:47+00:00 max=2026-10-30T20:03:35+00:00
sample={"avg_high_price": null, "avg_low_price": null, "economy": "main", "high_price_volume": null, "item_id": 10, "low_price_volume": null, "mid_price": 167723.0, "name": "Cannon barrels", "total_volume": 532, "ts": 1785684467}
kaggle-5m: rows=876507211 items=4513 min=2021-03-08T07:35:00+00:00 max=2026-10-17T13:10:00+00:00
sample={"avg_high_price": 161.0, "avg_low_price": 159.0, "economy": "main", "high_price_volume": 50300, "item_id": 2, "low_price_volume": 394, "mid_price": 160.0, "name": "Steel cannonball", "total_volume": 50694, "ts": 1615188900}
kaggle-5m-unclassified: rows=247494 items=26 min=2021-03-08T07:35:00+00:00 max=2026-09-24T09:40:00+00:00
sample={"avg_high_price": 2148000.0, "avg_low_price": null, "economy": "unclassified_legacy", "high_price_volume": 2, "item_id": 9044, "low_price_volume": 0, "mid_price": null, "name": null, "total_volume": 2, "ts": 1615188900}
wiki-v2-5m: rows=7174028 items=4497 min=2021-03-08T07:35:00+00:00 max=2026-10-30T21:40:00+00:00
sample={"avg_high_price": 161.0, "avg_low_price": 159.0, "economy": "main", "high_price_volume": 50300, "item_id": 2, "low_price_volume": 394, "mid_price": 160.0, "name": "Steel cannonball", "total_volume": 50694, "ts": 1615188900}
wiki-v2-1h: rows=6880619 items=4530 min=2021-03-08T07:00:00+00:00 max=2026-10-30T20:00:00+00:00
sample={"avg_high_price": 161.0, "avg_low_price": 158.0, "economy": "main", "high_price_volume": 412231, "item_id": 2, "low_price_volume": 95906, "mid_price": 159.5, "name": "Steel cannonball", "total_volume": 508137, "ts": 1615186800}
wiki-v2-timeseries-6h: rows=432 items=3 min=2026-10-30T11:15:00+00:00 max=2026-10-30T21:05:00+00:00
sample={"avg_high_price": 204.89, "avg_low_price": 199.79, "economy": "main", "high_price_volume": 31354, "item_id": 2, "low_price_volume": 34055, "mid_price": 202.33999999999997, "name": "Steel cannonball", "total_volume": 65409, "ts": 1793358900}
wiki-v2-timeseries-7d: rows=1007 items=3 min=2026-10-23T17:00:00+00:00 max=2026-10-30T20:00:00+00:00
sample={"avg_high_price": 204.91, "avg_low_price": 199.85, "economy": "main", "high_price_volume": 967728, "item_id": 2, "low_price_volume": 615998, "mid_price": 202.38, "name": "Steel cannonball", "total_volume": 1583726, "ts": 1792774800}
wiki-v2-latest: rows=9048 items=4524 min=2026-10-30T17:37:42+00:00 max=2026-10-30T18:39:30+00:00
sample={"avg_high_price": 207.0, "avg_low_price": 193.0, "economy": "main", "high_price_volume": null, "item_id": 2, "low_price_volume": null, "mid_price": 200.0, "name": "Steel cannonball", "total_volume": null, "ts": 1793381862}
wiki-v2-latest-unclassified: rows=54 items=27 min=2026-10-30T17:37:42+00:00 max=2026-10-30T18:39:30+00:00
sample={"avg_high_price": 50000.0, "avg_low_price": null, "economy": "unclassified_legacy", "high_price_volume": null, "item_id": 2660, "low_price_volume": null, "mid_price": null, "name": null, "total_volume": null, "ts": 1793381862}
kaggle-daily: rows=1550485 items=4420 min=2021-03-08T00:00:00+00:00 max=2026-06-27T00:00:00+00:00
sample={"avg_high_price": 1337.0, "avg_low_price": 1129.0, "economy": "main", "high_price_volume": 342, "item_id": 21512, "low_price_volume": 213, "mid_price": 1233.0, "name": "Bird house", "total_volume": 555, "ts": 1762387200}
kaggle-bonds: rows=3567 items=1 min=2015-03-28T00:00:00+00:00 max=2025-04-07T06:37:12+00:00
sample={"avg_high_price": null, "avg_low_price": null, "economy": "main", "high_price_volume": null, "item_id": 13190, "low_price_volume": null, "mid_price": 2000000.0, "name": "Old school bond", "total_volume": null, "ts": 1427500800}
academic-utk: rows=10378566 items=3525 min=2020-02-03T04:47:01+00:00 max=2020-02-07T03:10:01+00:00
sample={"avg_high_price": null, "avg_low_price": null, "economy": "osrs_unspecified", "high_price_volume": null, "item_id": 23336, "low_price_volume": null, "mid_price": 0.0, "name": "3rd age druidic robe top", "total_volume": null, "ts": 1581040801}
wayback-wiki: rows=1521 items=1 min=2015-03-27T00:00:00+00:00 max=2019-07-16T00:00:00+00:00
sample={"avg_high_price": null, "avg_low_price": null, "economy": "main", "high_price_volume": null, "item_id": 4151, "low_price_volume": null, "mid_price": 2040584.0, "name": "Abyssal whip", "total_volume": null, "ts": 1427414400}
jagex-guide: rows=246240 items=1368 min=2026-05-04T00:00:00+00:00 max=2026-10-30T00:00:00+00:00
sample={"avg_high_price": null, "avg_low_price": null, "economy": "main", "high_price_volume": null, "item_id": 10, "low_price_volume": null, "mid_price": 164347.0, "name": "Cannon barrels", "total_volume": null, "ts": 1777852800}
seasonal-deadman_reborn: rows=1816933 items=2799 min=2021-08-25T14:00:00+00:00 max=2021-09-16T20:55:00+00:00
sample={"avg_high_price": 200000.0, "avg_low_price": null, "economy": "deadman_reborn", "high_price_volume": 1, "item_id": 10344, "low_price_volume": 0, "mid_price": null, "name": "3rd Age amulet", "total_volume": 1, "ts": 1631710500}
seasonal-fsw_2022: rows=4611444 items=2932 min=2022-10-19T15:20:00+00:00 max=2023-04-18T10:55:00+00:00
sample={"avg_high_price": null, "avg_low_price": 600000000.0, "economy": "fsw_2022", "high_price_volume": 0, "item_id": 12424, "low_price_volume": 1, "mid_price": null, "name": "3rd Age bow", "total_volume": 1, "ts": 1678824300}
seasonal-deadman_apocalypse: rows=2321831 items=3251 min=2023-08-25T17:00:00+00:00 max=2023-09-16T17:00:00+00:00
sample={"avg_high_price": 19155067.0, "avg_low_price": null, "economy": "deadman_apocalypse", "high_price_volume": 1, "item_id": 10344, "low_price_volume": 0, "mid_price": null, "name": "3rd Age amulet", "total_volume": 1, "ts": 1694218800}
seasonal-deadman_armageddon: rows=2289672 items=3373 min=2024-07-19T16:10:00+00:00 max=2024-08-03T19:25:00+00:00
sample={"avg_high_price": 10000000.0, "avg_low_price": null, "economy": "deadman_armageddon", "high_price_volume": 1, "item_id": 10344, "low_price_volume": 0, "mid_price": null, "name": "3rd Age amulet", "total_volume": 1, "ts": 1722447900}
seasonal-deadman_annihilation: rows=3998094 items=3789 min=2026-01-30T17:00:00+00:00 max=2026-02-28T17:55:00+00:00
sample={"avg_high_price": 54376087.0, "avg_low_price": null, "economy": "deadman_annihilation", "high_price_volume": 1, "item_id": 10344, "low_price_volume": 0, "mid_price": null, "name": "3rd Age amulet", "total_volume": 1, "ts": 1771580100}
wiki-mapping: feature_rows=4674 (snapshot/definitions; not a market time series)
sample={"examine": "Fabulously ancient mage protection enchanted in the 3rd Age.", "highalch": 30300, "icon": "3rd Age amulet.png", "id": 10344, "limit": 8, "lowalch": 20200, "members": true, "name": "3rd Age amulet", "value": 50500}
wiki-items: feature_rows=4665 (snapshot/definitions; not a market time series)
sample={"item_id": null, "page_id": 51894, "price": null, "price_date_literal": null, "revision_id": 15342489, "revision_ts": 1789274728, "title": "3rd Age amulet", "volume": null, "volume_date_literal": null}
wiki-modules: feature_rows=4674 (snapshot/definitions; not a market time series)
sample={"item_id": 10344, "page_id": 60166, "price": null, "price_date_literal": null, "revision_id": 15308952, "revision_ts": 1787167892, "title": "Module:Exchange/3rd Age amulet", "volume": null, "volume_date_literal": null}
wiki-monsters: feature_rows=1661 (snapshot/definitions; not a market time series)
sample={"item_id": null, "page_id": 27806, "price": null, "price_date_literal": null, "revision_id": 15199544, "revision_ts": 1777360873, "title": "A Doubt", "volume": null, "volume_date_literal": null}
wiki-shops: feature_rows=508 (snapshot/definitions; not a market time series)
sample={"item_id": null, "page_id": 29644, "price": null, "price_date_literal": null, "revision_id": 15359514, "revision_ts": 1790854778, "title": "Aaron's Archery Appendages.", "volume": null, "volume_date_literal": null}
wiki-special: feature_rows=5 (snapshot/definitions; not a market time series)
sample={"item_id": null, "page_id": 17287, "price": null, "price_date_literal": null, "revision_id": 15373641, "revision_ts": 1792116163, "title": "Grand Exchange", "volume": null, "volume_date_literal": null}
mediawiki-revisions: feature_rows=83 (snapshot/definitions; not a market time series)
sample={"item_id": 2, "page_id": 55498, "price": 229.0, "price_date_literal": "'00:20, September 1, 2015 (UTC)'", "revision_id": 318671, "revision_ts": 1441066800, "title": "Module:Exchange/Steel cannonball", "volume": null, "volume_date_literal": null}
official-activity: feature_rows=11840 (snapshot/definitions; not a market time series)
sample={"activity": "750 skill total", "location": "United States", "membership": "Free", "players": 69, "population_literal": "69 players", "ts": 1793381338, "world_id": 393}
jagex-moving-average: feature_rows=246240 (snapshot/definitions; not a market time series)
sample={"avg_high_price": null, "avg_low_price": null, "economy": "main", "high_price_volume": null, "item_id": 10, "low_price_volume": null, "mid_price": 165869.0, "name": "Cannon barrels", "source": "jagex-guide", "total_volume": null, "ts": 1777852800}
kaggle-alch: feature_rows=4246 (snapshot/definitions; not a market time series)
sample={"buy_limit": 8, "highalch": 30300, "item_id": 10344, "lowalch": 20200, "name": "3rd age amulet", "value": 50500}
kaggle-polls: feature_rows=1794 (snapshot/definitions; not a market time series)
sample={"peak_players_unverified": 63108.0, "poll_date_ts": 1363219200, "question": "The Easter 2007 event is re-activated for Easter this year.", "question_index": 0, "title": "Old School feature poll #1 \u2013 March 2013", "total_votes": 101407}
wiki-feature-facts: feature_rows=181600 (snapshot/definitions; not a market time series)
sample={"field": "name", "literal": "3rd Age amulet", "numeric_literal": null, "page_item_id": 10344, "revision_id": 15342489, "revision_ts": 1789274728, "template": "Infobox Item", "template_offset": 33, "title": "3rd Age amulet"}
osrsbox-items: feature_rows=24735 (snapshot/definitions; not a market time series)
sample={"buy_limit": null, "cost": 1, "equipment_json": "null", "highalch": 0, "item_id": 0, "last_updated": "2021-09-24", "lowalch": 0, "name": "Dwarf remains", "weapon_json": "null", "weight": 16.0}
osrsbox-monsters: feature_rows=3000 (snapshot/definitions; not a market time series)
sample={"last_updated": "2021-09-02", "monster_id": 1, "name": "Molanisk"}
osrsbox-drops: feature_rows=73089 (snapshot/definitions; not a market time series)
sample={"item_id": 1623, "monster_id": 1, "name": "Uncut sapphire", "quantity": "1", "rarity": 0.013671875, "rolls": 1.0}
osrsreboxed-items: feature_rows=28744 (snapshot/definitions; not a market time series)
sample={"buy_limit": null, "cost": 1, "equipment_json": "null", "highalch": 0, "item_id": 0, "last_updated": "2023-10-15", "lowalch": 0, "name": "Dwarf remains", "weapon_json": "null", "weight": 16.0}
osrsreboxed-monsters: feature_rows=1192 (snapshot/definitions; not a market time series)
sample={"last_updated": "2024-05-11", "monster_id": 1, "name": "Molanisk"}
osrsreboxed-drops: feature_rows=37762 (snapshot/definitions; not a market time series)
sample={"item_id": 1623, "monster_id": 1, "name": "Uncut sapphire", "quantity": "1", "rarity": 0.013671875, "rolls": 1.0}
```

## Storage

Actual `du -sh` output for every acquisition directory, including host-lock metadata:

```text
56M	/home/martin/osrs-data/sources/academic-utk
4.0K	/home/martin/osrs-data/sources/coverage-20261030T180317777450Z
280K	/home/martin/osrs-data/sources/coverage-20261030T180416642963Z
724K	/home/martin/osrs-data/sources/coverage-20261030T183046130957Z
4.1M	/home/martin/osrs-data/sources/coverage-20261030T210707637118Z
6.2M	/home/martin/osrs-data/sources/coverage-20261030T214757409995Z
284K	/home/martin/osrs-data/sources/discovery-2110
5.2G	/home/martin/osrs-data/sources/evidence
38M	/home/martin/osrs-data/sources/jagex-guide
33G	/home/martin/osrs-data/sources/kaggle-5m
712K	/home/martin/osrs-data/sources/kaggle-features
326M	/home/martin/osrs-data/sources/kaggle-other
16K	/home/martin/osrs-data/sources/legacy-osbuddy
52K	/home/martin/osrs-data/sources/mediawiki-revisions
480K	/home/martin/osrs-data/sources/official-activity
14M	/home/martin/osrs-data/sources/osrsbox
16M	/home/martin/osrs-data/sources/osrsreboxed
773M	/home/martin/osrs-data/sources/seasonal-dumps
708K	/home/martin/osrs-data/sources/terms
12K	/home/martin/osrs-data/sources/verification
136K	/home/martin/osrs-data/sources/verification-2106
88K	/home/martin/osrs-data/sources/verification-complete-20261030
212K	/home/martin/osrs-data/sources/wayback
316M	/home/martin/osrs-data/sources/weirdgloop-all
68M	/home/martin/osrs-data/sources/weirdgloop-last90d
3.6M	/home/martin/osrs-data/sources/wiki-feature-facts
12M	/home/martin/osrs-data/sources/wiki-pages
639M	/home/martin/osrs-data/sources/wiki-v2
```

Separate `du -sh /home/martin/osrs-data/sources`:

```text
40G	/home/martin/osrs-data/sources
```

Storage includes immutable raw downloads, extracted data, HTTP attempts, both preserved conversion versions, manifests and reports. It is not just the size of the qualified canonical rows.

## Rate and identity audit

The actual-attempt audit counted **23,904 requests** across the acquisition evidence. Its cutoff gate verified the exact requested UA for every request after 2026-10-30 21:04 UTC. Four older probes used a different descriptive UA; that evidence was preserved, not rewritten.

| Host | Requests | Actual statuses | Minimum recorded start gap (s) |
|---|---:|---|---:|
| api.crossref.org | 1 | `{"200": 1}` | not recorded |
| api.github.com | 33 | `{"200": 32, "404": 1}` | 1.0500869750976562 |
| api.rsbuddy.com | 4 | `{"0": 4}` | not recorded |
| api.weirdgloop.org | 9387 | `{"0": 4, "200": 9383}` | 1.0500380992889404 |
| huggingface.co | 1 | `{"200": 1}` | not recorded |
| legal.jagex.com | 5 | `{"200": 5}` | not recorded |
| meta.weirdgloop.org | 1 | `{"200": 1}` | not recorded |
| oldschool.runescape.com | 43 | `{"200": 42, "404": 1}` | 272.54810905456543 |
| oldschool.runescape.wiki | 502 | `{"200": 502}` | 1.0500891208648682 |
| osbuddy.com | 1 | `{"200": 1}` | not recorded |
| prices.runescape.wiki | 9169 | `{"0": 6, "200": 9163}` | 1.050037145614624 |
| raw.githubusercontent.com | 19 | `{"200": 19}` | 1.0501019954681396 |
| rsbuddy.com | 2 | `{"302": 2}` | not recorded |
| secure.runescape.com | 4677 | `{"0": 2, "200": 4637, "404": 38}` | 1.0500459671020508 |
| static.runelite.net | 2 | `{"404": 2}` | not recorded |
| storage.googleapis.com | 6 | `{"200": 6}` | 1.418546199798584 |
| web.archive.org | 11 | `{"200": 11}` | 1.0500891208648682 |
| www.ge-tracker.com | 1 | `{"200": 1}` | not recorded |
| www.google.com | 1 | `{"200": 1}` | not recorded |
| www.jagex.com | 4 | `{"308": 4}` | not recorded |
| www.kaggle.com | 28 | `{"200": 22, "302": 6}` | 1.0500798225402832 |
| www.misplaceditems.com | 2 | `{"200": 2}` | 1.0501041412353516 |
| www.runescape.com | 3 | `{"302": 2, "404": 1}` | not recorded |
| zenodo.org | 1 | `{"200": 1}` | not recorded |

Actual policy: **one in-flight request per host, minimum 1.05 seconds between starts**; independent hosts may proceed concurrently. Start timestamps are unavailable in some older records, so their spacing cannot be proven retrospectively. No HTTP 429 or 5xx was observed in this audit. Transport errors and DNS failures are recorded as status 0; retries use bounded exponential backoff with jitter. `Retry-After` is honored. GitHub advertised **60 core requests** in its unauthenticated quota headers; quota headers/reset times are retained in the audit, and no exhaustion experiment was performed. No numerical provider limit was discovered for Wiki or Weird Gloop. This does not authorize faster requests.

## Tests

`cd ml && uv run --frozen pytest -q` (exit 0):

```text
........................................................................ [ 20%]
........................................................................ [ 40%]
........................................................................ [ 60%]
........................................................................ [ 80%]
.....................................................................    [100%]
=============================== warnings summary ===============================
.venv/lib/python3.13/site-packages/fastapi/testclient.py:1
  /home/martin/src/osrs-market/ml/.venv/lib/python3.13/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
357 passed, 1 warning in 38.87s
```

`cd tui && PATH="$HOME/.cargo/bin:$PATH" cargo test --release` (exit 0; same cargo binary used by absolute path in this run):

```text
    Finished `release` profile [optimized] target(s) in 0.53s
     Running unittests src/main.rs (target/release/deps/osrs_term-94fbfe78af6cbdc9)

running 31 tests
test chat::billing_tests::subscription_never_formats_dollars_and_marks_unavailable ... ok
test chat::workdir_tests::workdir_palette_command_routes_and_cannot_change_a_running_conversation ... ok
test chat::conversation_tests::new_conversations_reset_writes_and_explicit_target_always_starts_fresh ... ok
test chat::tests::editing_preserves_unicode_and_multiline ... ok
test chat::input_tests::input_sends_multiline_argv_text_and_stays_cancellable ... ok
test interaction::app_tests::drag_and_border_presses_do_not_select ... ok
test interaction::app_tests::single_click_retargets_without_duplicates_and_double_preserves_existing ... ok
test interaction::tests::filtered_scrolled_and_sorted_rows_use_the_painted_order ... ok
test interaction::link_click_tests::linked_chart_selection_and_comparison_cap ... ok
test interaction::app_tests::every_item_table_maps_exact_painted_rows ... ok
test interaction::tests::header_border_and_empty_area ... ok
test interaction::tests::press_drag_release_never_selects_even_after_returning ... ok
test search::tests::full_catalogue_latency ... ok
test search::tests::filters_are_closed_and_missing_fails ... ok
test search::tests::pins_recents_and_blending ... ok
test terminal::tests::close_undo_restores_exact_window_and_link_configuration ... ok
test search::tests::queries_and_unicode ... ok
test terminal::tests::linked_tickers_propagate_without_changing_unlinked_windows_or_studies ... ok
test window::chart_tests::hover_clamps_to_bucket ... ok
test window::resize_tests::all_eight_handles_and_corner_priority ... ok
test window::edge_tests::snap_and_resize_edges ... ok
test terminal::tests::chart_panes_and_help_render_on_tiny_and_full_terminals ... ok
test window::resize_tests::each_edge_anchors_opposite_edge_and_clamps_minimum ... ok
test window::resize_tests::terminal_edges_offscreen_and_tiny_terminal ... ok
test window::tests::fuzzy_subsequence ... ok
test window::tests::drag_clamps_all_edges ... ok
test window::tests::hit_regions ... ok
test window::tests::overlapping_z_order ... ok
test window::tests::resizing_and_tiny_terminal ... ok
test window::workspace_tests::launch_and_clear_restore_exact_windows ... ok
test drag::tests::cached_drag_matches_full_redraw_across_overlap ... ok

test result: ok. 31 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s

```

## What remains unavailable

- No verified, broad main-economy bid/ask and volume history before **2021-03-08**. The short February 2020 academic capture has unresolved methodology, zeros and names; it does not close that gap.
- No volume before **2018-02-19** in Weird Gloop daily history, and considerable item-specific missingness thereafter. Official guide graphs, latest side trades, the academic capture and bond mirror do not supply volume.
- No recovered pre-2015 daily market series. The inspected 2013 Wayback page contains metadata; the GE did not launch until February 2015. Module revisions are sparse snapshots from September 2015 in the tested items and are not an independent daily source.
- No complete realized monster supply, item-sink removal-count series or official historical activity series. Drops/shops are definitions; world counts are forward observations, including special economies. The polling workbook's historical player estimates are third-party and unverified.
- Defunct RSBuddy/OSBuddy and guessed static endpoints, missing API titles, unrelated RS3 datasets and repositories publishing only collector code contribute no new price rows. New GE Tracker scraping is disallowed by its published terms. Exact evidence and verdicts are in [the source matrix](data-sources.md).

Research acquisition is wired for Weird Gloop daily/rolling history, Wiki v2 bulk/timeseries/latest, the public mirrors, isolated seasonal markets, official guide graphs, feature archives and forward world populations. Nothing was connected to the shipped server or evaluation pipeline. The single highest-value remaining gap is **verified main-economy bid/ask and volume observations before March 2021**.
