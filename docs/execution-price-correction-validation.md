# Executed price/tick correction on frozen development scores

The [pre-implementation judgment and price specification](execution-price-correction.md)
was committed at `6104063`, before implementation `114772a`. The market replay ran
from clean `114772a`; `901242f` subsequently added an independent auditor and its
corruption tests. No executor logic changed during or after this replay.

**The earlier all-fold-negative moderate/conservative CatBoost conclusion is
withdrawn.** Corrected moderate is +1,432 / −46,392 / +47,770 GP; conservative is
−97 / −6,046 / +6,238 GP. Their sums over separately funded folds are only +2,810
and +95 GP, respectively. These results look substantially better than the legacy
stresses, but do not demonstrate executable profit. The assumed passive fills,
current-limit lookahead and daily resolution remain uncalibrated.

## Commands and actual completion output

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  osrs-ml diagnose-execution \
  --panel /home/martin/osrs-data/assembled-v3/daily.parquet \
  --development-run ml/runs/phase2-real-v1 \
  --output /home/martin/osrs-data/execution-price-correction-v2 \
  > /home/martin/osrs-data/execution-price-correction-v2.log 2>&1
```

Exit code 0; the printed CatBoost GP table was:

```text
fold                       0       1       2
scenario
conservative             -97   -6046    6238
crossed_slip_0bps      15713 -288771  110353
crossed_slip_10bps     15495 -287987  107821
crossed_slip_30bps     15034 -291644  102911
crossed_slip_5bps      15609 -287069  109049
moderate                1432  -46392   47770
moderate_passive        4372    8954  140060
only_freshness         58020   20185  280599
only_latency           58020   20185  280599
only_participation      8919  -13545  151408
only_price_side        15713 -288771  110353
only_queue             23401  -17684  160502
only_slippage          57966   19704  277690
only_terminal_haircut  58018   19208  280441
optimistic             58020   20185  280599
passive_slip_0bps      58020   20185  280599
passive_slip_10bps     57966   19704  277690
passive_slip_30bps     57429   14698  272675
passive_slip_5bps      58097   20957  278943
Completed 285 corrected development sensitivities; 45 original presets reproduced with legacy_v1; holdout NOT read. Artifacts: /home/martin/osrs-data/execution-price-correction-v2
```

The manifest records `status=complete`, `price_model=integer_lots_v2`, 285 corrected
combinations and 45 matched legacy preset/model/fold replays. Result Parquet SHA-256:
`f8364604c60bf3b5ed1a92f6830e251641cb76c897858ac3a19b908ff0d11c9f`.
Panel/config/lock/development artifact hashes equal those in the previous 285-run
experiment. Every scenario's parameters also match after excluding the two added
price-model/tick fields. No fitting, threshold search, tuning, model selection,
feature rebuilding or holdout access occurred. Panel hashes cover the whole file
for integrity; observation frames use development-fold predicates, strictly before
the holdout cutoff. No holdout forecast, outcome, metrics or access markers were read.

## Original presets: exactly what is superseded

All 45 legacy replays matched the saved development net/realized GP, cash, marks,
inventory units, requested buys and bought/sold units before correction. The
`legacy_reproduction/` directory preserves these ledgers, including invalid sales,
as reproduction evidence only. Corrected results are in separate scenario paths.

| CatBoost preset | Fold | Legacy GP | Corrected GP | Change | Cash change | Mark change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| optimistic | 0 | 58,020 | 58,020 | 0 | 0 | 0 |
| optimistic | 1 | 20,185 | 20,185 | 0 | 0 | 0 |
| optimistic | 2 | 280,599 | 280,599 | 0 | 0 | 0 |
| moderate | 0 | −26,493 | 1,432 | +27,925 | +27,925 | 0 |
| moderate | 1 | −76,247 | −46,392 | +29,855 | +19,515 | +10,340 |
| moderate | 2 | −10,974 | 47,770 | +58,744 | +55,405 | +3,339 |
| conservative | 0 | −3,914 | −97 | +3,817 | +3,817 | 0 |
| conservative | 1 | −9,683 | −6,046 | +3,637 | +2,398 | +1,239 |
| conservative | 2 | −7,293 | 6,238 | +13,531 | +13,287 | +244 |

CatBoost bought units, sold units and terminal inventory units are **unchanged in
all nine original-preset comparisons**. In particular moderate fold 0 buys/sells
14,004 units under both versions, with no terminal inventory. An intermediate
status update incorrectly compared that fold to an old three-fold total and
suggested reduced exposure; that was corrected during execution. The price model
can change sale times even when aggregate units match. In moderate fold 2, the
three-unit zero-price legacy sale is rejected at that opportunity; the units sell
later at a legal positive price. This is not a fixed-fill counterfactual.

The moderate sum changes from −113,714 to +2,810 GP (+116,524); +102,845 of the
change is cash and +13,679 is marks. Conservative changes from −20,890 to +95 GP
(+20,985). These are sums of three separate 10M-GP starting portfolios, not a
continuously compounded curve, a deployment return or three independent trials.
The deltas measure this specified arithmetic correction, not actual market profits.

All models were replayed; corrected preset GP is:

```text
fold                              0        1        2
scenario     model
conservative catboost           -97    -6046     6238
             no_change            0        0        0
             no_trade             0        0        0
             raw_spread           0        0        0
             spread_volume  -851695  -878251 -1331603
