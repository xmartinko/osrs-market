# Private deep-history and participation validation

The full-universe archive is collecting with eight concurrent workers, cached
responses and resumable exponential backoff. The previous artificial two-second
request interval has been removed. Actual collection encountered HTTP 429 with
server `Retry-After` values of 171 and 288 seconds. These are measured operational
backoffs, not a restriction invented from the terms. The frozen cached catalogue
contains **4,586 identifiers**, rather than the 4,523 in the preliminary estimate.
Archive coverage and cross-era conclusions remain pending until the sweep completes;
no partial item sample is being used to select a rule.

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
All uncertainty calculations above use empirical blocks; none uses Gaussian
samples. The weekly normality screens and any eligible Gaussian mean intervals
will be reported separately. The saved daily predictions include a history-length
feature; their reuse is a diagnostic of that frozen model, not certification of
the stricter six-feature date-invariant weekly model.

Verification so far:

```text
115 passed in 30.43s
All checks passed!
```

All original tests remain. Changes include concurrency, cache/backoff, exact-gap
horizons, causal features, date-translation invariance, tied ranking and inadequate
era tests. No C++ backend file was modified. Holdout stays sealed at Unix
`1785024300`; weekly rows require `timestamp + 604800 + 300 < holdout_start`.
