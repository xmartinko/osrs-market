# Handoff / parallel-agent entry point

The user opened a Gemini 4 Argon sidebar agent while Codex was completing the pilot milestone, then transferred project ownership after Codex stopped at commit `310b96f`. All three GPU pilots, the full 21-model 3-fold chronological `E1` CPU baseline suite, the 54-fit `E2` 6-architecture GPU campaign (`54 / 54` completed, `0` failures), and the 9-fit `E3` feature-ablation GPU campaign (`9 / 9` completed, `0` failures) have now completed; there are **no active jobs** on any node.

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

Both GPU nodes have isolated Python 3.13.13 / `torch 2.8.0+cu128` environments (`ml/requirements-probabilistic.lock`), and Desktop WSL additionally hosts `/home/xmart/osrs-research/venv-baselines` (`ml/requirements-baselines.lock`) for CPU statistical/tabular baselines. There are **61 passing tests** across `ml/tests/test_probabilistic_{data,evaluation,models,train,baselines,campaign}.py` (`ruff` clean).

Completed milestones:
1. **GPU Pilots (`bca7dfb`):** `p01_diag_3070_r1`, `p02_lowrank_5080_r1`, and `p03_spline_5080` completed (`256` steps, `512` sampled origins), with two earlier pre-optimization CUDA device-index failures retained (`5 / 72` neural fit slots consumed). Read `pilot_protocol.json`, `pilot_amendment_01.json`, `pilot_budget_review.json`, and `pilot_results.md/json`.
2. **Audit Repairs & `E1` 21-Baseline 3-Fold Campaign (`16f91c7`):**
   - Repaired plug-in variogram dispersion bias (`estimator="unbiased"`), closed-form Student-$t$ CRPS, incomplete-panel block bootstrap + Holm adjustment, campaign feature handling (`bridged_scaled_return`, `freshness_age_log1p`, `inverted_side`, signed crossed spreads), and `SplineTrajectoryModel` tail affine scaling + cross-horizon permutations (`spline_variant="campaign_v2"`, keeping `"pilot_v1"` compatible).
   - Completed `e1_baselines_3fold_r1` (`7.40 / 12.0` CPU-hours, **`0` neural slots consumed**, `holdout_touched: false`) across all 74 items and all 3 purged 90-day folds (`230,657` `complete_24h` pairs; `451,429` usable origin pairs). An earlier non-streaming run (`e1_baselines_3fold`) stopped cleanly during Fold 1 for memory/SIMD streaming refactoring (`0` neural slots) and is retained in run provenance.
   - **Strongest calibrated baseline:** `catboost_multiquantile_copula` (`primary_macro_scaled_crps_1_4_24 = 1.1607`, unbiased scaled variogram `99.24`, 90% coverage `89.4% / 89.9% / 89.6%` at `h = 1 / 4 / 24`), followed by `ridge_lag_ewma_student_t` (`1.1983`) and zero-parameter `empirical_block24_rw` (`1.2492`). All beat `gaussian_rw_std` (`1.4934`) and `I(1)` ETS/GARCH random walks (`1.2787–1.4061`, which inflate to `97.0%–98.5%` 90% coverage at `h=24` due to 4h–72h Grand Exchange price anchor reversion) with Holm-adjusted 168h block-bootstrap $p = 0.0100$.
   - **Censoring finding:** `complete_24h` validation survival falls from `67.52%` (Fold 1) to `43.04%` (Fold 2) to `35.38%` (Fold 3), and `endpoint_marginal` scaled CRPS is `+0.043` to `+0.074` higher across all 21 models, quantifying calm-window selection bias while preserving model rank order. Read `campaign_budget_reconciliation.json`, `e1_baseline_protocol.json`, and `e1_baseline_results.md/json`.
3. **`E2` 54-Fit Architecture Campaign & `E3` 9-Fit Feature-Ablation Campaign (`52e1860`, `559cc9e`):**
   - Enforced clean-Git tree provenance (`_code_tree_provenance`, `require_clean_git=True`) and verified byte-for-byte `sha256sum` parity across Windows (`C:/Users/xmart/osrs-phase-one`), Desktop WSL2 (`/home/xmart/osrs-research/code`), VPS (`/home/martin/osrs-phase-one-worktree`), and ThinkPad (`/home/martin/osrs-research/code`) prior to each dispatch. Archived all `63` completed run directories (`315` file digests in `e2_e3_runs.sha256` = `5452b391...`) on VPS `/home/martin/osrs-data/phase-one-20261101/runs/`.
   - **`E2` Verdict (`54 / 54` completed, `0` failures):** Under the untouched `e2_e4_campaign_protocol.json` thresholds against `catboost_multiquantile_copula` (`1.1607` CRPS, `99.24` variogram):
     - **Gate A (`<= 1.1375` marginal CRPS, `-2.0%`) failed across all `6 / 6` architectures** (`recursive_student_t` `-0.86%` at `1.1507` and `direct_marginal_student_t` `-0.85%` at `1.1508` reached less than half of `-2.0%`).
     - **`5 / 6` architectures failed overall:** `direct_marginal_student_t` (`136.30` variogram, `+37.33%`), `spline_flow` (`campaign_v3`: `1.1668` CRPS `+0.53%`, `94.38` variogram `-4.90%`, `0.10` shy of `94.28`), and open-loop `gaussian_lowrank` (`1.3148`), `student_t` (`1.3152`), and `gaussian_diag` (`1.3337`) (all three inflating to `98.2%–98.4%` 90% coverage at `h=24`).
     - **`recursive_student_t` (`1 / 6`) cleared Gate B (`<= 94.28` unbiased variogram + no marginal CRPS loss + `[87%, 93%]` 90% coverage):** `92.90` unbiased variogram (`-6.40%`, `p_holm = 0.0030`), `1.1507` CRPS (`-0.86%`, `p_holm = 0.0030`), `89.4% / 89.6% / 88.8%` 90% coverage (`Seed SD = 0.00187`).
   - **`E3` Verdict (`9 / 9` completed, `0` failures, `recursive_student_t` seed `11`):** `e3_price_only` (`13` cols, dropping all `6` volume/imbalance/buy-ratio/spread columns while keeping gap-bridged returns + 4h/24h/72h EWMA price-anchor deviations + 24h realized vol + calendar) achieved `1.1503` CRPS (`-0.90%`) and `93.00` variogram (`-6.29%`, Gate B `PASS`), statistically indistinguishable from `19`-col `e2_matched` (`1.1530` / `92.81`; `p_holm = 0.3258` CRPS, `p_holm = 0.0790` variogram). Dropping explicit multi-horizon anchor deviations (`campaign` `11`-col: `1.1580` / `93.33`; `pilot_v1` `8`-col: `1.1718` `+0.95%` CRPS loss, Gate `FAIL`) degraded performance significantly (`p_holm = 0.0015`). Read `e2_e3_campaign_results.md`, `E2_STATUS.md`, `e2_gate_results.json`, `e3_gate_results.json`, and `e2_e3_campaign_results.json`.

## Remaining reserve (`E4` future live prospective window only)

**`68 / 72` neural fit slots have been consumed; `4 / 72` slots remain strictly reserved for `E4`.** Keep the sealed historical holdout (`1785024300`) closed (`holdout_touched: false`). Do not launch `E4` fits without explicit user authorization and a frozen prospective manifest targeting a future live 56-day window starting `>= 7` days after final freeze.

Save code, tests, manifests and aggregate findings to devstash with follow-up commits. Preserve the live infrastructure and existing branch histories; never force-push.
