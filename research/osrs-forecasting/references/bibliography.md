# Primary references and provenance

Accessed or checked by principal/native research workers on 2026-11-01. DeepSeek reports had no browsing tools; their citations are leads, not independently consulted evidence. Archive facts are sourced separately below. No published benchmark is an OSRS result.

## Market definitions / dated rules

- [OSRS Wiki real-time API publisher documentation](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices): source/client coverage break, endpoint definitions, interval-start timestamps, v2decimal/large-price semantics and usage guidance. Mutable page; snapshot revision should be pinned in Phase One.
- [Grand Exchange mechanics](https://oldschool.runescape.wiki/w/Grand_Exchange) and [buying limits](https://oldschool.runescape.wiki/w/Buying_limit): market/account constraints; current rules are not reconstructed historical rules.
- [Jagex: Grand Exchange tax and item sink,2021-12-09](https://secure.runescape.com/m=news/grand-exchange-tax--item-sink?oldschool=1).
- [Jagex: Yama CAs and more,2025-05-29](https://secure.runescape.com/m=news/yama-cas--more?oldschool=1): 2% new-offer tax transition, legacy offers and exemptions.
- [Jagex: GE improvements beyond max cash,2026-09-30](https://secure.runescape.com/m=news/ge-improvements-beyond-max-cash?oldschool=1): guide-price/max-cash changes, cap/limit continuity.
- [Jagex terms](https://legal.jagex.com/docs/terms); [Weird Gloop licensing](https://meta.weirdgloop.org/w/Licensing). Source-specific permission is not inferred from public access.

## Gaussian and generative models

- Rasmussen and Williams,2006, [Gaussian Processes for Machine Learning](https://gaussianprocess.org/gpml/chapters/RW.pdf).
- Titsias,2009, [Variational Learning of Inducing Variables in Sparse GPs](https://proceedings.mlr.press/v5/titsias09a.html).
- Bishop,1994, [Mixture Density Networks](https://www.microsoft.com/en-us/research/publication/mixture-density-networks/).
- Salinas et al., [DeepAR](https://arxiv.org/abs/1704.04110): shared autoregressive probabilistic forecasting.
- Salinas et al.,2019, [High-dimensional multivariate forecasting with low-rank Gaussian copula processes](https://proceedings.neurips.cc/paper/2019/hash/0b105cf1504c4e241fcc6d519ea962fb-Abstract.html).
- Papamakarios et al., [Masked Autoregressive Flow](https://arxiv.org/abs/1705.07057).
- Durkan et al., [Neural Spline Flows](https://arxiv.org/abs/1906.04032).
- Lipman et al., [Flow Matching for Generative Modeling](https://arxiv.org/abs/2210.02747).
- [TSFlow—Flow Matching with Gaussian Process Priors for Probabilistic Time Series Forecasting](https://arxiv.org/abs/2410.03024), ICLR2025; [checked full-text v2](https://arxiv.org/html/2410.03024v2). Published benchmark evidence, not OSRS evidence.
- [ProFITi,AAAI2025 publisher record](https://doi.org/10.1609/aaai.v39i20.35494); [full-text v3](https://arxiv.org/html/2402.06293v3), especially Appendix G query-set marginal consistency limitation.

## Evaluation

- Gneiting and Raftery,2007, [Strictly Proper Scoring Rules, Prediction, and Estimation](https://doi.org/10.1198/016214506000001437).
- Bracher et al.,2021, [Evaluating epidemic forecasts in an interval format](https://doi.org/10.1371/journal.pcbi.1008618): interval scoring methodology, not market evidence.
- Scheuerer and Hamill,2015, [Variogram-based proper scoring rules](https://repository.library.noaa.gov/view/noaa/22327/).
- Politis and Romano,1994, [The Stationary Bootstrap](https://doi.org/10.1080/01621459.1994.10476870).
- Holm,1979, [A Simple Sequentially Rejective Multiple Test Procedure](https://www.jstor.org/stable/4615733); [accessible paper copy](https://www.ime.usp.br/~abe/lista/pdf4R8xPVzCnX.pdf).

## Software / hardware primary documentation

- [NVIDIA current CUDA GPUs](https://developer.nvidia.com/cuda/gpus), [legacy GPUs](https://developer.nvidia.com/cuda/gpus/legacy).
- [CUDA13.0.1 release notes](https://docs.nvidia.com/cuda/archive/13.0.1/cuda-toolkit-release-notes/index.html): Pascal support removal.
- [PyTorch2.7 release](https://pytorch.org/blog/pytorch-2-7/): historical Blackwell support milestone; [release matrix](https://github.com/pytorch/pytorch/blob/main/RELEASE.md) is mutable.
- [CUDA on WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html), [Microsoft WSL filesystems](https://learn.microsoft.com/en-us/windows/wsl/filesystems).
- [PyTorch AMP](https://docs.pytorch.org/docs/stable/amp.html), [distributed backends](https://docs.pytorch.org/docs/stable/distributed).
- [DuckDB Parquet](https://duckdb.org/docs/stable/data/parquet/overview), [Polars lazy evaluation](https://docs.pola.rs/user-guide/lazy/using/).
- [OpenRouter DeepSeek model/API metadata](https://openrouter.ai/deepseek/deepseek-v4.1-flash): actual model availability queried2026-11-01; requests routed todeepseek-v4.1-flash-1017. Model outputs are reviews, not primary factual sources.

## Local evidence inspected

VPS: /home/martin/homelab-overview.md (last verified 2026-11-01); /home/martin/src/osrs-market at 4f281ba during reconnaissance; README.md, ml/README.md, ml/pyproject.toml, docs/data-coverage.md, docs/data-sources.md, docs/deliberation-after-null.md and docs/prospective-pipeline-repair.md.

Archive: /home/martin/osrs-data/EXPORT_METADATA.json, assembled-v3/quality.json and panel manifests; sources/coverage-20261030T214757409995Z/coverage.json; sources/kaggle-5m/timestamp-validation.json; sources/verification-complete-20261030/metadata-id-audit.json (empty object). Observed footers and two-row samples recorded in the archive audit. Existing counts/hash assertions remain attributed reports; no full rehash/recount was performed. Original prices.parquet: ZSTD, 30,458,813 bytes, 2,502,566 rows; items.parquet: 163,811 bytes, 4,524 rows, directly confirmed.

Direct desktop commands: nvidia-smi queries for GPU name, driver and memory; wsl.exe --list --verbose. Historical network and disk-free facts come from the homelab overview, not live benchmarks. No private keys, secret environment contents, account tokens, private price payloads or raw datasets belong in this repository.
