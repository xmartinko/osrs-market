# Executed participation bounds

**Recommendation: stop the present strategy and reconsider its order lifecycle.**
No-trade remains the economic hurdle. The reframing correctly identifies real
passive counterparties, but aggregate prints do not identify our queue share or
price-compatible volume. The new fixed-offer replay supplies no profitable
CatBoost participation sample common to all development folds under the average
qualification proxy, including the zero-cost preset. A 50% share of reported
compatible volume is not a credible uncalibrated central assumption.

Everything below is **`current_limits_sensitivity`**: hypothetical fills, backward
joined current limits, daily timing and unknown queue/adverse-selection effects.
These are scenario profit ranges, not confidence intervals or rigorous P&L bounds.
The guaranteed own-fill lower bound is zero; neither zero fills nor maximum
volume bounds portfolio P&L. The [pre-code reasoning and frozen protocol](participation-bounds.md)
was committed at `03c4a95`. Implementation was committed at `3c77663`; the completed
market run used clean `f5ad5b7`, which adds an observation cache with an equivalence
test. The full frozen grid ran without fitting, tuning, changing scores or selecting
a new model. The holdout was not read or unlocked.

## Headline: participation required to beat no-trade

Under `mean_proxy`, CatBoost's first positive sampled share is **0.1% in fold 0,
50% in fold 1, and none through 100% in fold 2**, in every cost/time preset. These
are sampled brackets, not an inferred monotone threshold. Fold 0 loses again
above 0.1% (conservative) or 0.5% (optimistic/moderate). The fold-1 bracket is
(20%,50%], **30 percentage points wide**. Fold 2 has no demonstrated positive
region on the frozen grid. Unsampled profitable islands cannot be ruled out;
searching for them now would be outcome-driven tuning.

The 1% planning case loses in **every fold and every preset**:

```text
current_limits_sensitivity; mean_proxy; CatBoost net GP
preset          fold0    fold1    fold2
optimistic        -83   -24041   -54625
moderate         -151   -24476   -56513
conservative     -298   -25389   -60841
```

The broader `moment_upper` capacity scenario first profits at **0.1%, 0.1%, 5%**
by fold, but fold 1 becomes negative at 5% and 20%. All three folds are positive
together only at the **50% and 100% tested shares**. This ceiling can admit almost
all low-side volume even when its mean is far above our bid: an unobserved extreme
print can explain the mean. It explicitly assumes a favorable hidden price
allocation as well as favorable queue allocation. It cannot rehabilitate the
strategy or demonstrate that 5% of actual accessible flow is sufficient.

## Complete model ranges and sampled break-even brackets

Each cell is **first profitable bracket in percent; [minimum, maximum] GP** across
the eight strictly positive shares (0.1%, 0.5%, 1%, 2%, 5%, 20%, 50%, 100%).
A first profitable sample requires both buys and sales, and positive final equity
P&L. `none` means no such sample, not a theorem about intermediate shares.
Brackets with zero as the left endpoint are against vacuous no-trade, without
asserting profitability near zero. Profits at later shares may reverse.

`no_trade` and `no_change` are exactly **[0,0] GP, zero bought/sold units, and no
strictly profitable share** in every fold, preset and qualification rule. The
no-change control is inactive under the frozen score admission policy. For the
three active score sets, the full results follow.

### `mean_proxy` — `current_limits_sensitivity`

| Preset | Model | Fold 0 | Fold 1 | Fold 2 |
| --- | --- | --- | --- | --- |
| optimistic | catboost | (0,0.1]%; [-9,944, +1,994] | (20,50]%; [-198,310, +95,622] | none; [-60,349, -13,330] |
| optimistic | raw_spread | (50,100]%; [-497,912, +433,363] | (20,50]%; [-139,488, +94,413] | none; [-414,859, +40,832] |
| optimistic | spread_volume | none; [-1,590,880, -325,007] | none; [-2,009,068, -1,570,127] | none; [-1,746,820, -538,561] |
| moderate | catboost | (0,0.1]%; [-11,555, +1,980] | (20,50]%; [-199,421, +90,644] | none; [-62,167, -15,667] |
| moderate | raw_spread | (50,100]%; [-515,864, +386,667] | (20,50]%; [-143,179, +86,248] | none; [-253,083, +34,245] |
| moderate | spread_volume | none; [-1,653,790, -352,596] | none; [-1,916,913, -1,201,843] | none; [-1,817,123, -593,179] |
| conservative | catboost | (0,0.1]%; [-14,811, +1,943] | (20,50]%; [-205,886, +80,650] | none; [-66,342, -17,370] |
| conservative | raw_spread | (50,100]%; [-551,724, +293,438] | (20,50]%; [-170,411, +69,861] | none; [-277,509, +0] |
| conservative | spread_volume | none; [-1,859,514, -494,075] | none; [-2,104,490, -1,364,863] | none; [-2,045,836, -809,264] |

