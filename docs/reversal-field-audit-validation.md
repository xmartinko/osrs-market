# Executed reversal field consistency audit

**The reversal rank relationship is not confined to overallPrice.** All 28
side-midpoint/side-midpoint era tests pass the registered 112-test correction.
This is a source measurement finding, not evidence of executable profit. The
original account battery still has zero corrected survivors, and processing's
original adjusted p remains 1. Actual own-fill evidence remains the execution gate.

The [protocol](reversal-field-audit-protocol.md) was committed in `5aa7195` before
outcomes, and implementation plus tests in `0ef050d` before execution. No parameter,
sample exclusion, horizon, field or significance threshold changed after outcomes.
This development diagnostic is motivated by known source inconsistencies and
prior reversal discovery; its correction does not cover the entire research history.

## Data, comparison and uncertainty

The hash-verified sealed panel contains **1,803,631 development rows**. Maximum
availability is 1784765100, strictly before the reserved cutoff 1785024300. The
loader verifies the panel hash and date-only boundary before projecting market
columns through DuckDB. No raw histories, later market fields, holdout controls or
C++ backend were opened or modified. All detailed artifacts remain outside git in
`/home/martin/osrs-data/reversal-field-audit-v1`.

O denotes overallPrice; M denotes the arithmetic mean of buyingPrice and
sellingPrice. Each weekly cross-section uses the same items for all four cells,
requiring positive finite prices and side counts at all three exact endpoints.
Outliers and inverted side averages remain. There are **5,208 weekly score rows**,
112 era tests and 224 block tests. All 112 tests meet the registered coverage gate;
there are no missing calendar correlations. At least **2,446 matched items** enter
every cross-section. One-week labels have 29–52 weeks per era; four-week labels
have 26–49. The first six eras are complete calendar eligibility windows, with
labels purged before the following era; 2026 is development only.

Each primary statistic is the equal-week mean of cross-sectional Spearman
correlations. Both four- and eight-week circular block bootstraps use 20,000
empirical draws, seed 42, with shared timestamp indices across cells/lookbacks.
The worse centered-null p receives Bonferroni correction for all 112 tests.
Threshold .05/112 = **0.000446428571**; expected pointwise 5% false positives under
an all-null family = **5.6**. Ordinary percentile intervals are not simultaneous
bounds. There are no Gaussian statistics or synthetic profit/training observations.
Deterministic accounting-sized test fixtures never enter the research panel.

## Results

**106/112 corrected diagnostic passes; six corrected failures.** All 28 M/M
tests have raw p **1/20001 = 0.0000499975001**, adjusted p
**112/20001 = 0.005599720014**, and positive ordinary lower bounds at both blocks.
These are Monte Carlo floor p-values, not more precise tail probabilities.

| Lag / future horizon | Annual mean M/M correlation range | Smallest ordinary lower bound, either block | Passing eras |
| --- | ---: | ---: | ---: |
| 1w / 1w | 0.111051–0.171149 | 0.089524 | 7/7 |
| 1w / 4w | 0.167814–0.227355 | 0.140073 | 7/7 |
| 4w / 1w | 0.174860–0.236495 | 0.149073 | 7/7 |
| 4w / 4w | 0.216212–0.301565 | 0.167058 | 7/7 |

The six failures all use the midpoint signal and overallPrice label at lag 1w /
horizon 1w. They are 2020, 2021, 2023, 2024, 2025 and development 2026; their
adjusted p-values are 0.722364, 0.358382, 1, 1, 1 and 1 respectively. Positive
pointwise lower bounds in 2020/2021 do not rescue corrected failures. That cell
passes only in 2022. It therefore has no all-era consistency claim. Every other
cell passes all seven registered eras.

The mean weekly O/M lag-rank agreement ranges from 0.545982–0.736362 for the
one-week lag and 0.595995–0.819463 for the four-week lag across these matched
samples. The two fields carry materially different rankings. O/O here is a
matched-sample reference and does not replace the earlier screen's sample.

## Meaning and next lead

This rules out an explanation restricted to anomalies in overallPrice: reversal
also appears in the two side averages' midpoint, at the predeclared settings in
every development era. It does **not** rule out aggregate measurement error,
spread bounce, stale observations, source revisions or selection effects. Signal
and label still share the current price endpoint. None of these aggregate fields
identify a price or quantity our account can obtain. No GP expectation, buy-limit
capacity or achievable participation is estimated by a rank-correlation test.

