# Phase One `E1` Baseline Suite: 3-Fold Chronological Development Results

Recorded 2026-11-01 on branch `research/osrs-phase-one-2026-11-01`. Full aggregate machine-readable outputs are in [`e1_baseline_results.json`](e1_baseline_results.json); frozen preregistration and budget records are in [`e1_baseline_protocol.json`](e1_baseline_protocol.json) and [`campaign_budget_reconciliation.json`](campaign_budget_reconciliation.json).

## 1. Provenance, Governance, and Resource Accounting

- **Source panel:** `hourly.parquet` (`1,127,760` rows, `74` items, SHA-256 `5a5bf0fa4d656b24b4df5883804fbb32068e5c0262924c3d51ccffe93af321a8`; manifest SHA-256 `6b4f501c4bf54c33df386caf5f4e46679d9273bddaf3cb6dc6ed967b32d9754f`).
- **Frozen protocol:** `e1_baseline_protocol.json` (SHA-256 `13a8ed14dc925f581ea8f89d937f7ff80cea360cd7ede16a874242b15645e04b`), committed at `45f0740403ad0d59f8295f33f84cf8fb70659e6b` prior to full market-panel evaluation.
- **Evaluated code commit:** `16f91c7afb3d4634ef7f19fc3b92fe764788bedb` (`git_dirty: false`), CPython `3.13.13`, isolated baseline environment frozen in `ml/requirements-baselines.lock` (SHA-256 `9500f5e75fa4794410e0cc91517d5873277dc2a92914fb072671848c0669f6ac`).
- **Sealed holdout:** Unix `1785024300` (`2026-07-26T00:05:00Z`) untouched (`holdout_touched: false`). All Fold 3 target horizons terminate strictly before `1785024000`.
- **Compute & fit budget:** Wall time `4,437.66s` (`73.96 min`) across `6` CPU worker threads (`7.40` CPU-hours of the `12.0` CPU-hour `E1` allowance; peak host RSS `< 5.5 GiB`, `0 B` swap). **Neural GPU fit slots consumed: `0`** (`5 / 72` pilot slots used previously; **`67 / 72` neural fit slots remain**). An initial non-streaming launch (`e1_baselines_3fold`) was cleanly stopped during Fold 1 for memory/SIMD streaming refactoring (`16f91c7`) and is retained in run provenance (`0` neural slots used); completed results come from `e1_baselines_3fold_r1`.
- **Archived run artifact SHA-256 hashes (stored outside Git on Desktop, local mirror, and VPS `/home/martin/osrs-data/phase-one-20261101/runs/`):**
  - `e1_baselines_3fold_r1/e1_summary.json`: `6382417dc9e7a38fa72dc49099ab6f998d8554a82cfb757837677b2bec43b65c`
  - `e1_baselines_3fold_r1/status.json`: `552b38f4b46adf2339db569674308348b62dd037f1187bfc515919c83eb26efa`
  - `e1_baselines_3fold_r1/environment.txt`: `aa926ca1e07520a180ceaa49fcf72cb39db81b6bdf487403bf4f2e9d01608232`
  - `e1_baselines_3fold_r1/fold1_loss_panels.npz`: `795f52a64668d1835947cebd25ed867dcdd831a2ffeed64136302ee7b7a5318f`
  - `e1_baselines_3fold_r1/fold2_loss_panels.npz`: `ba1684e9f5d2c9127ff5d4242092a54b293b4456651693207f1b3e904ce810f3`
  - `e1_baselines_3fold_r1/fold3_loss_panels.npz`: `5a76330854cf38e3faa61493f72da27ab25ca908bd1a461871524b7d6037a472`
  - `e1_baselines_3fold/status.json` *(aborted pre-streaming launch)*: `e21461bf3ce9d1c5e11b1d7aef55a5455af86784f9ca5b4d6fc4367939777e32`

## 2. Rolling-Origin Purged Folds and Target-Completeness Censoring

Each fold uses a 365-day rolling training window, a causal 25-hour boundary purge (`24h` horizon + `300s` assumed publication latency so training targets satisfy `t + 24h + 300s <= origin + 3900s`), causal per-(item, fold) `diff_scale` (`MAD * 1.4826`, fallback std, floor `1e-4`), and `M = 256` predictive trajectory paths per scored `(item, origin)`.

