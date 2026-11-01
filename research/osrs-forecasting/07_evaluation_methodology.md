# Evaluation and statistical validity

Phase Zero design, 2026-11-01. This document proposes tests; it reports no trained-model results. Native Codex research, not DeepSeek execution.

## Common dataset and information boundary

Freeze one immutable derived dataset manifest, eligible item universe, target definition, missingness treatment, as-of feature timestamps, split boundaries, compute limits and score weights for all competitors. A row is eligible at forecast origin only after its aggregate closes and its publication/ingestion delay has elapsed. If ingest times are absent, label timing fidelity unverified and test conservative delays; never assume zero latency. Fit scalers, item selection, liquidity strata, clipping thresholds and feature selection on training data only. Keep outcome extremes in evaluation; document invalid prices separately.

Existing archive/project development makes retrospective periods potentially contaminated. Reserve a **prospective** locked test beginning only after protocol and code/config hashes are frozen; choose exact dates after archive continuity and latency audit. A split of old data is useful exploratory evidence, not a newly untouched test. Do not expose test scores during model/policy selection.

Use chronological rolling origins with common cutoffs across all items. Training labels must end before each validation origin; purge H-step overlapping labels at boundaries. Forward-only training needs no arbitrary blanket history-length gap when past features are legitimately available; add embargo only for actual publication/revision overlap or label construction. For primary tests, space origins by the tested horizon where feasible; retain dense overlapping-origin diagnostics with dependence-aware inference. All test labels must be complete. Seven-day horizons need many independent weeks, not just many item rows.

## Baseline ladder

1. Constant last valid price / zero-return point forecast; probabilistic random walk with train-only empirical or Gaussian increments. The deterministic baseline is valid for MAE/CRPS but has degenerate likelihood; do not use its infinite NLL as a sophisticated-model victory.
2. Past rolling drift/volatility, empirical block-resampled paths and daily/weekly seasonal naive when supported. Include a no-drift EWMA Gaussian and Student-t forecast so flows cannot win merely by learning changing scale or heavy tails.
3. Exponential smoothing, a small ARIMA order grid, Gaussian/Student-t GARCH for selected liquid series, ridge/elastic-net lag regression, and a shallow tree quantile model with noncrossing postprocessing fixed on validation.
4. Small shared MLP or GRU probabilistic model, diagonal Gaussian and Student-t heads, then structured joint Gaussian. Match encoder/features and parameter budgets where testing distribution family.

Keep per-item statistical models optional at large universes; pre-specify representative training-selected strata. Hyperparameter opportunities are a confound: log every trial including failed runs and allocate comparable bounded search budgets.

## Scores and diagnostics

