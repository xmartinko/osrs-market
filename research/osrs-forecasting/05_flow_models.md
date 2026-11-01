# Flow forecasting: candidates, likelihoods and identifiable tests

Phase Zero, 2026-11-01. No flow was trained, benchmarked or installed. All OSRS usefulness statements below are hypotheses or design judgments.

## The question

Does flexible conditional shape or dependence improve calibrated predictions beyond the best Gaussian, Student-t, empirical and existing tree baselines, at matched information and a bounded compute budget? A plausible generated path is not evidence. Model shape, joint dependence and the history encoder must be tested separately.

For a fixed d-dimensional future-return grid, an invertible transform y=f_theta(z;x), z~p_0 gives log p(y|x)=log p_0(f_theta^-1(y;x))+log|det J_f^-1|. This is an exact change-of-variables identity for a discrete flow, up to floating-point error, when its Jacobian is computable. A conditional normalizing flow and a flow-matching objective are not interchangeable labels.

Flow matching commonly trains a vector field v_theta(s,y_s,x) by a squared regression loss along a chosen probability path, where generative time s is distinct from market time. For the simple interpolation y_s=(1-s)z+s*y, a target velocity is y-z. Sampling solves an ODE from s=0 to 1. The training loss is not NLL. A continuous flow can in principle obtain density by integrating divergence, but that adds numerical and often trace-estimation cost. Do not place its regression loss in the NLL results column. [Flow Matching](https://arxiv.org/abs/2210.02747).

## First architecture: conditional rational-quadratic spline coupling flow

**Proposed configuration, not a benchmark:** one item per example, hourly log-return increments, H=24, a shared small GRU or MLP history encoder (width 64), four coupling blocks, eight spline bins, alternating masks/permutations, and bounded scale/spline parameters. Start with <=1M parameters. Use the same history, masks, item representation and volume availability as the Gaussian/Student-t heads. Two/four/six blocks are a depth ablation only after the first candidate passes validation.

The spline transform family and analytical inverse come from [Neural Spline Flows](https://arxiv.org/abs/1906.04032). The OSRS configuration is our proposal. Gaussian and Student-t bases are competing variants, because a linear-tail spline with a Gaussian base does not automatically supply robust extreme tails. Compare tails with event Brier scores and threshold-weighted proper scores; do not infer heavy-tail accuracy from flexible central density.

Fit by conditional NLL with chronological validation and early stopping. Sample the entire H-vector once, reconstruct prices by cumulative sums/exponentiation, and derive all endpoints and path statistics from the same samples. This ensures internal consistency on that fixed grid. It says nothing about prices between grid points or arbitrary subset-query consistency.

## Alternatives and priority

| Candidate | Likelihood and sampling | Why/when to test | Main limitation |
|---|---|---|---|
| Conditional spline coupling flow | Tractable Jacobian; parallel block sampling | First flexible joint model | Shape/dependence can overfit finite regimes |
| Conditional MAF | Tractable density; ancestral generation can be sequential over dimensions | Density-oriented comparator at d=24 | Many samples/higher d can cost more |
| Direct conditional flow matching with small temporal convolution/GRU field | Primarily sampled evaluation; ODE likelihood optional | After spline candidate or Gaussian dependence signal | Solver tolerance, steps and sampling cost affect results |
| TSFlow-inspired GP prior | Structured source distribution plus conditional vector field | Isolate prior effect after basic CFM works | Prior misspecification and extra tuning |
| ProFITi | Query-conditioned invertible layers, joint density | Only when true irregular queries justify complexity | Query-set marginal inconsistency; quadratic attention cost |
| Latent flow + decoder | Often latent likelihood or ELBO only | Long/multichannel trajectories after low-dimensional success | Decoder likelihood and reconstruction loss can obscure forecast density |
| Likelihood-trained continuous normalizing flow | ODE/divergence integration | Low priority | Training and inference complexity with no established OSRS need |

The density-oriented construction is described by [Masked Autoregressive Flow](https://arxiv.org/abs/1705.07057). Coupling versus autoregressive transforms create different evaluation/sampling tradeoffs. A latent density cannot be reported as an observed-space NLL without an appropriate observation model and its integration or justified bound.

## TSFlow: what transfers and what must be tested

TSFlow uses data-dependent Gaussian-process priors in conditional flow matching, including conditional generation and optimal-transport constructions. Its principal experiments are largely univariate. [Full paper](https://arxiv.org/html/2410.03024v2).

**Our hypothesis:** a GP covariance over future increments could reduce the transport burden compared with iid noise, provided past-only fitted structure is stable. This is distinct from forecasting directly with the GP. For a joint Gaussian over observed context c and future f, the conditional prior has mu_f|c=mu_f+K_fc*(K_cc+R)^-1*(c-mu_c), and covariance K_ff-K_fc*(K_cc+R)^-1*K_cf. Fit kernels and normalization using training data or as-of context only. Add positive jitter; never invert explicitly when a solve suffices.

Test iid prior, OU/Matérn prior and training-residual covariance prior with the same vector field, update count, parameter budget and sample count. If cumulative log-price priors are too smooth, test increments and inspect innovations. Choose kernels on validation. Compare random and minibatch transport couplings separately; “optimal transport” between training samples is a generative coupling, not an assertion of optimal economic decisions. Do not add periodic kernels merely because benchmark datasets contain seasonality.

## ProFITi: useful irregularity, important coherence limit

ProFITi conditions on queried times/channels and uses sorted invertible triangular attention and an invertible activation. Its appendix documents absence of guaranteed marginal consistency. [Publisher](https://ojs.aaai.org/index.php/AAAI/article/view/35494), [Appendix G](https://arxiv.org/html/2402.06293v3#A7).

**Design consequence:** a forecast at hour 24 queried alone need not match the marginal at hour 24 when hours 1–24 are queried jointly. For event comparisons, always generate a fixed full grid and marginalize samples; explicitly test subset-query divergence before exposing flexible query APIs. Missing aggregation bins should not be converted into a ProFITi problem until collector failures, genuine zero trade, and source resolution are distinguished.

## Missingness and discrete measurement

Never zero-fill future prices or score fabricated targets. A flow on a full grid generally cannot obtain the marginal density of an arbitrary partially observed target by simply dropping Jacobian terms. Initial joint-density experiments should use a prespecified complete-window cohort and report its selection bias; broader cohorts may use properly formulated masked objectives or sample-based marginal scores. The conditioning encoder can include past masks and time since last observation without inventing observations.

Continuous flows do not model zero-return point masses exactly. If staleness creates an atom, compare a hurdle model (change/no-change plus continuous changed-return density), conditional empirical distributions and Student-t. If integer-price likelihoods are compared, use common bin probability or a common explicit dequantization convention. Always include the transform Jacobian when reporting NLL in original price coordinates. A fair comparison uses the same target, support, units, masks and scored examples.

## Falsifiable ablations

1. **Marginal shape:** independent one-dimensional spline heads versus Gaussian and Student-t heads with the identical encoder. Null: flexible shape has no CRPS/WIS/tail-score value.
2. **Dependence:** joint spline versus independently sampled spline marginals, recursive one-step sampling and low-rank Gaussian. Null: joint dependence adds no event/energy/variogram score value. Post-hoc shuffling of joint samples across horizons is an additional diagnostic that preserves approximate marginals while destroying dependence.
3. **Prior:** iid versus GP-informed CFM prior, matched optimization and evaluation budget. Null: prior structure adds no score or fixed-quality sampling-efficiency gain.
4. **Conditioning:** volume on/off, item embedding on/off and history 24/72/168 hours; choose a small registered subset instead of a full combinatorial search.
5. **Sampling:** report score convergence and runtime at 100/500/2000 paths and ODE steps 8/16/32 only on validation. Use the selected settings once on the locked test. For rare events these counts may be inadequate; quantify Monte Carlo uncertainty.
6. **Irregularity:** compare regular masked baseline with ProFITi on a genuine irregular subset and query-subset consistency diagnostic. Null: irregular modeling brings no benefit after freshness and missingness features.

Fixed budget and source-regime stratification matter more than broad architecture sweeps. Cross-item experiments should start global per-item prediction, then small predeclared related-item groups. One item per training example is not a joint all-item distribution.

## Planning envelope and stop rules

For d=24, context <=168, width 64 and batches 32–128, reserve 2–6 GB VRAM for the first spline pilot and 4–10 GB for a bounded CFM variant. These are unmeasured allowances; optimizer state alone is insufficient to estimate total memory. Start batch 32, FP32 log-density/covariance/ODE-critical operations, and profile after authorization before revising limits. An 8 GB GPU can be a reduced-batch replication candidate; no fit guarantee is asserted.

Propose at most 2 GPU-hours per spline candidate, 4 per CFM candidate, three confirmation seeds only for finalists, and a 24 GPU-hour total exploratory cap before a review. These are resource caps, not predicted runtimes. Computing 500 samples for 10,000 origins at H=24 in FP32 produces about 480 MB of raw one-channel returns before metadata; stream event summaries and retain a fixed sample subset instead of all paths. Count solver function evaluations and inference latency in every CFM result.

Stop additional flow complexity if proper scores fail to exceed the strongest simple baseline under the common registered confidence rule, tail calibration degrades, gains vanish after realistic latency, or the archive lacks sufficiently independent held-out regimes. Do not rescue a failure by displaying attractive paths. Confidence: high in the experiment order and likelihood distinctions; low in any prediction of OSRS superiority or unmeasured hardware performance.
