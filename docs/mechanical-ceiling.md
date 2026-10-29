# Mechanical account ceilings, 2026-10-30

Direct alchemy remains the best **measurement** candidate because its output is
fixed coins. A liquid direct example, dragon javelin tips, has a conditional
planning range of about **4,700–262,000 GP per active hour** and **1,347–249,151
GP per real day** before one-time staff when slow-cycle stress is included. These are assumptions
applied to development averages, not measured account profits or confidence
bounds. With daily completed batches the cautious endpoint is 13,626 GP/active
hour and 5,387 GP/day. Zero fills gives zero conversion profit; actual stranded
inputs can lose money. No positive executable lower bound is identified.

The dominant unknown is **matching fills at a retained margin**, including
competition, failures and the time until capital is released. Clicking speed is
secondary. The cautious/slow-cycle case fails the frozen 100,000 GP/active-hour
hurdle badly. This does not justify a dedicated account. A small actual-fill
calibration of the unchanged frozen candidates is still defensible; another
forecast sweep or average-price strategy replay is not.

The [registration](mechanical-ceiling-protocol.md) was committed as `3c5c1a5`
before outcomes, implementation as `c97a250`. The [source corrections](mechanical-ceiling-amendment.md)
retain v1 and lower unsupported transport/furnace rates plus exempt saws from
tax in v2. All generated data are outside Git. No frozen prospective trial was
run, no actual order was submitted, and no significance test was performed.

Evidence and assumptions
------------------------

**Measured:** 341,047 daily development rows, 84 timestamps, availability
1777766700–1784937900, strictly below sealed 1785024300. Provenance is checked
before market fields load; no weekly market data are used. Every recipe joins
only valid contemporaneous real legs: finite positive noninverted sides and
positive volumes on both sides. Rejected/missing days are zero-production days
in the 84-day income denominator, with assumed check time charged. No prices or
market observations are imputed. Current metadata and web mechanics are
conditional rules, not a historical reconstruction.

| Input | Status and justification |
| --- | --- |
| Cash / batch | **Assumption:** 10 M GP account, <=1 M inputs/fees per unfinished batch, inherited envelope; 9 M is idle. Reserve 1,500 inside casting batch budgets; expense staff once on first production. |
| Buy reset | **Documented rule:** four hours from first purchase. **Assumption:** full unused current allowance at each new batch; no prior competing account use. Use one allowance, never six invented fills. 6 L is only an ideal continuously reset 24 h bound. |
| Slots | **Documented rule:** eight members' offers. **Assumption:** one unfinished batch; direct uses two ingredient offers, bows two plus an output sale, combined three inputs. Never add income across rows. Slots are offers, not inventory stacks. |
| Alch actions | **Documented maximum:** one cast/3 s =1,200/hour. **Assumption:** 600/1,000/1,200 casts/hour, requiring 1,200/2,000/2,400 clicks/hour at two clicks/cast, plus setup/check actions. Missed ticks, breaks and extra UI actions make actual rates lower. |
| String actions | **Assumption:** 1,200–1,800 units/hour inclusive of banking, below the wiki's up-to-2,400 rate. H4 adds string and cast time; no simultaneous-work credit. |
| Nature / fire | **Measured nature high mean:** 119–144 GP, median 125.5; cost uses ceil(1.001×mean), one nature/cast. **Assumption:** fire staff supplies fire; first-use 1,500 GP cost; runes purchased/costed, no free stock. |
| Tax | **Documented/current-rule sensitivity:** seller pays floor(2%×sale price), cap 5 M/item, zero below 50; catalogue saw is exempt. Buyers and alchemy owe no seller tax. Resale of leftover inputs would pay tax and is not free. |
| Setup / cadence | **Assumption:** 5–15 active minutes every calendar day, including failed checks/acquisition; one batch/day or .25/day for 72 h offers plus daily check delay. Busy days retain their check time. |
| Margin / competition | **Assumption:** retain 25%/50%/100% of positive adverse-rounded gap; allocate 0/0.1%/1% of each required side's recorded volume; complete 0/25%/100% of target matched units. None is a measured fill probability. |
| Other resources | **Assumption:** existing membership, levels, quests, diaries, mould/pestle and required tools. Their acquisition is not free profit; no membership, training or diary return is claimed. Routes use walking/banking, no uncosted teleport/stamina supplies, bonus yields or free XP value. |