| Fold | Validation Window (UTC) | Candidate Pairs (`74 * T`) | Usable Origin Pairs | `complete_24h` Pairs | `complete_24h` Survival vs Candidates |
|---:|---|---:|---:|---:|---:|
| 1 | `2025-10-29` .. `2026-01-27` (`2,136h`) | 158,064 | 152,975 (`96.78%`) | 106,724 | **67.52%** |
| 2 | `2026-01-27` .. `2026-04-27` (`2,136h`) | 158,064 | 150,649 (`95.31%`) | 68,030 | **43.04%** |
| 3 | `2026-04-27` .. `2026-07-26` (`2,135h`) | 157,990 | 147,805 (`93.55%`) | 55,903 | **35.38%** |
| **Total** | **270 days (`6,407h`)** | **474,118** | **451,429 (`95.21%`)** | **230,657** | **48.65%** |

### Censoring Finding (`complete_24h` vs `endpoint_marginal`)
Single-hour usability declines modestly from Fold 1 (`96.78%`) to Fold 3 (`93.55%`), because the 95% item-coverage gate was frozen strictly on Year 1 (`2024-10-29` .. `2025-10-29`) without lookahead. However, requiring **24 consecutive usable future hours** compounds intermittent missingness and spread-inversion exclusions exponentially, dropping joint trajectory survival from `67.52%` in Fold 1 to `35.38%` in Fold 3.

Scoring all origins where individual marginal endpoints `t + h` (`h in {1, 4, 24}`) are usable (`endpoint_marginal`) yields systematically **higher (worse) scaled CRPS by `+0.043` to `+0.074` (`+3.5%` to `+4.9%`) across every single one of the 21 models** (`+0.0589` for `catboost_multiquantile_copula`, `+0.0576` for `ridge_lag_ewma_student_t`, `+0.0481` for `gaussian_rw_std`). Requiring complete 24-hour trajectory windows selects calmer, uninterrupted trading periods and understates marginal error around liquidity gaps and spread inversions. Model **rankings**, however, are invariant between `complete_24h`, `endpoint_marginal`, and non-overlapping `stride_24h`.

## 3. All 21 Baselines: 3-Fold Equal-Weighted Item-Macro Scoreboard

Primary metric: `primary_macro_scaled_crps_1_4_24`, the equal-weighted 3-fold mean of the 74-item macro-averaged `diff_scale`-normalized cumulative log-return CRPS averaged across `h in {1, 4, 24}` on `complete_24h`. Strongest-baseline eligibility requires nominal 90% central interval coverage within `[87.0%, 93.0%]` simultaneously at `h = 1`, `h = 4`, and `h = 24`.

