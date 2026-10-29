# Private deep-history and participation validation

**The full sweep and frozen cross-era experiment are complete.** Time-invariant
reversal rules and the earlier-only ridge fit survive the predeclared **price**
screen across all seven test eras. An executable one-account edge remains
unidentified: the existing daily replay's conditional break-even grid interval is
**[0.1%, infinity]**, and weekly averages cannot identify fills for the new rules.
Recommend stopping deployment/expansion of the present daily strategy, while
retaining the demonstrated source-price reversal finding as a research result.

The artificial two-second delay was removed. Eight-worker collection actually
encountered HTTP 429; headers reported `X-RateLimit-Limit: 200`, remaining zero,
`Retry-After: 275` and reset timestamps, with successive windows approximately
five minutes apart. Server-directed backoff dominated the roughly 103-minute
concurrent sweep. This is measured operational throttling, not a ToS restriction.
All 4,586 frozen catalogue identifiers were attempted: **4,536 histories and 50
HTTP 200 provider failures**. The latter remain unavailable under the instruction
to retry only 403/429/5xx or connection errors; they are not empty histories.
Successful cache records were retained through live restarts. Full responses and
every derived artifact remain under `/home/martin/osrs-data`, outside Git.

## Headline: break-even participation uncertainty

**The attainable continuous break-even participation is unidentified.** The frozen
model has no observed mean-proxy participation sample profitable in all three
folds. Its conditional first-positive-grid statistic has the extended-real
**95% interval [0.1%, infinity]**, under every cost preset and both block lengths.
Infinity means *no profitable sample on the frozen 0.1%–100% grid*, not a requirement
to capture more than 100% and not a claim about unsampled participation islands.
This is not a calibrated confidence interval for an executable account threshold.

Executed reproduction: the complete 810-scenario `participation-bounds-v3-cached`
experiment, corrected `integer_lots_v2` pricing and `volume_bounded_v3` execution,
three saved development folds, all five frozen score sets, all three cost presets,
both qualification rules and all nine shares. No fit, tuning or holdout access.
Paired circular empirical blocks of **observed daily marked-equity increments**,
2,000 draws, seed 42 (+ fold), preserve comparisons between shares. The original
buy-and-sale activity gate is retained. These intervals condition on the observed
equity paths and terminal marks; they do not rerun accounts or identify queue share,
execution uncertainty, historical limits or liquidation value.

| CatBoost qualification / preset | 7-day CI | No positive grid sample, 7-day | 14-day CI | No positive grid sample, 14-day |
| --- | --- | --- | --- | --- |
| mean_proxy / optimistic | [0.1%, infinity] | 79.00% | [0.1%, infinity] | 80.75% |
| mean_proxy / moderate | [0.1%, infinity] | 80.05% | [0.1%, infinity] | 82.70% |
| mean_proxy / conservative | [0.1%, infinity] | 80.10% | [0.1%, infinity] | 84.35% |
| moment_upper / optimistic | [0.1%, infinity] | 10.15% | [0.1%, infinity] | 7.40% |
| moment_upper / moderate | [0.1%, infinity] | 10.85% | [0.1%, infinity] | 8.00% |
| moment_upper / conservative | [0.1%, infinity] | 12.25% | [0.1%, infinity] | 9.05% |

The moment envelope requires favorable unobserved price allocation in addition to
queue allocation. Even that ceiling does not produce a finite upper confidence
bound. The observed all-fold first positive sample for that ceiling is 50%; for
mean_proxy it is absent. Profit is nonmonotone on the grid; no interpolation or
additional participation search was performed.

At the 1% planning case, moderate mean-proxy CatBoost has these actual outputs:

```text
block_days fold net_gp lower_gp upper_gp
7          0      -151    -8445     8395
7          1    -24476  -118077    54524
7          2    -56513  -252622   113230
14         0      -151    -5139     4824
14         1    -24476   -82393    32964
14         2    -56513  -219949   106053
```

No mean-proxy CatBoost tested share has a positive lower 95% profit bound, in any
fold or preset, at either block length. Broad intervals crossing zero indicate
insufficient positive evidence; they do not establish statistically certain losses.
No-trade and inactive no-change remain exactly zero. All baseline outputs were
retained, without choosing a winner from this analysis.

## What the full weekly archive bought