No patient holding period, universe or execution policy was retuned. The prior
account-profit null/inconclusive results stand, including processing's adjusted
p=1. The direct economic lead remains genuine own-fill processing calibration.
If no actual records are available, the next distinct historical question is a
separately registered reversal diagnostic whose signal and future-return label
do not share a price endpoint (a fixed intervening complete week). This would
test persistence beyond immediate measurement reversal; it is not authorized as
a new profit claim by the present results.

## Execution and verification

From the repository root:

```bash
OSRS_DATA_DIR=/home/martin/osrs-data ml/.venv/bin/python -m osrs_ml.reversal_fields \
  --source /home/martin/osrs-data/ge-tracker-weekly-v1 \
  --output /home/martin/osrs-data/reversal-field-audit-v1 \
  --acknowledge-private-research
```

Real machine output:

```text
COMPLETE: 112/112 tests; 224 block tests; corrected diagnostic passes=106; holdout NOT read
```

Thirty new test cases cover exact horizons, paired item samples, retention of
outliers/inversions, causal scores, era boundaries, centered-null p-values,
correction, constant/missing weeks, full-family enumeration, worse-block selection,
source provenance, date rejection and output overwrite refusal. The initial test
run failed at collection because the implementation module did not exist. Full
verification from `ml/`, before the outcome run:

```text
221 passed in 33.69s
All checks passed!
```

A subsequent check rehashed source/manifest, protocol, statistical helpers and
outputs; recomputed every block test from saved weekly scores; checked all label
boundaries and family members; and independently reconstructed the first allowed
2020 cross-section for all four lag/horizon combinations through SQL endpoint
joins, comparing all 16 field correlations and matched counts:

```text
PASS: 112 family rows, 224 block tests and 5208 weekly rows; all inference and output hashes reconciled
PASS: 16 independent SQL field correlations match; all development label boundaries verified
PASS: 28/28 midpoint tests; 106/112 total corrected passes; 6 corrected failures retained; holdout_read=False
```

External artifact hashes:

| Artifact | SHA-256 |
| --- | --- |
| weekly-scores.parquet | `76fac31ff55afb1780646b158f7c995b5c2fe60fce80446e999d2f81195424dd` |
| summary.csv | `733e749e4293d3047622a919507a983689df904d4e493fe8b07fe241d585f494` |
| block-tests.csv | `9ab6ae499ce8508ca7b5d77262967c1907a83ef1b86a8b941a8b837352ae029b` |

The external manifest records all provenance hashes. `block-tests.csv` retains
every block's mean, lower/upper interval, raw/adjusted p, eligibility and counts;
`summary.csv` retains every era/cell's worse-block decision. The table below
reports every registered cell. Each cell is **mean correlation / adjusted p**;
its raw p equals adjusted p/112 unless adjusted p=1, for which exact raw values
are listed after the table. All p-values below use the worse block. Values are
rounded for display; files retain full precision.

## Every registered era and field cell

