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

### Completion appended — conversion spread survives attribution, inference unchanged

Registered in `b53486f`; tested reconstruction committed in `433fa7c` before the
attribution run. All three original processing shares reconcile to saved metrics
and to every equity timestamp: **420 development source rows and 252 account
timestamps**. The [full validation](processing-attribution-validation.md) records
all shares, components, inventory accounting, waits, limitations and reproduction.
External artifacts are `/home/martin/osrs-data/processing-attribution-v1`.

**Numbers (0.1% / 1% / 5%):** net GP +1,053,603 / +1,764,761 / +1,764,761;
simulated realized GP +1,102,393 / +2,054,103 / +2,054,103; remaining input book
507,674 / 1,943,729 / 1,943,729; terminal mark 458,884 / 1,654,387 / 1,654,387;
**unrealized losses −48,790 / −289,342 / −289,342**. Cash changes remain
+594,719 / +110,374 / +110,374. Produced/fully-sold batches are 6/6, 8/8, 8/8
out of 11/16/16 submissions. All produced output sells; final inputs number
2,746 / 9,900 / 9,900. All batches are positive in the simulation; largest batch
is 25.51% / 16.25% / 16.25% of realized P&L. Shares are dependent sensitivities.

At 1%, realized +2,054,103 GP decomposes exactly into **+2,115,300 GP decision
conversion spread, −60,977 GP input movement, −220 GP output movement**. Production
requires eight modeled active hours, or 256,762.88 realized GP/active hour;
marked rate remains 220,595.13 GP/active hour and 885.92 GP/elapsed hour over
1,992 hours. Input/production waits are 72–120h, final output sales another 48h.
The 1% and 5% fill paths are identical. No new profit inference was performed;
all original raw/Bonferroni-adjusted **p=1.0** and activity failures remain intact.

**Explicit interpretation correction:** cycle 1 emphasized the 1,654,387 GP gross
inventory mark and small cash change. Those numbers were correct, but they must
not be read as evidence that inventory appreciation supplied the simulated profit.
The correct contribution is **mark less remaining book cost**, a loss of 289,342 GP
at 1%. Cash change is realized profit less purchases still in inventory. The saved
realized metric was independently reproduced, not newly created by this audit.

**Learned / ruled out / next lead:** terminal appreciation does not explain this
processing gain, and later output movement supplies essentially none of it. The
candidate mechanism is the original conversion spread. Stranded inputs reduce
profit and tie up cash; partial input costs can also be reused by later batches.
This strengthens processing's priority as a prospective **measurement** lead,
without turning a six/eight-completion corrected failure into a survivor. Next
pre-register own-fill calibration of the fixed mechanism, including both input
legs, failed submissions and stranded inventory, actual output tax, active time
and capital occupancy. Do not tune inventory netting or relax the activity gate
on these results. Attainable fills and expected executable profit remain unknown.

Procedural note: an exploratory schema/head read followed run-provenance checks
but preceded per-artifact hash verification. The subsequent 15 artifact hashes
all matched the cycle-1 audit. The committed executable enforces artifact checks
before scenario reads. No economic parameter or audit definition changed after
outcomes. The reserved holdout stayed sealed; no later market fields, training,
synthetic profit data, Gaussian inference or C++ changes were used.

The ten new accounting/integrity tests failed before implementation (missing
module), then passed. Full executed verification from `ml/`:

```text
162 passed in 32.29s
All checks passed!
PASS: 3 unchanged processing accounts attributed; original inference retained; holdout NOT read
PASS: 420 development source rows; 252 equity timestamps reconciled; all 10 output hashes verified; original adjusted p=1 for all three shares; holdout_read=False
```

The output summary SHA-256 is
`88b43dd698846691fcc23dba044c07d9069dbbd23158ff0327919885b9b33544`.

The original independent 213-scenario audit was also rerun after attribution:
passed, 23,537 fills, 22 productions, zero negative cash, capacity violations or
holdout rows, `holdout_read=false`. Existing battery artifacts remain unchanged.

## 2026-10-29 — cycle 3, own-fill measurement registered before intake

Starting revision: `796d92b`. Read the five requested records in order. The cycle-2
attribution identifies conversion spread, not inventory appreciation, as processing's
simulated gain. Historical patient and cross-item failures remain failures; another
historical replay would not identify our actual fills.