The cautious daily endpoint combines 600 casts/hour, 1,200 strings/hour, 15-minute
setup, 25% retained margin, 0.1% participation, 25% matched completion. The optimistic
endpoint combines 1,200 casts/hour, 1,800 strings/hour, 5-minute setup, full margin,
1% participation and full matching. Other-family rates (all **assumptions**, not
measured throughput): tanning 1,000–2,000/hour; walking sawmill 500–1,000;
grinding 1,000–3,000; ordinary furnace 400–800 except mithril 400–600,
adamant 350–500/runite 300–400; bracelet crafting 600–1,000 plus casting;
shop transport 200–800. Bank travel and inventory loads are why raw animation
rates are insufficient. These brackets need actual timing before deployment.

For each observed day and recipe, let C be adverse-rounded full input/fee cost,
g the full after-tax/fixed-coin gap, rho retained margin, v assumed participation,
f matched completion, t total production seconds/unit, and s daily setup hours.
Effective reserved unit cost C' = C+(1-rho)max(g, 0). For fixed-price vendors the
extra is a sale-realization reserve, not a higher vendor price.

```text
q_target = max(0, min(floor((1-s)*3600/t), floor(batch_budget/C'),
                     each remaining ingredient limit/recipe coefficient,
                     floor(v*each input side volume/coefficient),
                     floor(v*output sale volume) when a sale is needed,
                     stock/quota when applicable))          [only if g>0]
q_matched = floor(f*q_target)
GP/calendar day = cadence*q_matched*rho*max(g,0)
active hours/calendar day = s + cadence*q_matched*t/3600
GP/active hour = sum(GP)/sum(active hours), over all 84 days
```

The model is deliberately **matched-cycle capacity arithmetic**. It does not
invent a fill timestamp, predict daily means, certify queue access, or assume
unmatched purchases vanish. Reservations are charged in full for target units;
only matched production earns coins. An actual failed multi-leg cycle can leave
costly inventory, so these positive conditional bands are not P&L loss bounds.
Sale-leg methods additionally face unknown future output proceeds and capital
occupancy. The .25 cadence is a sensitivity to that delay, not an observed wait.

Frozen candidates: all members reported
--------------------------------------

**M** columns are measured gaps on archive means under current rules. All
**A** columns are conditional cautious–optimistic calculations. Income and units
are averages over **all 84 calendar days**, not just available/profitable days.
Ranges are joint scenarios, not statistical intervals; rows cannot be summed.
Amounts below exclude first-use staff, shown separately afterward.

| Candidate | M positive/valid days | M median gap GP | A units/day | A GP/active h | A GP/real day |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct yew longbow | 84/84 | 107 | 106.7–1,100.0 | 6,614–117,687 | 2,830–117,687 |
| Direct magic longbow | 83/83 | 189 | 110.7–754.0 | 14,327–242,082 | 6,224–172,289 |
| Direct rune javelin tips | 84/84 | 201.5 | 111.9–1,100.0 | 13,866–237,914 | 6,053–237,914 |
| Direct dragon javelin tips | 84/84 | 205 | 87.2–1,041.5 | 13,626–261,911 | 5,387–249,151 |
| String magic, sell | 75/75 | 114 | 117.7–868.5 | 9,243–173,049 | 3,217–97,916 |
| String yew, sell | 76/76 | 155 | 104.9–1,492.9 | 12,214–261,446 | 4,122–238,621 |
| String magic, alch | 75/75 | 369 | 67.0–589.3 | 15,182–247,358 | 6,337–223,064 |

Direct current limits are 18,000/4 h for each bow and 18,000 for nature runes,
10,000 for each javelin tip. Ideal uninterrupted 24 h allowances are 108,000 bow/
rune units and 60,000 tips, **not assumed fills**. Unstrung bows are 10,000/4 h,
strings 13,000. Therefore single-account daily production here is only roughly
67–1,493 conversions across stand-alone frozen examples, despite very large
ideal buy allowances. Direct consumes q items plus q runes; string/sell consumes
2 q ingredients and sells q bows; combined consumes 3 q ingredients, strings q
bows then casts q times. Nature volume is shared once, not counted separately
for every possible candidate in a portfolio.

