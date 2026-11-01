# Risk register and adversarial decisions

No positive predictive or economic result has been demonstrated by this phase. Existing docs/deliberation-after-null.md reports 213 corrected null tests and large execution-price dependence; this is prior project evidence, not independently reproduced here.

| Risk | Evidence / uncertainty | Falsification / action |
|---|---|---|
| No stable predictable signal | Market hypothesis unknown; prior null discouraging | Flow fails strongest RW/Student-t/CatBoost after adjustment: stop architecture escalation |
| Availability leakage | Old export lacks source resolution and real historical latency | Gains disappear at bucket-end+delay; retire leaked feature, register fresh test |
| Timestamp corruption | Mirror raw timestamp is bucket index; latest canonicalts is snapshot time | Unresolved semantics quarantine; no general timestamp parser |
| Coverage/source break | September 30 client coverage plus GE mechanics and decimal precision changes | Gains concentrated at transition or vanish within-era: no stationary/general claim |
| Duplicate pseudo-replication | Overlapping 941 million physical rows | Require key/lineage reconciliation; no sample-size claim based on raw rows |
| Selection/survivorship | Current mapping differs from historical IDs | Training-only universe and lifecycle sensitivity; no extrapolation to disappeared items |
| Aggregate fills unidentified | No order book/queues/own fill ledger established | No-fill lower bound remains zero opportunity; no real profit claim |
| Gaussian tails/discreteness | Hypothesis, requires residual checks | Student-t/empirical hurdle baseline wins; report Gaussian failure |
| Flow overfitting | High capacity vs effective regimes | Calibration worsens or no practical gain: no-go; attractive samples irrelevant |
| Joint model unnecessary | Marginal gain may explain path-score gain | Marginal-preserving shuffle/copula matches joint model: no dependence benefit |
| Reused final test | Existing development/holdout history and published summaries | Preserve old holdout; new prospective locked test; no architecture tuning after reveal |
| Weak inference | Only about eight weekly blocks in the proposed 56 days | Inconclusive intervals→no claim; independently registered future replication |
| Multiplicity/search bias | Seven workstreams and many ablations | Three confirmatory claims; report all attempts; further claims new preregistration |
| Insufficient tail events | Rare barriers/liquidity strata | Fewer than 50 positive events descriptive; adjust future power plan prospectively |
| Rights/provenance | Private source restrictions, current upstream policies | No new acquisition/public raw redistribution; source-specific review |
| Heterogeneous compute | Pascal unsupported by CUDA13, desktop interactive, ThinkPad thermals | Independent queues; no DDP without benchmark; no reboot/install during Phase Zero |
| Storage loss | Homelab overview says no formal backup regime | Require independent snapshot integrity plan before major future data work; research Git is not dataset backup |

Consequential unknowns: canonical unique observation count; actual per-item null/outage profile for broad archive; reliable historical availability; historical limits/metadata; prior holdout exposure chain; actual forecasting signal; calibration under reporting shift; own execution evidence; memory/time benchmarks. Each is a condition to test, never a fact to fill in from memory.

Independent adversarial review is in agent_reports/adversarial_review.md. Its reasoning is evidence-informed critique, not a new audit or empirical replication. Review disagreements must remain visible; safety gates override attractive performance.
