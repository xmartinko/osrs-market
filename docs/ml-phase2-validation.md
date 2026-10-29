# Phase 2 real-data qualification and evaluation

This extends checkpoint `107cfbf` on `ml/financial-model`. No C++ or database schema changes.
Generated data stays under `$OSRS_DATA_DIR` (default `/home/martin/osrs-data`) or ignored `ml/runs`.

Assembly command executed: `uv run --project ml --frozen osrs-ml assemble`.
Output: `/home/martin/osrs-data/assembled-v3/quality.json`, panel manifests, per-item
coverage Parquet, and full observed-gap histogram CSV. SQL writes Parquet directly;
nullable integer prices remain integers. Source interval remains NULL: timestamp phase
is inference, not recovered provenance. Inverted spreads remain flags and cannot trade.

| Panel | Rows | Items | Calendar days | Two valid sides, not inverted | Inverted | Items ≥300 days | Items ≥300 usable rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| Daily candidates (audit only) | 1,495,260 | 4,523 | 366 | 1,208,448 | 125,936 | 3,876 | 2,618 |
| Strict daily | 1,466,390 | 4,523 | 359 | 1,190,676 | 124,974 | 3,859 | 2,577 |
| Hourly | 450,822 | 4,445 | 7 | 293,497 | 12,162 | 0 | 0 |
| Five minute | 481,052 | 4,214 | 2 | 183,126 | 5,148 | 0 | 0 |

Strict daily cuts at the first global non-midnight observation (`1792638000`);
hourly cuts at the first non-hour observation (`1793156700`). Midnight rows in the
mixed tail and hourly-boundary rows in the fine panel are excluded, since overwritten
source resolution cannot be identified. These deliberately incomplete intraday panels
never double-count daily/hourly volume. The audit candidates count differs from the
user's earlier builder by 520 rows and one item at ≥300 days; no unsupported repair is
made to force the count. A provenance-preserving collector removes this ambiguity going forward.

Raw null rates from executed assembly: high 12.919659%, low 12.760343%, midpoint
25.680002%, current limit 6.872986%. Strict daily: high 4.422630%, low 5.857037%,
midpoint 10.279666%, current limit 7.560062%. Missing buckets within observed item
lifetimes: daily 107,882; hourly 154,827; five minute 627,051. Intraday missing counts
include deliberately excluded boundaries. Noncanonical consecutive gaps: 231,792;
this includes missing-bucket multiples and resolution transitions, not just clock jitter.
Coverage is an audit, never an ex-post survivor filter for model inclusion.

No point-in-time historical buy limits were exported. They remain NULL; current
metadata is explicitly named and excluded from features. Strict execution therefore
cannot buy. Current-limit execution is a separate lookahead-sensitive capacity study.
Aggregate-side freshness is an interval bound, not an observed trade timestamp;
availability assumes start + inferred interval + 300s. Historical ingestion times are unknown.

Tax boundary verified against [OSRS Wiki Grand Exchange](https://oldschool.runescape.wiki/w/Grand_Exchange):
prices **below** 50 are exempt; exactly 50 pays floor(50×0.02)=1 gp. The checkpoint
already corrected this. Phase 1's exempt-through-50 description is superseded.
Rate 2%, per-unit flooring, 5M cap. Item exemptions are configurable but not populated;
this overcharges exempt items. [Wiki API documentation](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices)
describes aggregate blocks; none is an executable quote or an order book.

Frozen protocol: `ml/experiments/daily-v1.json`. A 90-day holdout is partitioned before
feature construction. Three expanding 28-day validation blocks precede it; training
labels ending at or after each boundary are purged. Daily-specific causal features
replace the phase-1 intraday feature windows. Parameters are fixed without searching.
All candidates and scenarios are evaluated; selection uses development moderate gp/hour
and is persisted before the holdout command can run. No-change is the random-walk forecast.
