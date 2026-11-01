# Independent research function 2: Gaussian forecasting

Prepared 2026-11-01 by a native Codex subagent, not DeepSeek. No empirical models were run. Scope: distinguish candidate Gaussian families, rank them, and define tests that can falsify their usefulness. The project/archive inspection belongs to the lead's data audit.

## Key findings and mathematical justification

**Established mathematics:** Gaussian conditional likelihood, GP function prior, Gaussian mixture and latent Gaussian state model are separate model classes. A multivariate Gaussian can forecast a coherent joint trajectory and therefore is the first direct competitor to a joint flow. Cumulative returns transform increment covariance linearly. A finite Gaussian mixture is not a Gaussian distribution and can fit skew/modes, but fixed finite-variance components do not give asymptotic power-law tails.

**Published methods:** [GPML](https://gaussianprocess.org/gpml/chapters/RW.pdf), [variational sparse GPs](https://proceedings.mlr.press/v5/titsias09a.html), [mixture density networks](https://www.microsoft.com/en-us/research/publication/mixture-density-networks/), and [low-rank Gaussian copula forecasting](https://proceedings.neurips.cc/paper/2019/hash/0b105cf1504c4e241fcc6d519ea962fb-Abstract.html) supply relevant constructions. None validates OSRS efficacy.

**Deduction:** prioritize ridge/EWMA scale, conditional Gaussian head, and diagonal-plus-low-rank increment covariance. A small state-space model and GP subset can test whether explicit latent smoothness helps. Full thousands-item covariance and dense all-history GPs are poorly motivated before a small comparison succeeds.

## Assumptions and limitations

Requires positive meaningful price proxies, as-of histories, sufficient contiguous windows, and a known measurement process. Existing development experiments cannot establish independence of an old final period. Mixed resolutions cannot be used to manufacture short-horizon labels. Unconditional heavy tails may reflect changing conditional variance; they do not alone prove conditional Gaussian failure. Global models may transfer sampling artifacts as easily as economic information.

## Competing approaches and falsifications

Compare Student-t, past-residual bootstrap, persistence and existing CatBoost on exactly the same observations. Hold mean/encoder fixed when testing scale; hold marginal flexibility fixed when testing dependence. Reject complexity if proper-score gains do not survive the lead's paired block comparison, if coverage deteriorates during stress, or if gains disappear under source-regime separation. Test grouped/global pooling versus per-item models under common chronological splits.

## Complexity, confidence and recommendation

Gaussian heads are moderate implementation work; structured covariance adds modest algebra at H=24. Dense GP cost grows cubically in observations; sparse approximations trade accuracy and inducing-point tuning for scale. Small CPU controls and <=1M-parameter heads are appropriate first candidates. Planning allowances: 1–4 GB VRAM and 0.25–2 GPU-hours per bounded candidate, not measured runtimes.

High confidence in a staged comparison, moderate confidence in small GP/state-space controls, low confidence in any OSRS performance expectation. Full specifications, equations, family ranking and experimental hypotheses are in [04_gaussian_models.md](../04_gaussian_models.md). This report is independent scientific analysis, not a new result or claimed replication.
