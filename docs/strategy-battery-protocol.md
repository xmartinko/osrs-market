# Broad strategy battery v1 — frozen before outcomes

Registered 2026-10-29 on `ml/financial-model`, following `3a7fa03`.
The objective is positive expected GP after costs and account capacity, at any
timescale. Calendar/regime/event features are permitted by the corrected scope;
this finite battery does not need them. Earlier reversal diagnostics motivate
these hypotheses: this is **not independent confirmation** of that discovery.
Do not tune or replace a failed rule. Every registered row must be reported.

## Data boundary and provenance

`OSRS_DATA_DIR=/home/martin/osrs-data`; private research only. No C++ changes.
Reserved daily holdout begins at Unix **1785024300**. Never unlock it, read its
market columns, or use later market observations as a substitute evaluation set.
Project/filter parquet through DuckDB before materializing data. Weekly input is
the already sealed `ge-tracker-weekly-v1/weekly.parquet`; verify its manifest and
hash and require `available_at < holdout_start` everywhere. Daily and intraday
inputs are `assembled-v3/{daily,intraday_1h,intraday_5m}.parquet` with their hashes.
Current `items.parquet` provides only IDs, names, buy limits and high-alch values;
these are present-day metadata sensitivities, never claimed historical revisions.
Forward bucket dates/counts may be read for coverage, but no post-boundary prices.
No interpolation, bridge data, synthetic market/training data or Gaussian draws.

Use the union of the three existing contiguous development folds for a single
daily/intraday account (1777766700 <= availability < 1785024300). Earlier rows
within development are causal feature context only. Weekly evaluation is one
continuous account from 2020-01-01 until the sealed boundary, with earlier rows
for causal features. Report annual diagnostics without selecting eras. Resolution
300 seconds for 5m, 3600 for 1h/4h, 86400 for daily, 604800 for weekly.
No upsampling. Lack of eligible observations is inconclusive, not no-trade proof.

## Enumerated hypotheses

The executable enumeration lives in `ml/strategy-battery-v1.json` and is committed
with this document before strategy outcomes are computed. There are **71 rules**:

* 24 directional rules: {cross-sectional reversal, cross-sectional momentum,
  absolute reversal, absolute momentum} x {5m,1h,4h,1d,1w,4w}. Lookback and
  minimum holding equal the named horizon. Rank rules select the upper decile,
  require the intended return sign, and rank by absolute return. Absolute rules
  require moves of respectively 0.5%,1%,2%,5%,10%,20%. Long-only; no fictitious
  shorts. Exact lag endpoints only. Price is side midpoint (daily/intraday) or
  overallPrice (weekly); inverted or nonpositive sides and zero side volumes are
  ineligible signals.
* Eight patient reversals: daily 7d lookback, >=10% fall, hold {3,7,14,28}d;
  weekly 4w lookback, >=20% fall, hold {1,2,4,8}w. At most one new ranked
  candidate every two calendar days on daily data; one per weekly decision on
  weekly data. Require estimated full reversal margin minus 2% tax and 20bps
  round-trip slippage >=8%. Four slots, 25% of initial capital per position.
  No extra trading near evaluation end (stop entries holding+3 buckets before
  end). No return target calibrated from future prices. Positions may remain
  unsold; report their marked share and cash/realized profit.
* Twelve cross-item rules: {input leads output, ratio convergence} x
  {herbs/potions, ores/bars, raw/processed/shared resource} x {1d,1w}.
  Fixed pairs: (ranarr,prayer potion(4)), (snapdragon,super restore(4)),
  (toadflax,Saradomin brew(4)); (iron ore,iron bar), (coal,steel bar),
  (runite ore,runite bar); (raw shark,shark), (magic logs,magic longbow),
  (dragon bones,superior dragon bones). IDs/names resolved from metadata only;
  absent pairs remain absent. Lead rule buys output when input horizon return
  exceeds output by >=5%. Convergence buys the cheaper relative leg when log
  price ratio deviates >=10% from its past 8 exact-bucket mean; no short other
  leg. Ratio history includes current completed bucket; no future fit. Top decile
  within the fixed pair signals; holding equals horizon. No mined correlations.
* Nine liquidity rules: {persistent spread, volume shock continuation,
  buy-limit-aware spread} x {1d,1w,4w}. Persistent spread requires each of the
  past four exact buckets to have after-tax side spread >0; rank their mean.
  Volume shock requires current min side volume >=2 times prior four-bucket
  mean and positive horizon return; rank return times volume ratio. Limit-aware
  ranks positive net spread times min(current limit,1% of min side volume,
  1M GP / entry price). Upper decile; holding equals horizon.
* Three low-tax spread rules at {1d,1w,4w}: positive net spread, upper decile
  among current side prices <50GP or the fixed exemption subset (bronze/iron/
  steel arrows and darts, mind rune; bass,bread,cake,cooked chicken,cooked meat,
  herring,lobster,mackerel,meat pie,pike,salmon,shrimps,tuna; chisel,hammer,
  needle,pestle and mortar,rake,saw,secateurs,seed dibber,shears,spade).
  Apply these exemptions only in these three rules; elsewhere default tax is a
  conservative current-policy counterfactual. Exemption subset intentionally
  excludes bonds and items whose charges/variants need extra state.
