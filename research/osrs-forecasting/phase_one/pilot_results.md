# Measured pilot results

2026-11-01. Three bounded development pilots completed. This is implementation/resource evidence, not the registered confirmatory campaign.

| Model / GPU | End-to-end seconds | Peak allocated CUDA MiB | 24-step CRPS | Gaussian RW CRPS | Nominal90% coverage |
|---|---:|---:|---:|---:|---:|
| gaussian_diag / NVIDIA GeForce RTX 3070 Laptop GPU | 20.43 | 145.03 | 0.022284 | 0.021806 | 97.66% |
| gaussian_lowrank / NVIDIA GeForce RTX 5080 | 7.14 | 145.13 | 0.022072 | 0.021806 | 97.07% |
| spline_flow / NVIDIA GeForce RTX 5080 | 22.03 | 147.94 | 0.019356 | 0.021806 | 88.67% |

Scores are cumulative log-return scores on 512 seeded, origin-weighted complete-target windows. They are not item-macro primary results, GP profits, or independent observations. Tensor allocation excludes display use, CUDA context and allocator reservation. Different model heads and cold-start costs prevent treating these runtimes as a controlled GPU speed comparison.

The spline pilot has a lower point CRPS than the fixed-volatility Gaussian random walk on this sampled cohort. Both Gaussian pilots have slightly higher 24-step CRPS and broad intervals. This is a hypothesis for stronger validation, not a model winner: optimization is short, controls are limited, cohort selection and overlapping forecasts matter, and no corrected statistical comparison was performed.

The 3070 Gaussian and 5080 spline logged approximately 1.90 seconds of overlapping optimizer-loop interiors, assuming synchronized host clocks. This verifies independent concurrent execution; it does not measure simultaneous kernel occupancy or justify distributed training.

## Integrity and reproducibility

- All seven recorded artifact hashes per successful run were verified after transfer. Training and validation origin-index files are identical across all three fits. Installed environment freezes are identical across nodes. All three used code commit bca7dfb3abaf9bdef351b482c9c1c9dc4afafbfb and the same panel hash.
- The RTX3070 checkpoint loaded on desktop WSL CPU and produced finite samples with no optimizer steps. See checkpoint_portability.json.
- Source data, sealed holdout and existing collectors were not changed. Full artifacts are preserved on the VPS under /home/martin/osrs-data/phase-one-20261101/runs, on their originating GPU nodes and in the local tools directory. Only aggregate results and hashes are in Git.

## Failures and budget

Two initial attempts failed before optimizer initialization because the memory-fraction API rejected an unindexed CUDA device. The default was fixed, regression-tested, committed and deployed. Failed directories remain intact. A separate SSH launcher exited before creating a run directory and performed no fit.

Total neural fit attempts consumed: **five** (three completed, two failed). Maximum remaining slots under the approved 72-fit ceiling: **67**. These bounded subset pilots do not replace full-fold fits. The original six configurations ? three seeds ? four fits matrix would therefore exceed the remaining budget if executed in full: register an explicit reduced allocation or obtain a revised budget before launching that matrix. There is no automatic full-campaign queue.

Next scientific work is the stronger baseline suite and full chronological development evaluation, with paired per-origin losses, item-macro scoring, calibration/tail diagnostics and dependence-aware comparisons. Final prospective dates/model selection remain unregistered; do not open the old holdout or promote these pilot numbers to confirmatory evidence.

## Post-audit diagnostics and E1 baseline update

Independent code and artifact audit (`pilot_results.json`) identified two important pilot caveats preserved in the record above:

1. **Spline `h=1` under-coverage and tail NLL:** While `p03_spline_5080` achieved `88.67%` nominal 90% coverage at `h=24` (`88.48%` at `h=4`), its `h=1` 90% coverage was **`84.96%`** and its `normalized_nll_per_increment` was **`2.0271`** (worse than `gaussian_lowrank` at `1.8448` and `gaussian_diag` at `1.8540`). Root cause: `PiecewiseRationalQuadraticCouplingTransform(..., tails="linear", tail_bound=6.0)` acts as an identity pass-through outside `[-6, 6]` without a learned conditional location-scale pre-transform, leaving extreme standardized jumps `|z| > 6` under-dispersed under the standard normal base density. `SplineTrajectoryModel` (`spline_variant="campaign_v2"`) repairs this for future fits by prepending a conditional affine location-scale layer and cross-horizon permutations while preserving `spline_variant="pilot_v1"` for archived pilot checkpoints.
2. **Pilot `gaussian_rw` weakness and E1 completion:** The 21-model, 3-fold chronological `E1` baseline campaign has now completed (`0` neural slots consumed; `67 / 72` neural slots remain). On full 74-item macro-averaged 3-fold evaluation, `catboost_multiquantile_copula` (`1.1607`), `ridge_lag_ewma_student_t` (`1.1983`), and zero-parameter `empirical_block24_rw` (`1.2492`) substantially outperform the pilot's fixed-std `gaussian_rw` control (`1.4934`, 18th of 21). Read [`e1_baseline_results.md`](e1_baseline_results.md) and [`campaign_budget_reconciliation.json`](campaign_budget_reconciliation.json).
