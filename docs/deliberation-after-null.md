# Deliberation after the corrected null

2026-10-29. This document begins before implementation. The completed 213-test
battery remains frozen; nothing here changes its tests, activity gates or p-values.
The reserved holdout begins at 1785024300 and stays unread. Only the existing
weekly development archive and daily development folds
[1777766700, 1785024300) may supply market observations. Current item metadata
is a sensitivity, not a reconstructed historical rulebook. Generated data stays
under `/home/martin/osrs-data`. No C++ changes are proposed.

## 1. What the null means, and how the instrument could obscure it

My initial argument for stopping: 213 failed tests, enormous marked-path
uncertainty, and earlier extreme arithmetic returns leave no established
forecast trading edge. My argument against declaring the market efficient:
the instrument combines independent aggregate prices with uncalibrated fills;
it could manufacture profits, erase profits or prevent matched production.
Failure of this instrument is weaker than evidence that every economic mechanism
is exhausted. Both arguments can be true. Neither licenses promoting a nominal
winner or relaxing multiplicity correction.

Before selecting implementation I will reconcile every patient account, including
open inventory. Define a trade episode from first owned unit through zero stock;
retain an unclosed episode with a terminal mark. Primary extreme flag: any exact
consecutive weekly side-price ratio above 101 or below 1/101 during submission
through disposition, or a weighted sale/buy price ratio above 101. This keeps the
earlier >10,000% criterion in view, with symmetric crashes. Also report a separate
10-fold diagnostic, chosen now, not after seeing contributions. These are
attributions of fixed fills, never accounts rerun after excluding bad trades.
The overall-price signal can be anomalous even if side-price trades do not jump;
keep that source inconsistency distinct from trade-price gains.

Weekly `overallPrice` is used for selection, and the two side averages for frozen
passive offer references and mean-based compatibility. None is an observed quote
or print. A mean does not establish any executable quantity at a frozen limit.
I will reprice the *same quantities* at contemporaneous opposite-side means,
with the original 10bps costs and integer tax, as a spread sensitivity. That is
still a hypothetical calculation, not a more truthful fill reconstruction. I
will also compute the cash-at-risk/no-fill alternative: zero execution and zero
profit. Aggregate records identify no positive executable lower bound. The
fraction of profits causally attributable to this assumption is unidentified;
the full reported path relies on it. Do not substitute a precise-looking haircut
for that identification failure.

The existing independent ledger audit should establish cash, owned units,
conversion consumption, tax, marks, causality and registered capacity arithmetic.
It cannot establish that any quoted price was available, our queue position,
historical metadata, actual production time, or an attainable participation rate.
Run it again before interpreting gains.

Executed diagnostics before implementation:

The diagnostic script is `/home/martin/osrs-data/deliberation-diagnostics.py`;
its CSVs and item-day panel are in `deliberation-diagnostics-v1`. It verifies the
original daily/weekly/metadata hashes, SQL-filters daily development folds and
weekly availability before materialization, and reconciles all **24** patient
accounts exactly to their saved net GP and terminal marks. These are descriptive
attributions of already inspected development results. No new significance test,
model fit, profit-rule outcome or holdout access occurred.

### Patient concentration and execution-price dependence

The table below is pasted machine output. `extreme101_gp` and `extreme101_rest`
partition *entire episode P&L*, including open episodes, by the prewritten jump
flag. Daily accounts use exact daily ratios; weekly accounts use weekly ratios.
`extreme 10` is the separate prewritten tenfold sensitivity. A source jump inside
a long episode establishes exposure, not causation: it does not mean every GP
was earned on that jump. Trade episode counts include open episodes separately
from the original count of completed positions.

