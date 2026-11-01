# Phase One `E2–E3` Neural Probabilistic Campaign: 3-Fold Architecture & Feature-Ablation Results

Recorded 2026-11-01 on branch `research/osrs-phase-one-2026-11-01`. Full aggregate machine-readable outputs are in [`e2_gate_results.json`](e2_gate_results.json), [`e3_gate_results.json`](e3_gate_results.json), and [`e2_e3_campaign_results.json`](e2_e3_campaign_results.json); frozen protocols and budget records are in [`e2_e4_campaign_protocol.json`](e2_e4_campaign_protocol.json), [`e3_instantiated_protocol.json`](e3_instantiated_protocol.json), and [`campaign_budget_reconciliation.json`](campaign_budget_reconciliation.json).

---

## 1. Provenance, Source-Tree Synchronization, and Budget Accounting

- **Source panel:** `hourly.parquet` (`1,127,760` rows, `74` items, SHA-256 `5a5bf0fa4d656b24b4df5883804fbb32068e5c0262924c3d51ccffe93af321a8`; manifest SHA-256 `6b4f501c4bf54c33df386caf5f4e46679d9273bddaf3cb6dc6ed967b32d9754f`).
- **Frozen preregistered protocols:**
  - `e2_e4_campaign_protocol.json` (SHA-256 `5e1533a5ccfe2a5f79aa64bce6ed863c86811b4259b0f010ba7e74d8680ee39a`), untouched throughout `E2–E3`.
  - `e3_instantiated_protocol.json` (SHA-256 `323cf40663b0a3454df4c07c33960e64bde1338f54ab5485a5de9f157a663f14`), instantiating the preregistered `E3` selection rule with `recursive_student_t` prior to launching any `E3` fit.
- **Authoritative Git tree & multi-node provenance enforcement:**
  - `C:/Users/xmart/osrs-phase-one` served as the single authoritative Git development tree. Prior to each stage launch, commits were synced via Git into native Linux `ext4` execution checkouts on Desktop WSL2 (`/home/xmart/osrs-research/code`) and ThinkPad (`/home/martin/osrs-research/code`), verified byte-for-byte with `sha256sum` across all four nodes (`Windows`, `WSL2`, `VPS`, `ThinkPad`), and enforced at runtime by `run_node_queue(..., require_clean_git=True)`.
  - **`E2` (`54 / 54` fits):** executed at `code_commit = 52e18603e631bd4ba79ce1621f1145b076f8f912` (`git_dirty: false`).
  - **`E3` (`9 / 9` fits):** executed at `code_commit = 559cc9e9ed09d9502c73131640eba5a6eb282e34` (`git_dirty: false`), which added the exact 13-column closed-loop price-only recurrence (`if f_dim == 13:`) in `RecursiveStudentTModel._advance_feature_step` and unit tests (`61` passing `pytest` tests, `ruff` clean).
- **Sealed holdout:** Unix `1785024300` (`2026-07-26T00:05:00Z`) **strictly untouched (`holdout_touched: false`)**. All Fold 3 target trajectories terminate strictly before `1785024000`.
- **Archived full-run SHA-256 manifest (stored outside Git on Desktop WSL2, ThinkPad, and VPS `/home/martin/osrs-data/phase-one-20261101/runs/`):**
  - `e2_e3_runs.sha256` (`315` file digests = `63` completed run directories × `{status.json, metadata.json, fold_eval_summary.json, loss_panel.npz, checkpoint.pt}`): SHA-256 `5452b391892eaa4f6524addbd10cff59e6eecaa68d2b37fd6e3af261e225408a` (mirrored to `C:/Users/xmart/osrs-phase-one-tools/results/e2_e3_runs.sha256` alongside all four `*_queue_status.json` manifests).

### Neural Fit Budget & Hardware Telemetry (`68 / 72` Consumed, `4 / 72` `E4` Reserved)

