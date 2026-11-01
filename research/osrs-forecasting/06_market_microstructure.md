# Market microstructure and hypothetical economics

Phase Zero, 2026-11-01. Evidence-backed facts below concern public feeds and rules; none demonstrates archive quality or executable profits. Archive evidence belongs in `01_data_archive_audit.md`.

## Observations and structural breaks

The feed publisher distinguishes latest directional transaction observations from interval averages and volumes. Aggregate timestamps denote interval starts; publication follows completion. Its documentation identifies 2026-09-30 as the change from RuneLite reporting to Jagex reporting across clients. These data are neither standing quotes nor an order book. [Publisher documentation](https://oldschool.runescape.wiki/w/RuneScape%3AReal-time_Prices).

Research implications (deductions): asynchronous last trades can create apparent negative spreads; repeated prices need not mean new transactions; missing intervals need not imply zero demand. A midpoint of directional averages is a statistical target, not a transaction that occurred. Total directional volume cannot identify queue position, fill probability, depth, or market impact. Separate missing side, missing collector response, zero reported volume, unchanged observation timestamp, and newly created item.

The same 2026-09-30 update enabled higher-value GE trades and changed guide prices from at most 5% every 24 hours to 20% every three hours, including more updates for low-volume items. The tax cap remained 5M GP per item and buy limits remained unchanged. Thus a measured discontinuity cannot automatically be attributed to reporting coverage alone. [Jagex update](https://secure.runescape.com/m=news/ge-improvements-beyond-max-cash?oldschool=1).

Pre-register common-item comparisons around the break: missingness, observed directional volume, return quantiles, stale durations, and effective item coverage. Match weekday/hour and liquid/illiquid strata; repeat excluding release-day windows and expensive newly observable items. This is descriptive break analysis, not causal identification. Do not estimate an all-client volume conversion factor from pooled before/after means.

## Tax and account constraints

Jagex introduced a per-unit seller tax on 2021-12-09 at 1%, rounded down and capped at 5M GP; some tools and bonds were exempt. [Original rule](https://secure.runescape.com/m=news/grand-exchange-tax--item-sink?oldschool=1). On 2025-05-29 the rate became 2% for **new** offers, existing offers retained 1%, and more low-tier consumables became exempt. Unknown historical offer creation dates require transition bounds. [Jagex change](https://secure.runescape.com/m=news/yama-cas--more?oldschool=1).

For integer per-unit sale price p and applicable historical exemption flag e:

`tax(p, date, offer_cohort, e) = 0 if exempt; otherwise min(floor(rate * p), 5_000_000)`.

At the current 2% rate, 49 GP has zero tax and 50 GP incurs one GP; the cap begins at 250M GP. These are arithmetic deductions. The existing project warning about `exempt_through_gp=50` therefore requires correction and independent boundary checks in a later authorized implementation phase. Do not silently use the old default in reported net returns. Apply rounding per unit before multiplication by quantity. Do not apply current exemptions to historical dates without evidence.

The documented GE account constraints include eight member slots versus three free-player slots; purchase limits reset four hours after the first purchase and can be shared across related item variants. Archive present-day metadata is not proof of historical limits. [GE mechanics](https://oldschool.runescape.wiki/w/Grand_exchange), [buy-limit documentation](https://oldschool.runescape.wiki/w/Buying_limit). Maintain dated item-ID exemption and shared-limit-group tables; reject capacity claims when these are unknown. Sell orders occupy slots and capital/inventory can remain locked pending completion.

## Five levels of claim

| Level | Meaning | Permitted evidence |
|---|---|---|
| Forecast accuracy | Better held-out distributions for a defined observable | Proper scores, calibration, dependence-aware uncertainty |
| Gross opportunity | Favorable hypothetical future price differences | Explicit reference-price definition; no fill claim |
| Tax-adjusted opportunity | Reference-price opportunity after dated tax | Correct exemptions, rounding and caps |
| Conservative simulation | Scenario outcomes under stated delays/fills/capacity | Sensitivity results and inventory/capital ledger |
| Executability | Actual attainable outcome | Requires authorized real execution observations; presently unverified |

## Proposed paper evaluation; no live execution

Freeze one simple decision rule on validation, for example trade only if predicted tax-adjusted expected gain exceeds a fixed cost/risk buffer; choose size subject to downside and exposure limits. Compare to the same rule using no-change and empirical-return distributions, plus a no-trade policy. A distribution cannot be credited for a more extensively tuned policy.

Proposed scenario parameters, not measurements: initial 10M and 100M GP balances; long-only, no borrowing, eight slots for a member account; 10% capital maximum per item, 50% total invested maximum; participation caps 0.1%, 0.5%, 1% of observed relevant-side volume. These fractions are sensitivity settings, not validated safe capacity, especially before the coverage break. Require past-only sizing and next-available execution windows. Test delays of one and two completed bars; one additional bar adverse holding-period extension; adverse prices of 0, 0.5, 1, 2% plus integer rounding; and incomplete/zero fills.

Aggressive proxy scenario: future completed high-side reference for entry, low-side reference for exit, then adverse costs and seller tax. These averages do not bound actual fills. Passive scenario: crossing an aggregate reference never guarantees an order filled; report conditional outcomes across 0%, 25%, 50% fill assumptions, including adverse-selection stress. Include the zero-fill case. Aggregates alone provide no nontrivial guaranteed profit lower bound.

For a hypothetical completed round trip, `net_GP = q * (exit_price - tax(exit_price) - entry_price) - other_scenario_costs`. Report realized/scenario cash, inventory marked at conservative liquidation proxy, unliquidated inventory, drawdown, turnover, capital-days, concentration, rejected orders, slot occupancy and purchase-limit utilization. Never mark stranded inventory as cash profit. All probabilities of barrier hits are probabilities for the modeled observable at its resolution; intrabar crossing order remains unidentifiable from averages.

## Recommendation

High confidence: predictive research is meaningful independently of execution. Low confidence: aggregate-only economic evaluation can establish real-world opportunity. Require calibration and robustness across cost/delay scenarios before promoting any forecast to a paper policy. Stop economic claims if gains depend on contemporaneous fills, use guide prices as execution prices, or vanish under one-bar delay. No trading, game-account automation, or dataset mutation was performed.