| Era | Lag / horizon | Weeks | O/O | O/M | M/O | M/M |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2020 | 1w / 1w | 52 | 0.154779 / 0.005600 | 0.109561 / 0.005600 | 0.025886 / 0.722364 | 0.158398 / 0.005600 |
| 2020 | 1w / 4w | 49 | 0.209134 / 0.005600 | 0.162781 / 0.005600 | 0.106166 / 0.005600 | 0.215259 / 0.005600 |
| 2020 | 4w / 1w | 52 | 0.218443 / 0.005600 | 0.174231 / 0.005600 | 0.118183 / 0.005600 | 0.223333 / 0.005600 |
| 2020 | 4w / 4w | 49 | 0.269855 / 0.005600 | 0.222047 / 0.005600 | 0.186520 / 0.005600 | 0.275143 / 0.005600 |
| 2021 | 1w / 1w | 51 | 0.161472 / 0.005600 | 0.087870 / 0.005600 | 0.019092 / 0.358382 | 0.171149 / 0.005600 |
| 2021 | 1w / 4w | 48 | 0.215110 / 0.005600 | 0.129566 / 0.005600 | 0.067464 / 0.005600 | 0.223196 / 0.005600 |
| 2021 | 4w / 1w | 51 | 0.225971 / 0.005600 | 0.138459 / 0.005600 | 0.076676 / 0.005600 | 0.232142 / 0.005600 |
| 2021 | 4w / 4w | 48 | 0.290011 / 0.005600 | 0.188378 / 0.005600 | 0.123803 / 0.005600 | 0.293068 / 0.005600 |
| 2022 | 1w / 1w | 51 | 0.163272 / 0.005600 | 0.084635 / 0.005600 | 0.014153 / 0.005600 | 0.166227 / 0.005600 |
| 2022 | 1w / 4w | 48 | 0.220099 / 0.005600 | 0.131389 / 0.005600 | 0.061893 / 0.005600 | 0.227355 / 0.005600 |
| 2022 | 4w / 1w | 51 | 0.228953 / 0.005600 | 0.139543 / 0.005600 | 0.071803 / 0.005600 | 0.236495 / 0.005600 |
| 2022 | 4w / 4w | 48 | 0.294819 / 0.005600 | 0.187904 / 0.005600 | 0.115540 / 0.005600 | 0.301565 / 0.005600 |
| 2023 | 1w / 1w | 51 | 0.141806 / 0.005600 | 0.072035 / 0.005600 | 0.001085 / 1.000000 | 0.147843 / 0.005600 |
| 2023 | 1w / 4w | 48 | 0.207392 / 0.005600 | 0.121409 / 0.005600 | 0.058514 / 0.005600 | 0.209472 / 0.005600 |
| 2023 | 4w / 1w | 51 | 0.216122 / 0.005600 | 0.131481 / 0.005600 | 0.069281 / 0.005600 | 0.221478 / 0.005600 |
| 2023 | 4w / 4w | 48 | 0.277905 / 0.005600 | 0.175135 / 0.005600 | 0.109216 / 0.005600 | 0.276210 / 0.005600 |
| 2024 | 1w / 1w | 51 | 0.136999 / 0.005600 | 0.068476 / 0.005600 | -0.004475 / 1.000000 | 0.142509 / 0.005600 |
| 2024 | 1w / 4w | 48 | 0.195120 / 0.005600 | 0.110342 / 0.005600 | 0.046486 / 0.005600 | 0.196755 / 0.005600 |
| 2024 | 4w / 1w | 51 | 0.201285 / 0.005600 | 0.124681 / 0.005600 | 0.056206 / 0.005600 | 0.211162 / 0.005600 |
| 2024 | 4w / 4w | 48 | 0.258201 / 0.005600 | 0.166024 / 0.005600 | 0.097999 / 0.005600 | 0.261070 / 0.005600 |
| 2025 | 1w / 1w | 51 | 0.124707 / 0.005600 | 0.065174 / 0.005600 | -0.004881 / 1.000000 | 0.127915 / 0.005600 |
| 2025 | 1w / 4w | 48 | 0.191054 / 0.005600 | 0.120008 / 0.005600 | 0.054036 / 0.005600 | 0.194074 / 0.005600 |
| 2025 | 4w / 1w | 51 | 0.193429 / 0.005600 | 0.123585 / 0.005600 | 0.058572 / 0.005600 | 0.197464 / 0.005600 |
| 2025 | 4w / 4w | 48 | 0.253613 / 0.005600 | 0.173696 / 0.005600 | 0.101775 / 0.005600 | 0.256558 / 0.005600 |
| 2026 | 1w / 1w | 29 | 0.109672 / 0.005600 | 0.066288 / 0.005600 | -0.006611 / 1.000000 | 0.111051 / 0.005600 |
| 2026 | 1w / 4w | 26 | 0.163539 / 0.005600 | 0.108824 / 0.005600 | 0.047563 / 0.005600 | 0.167814 / 0.005600 |
| 2026 | 4w / 1w | 29 | 0.168994 / 0.005600 | 0.115695 / 0.005600 | 0.058308 / 0.005600 | 0.174860 / 0.005600 |
| 2026 | 4w / 4w | 26 | 0.214721 / 0.005600 | 0.155380 / 0.005600 | 0.086413 / 0.005600 | 0.216212 / 0.005600 |

Exact worse-block raw/adjusted p for the six failures:

| Era | M/O, 1w / 1w raw p | Adjusted p |
| --- | ---: | ---: |
| 2020 | 0.006449677516 | 0.722363881806 |
| 2021 | 0.003199840008 | 0.358382080896 |
| 2023 | 0.361931903405 | 1.000000000000 |
| 2024 | 0.965651717414 | 1.000000000000 |
| 2025 | 0.852207389631 | 1.000000000000 |
| 2026 | 0.750012499375 | 1.000000000000 |
