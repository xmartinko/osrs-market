# Frozen strategy battery v1 — executed development results

Completed 2026-10-29 from registration `edc2028` and unchanged executor `0023d27`.
The continuation resumed the interrupted original run; it introduced no new rules,
parameters, exclusions or participation samples. **No established deployable edge:
zero of 213 scenarios survives the registered correction.** This is a failure to
establish an edge in this finite battery, not proof that the market has no edge.

## Search, data boundary and execution

All 71 rules and 0.1% / 1% / 5% participation samples are reported, including
unavailable rules. There are 98 adequate tests, 58 inconclusive scenarios and 57
unidentified scenarios. The latter include all 54 intraday scenarios (no development
evaluation buckets) and the three shop scenarios (no shop stock/cost observations).
There are 84 daily account timestamps over 83 elapsed days, and 343 weekly
account timestamps over 342 elapsed weeks. Daily evaluation contains 341,047 rows
and 4,427 items; weekly evaluation contains 1,319,958 rows and 4,448 items.

The [registered protocol](strategy-battery-protocol.md) and
[enumeration](../ml/strategy-battery-v1.json) remain unchanged. Every loaded market
row has `available_at < 1785024300`, filtered in DuckDB before materialization.
The reserved holdout was neither opened nor unlocked. No synthetic observations,
training data or Gaussian draws enter these results. This battery trains no model.
Current metadata, including limits and alchemy values, remains an explicit historical
sensitivity; aggregate-price fills do not identify queue allocation or adverse selection.

Inference uses 20,000 empirical circular moving-block draws of account equity
increments, seed 42, synchronized timestamps, and the worse of both registered
block lengths. Intervals below envelope their ordinary 95% percentile intervals;
they are **pointwise conditional intervals**, not simultaneous intervals or an
execution uncertainty model. Adequacy requires ten completed positions and four
times the larger block length. Inadequate, unavailable and inactive rules get p=1.
Volatility sizing additionally must beat its paired plain-reversal baseline.

Bonferroni uses all **213 tests**: the familywise threshold is
`0.05/213 = 0.000234741784`. There would be **10.65 pointwise 5% false positives
in expectation** in an all-null family, irrespective of dependence. Correction
covers this registered family, not the full adaptive research history. Every
adjusted p-value is 1.0. No failing rule was tuned or rescued by an era or diagnostic.

## Most informative numbers

* Largest raw net GP: `limit_spread_1w`, **5% participation**, +29,900,843 net
  (+31,301,248 same-fill gross), 50 completed positions, raw p=0.439828,
  adjusted p=1.0, conditional interval **[−402,725,397, +461,693,757] GP**.
  Elapsed return is 520.41 GP/hour over 57,456 hours, 299.01% of initial 10M;
  maximum drawdown is **96.96%**. Cash P&L is +29,131,711 and realized P&L
  +33,425,513 GP; remaining inventory is 769,132 GP (1.93% of final equity),
  not a liquidation. Turnover is 10.0782 times initial capital, mean/peak tied
  capital 4,846,746 / 7,264,685 GP, bought/sold units 102,746 / 93,419.
  It has 137 buy / 237 sell fill lots (71 / 134 opportunities).
  It uses a peak 5% of a reported side bucket and is first positive at the
  registered 1% sample. These observations do not identify attainable participation.
  Six of seven calendar eras are profitable, including partial 2026; the pooled
  uncertainty still fails. Large transient marks and reversals remain in the path.
* Smallest raw p: `low_tax_1d`, **1% participation**, +5,022 GP (2.52 GP/hour),
  13 completions, interval [+991, +9,434], raw p=0.012899355, adjusted p=1.0.
  A positive unadjusted interval does not survive the search.
* Patient daily holds at 1% earn **+537 / +137 / +134 / −162 GP** for
  3/7/14/28 days, with only **2 / 1 / 1 / 2 completions**. All are inconclusive,
  even before search correction; longer holds also fail temporal coverage.