### `moment_upper` — `current_limits_sensitivity`

| Preset | Model | Fold 0 | Fold 1 | Fold 2 |
| --- | --- | --- | --- | --- |
| optimistic | catboost | (0,0.1]%; [+12,780, +230,625] | (0,0.1]%; [-51,198, +290,486] | (2,5]%; [-47,792, +853,737] |
| optimistic | raw_spread | (20,50]%; [-574,967, +5,232,429] | (2,5]%; [+0, +13,321,771] | (5,20]%; [-8,092, +6,666,434] |
| optimistic | spread_volume | (0,0.1]%; [+375,690, +1,135,176] | (0.1,0.5]%; [-684,921, +661,980] | (5,20]%; [-1,031,520, +3,255,125] |
| moderate | catboost | (0,0.1]%; [+12,435, +223,759] | (0,0.1]%; [-53,802, +283,309] | (2,5]%; [-49,596, +784,339] |
| moderate | raw_spread | (20,50]%; [-613,377, +5,163,184] | (2,5]%; [+0, +12,292,193] | (5,20]%; [-20,687, +6,752,215] |
| moderate | spread_volume | (0,0.1]%; [+296,503, +1,027,735] | (0.1,0.5]%; [-761,296, +565,414] | (5,20]%; [-1,134,428, +3,087,142] |
| conservative | catboost | (0,0.1]%; [+11,734, +210,008] | (0,0.1]%; [-59,066, +268,916] | (2,5]%; [-53,745, +768,743] |
| conservative | raw_spread | (20,50]%; [-690,103, +5,024,897] | (2,5]%; [+0, +11,994,133] | (5,20]%; [-53,265, +6,478,299] |
| conservative | spread_volume | (0,0.1]%; [+138,033, +818,757] | (0.1,0.5]%; [-911,954, +367,071] | (5,20]%; [-1,360,818, +2,779,212] |

Positive range maxima with `none` occur for mean-proxy raw-spread fold 2 under
optimistic/moderate: these profits are **inventory-only**, with no sales, so they
fail the frozen break-even evidence rule. Small-share raw-spread zeroes often
mean no buys; they do not establish executable break-even. Across all combinations,
438 have no buys and 24 are inventory-only.

## Sign changes and the undecidable region

All figures in this section are `current_limits_sensitivity`. The complete sampled
CatBoost price-proxy output is reproduced here; zero-share rows are all zero.

```text
participation %              0.1      0.5       1       2        5       20      50     100
optimistic fold0            1994      150     -83    -155     -373      -42   -3554   -9944
optimistic fold1           -2407   -12253  -24041  -46012  -127204  -198310   95622   44154
optimistic fold2          -14826   -60349  -54625  -58167   -58825   -44420  -22391  -13330
moderate fold0              1980       90    -151    -241     -515     -378   -4634  -11555
moderate fold1             -2441   -12470  -24476  -46803  -129679  -199421   90644   39890
moderate fold2            -15667   -62167  -56513  -60126   -60923   -40677  -28296  -34276
conservative fold0          1943      -44    -298    -433     -834    -1098   -6839  -14811
conservative fold1         -2524   -12939  -25389  -48440  -134672  -205886   80650   31333
conservative fold2        -17370   -66342  -60841  -64597   -65701   -46878  -34827  -42751
```

The observed nonzero-sign reversal brackets are below. Each bracket only locates
adjacent sampled signs; it does not prove there is one crossing inside it. Widths
are percentage points. Inactive controls have no sign changes. Transitions from
zero activity to losses/profits are separately preserved in `sign_changes.csv`.