Peak reserved input cash (**A**, cautious/optimistic): yew 339 k/779 k;
magic 679 k/998 k; rune tips 354 k/784 k; dragon tips 504 k/998 k;
magic string/sell 934 k/1 M; yew string/sell 388 k/620 k;
combined 436 k/795 k. Casting additionally reserves the staff 1,500 inside 1 M.
For dragon tips the median reservation is 398 k/998 k. One open batch can hold that
cash for 72 h or longer; a sale arm waits again for output disposal. Capacity is
not a return on continuously employed 10 M. Releasing funds and reusing slots
requires actual completion/cancellation, never just a new daily observation.

After first staff expense once across 84 days, the direct dragon daily range is
5,368.81–249,133.14 GP and active-hour range 13,581.02–261,892.61 GP.
The unchanged prospective 56-day, four-arm rotation cannot earn four stand-alone
rows every day: equal assignments divide opportunities by four even before busy
and failed days. This report is not a simulated result of that prospective trial.

On the first chronological source day (availability 1777766700), observed dragon
high mean 924 and nature 120 become input ceilings 925+121=1,046; fixed payout
1,170 gives gap 124. With **reference assumptions**, q=min(916 casts, 954 cash,
10,000 item limit, 18,000 rune limit, 4,019 item-volume allocation, 146,374 rune
allocation)=916; input reservation 958,136, GP=916×124=113,584, time=5/60+916/1000
=.999333 h, GP/active h=113,659.77. First-use staff subtracts 1,500 once.
With **cautious assumptions** on that same measured day, reserve 1,139/unit,
target 401, matched 100; GP=100×(.25×124)=3,100 and time=.25+100/600=.416667 h,
or 7,440 GP/active h. This uses the first day, not a selected favourable example.

Why 135,700 is not an account ceiling
----------------------------------

The reproduced sum is 11,398,956/84=**135,701.86 GP/day**, summing **one unit** of
every positive low-input-side item-day, without volume weights. It is neither an
attainable portfolio nor the whole market's profit capacity. A candidate can
repeat many units, so comparing its volume-weighted GP to this sum can exceed
100%; that does not mean capturing more than all available market profit.

**Measured denominator contribution**, one unit/day averaged across 84 days:
yew 119.14 GP (0.0878% of that sum), magic 235.27 (0.1734%), rune tips 227.95
(0.1680%), dragon tips 251.61 (0.1854%). The four together contribute only 0.6146%
of the original one-unit sum. Their higher liquid capacities are why the median
26-unit row across the full screen is not their account ceiling.

**Conditional repeated-unit comparison:** dragon tips 87.19–1,041.54 units/day
produce 5,386.67–249,151 GP/day, or 3.97%–183.60% of 135,701.86. These are ratios
with an inconsistent one-unit denominator, **not an attainable share of a profit
pool**. The honest share of executable market profit is unidentified. A corrected
market-wide pool would require actual joint prices/quantities and competing fills.
Also, 13,915 positive rows and median 179 GP describe the **high-input-side alchemy
screen**, not bow recipes. Original low alchemy is 24,622/254,377 item-days;
high alchemy 13,915/254,377; no original finding is relabelled as account income.

Sensitivity, no tuning or new inference
--------------------------------------

Below is pasted calculation output for direct dragon tips. Everything varying
here is **A**, an assumption; the development prices stay fixed. Defaults:
1,000 casts/hour, 1,800 strings/hour, 5-minute check, 100% gap retained, 1% share,
100% matching, one batch/day. One knob changes at a time.

```text
        scenario  units_real_day  gp_real_day  gp_active_hour  active_hours_day
       reference          916.00    215085.52       215229.01              1.00
        cautious           87.19      5386.67        13626.19              0.40
      optimistic         1041.54    249151.00       261911.39              0.95
       casts=600          550.00    129145.24       129145.24              1.00
      casts=1000          916.00    215085.52       215229.01              1.00
      casts=1200         1041.54    249151.00       261911.39              0.95
   retained=0.25          897.48     53004.55        54041.63              0.98
    retained=0.5          913.36    107372.48       107729.01              1.00
      retained=1          916.00    215085.52       215229.01              1.00
         share=0            0.00         0.00            0.00              0.08
     share=0.001          376.67     94858.26       206213.61              0.46
      share=0.01          916.00    215085.52       215229.01              1.00
    completion=0            0.00         0.00            0.00              0.08
 completion=0.25          229.00     53771.38       172160.24              0.31
    completion=1          916.00    215085.52       215229.01              1.00
 setup_minutes=5          916.00    215085.52       215229.01              1.00
setup_minutes=15          750.00    176107.14       176107.14              1.00
    cadence=0.25          229.00     53771.38       172160.24              0.31
       cadence=1          916.00    215085.52       215229.01              1.00
```