Highest-value work: freeze the [processing own-fill calibration protocol](processing-own-fill-protocol.md)
and implement an offline, immutable actual-event intake ledger with accounting,
evidence-integrity and completeness gates. No orders will be placed and no market
archive or reserved holdout will be read. Initialize an empty external study and
report missing observations honestly. The fixed 56-day calibration is descriptive;
it adds no alpha significance test and cannot rescue original adjusted p=1.
No synthetic data will enter that study; accounting test fixtures remain tests only.
Completion, executed verification and next lead will be appended below.

### Completion appended — actual-fill intake ready, actual evidence still absent

Registration committed in `1366d26`, durable intake/tests in `84bd183`, and actual
execution measurements/documentation in `fdde48d`. The [executed validation](processing-own-fill-validation.md)
records the machine output and limits. Built offline immutable SQLite intake for
operator decisions, submitted/rejected/cancelled orders, partial fills with actual
tax, owned-input production and daily cash/inventory/active-time checks. It
reconstructs weighted books, realized P&L, remaining inventory and capital-time
occupancy. Evidence integrity, duplicate identities, impossible accounting and
changed protocol/code fail closed. Envelope violations remain visible and block
readiness; they are not discarded to improve results. Late-recorded decisions
cannot count as durable pre-submission selection.

**Numbers:** enrolled `/home/martin/osrs-data/processing-own-fill-v1` at
2026-10-29 20:22:41 UTC. Its fixed 56-day window is 2026-10-30 through
2026-12-25 00:00 UTC, end exclusive. **0 actual events, 0 decisions, 0 sessions,
0 fills, 0 completed batches**. Status `awaiting_actual_records`, `ready=false`;
expected profit and new adjusted p are null/unidentified. The configured 10M GP
is an accounting allocation, not observed deployed funds. No import, order or
market-price read occurred. Historical processing raw/adjusted **p=1.0** remains
unchanged; no additional alpha test or Gaussian statistic was performed.

**Learned / ruled out:** a reproducible ledger now exists to measure attainable
conversion margins without dropping failed/partial attempts or equating residual
inventory marks with profit. Software readiness supplies no economic evidence.
The empty sample rules out any claim that this cycle independently confirmed
processing profit. Evidence hashes cannot authenticate supplied records, enforce
unrecorded activity coverage or prove causal recipe selection. The passing
readiness gate is accounting/coverage qualification only, not an edge verdict.

**Next lead:** genuine own-fill calibration of the unchanged two-recipe processing
mechanism. Import decisions before submissions and retain both legs, failed
orders, leftovers, actual output tax and all interaction time. Do not rebuild the
same intake or rerun failed rules as new evidence. If no actual records can be
obtained, expected executable processing profit remains unidentified; any distinct
development-only research hypothesis must be registered separately. A later
prospective profit trial must freeze its economic endpoint, sample adequacy,
empirical block-bootstrap and search-family correction before outcomes.

All 29 new intake/accounting test cases plus the original 162 tests pass. Tests
initially failed because the implementation module did not exist. Fixtures are
accounting examples only and were never imported into the external actual study.
Executed from `ml/`:

```text
191 passed in 32.62s
All checks passed!
PASS: frozen protocol/code hashes; 0 actual events; 56-day window; expected profit unidentified; holdout_read=False
```

Initial readiness report SHA-256:
`48c1cfc4cab6cfee3e31e15504b40435a01ff3c0baee63d75f2477d8dcf9451c`.
The reserved holdout remained sealed; no archive market rows, forward aggregate
prices, training, synthetic profit evidence or C++ changes were used.

## 2026-10-29 — cycle 4, reversal field audit registered before outcomes

Starting revision: `94fa346`. Read the five requested records in order. Processing
own-fill intake already exists and has no actual observations; rebuilding it or
replaying the failed battery would add no economic evidence. The source-price
reversal finding is still worth testing for measurement dependence: overallPrice
lies outside the side-average band in 15.50% of usable rows in the prior audit.

Highest-value feasible work: the [frozen field audit](reversal-field-audit-protocol.md),
comparing four overall/midpoint signal/label cells, both fixed lookbacks and
horizons, and seven development eras on matched item sets. There are 112 tests,
20,000 empirical block draws, two block lengths and Bonferroni correction. This
tests a measurement explanation, not expected profit; prior account failures and
the own-fill gate stand. No new trading rule, holdout read, synthetic profit
evidence or C++ change. Outcomes and executed checks will be appended later.