| Stage / Queue | Node & GPU | Planned Cap | Consumed | Completed | Failed | Wall Time | Peak CUDA Alloc / Reserved | Peak Host RSS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Pilot stage (`p01`–`p03` + 2 pre-opt CUDA index errors) | RTX 3070 + RTX 5080 | 5 | 5 | 3 | 2 | — | `< 0.50 GiB` | `< 3.5 GiB` |
| `E1` 21-baseline 3-fold CPU campaign | Desktop WSL2 (`6` CPU threads) | 0 | 0 | — (`21` CPU) | 0 | `4,437.66s` (`7.40` CPU-h) | `0` | `< 5.5 GiB` |
| `rtx5080_e2` (`spline_flow`, `gaussian_lowrank`, `recursive_student_t` s11/s23) | Desktop WSL2 RTX 5080 (`16 GiB`) | 27 | 27 | 27 | 0 | `8,373.79s` (`2.33h`) | `924.9 / 1,132.0 MiB` | `4.58 GiB` |
| `rtx3070_e2` (`direct_marginal_student_t`, `student_t`, `gaussian_diag`, `recursive_student_t` s47) | ThinkPad RTX 3070 Laptop (`8 GiB`) | 27 | 27 | 27 | 0 | `6,031.48s` (`1.68h`) | `373.6 / 500.0 MiB` | `4.06 GiB` |
| `rtx5080_e3` (`pilot_v1_8col` + `campaign_11col`, seed `11`, Folds `1–3`) | Desktop WSL2 RTX 5080 (`16 GiB`) | 6 | 6 | 6 | 0 | `2,009.24s` (`0.56h`) | `367.5 / 508.0 MiB` | `3.49 GiB` |
| `rtx3070_e3` (`e3_price_only_13col`, seed `11`, Folds `1–3`) | ThinkPad RTX 3070 Laptop (`8 GiB`) | 3 | 3 | 3 | 0 | `2,734.61s` (`0.76h`) | `368.5 / 508.0 MiB` | `3.03 GiB` |
| **`E4` Prospective Reserve** *(future live 56-day window only; holdout closed)* | Reserved | `<= 4` | **0** | 0 | 0 | — | — | — |
| **Total Neural Fit Budget** | **Both GPUs** | **72** | **68** | **66** | **2** *(pilot only)* | — | **`<= 1.11 GiB`** | **`<= 4.58 GiB`** |

---

## 2. Unmodified Preregistered Promotion Gate & Executive Verdict

