# Participation bounds: reasoning and frozen development experiment

Written against `ce0b499`, before implementation or new outcome inspection.
This protocol does not authorize holdout access, fitting, tuning or model selection.
All market results in this phase are `current_limits_sensitivity`.

## Verdict on the reframing

The essential observation is sound: reported low-side instant sells have a buyer,
and high-side instant buys have a seller. Passive execution is real. The leap from
that fact to availability for our particular order remains conditional. The Wiki
sample is reported transactions, not every exchange transaction, an order book,
or a history of our queue position. Reported volume is a useful denominator, not
proof of our attainable share or an upper bound on total exchange volume.

The [Wiki API description](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices)
defines aggregate price/volume endpoints. The [exchange description](https://oldschool.runescape.wiki/w/Grand_Exchange)
says internals are not fully public and older equal-price offers are loosely
prioritized. It does not justify assuming a strict known FIFO algorithm. The
[limit description](https://oldschool.runescape.wiki/w/Buying_limit) starts the
four-hour timer at the first purchase. These are the semantics being modeled,
not independently verified per-trade records. The API documentation page was
blocked to the web reader during this phase; no additional rounding guarantee
was established from it.

A mean of 100 can describe trades at 90 and 110 without a single trade at 100.
An average below our buy bid establishes some compatible units (subject to rounding),
not that every unit traded below it. The same problem applies to sell asks. A
single large execution can supply all reported volume: a deterministic 1% share
of it is a fractional allocation assumption, not a 1% chance of a real fill.
Being exactly at a rounded average supplies particularly weak price evidence.
Even trading inside the observed price range does not establish priority at the
instant of the trade. Better-priced competing offers may take all flow.

## Bounds, conditions and price qualification

Let N be reported side volume; Q remaining order units; L remaining account/item
buy allowance; and p the assumed captured share. For a bucket wholly inside an
order's live period, hypothetical buys are at most min(Q, L, floor(p C)); sales
at most min(Q, floor(p C)). C is a price-compatible volume capacity. Never reuse
volume across lifecycles or carry fractional capacity into another bucket. Partial
fills retain inventory and reservation; canceled unfilled units release cash.

There are two distinct capacities in this experiment:

* `mean_proxy`: C=N only when the low-side average is no greater than our frozen
  minimum buy-lot price, or the high-side average is no less than our frozen
  maximum sale-lot price. Otherwise C=0. This is a conditional scenario using a
  common proxy. It is **not** an identified upper bound: incompatible averages
  can hide compatible trades, and qualifying averages can hide incompatible units.
* `moment_upper`: a deliberately loose price-compatible unit upper envelope.
  Assume positive integer trade prices and true mean within the reported integer
  mean m plus/minus 1 GP, inclusively. Thus total consideration S lies between
  N max(1,m-1) and N(m+1). For buy threshold B, capacity is N if the lower S is
  at most NB, otherwise at most N-1 (one arbitrarily high trade can explain the
  mean). For sale threshold A>1, capacity is at most
  min(N, floor((N(m+1)-N)/(A-1))); for A=1 it is N. These are necessary-condition
  upper bounds, not identified counts. The one-GP rounding envelope is an explicit
  data assumption; errors outside it invalidate the refinement. The unrefined
  bound N remains valid regardless of averaging details. A bucket containing a
  known compatible trade would have ceiling N, but this dataset cannot generally
  identify such buckets or their compatible-unit totals.

Actual own fills have rigorous lower bound zero, even if compatible volume is
positive. The upper envelope assumes we jump ahead of every competitor, remain
live, and can capture every compatible unit without changing the market. At
100% it is useful as a capacity ceiling, and usually fantasy as an execution
forecast. It is not a P&L upper bound: more fills can cause more losses or consume
slots that would otherwise earn money. Similarly zero fills is not a lower P&L
bound. The reported profit ranges are scenario ranges, not confidence intervals
or bounds on all possible fill histories.

A planning central case is 1% of `mean_proxy` volume on each side. This encodes
persistent priority sufficient to receive one unit per hundred reported units,
with competing participants receiving the remainder. It is defensible as a
transparent sensitivity coordinate, **not** as an empirically defensible estimate.
There is no data-supported positive central share. A cautious operational case
is 0.1%; the identified conservative fill lower bound remains 0%. Multiple traders
cannot each receive 100%: these are single-account counterfactuals, not additive
capacity. No extra queue multiplier is applied; p includes queue competition.

Orders freeze prices when submitted. They cannot choose future bucket prices.
The integer_lots_v2 target is frozen too; adjacent integer lots retain corrected
notional-cost arithmetic rather than charging a whole tick per unit. Qualification
uses the least permissive lot edge (minimum buy price / maximum sell price).
This is a hypothetical adjacent-price allocation, not proof that an exact posted
order gets those fills. No free future-average price improvement is granted.
Sales freeze from the latest available high side when the existing lifecycle
submits its exit; invalid/missing prices delay submission. They remain open
until filled or evaluation ends. No within-bucket amendment or cancel/replace is
invented. Queue share is held constant while each order is live, without claiming
priority improves with age. A real cancellation/replacement loses any old priority.

A bucket must start after submission plus latency and finish before buy expiry;
no time-proportional allocation of an overlapping bucket is knowable. The executor
records fills when completed observations become available, so observed purchase
time starts the four-hour counter. At most one remaining buy limit is consumed
per bucket, never six allowances inferred from a daily bucket. This deliberately
underuses possible daily capacity; the true intraday fill times and limit resets
are unidentified. Existing expiry processing may discard a bucket ending at the
expiry boundary before processing it; retain that conservative convention and
record it. Holding and exits use observed fill availability times. These delays
are conservative timing conventions, not reconstructed trade timestamps.

## What the data cannot settle

Queue depth, cancellations, opponent identities, hidden prices, print sizes and
within-bucket arrival times are absent. Reported volume may be concentrated at
prices far from the mean. Our fills can be concentrated just before adverse price
moves, even when the unconditional average subsequently looks favorable. Replaying
future bucket marks captures subsequent aggregate changes but not selection of
our particular fills within the bucket. A constant p does not solve this adverse
selection problem. Our presence can alter prices and who trades. Shared buy-limit
groups are not represented in the existing metadata; per-item enforcement can
therefore overstate account capacity. Current limits joined backward remain
lookahead. No backend change is needed for this sensitivity; prospective own-order
submission/amendment/cancellation/partial-fill records are the missing evidence.

## Decision metric

For each frozen model, fold, preset and qualification rule, define P(p) as final
cash plus after-tax marked inventory minus the starting 10M GP, after simulated
buy limits, slots, integer price costs and tax. No-trade has P=0. Break-even means
**strictly P(p)>0 with actual buys and sales**, not a zero-trade tie or a profitable
inventory-only mark. Report smallest profitable tested share and the neighboring
sampled nonpositive share; also show every observed sign reversal. If profitability
later reverses, there is no single monotone threshold. No interpolation, binary
search or claim about untested shares is allowed. At 1%, the operator must obtain
about one of every hundred qualifying reported units on both sides, while keeping
these prices, waits and costs. That is the plain-language hurdle to calibrate.
The realized/cash P&L and terminal marks must accompany small equity profits.

The undecidable participation region is the interval between adjacent sampled
signs, plus every uncalibrated share in practice. Zero participation is a vacuous
no-trade outcome. A first profitable 0.1% observation says only that the threshold
could lie in (0,0.1%]; it does not establish profitability arbitrarily close to zero.
If no tested share wins, say none through 100% on this grid, not a proof that no
intermediate share could win. Model ranks and comparison with no-trade are reported
at every share; no winning parameter or model is selected from these outcomes.

## Frozen experiment (before execution)

* Development folds 0, 1, 2 from `ml/runs/phase2-real-v1/run.json`; enumerate only
  their saved prediction paths. Read panel with fold predicates strictly before
  the recorded holdout start. No training/features/holdout files or access markers.
  Verify panel, config, manifest, lock and prediction hashes, coverage and fold purge.
* Read `/home/martin/osrs-data/assembled-v3/daily.parquet` using
  `OSRS_DATA_DIR=/home/martin/osrs-data`. Keep all generated artifacts outside Git.
* New fill policy `volume_bounded_v3`; preserve existing `bucket_proxy_v1` default
  and both old price models. v3 requires `integer_lots_v2`, passive pricing and
  queue multiplier 10000. Zero participation is allowed only for v3.
* Both `mean_proxy` and `moment_upper`, each at fixed shares
  **0%, 0.1%, 0.5%, 1%, 2%, 5%, 20%, 50%, 100%**. No outcome-adaptive refinements.
* All five frozen score sets: `no_trade`, `no_change`, `raw_spread`, `spread_volume`,
  `catboost`. Same rankings and score admission threshold as the frozen run.
* All three cost/time presets from daily-v1: optimistic (0 bps, 0 haircut),
  moderate (10 bps, 1% haircut), conservative (30 bps, 3% haircut). Restore passive
  pricing in all three, replace their participation/queue factors with p, retain
  latency/freshness/345600-second buy expiry. These are named cost/time sensitivities,
  not calibrated realism levels. Capital 10M GP, eight slots, 10% initial-capital
  budget/order, 86400-second holding horizon, existing per-lot tax policy.
* Mark unsold units at the latest available low-side reference less preset costs,
  tax and haircut using integer_lots_v2. Invalid marks value at zero with separately
  counted unpriceable units. Marks are not liquidation proceeds or released slots.
* Persist full orders/fills/equity/metrics and qualification/capacity audit fields,
  input/code hashes, exact parameters, durable progress, overwrite refusal and
  completion status. Summarize all 810 combinations (2 x 9 x 3 x 5 x 3), ranges,
  sign brackets, no-trade ranks, terminal exposure and zero-activity cases.
* Add mechanics and corruption/gate tests for every new behavior, retain all 76
  original tests, execute tests/lint and audit real ledgers. Commit the protocol
  before implementation, implementation/tests before running the frozen grid,
  and measured report after actual completion. Results cannot establish attainable
  share without prospective calibration; high requirements justify stopping model
  expansion, not choosing a convenient participation assumption.