Lowering retention from 100% to 25% cuts reference hourly GP from 215,229 to 54,042;
cutting speed 1,000->600 gives 129,145. Participation 1%->0.1% reduces daily GP
215,086->94,858 while hourly GP remains 206,214 because less time is spent
casting. This is why active-hour efficiency and calendar income must both be
reported. Zero share or completion gives zero GP with daily check time still
charged. Unmeasured margin retention and matching can wipe out all income.

An additional **joint slow-cycle stress**, composing the already specified
cautious assumptions with .25 daily cadence (no parameter selection), gives:
GP/day=.25×5,386.66964=1,346.66741; active hours/day=.25+
.25×(.39531746-.25)=.28632937; GP/active h=**4,703.21**. Only 21.80 dragon tips/day
are converted. This is 0.99% of the one-unit 135,701.86 comparator, not a market
share. First staff across 84 days reduces it to about 4,641 GP/active h.
At a 100 k time hurdle, daily surplus is 1,346.67−28,632.94=**−27,286.27 GP/day**
before first staff. So a few-thousand-GP/hour outcome is entirely plausible,
without pretending it was measured. The archive cannot identify which scenario
will obtain. The repeated-batch, full-margin optimistic result is a ceiling,
not a forecast or a positive lower bound.

Other fixed structures: complete bounded catalogue
-------------------------------------------------

This scan covers 33 additional rows (including four mutually exclusive diary
tiers), not the whole item universe. **M:** positive/valid days, median of **all**
valid gaps (negative/zero retained). **A:** cautious–optimistic matched units,
GP/active h and GP/day, using the same setup/matching/competition stresses.
Missing days remain in all 84 calendar denominators. Full min/positive median/
p 90/max and low-input-side checks are retained in external screens.csv.

| Recipe | M positive/valid days | M all-gap median GP | A units/day | A GP/active h | A GP/day |
| --- | ---: | ---: | ---: | ---: | ---: |
| tan cow soft | 74/74 | 33 | 3.7–164.3 | 122–33,053 | 31–5,470 |
| tan cow hard | 70/73 | 26 | 1.4–73.1 | 42–17,656 | 11–2,117 |
| tan snake | 0/58 | -207 | 0.0–0.0 | 0–0 | 0–0 |
| tan snake swamp | 0/9 | -368 | 0.0–0.0 | 0–0 | 0–0 |
| tan green | 70/70 | 219.5 | 12.3–429.8 | 2,558–314,089 | 671–93,677 |
| tan blue | 68/68 | 242 | 13.9–408.0 | 3,177–336,806 | 839–96,780 |
| tan red | 67/68 | 243.5 | 18.1–317.3 | 4,350–326,949 | 1,166–79,120 |
| tan black | 68/71 | 202 | 9.6–206.0 | 1,957–223,517 | 508–41,645 |
| Regular plank | 72/72 | 10 | 44.1–785.1 | 347–9,869 | 117–8,571 |
| Oak plank | 79/79 | 181 | 84.6–861.5 | 9,492–170,933 | 3,979–161,500 |
| Teak plank | 84/84 | 205.5 | 81.7–916.0 | 10,034–191,299 | 4,149–191,171 |
| Mahogany plank | 75/75 | 255 | 83.0–517.5 | 12,469–215,021 | 5,188–129,192 |
| Chocolate dust | 59/59 | 10 | 3.5–154.0 | 41–13,566 | 10–1,827 |
| Unicorn horn dust | 76/78 | 54.5 | 1.8–87.7 | 111–48,269 | 28–5,433 |
| Goat horn dust | 67/71 | 50 | 0.8–46.9 | 45–26,584 | 11–2,631 |
| Crushed nest | 53/65 | 34 | 9.0–130.8 | 403–51,623 | 104–6,553 |
| smelt bronze | 48/48 | 28 | 7.6–293.0 | 196–17,977 | 53–8,083 |
| smelt silver | 65/65 | 32 | 24.2–561.7 | 645–24,028 | 200–18,872 |
| smelt gold | 0/84 | -56.5 | 0.0–0.0 | 0–0 | 0–0 |
| smelt steel | 81/81 | 179 | 72.3–706.8 | 7,247–126,228 | 3,122–122,044 |
| smelt mithril | 77/79 | 150 | 68.8–504.2 | 5,689–76,230 | 2,400–70,407 |
| smelt adamant | 82/84 | 315 | 63.5–447.1 | 10,841–134,814 | 4,676–131,784 |
| smelt runite | 79/80 | 332.5 | 19.0–79.6 | 5,217–97,440 | 1,634–27,521 |
| gold bracelet alch | 84/84 | 96.5 | 56.0–500.0 | 3,050–47,560 | 1,332–47,560 |
| Shop saw | 80/80 | 210.5 | 0.0–2.1 | 0–5,054 | 0–435 |
| Shop cloth | 0/84 | -261.5 | 0.0–0.0 | 0–0 | 0–0 |
| Shop bronze nails | 0/74 | 0 | 0.0–0.0 | 0–0 | 0–0 |
| Shop iron nails | 53/83 | 1 | 23.0–462.5 | 22–989 | 8–654 |
| Shop steel nails | 84/84 | 23 | 37.0–733.0 | 505–17,416 | 220–17,409 |
| zaff 15 | 84/84 | 278.5 | 3.0–15.0 | 830–43,113 | 220–4,401 |
| zaff 30 | 84/84 | 278.5 | 7.0–30.0 | 1,802–72,845 | 513–8,802 |
| zaff 60 | 84/84 | 278.5 | 15.0–60.0 | 3,385–111,185 | 1,100–17,604 |
| zaff 120 | 84/84 | 278.5 | 30.0–120.0 | 5,501–150,894 | 2,201–35,209 |