* Patient weekly holds at 1% earn **−386,735 / −1,786,743 / +1,334,901 /
  −79,835 GP** for 1/2/4/8 weeks, with **25 / 26 / 16 / 16 completions**.
  Every adjusted p=1.0; the positive four-week rule has interval
  [−172,904,813, +172,331,718]. At 5%, two-week patient profit rises to
  +9,260,118 GP, but raw p=0.351882 and adjusted p=1.0. Low turnover does
  not resolve the uncertainty in these provider-derived marked accounts.
* Processing at 1% shows **+1,764,761 GP**, interval [+511,006, +3,001,436],
  but only **8 completed batches**, so registered raw/adjusted p=1.0.
  It produces/sells 13,200 bows, buys 36,300 input units, spends 8 active hours
  (55 minutes production plus five setup each), and reports 220,595 GP/active
  hour versus 885.92 GP/elapsed hour. Cash P&L is just **+110,374 GP**;
  **1,654,387 GP is marked inventory (14.06% of final equity)**. Realized P&L
  is +2,054,103 GP, with unmatched inputs retained. Peak observed side share
  is 0.5305%; the first positive registered sample with realization is 0.1%.
  Positive intervals cannot override the activity gate or validate actual fills.
* Alchemy shows +24,073 GP at each share but **zero casts, zero production
  sessions and zero coin realizations**. Cash P&L is −246,853 GP and inventory
  mark 270,926 GP, after the 1,500 GP staff charge. This is inventory appreciation,
  not an observed alchemy margin. Partial legs consume slots; no matched-input
  production is inferred from them. Shop profitability remains unidentified.

## Complete 71-rule table

Planning case is 1%. C = completed positions/batches; CI = pointwise conditional
95% interval envelope in GP; adjusted p includes every registered share. Other
net GP reports 0.1% / 5%, without selecting one. Years counts positive calendar
equity increments at 1%; 2026 is partial and daily accounts only cover 2026.
“Inconclusive” is insufficient activity/coverage, not evidence of no opportunity.
“Unidentified” means required observations are unavailable. All adjusted p=1.

