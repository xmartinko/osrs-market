# Executed processing attribution — cycle 2

The unchanged processing account's positive marked result comes from simulated
conversion margins, with **losses on remaining inputs**. It is not a new profit
test or an executable edge. Every original processing raw/adjusted p remains
**1.0**: only six/eight/eight completed batches across the three registered shares.
The 213-scenario battery still has zero corrected survivors.

The [protocol](processing-attribution-protocol.md) was committed in `b53486f`
before detailed batch inspection. Implementation and ten accounting/integrity
tests were committed in `433fa7c` before the attribution run. No parameters,
recipes, fills, activity gates or original outcomes were changed.

| Registered participation | Submitted / produced / fully sold batches | Simulated realized GP | Remaining input book GP | Terminal mark GP | Unrealized GP | Net GP | Cash change GP | Original adjusted p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.1% | 11 / 6 / 6 | 1,102,393 | 507,674 | 458,884 | −48,790 | 1,053,603 | 594,719 | 1.0 |
| 1% | 16 / 8 / 8 | 2,054,103 | 1,943,729 | 1,654,387 | −289,342 | 1,764,761 | 110,374 | 1.0 |
| 5% | 16 / 8 / 8 | 2,054,103 | 1,943,729 | 1,654,387 | −289,342 | 1,764,761 | 110,374 | 1.0 |

These are hypothetical crossed aggregate-bucket fills using current metadata,
tax, slippage, limits, slots and volume participation from the original account.
“Realized” describes sold inventory in that simulation; no actual orders or casts
were executed. The accounts cover the same **84 daily timestamps / 1,992 elapsed
hours**, entirely inside development. The shares are dependent sensitivities,
not independent replications. The 1% and 5% fill paths are identical.

At 1%, the exact accounting is:

```text
cash change = 2,054,103 realized - 1,943,729 remaining book =   110,374 GP
net profit  = 2,054,103 realized -   289,342 unrealized loss = 1,764,761 GP
```

This corrects the possible reading of the preceding cycle's emphasis on the
1,654,387 GP mark and 110,374 GP cash change. The gross mark does **not** mean that
1,654,387 GP of profit came from appreciation. The original metrics already
reported realized P&L of 2,054,103 GP; the audit independently reconstructs it.
No numeric battery result or inference is withdrawn or replaced.

All produced output sold. Remaining inventory consists entirely of unconsumed
inputs, with fresh final source observations (zero availability age). There are
2,746 input units at 0.1% and 9,900 at 1%/5%. Unmatched input risk is material even
when completed production is profitable. At 1%, eight submissions produced no
output; seven of those bought one leg. Some prior partial inputs were subsequently
pooled into production, so spending by an unproduced submission must not be equated
to its final stranded inventory. The audit retains the original weighted book.

The fixed decomposition of **sold** production P&L is:

| Participation | Decision conversion spread GP | Input cost movement GP | Output price movement GP | Sum: simulated realized GP |
| --- | ---: | ---: | ---: | ---: |
| 0.1% | 1,050,769 | +103,539 | −51,915 | 1,102,393 |
| 1% | 2,115,300 | −60,977 | −220 | 2,054,103 |
| 5% | 2,115,300 | −60,977 | −220 | 2,054,103 |

The decision spread uses conservative integer input ceilings and an after-tax
output quote at the original submission, on the eventual sold quantities. The
input component then replaces the ceiling cost with the actual consumed pooled
book cost, and the output component replaces the decision quote with actual
simulated after-tax sale proceeds. This exact same-fill identity does not assume
all inputs could fill together or that decision prices could be executed. It is
an attribution, not a second strategy or a counterfactual account return.

All six/eight/eight completed batches are positive in the simulation; no batch
was excluded. Largest-batch contributions to realized P&L are 25.51% at 0.1% and
16.25% at 1%/5%. No individual-batch significance is claimed. The original search
correction and ten-completion gate cannot be bypassed using these counts.

At 0.1%, 6,392 bows required 4.0511 modeled active hours; realized GP per active
hour is 272,121.15. At 1%/5%, 13,200 bows required eight modeled active hours;
realized GP per active hour is 256,762.88, versus original marked GP per active
hour 220,595.13 and marked GP per elapsed hour 885.92. These rates retain the
registered production/setup assumptions; measured human execution time is absent.
Submission-to-production waits are 120 hours at 0.1% and 72–120 hours (median 72)
at 1%/5%. Production-to-final-sale waits are 48–120 hours (median 96) at 0.1%
and exactly 48 hours at 1%/5%. Active time and capital occupancy are distinct.

This rules out **terminal inventory appreciation as the explanation of this
particular simulated gain**. The favorable term is already present in the
decision-time conversion spread; later price changes reduce pooled profit. It
does not verify attainable prices, participation, historical limits or expected
account profit. The result stays inconclusive, with original adjusted p=1.0;
no new bootstrap, unadjusted diagnostic test or Gaussian inference was performed.

The next lead is prospective own-fill calibration of this fixed processing
mechanism, measuring both input legs, partial fills and reuse, cancellation,
output proceeds/tax, active time and tied capital. Retain all failed submissions
and unsold inputs. More participation alone did not change the registered 1% to
5% result. Do not relax the completion gate or tune stranded-leg purchases on
these development outcomes. Any future execution trial needs its own frozen
period and account lifecycle; no later prices were collected or substituted for
the reserved holdout during this cycle.

Reproduction, from the repository root:

```bash
OSRS_DATA_DIR=/home/martin/osrs-data ml/.venv/bin/python -m osrs_ml.processing_attribution \
  --source /home/martin/osrs-data/strategy-battery-v1 \
  --output /home/martin/osrs-data/processing-attribution-v1 \
  --acknowledge-private-research
```

The output directory must not exist. The executable checks original run provenance,
all 15 input artifact hashes and the daily source hash before reading scenario
ledgers. DuckDB selects only five recipe IDs and
`1777766700 <= available_at < 1785024300` before materialization: **420 source
rows**, no reserved market rows. All 252 account equity timestamps reconcile.
Production precedes current fills; pooled costs are consumed once per opportunity,
including split integer-price lots. Saved realized GP, cash, quantity, marks,
completion counts and active time all agree exactly (time within float tolerance).

All generated batch, submission, item-inventory and summary CSVs, their hashes
and the run manifest remain in `/home/martin/osrs-data/processing-attribution-v1`.
Summary CSV SHA-256:
`88b43dd698846691fcc23dba044c07d9069dbbd23158ff0327919885b9b33544`.

Real machine output:

```text
PASS: 3 unchanged processing accounts attributed; original inference retained; holdout NOT read
PASS: 420 development source rows; 252 equity timestamps reconciled; all 10 output hashes verified; original adjusted p=1 for all three shares; holdout_read=False
```

Executed from `ml/`: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`:

```text
........................................................................ [ 44%]
........................................................................ [ 88%]
..................                                                       [100%]
162 passed in 32.29s
All checks passed!
```

Before implementation, the new tests failed collection with
`ModuleNotFoundError: No module named 'osrs_ml.processing_attribution'`.
After implementation, all ten passed, including partial sales, split lots,
cash-versus-realization, interior path corruption, duplicated events, unowned
production, source drift and sealed-boundary filtering. Fixtures are accounting
tests only, never evidence for profit. No C++ file was changed.

The original independent audit was rerun after attribution and still passed:

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