| Rank | Model | 90% Gate | Primary CRPS (`1,4,24`) | Fold SD | `h=1` CRPS | `h=4` CRPS | `h=24` CRPS | Scaled WIS | Scaled Energy | Unbiased Variogram (`p=0.5`) | Shuffled Variogram | 90% Cov (`h=1 / 4 / 24`) | Endpoint Marginal CRPS | Pooled Unscaled `h=24` CRPS |
|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|---:|---:|
| **1** | **`catboost_multiquantile_copula`** | **PASS** | **1.1607** | 0.2605 | **0.6674** | **1.0377** | **1.7770** | **0.8225** | **8.093** | **99.24** | 137.81 | **89.4 / 89.9 / 89.6%** | **1.2196** | **0.01251** |
| **2** | **`ridge_lag_ewma_student_t`** | **PASS** | **1.1983** | 0.2633 | 0.6882 | 1.0647 | 1.8421 | 0.8634 | 8.285 | 100.47 | 163.81 | **90.4 / 91.8 / 90.8%** | 1.2559 | 0.01314 |
| **3** | **`empirical_block24_rw`** | **PASS** | **1.2492** | 0.2656 | 0.7170 | 1.1375 | 1.8932 | 0.9096 | 8.748 | 106.51 | 175.53 | **89.4 / 90.2 / 89.7%** | 1.3141 | 0.01347 |
| 4 | `ridge_lag_homoskedastic` | FAIL | 1.2661 | 0.2476 | 0.7154 | 1.1303 | 1.9526 | 0.9252 | 8.743 | 123.19 | 221.10 | 93.8 / 93.7 / 93.1% | 1.3234 | 0.01419 |
| 5 | `ets_ewma_student_t` | FAIL | 1.2787 | 0.2524 | 0.6903 | 1.1040 | 2.0418 | 0.9319 | 8.919 | 119.11 | 281.47 | 90.3 / 93.2 / 97.4% | 1.3281 | 0.01439 |
| 6 | `ma1_garch11_student_t` | FAIL | 1.3027 | 0.2392 | 0.6897 | 1.1124 | 2.1059 | 0.9519 | 9.104 | 125.92 | 290.78 | 89.7 / 93.0 / 97.0% | 1.3590 | 0.01489 |
| 7 | `arima_aicc_gaussian` | FAIL | 1.3072 | 0.2391 | 0.7249 | 1.1557 | 2.0411 | 0.9594 | 9.056 | 144.54 | 273.70 | 93.4 / 93.7 / 93.7% | 1.3602 | 0.01434 |
| 8 | `gaussian_rw_mad` | FAIL | 1.3091 | 0.2460 | 0.7203 | 1.1517 | 2.0552 | 0.9596 | 9.120 | 122.03 | 241.45 | 83.0 / 89.4 / 95.1% | 1.3683 | 0.01506 |
| 9 | `ets_ses_student_t` | FAIL | 1.3219 | 0.2249 | 0.6988 | 1.1314 | 2.1355 | 0.9820 | 9.268 | 137.88 | 331.77 | 91.0 / 93.2 / 97.2% | 1.3745 | 0.01530 |
| 10 | `ma1_garch11_gaussian` | FAIL | 1.3397 | 0.2307 | 0.6971 | 1.1300 | 2.1920 | 0.9827 | 9.363 | 142.14 | 329.11 | 91.9 / 94.2 / 97.6% | 1.3932 | 0.01548 |
| 11 | `ewma_iid_gaussian` | FAIL | 1.3548 | 0.2457 | 0.7104 | 1.1569 | 2.1970 | 0.9906 | 9.458 | 140.09 | 337.94 | 89.4 / 94.7 / 97.8% | 1.4076 | 0.01603 |
| 12 | `ewma_iid_student_t` | FAIL | 1.3758 | 0.2478 | 0.7063 | 1.1561 | 2.2649 | 1.0178 | 9.627 | 148.89 | 382.96 | 89.3 / 95.5 / 98.4% | 1.4283 | 0.01651 |
| 13 | `rolling_168h_gaussian` | FAIL | 1.3915 | 0.2572 | 0.7228 | 1.1857 | 2.2660 | 1.0257 | 9.718 | 153.65 | 375.72 | 90.3 / 95.0 / 98.3% | 1.4373 | 0.01649 |
| 14 | `ets_ses_gaussian` | FAIL | 1.4040 | 0.2157 | 0.7339 | 1.2031 | 2.2751 | 1.0456 | 9.833 | 170.35 | 393.05 | 93.4 / 94.5 / 97.4% | 1.4531 | 0.01617 |
| 15 | `ets_damped_gaussian` | FAIL | 1.4061 | 0.2153 | 0.7340 | 1.2044 | 2.2798 | 1.0475 | 9.849 | 171.08 | 395.20 | 93.4 / 94.4 / 97.4% | 1.4551 | 0.01620 |
| 16 | `empirical_iid_rw` | FAIL | 1.4146 | 0.2145 | 0.7163 | 1.1850 | 2.3425 | 1.0631 | 9.940 | 165.77 | 425.26 | 90.1 / 95.0 / 98.4% | 1.4661 | 0.01724 |
| 17 | `rolling_168h_drift_gaussian` | FAIL | 1.4383 | 0.2638 | 0.7252 | 1.1983 | 2.3913 | 1.0507 | 10.033 | 155.95 | 378.07 | 90.2 / 94.9 / 97.9% | 1.4893 | 0.01730 |
| 18 | `gaussian_rw_std` *(pilot control)* | FAIL | 1.4934 | 0.2059 | 0.7460 | 1.2583 | 2.4759 | 1.1230 | 10.504 | 198.90 | 484.62 | 92.9 / 95.8 / 98.5% | 1.5415 | 0.01808 |
| 19 | `no_change` *(point zero)* | FAIL | 1.6557 | 0.3473 | 0.9602 | 1.5083 | 2.4985 | 1.6557 | 11.658 | 483.05 | 483.05 | 0.2 / 0.2 / 0.2% | 1.7299 | 0.01773 |
| 20 | `seasonal_naive_168h` | PASS | 1.7932 | 0.3742 | 1.0247 | 1.5979 | 2.7570 | 1.2970 | 12.337 | 190.42 | 334.83 | 89.5 / 89.9 / 89.6% | 1.8455 | 0.01961 |
| 21 | `seasonal_naive_24h` | PASS | 1.7943 | 0.3588 | 1.0094 | 1.5611 | 2.8123 | 1.3008 | 11.950 | 172.34 | 299.94 | 88.8 / 89.3 / 88.7% | 1.8377 | 0.01988 |

