# Fixed-gap midpoint reversal diagnostic v1 — frozen before outcomes

Registered 2026-10-29 following `f1a3e1a`, before inspecting any gap outcomes.
This follows cycle 4's measurement finding; it is neither independent discovery
nor a profit backtest. Historical account failures and processing's adjusted p=1
remain unchanged. No economic rule is modified or tuned.

Question: does midpoint reversal persist when the label has no common endpoint
with the signal and leaves one complete source bucket between them?

## Fixed observations and family

M[t] = (buyingPrice[t] + sellingPrice[t])/2, using weekly aggregate averages.
Score = -(M[t]/M[t-L]-1), for L in {1,4} weeks.
Label = M[t+2w+H]/M[t+2w]-1, for H in {1,4} weeks.
The fixed baseline offset is **two weeks**, not a searched parameter: bucket
[t+w,t+2w) intervenes between signal bucket [t,t+w) and baseline bucket
[t+2w,t+3w). The signal becomes available at t+w+300 seconds. No shared price
endpoint remains. This does not eliminate stale prices, serial measurement error,
spread effects or selection in the provider's current catalogue.

Exactly **28 tests**: seven eras (2020–2025 and development 2026), two lookbacks,
two horizons. Midpoint only; no alternate gap, field, universe, threshold or
subperiod will be evaluated. All four endpoints must be exact observations for
the same item, with finite positive buying/selling prices and completed counts.
No requirement on overallPrice, no clipping, named-item exclusion, inversion
removal or interpolation. Require >=20 eligible items per weekly correlation.
Within-week Spearman(score,label) is the sole tested outcome, equally weighted
across weeks. This estimates no GP, tax-adjusted return or account capacity.

Decision availability t+w+300 must be >= era start. Last label availability
`t+(2+H+1)w+300` must be strictly < era end (holdout cutoff for 2026). Earlier
sealed rows supply lookback context only. Reindex onto every calendar week allowed
by these inequalities; missing or constant correlations remain missing, never zero.

## Sealed data and durable execution

Use only the sealed development `ge-tracker-weekly-v1/weekly.parquet` under
`OSRS_DATA_DIR=/home/martin/osrs-data`, SHA-256
`36b861ec5d7baa636a1eb70e9dea3fcbb73dd151ec603e6c9659feea91ea5208`.
Reuse the verified date-first loader: complete manifest, `holdout_read=false`,
cutoff 1785024300, hash before reads, date-only availability/grid/duplicate checks
before materializing any market column, SQL `available_at < cutoff`. Never open
raw histories, reserved daily data, later market observations or holdout controls.
No training, synthetic market data, live orders or C++ changes.

Commit this registration before implementation and outcomes. Commit tested code
before running it. Record protocol, source, code/helper and output hashes outside
git; reserve each attempt durably and refuse output-directory reuse. Failed
attempts must be documented; no silent replacement of an inspected result.

## Frozen uncertainty and interpretation

Empirical circular whole-week block bootstrap, blocks {4,8} weeks, 20,000 draws,
seed 42. Share timestamp draws across lookbacks within each era/horizon. No
Gaussian statistics. Mean weekly Spearman is the statistic. One-sided centered-null
p = (1 + count(bootstrap_mean - observed_mean >= observed_mean))/20001.
Report ordinary uncentered 95% percentile intervals using inverted-CDF quantiles.
Require all calendar correlations finite, >=24 weeks and nonconstant series;
otherwise inconclusive and p=1. Use the worse p of the two blocks.

Conservatively reserve the preceding field audit's 112 tests too: the new rows use
**Bonferroni multiplier 140 = 112 prior + 28 new**, including inadequate rows.
Raw familywise threshold .05/140 = 0.000357142857; all-null expected pointwise 5%
false positives for the combined finite diagnostic family is 7. This does not
correct the full prior research history, nor retrospectively replace the earlier
audit's reported 112-test inference. Pass only if adjusted p<.05 and both ordinary
lower bounds >0. Require all seven eras for a lag/horizon all-era persistence claim.
Report all 28 rows and both blocks, including corrected failures and missingness.

A pass rules against an explanation solely from the identical signal/label price
endpoint; it does not establish executable alpha or rule out serial measurement
error. A failure means the previous finding does not establish this delayed
relationship; do not change the gap or horizon until it passes. Own-fill processing
records remain the direct economic gate. Any next strategy/profit experiment
requires separate registration, realistic execution and search-adjusted inference.
