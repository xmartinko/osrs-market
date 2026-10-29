# Processing own-fill calibration v1 — cycle 3 registration

Frozen on 2026-10-29, starting from `796d92b`, before any own-order observations.
This is a measurement study of the selected processing mechanism, not a new
historical profit test or a rescued battery result. Historical processing has
six/eight/eight completions and raw/adjusted p=1 in the 213-test family. Its
+2,054,103 GP simulated realized planning-case profit motivates measurement;
it is not independent evidence of attainable execution.

## Scope and boundary

Build an offline, append-only intake ledger for operator-supplied actual orders,
fills, production and account checks. Initialize a study now; its 56-day recording
window starts at the next UTC midnight after enrollment. Do not place orders,
read market archives, evaluate forward price buckets, open the reserved holdout,
or treat later aggregate prices as a substitute evaluation set. No credentials
or account names belong in evidence. Data and evidence stay under
`OSRS_DATA_DIR=/home/martin/osrs-data`, outside Git. C++ is unchanged.

An empty study is an honest missing-data result. A program, screenshot hash or
protocol cannot prove that an order executed. Only operator-supplied actual
execution records can inform calibration. Hashes preserve supplied evidence;
they do not authenticate its origin or establish completeness of unrecorded acts.

## Fixed measurement envelope

Retain both original recipes: 70 + 1777 -> 859 (magic longbow) and
66 + 1777 -> 855 (yew longbow). No recipe selection using future outcomes.
Use a dedicated initially empty inventory and 10M GP research account allocation,
eight GE slots, at most one unfinished batch, 1M GP purchased inputs per batch,
1,650 produced units per UTC day, and at most 3,600 recorded active seconds/day.
Record all interaction time, including price checks, failed submissions, purchasing,
production, cancellations and sales. These caps describe the study; actual
violations must remain visible and disqualify readiness rather than be deleted.
Skill eligibility and current mechanics need operator verification before trading.
This code does not authorize or automate trading.

At the first available daily operator session, record either a no-attempt decision
with a reason or one planned batch. Missing sessions remain missing, never zero
profit. Capture both input price ceilings, output reference price, observed
buy limits and timestamped original evidence before submission. Choose the
positive conservative conversion margin/capital leader across the two original
recipes, stable output-ID ties; no positive candidate means no attempt. Price
references and subsequent moves remain in evidence, not invented fills.
Purchase each input separately at its frozen ceiling for at most 72h. Never
substitute another recipe after a failed order. Produce only owned matched
inputs; record partials and leftovers. Output orders and sales require actual
production. Amendments cancel an old order and submit a new ID, retaining both.
A rejected or cancelled order is retained even when no fill occurs. Active
production throughput, achievable prices, tax and delays are measured, not assumed.
Liquidate outstanding inventory only through recorded actual trades; otherwise
report remaining units/book cost, with executable liquidation value unidentified.

## Durable intake contract

Enrollment freezes protocol and implementation SHA-256 hashes, the exact recipe
map, dates and envelope in SQLite. Updates/deletes are blocked. The CLI never
creates or opens an existing ledger through an implicit schema initialization.
Every import is atomic, chronologically ordered, duplicate-resistant and verified
by replaying the full ledger. Changed protocol/code or changed evidence fails
closed. The study cannot be backdated or reused after an implementation change.
Corrections require a separately versioned study; existing records are preserved.

Each JSONL event has `id`, `kind`, integer Unix `at`, `source="operator_actual"`,
`evidence` (a relative file under the study directory), `evidence_sha256`, and a
`data` object. Evidence paths may not escape that directory or point to the ledger.
Imports require `at` in the enrolled window and no later than import time.
Kinds and data fields are fixed:

* `decision`: `batch_id`, `output_id`, `quantity`, `input_ceilings` (string item IDs),
  `buy_limits` (string item IDs), `output_reference_gp`. A no-attempt decision uses
  quantity zero and includes `reason`. One decision per UTC day, including busy days.
* `submit`: `order_id`, `batch_id`, `item_id`, `side`, `quantity`, `price_gp`.
* `reject`, `cancel`, `close`: `order_id`, `reason`. Close requires fully filled;
  cancel/reject retain partials (reject must have no fills).
* `fill`: `order_id`, `quantity`, `price_gp`, `tax_gp` (actual total, never inferred).
* `produce`: `batch_id`, `quantity`; consumes both owned input legs at weighted
  book cost and creates the selected output. Input inventory is pooled across
  attempts, keeping earlier leftover costs visible.
* `session`: `active_seconds`, `cash_gp`, `inventory` (string item IDs to units).
  At most one daily aggregate session, recorded after that day's interactions;
  checks exact cash/inventory against the replay. A zero-active session is valid.

All quantities, GP and times use integers; booleans/floats are rejected. Fills
must follow a live submitted order, obey its price and remaining quantity, and
use positive whole-GP prices. Taxes must be between zero and sale notional;
buys have zero tax. No sale or production of unowned inventory; no negative
cash; no deposits, withdrawals or unrecorded external inventory. Impossible
accounting rejects the entire import. Envelope deviations (slots, batch budget,
active time, buy limits, production rate, expiry, overlapping batches) stay in
accepted data and explicitly block readiness. Actual tax is reported as supplied,
not silently replaced by a counterfactual policy. Source evidence is checked
again at report time. Empty, incomplete and open-order accounts remain visible.

## Fixed report and interpretation

Report all decisions, attempted batches, submissions/rejections/cancellations,
buy/sell fills and units, matched production, completely sold batches, tax, active
time, cash change, realized P&L, remaining input/output units and weighted book
cost. Require `cash change = realized P&L - remaining book cost`. Report maximum
open slots, peak book capital, capital-time integral, and each order's requested
and filled units/timing. No synthetic terminal price or simulated tax.
No marked profit or calibrated participation estimate without observations.

The 56-day endpoint is fixed; interim reports are collection diagnostics only.
Readiness requires the window to end, all 56 decisions and session checks, at
least ten fully produced-and-sold batches, both buy and sell activity, no open
orders, no residual inventory and no envelope deviations. Insufficient activity
is inconclusive, never evidence of zero expected profit. A clean negative result
remains in the record. Passing readiness means a complete calibration sample,
not a deployable edge or independent forecast validation.

All GP, delays, fill fractions and rates in this calibration are **descriptive**.
No per-batch/recipe p-values, Gaussian intervals or significance claims. The old
battery's adjusted p=1 remains unchanged. A separate prospective economic trial
must freeze policy, adequate temporal sample, empirical block-bootstrap lengths,
search-family correction including the selection history, and a primary after-cost
endpoint before its observations. Calibration cannot itself establish positive
expected profit. Do not tune a failing strategy to these calibration outcomes.
