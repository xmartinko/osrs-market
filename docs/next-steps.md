# Judgment after phase 2

**Current decision:** the [executed participation bounds](participation-bounds-validation.md)
recommend stopping and reconsidering the current strategy. All 810 frozen
development combinations completed. With fixed resting offers, CatBoost at 1%
mean-proxy participation loses in every fold and preset; fold 1 first profits at
the 50% sample, and fold 2 never profits on the grid through 100%. The broader
volume ceiling is not achievable execution evidence. The holdout remains sealed.

**Previous phase result:** the [executed price correction](execution-price-correction-validation.md)
supersedes the stressed numbers and negative-sign conclusions retained below as
historical assessments. Corrected CatBoost moderate is +1,432 / −46,392 / +47,770
GP and conservative is −97 / −6,046 / +6,238 GP. The holdout remains sealed.

Written before new implementation, against `988efd0` on `ml/financial-model`.
The supplied tournament figures are development sensitivity evidence, not investment
returns. The implementation and saved experiment protocol were inspected as well.

## Verdict

There is **no demonstrated executable edge**. My working explanation is that most
of the optimistic profit is compensation assumed from collecting the spread,
without evidence that our orders could collect it. I have roughly 85% confidence
that execution assumptions are the principal explanation of the reported sign
change. That is a subjective engineering judgment, not a statistical probability
estimated from three folds. I have low confidence in the stronger claim that no
predictive signal exists. A weak forecast and an untradeable forecast are different
failures, and the present experiment cannot separate them.

The optimistic preset buys at the observed low side and sells at the high side;
the other presets pay the high side and receive the low side. That changes the
economic strategy, alongside participation, queue fraction, latency, freshness,
slippage and terminal inventory marks. Calling this merely increasing realism
conceals a confounded experiment. In the actual executor even optimistic orders
wait for a subsequent eligible bucket; they do not fill on their decision bucket.
Nevertheless, a future bucket average and a fraction of its volume do not establish
that a particular passive order would fill, or that a filled order would escape
adverse selection. The optimistic scenario is an uncalibrated favorable case,
not a mathematically guaranteed upper bound.

CatBoost losing less than a catastrophically bad naive strategy is weak evidence.
A baseline capable of losing almost the entire 10M bankroll makes almost anything
look competent. No-trade is the relevant economic hurdle and wins under the
development selection policy. Three positive optimistic folds do not override
three negative moderate folds. Nor are the folds three independent market trials.

## Ranked work and the decision each step supports

1. **First: isolate execution economics using the already saved development
   predictions.** Freeze the model scores, folds, capital, slots, horizon and tax;
   replay the existing three presets plus one-factor changes from optimistic to
   moderate (price side, participation, queue, slippage, latency, freshness and
   terminal haircut). Also restore passive pricing in moderate and report a small
   predefined slippage grid under each pricing convention. Include all five
   existing models and no-trade, with zero-fill cases explicitly called vacuous.
   Reprice the *same optimistic fill quantities and times* on crossed sides as a
   separate accounting diagnostic. This removes changing trade selection from
   the mechanical cost comparison; it is not a feasible execution simulation.
   Persist manifests, input hashes, complete fill/order/equity records, bought
   and sold units, tax, realized P&L, terminal inventory and per-fold results.
   Do not train, search for a winning threshold, select a new model or read any
   holdout artifacts. This can establish whether assumed spread capture alone
   destroys the profit, or whether turnover, marking or availability dominates.
   It cannot measure actual passive fill probabilities. It beats a schema rewrite
   because it answers the immediate economic question with existing data, and
   beats more models because it tests the measurement apparatus first.
2. **Calibrate execution prospectively while preserving the live archive.**
   Accumulate uninterrupted 5-minute buckets with fetch times, mapping revisions
   and source resolution; report collection gaps and usable history by item.
   Add separately timestamped latest-side observations if needed, preserving their
   own fetch times. Latest-side timestamps must never be passed off as timestamps
   of every trade in an aggregate bucket. To settle passive profitability, collect
   manual/authorized own-order records: submissions, prices, amendments,
   cancellations, partial fills, actual tax, inventory and subsequent price moves.
   Estimate fill probability conditional on price/size/wait/spread, and post-fill
   adverse selection, with uncertainty. Bulk completed-trade data alone cannot
   identify queue priority or our counterfactual fills. A matched prospective
   comparison against simple causal controls would distinguish useful forecasting
   from a free-spread artefact; a failing instant-side replay alone cannot reject
   every passive strategy. An adequate execution history, not a particular count
   of model adapters, is the gate to economic claims.