| Rule | Net GP at 1% | C | CI GP | Adjusted p | Status | Other net GP: 0.1% / 5% | Positive years |
| --- | ---: | ---: | --- | ---: | --- | ---: | ---: |
| xs_reversal_5m | — | — | — | 1.0 | unidentified | — / — | — |
| xs_momentum_5m | — | — | — | 1.0 | unidentified | — / — | — |
| abs_reversal_5m | — | — | — | 1.0 | unidentified | — / — | — |
| abs_momentum_5m | — | — | — | 1.0 | unidentified | — / — | — |
| xs_reversal_1h | — | — | — | 1.0 | unidentified | — / — | — |
| xs_momentum_1h | — | — | — | 1.0 | unidentified | — / — | — |
| abs_reversal_1h | — | — | — | 1.0 | unidentified | — / — | — |
| abs_momentum_1h | — | — | — | 1.0 | unidentified | — / — | — |
| xs_reversal_4h | — | — | — | 1.0 | unidentified | — / — | — |
| xs_momentum_4h | — | — | — | 1.0 | unidentified | — / — | — |
| abs_reversal_4h | — | — | — | 1.0 | unidentified | — / — | — |
| abs_momentum_4h | — | — | — | 1.0 | unidentified | — / — | — |
| xs_reversal_1d | 238 | 7 | [-5,703, 6,058] | 1.0 | inconclusive | 78 / 23,442 | 1/1 |
| xs_momentum_1d | -69,000 | 8 | [-177,425, 6,850] | 1.0 | inconclusive | -8,482 / -294,536 | 0/1 |
| abs_reversal_1d | 238 | 7 | [-5,703, 6,058] | 1.0 | inconclusive | 78 / 23,442 | 1/1 |
| abs_momentum_1d | -69,000 | 8 | [-177,425, 6,850] | 1.0 | inconclusive | -8,482 / -294,536 | 0/1 |
| xs_reversal_1w | 2,250,254 | 42 | [-41,780,264, 46,170,433] | 1.0 | tested | -371,032 / 18,621,766 | 5/7 |
| xs_momentum_1w | 260,530 | 49 | [-83,036,180, 81,435,154] | 1.0 | tested | -189,037 / 4,579,010 | 3/7 |
| abs_reversal_1w | 2,250,254 | 42 | [-41,780,264, 46,170,433] | 1.0 | tested | -371,032 / 18,621,766 | 5/7 |
| abs_momentum_1w | 260,530 | 49 | [-83,036,180, 81,435,154] | 1.0 | tested | -189,037 / 4,579,010 | 3/7 |
| xs_reversal_4w | -362,924 | 41 | [-17,150,310, 15,402,537] | 1.0 | tested | -525,837 / 8,792,993 | 4/7 |
| xs_momentum_4w | -565,594 | 48 | [-13,422,025, 12,308,600] | 1.0 | tested | -274,537 / 2,201,766 | 2/7 |
| abs_reversal_4w | -362,924 | 41 | [-17,150,310, 15,402,537] | 1.0 | tested | -525,837 / 8,792,993 | 4/7 |
| abs_momentum_4w | -565,594 | 48 | [-13,422,025, 12,308,600] | 1.0 | tested | -274,537 / 2,201,766 | 2/7 |
| patient_3d | 537 | 2 | [-24, 1,638] | 1.0 | inconclusive | 0 / 12,406 | 1/1 |
| patient_7d | 137 | 1 | [-6,683, 6,974] | 1.0 | inconclusive | 0 / 9,246 | 1/1 |
| patient_14d | 134 | 1 | [-6,648, 6,714] | 1.0 | inconclusive | 0 / 11,887 | 1/1 |
| patient_28d | -162 | 2 | [-6,628, 6,268] | 1.0 | inconclusive | 0 / -967 | 0/1 |
| patient_1w | -386,735 | 25 | [-10,174,694, 8,496,521] | 1.0 | tested | -57,566 / 8,807,318 | 3/7 |
| patient_2w | -1,786,743 | 26 | [-11,528,005, 7,174,225] | 1.0 | tested | -51,186 / 9,260,118 | 3/7 |
| patient_4w | 1,334,901 | 16 | [-172,904,813, 172,331,718] | 1.0 | tested | -150,521 / 7,351,224 | 4/7 |
| patient_8w | -79,835 | 16 | [-77,259,422, 78,608,195] | 1.0 | tested | -265,658 / 787,068 | 4/7 |
| lead_herbs_1d | 0 | 0 | [0, 0] | 1.0 | inconclusive | 0 / 0 | 0/1 |
| convergence_herbs_1d | 0 | 0 | [0, 0] | 1.0 | inconclusive | 0 / 0 | 0/1 |
| lead_ores_1d | 0 | 0 | [0, 0] | 1.0 | inconclusive | 0 / 0 | 0/1 |
| convergence_ores_1d | -19,427 | 1 | [-157,060, 88,850] | 1.0 | inconclusive | -19,426 / -19,427 | 0/1 |
| lead_resources_1d | -16,757 | 1 | [-88,507, 40,873] | 1.0 | inconclusive | -16,757 / -16,757 | 0/1 |
| convergence_resources_1d | 0 | 0 | [0, 0] | 1.0 | inconclusive | 0 / 0 | 0/1 |
| lead_herbs_1w | -1,015,516 | 7 | [-2,358,203, 404,392] | 1.0 | inconclusive | -1,015,516 / -1,015,516 | 2/7 |
| convergence_herbs_1w | -1,212,281 | 11 | [-2,242,972, -275,891] | 1.0 | tested | -1,212,281 / -1,212,281 | 0/7 |
| lead_ores_1w | -2,653,009 | 34 | [-4,914,587, -459,954] | 1.0 | tested | -2,290,352 / -2,653,009 | 1/7 |
| convergence_ores_1w | -2,131,016 | 39 | [-4,388,277, 74,473] | 1.0 | tested | -1,818,997 / -2,131,016 | 1/7 |
| lead_resources_1w | -1,420,350 | 20 | [-3,095,260, 235,220] | 1.0 | tested | -1,420,350 / -1,420,350 | 0/7 |
| convergence_resources_1w | -1,133,895 | 14 | [-2,542,967, 228,427] | 1.0 | tested | -1,133,895 / -1,133,895 | 1/7 |
| persistent_spread_1d | 3,496 | 4 | [-90,186, 98,320] | 1.0 | inconclusive | 236 / 4,766 | 1/1 |
| volume_shock_1d | -432,176 | 14 | [-1,191,559, 72,987] | 1.0 | tested | -48,118 / -939,972 | 0/1 |
| limit_spread_1d | -3,522,442 | 26 | [-5,383,945, -1,899,163] | 1.0 | tested | -1,388,344 / -3,186,511 | 0/1 |
| low_tax_1d | 5,022 | 13 | [991, 9,434] | 1.0 | tested | 438 / 13,461 | 1/1 |
| persistent_spread_1w | 4,264,599 | 28 | [-112,781,368, 118,495,559] | 1.0 | tested | 91,058 / 3,586,065 | 6/7 |
| volume_shock_1w | -2,380,339 | 90 | [-16,719,360, 12,202,519] | 1.0 | tested | -797,240 / 984,888 | 3/7 |
| limit_spread_1w | 3,781,140 | 38 | [-1,238,727,919, 1,247,954,802] | 1.0 | tested | -439,471 / 29,900,843 | 4/7 |
| low_tax_1w | 976,175 | 44 | [-14,019,711, 14,683,090] | 1.0 | tested | 128,690 / 5,338,386 | 6/7 |
| persistent_spread_4w | 12,654,849 | 31 | [-110,579,504, 133,358,773] | 1.0 | tested | -6,306 / 1,478,728 | 6/7 |
| volume_shock_4w | -1,336,121 | 51 | [-16,899,604, 13,859,756] | 1.0 | tested | -729,853 / 2,051,097 | 2/7 |
| limit_spread_4w | 14,721,392 | 35 | [-1,236,807,852, 1,266,742,827] | 1.0 | tested | 302,422 / 9,683,952 | 5/7 |
| low_tax_4w | 742,623 | 58 | [-16,009,853, 16,591,428] | 1.0 | tested | 135,681 / 7,165,549 | 7/7 |
| alchemy_1d | 24,073 | 0 | [-10,737, 60,476] | 1.0 | inconclusive | 24,073 / 24,073 | 1/1 |
| processing_1d | 1,764,761 | 8 | [511,006, 3,001,436] | 1.0 | inconclusive | 1,053,603 / 1,764,761 | 1/1 |
| shop_1d | — | — | — | 1.0 | unidentified | — / — | — |
| vol_size_5m | — | — | — | 1.0 | unidentified | — / — | — |
| range_5m | — | — | — | 1.0 | unidentified | — / — | — |
| vol_size_1h | — | — | — | 1.0 | unidentified | — / — | — |
| range_1h | — | — | — | 1.0 | unidentified | — / — | — |
| vol_size_4h | — | — | — | 1.0 | unidentified | — / — | — |
| range_4h | — | — | — | 1.0 | unidentified | — / — | — |
| vol_size_1d | 1,071 | 12 | [-4,690, 8,646] | 1.0 | tested | -1,175 / 18,743 | 1/1 |
| range_1d | -4,741 | 7 | [-113,395, 102,780] | 1.0 | inconclusive | -4,764 / -119,707 | 0/1 |
| vol_size_1w | 252,906 | 68 | [-6,472,780, 7,018,325] | 1.0 | tested | 75,378 / 2,512,011 | 6/7 |
| range_1w | 137,392 | 66 | [-1,820,619, 2,116,985] | 1.0 | tested | -24,146 / 1,023,499 | 2/7 |
| vol_size_4w | 280,963 | 57 | [-3,680,913, 3,988,115] | 1.0 | tested | 4,697 / 1,538,212 | 6/7 |
| range_4w | -238,780 | 50 | [-3,896,032, 3,746,362] | 1.0 | tested | 108,457 / -618,547 | 3/7 |

