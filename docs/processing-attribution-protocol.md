# Processing attribution audit — cycle 2 registration

Frozen before opening batch outcomes on 2026-10-29, starting at `9b6c549`.
The preceding battery already disclosed processing's 1% marked net +1,764,761 GP,
cash change +110,374 GP, terminal mark 1,654,387 GP, eight completed batches and
13,200 produced bows. These are selection context, not independent evidence.

The single task is an accounting and mechanism audit of the **unchanged** processing
rule at **all three original shares: 0.1%, 1%, 5%**. No new strategy, threshold,
hold, recipe, participation search, exclusion, fit or profit test is introduced.
Primary raw and Bonferroni-adjusted p-values stay those of the 213-test battery;
an attribution cannot rescue its failure. No significance is claimed for individual
batches, recipes, components or this selected diagnostic. No Gaussian inference
or synthetic training/profit data. Unit-test fixtures are accounting tests only.

## Fixed inputs and boundary

Use only `/home/martin/osrs-data/strategy-battery-v1`'s saved processing orders,
fills, equity, metrics and summaries, checking the completed run's registration,
protocol, executed-code, results and development-manifest hashes. Also check the
cycle-1 `audited-artifacts-sha256.json` hashes before reading scenario artifacts.
Use the existing daily source for exact decision and terminal references, with
DuckDB projecting **only** the five recipe IDs (66, 70, 855, 859, 1777), dates and
side price/volume fields, and predicates
`1777766700 <= available_at < 1785024300` **before materialization**. Check its
original hash. Do not open any reserved holdout file or use post-boundary prices.
Current metadata remains a sensitivity; no claim of historical buy-limit revisions.
All generated batch/item records stay outside Git under `OSRS_DATA_DIR`.

## Fixed reconstruction and reporting

Replay productions before fills at each timestamp. Group integer price lots by
opportunity for the account's weighted-cost consumption; do not treat rounded
lots as independent production batches. Inputs follow the original weighted
book-cost convention; both input legs must be owned before production, with
strictly earlier purchases. A batch is linked to the preceding matching submission;
output sales are assigned in production order and must occur in a subsequent
complete bucket. Unproduced submissions and partial input balances stay visible.
Require exact reconciliation to saved cash, realized P&L, production quantities,
completed batches, active time, terminal inventory and marked net. Refuse drift,
duplicate events, unowned inputs/sales, missing causal prices or output overwrites.

Report each share's submitted/produced/fully-sold batches, units, elapsed and active
hours, after-tax proceeds, realized production P&L, remaining inventory book cost,
terminal mark and **unrealized gain/loss = mark minus remaining book cost**.
Use these exact identities:

* `cash change = realized production P&L - remaining inventory book cost`;
* `net GP = realized production P&L + unrealized gain/loss`.

The gross terminal mark as a percentage of net profit is not the fraction of
profit due to appreciation. Also report realized GP per active hour (all production
time in the denominator, including unsold output) separately from marked GP/hour;
cash change is not interchangeable with realized profit.

For each produced batch, reconstruct the original decision's integer ceiling on
each input (high +10bps, rounded up) and conservative output quote (low -10bps,
rounded down, per-unit tax). On sold quantity, decompose realized P&L exactly into:

* decision conversion spread = sold units times (decision net output quote minus
  summed decision input ceilings);
* input cost movement = sold units times summed decision input ceilings minus
  consumed cost assigned to those sold units;
* output price movement = actual after-tax proceeds minus sold units times
  decision net output quote.

These components sum to realized production P&L. They are same-fill accounting
diagnostics, not executable counterfactual profits. Pooled leftover inputs may
have been acquired by earlier submissions; preserve that cost and report it.
List all batches externally with wait times, input costs, sales, margins and tax;
report aggregate profitable/losing batch counts and concentration without dropping
any batch. For every remaining item report units, book cost, mark and last source
age, classifying unconsumed inputs and unsold outputs separately. Reconcile all
timestamps' cash and equity, not just the final row.

## Decision

If identities fail, report an implementation failure explicitly; preserve original
battery results and do not tune a strategy. If they pass, use the decomposition
to decide whether processing remains a prospective own-fill measurement lead or
is predominantly inventory drift. The existing battery failure stays a failure
in either case. Aggregate historical bucket averages cannot verify attainable
purchase/sale prices, queue share, active throughput or executable expected profit.
Freeze a future own-fill study only after this audit identifies what needs measuring;
do not pretend that a prospective protocol or historical audit is new execution data.
