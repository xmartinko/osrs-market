# Reversal field consistency audit v1 — frozen before outcomes

Registered 2026-10-29 following `94fa346`. This development-only source measurement
diagnostic follows the documented overall/side-price inconsistency. It is not an
independent rediscovery, account backtest or profit test. The original battery's
213 failures remain intact. No historical trading rule will be tuned.

## Question and fixed comparison

Does the reversal rank relationship persist when both lagged signal and future
label use the arithmetic midpoint of the provider's two side averages?
O = overallPrice; M = (buyingPrice + sellingPrice)/2. Enumerate all four
signal/label cells: O/O, O/M, M/O, M/M. Score = `-(P[t]/P[t-L]-1)`; label =
`Q[t+H]/Q[t]-1`, with exact observed endpoints. Lookback L independently {1,4}
weeks; horizon H independently {1,4} weeks. No fit, tax-return proxy or arithmetic
profit claim. Within-week Spearman correlation is the sole tested outcome.

For each L/H/week, use the same items for all four cells: all five source fields
(O, both side prices, both side completed counts) must be finite and >0 at t-L,
t and t+H. Require >=20 common items. Do not remove inversions, outliers, overall
prices outside the side band, named items or selected eras. Midpoints of averages
are aggregate measurements, not quotes. Report common-item counts and weekly
O/M lag-return rank agreement descriptively. Attenuation or persistence cannot
prove causality or fills.

Seven eras: 2020, 2021, 2022, 2023, 2024, 2025 and development 2026. Decision
availability `t + WEEK + 300` must be >= era start; future availability
`t + (H+1)*WEEK + 300` must be strictly < era end (or holdout cutoff). Earlier
development rows may supply lag context. Reindex onto the full calendar weekly
grid allowed by these inequalities, preserving missing weeks. Missing or constant
within-week correlation is not zero and is not dropped.

## Boundary and provenance

Read only `/home/martin/osrs-data/ge-tracker-weekly-v1/weekly.parquet`, the sealed
development panel with SHA-256
`36b861ec5d7baa636a1eb70e9dea3fcbb73dd151ec603e6c9659feea91ea5208`.
Require matching completed source manifest, `holdout_read=false`, cutoff
**1785024300**, and date-only verification of every availability before projecting
market fields through DuckDB with `available_at < cutoff`. Refuse duplicates,
noninteger timestamps, inconsistent weekly grids or availability other than
`timestamp + WEEK + 300`. Never open raw histories, later market columns, daily
reserved data or holdout controls. Data/artifacts remain outside git under
OSRS_DATA_DIR. Record hashes of protocol, code, imported statistical helpers,
source manifest, panel and every output. Refuse existing output manifests;
incomplete attempts cannot silently overwrite.

## Fixed inference and decision

112 tests = 7 eras x 2 lookbacks x 2 horizons x 4 field cells. Empirical circular
whole-week block bootstrap with blocks {4,8} weeks, **20,000 draws, seed 42**.
Within each era/horizon share timestamp draws across lookbacks and field cells.
No Gaussian statistics or synthetic training/market observations. Statistic:
mean weekly rank correlation. Center the observed series under the zero-mean
null; one-sided p = (1 + count(centered bootstrap means >= observed mean))/20001.
Ordinary 95% percentile intervals use uncentered draws.

Require every allowed calendar week finite, >=24 weeks (three larger eight-week
blocks), and a nonconstant weekly series. Otherwise label inconclusive and p=1;
report missing/constant reason and counts. Use the worse p of both blocks.
Bonferroni p_adj=min(1,112*p); pass only if p_adj<.05 and both ordinary lower
bounds >0. Report raw and adjusted p together. Raw threshold = .05/112; expected
pointwise 5% false positives under an all-null family = 5.6. Correction covers this
finite diagnostic, not prior research. Intervals are not simultaneous bounds.

A lookback/horizon supports **all-era midpoint consistency** only if its seven
M/M rows pass. O/O is a matched-sample reference, not exact reproduction of the
older differently sampled screen. Publish every cell, block and era including
failures. No clipping, universe repair or parameter revision to obtain a pass.
A surviving diagnostic only justifies further measurement; it cannot rescue
failed account-profit tests. Own-fill processing calibration remains the direct
execution gate. Any additional reversal experiment needs separate registration.
