# Private weekly history: frozen research protocol

This protocol is frozen before cross-era outcomes are examined. The existing
strategy's stop verdict stands unless new evidence overturns it. No tuning,
sub-period selection, model tournament, synthetic training data, or holdout access.
No C++ change is needed or authorized by this work.

## Source restrictions and storage

Source: https://www.ge-tracker.com/api/graph/{itemId}/all with
`Accept: application/x.getracker.v2.1+json`; catalogue: `/api/items`.
[Terms checked 2026-10-29](https://www.ge-tracker.com/terms-and-conditions).
The user authorizes private research only. No public-facing or competing tool,
publication of source data, or commercial redistribution without written consent.
UK database rights apply; access and IPs may be blocked. These restrictions also
apply to derived item-level panels, caches and research artifacts. Do not treat API
availability as permission for unrestricted reuse.

All source responses, metadata and derived panels live **outside the repository**
under `OSRS_DATA_DIR=/home/martin/osrs-data`. The ingester requires the explicit
`--acknowledge-private-research` flag, rejects paths inside the repository (including
resolved symlinks), and uses a process lock with bounded concurrency (eight workers
by default, up to sixteen). There is no artificial inter-request delay. The earlier
two-second limit was a user-supplied assumption, withdrawn on 2026-10-29; it was
not a source term. Cached successes, empty results and nonretryable failures are
retained. Only 403/429/5xx and connection failures retry with exponential backoff;
persistent errors pause scheduling, are reported, and can be retried on resume.
Blocking does not establish that access is forbidden. No access workarounds. An
interrupted collection resumes its immutable universe and original version directory.
Each cached response and every panel row carries URL, fetch timestamp, source and
schema version. Delete the whole version directory and its derived artifacts on a
source purge request. Never commit source data, item-level outputs, models or ledgers.
Only methodological documentation and aggregate findings may enter Git.

The catalogue is a **current listed-item universe**, not proof that delisted items
are represented. Coverage includes every requested item, including empty/error and
sparse histories; current listings impose survivorship limitations. No historical
buy limits, order-book depth, or source methodology continuity are inferred.

## Questions and fixed analysis

Weekly averages cannot answer five-minute flipping, queue position, achievable
fills, intrabucket price paths, attainable participation or realized account P&L.
They can challenge the temporal stability of spreads, margins, liquidity rankings,
momentum and mean reversion. Source aggregation changes can mimic market changes.
Two observations separated by a gap are never silently treated as adjacent weeks.

Keep all weekly periods whose conservative end (`ts + 7 days + 300 seconds`) is
strictly before the saved daily holdout start. Later source data stay sealed in
the raw cache; no analysis of their prices or volumes. Dates are used only for
causal lags, exact horizon matching, purge boundaries and reporting eras. Model
inputs are explicit market-state allowlists, never dates, weekday, regime, update,
event, item-age or history-length proxies for calendar time. The old frozen daily
predictions are diagnostics of the previous model (which includes history length),
not certification of this stricter feature policy. No refitting those predictions.

Analyze annual eras, with 2017–2019 as the initial training interval and expanding
earlier-only fitting for 2020 onward. Fixed one- and four-week horizons. Fit a
linear rank relationship using spread fraction, log price, log observed volume,
one/four-week returns and four-week volatility. Train-only medians/scaling and
ridge penalty 1; no hyperparameter search. Report out-of-era rank correlation and
top-minus-universe *price-return diagnostic*, plus fixed momentum and reversal
rules. No return diagnostic is a fill or profit claim. Use a constant present-day
2% per-unit floored/capped tax as a counterfactual across all eras, not an invented
historical tax schedule or calendar feature. Report margins with and without tax.
Reject an all-era edge claim if any adequately observed test era lacks positive
statistical support. Inadequate eras are inconclusive, never silently excluded.
Report item ranking correlations on common items and their counts between eras.

## Uncertainty (frozen before running)

Test log-returns and signed relative spreads per item and within three liquidity
bands, whose boundaries are learned only from 2017–2019. Use D'Agostino–Pearson
normality tests (minimum 20 observations), plus lag-one dependence diagnostics.
Non-rejection is not proof of normality. Gaussian mean intervals require p >= .05,
at least 30 observations and no material lag-one dependence (absolute correlation
<= .1); otherwise use moving-block bootstrap. Constant/insufficient samples are
explicitly unidentified. Do not generate Gaussian samples. Financial P&L and
participation inference always use empirical blocks because of state dependence,
short folds and terminal marks. Weekly diagnostics resample entire weeks together
across items, four-week circular blocks; repeat with eight weeks as a sensitivity.
Use 2,000 draws and seed 42; report pointwise 95% percentile intervals and the
all-era requirement rather than cherry-picking a pooled positive interval.

Daily uncertainty uses only the already completed `integer_lots_v2`,
`volume_bounded_v3` development ledgers. Paired seven-day circular moving blocks
of daily equity increments preserve scenario comparisons, cross-item dependence
and local serial dependence. Repeat with 14-day blocks. These are conditional
intervals for the observed marked-equity path, **not** resimulated accounts or
identified execution uncertainty. No bootstrap sample enters training or becomes
a claimed observed market path. Report each fold/preset/share and all frozen
baselines; no new participation search. No-trade is exactly zero.

For break-even, retain the original grid and nonmonotonicity. For each paired draw,
record the first positive sampled participation in each fold and the first sample
positive in all folds; no positive sample is an explicit infinity atom. Report its
mass and extended-real 95% interval; also report the observed adjacent grid bracket.
This is a conditional **first-positive-grid statistic**, not a continuous threshold
CI. An unidentified continuous/attainable break-even must be reported as such,
even when this proxy statistic has a finite interval. Equity increments cannot
identify activity on a resampled account; use the original buy/sell activity gate
and disclose that condition. No interpolation and no assumption of monotonic P&L.

## Implementation definitions (2026-10-29, before cross-era results)

Use the observed integer `overallPrice` for price changes and log price; relative
spread is `(buyingPrice-sellingPrice)/overallPrice`. Feature-eligible weeks require
positive overall and side prices and positive completed volume on both sides;
signed/inverted spreads remain diagnostic observations. All raw and coverage rows
remain retained. One/four-week returns require exact timestamp matches; four-week
volatility requires four consecutive one-week log returns. No gap filling. Labels
are forward overall-price returns at exact one/four-week timestamps, with label
availability at the **end** of the future weekly bucket plus 300 seconds. Both
fitting and annual test summaries purge labels reaching the next era boundary or
the holdout. The constant-tax diagnostic subtracts the exact per-unit tax on the
future observed overall price; this remains a price diagnostic, not a fill claim.

The six allowed features enter the linear ridge fit after train-only median
imputation and scaling; the target is the within-week cross-sectional fractional
rank of the forward return, centered at 0.5. Penalty is 1 with an unpenalized
intercept. No item identifiers, missing indicators, dates or ages enter fitting.
Separate fits use each fixed horizon, expanding from 2017–2019. In addition to
the rank fit, report the fixed one/four-week momentum and their sign reversals,
spread fraction and observed-volume rankings, with no choice between them after
results. The top group is the upper decile of each observed weekly score ranking
(including ties at the cutoff); the universe is the same feature/label-eligible
weekly cross section. Spearman correlations and top-minus-universe returns are
computed weekly before bootstrapping entire weeks. An adequately observed era
requires at least 20 weekly cross sections with at least 20 items each; all other
eras are explicitly inconclusive. A claimed stable price-ranking rule must have
positive lower 95% bounds on both rank correlation and **after-tax** top-minus-
universe diagnostic in every adequate era, at both predeclared block lengths.
This strict screen is a rejection diagnostic, not an executable-profit test.

Normality screens use ordered exact log returns and signed spreads per item and
within fixed train-volume terciles. Pooled bands concatenate items within weeks;
their lag screen is supplemented by lag-one correlation of the weekly band mean.
Gaussian mean intervals are only reported for eligible per-item series; band and
cross-era intervals always preserve whole weeks with empirical blocks. Report
how many per-item series pass and fail, including insufficient/constant samples.
Common-item annual median spread, tax-adjusted margin, volume and momentum
ranking correlations quantify descriptive stability, with common-item counts.