### Calibration and Tail Diagnostics (Top Models + Anchors)

| Model | 50% Cov (`h=1/4/24`) | 80% Cov (`h=1/4/24`) | 95% Cov (`h=1/4/24`) | Brier `\|R_24\| >= 5%` *(base 0.0818)* | Brier `max_h R_h >= log(1.03)` *(base 0.2391)* | GP Rel CRPS `h=24` | `stride_24h` CRPS | 12-Item Subset CRPS |
|---|:---:|:---:|:---:|---:|---:|---:|---:|---:|
| `catboost_multiquantile_copula` | `49.4 / 50.5 / 50.6%` | `79.3 / 80.1 / 80.0%` | `94.3 / 94.7 / 94.5%` | **0.0615** | 0.1420 | **0.01336** | **1.1575** | **1.0908** |
| `ridge_lag_ewma_student_t` | `46.4 / 50.5 / 53.5%` | `78.3 / 81.6 / 81.2%` | `96.1 / 96.4 / 95.6%` | 0.0688 | **0.1348** | 0.01429 | 1.1962 | 1.1246 |
| `empirical_block24_rw` | `48.6 / 50.9 / 52.0%` | `79.1 / 80.7 / 80.6%` | `94.4 / 94.7 / 94.3%` | 0.0705 | 0.1533 | 0.01454 | 1.2452 | 1.1725 |
| `ets_ewma_student_t` | `52.0 / 61.0 / 77.2%` | `80.8 / 86.3 / 94.4%` | `95.0 / 96.3 / 98.6%` | 0.0970 | 0.1552 | 0.01553 | 1.2708 | 1.1946 |
| `ma1_garch11_student_t` | `50.0 / 59.1 / 74.7%` | `79.7 / 85.7 / 93.2%` | `94.8 / 96.4 / 98.5%` | 0.0987 | 0.1577 | 0.01592 | 1.2908 | 1.2072 |
| `gaussian_rw_std` | `65.7 / 75.8 / 86.7%` | `87.5 / 92.5 / 97.0%` | `95.6 / 97.4 / 99.2%` | 0.1609 | 0.2157 | 0.02007 | 1.4883 | 1.3866 |

## 4. Microstructure & Econometric Mechanisms Revealed by `E1`

1. **Multi-Hour Anchor Reversion Defeats Integrated `I(1)` Random Walks at `h=24`:**
   - One-step volatility/bounce models (`ma1_garch11_student_t` at `0.6897` and `ets_ewma_student_t` at `0.6903`) beat `empirical_block24_rw` (`0.7170`) at `h=1` and achieve near-exact `h=1` 90% coverage (`89.7%` and `90.3%`).
   - By `h=24`, however, every `I(1)` integrated random-walk, GARCH, and state-space ETS baseline inflates to **`97.0%–98.5%` 90% coverage** (`50%` coverage reaches `74.7%–86.7%`!), losing badly on `h=24` CRPS (`2.04–2.48`) and tail Brier (`0.097–0.161` vs base rate `0.0818`).
   - *Mechanism:* Grand Exchange item prices are tethered over 4h–72h windows by High Alchemy floors, NPC shop supply/buyback bounds, crafting conversion margins, and 4-hour GE buy-limit replenishment cycles. An `I(1)` state-space or GARCH model fit to 1-hour increments extrapolates permanent variance linearly ($h \sigma_{\xi}^2$), whereas true 24-hour cumulative log-return variance grows sub-linearly.
   - Direct multi-horizon models conditioning on 4h–72h EWMA anchor deviations, spread, volume imbalance, and hour-of-week (`catboost_multiquantile_copula`, `ridge_lag_ewma_student_t`) and contiguous 24-hour historical trajectory blocks (`empirical_block24_rw`) capture this sub-diffusive anchor reversion naturally, maintaining `89.6%–90.8%` nominal 90% coverage at `h=24`.

