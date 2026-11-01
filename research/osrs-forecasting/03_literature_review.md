# Literature review and evidence boundaries

Phase Zero, 2026-11-01. Prepared by a native Codex research subagent; DeepSeek execution is not claimed. No models were fitted. Existing project results remain development evidence, not a newly independent replication.

## Reading map

| Primary source | Established contribution | What it does not establish here |
|---|---|---|
| [Rasmussen and Williams, Gaussian Processes for Machine Learning (2006)](https://gaussianprocess.org/gpml/chapters/RW.pdf) | Function-space Gaussian priors and posterior prediction | Gaussian OSRS residuals, profitable decisions, or scalable dense fleet-wide fitting |
| [Titsias, sparse variational GPs (2009)](https://proceedings.mlr.press/v5/titsias09a.html) | Inducing-variable variational approximation | An automatic solution to nonstationarity or cross-item dependence |
| [Bishop, Mixture Density Networks (1994)](https://www.microsoft.com/en-us/research/publication/mixture-density-networks/) | Conditional mixtures learned through a network | Evidence of conditional multimodality in this archive |
| [Salinas et al., low-rank Gaussian copula processes (2019)](https://proceedings.neurips.cc/paper/2019/hash/0b105cf1504c4e241fcc6d519ea962fb-Abstract.html) | Structured covariance and non-Gaussian marginals for multivariate forecasting | OSRS covariance stability or sufficient independent market regimes |
| [DeepAR](https://arxiv.org/abs/1704.04110) | Global autoregressive probabilistic forecasting | A reason to omit per-item, linear, tree, or persistence comparators |
| [Masked Autoregressive Flow](https://arxiv.org/abs/1705.07057) | Density estimation through stacked autoregressive transformations | Low-cost parallel ancestral sampling in every parameterization |
| [Neural Spline Flows](https://arxiv.org/abs/1906.04032) | Invertible rational-quadratic spline transforms | Guaranteed calibrated tails or extrapolation |
| [Flow Matching](https://arxiv.org/abs/2210.02747) | Vector-field regression for continuous generative flows | That training loss is a log likelihood or trading objective |
| [TSFlow, version 2](https://arxiv.org/html/2410.03024v2) | GP-informed priors for time-series flow matching | Financial predictive signal or a validated thousands-item joint forecaster |
| [ProFITi, AAAI 2025](https://ojs.aaai.org/index.php/AAAI/article/view/35494) and [full text](https://arxiv.org/html/2402.06293v3) | Conditional flows over irregular queried observations | Projective consistency across arbitrary query subsets |

## Findings that change experimental design

**Published finding:** TSFlow combines a structured prior with flow matching. Its limitations emphasize predominantly univariate testing. Its A100 runtime table is a benchmark configuration, not a timing prediction for the homelab. Kernel choice belongs in validation. [Paper, sections 3, 6, A.8](https://arxiv.org/html/2410.03024v2).

**Published limitation:** ProFITi Appendix G explicitly identifies lack of guaranteed marginal consistency. This matters if a 24-hour forecast changes when a 7-day query is added. Fix the grid for each experiment and derive reported marginals and event probabilities from that grid's joint samples; test query-subset sensitivity separately. [Appendix G](https://arxiv.org/html/2402.06293v3#A7).

**Deduction:** Published benchmark gains cannot be transferred to OSRS. This archive mixes historical resolutions and sources; measurement and aggregation changes can mimic improved predictability. A regular hourly series and a sparse irregular feed are different tasks. Neither paper proves that a conditional density can learn market signal beyond changing volatility.

**Deduction:** Conditional Gaussian likelihoods, GPs, and mixtures solve different modeling problems. A neural Gaussian head can forecast heteroskedastic residuals without a GP. A GP imposes covariance over input locations. A mixture is generally non-Gaussian despite Gaussian components. Use distinct model IDs and hypotheses.

## Evidence policy

Source access was through primary papers and publisher/author pages. DOI access for ProFITi failed initially; the AAAI publisher page and arXiv full text were accessible. TSFlow versions and ProFITi preprint/publication abstracts differ in wording of benchmark gains; no numerical gain is imported into OSRS expectations. Versions should be pinned in the eventual bibliography and implementation manifest.

All OSRS efficacy claims remain hypotheses. Proposed GPU budgets in model documents are planning bounds, not measurements. Prior project model selection makes a fresh prospective final test preferable to relabeling an already inspected period as untouched.

## Research sequence

First establish as-of data validity and strong conventional baselines, including existing CatBoost work. Then isolate conditional scale, temporal covariance, and marginal shape. Only then test a spline flow against the strongest Gaussian and Student-t models with matched input information. TSFlow is a later prior-structure ablation; ProFITi is conditional on genuine irregular sampling needs. See [Gaussian candidates](04_gaussian_models.md), [flow candidates](05_flow_models.md), and [experiment matrix](08_experiment_matrix.md).
