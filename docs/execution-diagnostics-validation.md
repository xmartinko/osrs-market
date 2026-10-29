# Execution diagnosis: executed development sensitivity

Run on `ml/financial-model`, with implementation commit `987cd12`, after the written
assessment was committed at `0cc55d4`. Documentation commits followed during the run;
the implementation did not change. C++ and existing research artifacts were unchanged.
Raw data, ledgers, reports and logs are outside Git under `/home/martin/osrs-data`.

## Commands and real output

```bash
OSRS_DATA_DIR=/home/martin/osrs-data uv run --project ml --frozen \
  osrs-ml diagnose-execution \
  --panel /home/martin/osrs-data/assembled-v3/daily.parquet \
  --development-run ml/runs/phase2-real-v1 \
  --output /home/martin/osrs-data/execution-diagnostics-v2 \
  > /home/martin/osrs-data/execution-diagnostics-v2.log 2>&1
```

Final command output (all three folds; CatBoost only in this printed table):

```text
fold                       0       1       2
scenario
conservative           -3914   -9683   -7293
crossed_slip_0bps      15713 -288771  110353
crossed_slip_10bps    -48537 -354040  -22537
crossed_slip_30bps    -48537 -354050  -22537
crossed_slip_5bps     -48537 -354040  -22537
moderate              -26493  -76247  -10974
moderate_passive      -14396  -45030   88604
only_freshness         58020   20185  280599
only_latency           58020   20185  280599
only_participation      8919  -13545  151408
only_price_side        15713 -288771  110353
only_queue             23401  -17684  160502
only_slippage           9997 -157462  110107
only_terminal_haircut  57953   -3434  276233
optimistic             58020   20185  280599
passive_slip_0bps      58020   20185  280599
passive_slip_10bps      9997 -157462  110107
passive_slip_30bps      9997 -157514  109821
passive_slip_5bps       9997 -157462  110163
Completed 285 development sensitivities; original presets reproduced; holdout NOT read. Artifacts: /home/martin/osrs-data/execution-diagnostics-v2
```

The command exited 0. Manifest status is `complete`, with 285 completed combinations
(19 scenarios × five models × three folds). Result Parquet SHA-256:
`fa846053c8227e63b44ff997c2b5cf83a296904d0b6a0af6fdf87c3c1fc338d4`.

The panel was hashed in full for integrity, but observation loading used fold-boundary
predicates. No holdout values entered a loaded frame, and no holdout forecast, outcome,
metric or access-marker artifacts were opened. Scores were reused, without fitting,
feature/label construction, parameter selection or alteration of the old selection.
Each original-preset replay matched saved net/realized GP, cash, inventory marks/units,
requested buys and bought/sold units before its new diagnostics were published.

```bash
uv run --project ml --frozen pytest -q
```

```text
......................................................                   [100%]
54 passed in 8.86s
```

All original 43 tests plus 11 new tests pass. New tests cover fixed-quantity repricing,
tax changes at the exemption boundary, incomplete opposite-side prices, decision-key
coverage, fold/label boundaries, legitimate versus unexplained undefined scores,
Arrow/native integer keys, no-trade behavior, an injected future observation, immutable
inputs/outputs, baseline drift and durable partial failure. Fixture results in these
tests are software checks only, not market findings.

```bash
uv run --project ml --frozen ruff check --config ml/pyproject.toml ml/src ml/tests
```

```text
All checks passed!
```

An additional ledger audit was executed from a retained external script:

```bash
uv run --project ml --frozen python /home/martin/osrs-data/audit-execution-diagnostics.py
```

```text
285 scenarios audited; 7341 fill events; 57 no-trade controls.
PASS: cash, inventory, realized P&L, tax, volume capacity, buy limits, offer slots, temporal causality, no-trade.
All checks apply to hypothetical current-limit sensitivity, not actual market fills.
```

This audit reconstructs cash, per-item inventory/book cost, realized P&L, terminal
marks and per-item four-hour buy-limit windows from fills. It checks volume capacity,
source price/assumed adjustments, order submission latency, bucket start eligibility,
freshness bounds, offer-slot maxima, requested quantities and no-trade invariants.
It validates ledger consistency, not whether assumed fill prices are economically
achievable. The zero-price stress behavior discussed below remains in the executor.
Separate comparisons confirmed that all intentionally duplicated policies agree for
all models/folds on P&L, bought/sold units, realized P&L and terminal inventory marks.

