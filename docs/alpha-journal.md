# Alpha research journal

Append-only continuation record. Raw data, item statistics and account ledgers
remain under `OSRS_DATA_DIR=/home/martin/osrs-data`; the reserved holdout stays sealed.

## 2026-10-29 — cycle 1, completion audit registered before reading outcomes

Starting revision: `0023d27`. No earlier journal existed. Read the battery protocol,
71-rule/213-scenario registration, deep-history validation and next-steps assessment
in the requested order. Prior evidence supports a provider-price reversal structure,
but not an executable account edge. The battery was already partly executed and an
untracked independent audit implementation was present; its manifest still said
`running`. No new hypothesis, threshold, participation share or exclusion is added.

Highest-value work this cycle: finish the exact frozen battery, audit its provenance,
accounting, buy limits, slots, bucket participation and marks, and publish every
registered result. Resume refuses changed protocol/code/input hashes. Inference
retains 20,000 empirical circular block draws, seed 42, the worse of both registered
block lengths, activity/coverage gates and Bonferroni family size 213. Corrected
failures remain failures. Any discovered implementation defect will be documented
explicitly, without tuning the economic rules. An audit pass cannot establish
actual queue allocation or historically observed buy limits.

Completion, executed numbers, verification and next lead will be appended below.

### Completion appended — unchanged battery, zero corrected survivors

Resumed the original external run to completion: **213/213 scenarios**, comprising
98 adequate tests, 58 inconclusive and 57 unidentified. Both intraday resolutions
have no pre-holdout evaluation buckets; all 54 corresponding scenarios remain
unidentified, alongside three shop scenarios. No rule was retuned or omitted.
The [complete validation](strategy-battery-validation.md) reports all 71 rules at
1% plus the two other registered shares and annual diagnostics. Original and
augmented 213-row CSVs, 696 annual rows, 330 block-test rows, ledgers and artifact
hashes remain in `/home/martin/osrs-data/strategy-battery-v1`.

**Numbers:** all adjusted p=1.0. Best raw GP is weekly limit-aware spread at 5%:
+29,900,843 GP, 50 completions, raw p=0.439828, corrected p=1.0, block interval
[−402,725,397, +461,693,757] GP and 96.96% drawdown. Smallest raw p is daily low-tax
spread at 1%: +5,022 GP, 13 completions, raw p=0.012899355, corrected p=1.0.
The registered familywise raw threshold is 0.000234741784. Pointwise intervals
do not override the finite-search correction or activity gate.

Patient daily 3/7/14/28-day holds at 1% return +537 / +137 / +134 / −162 GP,
with 2 / 1 / 1 / 2 completions: inconclusive. Patient weekly 1/2/4/8-week holds
at 1% return −386,735 / −1,786,743 / +1,334,901 / −79,835 GP, with 25 / 26 / 16 /
16 completions: no corrected support. Weekly cross-item planning cases lose.
This rules out treating these registered simulations as an established executable
edge; it does not refute the earlier provider-price rank-reversal diagnostic or
establish absence of all possible market edges.

Processing at 1% returns +1,764,761 GP, ordinary interval [+511,006, +3,001,436],
but only eight completed production batches, so raw/adjusted p=1.0. Cash P&L is
+110,374 GP; 1,654,387 GP is marked inventory. Production is 13,200 bows across
eight active hours, 220,595 GP/active hour versus 885.92 GP/elapsed hour. Alchemy's
+24,073 GP has zero casts/coin realizations and −246,853 cash P&L: only inventory
appreciation, not alchemy profit. Neither result may be promoted as a survivor.

**Learned / next lead:** the tested low-turnover formulation does not resolve the
account-profit uncertainty. Do not search holding periods or remove source spikes
until a positive emerges. Processing supplies a concrete next measurement target:
inspect its eight matched-input batches and partial-leg inventory, then pre-register
a distinct prospective own-fill calibration of prices, tax and active time. More
activity and actual execution observations are needed, not a relaxed ten-completion
gate. The reserved holdout remains sealed. There was no training, synthetic profit
evidence, Gaussian inference or C++ change.

Audit implementation/integrity tests were committed in `005324b` and `89717d2`.
The audit rejects incomplete/duplicated families, changed registration/protocol/
code/data, source-reference or lot-price errors, incorrect cash, unowned production
inputs and changed terminal marks. The whole frozen run passed independently:

```text
COMPLETE 213 tests; corrected survivors=0; holdout NOT read
{
  "status": "passed",
  "scenarios": 213,
  "unavailable": 57,
  "fills": 23537,
  "productions": 22,
  "negative_cash": 0,
  "capacity_violations": 0,
  "holdout_rows": 0,
  "holdout_read": false
}
```

Executed from `ml/`: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`:

```text
........................................................................ [ 47%]
........................................................................ [ 94%]
........                                                                 [100%]
152 passed in 31.18s
All checks passed!
```

Original `results.csv` SHA-256:
`b7ae4f903d605dd92046af93034f38ea4607758ce9c61f8296e769939db11ad0`.
No claim is made that the audit calibrates actual fills, historical metadata or
liquidation. Its pass validates the stated conditional accounting model.

Final executed aggregate consistency check:

```text
PASS: 213 aggregate rows match frozen results; 156 annual sums reproduce net GP; all 71 rules reported; zero corrected survivors; holdout_read=False
```

## 2026-10-29 — cycle 2, processing attribution registered before batch inspection

Starting revision: `9b6c549`. Read the five requested records in order. The completed
battery and prior patient/null results are retained; rerunning those rules would
not add evidence. Highest-value next work is the processing measurement lead:
reconstruct every submitted/produced/sold batch and remaining input at all three
original participation shares. The [frozen attribution protocol](processing-attribution-protocol.md)
defines cost allocation, decision-margin/input-movement/output-movement identities,
source predicates, integrity checks and the descriptive-only interpretation before
opening detailed outcomes. Existing raw/adjusted p-values remain unchanged.

The audit will distinguish cash change, realized production P&L and **mark less
remaining book cost**. Gross terminal inventory value alone does not measure the
contribution of appreciation to net profit. No new strategy or parameter search,
holdout access, synthetic profit evidence or C++ change is authorized by this audit.
Completion and executed verification will be appended below.
