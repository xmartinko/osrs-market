# Independent research function 3: flow-based generative forecasting

Prepared 2026-11-01 by a native Codex subagent, not DeepSeek. Scope: determine which conditional flow experiments can isolate added shape/dependence value and what the cited papers actually support. No training, installation or archive modification occurred.

## Findings and evidence classification

**Established mathematical distinction:** discrete invertible flows permit change-of-variables densities; flow matching typically regresses a continuous vector field and is evaluated through generated samples. Flow-matching loss is not NLL. Continuous-flow likelihood is possible with extra divergence/ODE computation. A latent-flow likelihood is not automatically an observed-price likelihood.

**Published methods:** [Neural Spline Flows](https://arxiv.org/abs/1906.04032), [MAF](https://arxiv.org/abs/1705.07057), [Flow Matching](https://arxiv.org/abs/2210.02747), [TSFlow](https://arxiv.org/html/2410.03024v2), [ProFITi](https://ojs.aaai.org/index.php/AAAI/article/view/35494).

**Material published limitation:** ProFITi does not guarantee marginal consistency across query subsets; see [Appendix G](https://arxiv.org/html/2402.06293v3#A7). TSFlow's scope is predominantly univariate; benchmark performance cannot justify all-item joint claims.

**Hypothesis:** a four-block conditional spline coupling flow on H=24 hourly return increments may improve shape/dependence forecasts beyond low-rank Gaussian and Student-t alternatives. **Separate hypothesis:** a GP-informed CFM source distribution may reduce transport complexity, but could impose inappropriate smoothness.

## Assumptions, competitors and falsifiable tests

Requires sufficiently many valid joint future windows and a stable definition of the observed target. Masking missing coordinates does not automatically yield a correct flow marginal likelihood. Stale-price atoms and integer measurement need common scoring conventions. Benchmark likelihood improvements on health/weather data are not financial evidence.

Run independent marginal spline versus Gaussian/t heads; joint spline versus independently sampled marginals and low-rank Gaussian; iid versus GP-informed CFM prior; fixed-grid versus subset-query consistency. Derive path events from one fixed-grid joint sample set. Hold information and selection budgets common. Failure to improve proper scores or tail calibration is a negative result; realistic-looking paths are irrelevant to the acceptance rule.

## Complexity, recommendation and confidence

First candidate: GRU/MLP conditioner width 64, four spline coupling blocks, eight bins, H=24. Budget allowances: 2–6 GB VRAM and a 2 GPU-hour cap per candidate; CFM 4–10 GB and 4 GPU-hours, all unmeasured. ProFITi and latent/CNF variants are later candidates requiring demonstrated need. Use one GPU and independent jobs, not mixed-generation distributed synchronization.

High confidence in these architecture distinctions and order of tests; low confidence in OSRS superiority and hardware estimates until authorized experiments. Details, equations, missingness cautions, exact ablations and stop rules are in [05_flow_models.md](../05_flow_models.md).
