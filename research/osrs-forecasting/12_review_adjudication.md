# Principal adjudication of independent reviews

2026-11-01. Reports are preserved verbatim in agent_reports/, including incorrect assertions. Tool-free DeepSeek reviews are critiques of supplied evidence, not independent empirical or literature audits. Native workers 2/3 and 4/5 share executors; independence applies between workers, not every named function. This is a limitation, not seven independent replications.

## Accepted challenges

- Physical observation count is not effective sample size. Block uncertainty, common cross-sectional shocks, source overlaps and a small number of market regimes constrain claims.
- A 56-day prospective test has only about 8 weekly blocks. Its interval precision must be evaluated; broad all-regime claims need independent future replication. Do not extend until significant or rerun a revealed holdout.
- 90% interval coverage within 87–93% is a proposed coarse gate, not full conditional calibration. Use PIT/reliability by horizon/liquidity/regime, dependence-adjusted uncertainty and tail Brier diagnostics. Passing coverage alone does not establish trustworthy path risk.
- Canonical timestamps, overlapping source resolution, source identity and current-only metadata remain critical blockers before training. Explicitly distinguish old assembled-v3 from later acquired source partitions.
- Economic scenario gains do not identify attainable profits. Real-time forecasts and voluntarily recorded order/fill histories would materially improve validity, but collection/execution is not authorized here.

## Rejected or corrected reviewer claims

1. **Holm requires orthogonal hypotheses:** incorrect. Holm controls familywise error under arbitrary dependence when individual p-values are valid. The actual concerns are valid dependence-aware tests and accounting for every confirmatory claim. See [Holm 1979](https://www.jstor.org/stable/4615733).
2. **Underpowered by deduction from 38 blocks, or mandatory 30 blocks or three prospective windows:** unproved. Power depends on variance, dependence and effect size; block count alone establishes none of these thresholds. Require development-only variance/power assessment and report inconclusive results. Three independent future windows are useful replication, not a universal mathematical prerequisite.
3. **KS on pooled PIT is a definitive calibration gate:** incorrect under serial dependence or parameter estimation, and uninformative for some conditional failures. Use dependency-aware calibration diagnostics. No single pooled uniformity test is a proof.
4. **Latest high/low trade age is ingestion latency:** incorrect. Observation time minus trade time measures age at snapshot, combining no trading/reporting delay; publication and ingestion latency need separate timestamps. The forensic report's proposed age-based latency test does not recover unknown historical availability.
5. **Any decimal mirror mismatch invalidates the mirror:** too strong. Observed rounding can be a documented measurement transform. Compare representations, keep precision strata and use source-priority rules; quarantine unexplained conflicts. One rounded observation does not prove all data contaminated.
6. **Duplicate rate > 0.5% proves unclean; zero-volume prevalence falsifies volume usefulness:** arbitrary or unsupported. Overlapping mirrors are expected. Admission requires explicit canonical deduplication and semantic integrity, while predictive usefulness requires a separate controlled ablation. Valid zero-volume buckets are observed zeros, not necessarily censoring.
7. **Proposed before/after September 30 scans are automatically holdout-excluded:** false for this project's reserved interval. Do not run those observation scans on sealed rows. This phase reads already published quality summaries and a latest snapshot after the original export ends; Phase One historical development must stay before the reserved start, or use explicitly approved independent/prospective data. Any use of sealed data requires a separate decision, never an implicit research exception.
8. **Identical encoder required for CatBoost fairness:** impossible literally. Match information set, targets, origins and search opportunity; shared encoders isolate neural head differences only. Item macro-averaging/strata address concentrated results, not a formal universal fairness guarantee.

## Resolved design choices

08_experiment_matrix.md is authoritative for proposed numeric settings:3confirmatoryclaims,7dayblocks with3/14sensitivity,2%marginalCRPS threshold,5%variogram threshold and≤1%marginal degradation gate,56day future test subject to a preregistered precision assessment. Earlier independent suggestions differ and remain in their original reports for provenance. Thresholds are project choices, not published universal cutoffs.

No significance, normality, autocorrelation, profit or hardware benchmark was computed here. Neither review establishes success or market efficiency. If precision/data gates fail, defer claims and register a new independent test rather than defending the architecture.