moderate     catboost          1432   -46392    47770
             no_change            0        0        0
             no_trade             0        0        0
             raw_spread           0   -54607    -1631
             spread_volume -1513424 -1764980 -1827665
optimistic   catboost         58020    20185   280599
             no_change            0        0        0
             no_trade             0        0        0
             raw_spread      -54567   251230  -208191
             spread_volume    60851  -328788   396412
```

`preset_deltas.csv` has all 45 before/after accounting/exposure comparisons.
The executed summary also writes `all_scenario_deltas.csv` for all 285 old/new
comparisons. Across them, 92 net-GP values change. Every intentionally duplicated
policy agrees on all eight compared accounting/exposure measures in every fold
and model. The no-buy count stays **122 of 285**, including inactive controls;
these remain `no_buys_inconclusive`. The old no-trade selection is untouched.

The old stressed numbers in [the diagnostic record](execution-diagnostics-validation.md)
and all original phase-2 moderate/conservative figures are superseded by this
version. The same legacy cost defect affects nonzero-cost phase-1 tables; those
have **not** been rerun here and have no new numerical replacements. Zero-cost
optimistic/price-side/participation/queue/latency/freshness results and the zero-cost
fixed-fill accounting diagnostic remain unchanged. All versions remain hypothetical
current-limit sensitivities, never demonstrated historical execution.

## Measured bps and the non-monotone comparison

The following is real CatBoost fold-0 output, not a fixture. Reference purchase
notional is 106,814 GP in all four cases. Reference sale notional is 165,917 GP at
zero cost and 165,853 GP in the positive-bps scenarios because 64 units no longer
sell. Every scenario buys 24,045 units.

| Nominal bps | GP | Sold units | Paid buy cost GP | Achieved buy bps | Uncharged buy rounding GP | Paid sale cost GP | Achieved sale bps | Uncharged sale rounding GP |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 58,020 | 23,978 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | 58,097 | 23,914 | 44 | 4.119310 | 9.407 | 71 | 4.280899 | 11.9265 |
| 10 | 57,966 | 23,914 | 96 | 8.987586 | 10.814 | 153 | 9.225037 | 12.853 |
| 30 | 57,429 | 23,914 | 311 | 29.116033 | 9.442 | 481 | 29.001586 | 16.559 |

Nominal 5 bps now specifies exactly 53.407 GP purchase cost and 82.9265 GP sale
cost on the executed reference notionals; paid costs plus the explicitly uncharged
residual equal those targets. Paid rates are **not** asserted to be exactly 5.
The residual is less than 1 GP per opportunity, not one GP per unit. Small orders
can under-realize the nominal rate materially; both quantities are reported.
No fractional fee is silently deducted from cash. There are no explicit tick
charges in this grid. A separately configured `adverse_ticks` stress has its own
cost and effective-bps fields, with low-price regressions verifying the separation.

Compare this with the superseded nominal 5-bps fold-0 costs of 24,045 GP on buys
and 23,978 GP on sales (2,251 / 1,445 bps). The new total paid price cost is 115 GP,
not 48,023 GP. Because sale quantities differ, this comparison is a policy replay,
not a claim to refund exactly 47,908 GP on fixed trades.

Why is corrected passive 5-bps P&L 77 GP *above* zero cost? The sale target for
64 units at a 1-GP reference is below 1 GP, so the offer stays open. Compared with
zero cost, cash is 179 GP lower (115 GP paid costs plus 64 GP forgone sale), but
terminal inventory is marked 256 GP higher. These retained units are marked later
at a different reference, rather than liquidated. This is a timing/mark effect,
not a benefit from paying slippage. Terminal unpriceable units happen to be zero
in these four scenarios; the untradeable opportunity is still recorded.

The same issue affects comparisons across positive bps in other folds: sale
eligibility, cash, slots and terminal marks can move. For example corrected
crossed fold 1 at 5 bps loses less than at 0 bps. The grid is not a monotone
fixed-quantity transaction-cost curve. The separate unchanged fixed-fill repricing
still supplies the clean spread accounting comparison: fold 2 falls from +280,599
to +27,198 GP, with unchanged quantities and terminal mark; folds 0/1 remain
incomplete (two/one missing opposite-side prices).

## Executed software and ledger verification

The original 54 tests plus 22 additional cases pass. These are mechanics tests,
not market observations. Recorded output:

```text
$ uv run --project ml --frozen pytest -q
........................................................................ [ 94%]
....                                                                     [100%]
76 passed in 14.20s
$ uv run --project ml --frozen ruff check --config ml/pyproject.toml ml/src ml/tests
All checks passed!
```

The independent audit command and its actual output follow below.

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  python -m osrs_ml.execution_audit \
  /home/martin/osrs-data/execution-price-correction-v2 \
  /home/martin/osrs-data/assembled-v3/daily.parquet
```

