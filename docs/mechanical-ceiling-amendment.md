# Source and physical-capacity corrections to sensitivity v1

The first descriptive run is retained at mechanical-ceiling-v1 outside Git.
No candidate or profitable-day filter changes. These changes address mechanics,
not outcome maximization, before the final v2 report:

- The GE exemption list includes **Saw (8794)**. Apply zero seller tax to that
  product. All other catalogue sale items retain the existing integer 2% policy.
  Source: https://oldschool.runescape.wiki/w/Grand_exchange#Exempt_from_tax .
- The initial generic 400–800 ordinary-furnace range is too generous for high-coal
  inventory loads. At 27 ingredient slots, runite fits three bars before banking;
  the OSRS Wiki's ordinary Edgeville guide uses 400/hour. Use runite 300–400,
  adamant 350–500 and mithril 400–600; other bars retain 400–800. These remain
  unmeasured assumptions, with no coal bag, catalyst or diary bonus.
  Source: https://oldschool.runescape.wiki/w/Money_making_guide/Smelting_runite_bars .
- Reduce all four walking sawmill planning rates to 500–1,000/hour. The documented
  fast 20-second route requires paid teleports, while this model buys none.
  This deliberately conservative transport assumption replaces 1,000–2,000;
  it is not a newly measured rate or an optimized route.
  Source: https://oldschool.runescape.wiki/w/Sawmill#Making_planks .

Also state explicitly: the 1,500 GP staff cost is reserved inside the 1M GP batch
budget on every casting example, but expensed only once on first production.
Other tools (pestle/mortar, mould) and access are assumed already owned. Retained
margin is a stress allowance charged before cash sizing; for fixed vendor goods
it is a reserved sale-realization allowance, not a claim that the vendor charges
more than the fixed price. No membership/level/diary acquisition return is included.

The stricter all-leg noninversion gate leaves 75 magic/76 yew bow days rather
than the previous 84: bow strings have eight inverted days, unstrung magic one,
and finished magic one (overlap accounted for). Missing/rejected days stay in
all 84 daily income denominators, with a charged check and zero production.
This is the original cycle's validity rule applied consistently to every leg,
not an exclusion based on profitability.