Tanning fees are 1/3 GP soft/hard cow, 15/20 ordinary/swamp snake, 20 per dragonhide;
no spell or diary discounts. Dragon tanning often has an arithmetic gap but only
about 206–430 units/day at the optimistic 1 M/volume gate and just 10–18/day at the
cautious gate. Snakes are negative; cowhide margins and quantities are small.
Selling the leather remains a price/fill risk.

Sawmill fees 100/250/500/1,500 bind the regular/oak/teak/mahogany ledgers. Teak's
84/84 positive means and conditional 4,149–191,171 GP/day merit attention as a
labour conversion, but do not establish future sale proceeds. Walking time,
output completion and input capital determine whether its 191 k optimistic hourly
rate can be approached. Mahogany's higher 255 GP median gap yields only 518
units/day optimistic because cash binds. No free voucher, butler or spell chain.

The ordinary bar recipes consume full 2/4/6/8 coal for steel/mithril/adamant/runite.
Gold ore->bar is 0/84 positive; gold bar->bracelet->330 fixed coins is 84/84 positive
but two production steps cap its optimistic rate near 47.6 k/hour. Grinding's
modest margins and side-volume bottlenecks keep even its optimistic daily GP
below 6.6 k; negative and missing nest/horn days are retained.

Shop-to-GE is checked across all five fixed-price sawmill goods, not a single
favourable stock. Caps assume at most 1,000 initial units of each good in one
world, no hopping or free replenishment; real stock competition can give zero.
Saws have a 210.5 GP median gap after their correct exemption, yet about 2.14
units/day at 1% of observed low-side sale volume:434.68 GP/day divided by
.0860119 h/day=**5,053.70 GP/active h**, even in the optimistic case. Cloth is
negative 84/84, bronze nails never strictly positive, iron nails about 989/h and
steel nails 17,416/h optimistic. These are not worth a dedicated account's time.

Zaff's barrel is fixed 7,000/item with 15/30/60/120 daily quota after the corresponding
existing Varrock Diary. Tiers are alternatives, not four additive incomes.
At the measured average gap 293.40476, even the 120 tier is capped at
120×293.40476=**35,208.57 GP/day** before any missed sale; the 15 tier is 4,401/day.
The assumed slow transport setup reduces hourly appeal; no cost of obtaining the
diary is hidden as a return. Ordinary Zaff stock changes price as stock depletes,
so its first-unit price is not extrapolated as a fixed 7,000 supply. Vendor price
bounds acquisition cost, not future GE proceeds. These mechanisms can persist
as payment for time/access rather than forecast alpha.