```text
PATIENT RECONCILIATION
         scenario  trades  open      net  crossed_known_remainder_original  missing_opposite  missing_opposite_units  spread_sensitivity  largest_gp          largest_item  largest_jump  rest_gp  extreme101_n  extreme101_gp  extreme101_rest  extreme10_n  extreme10_gp  extreme10_rest
patient_14d_p0010       0     0        0                                 0                 0                       0                   0           0                  none      0.000000        0             0              0                0            0             0               0
patient_14d_p0100       1     1      134                                53                 0                       0                  81         140              Bluegill    705.905263       -6             1            140               -6            1           140              -6
patient_14d_p0500       2     2    11887                              1948                 0                       0                9939       11085       Ancient crozier      9.359796      802             2            834            11053            2           834           11053
 patient_1w_p0010       7     3   -57566                           -630230                 1                       1              572664      111968      Adamant knife(p)   7528.666667  -169534             6         113486          -171052            7        112816         -170382
 patient_1w_p0100      25     4  -386735                          -3620161                 7                      36             3233426     2187179      Bronze hasta(p+)    820.000000 -2573914            15        2197717         -2584452           25       -112852         -273883
 patient_1w_p0500      31     4  8807318                          -7021079                17                     284            15828397    10935888      Bronze hasta(p+)    820.000000 -2128570            18       10702674         -1895356           29      10706679        -1899361
patient_28d_p0010       0     0        0                                 0                 0                       0                   0           0                  none      0.000000        0             0              0                0            0             0               0
patient_28d_p0100       2     0     -162                              -252                 0                       0                  90          -9            Body tiara      5.000000     -153             1           -153               -9            1          -153              -9
patient_28d_p0500       2     1     -967                             -1551                 0                       0                 584           0 Fremennik brown shirt    567.828571     -967             2           -919              -48            2          -919             -48
 patient_2w_p0010       7     3   -51186                           -623831                 1                       1              572645      111968      Adamant knife(p)   7528.666667  -163154             6         113468          -164654            7        112798         -163984
 patient_2w_p0100      26     4 -1786743                          -4680752                 5                      34             2894009     2187179      Bronze hasta(p+)    820.000000 -3973922            16        2229282         -4016025           25        -79290        -1707453
 patient_2w_p0500      27     4  9260118                          -7030003                15                     114            16290121    10935888      Bronze hasta(p+)    820.000000 -1675770            12       10874673         -1614555           23      11076524        -1816406
 patient_3d_p0010       0     0        0                                 0                 0                       0                   0           0                  none      0.000000        0             0              0                0            0             0               0
 patient_3d_p0100       2     0      537                              6450                 0                       0               -5913         540              Bluegill    705.905263       -3             1            540               -3            1           540              -3
 patient_3d_p0500       3     3    12406                             46050                 0                       0              -33644        8404       Ancient crozier     38.733965     4002             1           3234             9172            3         12155             251
 patient_4w_p0010       8     4  -150521                           -861612                 3                      26              711091       74264      Adamant knife(p)   7528.666667  -224785             8         114139          -264660           11       -150600              79
 patient_4w_p0100      16     4  1334901                          -5767153                 6                      68             7102054     1179265      Adamant knife(p)   7528.666667   155636            15        1273112            61789           16       1265084           69817
 patient_4w_p0500      17     4  7351224                         -28140642                10                     245            35491866     6774770      Adamant knife(p)   7528.666667   576454            14        7100428           250796           18       7126332          224892
 patient_7d_p0010       0     0        0                                 0                 0                       0                   0           0                  none      0.000000        0             0              0                0            0             0               0
 patient_7d_p0100       1     1      137                                55                 0                       0                  82         140              Bluegill    705.905263       -3             1            140               -3            1           140              -3
 patient_7d_p0500       2     3     9246                              1618                 0                       0                7628        7911       Ancient crozier      9.359796     1335             2            834             8412            3          1351            7895
 patient_8w_p0010      16     2  -265658                           -953436                 3                      29              687778       12686 Tarromin potion (unf)      1.419048  -278344            11           -903          -264755           14       -275687           10029
 patient_8w_p0100      16     3   -79835                          -6064058                 7                      68             5984223      126892 Tarromin potion (unf)      1.419048  -206727            15        -236095           156260           16       -234859          155024
 patient_8w_p0500      24     2   787068                             23499                 8                     160              763569      421366       Sandstone (5kg)   1849.500000   365702            19         442876           344192           22        490981          296087
```

The strongest patient result is carried by **one completed Bronze hasta(p+)
episode: +10,935,888 GP**, or 118.10% of the two-week 5% account's +9,260,118.
Everything else totals **−1,675,770**. Its 60 units cost 2,050,628 and sold for
12,986,516 after tax. The same episode carries the one-week 5% account too;
these are dependent variants. The 4w/5% account's largest episode, Adamant knife(p),
contributes **6,774,770 / 7,351,224 = 92.16%**; the remainder is +576,454.
At 4w/1% it contributes **1,179,265 / 1,334,901 = 88.34%**. This episode is
*still open*: its attributed profit includes earlier partial sales; its final
2,155 units at 5% have a zero mark because the latest low side is missing. It
is not one completed successful trade. The 8w/5% result is less concentrated:
Sandstone (5kg) contributes +421,366, leaving +365,702; its observed net sale/buy
ratio is 151.76. The +415,900 Tarromin potion (unf) episode has maximum side jump
only 1.419. Thus **not every positive contribution is an extreme jump**.