**1,869,751 raw weekly records; 1,803,631 development records**, from
**2017-03-02 through 2026-07-16** in the sealed panel. Raw date-only coverage
extends through 2026-10-29; the maximum span is **9.659 years**, approximately
9.7 years. No later market fields entered these analyses. There are **4,451 items
with development rows**, 85 histories entirely outside the development boundary,
and the 50 unavailable provider responses. Each stored observation retains its
source URL, fetch timestamp, source/schema version and provider metadata.

History **span** includes gaps. Observed-week equivalents count real rows divided
by 365.25/7; they do not fill gaps or claim uninterrupted coverage.

| Span in years | Raw-date items | Development items |
| --- | ---: | ---: |
| <1 | 345 | 299 |
| 1–<2 | 104 | 112 |
| 2–<3 | 187 | 161 |
| 3–<4 | 59 | 55 |
| 4–<5 | 76 | 59 |
| 5–<6 | 67 | 78 |
| 6–<7 | 65 | 112 |
| 7–<8 | 188 | 144 |
| 8–<9 | 144 | 165 |
| 9–<10 | 3,301 | 3,266 |
| Zero rows / unavailable | 50 | 135 |

Among nine-year raw spans, median observed length is **505 weeks**; for
nine-year development spans it is **490 weeks**. Only **3,024 raw histories** and
**2,914 development histories** actually contain nine observed-week year
equivalents. First observations are in 2017 for 3,325 items, 2018 for 122, 2019
for 195, 2020 for 65, 2021 for 87, 2022 for 50, 2023 for 99, 2024 for 159,
2025 for 283 and 2026 for 151; 85 of the last group have no development rows.

Early years are broad, although less complete than recent years. A usable row
has positive overall/side prices and positive completed volume on both sides:

| Year | Weeks | Items with usable rows | Usable rows | Median usable items/week | Usable current-universe cells |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2017 | 44 | 3,301 | 135,432 | 3,082.5 | 67.12% |
| 2018 | 52 | 3,429 | 165,376 | 3,183.5 | 69.35% |
| 2019 | 52 | 3,612 | 168,125 | 3,244.0 | 70.50% |
| 2020 | 53 | 3,648 | 165,060 | 3,142.0 | 67.91% |
| 2021 | 52 | 3,789 | 181,357 | 3,606.0 | 76.05% |
| 2022 | 52 | 3,826 | 186,930 | 3,596.5 | 78.39% |
| 2023 | 52 | 3,880 | 189,527 | 3,646.0 | 79.48% |
| 2024 | 52 | 3,990 | 195,331 | 3,760.5 | 81.91% |
| 2025 | 52 | 4,155 | 198,247 | 3,797.5 | 83.13% |
| 2026, development | 29 | 4,019 | 109,833 | 3,800.0 | 82.58% |

The denominator is today's **4,586 listed identifiers**, including later releases
and unavailable items. These percentages do not estimate coverage of the
then-existing market. Delisted items remain unidentified. The first and final
years are partial. Thus the archive buys thousands of items per early week, not
nine complete years for every current item.

## Which date-invariant rules survived

The fixed six-feature ridge fit uses train-only medians/scaling, penalty 1 and
within-week ranked labels. Initial fitting uses 2017–2019, followed by expanding
earlier-only fits for **2020, 2021, 2022, 2023, 2024, 2025 and development 2026**.
All **14 fits** have training labels strictly before test start and test labels
strictly before the next era/holdout boundary. Calendar, weekday, regime, event,
item identity and history-length features never enter this fit. Translation of
dates leaves features and fitted predictions unchanged in the mechanics test.

Each horizon/rule must have positive lower 95% bounds on weekly Spearman
correlation **and** after-tax top-decile-minus-universe return in every era, using
both four- and eight-week blocks. Every test era is adequate: 29–52 weeks at the
one-week horizon and 26–49 at the four-week horizon. All 980 metric/block
intervals have complete weekly inputs, without empty resamples.

| Predeclared rule | One-week horizon | Four-week horizon |
| --- | --- | --- |
| One-week momentum | Fail | Fail |
| Four-week momentum | Fail | Fail |
| One-week reversal | Pass | Pass |
| Four-week reversal | Pass | Pass |
| Earlier-only ridge | Pass | Pass |
| Spread ranking | Fail | Fail |
| Volume ranking | Fail | Fail |