| Qualification | Model / fold | Presets | Observed reversals and bracket widths |
| --- | --- | --- | --- |
| mean_proxy | CatBoost / 0 | optimistic, moderate | positive → negative between 0.5% and 1%; width 0.5 |
| mean_proxy | CatBoost / 0 | conservative | positive → negative between 0.1% and 0.5%; width 0.4 |
| mean_proxy | CatBoost / 1 | all | negative → positive between 20% and 50%; width 30 |
| mean_proxy | CatBoost / 2 | all | always negative at positive sampled shares |
| mean_proxy | raw_spread / 0 | all | negative → positive between 50% and 100%; width 50 |
| mean_proxy | raw_spread / 1 | all | negative → positive between 20% and 50%; positive → negative between 50% and 100%; widths 30, 50 |
| mean_proxy | raw_spread / 2 | optimistic, moderate | negative → inventory-only positive between 2% and 5%; positive → negative between 5% and 20%; widths 3, 15 |
| mean_proxy | raw_spread / 2 | conservative | no positive sample |
| mean_proxy | spread_volume / all | all | always negative at positive sampled shares |
| moment_upper | CatBoost / 0 | all | always positive at positive sampled shares |
| moment_upper | CatBoost / 1 | all | positive → negative between 2% and 5%; negative → positive between 20% and 50%; widths 3, 30 |
| moment_upper | CatBoost / 2 | all | negative → positive between 2% and 5%; width 3 |
| moment_upper | raw_spread / 0 | all | negative → positive between 20% and 50%; width 30 |
| moment_upper | raw_spread / 1 | all | first positive between inactive 2% and 5%; width 3; no later sign reversal |
| moment_upper | raw_spread / 2 | all | negative → positive between 5% and 20%; width 15 |
| moment_upper | spread_volume / 0 | all | always positive at positive sampled shares |
| moment_upper | spread_volume / 1 | all | negative → positive between 0.1% and 0.5%; positive → negative between 1% and 2%; widths 0.4, 1 |
| moment_upper | spread_volume / 2 | all | negative → positive between 5% and 20%; width 15 |

The deeper undecidable region is larger than these numerical gaps. Under the
proxy, no tested share makes CatBoost positive in every fold. Under the loose
capacity envelope, 50–100% samples can, but attainable priority is unmeasured
throughout [0%,100%]. A positive low-share ceiling result cannot establish our
ability to capture even that share of actually compatible trades. The interval
between the two qualification rules measures unidentified price distributions,
not a statistical error bar. The buy-limit clock also remains unidentified inside
daily buckets; we permit one remaining per-item allowance per observation,
never six invented intraday replenishments.

## Model ordering and inventory dependence

Ordering is **not stable**. Across 24 positive-share fold combinations per preset,
mean-proxy CatBoost beats no-trade only 4 times under optimistic/moderate and 3
times under conservative. It beats spread-volume in all 24, but that baseline
loses in every case. It beats raw-spread in only 11/24 (optimistic/moderate) or
10/24 (conservative). Losing less than spread-volume is not an economic edge.

With the loose moment envelope, CatBoost beats no-trade 18/24 under each preset,
but beats spread-volume only 8/24 optimistic, 9/24 moderate and 11/24 conservative;
it beats raw-spread 11/24 in each. Raw-spread's ceiling profits reach 13,321,771 GP
in optimistic fold 1: that result requires extreme favorable latent liquidity,
not extraordinary evidence for that ranking rule. The enormous sensitivity of
simple baselines is a warning about identification. Full ties/ranks at every
sample are recorded in `ranks.csv`; no model or execution setting was selected.

The first mean-proxy positive fold-1 sample is not cash recovery. At 50% under
moderate, CatBoost equity P&L is +90,644 GP, **cash P&L −93,934 GP**, realized P&L
+16,068 GP, and the terminal mark is 184,578 GP on 31,981 unsold units. It bought
111,225 and sold 79,244 units, paying 10,346 GP sale tax. Under optimistic the
same 50% sample has +95,622 GP equity, −91,020 GP cash and 186,642 GP marked
inventory; conservative has +80,650 GP equity, −99,802 GP cash and 180,452 GP marks.
These are valuations, not completed liquidation or released capacity.

Even the moment-envelope 0.1% first profits in folds 0/1 have negative cash P&L
under every preset. Moderate fold 0 is +12,435 GP equity with −15,493 GP cash and
27,928 GP marked inventory; fold 1 is +6,183 GP equity with −6,300 GP cash and
12,483 GP marks. Mean-proxy fold-0 0.1% is less mark-dependent (+1,980 equity,
+1,972 cash, 8 GP mark under moderate), but is small and disappears at larger
participation. There is no stable participation threshold hiding in these points.

The new policy also changes the economic interpretation of prices. The old
executor used future bucket averages for each fill; v3 freezes quote targets at
submission and never grants that future-average improvement. That change is
necessary to model resting offers and was frozen before seeing outcomes. The
new losses cannot be attributed exclusively to the participation percentage,
or used to claim every passive strategy must lose. They do undermine the existing
forecast-plus-order-lifecycle strategy once its resting offers are made concrete.

## Executed commands, provenance and verification

The completed run command (exit 0) was:

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  python -m osrs_ml.participation \
  --panel /home/martin/osrs-data/assembled-v3/daily.parquet \
  --development-run ml/runs/phase2-real-v1 \
  --output /home/martin/osrs-data/participation-bounds-v3-cached \
  > /home/martin/osrs-data/participation-bounds-v3-cached.log 2>&1
