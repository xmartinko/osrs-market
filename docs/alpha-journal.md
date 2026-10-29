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

### Completion appended — midpoint reversal persists; account-profit verdict unchanged

Registration `5aa7195` and implementation/tests `0ef050d` preceded execution.
The [full validation](reversal-field-audit-validation.md) reports every one of the
112 era/cell tests, including six corrected failures. External artifacts remain
in `/home/martin/osrs-data/reversal-field-audit-v1`: 5,208 weekly score rows,
112 summaries and 224 block tests. All 112 have complete calendar correlations
and meet the frozen coverage gate. The sealed source has 1,803,631 rows, maximum
availability 1784765100 < 1785024300; every cross-section has >=2,446 matched items.

**Numbers:** all **28/28 midpoint-signal/midpoint-label** tests pass the finite
112-test correction, across both lag lengths, both horizons and all seven eras.
Annual mean rank correlations for lag/horizon 1w/1w, 1w/4w, 4w/1w and 4w/4w
are respectively **0.111051–0.171149, 0.167814–0.227355, 0.174860–0.236495 and
0.216212–0.301565**. Their smallest ordinary lower bounds across eras/blocks
are 0.089524, 0.140073, 0.149073 and 0.167058. Each has worse-block raw
**p=1/20001=0.0000499975001**, adjusted **p=112/20001=0.005599720014**.
These are Monte Carlo floor p-values, not more precise tail estimates. The
familywise raw threshold is .05/112=0.000446428571; all-null expected pointwise
5% false positives are 5.6. No Gaussian statistics were used.

Across all cells there are **106/112 diagnostic passes**. The six failures all
use midpoint signal / overallPrice label, one-week lag / one-week horizon:
2020/2021/2023/2024/2025/development-2026 adjusted p=0.722364/0.358382/1/1/1/1.
Only 2022 passes in that cell; it has no all-era consistency claim. Other cells
pass all seven eras. Positive pointwise bounds in 2020/2021 do not rescue their
failures. No row, outlier, inversion or failed era was removed or retuned.

**Learned / ruled out:** reversal is not confined to anomalous overallPrice
observations; the midpoint of side averages also carries a repeatable rank
relationship on these matched development samples. This does not rule out
aggregate measurement error, spread bounce, stale observations or selection.
Signal and label still share the current endpoint. No account was simulated,
no GP expectation was estimated and no capacity/participation claim is added.
The original battery remains **zero corrected profit survivors**; original
processing adjusted p=1 and the actual-fill measurement gate remain unchanged.

**Next lead:** genuine processing own-fill observations remain the direct
economic gate. Without actual records, the next distinct development question
is a separately registered, fixed-gap reversal diagnostic whose future-return
label begins after an intervening complete week and shares no signal endpoint.
This could distinguish persistent structure from immediate measurement reversal;
it must not be turned into a tuned rescue of the failed patient accounts.

The 30 new test cases initially failed because the implementation module did
not exist; all original 191 plus the new 30 now pass. Full machine output from
`ml/` before the outcome run:

```text
221 passed in 33.69s
All checks passed!
```

Independent post-run checking rehashed all provenance and outputs, recomputed
each bootstrap result, checked every era boundary/family member, and reconstructed
16 field correlations through separate SQL endpoint joins:

```text
COMPLETE: 112/112 tests; 224 block tests; corrected diagnostic passes=106; holdout NOT read
PASS: 112 family rows, 224 block tests and 5208 weekly rows; all inference and output hashes reconciled
PASS: 16 independent SQL field correlations match; all development label boundaries verified
PASS: 28/28 midpoint tests; 106/112 total corrected passes; 6 corrected failures retained; holdout_read=False
```

Summary SHA-256:
`733e749e4293d3047622a919507a983689df904d4e493fe8b07fe241d585f494`.
The holdout stayed sealed. No training, synthetic market/profit data, actual-order
submission or C++ change occurred. The correction covers this finite diagnostic,
not the prior research search; persistence is not confirmation of deployable alpha.

## 2026-10-29 — cycle 5, fixed-gap reversal registered before outcomes

Starting revision: `f1a3e1a`. Read the five requested records in order. Cycle 4
established midpoint reversal with a shared signal/label endpoint. The actual-fill
intake is already built and no actual records have been supplied this cycle.
Highest-value feasible work is the [fixed-gap diagnostic](reversal-gap-protocol.md):
midpoint signal, one intervening source bucket, disjoint future endpoints, fixed
1/4-week lookbacks and horizons across all seven development eras. Exactly 28 new
tests, 20,000 empirical block draws, blocks 4/8, with a conservative 140-test
Bonferroni multiplier reserving the prior 112 field comparisons too.