The two dominant hasta/knife episodes have weighted simulated sale/buy ratios
6.33 and 7.65, rather than >101. The 820-fold and 7,529-fold figures concern
source movements during their episodes. This distinction prevents attributing
the earlier ridge's exact 62–98% mechanism to these accounts without evidence.
We have established extreme concentration and exposure to incoherent sides,
not a causal decomposition of executable profit.

The hasta example makes the instrument problem concrete (original observations):

```text
patient_2w_p0500 FILLS
 submitted  timestamp side  quantity  price_gp  bucket_mean_gp  reference_price_gp  bucket_volume
1623283500 1624493100  buy        30     34177               2               34143            710
1623283500 1624493100  buy         5     34178               2               34143            710
1623283500 1625097900  buy        22     34177            1000               34143            510
1623283500 1625097900  buy         3     34178            1000               34143            510
1625702700 1627517100 sell         3    220858          322500              221080            847
1625702700 1627517100 sell        39    220859          322500              221080            847
1625702700 1628121900 sell         1    220858          322500              221080            472
1625702700 1628121900 sell        17    220859          322500              221080            472
```

The signal bucket's overallPrice is 7,091, buyingPrice 143,256 and sellingPrice
34,143; they cannot be treated as a coherent instantaneous book. Later the
executor uses 2/1,000 GP low-side averages to qualify whole volumes at a frozen
34,143 GP offer, then a 322,500 GP high-side mean to qualify sales near 220,859.
These averages neither establish own fills nor certify a two-sided quote.

`crossed_known_remainder_original` replaces fixed-fill buys by current buyingPrice
and sells by current sellingPrice, retaining 10bps costs, exact integer lots/tax,
quantities and terminal marks. It is an attribution, **not a rerun**: cash may
become infeasible, signals and fills are not reselected. Where the opposite mean
is missing, nonpositive or below legal tick granularity after slippage, the
original cashflow is retained and counted in `missing_opposite`. Therefore these
partial sensitivities are not executable bounds. For 2w/5%, replacing known
prices removes **16,290,121 GP** and changes the reported +9,260,118 to
**−7,030,003**, with 15 unresolved opportunities / 114 units. The corresponding
4w/5% change is **35,491,866 GP**, to **−28,140,642**, with ten unresolved
opportunities / 245 units. For 4w/1% it becomes **−5,767,153**. The 8w/5%
partial sensitivity is still +23,499, with eight unresolved opportunities /160
units: neither that residual nor its sign validates execution. Some daily
sensitivities improve profits, confirming that means can distort both ways.

All reported weekly execution relies on average-based references/qualification;
**100% of its claimed executable profit is unverified**. The true amount earned
or lost at real executable prices, or the causal percentage due to averaging,
is unidentified. A no-own-fill account earns zero. The archive supplies no
positive lower bound on attainable GP. It cannot prove that these opportunities
never existed either. Consequently retain the corrected failure to establish
an edge, and reject interpreting it as proof of a universal economic null.

The existing independent audit was rerun unchanged:

```text
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

It reconstructs owned inventory and pooled book costs through buys, sells and
conversions; checks conversion coin amounts, nonnegative cash, final cash/units,
terminal marks, per-item limits, bucket participation, slots, registered prices,
latency and correction arithmetic. It checks nonnegative sampled cash, rather
than authenticating a live cash balance. Unlike the processing attribution's
full interior reconciliation, this battery audit primarily reconciles **final**
ledger cash/units/marks; it does not independently prove every interior equity
mark correct. It cannot prove quote availability, historical limits, own fills,
queue allocation, real throughput, item eligibility or economic profitability.

## 2. What could be known without forecasting prices

Alchemy is the cleanest theoretical counterargument to forecast failure. Once a
valid item and a nature rune are owned, high alchemy exchanges them for a fixed
coin amount. GE tax belongs to a GE seller, not the buyer; the spell itself is
not a GE sale. Thus subtract the actually paid item and rune costs, fire/setup
costs and time, not an imaginary buyer tax. A fire staff is the explicit existing
assumption. The alchemy value is a conversion value, not an unconditional market
price floor: casting time, eligibility and buy limits permit prices below it.
A positive low-side mean gap might be available to passive buying; a positive
high-side mean gap is a stronger screening diagnostic, still not a fill guarantee.
Measure both, volume and limits, rather than assume either free money or no edge.

Processing has a weaker guarantee. Owned bow inputs produce a known output
quantity, but its *sale proceeds* remain unknown until sold. Subtract all input
purchase costs and output seller tax. The input sellers' taxes are already
embedded in their willingness to sell; charging our account tax on purchases
would double count. Report a deliberately extra input-tax stress separately if
useful, never as the actual tax rule. Ores and potions require full recipes,
secondary ingredients, yields and unlocks; a pairwise price ratio is not a
conversion ledger. Prefer the two already specified bow recipes over inventing
new incomplete recipes.

Tax exemptions and rounding reduce an actual transaction cost; buy limits cap
capacity and can fragment supply. A patient account might service small slow
orders that larger accounts avoid, but waiting itself creates no queue priority
or guaranteed spread capture. Evidence must survive actual time, stranded legs,
limits and capital occupancy. The archive can settle arithmetic conversion
margins and necessary capacity ceilings; it cannot settle allocation to our offer.

### Mechanical economics measured on the daily folds

The daily panel supplies 341,047 rows across 84 development timestamps. Requiring
positive noninverted sides, positive side volumes, positive current alch value,
known positive limit, and a same-availability valid nature-rune observation leaves
**254,377 item-days / 3,910 items**. No missing leg is interpolated. Nature-rune
high-side prices range **119–144 GP**, median 125.5. The low-side screen uses
item low plus rune **high**, so it does not assume both legs buy passively.
Both screens charge ceilings of 10bps adverse cost on *each* input.

Pasted output:

```text
DAILY valid eligible item-days 254377 days 84 items 3910 nature high min/median/max 119 125.5 144
ALCHEMY {"side": "low", "eligible": 254377, "raw_positive": 24819, "positive": 24622, "days": 84, "items": 724, "gap_min": 1.0, "gap_median": 327.0, "gap_p90": 910.0, "gap_max": 54548.0, "reported_volume": 1462107996, "rune_cost_sum": 3140495, "rune_cost_median": 126.0, "positive_capacity_rows": 15741, "capacity_median": 26.0, "gross_gap_sum": 14960774, "net_gap_sum": 11398956}
ALCHEMY {"side": "high", "eligible": 254377, "raw_positive": 14157, "positive": 13915, "days": 84, "items": 485, "gap_min": 1.0, "gap_median": 179.0, "gap_p90": 514.0, "gap_max": 8276.0, "reported_volume": 1197119730, "rune_cost_sum": 1776576, "rune_cost_median": 126.0, "positive_capacity_rows": 10662, "capacity_median": 26.0, "gross_gap_sum": 5377975, "net_gap_sum": 3422903}
BOW SPREADS
Magic longbow days 84 positive 84 gap min/median/max 37.0 114.0 219.0 output tax median 24.0 positive with extra input-tax stress 84
Yew longbow days 84 positive 84 gap min/median/max 112.0 156.5 212.0 output tax median 10.0 positive with extra input-tax stress 84
PASS: development-only descriptive diagnostics; no fits, new profit tests or holdout observations
```

Low-side gaps are positive on **9.68%** of eligible item-days, across all 84 days
and 724 items; high-side gaps on **5.47%**, all 84 days and 485 items. Positive
rows contain respectively **1.462bn / 1.197bn reported side units** in aggregate.
This is summed historical market activity across items and days, not available
inventory or capacity for one account. At the fixed 1% volume share, one current
buy allowance, 1M GP input budget and 916 daily casts, **15,741 / 10,662** positive
rows permit at least one hypothetical matched unit. Median capacity among those
rows is just **26**: rare high percentage margins are a poor ranking objective.
Rune volume is a shared resource; summing candidate capacities would double count
it and daily casting time. These calculations never prove any positive own fill.

Examples fixed for the subsequent direct-alchemy tool (machine output):

```text
{'name': 'Magic longbow', 'high_alch': 1536, 'buy_limit': 18000} {'days': 83, 'positive_high': 83, 'high_median': 1220.0, 'rune_high_median': 126.0, 'gap_median': 189.0, 'high_volume': 62796630, 'high_volume_median': 740042.0, 'capacity_median': 742.0, 'low_gap_median': 202.0}
{'name': 'Yew longbow', 'high_alch': 768, 'buy_limit': 18000} {'days': 84, 'positive_high': 84, 'high_median': 527.5, 'rune_high_median': 125.5, 'gap_median': 107.0, 'high_volume': 43862614, 'high_volume_median': 507454.0, 'capacity_median': 916.0, 'low_gap_median': 119.0}
{'name': 'Rune javelin tips', 'high_alch': 810, 'buy_limit': 10000} {'days': 84, 'positive_high': 84, 'high_median': 481.0, 'rune_high_median': 125.5, 'gap_median': 201.5, 'high_volume': 74546448, 'high_volume_median': 886919.0, 'capacity_median': 916.0, 'low_gap_median': 209.5}
{'name': 'Dragon javelin tips', 'high_alch': 1170, 'buy_limit': 10000} {'days': 84, 'positive_high': 84, 'high_median': 837.5, 'rune_high_median': 125.5, 'gap_median': 205.0, 'high_volume': 31681790, 'high_volume_median': 359508.5, 'capacity_median': 916.0, 'low_gap_median': 223.5}
```

How much do runes and tax eat? Across positive low rows, raw item-to-alch gaps
sum to 14,960,774 GP for one unit of each row; rune high costs sum to 3,140,495;
after both input ceiling costs, 11,398,956 remains. Across positive high rows,
the corresponding numbers are 5,377,975, 1,776,576 and 3,422,903 GP. These are
one-unit arithmetic decompositions, not a portfolio. No GE tax is owed by our
buyer on either input or by the spell's coin conversion. A resold stranded item
would pay seller tax; the archived simulated marks already deduct it. The median
189 GP magic-bow gap is before casting time/setup: at 1,000 casts/hour, time
valued at 100,000 GP/hour costs 100 GP/cast plus setup time. A gap is not free
money, but these volumes plainly contradict "only untransactable scraps".

The old alchemy account made **16 submissions, zero productions**, and purchased
only **1,957 nature runes for 245,353 GP**. It paid 1,500 setup. It never purchased
an alchable item. The nominal +24,073 is the rune mark, not alchemy payoff. Its
highest margin/capital choices and frozen ceilings did not obtain the item leg;
therefore zero casts neither establishes nor refutes the four liquid candidates.
I will not change the old rule to rescue it.

Processing is also not obviously arbitraged to zero in this archive. Both fixed
bow recipes have positive same-timestamp crossed-average conversion margins on
**84/84 days**: magic 37–219 GP/unit (median 114), yew 112–212 (median156.5),
after output tax (median 24/10) and adverse input/output rounding. Even an extra,
**counterfactual** 2% input-price tax stress leaves all 84 days positive. Actual
buyers owe no such input tax. If one buys and resells input inventory, however,
that resale genuinely pays tax in addition to any later output sale; do not
confuse that lifecycle with buying recipe inputs.

The independently attributed old 1% processing account reports **2,115,300 GP
of decision conversion spread**, −60,977 input movement, −220 output movement,
= **2,054,103 simulated realized GP**, then −289,342 unrealized input losses
= +1,764,761 net. Thus its positive component was already visible at decision
time rather than a fortunate output-price forecast. Eight completions and
adjusted p=1 still cannot establish expected profit. Partial-leg and future
output-price risks remain. Combining stringing with alchemy would fix the output
coin amount but add casting time and a third input; it deserves one fixed
hypothesis, not an unexplored recipe sweep.

The tax wedge and buy-limit structure offer a plausible *service niche*: accept
active conversion labor and limited batch size to turn cheap supply into coins.
They do not establish a passive-account advantage. The four examples have
10,000/18,000 unit current limits, versus <=916 casts/day: within a single batch,
casting time and budget bind before those full allowances. Remaining limits
could still bind if the account has traded earlier. A patient account may obtain
cheaper item fills, but waiting can consume more active time and money; only own
records resolve that. The data settle necessary arithmetic and volume scales,
not queue allocation or an attainable daily GP rate.

Mechanics checked against [High Level Alchemy](https://oldschool.runescape.wiki/w/High_alchemy),
[Grand Exchange](https://oldschool.runescape.wiki/w/Grand_exchange), and the
[bow recipe](https://oldschool.runescape.wiki/w/Money_making_guide/Stringing_magic_longbows).
Only mechanics inform this argument; live/cached prices on web pages are not
evaluation observations. The existing 1,000 casts/hour and 1,800 strings/hour
remain conservative planning assumptions, not measured human throughput.

## 3. Necessary, falsifiable conditions

1. A legal conversion or completed sale pays more than all paid inputs, tax,
   setup and a fixed value of active time. Archive screens can disprove positive
   aggregate margins; only own fills establish paid costs and proceeds.
2. Enough matching input units can actually be obtained within limits, cash,
   slots and the declared deadline. Archive volumes give ceilings; own orders
   must identify allocation, cancellations and partial-leg risk.
3. The margin is available repeatedly, rather than depending on one discontinuity
   or a terminal inventory mark. Development attribution can diagnose this;
   prospective completed cycles must establish recurrence.
4. One account can execute the conversion at the declared rate with the required
   skills, valid item variants and setup. Metadata/recipe checks help; measured
   own conversion records establish eligibility and throughput.
5. The resulting account return remains positive after failed attempts, residual
   inventory liquidation and the fixed time charge. Historical hypothetical
   ledgers check conservation; own records establish economic performance.
6. Any statistical claim survives dependence, the frozen family and sufficient
   activity. Whole-calendar block bootstrap can assess observed paths; it
   cannot repair unobserved fills. No Gaussian inference is planned.

### Verdict on necessary conditions

The six conditions above remain the falsifiable gates. Development data support
positive *aggregate arithmetic* for alchemy and bows and ample reported volume
for named candidates; reject the assertion that this archive has no mechanical
gaps. Execution and active time remain unmeasured. None of conditions 1–5 is
fully established for an actual account. The unchanged audit establishes
conservation, not the unknown fills. Condition 6 has failed for the completed
historical battery. Stop more forecast sweeps; do not deploy from these means.

## 4. Next battery, frozen before its outcomes

Exactly **four** economic hypotheses; no extra participation grid, recipe, hold
horizon, item variant or exclusion. This is a *prospective own-record* battery,
not another test on these inspected daily averages. It is registered now and is
**not run** without actual operator records. The old holdout remains sealed;
subsequent aggregate market prices cannot substitute for own executions.

| Hypothesis | Mechanism | Fixed candidate/input set |
| --- | --- | --- |
| H1 | Buy and high-alch liquid finished goods; no output sale forecast | 855,859,19580,19582 plus owned561; choose highest positive cap-surplus per total input capital, stable item-ID ties |
| H2 | String magic bows and sell output | 70+1777 ->859 |
| H3 | String yew bows and sell output | 66+1777 ->855 |
| H4 | String magic bows and high-alch output | 70+1777+561 ->1536 coins |

A new enrollment timestamp (not backdated) fixes the next UTC midnight as day0
and 56 full recording days. Assign days by UTC-day index modulo 4 to H1/H2/H3/H4;
no substitution if the assigned arm is unavailable. One dedicated 10M GP account,
eight slots, one unfinished batch globally, <=1M GP total paid inputs/setup per
batch, <=one active hour/day. Production assumptions for pretrade screening:
1,000 casts/hour,1,800 strings/hour, five minutes setup per production session;
combined H4 unit time is the **sum** of stringing and casting time. Buy limits
are actual recorded remaining four-hour allowances, never six invented resets.
Nature runes must already be owned and costed before H1 item submission; rune
acquisition cost/time/failures are assigned to H1, never free inventory. H4
likewise retains all third-leg costs and failures. Initial staff charge 1,500 GP
unless previously owned at enrollment; do not discard a fee by resetting a batch.

At each assigned first daily session, record no-attempt/reason or all candidate
quotes before any order. Apply conservative10bps input ceilings/output markdowns
for screening, integer 2% current seller tax, and **100,000 GP per recorded active
hour** as the fixed economic hurdle. H1 caps the item purchase price using the
fixed alch payoff and the *paid* rune cost, requiring strictly positive surplus
after all setup and time charges. At most 72h for input offers, no raising frozen
caps or switching candidate after a failed offer. Retain partials; produce only
owned matched inputs. For H2/H3 submit output at the original after-tax positive
screened output reference, for <=72h; cancellations/requotes and any later sales
remain actual records and their time is charged. No new input submissions in the
last seven days. Log decisions, rune purchases, orders, cancellations, fills,
conversions, actual tax, active seconds and reconciled cash/units, including busy
and zero-fill days. Shared-capacity busy days remain in the assigned arm with
zero new submissions; each event's cash/time remains charged to its originating
arm. No order placement is authorized or automated by this implementation.

Primary statistic per arm: sum of actual daily cash changes, less 100,000 GP/hour
of **all** recorded active time (checks, purchases, failed attempts, production,
liquidation) and setup, with zero terminal credit for unsold inventory. Initial
cash is partitioned by origin in one conserved account; transfers are not profits.
Actual purchase debits for leftovers stay in the statistic; book or average-price
marks cannot rescue it. Report realized conversion/sale margin and remaining
book/units separately. No terminal liquidation price is invented. No-attempt
days are zero only when an actual session record confirms them; missing records
make inference inconclusive. Expenses incurred before a batch count too.

Use empirical whole-calendar moving blocks 7 and 14 days,20,000 draws, seed42,
shared across arms, on the complete 56-day cash/time increment grid. Require
>=10 completed cycles **per arm**, all daily sessions reconciled, no missing
cost/time/evidence, and nonconstant increments. Otherwise p=1/inconclusive.
Use worse centered-null one-sided p and ordinary95% inverted-CDF intervals.
Require positive lower bounds for both blocks and Bonferroni adjusted p<.05.
Reserve **217 tests =213 prior profit tests+4 new** (no claim to correct the full
adaptive history). No Gaussian approximation or batch-as-independent t-test.
If an arm fails or lacks activity, report it; do not extend the window or reduce
the hurdle until something passes. The window may prove underpowered; that is
preferable to calling 14 possible decision sessions independent replication.

**Implementation selected before new outcomes:** implement only the H1 offline
cost-cap planner and reproducible sealed daily mechanical screen. Require owned,
explicitly costed runes, actual remaining allowance and cash; cap quantity by
runes, casts, input budget and remaining limit; report a conditional maximum item
price and time-adjusted surplus. Defaults charge staff once and five minutes setup;
an operator may explicitly declare the staff already paid. The planner cannot
assert ownership from averages, execute trades, certify evidence, estimate fills
or claim observed profit. Restrict it to the four named IDs/known alch values;
refuse changed metadata, invalid/duplicate IDs, missing/invalid legs and sealed
rows. A screen is a diagnostic of means, not a new battery outcome. Existing
processing intake remains untouched. No unmeasured actual trial is initialized
or retrospectively populated from historical averages.

Best remaining bet: **direct high alchemy of the fixed liquid candidates at
strict cost caps**, measured with actual own fills and actual active time. Unlike
processing, it eliminates the output sale forecast. Repeated crossed-average
margins and large source volume support attempting measurement. It is falsified
as an economically useful account strategy if owned matched inputs cannot be
obtained at the caps, if actual eligibility/throughput fails, or if the complete
56-day cash return fails to cover the fixed active-time hurdle after all failed
attempts and leftovers. Failure of significance alone means unestablished,
not proof of negative expectation. No forecast trading deployment is supported.

Reproduce diagnostic calculations (all artifacts outside Git):

```bash
OSRS_DATA_DIR=/home/martin/osrs-data ml/.venv/bin/python -u \
  /home/martin/osrs-data/deliberation-diagnostics.py
OSRS_DATA_DIR=/home/martin/osrs-data ml/.venv/bin/python -m osrs_ml.battery_audit \
  /home/martin/osrs-data/strategy-battery-v1
```

Exploration encountered missing opposite means, a missing terminal low mean,
a one-GP sale below legal post-slippage granularity, and empty daily fill schemas.
Four preliminary attempts failed before completing; no alternative outcomes were
selected. The final script counts unresolved opposite prices, retains the original
zero missing-side mark, and handles no-fill accounts explicitly. The descriptive
specification and source values were not tuned. Baseline verification before any
implementation: `245 passed in 34.60s`. Unit-test arithmetic is not market data;
new research computations use only actual archived observations.

Integrity anchors for the descriptive execution:

```text
deliberation-diagnostics.py 0372b384092d799e0dfe74617faf3f9892b320e67b417bae9d4e8fb3ee873838
alchemy-summary.csv b83cf424a19a11919ecd09cf1f43a24a76b0c88db323e8147da55af70e9f6d59
patient-episodes.csv debe746fcd9353fb50aa39526e4c45f2b6bf3e4565a8ea542188bda0592f6d36
patient-summary.csv 9eb960f7678b86a75ffabdfe84299c583faf6742982cf25596699a622f35dbf0
```