3. **Freeze a new prospective, nonvacuous evaluation.** Keep the existing holdout
   sealed under its original protocol; do not use it to assess or select these
   corrected execution rules. Define coverage, eligible decisions, requested units,
   bought/sold units and independent temporal coverage gates before examining
   outcomes. Show zero-trade reasons and mark insufficient activity inconclusive.
   Freeze an execution envelope justified by step 2, minimum usable sample and
   uncertainty rules before the next period starts. Include no-trade, a simple
   momentum/mean-reversion forecast and a fixed-seed, item/time-matched control
   with comparable exposure. Positive results must survive realistic costs,
   inventory liquidation and concentration checks; failure versus these controls
   would undermine an incremental forecasting edge. More predictions alone are
   not more independent trades.
4. **Only then improve targets, ranking and capacity.** Align forecast horizon
   and labels with the executable lifecycle, measure profit per occupied slot and
   tied-up capital, stratify by item/price/liquidity, and test tax exemptions and
   dated tax regimes where evidence supports them. Demand economic gain beyond
   simple controls. Current per-unit GP ranking can favor expensive items without
   improving return on scarce capital. Sweep capacity only within a calibrated
   envelope; a million units of hypothetical turnover is not evidence of scale.
5. **Defer the foundation-model tournament and stacking.** There is no good
   reason to pay its integration and compute cost before step 3 can distinguish
   a forecast improvement from a fill-assumption artefact. A model with better
   return MAE can still lose more money. Resume with one small adapter and a
   strict incremental-value/resource gate, not six families at once.

## Biggest validity threat

The largest threat is **mistaking completed aggregate trades for liquidity
available to our particular orders**, especially granting both passive spread
capture and unconditional fills. It creates false positives; replacing it with
arbitrarily punitive crossed prices and haircuts can also discard a real passive
signal. Changing several execution assumptions at once lets either conclusion
be rationalized afterward. Clean accounting prevents impossible money creation,
but cannot validate an assumed fill process. The Wiki describes latest-side
transaction timestamps and separate aggregate price/volume endpoints; neither is
an order book ([API documentation](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices)).

## Is metadata the bottleneck?

Historical limits and interval provenance are a real bottleneck for a *strict
historical tradability claim*. Joining today's limits backward is lookahead in
eligibility and sizing even when the model never sees the column. Guessing an
interval can reuse volume or misstate availability. Strict refusal is correct,
but zero GP from that refusal is no evidence about market edge.

They are **not the principal bottleneck for explaining the current losses** and
not an excuse to delay step 1. The forward Python collector already preserves
source interval, fetch time and mapping-at-fetch limits without a C++ change.
More metadata cannot turn bucket averages into executable quotes. Two days of
historical 5-minute data cannot validate intraday fill timing across regimes;
one year of daily data cannot supply the missing queue information. Live history
must accrue. Tax and capacity also matter: per-unit flooring and tax are already
modeled, but exempt-item policy and historical tax changes need dated verification;
participation and queue fractions are currently assumptions, not measurements.
The 171,067 → 49,422 → 10,033 reported fill-count collapse means the three presets
also test very different exposures. State separately whether a count means fill
events or units. Model/label horizon versus delayed buys and exits is another
source of mismatch that a richer model alone will not fix.

## Concrete future storage proposal (no backend changes in this phase)

Replace destructive resolution overwrites with an append-only observation table
keyed by `(source, endpoint, interval_seconds, bucket_start, item_id,
payload_revision_hash)`. Store nullable aggregate high/low prices, per-side
volumes, bucket end, response fetch time, ingestion time and raw-payload hash.
Retain the first observed revision for causal replay and retain later revisions
for audit. Store latest trades separately with `(item_id, side, trade_time,
price, fetched_at, source, payload_hash)`; never invent these fields for aggregates.
Store mapping revisions separately with `(item_id, buy_limit, observed_at,
payload_hash)` and join only revisions observed by the decision time. An observed
mapping time is not proof of the rule's historical effective time. Keep old rows
with unknown provenance explicitly unknown. Add own-order/fill tables keyed by
account/order/fill identity with submission/amendment/cancellation/fill timestamps,
prices, quantities and actual tax. Do not collect credentials in research exports.

## Revised phases 3–4

Phase 3 should become execution diagnosis, prospective data qualification and
calibration, with an explicit inconclusive outcome available. Phase 4 should be
an economically aligned CatBoost/simple-control trial on a newly frozen forward
period. Foundation adapters and out-of-fold stacking move behind that gate.
Do not tune against the sealed holdout or relabel current-limit
sensitivity as historical results. If calibrated achievable fills still cannot
beat no-trade with useful confidence, stop model expansion and reconsider the
strategy/horizon. If only passive execution works, research that specific strategy
and its adverse selection rather than interpreting crossed-side failure as a
universal impossibility theorem.

## Implementation protocol frozen here