These are **source-price diagnostic passes**, not account profit passes. The
smallest rank-correlation lower bound across all eras and both block lengths is:

| Rule | One-week horizon | Four-week horizon |
| --- | ---: | ---: |
| One-week reversal | 0.081449 | 0.128410 |
| Four-week reversal | 0.136692 | 0.159141 |
| Ridge | 0.058624 | 0.081279 |

Ridge's actual annual mean correlations are **0.0752–0.0890** at one week and
**0.1058–0.1295** at four weeks. For example, its weakest eight-week-block bounds
are **[0.058624, 0.090182]** (one-week horizon, 2021) and
**[0.081279, 0.134660]** (four-week horizon, 2021). Four-week reversal's annual
mean correlations range **0.1690–0.2290** at the one-week horizon and
**0.2147–0.2948** at the four-week horizon. No rule or horizon was selected for
trading, and none of the failed rules was rescued with a favorable sub-period.

Descriptive rankings also have temporal persistence: 2017-to-development-2026
median-volume Spearman correlation is **0.926597** on **2,935 common items**;
spread ranking is **0.584840**, and counterfactual tax-adjusted margin ranking is
**0.619165**, on the same count. Median one/four-week-return item rankings across
those eras are much less persistent: **0.013941 / 0.018900**, on 2,929 / 2,927
common items. Predictive reversal and persistent long-run item winners are
different claims; the archive supports the former diagnostic, not the latter.

## Fat tails, granularity and source consistency

D'Agostino–Pearson rejects normality for **4,157/4,338 tested log-return series**
and **4,309/4,373 tested signed-spread series**. All six liquidity-band tests
reject; train-only volume tercile boundaries are 844 and 17,180.67 units. Pooled
band intervals preserve whole weeks and use empirical blocks regardless.

Of 8,902 item/metric series, only **32 return series and three spread series**
meet the normality, n>=30 and absolute lag-one <=0.1 requirements for Gaussian
mean t intervals. **8,676 series** use four/eight-week empirical blocks, and
**191** are insufficient or constant. Non-rejection is not proof of normality.
All cross-era performance and all financial/participation intervals use empirical
blocks; no Gaussian sample enters training or profit calculations.

A post-run audit identified **481 per-item/block cases** with empty bootstrap
samples. Those per-item intervals condition on nonempty draws; unconditional
mean intervals for those cases are unidentified. Maximum missing mass is
55/2,000 (2.75%). This limitation does not affect any of the 980 complete-input
annual intervals or the complete-input daily participation intervals. The
item-level flags remain external in `deep-history-audit-v1`.

The arithmetic return magnitudes are especially unsuitable as profit estimates:

* **262,701/1,695,218 usable rows (15.50%)** have `overallPrice` outside the two
  side-price averages. 2,436 have overall price more than tenfold below both
  side averages; 477 are more than hundredfold below. Another 6,721 are more
  than tenfold above both. Independently aggregated fields need not be mutually
  composable; these discrepancies prevent treating them as a coherent quote book.
* Across all development observations, **1,155 one-week** and **1,616 four-week**
  endpoint pairs have returns above **10,000%**. The largest observed price ratio
  is **43,463,916-fold**. These source values were retained, not repaired or used
  to invent intervening price paths.
* Replaying the saved coefficients reproduces every frozen weekly excess-return
  score for ridge and both reversals. Returns above 10,000% contribute
  **62.2–97.8%** of ridge's annual one-week arithmetic excess and **48.0–99.93%**
  of its four-week excess. In 2021 at four weeks, frozen excess is 1,233.308494
  in return-fraction units, with **99.9257%** contributed by those extremes.

This audit was added **after** the frozen run; it changes no observation, fit,
threshold or reported result. It diagnoses the extraordinary arithmetic means.
Spearman's cross-era support still passes the frozen screen. The finding is a
repeatable relationship in the provider's weekly numbers, with unresolved
aggregation, ticks, affordability, queue, timing and source-continuity questions.
It cannot establish that an account could buy and later sell at these averages.

## Recommendation for one account

**Stop deployment and expansion of the existing daily execution strategy.** The
mean-proxy replay has no common profitable tested share and no positive lower
profit bound; its conditional break-even grid interval has an infinity upper
endpoint. Current-limit sensitivities and terminal inventory marks remain
uncalibrated. The weekly rules have no identified executable participation
threshold at all; the old daily interval must not be attributed to them.

