# DeepSeek independent review: adversarial_review

Executed2026-11-01 through OpenRouter; requested~deepseek/deepseek-flash-latest; returned model deepseek/deepseek-v4.1-flash-1017. Tool-free bounded reasoning based on supplied evidence; no independent source or archive inspection. Citation leads require principal verification. Not an experimental result.

# Agent7 Adversarial Review — Phase Zero Thresholds & Design

**Tagging:** [F] = supplied fact; [D] = deduction from supplied facts; [H] = hypothesis/lead; [C] = correction proposed.

## 1. Scope
Phase Zero only: no training, trading, or archive mutation. Review challenges proposed thresholds, power, dependency controls, the fixed 56-day holdout, fairness/calibration, path events, multiple testing, and economic inference. No efficacy is endorsed. [F]

## 2. Key Findings
1. **941,059,501 "observations" are not independent** [F]; effective N is orders of magnitude smaller. Any power calculation using raw N is invalid. [D]
2. **2% relative CRPS improvement with CI lower>0** is underpowered if the time-block bootstrap (7d, sensitivity 3/14d) is honest: 3 rolling 90d folds ≈ 270d, ~38 nonoverlapping 7d blocks — wide CIs. [D]
3. **Fixed 56-day prospective holdout** is a single realization; one path event (Sep30 RuneLite→allclients break, guide/maxcash changes) can dominate. [F][D]
4. **Calibration 87–93% at 90% target** is a coarse band; with heavy tails and regime breaks, band-pass ≠ calibration. [D]
5. **Economic scenarios are never executable fills** [F]; no order book or own fills [F] ⇒ economic inference is scenario-only, not P&L. [D]
6. **Holm over 3 claims** is fine only if the 3 claims are pre-registered and orthogonal; CRPS, variogram, calibration are correlated. [D]
7. **Fairness** across 4,513 IDs / 100 items is undefined without a fairness metric; ID-level heterogeneity likely swamps item-level. [F][D]

## 3. Math (sketch)
- Effective sample size: n_eff ≈ n / (1 + 2Σρ_k) under AR structure; with 5m buckets and H24 purge, ρ decays slowly ⇒ n_eff ≪ n. [D]
- Power for ΔCRPS/CRPS=2%: require σ_CRPS/√B_eff; with B_eff≈38 blocks, detectable effect likely >2% unless σ small. [D]
- Variogram improvement 5%: sensitive to bin choice; specify bins a priori. [C]
- Calibration: use PIT histogram + KS/CRPS-decomposition, not just 87–93% coverage. [C]

## 4. Citations (leads only; not independently read)
- [H] https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices
- [H] https://arxiv.org/abs/2410.03024
- [H] https://arxiv.org/abs/2402.06293
No browsing/filesystem tools used; no independent verification claimed.

## 5. Assumptions
- Archive integrity beyond footer/sample checks is unverified [F]; duplicate/null rates not recomputed [F]. [D] Treat as unknown-risk.
- Canonical raw timestamp = bucketindex*300 [F]; post-2026-09-30 rounded mirror vs v2 decimal discrepancy [F] is a **known contamination risk** for any post-break evaluation. [D]
- Holdout start 1785024300 unread [F]; must remain sealed. [C]

## 6. Limits
- No real order book / fills [F] ⇒ no execution realism. [D]
- Older assembled-v3 not broad archive [F]; guide history 2015–2026 not trades [F]. [D]
- Seasonal economies separate [F] ⇒ cross-season pooling invalid. [D]
- GPUs 5080/3070/1070 [F]; 1070 CPU tasks may bottleneck ablations. [D]

## 7. Competitors (baselines)
Random walk, empirical innovations, Student-t, ridge, CatBoost [F]. [D] CatBoost on 5m with leakage-prone features can beat flow models spuriously; require identical encoder and purge. [C] Add a **shuffled-path** and **independent-horizon** ablation as mandatory no-go gates. [F→C]

## 8. Falsifiable Experiments / No-Go
- **E1 Power:** pre-register minimum detectable effect; if B_eff<30, 2% threshold is a **no-go** unless σ supports it. [D]
- **E2 Dependency:** report n_eff and block-bootstrap CI width; if CI width >2× point estimate, **no-go**. [D]
- **E3 Holdout:** 56d single window is **insufficient**; require ≥3 nonoverlapping prospective windows or a pre-registered sequential test. [C]
- **E4 Calibration:** PIT uniformity test; fail ⇒ **no-go** regardless of CRPS. [C]
- **E5 Path events:** pre-specify Sep30 break handling; if model degrades >X% across break, **no-go** for that regime. [D]
- **E6 Multiple testing:** Holm only on pre-registered 3 claims; any post-hoc claim ⇒ exploratory, not confirmatory. [C]
- **E7 Economic:** scenario-only; label as **non-executable**; no P&L claims. [F→C]
- **E8 Fairness:** define ID-level error dispersion; if top-decile IDs dominate loss, **no-go** for broad deployment. [C]

## 9. Cost
- 5080 primary, 3070 replication, 1070 CPU [F]; ablations (independent, copula, shuffled) multiply runs. [D] Budget for ≥3× replication and holdout re-runs; 1070 CPU tasks likely the critical path. [D]

## 10. Confidence / Recommendation
- **Confidence: low** on efficacy; **high** that current thresholds are under-justified. [D]
- **Recommendation: NO-GO for efficacy claims.** Proceed only with: (a) n_eff and power pre-registration, (b) ≥3 prospective windows or sequential design replacing single 56d, (c) PIT calibration gate, (d) explicit Sep30 break protocol, (e) fairness dispersion metric, (f) economic claims relabeled non-executable. [C]
- Do not endorse success without data. [F]
