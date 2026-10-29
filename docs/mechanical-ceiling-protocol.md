# Mechanical capacity sensitivity v1

Registered before this cycle's capacity or new-family outcomes. Forecast sweeps
remain closed; the four prospective hypotheses in mechanical-edge-v1.json are
unchanged and will not be run on averages. This is descriptive arithmetic on the
84 daily development timestamps [1777766700,1785024300), loaded through the
existing provenance-checked sealed loader. No weekly data or holdout market fields.
No significance test, normal approximation, synthetic observation, or strategy
selection. Current metadata/mechanics are conditional historical sensitivities.

Report every member, failures, missing legs and zero-volume capacities. All price
inputs are archive side averages, never quotes or own fills. Prices use the
previous screen's conservative per-unit 10bps adverse rounding for comparability;
output sales pay the existing integer 2% seller tax. Alchemy buys and conversion
pay no seller tax. A 1,500 GP fire staff is charged once on first use, not daily.

Frozen candidate accounting examples, separately (never summed): direct alchemy
855/859/19580/19582 +561; 70+1777 ->859; 66+1777 ->855;
70+1777+561 ->1536 coins. Account assumptions: members, required skills/unlocks,
10M GP cash, <=1M paid inputs/fees per batch, one unfinished batch, eight offer
slots, <=one active hour/day including setup. Use actual four-hour limit L for
one batch; 6L/day is only a continuous, fully reset theoretical bound. One batch
per day does not multiply L by six. Nature-rune allowance and volume are shared.
Report ingredient units, input capital, production time, and zero-fill bound.
No fill-latency/queue assumption can be verified from daily means.

Conditional endpoints (assumptions, not confidence bounds): cautious =600
casts/hour (1,200 clicks/hour, two per cast), 1,200 strings/hour, 15 minutes
interaction per attempted batch, 25% retained positive gap, 0.1% participation
on each input/output volume, and 25% completion of targeted matched quantity;
optimistic =1,200 casts/hour (2,400 clicks/hour), 1,800 strings/hour, five minutes
interaction, full observed adverse-rounded gap, 1% participation, full completion.
1,000 casts/hour (2,000 clicks/hour) is the reference. H4 adds string and cast
seconds; it gets no overlapping-time credit. Price retention raises input cost
by the lost positive gap before the cash cap. No matched fills means zero
production; a recorded attempt still consumes setup. Incomplete/stranded-leg
losses are unidentified; these are matched-cycle ceilings, not profit guarantees.

Reference sensitivity: 1,000 casts/hour, 1,800 strings/hour, five minutes setup,
full gap, 1% share, full completion, one daily batch. Vary one assumption at a
time: cast rate 600/1000/1200; retained gap .25/.5/1; participation 0/.001/.01;
matched completion 0/.25/1; setup 5/15 minutes; batch cadence .25/1 per real day.
A .25 cadence represents a 72-hour failed/partial offer plus daily-session delay,
not measured fill latency. Charge idle daily checks too. Daily income uses all
84 calendar days, missing or unprofitable days zero. Hourly income divides total
modeled GP by total interaction plus production time, never by 24h. Display
first-use staff expense separately. Daily p10/p90 are empirical dispersion only.

Other-family fixed catalogue, no ranking or search for a favourable variant:
all eight standard-tanner recipes (cow soft/hard, two snakes, four dragonhides),
four basic sawmill recipes (fees 100/250/500/1500), chocolate/unicorn/goat/nest
one-to-one grinding, seven deterministic ordinary-furnace bars (bronze, silver,
gold, steel/mithril/adamant/runite; coal 2/4/6/8), and gold bar -> gold bracelet
->330 coins with one nature rune. Exclude stochastic iron smelting, blast-furnace
coal discounts, spells, vouchers and other consumable savings. Scan vendor-to-GE
all five fixed-price sawmill shop goods (saw13, cloth650, bronze nails2, iron
nails5, steel nails3) and Zaff's fixed 7,000 GP diary barrel (15/30/60/120 daily,
mutually exclusive tiers). Ordinary variable-price shop stocks are not fixed
vendor-price opportunities and are not extrapolated at their first-unit price.

Other-family assumed production rates inclusive of banking/walking: tanning
1,000–2,000 units/hour; sawmill 1,000–2,000; grinding 1,000–3,000; ordinary furnace
400–800; gold bracelet crafting 600–1,000 plus 600–1,200 casts/hour; shop transport
200–800 units/hour. These are deliberately labelled planning ranges, not observed
throughput. Shop caps: <=1,000 initial stock per good per day, one world/store,
no assumed replenishment or hopping; the daily barrel quota supersedes that cap.
Restock and competition remain unmeasured, so zero stock is allowed. Use the same
one-hour, capital, side-volume, retention and completion sensitivities, five to
15 minutes setup. Shop GE purchases do not consume buy limits, but output sale
volume and cash/time still bind. No free acquisition of levels/diaries/membership.

Archive outputs, source and output hashes, verification and logs stay outside
Git under OSRS_DATA_DIR. Commit code before outcomes. Reconcile original alchemy
counts and one-unit sums; independently recompute representative capacity/tax
identities from source. Keep all original 245 tests passing and run lint.