It would be false to conclude that no time-invariant price relationship exists:
the frozen reversal and ridge diagnostics survive every test era. The full
archive bought that distinction and substantial early breadth. It did not buy
identified fills, historical limits, executable profit or a finite one-account
break-even interval. Preserve the finding as research; it does not overturn the
stop verdict for the present account strategy. The holdout remains sealed.

## Reproduction and isolation

Run from the repository root; all generated artifacts and source data remain
outside Git. Commands are resumable for the archive and weekly diagnostics:

```bash
export OSRS_DATA_DIR=/home/martin/osrs-data
ml/.venv/bin/python -m osrs_ml.weekly_ingest \
  --output "$OSRS_DATA_DIR/ge-tracker-weekly-v1" \
  --development-run ml/runs/phase2-real-v1 \
  --workers 8 --acknowledge-private-research
ml/.venv/bin/python -m osrs_ml.weekly_coverage \
  --source "$OSRS_DATA_DIR/ge-tracker-weekly-v1" \
  --output "$OSRS_DATA_DIR/deep-history-coverage-v1" --acknowledge-private-research
ml/.venv/bin/python -m osrs_ml.weekly_research \
  --source "$OSRS_DATA_DIR/ge-tracker-weekly-v1" \
  --output "$OSRS_DATA_DIR/deep-history-weekly-v1" --acknowledge-private-research
ml/.venv/bin/python -m osrs_ml.uncertainty \
  --source "$OSRS_DATA_DIR/participation-bounds-v3-cached" \
  --output "$OSRS_DATA_DIR/deep-history-uncertainty-v2" --acknowledge-private-research
```

The uncertainty command refuses an existing output directory. The executed v2 run
completed **1,620 conditional profit intervals and 240 threshold summaries**; its
two result CSVs match v1 **byte for byte**. Source ledger hashes, source manifest
hash and code hash are recorded externally. The source results hash is
`8e46714296cb08d655eb0f6759fac2bb3bd0a74069972df9ba776e81c58c441d`.
All financial uncertainty calculations use empirical blocks; none uses Gaussian
samples. Weekly normality and Gaussian eligibility are reported above. The saved daily predictions include a history-length
feature; their reuse is a diagnostic of that frozen model, not certification of
the stricter six-feature date-invariant weekly model.

Executed verification:

```text
121 passed in 32.59s
All checks passed!
```

The streaming equivalence test preserves 10,000 rows, nulls, integer storage and
provenance across Parquet groups. Assembly streams batches rather than retaining
a two-million-row Python object list; analysis projects needed columns and releases
frames between horizons. All original mechanics remain covered. Changes include concurrency, cache/backoff, exact-gap
horizons, causal features, date-translation invariance, tied ranking and inadequate
era tests. No C++ backend file was modified. Holdout stays sealed at Unix
`1785024300`; weekly rows require `timestamp + 604800 + 300 < holdout_start`.


Executed completion and independent audits:

```text
Archived 4586/4586 items; elapsed=758.1s; holdout NOT analyzed
FULL ARCHIVE AND FROZEN WEEKLY ANALYSIS COMPLETE
PASS: 980 annual metric/block intervals have complete weekly inputs; no empty era draws
PASS: all 14 fits purge train/test labels; holdout_read=False
PASS: executed model, protocol and ingester code hashes match current files
```

The elapsed value is the **last resumed segment**, not total collection time.
The panel SHA-256 is
`36b861ec5d7baa636a1eb70e9dea3fcbb73dd151ec603e6c9659feea91ea5208`.
The weekly analysis records code/protocol hashes and each fit's saved score hash;
the independent audit replays coefficients without refitting. To reproduce it:

```bash
ml/.venv/bin/python -m osrs_ml.weekly_audit \
  --source "$OSRS_DATA_DIR/ge-tracker-weekly-v1" \
  --research "$OSRS_DATA_DIR/deep-history-weekly-v1" \
  --output "$OSRS_DATA_DIR/deep-history-audit-v1" --acknowledge-private-research
```

Only aggregate findings and methodology are committed. Raw responses, item-level
statistics, fitted parameters, ledgers and bootstrap audits remain external and
private. No C++ backend file was modified.