This is a source measurement diagnostic, not a retuned patient strategy, account
profit test or independent confirmation. No holdout access, synthetic market data,
Gaussian inference or C++ change. Register and commit before outcomes; completion,
all corrected failures and executed verification will be appended below.

## 2026-10-30 — mechanical account ceilings and fixed-recipe catalogue

Starting revision `0a3fb26`. Forecast sweeps stay closed. Registered the
[capacity sensitivity](mechanical-ceiling-protocol.md) in `3c5c1a5`, committed
implementation in `c97a250`, then ran development daily means only. The four
prospective hypotheses remain frozen and **were not run as accounts on averages**.
The [full report](mechanical-ceiling.md) gives every frozen candidate, every new
catalogue member, visible arithmetic, capital/limits/slots and assumptions.
Generated data/logs remain under `/home/martin/osrs-data/mechanical-ceiling-v2`.
The earlier v 1 is retained, with [source corrections](mechanical-ceiling-amendment.md):
saw seller-tax exemption, lower walking sawmill rates and inventory-aware
ordinary-furnace rates. No favourable recipe or era was selected out of the scan.

**Measured facts:** provenance-checked 341,047 rows, 84 development timestamps,
maximum availability 1784937900 < sealed 1785024300. The original alchemy sums
reproduce exactly: low-side 24,622 positive rows / 11,398,956 one-unit GP;
high-side 13,915 / 3,422,903. The latter is the 179-GP-median **alchemy** screen,
not bow recipes. Strict all-leg noninversion leaves 75 valid magic/76 yew bow
days (all positive); excluded days remain zero-production in 84-day income
calculations. No market observations, quotes or fills were synthesized.

**Assumptions, not findings:** 10 M account; <=1 M paid input/fee reservation;
one unfinished batch; eight member slots; one daily active hour including
5–15 minutes of daily checks/setup. Two-click alching at 600–1,200 casts/hour
requires 1,200–2,400 clicks/hour, against the documented 1,200-cast maximum.
Nature costs use observed high means plus the same adverse ceiling as before;
fire staff costs 1,500 once. A 4 h buy limit starts at first purchase; six full
allowances/day is only a theoretical bound, never six observed fills. Fixed
candidate limits 10 k/18 k and nature 18 k exceed the modeled quantities. Sale legs
pay actual-rule integer 2% seller tax (saw exempt); alchemy/purchases pay none.
H4 adds casting and stringing times. The report labels retention 25–100%,
participation 0–1%, matched completion 0–100% and cycle delays as assumptions.

Conditional stand-alone daily endpoints below combine the registered cautious
and optimistic assumptions. Every numeric column after the candidate name is
**assumption-driven arithmetic on measured daily averages**, not account profit,
a confidence interval, a queue model, or a prospective hypothesis result.

| Candidate | Assumed completed units/real day | Conditional GP/active hour | Conditional GP/real day |
| --- | ---: | ---: | ---: |
| Direct yew | 106.7–1,100.0 | 6,614–117,687 | 2,830–117,687 |
| Direct magic | 110.7–754.0 | 14,327–242,082 | 6,224–172,289 |
| Direct rune tips | 111.9–1,100.0 | 13,866–237,914 | 6,053–237,914 |
| Direct dragon tips | 87.2–1,041.5 | 13,626–261,911 | 5,387–249,151 |
| String magic/sell | 117.7–868.5 | 9,243–173,049 | 3,217–97,916 |
| String yew/sell | 104.9–1,492.9 | 12,214–261,446 | 4,122–238,621 |
| String magic/alch | 67.0–589.3 | 15,182–247,358 | 6,337–223,064 |

Staff is expensed once separately, not every day: direct dragon endpoints become
13,581–261,893 GP/active hour and 5,369–249,133 GP/day across these 84 days.
Rows cannot be added: they reuse one account, time, cash, slots and nature supply.
The frozen four-arm rotation further limits each arm's assigned opportunities.
No actual positive executable lower bound is established; zero fills means zero
conversion profit, and partial-leg inventory can lose money.

