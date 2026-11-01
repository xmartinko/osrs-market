# Gaussian models: distinct hypotheses and staged candidates

Phase Zero proposal, 2026-11-01. No training or archive-derived distributional results are reported here. Priority rankings are research judgments, conditional on the archive audit.

## Target and conditional likelihood

For a valid observed price proxy P greater than zero, use increments r_h = log(P_(t+h)/P_(t+h-1)), conditional on information actually available at forecast issuance. Start with hourly increments and H=24 only if continuous hourly data exists; lower-resolution historical sections cannot create intraday supervision. The primary outcome is a measured aggregate-price trajectory, not an executable-price trajectory.

A conditional Gaussian head specifies r | x ~ N(mu(x), Sigma(x)). Diagonal covariance tests conditional mean and scale; it does not test temporal dependence. Use positive scale floors selected on validation, standardized targets calculated from training/history only, and finite checks. The per-target negative log likelihood is 0.5[log(2*pi) + 2 log(sigma) + ((r-mu)/sigma)^2]. Excessively small sigma can produce disastrous NLL after ordinary surprises.

For a joint target with d=H*C coordinates, enforce positive covariance through Sigma=L*L' or Sigma=D+U*U'. A low-rank model with rank k uses O(d*k) output parameters and approximately O(d*k^2+k^3) likelihood algebra, excluding the encoder. Dense Cholesky uses O(d^2) parameters and generic O(d^3) factorization. For increments, cumulative log returns equal A*r with A lower triangular ones, so their Gaussian covariance is A*Sigma*A'. This creates consistent cumulative trajectories even when increment covariance is diagonal. Compare models on the same target coordinates and transforms.

These formulas and rankings are mathematical design deductions. They are not evidence that Gaussian assumptions fit OSRS.

## Priority hierarchy

| Priority | Family and exact first candidate | Data needed | Expected cost and principal failure |
|---|---|---|---|
| 0 | Random walk, rolling Gaussian innovations, historical drift with shrinkage | Valid lagged returns; sufficient observations to estimate scale | CPU; persistence can win; drift easily overfits |
| 1 | Ridge mean plus EWMA scale; same features as tree baseline | Past-only lags, volume/missingness if valid | CPU; linear conditional mean may be inadequate |
| 1 | Small MLP/GRU conditional Gaussian head, diagonal increment covariance | Regular masked histories, enough distinct time blocks | One GPU, small model; variance collapse and shared-model negative transfer |
| 1 | Joint Gaussian with diagonal-plus-rank-2/4 covariance over H=24 increments | Joint future windows with observed masks | One GPU; unstable learned correlations and low effective sample size |
| 2 | Local-level/local-trend linear Gaussian state-space model, optional seasonal state | Timestamped observations and noise interpretation | CPU Kalman filtering; latent smooth price may hide jumps |
| 2 | Rolling-window GP with Matérn or OU kernel plus white noise | A few representative liquid items, limited history | Dense O(n^3) time/O(n^2) memory; long history is costly and smoothness may be wrong |
| 3 | Sparse variational GP with 32/64/128 inducing locations | Need for longer histories after small GP success | O(n*m^2) common formulation; approximation and kernel sensitivity |
| 3 | Two-component diagonal/low-rank conditional Gaussian mixture | Enough independent tail/regime examples | More likelihood modes; component collapse, label switching, overfit |
| 4 | Grouped multi-output GP or Gaussian copula factor model | Stable overlap across related items | Covariance/metadata complexity; correlations can disappear at updates |