2. **Pilot Control Context (`gaussian_rw_std` Was Artificially Weak):**
   - The pilot's fixed training-std Gaussian random walk (`gaussian_rw_std`) ranks **18th of 21** (`1.4934`, pooled unscaled `h=24` CRPS `0.01808`, 90% `h=24` coverage `98.5%`) because non-robust sample standard deviation is inflated by rare outliers and extrapolated linearly across 24 steps.
   - Even the zero-parameter contiguous 24-hour empirical block bootstrap (`empirical_block24_rw`, `1.2492`, pooled unscaled `h=24` CRPS `0.01347`) improves over `gaussian_rw_std` by `16.3%` on 3-fold macro CRPS (`14.5%` on concatenated panel). Neural models cannot claim predictive value merely by beating `gaussian_rw_std`.

3. **Joint Trajectory Dependence Matters (Unbiased Variogram & Shuffle Control):**
   - Replacing the biased plug-in variogram estimator with the unbiased two-draw estimator (`variogram_score(..., estimator="unbiased")`) removes finite-sample dispersion bias (`99.24` unbiased vs `99.61` plug-in for `catboost_multiquantile_copula`; identical `483.05` for deterministic `no_change`).
   - Independently permuting marginal draws across horizons (`shuffled_unbiased`) degrades `catboost_multiquantile_copula` from `99.24` to `137.81` (`+38.57` penalty) and `ridge_lag_ewma_student_t` from `100.47` to `163.81` (`+63.33` penalty), confirming that the empirical Gaussian copula over standardized multi-horizon residuals captures genuine cross-horizon autocorrelation.

4. **GP-Notional vs Unit-Volume Liquidity Strata Inversion:**
   - Stratifying items by **manifest unit volume** produces the classic monotonicity: High (`1.0559`) < Medium (`1.1803`) < Low (`1.2494`) for `catboost_multiquantile_copula`.
   - Stratifying by **GP notional turnover** (`volume * exp(mid)`) inverts Low vs High/Medium for calibrated models: Low GP-notional (`1.0486`) < High (`1.2021`) < Medium (`1.2268`). Many low-GP-notional items that still pass the 95% active-hour filter are cheap shop/alch-anchored consumables whose discrete 1-GP tick bounce is highly mean-reverting relative to `diff_scale`, whereas high-GP-notional gear/raid items experience persistent demand shocks. Only `gaussian_rw_std` (`1.4236` High vs `1.5579` Low) obscured this structure due to unscaled outlier sensitivity in its variance estimate.

## 5. Dependence-Aware Paired Block-Bootstrap Inference (`B = 2,000`)

Paired cross-sectionally-aligned moving-block bootstrap (`block_length = 168h`, `2,000` replicates, `item_macro` aggregation over the `6,407` validation hours and `230,657` complete pairs; note that concatenating hours weights folds by observed `complete_24h` survival rather than equal `1/3` fold weights, giving `1.2478` vs `1.1607` for `catboost_multiquantile_copula` while preserving all pairwise rankings):

