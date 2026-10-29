# Price correction: judgment and specification before implementation

Written against `255dc6f`, after rereading the 285-run validation and next steps,
before changing the executor. This supersedes the proposed next action in those
records, not their preserved observations. No holdout, fitting or model selection
is authorized here.

## What the experiments changed

The size of the free-spread contribution surprised me: in the only complete
fixed-fill comparison, fold 2 loses 253,401 of 280,599 GP (90.3%) on crossing the
spread. The remaining 27,198 GP also matters: this does not prove there is no
forecast signal. The incomplete comparisons cannot establish the same percentage
for the other folds. I had not anticipated a median entry of only 3 GP, nor that
5/10/30 bps would largely mean the same full tick. The measured fold-0 purchase
cost was 2,251 bps, not 5. The zero-GP sales are a separate, unequivocal defect,
including in the original moderate preset. The 122 no-buy combinations and the
identical daily latency/freshness contrasts are warnings about identification,
not negative trials of the strategy. Participation and queue effects also change
the sign independently: there is no clean single-factor explanation.

## Defects ranked by the decision they prevent

1. **Repair price validity and cost measurement now.** A zero-price sale cannot
   represent a GE fill. Rounding every positive bps adjustment to a full adverse
   tick makes nominal bps comparisons false, particularly on cheap inventory.
   Both execution and terminal marks use that arithmetic. All published nonzero
   slippage/haircut P&L, exposure and drawdown figures are unsound as evidence of
   their labelled costs: original moderate/conservative, only-slippage,
   only-terminal-haircut, moderate-passive and positive-bps grids, across all
   models. They remain reproducible legacy arithmetic, not calibrated costs.
   Original zero-cost optimistic and zero-cost one-factor contrasts are internally
   interpretable hypothetical sensitivities; they are **not executable returns**.
   Fold-2 fixed-fill repricing remains an accounting diagnostic with the same
   terminal mark, not a feasible crossed portfolio. Rerun all scenarios, rather
   than guessing that fixing the three zero-price units fixes everything.
2. **Calibrate whether our orders could get these fills.** This invalidates any
   executable-edge interpretation of *all* existing results, including optimistic.
   It does not invalidate the recorded hypothetical accounting comparisons.
   Aggregate averages and volumes give neither an order book nor queue priority.
   Own-order prices, waits, partial fills and post-fill adverse moves are the next
   empirical gate. Changing cost arithmetic cannot repair that missing evidence.
3. **Qualification for the next evaluation.** Dated limits, prospective interval
   provenance, intraday coverage and a frozen nonvacuous forward trial remain
   prerequisites. Current limits joined backward already preclude a strict
   historical tradability claim. Daily data cannot identify intraday latency or
   freshness effects. These are not reasons to postpone correcting arithmetic.
   Do not revisit the holdout or change the original no-trade selection.

## Admissible prices and what the data can actually support

For this archived integer-GP panel, hypothetical unit fill prices must be positive
whole GP: 1, 2, 3, ... . Coins are indivisible; zero is not a GE sale. There is no
universal economic minimum of 50 or 100 GP: those are tax boundaries, not valid
price floors. **3 GP is a legal price**, not grounds for substituting an invented
more plausible price. A one-GP move there is 3,333 bps. The archive contains side
averages, not promises of liquidity at those prices. If a passive price looks too
favorable, report it as an uncalibrated passive assumption or use the observed
opposite side in the predeclared crossed contrast; never invent a replacement
quote. Missing, nonpositive, nonintegral or nonfinite archived references cannot
silently become integer fills. Reject and record the reason. Support nullable
inputs and exact integer arithmetic, including prices above signed int32; do not
hard-code an obsolete int32 ceiling into a general GP cost function. The portfolio's
cash and offer ceiling still bound purchases. Historical per-item special price
restrictions, if any, are not recoverable from this panel and remain unqualified.