## Annual diagnostics, all observed rules at 1%

No era was selected or excluded. Entries are account equity increments in GP,
including changing inventory marks, not annual realized sale proceeds. A dash
means the account is not observed in that year. The full external annual CSV
contains every available scenario at all three registered shares.

| Rule | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026, partial |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| xs_reversal_1d | — | — | — | — | — | — | 238 |
| xs_momentum_1d | — | — | — | — | — | — | -69,000 |
| abs_reversal_1d | — | — | — | — | — | — | 238 |
| abs_momentum_1d | — | — | — | — | — | — | -69,000 |
| xs_reversal_1w | -27,457 | 21,310 | 48,042 | 1,411,559 | 687,413 | 244,403 | -135,016 |
| xs_momentum_1w | -1,292,836 | -293,074 | 1,010,197 | 795,722 | 346,254 | -241,244 | -64,489 |
| abs_reversal_1w | -27,457 | 21,310 | 48,042 | 1,411,559 | 687,413 | 244,403 | -135,016 |
| abs_momentum_1w | -1,292,836 | -293,074 | 1,010,197 | 795,722 | 346,254 | -241,244 | -64,489 |
| xs_reversal_4w | -1,817 | -781,208 | -105,399 | 272,631 | 46,095 | 201,118 | 5,656 |
| xs_momentum_4w | -889,434 | 518,129 | -505,152 | -434,941 | 851,174 | -35,413 | -69,957 |
| abs_reversal_4w | -1,817 | -781,208 | -105,399 | 272,631 | 46,095 | 201,118 | 5,656 |
| abs_momentum_4w | -889,434 | 518,129 | -505,152 | -434,941 | 851,174 | -35,413 | -69,957 |
| patient_3d | — | — | — | — | — | — | 537 |
| patient_7d | — | — | — | — | — | — | 137 |
| patient_14d | — | — | — | — | — | — | 134 |
| patient_28d | — | — | — | — | — | — | -162 |
| patient_1w | 8,134 | 276,131 | -388,554 | -35,214 | -245,650 | 5,775 | -7,357 |
| patient_2w | 8,134 | 276,131 | -388,554 | -35,208 | -244,505 | 31,254 | -1,433,995 |
| patient_4w | 3,743 | -548,448 | 868,757 | 675,405 | 344,937 | -7,814 | -1,679 |
| patient_8w | 450 | -457,628 | 314,064 | -38,243 | 86,945 | -866 | 15,443 |
| lead_herbs_1d | — | — | — | — | — | — | 0 |
| convergence_herbs_1d | — | — | — | — | — | — | 0 |
| lead_ores_1d | — | — | — | — | — | — | 0 |
| convergence_ores_1d | — | — | — | — | — | — | -19,427 |
| lead_resources_1d | — | — | — | — | — | — | -16,757 |
| convergence_resources_1d | — | — | — | — | — | — | 0 |
| lead_herbs_1w | -614,743 | -128,270 | 127,684 | 109,961 | -89,541 | -299,436 | -121,171 |
| convergence_herbs_1w | -150,060 | -152,581 | -216,176 | -206,430 | -14,017 | -304,725 | -168,292 |
| lead_ores_1w | -698,651 | -113,017 | 36,165 | -426,320 | -553,363 | -780,570 | -117,253 |
| convergence_ores_1w | -896,708 | -181,926 | 314,218 | -39,049 | -246,603 | -469,894 | -611,054 |
| lead_resources_1w | -234,534 | -22,944 | -374,351 | -215,264 | -32,064 | -349,381 | -191,812 |
| convergence_resources_1w | 0 | -44,313 | -372,691 | -85,058 | -302,092 | -643,332 | 313,591 |
| persistent_spread_1d | — | — | — | — | — | — | 3,496 |
| volume_shock_1d | — | — | — | — | — | — | -432,176 |
| limit_spread_1d | — | — | — | — | — | — | -3,522,442 |
| low_tax_1d | — | — | — | — | — | — | 5,022 |
| persistent_spread_1w | 534 | 45,224 | 3,537,973 | 379,348 | 284,831 | -52,956 | 69,645 |
| volume_shock_1w | -1,146,478 | -472,003 | 295,745 | -1,130,132 | 7,550,164 | -8,013,457 | 535,822 |
| limit_spread_1w | -1,954,573 | -461,666 | 1,742,478 | 1,976,623 | -61,258 | 2,479,562 | 59,974 |
| low_tax_1w | 372,172 | 308,306 | 32,501 | 206,931 | 51,070 | 13,041 | -7,846 |
| persistent_spread_4w | 843 | 142,103 | 108,670 | 25,254 | 12,273,156 | -45,096 | 149,919 |
| volume_shock_4w | -1,539,590 | -51,095 | -697,805 | -26,367 | 180,937 | 854,643 | -56,844 |
| limit_spread_4w | -2,271,565 | 2,571,090 | 6,956,400 | 2,430,302 | 1,360,485 | 8,467,929 | -4,793,249 |
| low_tax_4w | 15,815 | 303,617 | 54,164 | 208,632 | 93,150 | 58,058 | 9,187 |
| alchemy_1d | — | — | — | — | — | — | 24,073 |
| processing_1d | — | — | — | — | — | — | 1,764,761 |
| vol_size_1d | — | — | — | — | — | — | 1,071 |
| range_1d | — | — | — | — | — | — | -4,741 |
| vol_size_1w | 13,442 | 60,621 | 84,190 | 44,889 | 27,009 | 30,974 | -8,219 |
| range_1w | -50,392 | -64,465 | 336,336 | -150,887 | 141,231 | -2,147 | -72,284 |
| vol_size_4w | -19,955 | 28,815 | 57,883 | 72,651 | 77,553 | 48,195 | 15,821 |
| range_4w | -16,175 | -20,106 | 243,115 | 77,863 | 16,834 | -521,753 | -18,558 |