Mechanics references, not price observations: [alchemy](https://oldschool.runescape.wiki/w/High_alchemy),
[GE rules/tax/exemptions](https://oldschool.runescape.wiki/w/Grand_exchange),
[bow recipe](https://oldschool.runescape.wiki/w/Money_making_guide/Stringing_magic_longbows),
[tanner fees](https://oldschool.runescape.wiki/w/Tanner),
[sawmill fees and stock](https://oldschool.runescape.wiki/w/Sawmill),
[ordinary bars](https://oldschool.runescape.wiki/w/Bar),
[runite capacity](https://oldschool.runescape.wiki/w/Money_making_guide/Smelting_runite_bars),
[bracelet recipe](https://oldschool.runescape.wiki/w/Gold_bracelet),
[Zaff quotas](https://oldschool.runescape.wiki/w/Zaff),
[empty nest conversion](https://oldschool.runescape.wiki/w/Bird_nest),
[goat dust](https://oldschool.runescape.wiki/w/Goat_horn_dust).
Fetched mechanics can differ from archived dates; none of their live/cached GE
prices enter calculations.

Execution and verification
--------------------------

Reproduce from repository root (new output directory; attempts are immutable):

```bash
OSRS_DATA_DIR=/home/martin/osrs-data ml/.venv/bin/python -u \
  -m osrs_ml.mechanical_ceiling --output /home/martin/osrs-data/mechanical-ceiling-v2
OSRS_DATA_DIR=/home/martin/osrs-data ml/.venv/bin/python \
  -m osrs_ml.mechanical_ceiling_audit /home/martin/osrs-data/mechanical-ceiling-v2
cd ml
OSRS_DATA_DIR=/home/martin/osrs-data .venv/bin/pytest -q
.venv/bin/ruff check src tests
```

Real execution output, from external logs:

```text
ORIGINAL SCREEN RECONCILED
      positive  unit_gap_sum
side                        
high     13915       3422903
low      24622      11398956
PASS: 341047 development rows; 84 calendar days; 40 recipes; 760 sensitivity rows; capacity/cash/time/limit assertions passed; profit_tests=0; holdout_read=False
PASS: 56639 scalar source reconciliations; 760 sensitivity summaries; all output/code/protocol hashes; capital, slots, tax, limits and time; holdout_read=False
245 passed in 38.19s
All checks passed!
```

The independent audit reconstructs every screen's valid calendar, gap counts,
medians/p 90 and every capacity row with scalar formulas directly from the source;
all 760 summaries reconcile. Hashes of protocol, amendment, implementation,
inputs and all five outputs are checked. The joint slow-cycle calculation is saved separately in
`/home/martin/osrs-data/mechanical-ceiling-slow-cycle.json`.
No inferential uncertainty is claimed:
the ranges are sensitivity endpoints and empirical daily quantiles, not Gaussian
or bootstrap confidence intervals; hence neither a normality test nor a profit
p-value is supplied. No new search-family correction is needed or claimed.
Existing 213-test failures and the sealed prospective 217-test family are unchanged.

Integrity anchors:

```text
run.json bacc58ed9eead4adb50d94831d66adfa03cc24653d44f509476c7c8a40ed0667
capacity.csv 66b2ac9fa9949320b126a55faa85bc74bcdf515d52a90b4c5535ebe7d834a8fe
screens.csv 271bd6ea9922f4aa26b564b1977a15883177d11f56b62e47ec87cf20fbf397cf
capacity-days.parquet bbcab64f00765a8beecf520c3b10bbc88d001f759eb149f425401e3b5ef18e49
```

Both the first uncorrected run and corrected v2 are retained. A preliminary
audit failed on nullable source fields and was fixed to reject missing legs
explicitly; no outcome or inclusion rule was changed. Initial test invocation
used the wrong relative executable path; the corrected full suite and final
suite both passed 245 tests. Lint must run from ml/ so existing import
classification matches the project. No C++ changes, training, synthetic market
evidence, forecast sweep, holdout market-field access or actual fills occurred.
