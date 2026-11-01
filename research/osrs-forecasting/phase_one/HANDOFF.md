# Handoff / parallel-agent entry point

The user opened a Gemini 4 Argon sidebar agent while Codex was completing the pilot milestone, then transferred project ownership after Codex stopped at commit `310b96f`. All three GPU pilots and the full 21-model, 3-fold chronological `E1` baseline suite have now completed; there are **no active jobs** on any node.

## Authority and scope

Phase One and concurrent independent use of RTX 3070 / RTX 5080 are approved. Keep the original holdout starting at Unix 1785024300 sealed. No trading, game automation, raw-archive rewriting, new acquisition, production deployment, driver/BIOS/network changes or unrelated-service disruption is authorized. Never display secrets/private keys. Follow `/home/martin/homelab-overview.md` and the user's infrastructure instructions.

The proposal's methodological requirements remain binding. Pilot execution and `E1` development baseline evaluation are recorded here; neither establishes executable trading profitability or confirmatory prospective success. Final prospective test dates and final model selection are not registered yet. Current-day collectors/forward ledgers are unrelated services and were left alone.

## Canonical locations

- Devstash repository: `https://git.devstash.tech/martinko/osrs-market`
- Active branch: `research/osrs-phase-one-2026-11-01`. Read its latest commit; do not assume the original Phase Zero branch is current.
- VPS working tree: `/home/martin/osrs-phase-one-worktree`.
- Windows development copy: `C:/Users/xmart/osrs-phase-one`. Check `git status` before edits.
- Desktop: WSL Ubuntu-24.04, `/home/xmart/osrs-research/{code,venv,venv-baselines,data,runs}`.
- ThinkPad: `/home/martin/osrs-research/{code,venv,data,runs}`; reached via existing root SSH from VPS. The shell is fish: pipe scripts rather than relying on scp protocol behavior.
- Central full artifacts: `/home/martin/osrs-data/phase-one-20261101/{hourly.parquet,hourly.manifest.json,runs/}`.
- Local artifact mirror: `C:/Users/xmart/osrs-phase-one-tools/results`. Keep panels/checkpoints/per-origin rows outside Git.

## Actual state

The frozen 95% coverage gate admitted 74 items. The panel has 1,127,760 item-hours and SHA-256 `5a5bf0fa4d656b24b4df5883804fbb32068e5c0262924c3d51ccffe93af321a8`. Eligibility uses only the initial training year; derived development dates stay strictly before the sealed holdout (`1785024300`). See `data_manifest.json` and `data_gate.md` for exact semantics, caveats and source checks.

Both GPU nodes have isolated Python 3.13.13 / `torch 2.8.0+cu128` environments (`ml/requirements-probabilistic.lock`), and Desktop WSL additionally hosts `/home/xmart/osrs-research/venv-baselines` (`ml/requirements-baselines.lock`) for CPU statistical/tabular baselines. There are **52 passing tests** across `ml/tests/test_probabilistic_{data,evaluation,models,train,baselines}.py` (`ruff` clean).

Completed milestones:
1. **GPU Pilots (`bca7dfb`):** `p01_diag_3070_r1`, `p02_lowrank_5080_r1`, and `p03_spline_5080` completed (`256` steps, `512` sampled origins), with two earlier pre-optimization CUDA device-index failures retained (`5 / 72` neural fit slots consumed). Read `pilot_protocol.json`, `pilot_amendment_01.json`, `pilot_budget_review.json`, and `pilot_results.md/json`.
2. **Audit Repairs & `E1` 21-Baseline 3-Fold Campaign (`16f91c7`):**
   - Repaired plug-in variogram dispersion bias (`estimator="unbiased"`), closed-form Student-$t$ CRPS, incomplete-panel block bootstrap + Holm adjustment, campaign feature handling (`bridged_scaled_return`, `freshness_age_log1p`, `inverted_side`, signed crossed spreads), and `SplineTrajectoryModel` tail affine scaling + cross-horizon permutations (`spline_variant="campaign_v2"`, keeping `"pilot_v1"` compatible).
   - Completed `e1_baselines_3fold_r1` (`7.40 / 12.0` CPU-hours, **`0` neural slots consumed**, `holdout_touched: false`) across all 74 items and all 3 purged 90-day folds (`230,657` `complete_24h` pairs; `451,429` usable origin pairs). An earlier non-streaming run (`e1_baselines_3fold`) stopped cleanly during Fold 1 for memory/SIMD streaming refactoring (`0` neural slots) and is retained in run provenance.
   - **Strongest calibrated baseline:** `catboost_multiquantile_copula` (`primary_macro_scaled_crps_1_4_24 = 1.1607`, unbiased scaled variogram `99.24`, 90% coverage `89.4% / 89.9% / 89.6%` at `h = 1 / 4 / 24`), followed by `ridge_lag_ewma_student_t` (`1.1983`) and zero-parameter `empirical_block24_rw` (`1.2492`). All beat `gaussian_rw_std` (`1.4934`) and `I(1)` ETS/GARCH random walks (`1.2787–1.4061`, which inflate to `97.0%–98.5%` 90% coverage at `h=24` due to 4h–72h Grand Exchange price anchor reversion) with Holm-adjusted 168h block-bootstrap $p = 0.0100$.
   - **Censoring finding:** `complete_24h` validation survival falls from `67.52%` (Fold 1) to `43.04%` (Fold 2) to `35.38%` (Fold 3), and `endpoint_marginal` scaled CRPS is `+0.043` to `+0.074` higher across all 21 models, quantifying calm-window selection bias while preserving model rank order. Read `campaign_budget_reconciliation.json`, `e1_baseline_protocol.json`, and `e1_baseline_results.md/json`.

## Next bounded work package (`E2–E4` neural campaign, awaiting explicit launch approval)

**67 of 72 neural fit slots remain.** Do not launch GPU fits without explicit user confirmation, and strictly follow the validation-gated allocation in `campaign_budget_reconciliation.json` (`<= 54` `E2` architecture fits + `<= 9` `E3` feature ablations + `<= 4` `E4` prospective fits = `<= 67` slots).

Any neural candidate evaluated in `E2–E4` must clear the preregistered gate against `catboost_multiquantile_copula` on the identical 3-fold `complete_24h` validation cohort: nominal 90% coverage within `[87%, 93%]` at `h in {1, 4, 24}`, plus either `>= 2.0%` primary scaled CRPS reduction (`<= 1.1375`) with Holm-adjusted 168h block-bootstrap $p < 0.05` or `>= 5.0%` unbiased variogram reduction (`<= 94.28`) without marginal CRPS loss. Keep the sealed holdout (`1785024300`) closed.

Save code, tests, manifests and aggregate findings to devstash with follow-up commits. Preserve the live infrastructure and existing branch histories; never force-push.