* Three mechanical rules at daily decisions: high alchemy across items with
  positive current alch values; processing a fixed mix of {magic longbow(u)+bow
  string -> magic longbow, yew longbow(u)+bow string -> yew longbow}; and
  shop-to-GE (feather, fire rune). Shop observations, stock/restock and travel
  costs do not exist in the archive: report **unidentified**, no profit claim.
  Alchemy assumes 55 Magic, a paid 1,500GP fire staff once per account, one nature
  rune per item, 1,000 casts/hour and at most one active hour per day. Processing
  assumes requisite Fletching, 1,800 bows/hour, one active hour/day. Spend five
  minutes of that hour on setup, leaving 55 minutes production. Buy inputs at
  observed high side +10bps in subsequent complete buckets, with limits,
  participation, 10M cash, 1M GP budget per production batch and eight slots.
  Carry partial leg inventory at conservative marks; never assume atomic input
  fills. Choose margin/capital descending from completed decision prices, stable
  ID ties, one recipe at a time. Produce only owned matched inputs, at the next
  decision after purchases; output sales consume a later full bucket, observed
  low -10bps, default per-unit tax. Alchemy coins have no GE tax. Runes and output
  have their own participation/limits. Record active hours separately from elapsed
  GP/hour. No shop success may be inferred from listed GE prices alone.
* Twelve volatility/range rules: {inverse-volatility reversal sizing, range-aware
  spread selection} x the six horizons. Volatility is std of four consecutive
  exact-horizon log returns. Size variant uses the corresponding cross-sectional
  reversal signal; position allocation is min(10%,10% * .05/max(vol,.01)) of
  initial capital. Range variant ranks min(positive net spread fraction, mean
  absolute return over four exact horizons), upper decile; holding equals horizon.
  Report forecast diagnostic Spearman between lagged volatility/range and future
  absolute horizon returns; the profit test is primary, never infer directional
  profitability from a positive range correlation. For sizing also test paired
  net increment improvement over the corresponding plain reversal. Its primary
  p is the worse of positive-profit and improvement p; no separate free test.

## Shared execution and account definitions

Every rule uses 10M GP, eight slots, 10% initial-capital allocation unless patient.
Predeclared participation scenarios **0.1%,1%,5%** are separate tests, including
unavailable rules: family size **213**. No extra break-even search or interpolation.
Baseline is no-trade exactly zero. Patient entries are throttled before execution,
so an unfilled chosen item cannot trigger a same-date search for another item.

Trading uses existing `backtest.simulate`, `integer_lots_v2`,
`volume_bounded_v3`, mean-proxy qualification, passive frozen limits, 10bps
adverse slippage per side, 300s latency, 1% terminal haircut, no queue multiplier.
Buy timeout is three source buckets +300s; freshness upper bound is two buckets
+300s. Entire fill buckets must follow submission/latency and fit buy timeout.
Volatility sizing groups candidate budgets by a causal score map; extending the
Python executor with optional per-decision allocation is allowed, default
behavior must remain identical. Tax is today's 2% floored per unit, <50 exempt,
5M cap, applied counterfactually in old eras. Unknown limits forbid buying.
Mechanical purchases cross the spread and use observed-side-volume constraints;
they remain hypothetical aggregate-price fills, never calibrated live fills.

No entry when fewer than holding+three buckets remain. Final inventory is marked,
never called a sale. Gross GP restores simulated tax and adverse price costs,
including end inventory adjustments; it is a same-fill accounting diagnostic.
Report net GP, elapsed GP/hour, active GP/hour where relevant, return/10M GP,
drawdown, completed position count and buy/sell fill counts, turnover, mean/peak
capital, units and matched-volume share. Required participation is observed peak
bucket use plus the first positive **registered** scenario, not an attainable
continuous threshold. Weekly side counts are used only as reported weekly counts;
no daily split or limit resets are invented inside a weekly bucket. A purchase
in one weekly bucket is capped at a single current four-hour buy allowance.

## One-shot uncertainty, search correction and decision

Empirical circular moving-block bootstrap of **account equity increments**, with
whole timestamps shared across rules, preserves cross-item dependence and local
serial dependence. Daily blocks: max(7d,holding) and twice that. Intraday blocks:
max(1d,holding), twice that. Weekly blocks: max(4w,holding), twice that. Use
20,000 draws, seed42, one-sided centered-null bootstrap p=(1+number of centered
bootstrap sums >= observed sum)/(20001); also ordinary 95% percentile intervals.
These are conditional inference on marked paths, not account re-simulations or
an execution-uncertainty model. No Gaussian assumption.

Require >=4 times the larger block length in observed elapsed buckets, >=10
completed positions, and both buy and output sale/coin realization activity.
All unavailable, inadequate, constant/nonpositive inactive results receive p=1
for correction; report reason. Use the worse p of the two block lengths.
Bonferroni p_adj=min(1,213*p); pass only p_adj<.05 and positive net at both
blocks' lower bounds. Vol sizing also needs paired improvement as above. Report
annual results, count profitable years and terminal-mark dependence; do not turn
pooled evidence into an all-era profitability claim. Secondary diagnostics cannot
rescue failed primary tests. No tuning, winsorization or post-hoc exclusions.

Report all 213 scenario rows in an aggregate CSV and all 71 rules in a readable
table (1% planning case plus registered-share summary), including null and
unidentified results. Highlight the best raw net GP result and its raw/adjusted p,
the familywise 5% threshold .05/213, and expected 10.65 pointwise 5% false positives
under an all-null family (dependence does not change that expectation).
Correction addresses this finite battery, **not** the full prior research history.
Recommend only a prospective capacity/fill test for corrected survivors; do not
claim realized profits from aggregate history. If no result survives, say that
this battery found no established deployable edge, not that the market has none.

Mechanical references checked before evaluation: [alchemy mechanics](https://oldschool.runescape.wiki/w/High_level_alchemy),
[casting cap](https://oldschool.runescape.wiki/w/Market_watch_high_alchemy),
[bow inputs and throughput](https://oldschool.runescape.wiki/w/Money_making_guide/Stringing_magic_longbows),
[current tax exemptions](https://oldschool.runescape.wiki/w/Grand_Exchange).
Current example market prices on those pages are not evaluation observations.