Every candidate in `E2` and `E3` was scored on the **exact identical 3-fold `complete_24h` validation cohort** (`230,657` complete 24-hour trajectories across `74` items and `6,407` validation hours; NaN mask equality verified via `np.array_equal` against `E1`'s `fold{1,2,3}_loss_panels.npz`) against the frozen `E1` winner **`catboost_multiquantile_copula`** (`primary_macro_scaled_crps_1_4_24 = 1.16069`, `scaled_variogram_p05_unbiased = 99.2443`, 90% coverage `89.4% / 89.9% / 89.6%`).

Under [`e2_e4_campaign_protocol.json`](e2_e4_campaign_protocol.json), promotion required:
1. **Calibration gate:** 3-fold mean nominal 90% central interval coverage within **`[87.0%, 93.0%]`** simultaneously at `h = 1`, `h = 4`, and `h = 24`.
2. **Superiority gate (either A or B):**
   - **Gate A (Marginal CRPS):** `>= 2.0%` relative reduction in 3-fold `primary_macro_scaled_crps_1_4_24` (**`<= 1.1375`** vs `1.1607`) with Holm-adjusted 168h moving-block bootstrap `p < 0.05`.
   - **Gate B (Joint Variogram):** `>= 5.0%` relative reduction in 3-fold `scaled_variogram_p05_unbiased` (**`<= 94.28`** vs `99.24`) with Holm-adjusted 168h moving-block bootstrap `p < 0.05` and **no marginal CRPS loss** (`<= 1.16069`).

### Honest Executive Synthesis (Both Negative & Positive Verdicts)

1. **Gate A (`>= 2.0%` Marginal CRPS Reduction, `<= 1.1375`) — Negative Result Across All `6 / 6` Architectures:**
   - **Zero** neural architectures came close to a `2.0%` marginal CRPS reduction over `catboost_multiquantile_copula`. The two strongest marginal neural architectures — `recursive_student_t` (`1.1507`, `-0.86%`, `p_holm = 0.0030`) and `direct_marginal_student_t` (`1.1508`, `-0.85%`, `p_holm = 0.0030`) — beat `catboost_multiquantile_copula` consistently on every fold and seed, but achieved **less than half** of the preregistered `-2.0%` marginal CRPS promotion bar.
2. **Overall Gate Failure for `5 / 6` `E2` Architectures:**
   - `direct_marginal_student_t` (`1.1508` CRPS, `136.30` variogram) failed Gate A (`-0.85%` vs `-2.0%`) and lost `+37.33%` on joint variogram because independent cumulative Student-$t$ marginals carry zero cross-horizon dependence.
   - `spline_flow` (`campaign_v3`, `1.1668` CRPS, `94.38` variogram) passed 90% calibration (`89.6% / 90.6% / 90.8%`) and achieved a `-4.90%` variogram reduction, missing Gate B's `-5.00%` (`94.28`) threshold by `0.10` variogram units while incurring a `+0.53%` marginal CRPS penalty (`1.1668 > 1.1607`).
   - All three open-loop 1-hour increment neural heads (`gaussian_lowrank` `1.3148`, `student_t` `1.3152`, `gaussian_diag` `1.3337`) failed calibration (`98.2%–98.4%` 90% coverage at `h=24`), marginal CRPS (`+13.3%` to `+14.9%`), and joint variogram (`+35.7%` to `+41.6%`).
3. **Genuine Unmodified Gate B Clearance by `recursive_student_t` (`1 / 6` Architectures):**
   - `recursive_student_t` (`9 / 9` fits completed across seeds `{11, 23, 47}` and Folds `{1, 2, 3}`, trained on `e2_matched` 19-column features with closed-loop step-by-step anchor-deviation and realized-volatility feedback) cleared the untouched Gate B criteria:
     - **90% Coverage:** `89.36% / 89.58% / 88.82%` at `h = 1 / 4 / 24` (**PASS**, inside `[87.0%, 93.0%]`).
     - **Joint Unbiased Variogram:** **`92.90`** vs `99.24` (**`-6.40%` reduction** vs `-5.00%` threshold `94.28`; concatenated 168h block-bootstrap diff `-6.22`, `95% CI [-6.72, -5.69]`, `p_holm = 0.0030` -> **PASS**).
     - **No Marginal CRPS Loss:** **`1.1507`** vs `1.1607` (**`-0.86%` reduction**; concatenated 168h block-bootstrap diff `-0.0096`, `95% CI [-0.0134, -0.0058]`, `p_holm = 0.0030` -> **PASS**).
4. **`E3` Decisive Feature-Ablation Finding (`e3_price_only` 13-Col Matches `e2_matched` 19-Col):**
   - Ablating all `6` order-flow, volume, buy-ratio, and bid-ask spread columns from `recursive_student_t` while retaining gap-bridged price returns, explicit 4h/24h/72h EWMA price-anchor deviations, 24h realized volatility, and calendar encodings (`e3_price_only`, `13` cols) yielded **`1.1503` primary CRPS (`-0.90%` vs `catboost`) and `93.00` unbiased variogram (`-6.29%` vs `catboost`)**, also clearing Gate B (`p_holm = 0.0015`) and showing **no statistically significant difference** from the full `19`-column `e2_matched` model on Seed `11` (`p_holm = 0.3258` on CRPS, `p_holm = 0.0790` on variogram). Conversely, dropping the explicit multi-horizon anchor deviations and 24h realized volatility (`campaign` `11`-col: `1.1580` CRPS; `pilot_v1` `8`-col: `1.1718` CRPS, Gate **FAIL**) degraded both CRPS and variogram significantly (`p_holm = 0.0015`).

---

## 3. `E2` 6-Architecture Scoreboard (`54` Fits = `6` Architectures × `3` Seeds × `3` Folds)

For each architecture, predictive samples from seeds `{11, 23, 47}` (`3 × 256 = 768` trajectories per `(item, origin)`) are pooled per fold under `evaluate_campaign_gates` (`e2_e4_campaign_protocol.json` §`seed_aggregation`), with individual seed 3-fold CRPS dispersion (`Seed SD`) reported alongside fold dispersion (`Fold SD`). Reference `E1` baseline `catboost_multiquantile_copula` is shown in the top row.

| Model / Candidate | Fits | 90% Gate | Primary CRPS (`1,4,24`) | vs `catboost` | Seed SD (`11,23,47`) | Fold SD (`F1..F3`) | `h=1 / 4 / 24` CRPS | Scaled WIS | Scaled Energy | Unbiased Variogram | vs `catboost` | Shuffled Variogram | 90% Cov (`h=1 / 4 / 24`) | Overall Gate Verdict |
|---|:---:|:---:|---:|---:|---:|---:|:---:|---:|---:|---:|---:|---:|:---:|:---:|
| *`catboost_multiquantile_copula` (`E1` ref)* | *CPU* | *PASS* | *`1.1607`* | *`0.00%`* | *—* | *`0.2605`* | *`0.6674 / 1.0377 / 1.7770`* | *`0.8225`* | *`8.093`* | *`99.24`* | *`0.00%`* | *`137.81`* | *`89.4 / 89.9 / 89.6%`* | *Reference* |
| **`recursive_student_t`** | `9/9` | **PASS** | **`1.1507`** | **`-0.86%`** | `0.00187` | `0.2593` | **`0.6571 / 1.0109 / 1.7840`** | **`0.8141`** | **`7.963`** | **`92.90`** | **`-6.40%`** | `134.35` | **`89.4 / 89.6 / 88.8%`** | **`PASS` (Gate B; Gate A FAIL)** |
| `direct_marginal_student_t` | `9/9` | **PASS** | `1.1508` | `-0.85%` | `0.00092` | `0.2604` | `0.6663 / 1.0238 / 1.7622` | `0.8146` | `8.275` | `136.30` | `+37.33%` | `136.30` | `89.2 / 89.4 / 89.2%` | **`FAIL`** (CRPS `< 2%`, Var `+37.3%`) |
| `spline_flow` (`campaign_v3`) | `9/9` | **PASS** | `1.1668` | `+0.53%` | `0.00288` | `0.2617` | `0.6669 / 1.0321 / 1.8015` | `0.8277` | `8.103` | `94.38` | `-4.90%` | `144.28` | `89.6 / 90.6 / 90.8%` | **`FAIL`** (Var `94.38 > 94.28`, CRPS `+0.53%`) |
| `gaussian_lowrank` | `9/9` | FAIL | `1.3148` | `+13.27%` | `0.00372` | `0.2471` | `0.6858 / 1.0956 / 2.1629` | `0.9589` | `9.138` | `134.67` | `+35.70%` | `314.05` | `89.9 / 94.8 / 98.2%` | **`FAIL`** (cov90, CRPS, Var) |
| `student_t` | `9/9` | FAIL | `1.3152` | `+13.32%` | `0.00315` | `0.2444` | `0.6701 / 1.0752 / 2.2004` | `0.9665` | `9.162` | `135.99` | `+37.03%` | `338.89` | `88.6 / 95.7 / 98.4%` | **`FAIL`** (cov90, CRPS, Var) |
| `gaussian_diag` | `9/9` | FAIL | `1.3337` | `+14.91%` | `0.00071` | `0.2501` | `0.6867 / 1.1100 / 2.2045` | `0.9768` | `9.300` | `140.54` | `+41.61%` | `339.11` | `89.8 / 95.6 / 98.4%` | **`FAIL`** (cov90, CRPS, Var) |

### Per-Seed, Per-Fold, Censoring, Calibration, and Liquidity-Stratum Diagnostics (`E2`)

| Candidate | Seed `11 / 23 / 47` 3-Fold CRPS | Fold `1 / 2 / 3` CRPS | 50% Cov (`1/4/24`) | 80% Cov (`1/4/24`) | 95% Cov (`1/4/24`) | Brier `\|R_24\|>=5%` | Brier `max R_h>=log(1.03)` | `endpoint_marginal` CRPS *(Δ vs complete)* | `stride_24h` CRPS | GP-Notional (`Low / Med / High`) | Manifest Vol (`Low / Med / High`) | Norm NLL / inc |
|---|---:|---:|:---:|:---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| `catboost_multiquantile_copula` | — | `1.5240 / 1.0185 / 0.9396` | `49.4/50.5/50.6%` | `79.3/80.1/80.0%` | `94.3/94.7/94.5%` | `0.0615` | `0.1420` | `1.2196` *(`+0.0589`)* | `1.1575` | `1.0486 / 1.2268 / 1.2021` | `1.2494 / 1.1803 / 1.0559` | — |
| **`recursive_student_t`** | `1.1530 / 1.1484 / 1.1506` | **`1.5144 / 1.0086 / 0.9290`** | `48.9/49.3/49.7%` | `79.2/79.6/79.0%` | `94.4/94.4/93.8%` | `0.0609` | **`0.1294`** | **`1.2112`** *(`+0.0605`)* | `1.1456` | **`1.0344 / 1.2150 / 1.1980`** | `1.2489 / 1.1684 / 1.0387` | **`1.4816`** |
| `direct_marginal_student_t` | `1.1509 / 1.1496 / 1.1518` | `1.5166 / 1.0045 / 0.9312` | `48.7/48.6/49.7%` | `78.8/79.2/79.3%` | `94.4/94.5/94.2%` | **`0.0608`** | `0.2496` | `1.2113` *(`+0.0605`)* | **`1.1446`** | `1.0378 / 1.2198 / 1.1902` | **`1.2409`** `/ 1.1712 / 1.0438` | `2.1573` *(marginal)* |
| `spline_flow` (`campaign_v3`) | `1.1700 / 1.1630 / 1.1675` | `1.5348 / 1.0182 / 0.9476` | `49.7/52.5/55.0%` | `79.7/81.7/82.6%` | `94.5/95.0/94.9%` | `0.0622` | `0.1347` | `1.2295` *(`+0.0627`)* | `1.1635` | `1.0510 / 1.2364 / 1.2085` | `1.2587 / 1.1809 / 1.0646` | `1.5058` |
| `gaussian_lowrank` | `1.3105 / 1.3142 / 1.3196` | `1.6618 / 1.1768 / 1.1057` | `55.8/68.1/82.6%` | `82.1/90.0/96.0%` | `93.8/96.9/99.0%` | `0.1078` | `0.1637` | `1.3644` *(`+0.0496`)* | `1.3152` | `1.2752 / 1.3430 / 1.3245` | `1.4047 / 1.3037 / 1.2395` | `1.6400` |
| `student_t` | `1.3142 / 1.3195 / 1.3120` | `1.6587 / 1.1778 / 1.1093` | `48.0/68.3/82.9%` | `78.0/90.9/96.1%` | `94.1/97.7/99.2%` | `0.1115` | `0.1534` | `1.3652` *(`+0.0500`)* | `1.3159` | `1.2629 / 1.3477 / 1.3330` | `1.4109 / 1.3052 / 1.2335` | `1.5746` |
| `gaussian_diag` | `1.3330 / 1.3335 / 1.3347` | `1.6855 / 1.1895 / 1.1262` | `55.8/70.5/83.7%` | `82.0/91.4/96.4%` | `93.7/97.4/99.1%` | `0.1132` | `0.1672` | `1.3827` *(`+0.0490`)* | `1.3327` | `1.3003 / 1.3577 / 1.3418` | `1.4233 / 1.3198 / 1.2616` | `1.6457` |

---

## 4. Architectural Mechanisms & Paired Block-Bootstrap Inference (`E2`)

1. **Why Open-Loop Increment Heads (`gaussian_diag`, `student_t`, `gaussian_lowrank`) Replicate `E1`'s `I(1)` Collapse:**
   - Emitting a 24-vector of future 1-hour increments conditional solely on origin-$t$ history forces cumulative variance to accumulate open-loop unless the model parameterizes dense negative cross-horizon autocovariances across all 24 lags simultaneously. Even rank-6 `gaussian_lowrank` (`98.2%` 90% coverage at `h=24`) fails to prevent random-walk variance inflation over 24 hours.
2. **Marginal vs Joint Decomposition (`direct_marginal_student_t` vs `spline_flow` vs `recursive_student_t`):**
   - **`direct_marginal_student_t`** predicts cumulative returns $R_{t,1..24}$ directly with horizon-specific Student-$t$ heads. It achieves the sharpest `h=24` marginal (`1.7622` vs `catboost` `1.7770` and `recursive_student_t` `1.7840`) and matches `recursive_student_t` on 3-fold primary CRPS (`1.1508` vs `1.1507`), confirming that the 168-hour GRU encoder extracts genuine but modest (`-0.85%`) conditional marginal signal beyond `catboost`'s tabular lags. Because its 24 marginal Student-$t$ distributions are sampled independently, however, its path-maximum Brier score (`max_h R_h >= log(1.03)`) blows up to **`0.2496`** (worse than the `0.2391` base rate!) and its unbiased variogram (`136.30`) equals its horizon-shuffled control (`136.30`).
   - **`spline_flow` (`campaign_v3`)** couples a rank-6 Gaussian base with 4 rational-quadratic spline coupling layers and reverse-horizon permutations, achieving calibrated coverage (`89.6% / 90.6% / 90.8%`) and strong path coherence (`94.38` variogram vs `144.28` shuffled; path-max Brier `0.1347` vs `catboost` `0.1420`), but loses `0.53%` on marginal CRPS relative to `catboost` and falls `0.10` variogram units shy of the `-5.0%` Gate B bar (`94.28`).
   - **`recursive_student_t`** rolls each sampled 1-hour increment forward inside `_advance_feature_step`, updating the item's 4h/24h/72h EWMA price-anchor deviations, 24h realized volatility, and cyclical hour/day-of-week encodings at every step $h = 1 \dots 24$. Whenever a simulated trajectory drifts away from its 4h–72h Grand Exchange anchor, the next step's Student-$t$ location and scale react state-dependently to pull the trajectory back. This closed-loop physical recurrence produces **both** the best per-increment normalized NLL (`1.4816`), the best path-max Brier score (`0.1294` vs `catboost` `0.1420`), the best scaled energy score (`7.963` vs `8.093`), and a **`-6.40%` unbiased variogram reduction (`92.90` vs `99.24`)** with zero marginal CRPS loss (`1.1507` vs `1.1607`).
3. **Target-Completeness Censoring & Liquidity-Stratum Invariance:**
   - Just as in `E1`, scoring all usable marginal endpoints (`endpoint_marginal`) increases scaled CRPS by `+0.0490` to `+0.0627` across all 6 neural architectures (`+0.0605` for `recursive_student_t` vs `+0.0589` for `catboost_multiquantile_copula`), confirming that calm-window selection bias in `complete_24h` affects neural and tree models identically without altering model rank order (`1.2112` vs `1.2196`).
   - Both `recursive_student_t` and `direct_marginal_student_t` preserve `E1`'s exact liquidity-stratum pattern: monotonic improvement with manifest unit volume (`1.2489` Low -> `1.1684` Med -> `1.0387` High) and inverted GP-notional ordering (`1.0344` Low < `1.1980` High < `1.2150` Med).

### Paired 168h Moving-Block Bootstrap vs `catboost_multiquantile_copula` (`B = 2,000`, `230,657` Pairs)

| Candidate (`A`) vs `catboost_multiquantile_copula` (`B`) | Concatenated CRPS Diff (`A - B`) & 95% CI | Holm $p$ (CRPS) | Concatenated Variogram Diff (`A - B`) & 95% CI | Holm $p$ (Variogram) |
|---|---|---|---|---|
| **`recursive_student_t`** | **`-0.0096` `[-0.0134, -0.0058]`** | **`0.0030`** | **`-6.22` `[-6.72, -5.69]`** | **`0.0030`** |
| `direct_marginal_student_t` | `-0.0095` `[-0.0116, -0.0074]` | `0.0030` | `+39.27` `[+36.54, +42.31]` | `0.0030` *(worse)* |
| `spline_flow` (`campaign_v3`) | `+0.0078` `[+0.0047, +0.0107]` | `0.0030` *(worse)* | `-4.89` `[-5.46, -4.35]` | `0.0030` |
| `gaussian_lowrank` | `+0.1472` `[+0.1400, +0.1551]` | `0.0030` *(worse)* | `+33.66` `[+31.82, +36.01]` | `0.0030` *(worse)* |
| `student_t` | `+0.1474` `[+0.1405, +0.1556]` | `0.0030` *(worse)* | `+34.55` `[+32.57, +37.03]` | `0.0030` *(worse)* |
| `gaussian_diag` | `+0.1669` `[+0.1600, +0.1744]` | `0.0030` *(worse)* | `+39.42` `[+37.49, +41.69]` | `0.0030` *(worse)* |

**Block-Length & Resampling Sensitivity (`recursive_student_t` vs `catboost_multiquantile_copula`, concatenated CRPS diff `-0.0096`):**
- `72h` moving block: `[-0.0133, -0.0062]` ($p_{\text{raw}} = 0.0005$)
- `168h` moving block (primary): `[-0.0134, -0.0058]` ($p_{\text{raw}} = 0.0005$, $p_{\text{Holm}} = 0.0030$)
- `336h` moving block: `[-0.0136, -0.0055]` ($p_{\text{raw}} = 0.0005$)
- `168h` Politis-Romano stationary bootstrap: `[-0.0135, -0.0059]` ($p_{\text{raw}} = 0.0005$)

---

## 5. `E3` Controlled Feature-Set Ablation (`9` Fits on `recursive_student_t`, Seed `11`, Folds `1–3`)

Following [`e3_instantiated_protocol.json`](e3_instantiated_protocol.json), `recursive_student_t` (the sole `E2` gate passer) was evaluated on Seed `11` across Folds `1–3` under three controlled feature representations and compared directly against its matched Seed `11` `E2` counterpart (`e2_matched`, `19` columns) as well as `catboost_multiquantile_copula`:

1. **`pilot_v1` (`8` cols):** raw 1h scaled return, `log_total_vol`, `spread_pct`, `imbalance`, `buy_ratio`, `usable_flag`, `hour_sin/cos` *(no gap-bridged return, no freshness/inversion flags, no 4h/24h/72h anchor deviations, no 24h realized volatility)*.
2. **`campaign` (`11` cols):** `pilot_v1` + `bridged_scaled_return`, `freshness_age_log1p`, `inverted_side` *(still no explicit multi-horizon anchor deviations, 24h realized volatility, or 4h volume/imbalance ratios)*.
3. **`e3_price_only` (`13` cols):** **drops all `6` volume/imbalance/buy-ratio/spread microstructure columns**, keeping only `ret_1h_scaled`, `bridged_scaled_return`, `usable_flag`, `freshness_age_log1p`, `inverted_side`, `hour_sin/cos`, `dow_sin/cos`, `anchor_dev_{4,24,72}h`, and `realized_vol_24h` (with exact closed-loop recurrence on all price/anchor/volatility/calendar states).
4. **`e2_matched` (`19` cols, from `E2` Seed `11`):** combines `e3_price_only` (`13` cols) + all `6` order-flow & spread microstructure columns (`log_total_vol`, `imbalance`, `buy_ratio`, `spread_pct`, `vol_4h_ratio`, `imbalance_4h`).

### `E3` 4-Tier Nested Feature Scoreboard (`recursive_student_t`, Seed `11`, Folds `1–3`)

| Feature Tier (Cols) | Primary CRPS (`1,4,24`) | Fold `1 / 2 / 3` CRPS | vs `catboost` (`1.1607`) | Unbiased Variogram | vs `catboost` (`99.24`) | 90% Cov (`h=1 / 4 / 24`) | `endpoint_marginal` CRPS | Paired Diff vs `19`-Col CRPS (`95% CI`, Holm $p$) | Paired Diff vs `19`-Col Variogram (`95% CI`, Holm $p$) | Gate Verdict vs `catboost` |
|---|---:|---:|---:|---:|---:|:---:|---:|---|---|:---:|
| **`e2_matched` (`19`-col, `E2` s11)** | `1.1530` | `1.5150 / 1.0130 / 0.9309` | `-0.66%` | **`92.81`** | **`-6.48%`** | `89.5 / 89.7 / 88.5%` | `1.2139` | *Reference (`0.0000`)* | *Reference (`0.00`)* | **`PASS` (Gate B)** |
| **`e3_price_only` (`13`-col, no vol/spread)** | **`1.1503`** | **`1.5159 / 1.0064 / 0.9284`** | **`-0.90%`** | `93.00` | `-6.29%` | `89.2 / 89.7 / 88.9%` | **`1.2116`** | **`-0.0016` `[-0.0044, +0.0018]` (`p=0.3258`, NULL)** | **`+0.27` `[-0.03, +0.58]` (`p=0.0790`, NULL)** | **`PASS` (Gate B)** |
| `campaign` (`11`-col, no explicit anchors) | `1.1580` | `1.5242 / 1.0149 / 0.9349` | `-0.23%` | `93.33` | `-5.96%` | `89.2 / 89.6 / 88.7%` | `1.2214` | `+0.0060` `[+0.0033, +0.0090]` (`p=0.0015`) | `+0.63` `[+0.28, +0.95]` (`p=0.0015`) | **`PASS` (Gate B)** |
| `pilot_v1` (`8`-col, unbridged) | `1.1718` | `1.5384 / 1.0297 / 0.9472` | `+0.95%` | `93.59` | `-5.70%` | `89.1 / 89.5 / 89.3%` | `1.2374` | `+0.0202` `[+0.0174, +0.0236]` (`p=0.0015`) | `+1.03` `[+0.65, +1.41]` (`p=0.0015`) | **`FAIL`** (CRPS loss `+0.95%`) |

### Econometric Takeaways from `E3`

1. **Gap-Bridged Returns + Explicit Multi-Horizon Price Anchors Drive Almost All Predictive Skill:**
   - Moving from `pilot_v1` (`8`-col, `1.1718`) -> `campaign` (`11`-col, `1.1580`) recovers **`-0.0138` CRPS** (`p_holm = 0.0015`) solely by adding gap-bridged scaled returns (`bridged_scaled_return`), staleness age (`freshness_age_log1p`), and spread-inversion indicators (`inverted_side`), rescuing `recursive_student_t` from failing Gate B's no-CRPS-loss requirement.
   - Adding explicit 4h/24h/72h EWMA price-anchor deviations, 24h realized volatility, and day-of-week (`e3_price_only`, `13`-col, `1.1503`) contributes a further **`-0.0077` CRPS** and **`-0.33` variogram** improvement over `campaign` (`11`-col), demonstrating that a 168-hour GRU encoder still benefits substantially from explicit causal multi-scale anchor-deviation state variables that are rolled forward in closed loop during rollout.
2. **Order-Flow Volume & Bid-Ask Spread Microstructure Carry Negligible Incremental Horizon-`1..24` Signal:**
   - Comparing `e3_price_only` (`13` cols, **zero** volume or spread inputs) against `e2_matched` (`19` cols, adding `log_total_vol`, `imbalance`, `buy_ratio`, `spread_pct`, `vol_4h_ratio`, `imbalance_4h`) shows **statistical equivalence** on both marginal CRPS (`concatenated diff = -0.0016`, `p_holm = 0.3258`; equal-weighted 3-fold CRPS slightly favors `13`-col `1.1503` over `19`-col `1.1530`) and unbiased variogram (`+0.27`, `p_holm = 0.0790`).
   - Because order-flow imbalance and quoted spread are fast-decaying `h=1` microstructure states that cannot be rolled forward in closed loop over `h = 2..24` without an auxiliary volume/spread generator, omitting them yields a cleaner, lower-dimensional state-space recurrence without losing accuracy or calibration.

---

## 6. `E4` Prospective Reserve Status & Scientific Caveats

- **Sealed Historical Holdout (`>= 1785024300`) Remains Closed:** In accordance with project governance and [`e2_e4_campaign_protocol.json`](e2_e4_campaign_protocol.json), **zero fits or reads** touched Unix `>= 1785024300`, and **`0 / 4` `E4` neural fit slots were spent**.
- **Remaining Reserve (`4 / 72` Neural Fit Slots):** Because `recursive_student_t` (both `19`-col `e2_matched` in `E2` and `13`-col `e3_price_only` in `E3`) cleared Gate B (`joint variogram <= 94.28` with calibrated `[87%, 93%]` 90% coverage and slight `-0.86%` to `-0.90%` marginal CRPS improvement over `catboost_multiquantile_copula`, while **failing** Gate A's `-2.0%` marginal CRPS bar), the `4` remaining neural fit slots stay preserved in reserve. Executing `E4` requires freezing a separate prospective preregistration manifest (`<= 4` refits) for a **future live 56-day prospective window starting `>= 7` days after final freeze** — never on the historical holdout `1785024300`.
- **Binding Caveats:** All scores measure aggregate 1-hour Grand Exchange volume-weighted buckets (`origin + 3,900s` decision convention, where the `h=1` bucket began `5` minutes prior to decision time), not executable limit-order fills, continuous-time barrier crossings, or net-of-tax trading PnL.