| Competitor (`A`) vs `catboost_multiquantile_copula` (`B`) | Concatenated Mean Diff (`A - B`) | 95% Block-Bootstrap CI | Relative Penalty vs Winner | Holm-Adjusted Two-Sided $p$ | Unbiased Variogram Diff (`A - B`) & 95% CI |
|---|---:|:---:|---:|---:|---|
| `ridge_lag_ewma_student_t` | `+0.0385` | `[+0.0345, +0.0416]` | `+3.08%` | `0.0100` | `+1.61` `[+0.64, +2.40]` ($p_{\text{raw}} = 0.0015$) |
| `empirical_block24_rw` | `+0.0894` | `[+0.0838, +0.0951]` | `+7.17%` | `0.0100` | `+8.06` `[+6.04, +10.47]` ($p_{\text{raw}} = 0.0005$) |
| `ridge_lag_homoskedastic` | `+0.1034` | `[+0.0977, +0.1102]` | `+8.29%` | `0.0100` | `+23.62` `[+21.49, +26.34]` ($p_{\text{raw}} = 0.0005$) |
| `ets_ewma_student_t` | `+0.1112` | `[+0.1038, +0.1195]` | `+8.91%` | `0.0100` | `+17.82` `[+16.18, +19.96]` ($p_{\text{raw}} = 0.0005$) |
| `ma1_garch11_student_t` | `+0.1348` | `[+0.1247, +0.1465]` | `+10.81%` | `0.0100` | `+24.55` `[+21.46, +28.40]` ($p_{\text{raw}} = 0.0005$) |
| `arima_aicc_gaussian` | `+0.1392` | `[+0.1303, +0.1486]` | `+11.16%` | `0.0100` | `+42.66` `[+38.74, +47.48]` ($p_{\text{raw}} = 0.0005$) |
| `gaussian_rw_mad` | `+0.1453` | `[+0.1376, +0.1545]` | `+11.64%` | `0.0100` | `+22.83` `[+21.10, +25.37]` ($p_{\text{raw}} = 0.0005$) |
| `gaussian_rw_std` *(pilot control)* | `+0.3167` | `[+0.2970, +0.3387]` | `+25.38%` (`-20.24%` gain) | `0.0100` | `+94.48` `[+87.55, +103.57]` ($p_{\text{raw}} = 0.0005$) |
| `no_change` | `+0.5252` | `[+0.4922, +0.5535]` | `+42.09%` | `0.0100` | `+410.87` `[+377.62, +438.90]` ($p_{\text{raw}} = 0.0005$) |

**Bootstrap Block-Length & Scheme Sensitivity (`catboost_multiquantile_copula` vs `gaussian_rw_std`, point diff `-0.3167`, relative gain `+20.24%`):**
- `72h` moving block: `[-0.3331, -0.3010]` (relative gain `[+18.68%, +22.00%]`, $p = 0.0005$)
- `168h` moving block (primary): `[-0.3399, -0.2983]` (relative gain `[+18.33%, +22.85%]`, $p = 0.0005$)
- `336h` moving block: `[-0.3504, -0.2931]` (relative gain `[+17.75%, +24.11%]`, $p = 0.0005$)
- `168h` Politis-Romano stationary bootstrap: `[-0.3506, -0.2916]` (relative gain `[+17.73%, +24.00%]`, $p = 0.0005$)

## 6. Promotion Bar for `E2–E4` Neural Fits and Scientific Caveats

`catboost_multiquantile_copula` is frozen as the **Strongest Calibrated `E1` Baseline** (`fallback_used: false`, 5 calibrated candidates eligible). Under [`campaign_budget_reconciliation.json`](campaign_budget_reconciliation.json) (`67 / 72` neural fit slots remaining), any neural trajectory family (`E2–E4`, evaluated with `CAMPAIGN_FEATURES` and `spline_variant="campaign_v2"`) must clear all three gates on the identical 3-fold `complete_24h` validation cohort before advancing to prospective testing:

1. **Calibration gate:** 3-fold mean nominal 90% central interval coverage within **`[87.0%, 93.0%]`** at `h = 1`, `h = 4`, and `h = 24` simultaneously.
2. **Marginal CRPS gate (`>= 2.0%` relative improvement or joint superiority):** 3-fold `primary_macro_scaled_crps_1_4_24 <= 1.1375` (vs `1.1607`), with paired 168h moving-block bootstrap Holm-adjusted $p < 0.05$ on aligned per-origin loss panels.
3. **Joint trajectory gate (`>= 5.0%` variogram improvement if marginal CRPS is tied within `1%`):** 3-fold `scaled_variogram_p05_unbiased <= 94.28` (vs `99.24`), without degrading marginal CRPS beyond `1.1723`.

**Non-negotiable interpretation limits:** All `E1` scores measure probabilistic distributional accuracy of volume-weighted 1-hour aggregate log mid-price returns under an assumed 300-second publication delay (`t_dec = origin + 3900s`, where bucket `t + 1` opened 5 minutes earlier). They do **not** represent executable Grand Exchange limit-order fills, continuous-time barrier survival, post-2% GE tax profitability, or confirmatory out-of-sample evidence.
