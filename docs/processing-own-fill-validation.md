# Processing own-fill calibration intake — executed cycle 3

The [frozen protocol](processing-own-fill-protocol.md) is implemented and an empty
study is enrolled. **No actual execution evidence exists in this study. Expected
profit remains unidentified.** This cycle makes the next genuine observations
recordable and auditable; it adds no historical strategy result or profit test.

Registration was committed in `1366d26`, intake implementation/tests in `84bd183`,
and execution measurements/documentation in `fdde48d`. The new tests initially
failed collection with `ModuleNotFoundError: No module named
'osrs_ml.processing_calibration'`. After implementation, all 29 new test cases
and all 162 preceding tests pass. Test fixtures are deterministic accounting
examples, never real fills, training observations or profit evidence.

## Executed enrollment and result

From the repository root:

```bash
export OSRS_DATA_DIR=/home/martin/osrs-data
ml/.venv/bin/python -m osrs_ml.processing_calibration init \
  --study "$OSRS_DATA_DIR/processing-own-fill-v1" --acknowledge-private-research
ml/.venv/bin/python -m osrs_ml.processing_calibration report \
  --study "$OSRS_DATA_DIR/processing-own-fill-v1" --acknowledge-private-research
```

Enrollment: **2026-10-29 20:22:41 UTC**. Fixed recording window:
**2026-10-30 00:00:00 UTC <= event time < 2026-12-25 00:00:00 UTC**, 56 days.
The ledger and initial `readiness.json` are external under
`/home/martin/osrs-data/processing-own-fill-v1`. No import was run against it.
The configured 10M GP is an enrollment accounting allocation, not a newly
observed account balance or evidence of money deployed.

Actual CLI output excerpt:

```json
{
  "status": "awaiting_actual_records",
  "ready": false,
  "event_count": 0,
  "decisions": 0,
  "sessions": 0,
  "attempted_batches": 0,
  "completed_batches": 0,
  "buy_fills": 0,
  "sell_fills": 0,
  "expected_profit_gp": null,
  "p_adjusted": null,
  "historical_battery_p_adjusted": 1.0,
  "holdout_read": false
}
```

The five readiness failures are `window_not_ended`, `missing_daily_decisions`,
`missing_daily_sessions`, `fewer_than_ten_completed_batches`, and
`missing_buy_or_sale_activity`. Empty cash/inventory changes are accounting
initialization, not a zero-profit market sample. No new per-hypothesis p-value,
Gaussian interval, bootstrap result or significance claim was produced. The
original 213-test search correction and all its failed rules are unchanged.

The executed consistency check re-opened only this new ledger and its readiness
report, checked event count, protocol/code hashes, dates, null expected profit
and unchanged historical inference:

```text
PASS: frozen protocol/code hashes; 0 actual events; 56-day window; expected profit unidentified; holdout_read=False
```

Initial readiness report SHA-256:
`48c1cfc4cab6cfee3e31e15504b40435a01ff3c0baee63d75f2477d8dcf9451c`.
Frozen protocol SHA-256:
`53d5f422fb9a0bd69ec6283539329297adaf333a8177287b9998f05b10388087`.
Frozen intake code SHA-256:
`5b9316da1e13872d937b339400462834095e7f7411084d3e3eba23a1e0606e1c`.

## What is now checked

Append-only SQLite tables and a chained event digest preserve enrollment and
records. Imports are transactional; evidence is hashed before acceptance and
again on reports. The ledger rejects future/out-of-window events, duplicate
identities, evidence path escapes, corrupt evidence, order overfills or price
violations, invented tax/cash, unowned production/sales and broken daily account
checks. It refuses existing initialization, missing report databases and changed
protocol/code. All raw records and evidence remain external.

Actual envelope breaches stay in accepted data and block readiness: oversized
batches, excessive slots, buy-limit use, expired buys, overlapping batches,
production/time caps, missing active time and decisions recorded after submission.
A failed submission or partially filled cancelled order cannot be dropped without
losing recorded coverage. The account exposes actual tax, fill prices/fractions,
wait times, remaining units/book cost and capital occupancy; cash change equals
realized profit minus remaining book cost. It invents no terminal price.

Tests cover both inconclusive complete-calendar/no-trade data and a mechanically
complete calibration example. A ready sample still receives no expected-profit
estimate or significance claim. Operator authenticity, completeness of unrecorded
activity, causal recipe selection and skill eligibility require external audit.
No hash or readiness gate can establish those facts on its own.

Executed from `ml/`, `.venv/bin/pytest -q && .venv/bin/ruff check src tests`:

```text
........................................................................ [ 37%]
........................................................................ [ 75%]
...............................................                          [100%]
191 passed in 32.62s
All checks passed!
```

No market archive, reserved holdout, later aggregate prices, training data or
C++ file was read/changed for this work. No order was placed or synthetic event
imported into the actual study. No new deployable edge is established.

## Next lead

Collect genuine operator-supplied records of the original processing mechanism,
including both input legs, failed submissions, leftovers, output tax and all
active time. Do not repeatedly rebuild this intake or rerun the failed battery
as new evidence. Measurement readiness, even if achieved, cannot rescue the
historical null. Any later economic trial needs its own pre-outcome registration,
adequate temporal coverage and explicit search-adjusted empirical inference.
Without actual own records, attainable processing profit remains unidentified.