The GP framework and its dense computation are described in [GPML](https://gaussianprocess.org/gpml/chapters/RW.pdf). Inducing-variable approximation has a variational objective rather than an arbitrary subset fit; see [Titsias](https://proceedings.mlr.press/v5/titsias09a.html). These justify bounded GP comparisons, not treating sparse GPs as mandatory.

## Family distinctions and competing explanations

A GP is a prior over functions f(x), with covariance k(x,x'). With Gaussian observation noise it yields a Gaussian posterior predictive distribution. A neural Gaussian head directly parameterizes a conditional observation distribution; its mean function is not a GP. A Gaussian mixture p(r|x)=sum_j pi_j(x) N(r;mu_j,Sigma_j) can model multiple modes. A state-space model imposes latent temporal dynamics and an observation process. They should never share one generic “Gaussian model” result row.

Conditional mixtures follow the [mixture-density-network construction](https://www.microsoft.com/en-us/research/publication/mixture-density-networks/). They remain light-tailed asymptotically for finite components with fixed finite variance. They may approximate observed tail shapes over a finite range, but that is a hypothesis to test against Student-t innovations and empirical residual resampling.

A low-rank Gaussian copula can separate marginal shape from dependence. [Salinas et al.](https://proceedings.neurips.cc/paper/2019/hash/0b105cf1504c4e241fcc6d519ea962fb-Abstract.html) provide a relevant multivariate construction. Our use would first be a small related-item group, not all tradeable items simultaneously.

For a linear Gaussian state model z_(t+1)=F*z_t+eta_t and y_t=G*z_t+epsilon_t, forecast means and covariance can be propagated recursively. The measurement variance is crucial: an aggregate is a noisy, delayed measurement, not necessarily the latent spot price. Filtering may use observations through t; smoothed latent features using later observations are forbidden.

## Falsifiable experiments

1. **Conditional scale:** compare fixed/rolling Gaussian innovations with a Gaussian head using the same zero-drift mean. Null: conditional scale provides no proper-score improvement. Evaluate CRPS, WIS, coverage and tail exceedance frequencies; a gain only in mean error does not answer this question.
2. **Temporal covariance:** hold the encoder, marginal training objective and features as close as feasible; compare diagonal, rank-2 and rank-4 increment covariance. Null: dependence adds no energy/variogram/event-score value. Marginal CRPS is insufficient to accept this hypothesis.
3. **Gaussian failure:** compare Gaussian with Student-t heads and past-residual bootstrap using the same features/encoder. Inspect past-window standardized residuals, conditional coverage, tail Brier scores and quantile losses. Unconditional kurtosis can arise from heteroskedastic Gaussian mixtures across time and alone does not falsify conditional Gaussianity.
4. **GP value:** on 10 preselected representative items, compare GP with local-level state model and ridge/EWMA using identical rolling windows and horizons. Null: kernel structure adds no out-of-sample score improvement. Stop if any gain disappears under a short-window persistence comparator.
5. **Pooling:** compare per-item, grouped and global heads, plus a global model without embeddings. Fix time splits. A shared-item model must be evaluated both on future periods for familiar items and, separately, on held-out items if transfer is claimed.

Use the common prospective holdout, paired time-block comparisons, and multiplicity controls in [evaluation methodology](07_evaluation_methodology.md). No independent thresholds should be selected after seeing test results.

## Gaussianity diagnostics and failure modes

Examine conditional residual mean, skew, quantile calibration, serial dependence in squared residuals and stress-period coverage. Account for multiple items and overlapping horizons. Integer prices and stale repeated aggregates can cause zero-return atoms. A continuous density fitted to these may win through increasingly narrow peaks rather than useful uncertainty: compare distributional scores and consider an explicit zero-change hurdle when the measurement process warrants it. Missing records are not zero returns.

Regime breaks, changing feed coverage, changing item composition, and update events can invalidate stationary covariance. Use rolling and expanding windows as controlled alternatives. Any retraining trigger must depend only on already observed forecast errors after outcomes arrive; never fit change points on the full series and then describe the resulting regime labels as available in real time.

## Complexity and planning bounds

Implementation difficulty: ridge/EWMA low; state-space and Gaussian heads moderate; low-rank covariance moderate; sparse/multi-output GP and mixtures higher. Proposed heads below one million parameters with H=24, context at most 168 hourly bins, batch 32–128 and <=100 initially selected items should be explored on one GPU. A 1M-parameter FP32 Adam model needs roughly 16 MB for parameters, gradients and two moments before activations, library workspaces, and data buffers; activation memory often dominates.

Reserve 1–4 GB VRAM as an initial planning allowance for a small head/encoder, 0.25–2 GPU-hours per capped candidate run, and 2–8 CPU-hours for bounded baseline/GP pilots. These are unmeasured budget assumptions, not hardware forecasts. Hard-cap runs and revise only after authorized profiling. Do not combine GPU memory across hosts.

## Recommendation and confidence

High confidence in testing simple heteroskedastic Gaussian and low-rank trajectory heads before flows because they isolate mean, scale and covariance at low complexity. Moderate confidence that state-space and a tiny GP subset are useful controls. Low confidence in any claim of OSRS forecasting superiority until the archive passes temporal validity checks and these comparisons run on unseen data. Student-t and existing CatBoost baselines are mandatory competitors.