```

Actual completion output:

```text
Completed 810 current_limits_sensitivity combinations; holdout NOT read. Artifacts: /home/martin/osrs-data/participation-bounds-v3-cached
```

The manifest is `status=complete`, `completed_scenarios=expected_scenarios=810`,
`git.dirty=false`, `holdout_read=false`. Results Parquet SHA-256:
`8e46714296cb08d655eb0f6759fac2bb3bd0a74069972df9ba776e81c58c441d`.
Input/config/lock hashes were checked before and after replay; only explicit
fold0–2 prediction paths were enumerated. Panel reads used development-fold
predicates before conversion, strictly before the recorded holdout start.
Hashing the whole panel for integrity did not load holdout observation frames.

The initial uncached attempt at `/home/martin/osrs-data/participation-bounds-v3`
was interrupted after 16 completed combinations to eliminate repeated frame
conversion. Its manifest says `interrupted`; it is not the completed evidence.
The clean replacement uses a copied per-fold observation snapshot. Tests compare
cached and uncached full results and check independence from source-frame mutation.
No scenario, share, forecast, price rule or outcome criterion changed on restart.

The ledger auditor was executed independently (exit 0):

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  python -m osrs_ml.execution_audit \
  /home/martin/osrs-data/participation-bounds-v3-cached \
  /home/martin/osrs-data/assembled-v3/daily.parquet
```

Actual output:

```text
{"fill_lots": 29914, "no_buys": 438, "opportunities": 20546, "price_rejections": 24, "scenarios": 810}
PASS: positive integer prices, quantity/cash/inventory/realized P&L, per-lot tax, bps cost and residual, tick separation, capacity, buy limits, offer ceilings/slots, temporal causality, freshness, no-trade. Holdout NOT read.
```

For v3 it additionally reconstructs submission references from development
observations, frozen lot targets, both qualification formulas, per-bucket share
caps, non-reuse of volume and whole-bucket order survival. It checks fill audit
fields against independently calculated values. Marks are independently
reconstructed from remaining inventory and latest development low-side prices.
The 24 price rejections are not zero-price sales. Unit tests inject malformed
capacity fields and require rejection.

The complete test suite at clean implementation `f5ad5b7` produced:

```text
$ uv run --project ml --frozen pytest -q
........................................................................ [ 73%]
..........................                                               [100%]
98 passed in 29.47s
$ uv run --project ml --frozen ruff check --config ml/pyproject.toml ml/src ml/tests
All checks passed!
```

All original 76 tests remain passing; 22 new cases cover new policy constraints,
zero participation, a small exhaustive integer-price upper-envelope check,
fixed buy/sell prices, partial fills, expiry, latency, whole-bucket survival,
per-bucket flooring without volume carry, four-hour limits, corrected integer
lots/tax, invalid references, sale submission delays, nonmonotone break-even,
complete sealed development replay, overwrite refusal, changed inputs, durable
interruption, ledger corruption and cache equivalence. Fixtures establish mechanics
only; all market tables above come from the real development replay.

The reproducible summary command was also executed (exit 0):

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  python /home/martin/osrs-data/report-participation.py
```

Actual output excerpts:

```text
ALL FOLLOWING RESULTS: current_limits_sensitivity
Manifest: complete combinations= 810 holdout_read= False
No-buy combinations: 438
Inventory-only combinations: 24
```

The data directory contains full ledgers, `results.csv`/Parquet, `break_even.csv`,
`sign_changes.csv`, `ranks.csv`, manifest, replay/audit/summary logs and the summary
script. No data, models or ledgers were added to Git. C++ was unchanged.

## Decision

**Stop expanding or deploying the current strategy; reconsider the lifecycle and
measurement assumptions.** Fold 1 needs an unsupported 20–50% participation
bracket under the average proxy and still relies on unsold inventory; fold 2
never wins at a tested share. At 1% all three folds lose even before adverse
selection is calibrated. The no-trade benchmark survives this phase.

The reframing usefully replaces a vague objection to passive fills with an explicit
conditional-capacity experiment. It does not identify a positive attainable share.
The enormous gap between average qualification and latent-volume ceilings, and
the reversal of simple baseline rankings, show why the queue share cannot be
estimated from these aggregates alone. There is no sound basis here for a model
tournament, selecting a convenient participation rate, or opening the holdout.

Continuing would require a separately frozen prospective investigation with
actual authorized order/fill records demonstrating repeatable prices, waits,
partial quantities and post-fill outcomes. The forward collector should keep
accruing. That is a new evidence-gathering exercise, not a recommendation to
trade this strategy or keep tuning development profitability. No backend change
is needed for the completed sensitivity phase.