**Visible small-ceiling stress:** combine cautious dragon matching with a .25/day
cycle rate (72 h offers plus daily-check delay): 21.80 items/day;
GP/day=.25×5,386.66964=1,346.66741; hours/day=.25+.25×(.39531746−.25)=.28632937;
GP/active hour=**4,703.21** (about 4,641 after first staff). At the frozen 100 k/hour
time hurdle this is **−27,286 GP/day** before staff. This is a labelled joint
sensitivity, not a newly measured slow-fill result. The daily-batch reference
falls from 215,229 to 54,042 GP/hour when retaining only 25% of the gap, versus
129,145 when slowing 1,000->600 casts/hour. Zero competition allocation or
completion gives zero GP while daily checks still take time. **Matching fills
at retained margins, plus capital-release delay, dominate uncertainty.**

**135,700 is not a portfolio or a ceiling.** Its exact 135,701.86 GP/day is a sum
of one unit of each positive low-side item-day, without volume weights. Direct
dragon's one-unit contribution is 251.61 GP/day, 0.1854% of that sum; all four
fixed direct items contribute 0.6146%. Repeated dragon units give a conditional
3.97%–183.60% ratio to that one-unit denominator (0.99% under slow-cycle stress),
which is **not an attainable share of a market profit pool**. An account can
repeat liquid units, so that denominator is not even a valid market upper bound.
The honest executable pool/share remains unidentified. Do not multiply the
327-GP marginal median by the 26-unit marginal median and call it an account.

**Other mechanics, bounded catalogue:** measured all eight standard tanning
recipes, four basic planks, four grinding conversions, seven deterministic bars,
a gold-bar/bracelet/alch chain, all five fixed-price sawmill shop goods, and four
mutually exclusive Zaff diary quotas. The report retains every member's positive
frequency, negative/zero gaps, size and conditional capacity. Examples across
families: snake tanning 0/58 and 0/9 positive; gold ore smelting 0/84; cloth 0/84;
bronze nails 0/74; teak planks 84/84 with 205.5-GP median and assumed 81.7–916.0
units/day; blue tanning 68/68 with 242-GP median and assumed 13.9–408.0 units/day.
Their optimistic ceilings require output sales, which remain unmeasured.
Gold bracelet/alch is 84/84 positive but caps near 47.6 k GP/hour optimistic.
All four grinding methods have optimistic daily GP below 6.6 k after capacity.

Shop saws illustrate the capacity trap: measured 210.5-GP median gap, but assumed
1% output participation allows only 2.14 units/day, 434.68 GP/day and
**5,053.70 GP/active hour** even optimistic. Steel nails reach only 17.4 k/hour
optimistic; iron nails 989/hour. Zaff's fixed 7,000 GP barrel has a real 15/30/60/120
daily quota, not unlimited supply: conditional optimistic daily profits are
4,401/8,802/17,604/35,209 GP, respectively. Current diary access is assumed;
its acquisition has not been charged as free. No normal-shop first-unit price,
world hopping, replenishment, recipe bonus, uncosted teleport or spell discount
was extrapolated. These shop/small-processing cases do not merit a dedicated
account's time under the frozen 100 k/hour hurdle.

**Verification:** independent scalar reconstruction checks all source-valid
calendars, all 80 side/recipe gap screens, 56,639 daily capacity rows and 760
summaries; protocol/amendment/code/source/output hashes reconcile. Real output:

```text
ORIGINAL SCREEN RECONCILED
      positive  unit_gap_sum
side
high     13915       3422903
low      24622      11398956
PASS: 341047 development rows; 84 calendar days; 40 recipes; 760 sensitivity rows; capacity/cash/time/limit assertions passed; profit_tests=0; holdout_read=False
PASS: 56639 scalar source reconciliations; 760 sensitivity summaries; all output/code/protocol hashes; capital, slots, tax, limits and time; holdout_read=False
245 passed in 38.19s
All checks passed!
```

Run manifest SHA-256:
`bacc58ed9eead4adb50d94831d66adfa03cc24653d44f509476c7c8a40ed0667`.
No statistical inference was performed, so no Gaussian assumption, bootstrap
confidence interval or new significance claim is made. These sensitivity
endpoints do not change the failed original 213 tests or prospective 217 family.
Holdout stayed sealed; no C++ change, forecast sweep or actual-order submission.

**Decision:** direct alchemy still deserves at most a small actual-fill/time
calibration because fixed output removes sale risk. The strongest liquid direct
ceiling example spans roughly**5 k–262 k GP/active hour**, including plausible
slow-cycle stress, and roughly**1.3 k–249 k GP/real day** before one-time staff.
That broad range is dominated by unmeasured fills at retained margins. It is
**not worth dedicating an account to yet**; the cautious case is too small for
the account's active time. Further work should obtain actual records, not tune
this range or reopen forecast sweeps.