## Findings and limits

These are **current_limits_sensitivity** figures, with today's limits joined backward,
inferred historical availability and hypothetical aggregate fills. No claim here is
an actual market trading result. Every fold starts with its own 10M GP; curves must
not be concatenated into a continuously deployed portfolio.

The original quoted CatBoost fill-count sequence refers to **sold units**:

| Preset | Bought units | Sold units | Fill events | Ending inventory units |
| --- | ---: | ---: | ---: | ---: |
| optimistic | 198,965 | 171,067 | 213 | 27,898 |
| moderate | 56,387 | 49,422 | 160 | 6,965 |
| conservative | 10,820 | 10,033 | 132 | 787 |

These counts sum three independent fold portfolios. Across all models and scenarios,
122 of 285 combinations bought no units and are labelled `no_buys_inconclusive`;
that includes the deliberately inactive no-trade controls. Every result exposes
positive-score counts, overlapping static input gates, buy orders, fill events,
bought/sold units, actual simulated tax, realized GP, marks and remaining inventory.
Static gates do not explain dynamic cash/slot rejection or identify all fill failures.

Price-side changes alone remove all-fold profitability and make the aggregate fold
sum negative. Nevertheless, two folds remain positive under those favorable capacity
and zero-slippage assumptions. Changing participation or queue fractions alone also
makes fold 1 negative. Restoring passive prices in moderate leaves folds 0 and 1
negative. There is no single-factor explanation of the entire preset difference.
Latency and freshness contrasts happen to produce identical results at daily
resolution, so this experiment cannot identify their effects at five-minute resolution.

Fixed-fill repricing preserves quantities, dates and the terminal mark. It is an
accounting counterfactual, potentially violating cash, volume and order ceilings:

| CatBoost fold | Original optimistic GP | Crossed GP with same terminal mark | Missing opposite-side fill prices |
| --- | ---: | ---: | ---: |
| 0 | +58,020 | incomplete | 2 of 71 |
| 1 | +20,185 | incomplete | 1 of 66 |
| 2 | +280,599 | +27,198 | 0 of 76 |

No full-cohort conclusion is drawn from the incomplete comparisons. In the complete
fold 2 comparison, crossed buys reduce cash by 101,360 GP and crossed sales by
152,041 GP; the unchanged terminal mark is 15,933 GP.

The slippage grid exposes a second validity problem. For fold 0, all 71 CatBoost
events match between optimistic and passive nominal 5-bps execution, including their
quantities. Purchases pay 24,045 GP extra and sales lose 23,978 GP: **48,023 GP**.
Measured against the original side notionals, those price costs are **2,251.11 bps**
on purchases and **1,445.18 bps** on sales, not approximately 5 bps. The median
optimistic purchase price is 3 GP. Integer ceil/floor adjustments impose at least
one GP per unit, making 5/10/30-bps scenarios identical for this fold's CatBoost fills.
This is a deterministic tick stress; it is not a calibrated expected slippage model.

The same fold's passive slippage scenario includes 64 units sold at zero GP. Across
all folds the original moderate CatBoost simulation has one zero-GP sale event for
three units. These are consequences of the execution arithmetic, not observed market
prices. The executor is unchanged in this phase so the original experiment can be
reproduced. Valid positive trade prices and measured tick costs need a separately
versioned correction before interpreting stressed losses as evidence against a signal.

The initial diagnostic attempt remains at `execution-diagnostics-v1`, status `failed`
with no completed scenarios. It rejected legitimate NaN scores at missing-side rows.
The fix retains these ineligible original scores, adds a regression test, and rejects
unexplained NaNs on valid inputs. No old predictions or outcome data were rewritten.

The next work is the valid-price/tick-cost specification and own-fill calibration
described in [the revised assessment](next-steps.md), followed by a newly frozen
prospective evaluation. The foundation tournament remains deferred.