The first implementation will use development folds 0–2 and saved forecasts only.
The slippage grid is 0, 5, 10 and 30 bps per side with all other optimistic
assumptions fixed, once with passive prices and once with crossed prices. This
is a diagnostic grid, not a parameter selection exercise. Overlapping grid and
one-factor scenarios may share identical policies and must agree. Replay must
reject observations/predictions outside the recorded fold boundaries or at/after
the holdout cutoff, duplicate decision keys, missing prediction coverage, changed
panel/config hashes and incomplete inputs. It must refuse output overwrites,
record partial progress durably and label every result `current_limits_sensitivity`.
Reproduce the three original presets before interpreting the new diagnostics.

## Measured follow-up after implementing priority 1

The [execution validation record](execution-diagnostics-validation.md) contains the
executed command, complete CatBoost grid and audit output. All 285 development
replays completed; the original presets reproduced. All figures below remain
current-limit sensitivities using hypothetical fills, with no new holdout evaluation.

Changing **only price sides** produces CatBoost fold P&L of +15,713 / −288,771 /
+110,353 gp, versus +58,020 / +20,185 / +280,599 optimistic. This breaks the
all-fold-positive story but does not establish that passive spread capture explains
every positive result. The complete fixed-fill repricing in fold 2 reduces +280,599
to +27,198 gp; fold 0 and fold 1 repricings are incomplete because opposite-side
prices are absent for two and one fill events respectively. Those missing prices
were not filled in. Participation or queue changes alone also make fold 1 negative.
Latency and freshness changes alone have no effect in this daily experiment;
that does not validate their treatment for intraday trading.

The most consequential new finding is **price-tick quantization**. In fold 0,
optimistic CatBoost buys have median price 3 gp. The nominal passive 5-bps scenario
keeps all 71 fill events and quantities identical but charges one extra GP per
purchased unit and removes one GP per sold unit: 48,023 gp total. The effective
price costs are about 2,251 bps on purchases and 1,445 bps on sales. Its 5/10/30-bps
results are identical. It also generates 64 units of zero-GP sales; the original
moderate CatBoost scenario generates three zero-GP sale units across the folds.
These are not credible executable-price observations. The diagnostic deliberately
preserved the executor to reproduce phase 2; it has not repaired this behavior.

My verdict remains **no demonstrated executable edge**, with stronger grounds to
reject the interpretation that moderate/conservative losses prove no real signal.
Those presets mix uncalibrated fill assumptions with very large effective tick
costs on cheap items. Before the prospective calibration in priority 2, specify
valid positive execution prices and distinguish a deterministic one-tick stress
from an expected slippage estimate. Verify which adverse costs are actually paid,
including the selection of fills, rather than merely clamping zero prices and
declaring the model repaired. Preserve these v1 results and version any corrected
execution policy; then collect own-fill evidence and freeze a new forward trial.
Foundation-model expansion remains deferred.

## Decision after the 285-run diagnostics

The next action is the [reasoned price/tick correction](execution-price-correction.md),
written before implementation against `255dc6f`. It ranks the defects, withdraws
cost interpretations of the old stressed results, specifies admissible prices,
separates expected bps from whole-tick stress, and freezes the corrected replay.
Own-fill calibration and a new prospective trial remain the economic gates.

The earlier wording claiming the holdout had been consumed was unsupported: the
frozen development manifest records `holdout_evaluated=false`. No holdout access
markers or artifacts were opened to investigate that wording. The restriction
for this correction is to keep it sealed and use development forecasts only.

## After executing the price correction

All 285 corrected development combinations completed, and all 45 original
preset/model/fold baselines reproduced under quarantined legacy arithmetic.
76 tests pass, including all original 54. The independent audit verified 9,880
positive integer price lots representing 7,332 opportunities, with ten explicitly
untradeable price opportunities and no nonpositive fills.

The [full validation](execution-price-correction-validation.md) records real output,
all model results, measured costs and exact supersession deltas. CatBoost moderate
moves from −113,714 to +2,810 GP summed across separately funded folds; conservative
moves from −20,890 to +95 GP. Bought/sold and ending inventory units are unchanged
in all nine CatBoost original-preset comparisons. These small positive sums are
not a continuous deployment return. The old all-fold-negative argument is withdrawn;
corrected passive 5/10/30-bps runs remain positive in all three folds.

Priority 1's price/tick arithmetic defect is repaired. The blocking empirical
question is now whether our orders can obtain the assumed prices and quantities
without adverse selection. The unchanged complete fixed-fill comparison still
removes 90.3% of fold-2 profit on crossing the spread. I retain roughly 90%
subjective confidence in execution conventions/measurement as the explanation
of the **old reported** sign change, but cannot use the old costs to claim that
calibrated execution destroys the signal. Executable edge remains undecidable;
no model was reselected, and no holdout was read or unlocked. Proceed to own-fill
calibration and prospective data qualification, not a larger model tournament.