The provider describes these as aggregate side averages and volumes, distinct
from latest-side transaction timestamps. Its current API also allows decimal
averages and prices above int32; that is not permission to silently truncate a
future decimal export into this frozen integer-panel replay. Such input needs
an explicit precision/provenance change, outside this correction. See the
[provider's API specification](https://oldschool.runescape.wiki/w/RuneScape%3AReal-time_Prices?mobileaction=toggle_view_mobile)
and the [GE mechanics](https://oldschool.runescape.wiki/w/Grand_Exchange).
A game-admissible price is necessary but does not certify an available fill.

## Bps costs and ticks are different experiments

Version the corrected policy `integer_lots_v2`. Keep a quarantined
`legacy_v1` replay solely to reproduce old artifacts, including its invalid fills.
A nominal bps scenario specifies an **expected notional price cost**, not a
minimum one-tick deterioration on every unit. For integer reference p, quantity q
and b bps, the exact desired adverse cost is p*q*b/10000. Allocate its integer
part across at most two adjacent legal unit prices; the uncharged fractional GP
is a separately reported rounding residual, strictly less than 1 GP per fill
opportunity. Do not carry it between unrelated items or call it paid slippage.
A 3-GP, 10,000-unit buy at 5 bps pays 15 GP of price cost, not 10,000 GP. Each
allocation is explicitly a hypothetical cost distribution, **not inferred trade
prints or evidence that such an execution path existed**. Small orders may pay
zero GP: report achieved bps and residual, so a nominal grid never claims exact
realized precision it lacks. No random draws or favorable seed selection.

Offer reservations use the most expensive allocated unit price, rounded up;
this is a cash constraint, not a paid price cost. A future buy must still fit that
fixed ceiling. Apply tax per item at each allocated integer price, never to a
fractional average. Report spread convention, reference notional, nominal bps,
paid bps cost, explicit tick cost, residual and tax separately. A separate
`adverse_ticks` setting is a deterministic whole-GP stress, labelled in ticks,
with its effective bps reported; it must never be relabelled expected slippage.

If the desired sale unit price is below 1 GP (e.g. a 1-GP reference under any
positive adverse bps, or a 1-GP reference minus a tick), there is no adjacent
positive-price distribution representing it. Record
`untradeable_at_granularity`, retain inventory and its occupied slot, and wait
for another eligible bucket. Do not clamp to 1, donate at 0, or redistribute the
cost into a made-up fee. A zero or invalid reference is `invalid_reference_price`.
Use the same rules at submission and fills; failures must be countable in logs.
For a terminal mark, compose the fractional slippage and haircut before allocation
rather than flooring twice per unit. An unpriceable position has a zero
**valuation bound**, separately counted as unpriceable inventory, with no fill,
proceeds or slot release. A mark is not a liquidation and must not be printed
as one. Report changes in marks separately from cash and quantities.

## Changed judgment and falsification

I would now repair and instrument the measurement apparatus before drawing any
further cost conclusion, then replay frozen forecasts and every original preset.
I would not spend another cycle on model adapters or interpret zero buying as a
failed signal. My subjective confidence that execution assumptions broadly drive
the optimistic-to-moderate sign change rises from 85% to roughly 90% given the
complete spread comparison. My confidence that **calibrated achievable costs**
explain that sign change is much lower: the supposed cost experiment did not
measure them. I do not assign a useful statistical probability to an executable
edge from these three dependent folds. There is still no demonstrated edge.

I would revise the broad explanation downward if corrected fixed-cost accounting
preserved comparable executable-looking profit across crossed sides and useful
exposure, especially with unchanged quantities/marks. Strong prospective,
authorized own-order evidence of reliable passive fills with small adverse
selection, followed by a frozen forward trial beating matched causal controls
and no-trade, would change my view on an edge. Conversely, calibrated fills
that erase the remaining profit, or matched controls that do as well, would
support stopping model expansion. Neither a friendlier rounding rule nor a
punitive tick rule alone can establish either market conclusion.

## Frozen verification scope

Retain all 54 tests and add regressions for illegal prices, low-price bps versus
ticks, exact quantity/cash/tax accounting across mixed lots, unresolved sale
inventory, cash reservations, composed terminal marks, durable replay deltas and
legacy reproduction. Execute the same 19 policies × five models × three development
folds, writing only outside Git. First reproduce the original presets with the
legacy version and compare all saved accounting/exposure metrics. Then publish
v2 results and explicit deltas; preserve every earlier artifact. Audit legal
fills and achieved costs. The resulting cost distribution is a sensitivity,
not own-fill calibration. No C++ changes are needed.

## Implementation checkpoint

Implementation `114772a` makes `integer_lots_v2` the executor default and quarantines
legacy arithmetic for reproduction. `901242f` adds an independent development-ledger
auditor and corruption regressions. All original 54 tests are retained; 20 additional
cases cover the corrected defects and replay/audit behavior.

Executed:

```text
$ uv run --project ml --frozen pytest -q
........................................................................ [ 97%]
..                                                                       [100%]
74 passed in 14.33s
$ uv run --project ml --frozen ruff check --config ml/pyproject.toml ml/src ml/tests
All checks passed!
```

The real-data replay was launched from clean implementation commit `114772a`:

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  osrs-ml diagnose-execution \
  --panel /home/martin/osrs-data/assembled-v3/daily.parquet \
  --development-run ml/runs/phase2-real-v1 \
  --output /home/martin/osrs-data/execution-price-correction-v2 \
  > /home/martin/osrs-data/execution-price-correction-v2.log 2>&1
```

Completion, market figures and audit output will be recorded in a linked validation
record after the command and independent audit finish. The implementation was frozen
before this run; subsequent work here adds auditing and documentation only.