Use lower-is-better convention. `CRPS(F,y)=E|X-y| - 0.5 E|X-X'|`; energy score replaces absolute value by Euclidean norm for vectors. They support sample-based competitors. [Proper-score theory](https://doi.org/10.1198/016214506000001437). For Monte Carlo scoring, use equal sample budgets and an unbiased pairwise estimator or independent sample pairs; do not favor a model through more samples.

| Objective | Primary/secondary evidence | Guardrail |
|---|---|---|
| Marginal distributions | Primary mean CRPS on train-scaled log cumulative returns; WIS as secondary | Fixed item/horizon weights; also show GP-scale errors |
| Point forecast | MAE using median; RMSE using mean | Direction accuracy specifies zero-return/tie handling and base rate |
| Density | NLL for models with comparable densities | Same target, support, masks and Jacobians; don't compare KDE of flow samples against exact densities |
| Intervals | 50/80/90/95% empirical coverage plus widths by strata | Sharpness evaluated alongside calibration |
| Distribution calibration | PIT, reliability by horizon/liquidity/regime, residual autocorrelation | Randomized PIT for atoms/discrete targets; pooled uniformity can hide conditional failure |
| Joint paths | Energy score plus variogram score | Energy can weakly discriminate covariance errors |
| Path events | Brier scores for pre-fixed gain/drawdown/hitting-order events | Evaluate only grid-observable events; require enough positives and negatives |

WIS uses a fixed quantile grid and penalizes both width and missed intervals. [Bracher et al.](https://doi.org/10.1371/journal.pcbi.1008618). For dependence sensitivity use `VS_p = sum_ab w_ab (|y_a-y_b|^p - E|X_a-X_b|^p)^2`, p=0.5 with weights fixed before testing; it supplements rather than replaces marginal scores. [Scheuerer and Hamill](https://repository.library.noaa.gov/view/noaa/22327/).

Scales and weights must be determined without test outcomes. For cross-item CRPS, divide by a strictly positive train-only robust scale and macro-average items; show liquidity-stratified and economically weighted diagnostics separately. Avoid percentage skill ratios for zero-scale items; exclude with a recorded validity rule or report absolute score differences. Freeze sample count at 256 for screening and 1024 for finalists; evaluate rare-event Monte Carlo error separately. These are proposed budgets, not benchmarks.

## Compare joint forecasts without conflating marginals

Compare recursive one-step sampling, direct independent marginals, structured joint Gaussian and joint flow on identical origins. Add a decisive ablation: shuffle each horizon's sample indices independently, preserving empirical marginals while destroying path dependence. Any claimed trajectory advantage should beat this comparator on path-event Brier and variogram scores. Also compare a train-only residual copula attached to the same marginals. Realistic-looking plotted paths are a diagnostic, not evidence of skill.

## Inference, multiplicity and practical thresholds

Compute paired loss differences by origin after the pre-fixed item aggregation. Resample contiguous **time blocks with the complete item vector retained**; never treat thousands of correlated item-origin rows as independent replicates. Use seven-day blocks with three/fourteen-day sensitivity for the proposed hourly campaign, subject to development-only power checks before registration. Use stationary or moving-block bootstrap only within plausibly stable strata; it does not repair an unidentified structural break. [Politis and Romano](https://doi.org/10.1080/01621459.1994.10476870). Report effective time blocks and confidence-interval sensitivity; cross-item generalization needs a separate item-cluster/held-out-item study.

The final proposed confirmatory family is the three claims C1 Gaussian marginal skill, C2 path dependence and C3 flow marginal skill in 08_experiment_matrix.md. Apply Holm familywise correction at 0.05; additional horizons/ablation/stratum discoveries are exploratory. [Holm](https://www.ime.usp.br/~abe/lista/pdf4R8xPVzCnX.pdf). Holm permits arbitrary dependence when individual tests are valid; independence or orthogonality is not required. Neural seeds assess optimization variability and are not independent market histories. Report each seed and mean, without choosing the best test seed. Use a HAC loss-difference check as sensitivity, with stationarity and small-sample limitations.

Proposed practical threshold, explicitly a project choice: at least 2% aggregate CRPS improvement with adjusted evidence of improvement and no material deterioration of calibration. Target 90% coverage within +/-3 percentage points when dependence-adjusted uncertainty is sufficiently narrow. Require consistent sign in at least two pre-specified walk-forward windows; an underpowered interval means inconclusive, not failure or success. Joint complexity additionally needs at least 5% improvement in the pre-fixed variogram score without marginal degradation beyond 1%, as specified in 08_experiment_matrix.md. Validate these thresholds and power on development data before freezing. A 56-day future test is a bounded first confirmation, not evidence of all-regime generalization.

## Falsifiable experiments and cost

| Test | Null | Design and failure interpretation |
|---|---|---|
| Information timing | Apparent gains survive correct timing | Delay features by verified latency and one extra bar; collapse indicates leakage or brittle stale-price prediction |
| Complexity | Flow has no practical advantage over Gaussian/t | Common encoder and budget; failure keeps simpler family |
| Path dependence | Joint dependence adds no useful information | Marginal-preserving shuffle and residual copula; no event-score gain rejects trajectory premium |
| Pooling | Global training adds no skill | Individual/group/global fits, common time split and held-out-item study; contemporaneous correlation alone is insufficient |
| Adaptation | Triggered retraining adds no value | Fixed/rolling/expanding vs past-only drift trigger with equal retraining budget; all trigger parameters validated before test |
| Economic usefulness | Distribution-based policy has no net advantage | Frozen policy, dated frictions, capital ledger, delay/fill sensitivity; predictive success can coexist with economic failure |

Evaluation can dominate cost: for M samples and H horizons naive pairwise CRPS/energy costs O(M^2 H) per origin; use sorted univariate CRPS or fixed independent pairs and chunked vector scores. Store seeds and sufficient scores, not every path for every origin. Screening can use a fixed sparse-origin subset; final evaluation uses the pre-registered population. Hardware runtime remains unmeasured.

## No-go and limitations

No confirmatory claim if timing, target availability, item inclusion or test independence cannot be established. Stop neural escalation if well-calibrated empirical/t baselines match it within uncertainty under the bounded budget. Stop economic claims if only optimistic fills produce gains. The primary risks are short post-break history, unknown ingest delays, survivor-selected panels, public-aggregate execution ambiguity, rare events and researcher degrees of freedom. Confidence is high in the methodological requirements, low in any claim of achievable OSRS skill before audit and testing.