Exit code 0:

```text
{"fill_lots": 9880, "no_buys": 122, "opportunities": 7332, "price_rejections": 10, "scenarios": 285}
PASS: positive integer prices, quantity/cash/inventory/realized P&L, per-lot tax, bps cost and residual, tick separation, capacity, buy limits, offer ceilings/slots, temporal causality, freshness, no-trade. Holdout NOT read.
```

The audit independently reconstructs terminal marks, unpriceable inventory and
per-lot tax, as well as cash and book cost; it does not merely compare reported
net GP. There are zero nonpositive corrected fills and zero invalid-reference
rejections in these real inputs. All ten rejections are explicit
`untradeable_at_granularity` opportunities. The 9,880 price lots represent **7,332
fill opportunities**, not 9,880 independent executions. Five corrected combinations end with one unpriceable inventory unit each: fold-0
raw-spread under only-price-side and the four crossed-grid policies. Their zero
mark is a separately exposed valuation bound for an unavailable valid mark,
not sale proceeds. No CatBoost combination ends with unpriceable inventory.
Legal integer prices and ledger consistency are necessary checks, not proof of
achievable liquidity.

The comparison/consistency summary was also executed:

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  python /home/martin/osrs-data/summarize-price-correction.py
```

Excerpt of actual output:

```text
Manifest: complete corrected= 285 legacy reproduced= 45 holdout_read= False
No-buy combinations: legacy= 122 corrected= 122
Changed P&L combinations: 92
Total corrected price rejections: 10
Invalid reference price rejections: 0
PASS: all intentionally duplicated policies agree for all folds/models.
```

The script, replay log, `.audit.log`, `.summary.log`, all generated data, original
artifacts and corrected artifacts remain under `/home/martin/osrs-data`. No raw
data, Parquet, ledger, model or generated CSV files were added to Git. C++ and the
frozen model artifacts/configuration were not modified.

## Updated conclusion and confidence

The arithmetic correction makes the stressed strategy look **better**, materially.
The interpretation that nominal 5–30 bps destroys passive profitability is false
for these development replays: corrected passive CatBoost is positive in every
fold across that fixed grid. Restoring passive prices in moderate is now also
positive in all three folds (+4,372 / +8,954 / +140,060), replacing −14,396 /
−45,030 / +88,604. Corrected crossed-side moderate/conservative are mixed by fold,
with aggregate GP barely above zero. The old uniformly negative story relied in
part on a full-tick arithmetic stress mislabelled as small bps costs.

This does not rehabilitate the optimistic executable-edge claim. The unchanged
complete fixed-fill comparison still removes 90.3% of fold-2 profit on crossing
sides. Crossed zero-cost P&L still includes −288,771 GP in fold 1. Participation
and queue contrasts still change signs, and latency/freshness remain unidentified
at daily resolution. A single-factor explanation of all preset differences is
still unjustified. Marks can dominate small net profits; the corrected moderate
+2,810 GP includes 22,661 GP of ending marked inventory across the three portfolios.
The 122 no-buy cases still supply no signal evidence.

My subjective confidence that **the original reported sign change principally
reflects execution conventions and the measurement apparatus** remains around
90%, up from the pre-diagnostic 85%. That is not a statistical probability from
three folds. More narrowly, the proposition that *calibrated, achievable execution
costs* cause a negative sign is **not established**; the corrected aggregate signs
are now positive and the old cost model cannot support that belief. I withdraw
any strong negative inference about the signal from the old stressed losses.

I have **low confidence that an executable edge has been demonstrated** and no
useful basis to quantify the probability that one exists. The honest market
answer remains **undecidable with this data**, despite the better hypothetical
results. No new model was selected; the original no-trade choice is untouched.
The next blocking defect is now uncalibrated order availability/adverse selection,
followed by prospective data qualification. Authorized own-order evidence and a
newly frozen, nonvacuous forward comparison against matched simple controls and
no-trade could reverse this view. Foundation-model expansion remains deferred.