## Artifacts, reproduction and decision

All data remain outside Git, under `/home/martin/osrs-data/strategy-battery-v1`:

* `results.csv`: original frozen 213-row results.
* `reported-results.csv`: all original fields plus buy/sell lot and opportunity
  counts, marked-equity share, realization activity and first positive registered
  share. Net/gross, elapsed/active GP/hour, return, drawdown, capacity units,
  turnover, mean/peak capital, bought/sold units, cash/realized GP and terminal
  marks remain present, including explicit missing values for unavailable rows.
* `annual-results.csv`: annual results at all three shares; `block-results.csv`:
  both blocks' p-values/intervals and paired sizing-improvement tests.
* Per-scenario ledgers, `run.json`, `audit-cycle.json` and
  `audited-artifacts-sha256.json` preserve account evidence and provenance.
  `report-cycle.py` reproduces the aggregate CSVs and this table without opening
  any market panels. Raw data and item-level results are never committed.

```bash
export OSRS_DATA_DIR=/home/martin/osrs-data
ml/.venv/bin/python -m osrs_ml.battery \
  --output "$OSRS_DATA_DIR/strategy-battery-v1" --acknowledge-private-research
ml/.venv/bin/python -m osrs_ml.battery_audit "$OSRS_DATA_DIR/strategy-battery-v1"
ml/.venv/bin/python "$OSRS_DATA_DIR/strategy-battery-v1/report-cycle.py"
```

The independent audit reconstructs cash, owned input consumption, per-unit tax,
integer price lots, frozen source references, qualification, latency/buy timeout,
buy-limit windows, reported bucket participation, slots and final conservative
marks. It verifies protocol, code, metadata, market input, development-manifest and
results hashes and rejects partial/duplicated families and summary/CSV disagreement.
It does not calibrate queue share, historical metadata, source consistency or
liquidation value. Aggregate audit output and full test output are recorded in the
journal. No C++ file was modified.

**Decision:** no deployment and no expansion of the failed forecast rules on these
outcomes. The patient formulation tested here has no established account edge;
its source-price motivation remains a separate result. Cross-item weekly planning
cases also lose. Mechanical processing is the next most concrete measurement lead:
audit its eight matched-input production batches and partial-leg inventory, then
pre-register a distinct prospective own-fill calibration with actual input prices,
sale tax and active time. Its present positive simulation is inconclusive, not a
survivor or a profit claim. Do not tune its thresholds, remove losing batches or
use the reserved holdout to make it pass. Alchemy's marked gain establishes no
production opportunity. More independent activity and observed fills are needed.
