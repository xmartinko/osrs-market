# Prospective pipeline repair — 31 October 2026

The frozen daily model and the append-only prospective ledgers are retained. No
sealed holdout evaluation, model fitting, or source acquisition is part of this
repair. Nothing under `/home/martin/osrs-data/sources/` was changed.

## Daily categorical schema failure

The installed command was inspected with:

```sh
systemctl --user show osrs-ml-daily.service -p ExecStart
```

Its failing second command was reproduced directly:

```sh
uv run --project ml --frozen osrs-ml forward \
  --resolution-seconds 86400 --horizon-seconds 86400 \
  --model-dir ml/runs/phase2-real-v1/holdout/forecast \
  --history-panel /home/martin/osrs-data/assembled-v3/daily.parquet
```

```text
_catboost.CatBoostError: Invalid cat_features[0] = 12 value: index must be < 12.
```

This was **not a literal hard-coded off-by-one**. The saved model was trained on
13 named features, including `history_rows`, with `item` at index 12. The current
research matrix deliberately excludes `history_rows`, supplying 12 features.
CatBoost retrieved categorical index 12 from the saved model when constructing
its prediction Pool.

The daily forward path now constructs the matrix using the frozen training
schema, checks that schema against the saved model, and derives the categorical
index with `x.columns.get_loc("item")`. The current research feature set and the
frozen model remain unchanged. Real CatBoost regression tests cover both schemas.

```text
$ systemctl --user start osrs-ml-daily.service
$ systemctl --user show osrs-ml-daily.service -p Result -p ExecMainStatus
Result=success
ExecMainStatus=0
Oct 31 03:45:38 ... Consumed 39.517s CPU time, 911.9M memory peak.
```

The initial schema-only repair passed at the peak shown above. Restoring timers
under heavier host pressure exposed an additional daily memory failure:

```text
Oct 31 04:13:38 ... Result=oom-kill, ExecMainStatus=137, 353.2M memory peak.
```

The daily command had loaded all 1,466,390 history rows before keeping 30 per item.
It now validates the entire panel in a DuckDB connection limited to 32 MB with one
thread and disk spill, then materializes only the eight inference input columns
and 30 eligible observations per item. Model imports follow that query, and unused
context frames are released before settlement. Daily settlement and paper replay
also use the bounded archive index, avoiding the old pending-row and per-item
frame copies. The daily unit has its own `MemoryMax=384M` ceiling, zero swap, and
`OOMPolicy=stop`. Issuance time is recorded after scoring, never before the query.

Regression tests compare the resulting features against the full-panel loader,
including the legacy `history_rows` feature. They also prove that invalid data
outside the lookback still fails validation.

```text
$ systemctl --user start osrs-ml-daily.service
$ systemctl --user show osrs-ml-daily.service -p Result -p ExecMainStatus
Result=success
ExecMainStatus=0
MemoryPeak=286588928
Oct 31 04:23:02 ... Consumed 11.483s CPU time, 273.3M memory peak.
```

## Five-minute memory failure

Before the repair, the production journal and unit state reported:

```text
Oct 31 03:42:00 ... A process of this unit has been killed by the OOM killer.
Result=oom-kill
ExecMainStatus=137
MemoryPeak=2290483200
Oct 31 03:42:00 ... Consumed 1min 11.242s CPU time, 2.1G memory peak.
```

The same forward CLI was also reproduced under a transient user service capped
at 768 MiB, with a wrapper recording RSS at function boundaries. This avoided
another unrestricted host-memory failure:

```text
STAGE archive_observations before maxrss_kib=178792
STAGE archive_observations after maxrss_kib=602828
STAGE issue before maxrss_kib=602828
STAGE issue after maxrss_kib=602828
STAGE settle before maxrss_kib=602828
Result=oom-kill
ExecMainStatus=137
Consumed 15.999s CPU time, 768M memory peak.
```

The live ledger already held 1,475,404 predictions, and the archive had 546
snapshots. The old path loaded the entire archive into pandas, made per-item
frames for settlement, materialized pending/cohort predictions with `fetchall`,
and built full Python record lists for hashing and replay. SQL queries also
repeatedly fetched large prediction contexts from the 2.5 GiB ledger.

The replacement uses a rebuildable SQLite archive index beside the ledger:

- Checksum-verified Parquet input is read in batches of at most 4,096 rows. Each
  snapshot and its cache checkpoint commit together. Earliest-fetch revision
  selection is preserved; every archived snapshot remains authoritative.
- Prediction issuance materializes only the existing freshness window. Its
  issue time is captured after index construction, preventing backdating.
- Settlement scans the ordered identity index and fetches only pending contexts
  and the first eligible outcome. Covering indexes support horizon, cohort,
  identity, and score queries without loading full prediction contexts.
- Archive and run identities are hashed incrementally with the same canonical
  encoding as before. Real events are decoded once and shared across simulations;
  each cohort receives only its own synthetic decisions, with zero volume.
- Each simulation retains its independent portfolio state. Scores occupy one
  timestamp at a time. A paper run and all its fills commit atomically.

The installed and repository units set `MemoryAccounting=yes`, `MemoryMax=768M`,
`MemorySwapMax=0`, and `OOMPolicy=stop`. A ten-minute timeout permits a cold index
build plus replay; the measured normal replay completes within the five-minute
collection interval. No historical predictions or outcomes are removed.

Regression tests compare every ledger table, metrics, identities, nullable
integer contexts, revisions, missing sides, and different cohort start times
against the original full-frame implementation. A real SIGKILL during fill
insertion proves rollback and duplicate-free resume. An interrupted cache import
also rolls back, and cached snapshot checksums are rechecked.

## Final verification

The final daily unit result is recorded above. Two consecutive forward starts
were then run against the final implementation. Both collected new snapshots:

```sh
systemctl --user start osrs-ml-forward.service
systemctl --user show osrs-ml-forward.service -p Result -p ExecMainStatus
# Repeat immediately after completion, also recording MemoryPeak and the journal.
```

Run 1:

```text
Result=success
ExecMainStatus=0
MemoryPeak=387555328
InvocationID=4edc4094d90d4a8e96161d57abd62352
Oct 31 04:26:33 v2202605360246461845 systemd[1020]: osrs-ml-forward.service: Consumed 1min 32.330s CPU time, 369.6M memory peak.
```

Run 2:

```text
Result=success
ExecMainStatus=0
MemoryPeak=215445504
InvocationID=f507a60545a2487ba15aa0146652ceac
Oct 31 04:28:30 v2202605360246461845 systemd[1020]: osrs-ml-forward.service: Consumed 1min 16.900s CPU time, 205.4M memory peak.
```

The initial cold index construction also stayed below the 768 MiB ceiling
(about 538 MiB). Snapshot publication, ledger rows, and completed paper runs are
retained across retries. A previous production rerun of an unchanged snapshot
returned identical ledger counts with zero additional predictions or outcomes.
The timers were paused for maintenance and restored after verification.

```text
$ cd ml && uv run --frozen pytest -q
384 passed, 1 warning in 99.37s
$ cd tui && PATH=/home/martin/.cargo/bin:$PATH cargo test --release
31 passed; 0 failed
```

The Python warning is the existing Starlette/httpx deprecation. Ruff checks for
the changed Python files also pass. Replay still traverses retained history;
its input frames, observation buckets, and score lookups are bounded rather
than materializing the entire archive or cohort in memory.
