# Phase One `E2–E4` GPU Campaign Final Status (`E2_STATUS.md`)

**Last updated:** `2026-11-01T07:06:00-08:00`  
**Campaign state:** **`E2` (`54 / 54`) AND `E3` (`9 / 9`) COMPLETED (`0` failures; `0` active GPU jobs)**  
**Branch:** `research/osrs-phase-one-2026-11-01`  
**Evaluated commits:** `52e18603e631bd4ba79ce1621f1145b076f8f912` (`E2`), `559cc9e9ed09d9502c73131640eba5a6eb282e34` (`E3`), `git_dirty: false`  
**Authoritative Git tree:** `C:/Users/xmart/osrs-phase-one` -> synced & SHA-256 verified across WSL (`/home/xmart/osrs-research/code`), VPS (`/home/martin/osrs-phase-one-worktree`), and ThinkPad (`/home/martin/osrs-research/code`)  
**Central VPS full-run archive:** `/home/martin/osrs-data/phase-one-20261101/runs/` (`63` completed run dirs, `315` file digests in `e2_e3_runs.sha256` = `5452b391892eaa4f6524addbd10cff59e6eecaa68d2b37fd6e3af261e225408a`)  
**Sealed holdout (`>= 1785024300`):** **UNTOUCHED (`holdout_touched: false`)**

---

## 1. Neural Fit Budget Accounting (`68 / 72` Consumed, `4 / 72` `E4` Reserved)

| Stage | Budget Allocation | Consumed | Completed | Failed | Remaining |
|---|---:|---:|---:|---:|---:|
| Pilot stage (`p01`–`p03` + 2 pre-opt CUDA index errors) | 5 | 5 | 3 | 2 | 0 |
| `E1` 21-baseline 3-fold CPU campaign (`7.40 / 12.0` CPU-h) | 0 | 0 | — (`21` CPU models) | 0 | 0 |
| **`E2` 6-architecture × 3-seed × 3-fold GPU campaign** | `<= 54` | **54** | **54** | **0** | 0 |
| **`E3` controlled feature ablations (3 ablations × 3 folds, s11)** | `<= 9` | **9** | **9** | **0** | 0 |
| **`E4` prospective 56-day refits (future live window only)** | `<= 4` | **0** *(reserved; holdout sealed)* | 0 | 0 | **4** |
| **Total Campaign** | **72** | **68** | **66** | **2** *(pilot only)* | **4** |

---

## 2. Executive Gate Summary (Unmodified Thresholds vs `catboost_multiquantile_copula`)

Every candidate was evaluated on the **identical 3-fold `complete_24h` cohort** (`230,657` complete 24h trajectories across `74` items) under the untouched preregistered gate in [`e2_e4_campaign_protocol.json`](e2_e4_campaign_protocol.json) (SHA-256 `5e1533a5ccfe2a5f79aa64bce6ed863c86811b4259b0f010ba7e74d8680ee39a`):
- **Calibration:** 3-fold mean 90% central interval coverage in **`[87.0%, 93.0%]`** at `h = 1, 4, 24`.
- **Gate A (Marginal CRPS):** `>= 2.0%` reduction in primary macro scaled CRPS (**`<= 1.1375`** vs `catboost` `1.1607`, Holm 168h block-bootstrap `p < 0.05`).
- **Gate B (Joint Variogram):** `>= 5.0%` reduction in unbiased scaled variogram (**`<= 94.28`** vs `catboost` `99.24`, Holm 168h block-bootstrap `p < 0.05`, and **no marginal CRPS loss** `<= 1.1607`).

### Key Verdicts for Martin
1. **Gate A (`<= 1.1375` Marginal CRPS) — Negative Result (`0 / 6` passed):** No neural model came close to the `-2.0%` marginal CRPS bar. Both `recursive_student_t` (`1.1507`, `-0.86%`) and `direct_marginal_student_t` (`1.1508`, `-0.85%`) beat `catboost_multiquantile_copula` (`1.1607`) on all 3 folds and all 3 seeds (`p_holm = 0.0030`), but achieved less than half of the `-2.0%` marginal CRPS reduction threshold.
2. **Overall `E2` Failures (`5 / 6` failed):** `direct_marginal_student_t` (`136.30` variogram, `+37.33%`), `spline_flow` (`campaign_v3`: `1.1668` CRPS `+0.53%`, `94.38` variogram `-4.90%`, `0.10` shy of `94.28`), and all three open-loop increment models (`gaussian_lowrank`, `student_t`, `gaussian_diag`, which inflated to `98.2%–98.4%` 90% coverage at `h=24`) failed the preregistered gate.
3. **Genuine Unmodified Gate B Pass by `recursive_student_t` (`1 / 6` passed):** Closed-loop step-by-step anchor-deviation and realized-volatility feedback in `recursive_student_t` cleared Gate B cleanly at **`92.90` unbiased variogram (`-6.40%` vs `catboost` `99.24`, threshold `<= 94.28`, `p_holm = 0.0030`)**, **`1.1507` primary CRPS (`-0.86%`, no marginal loss, `p_holm = 0.0030`)**, and **`89.4% / 89.6% / 88.8%` 90% coverage** across all 3 seeds (`Seed SD = 0.00187`).
4. **`E3` Feature Ablation Discovery (`13`-col Price-Only Matches `19`-col Full):** Dropping all `6` volume/imbalance/buy-ratio/spread microstructure columns (`e3_price_only`, `13` cols) achieved **`1.1503` CRPS (`-0.90%`) and `93.00` variogram (`-6.29%`)**, statistically indistinguishable from `19`-col `e2_matched` (`p_holm = 0.3258` CRPS, `p_holm = 0.0790` variogram), whereas dropping explicit 4h/24h/72h price-anchor deviations (`campaign` `11`-col: `1.1580`; `pilot_v1` `8`-col: `1.1718`, Gate **FAIL**) degraded performance significantly (`p_holm = 0.0015`).

---

## 3. Complete `E2` Gate Verdicts (`54 / 54` Fits Completed)

| Candidate Architecture | Fits Done | 90% Cov (`h=1 / 4 / 24`) | Primary Macro Scaled CRPS | vs `catboost` (`1.1607`) | Unbiased Variogram | vs `catboost` (`99.24`) | Holm `p` (CRPS / Var) | Gate Verdict |
|---|:---:|:---:|---:|---:|---:|---:|:---:|:---:|
| **`recursive_student_t`** | `9 / 9` | `89.4% / 89.6% / 88.8%` | **`1.1507`** | **`-0.86%`** | **`92.90`** | **`-6.40%`** | `0.0030 / 0.0030` | **`PASS` (Gate B Joint Var; Gate A FAIL)** |
| `direct_marginal_student_t` | `9 / 9` | `89.2% / 89.4% / 89.2%` | `1.1508` | `-0.85%` | `136.30` | `+37.33%` | `0.0030 / 0.0030` | **`FAIL`** (CRPS `< 2%`, Var `+37.3%`) |
| `spline_flow` (`campaign_v3`) | `9 / 9` | `89.6% / 90.6% / 90.8%` | `1.1668` | `+0.53%` | `94.38` | `-4.90%` | `0.0030 / 0.0030` | **`FAIL`** (CRPS `+0.53%`, Var `94.38 > 94.28`) |
| `gaussian_lowrank` | `9 / 9` | `89.9% / 94.8% / 98.2%` | `1.3148` | `+13.27%` | `134.67` | `+35.70%` | `0.0030 / 0.0030` | **`FAIL`** (cov90, CRPS/Var) |
| `student_t` | `9 / 9` | `88.6% / 95.7% / 98.4%` | `1.3152` | `+13.32%` | `135.99` | `+37.03%` | `0.0030 / 0.0030` | **`FAIL`** (cov90, CRPS/Var) |
| `gaussian_diag` | `9 / 9` | `89.8% / 95.6% / 98.4%` | `1.3337` | `+14.91%` | `140.54` | `+41.61%` | `0.0030 / 0.0030` | **`FAIL`** (cov90, CRPS/Var) |

---

## 4. Complete `E3` Feature-Ablation Verdicts (`9 / 9` Fits Completed, `recursive_student_t`, Seed `11`)

| Feature Representation | Fits Done | 90% Cov (`h=1 / 4 / 24`) | Primary Macro Scaled CRPS | vs `catboost` (`1.1607`) | Unbiased Variogram | vs `catboost` (`99.24`) | Paired Holm `p` vs `19`-Col (CRPS / Var) | Gate Verdict vs `catboost` |
|---|:---:|:---:|---:|---:|---:|---:|:---:|:---:|
| *`e2_matched` (`19`-col, `E2` s11 ref)* | *`3 / 3` (`E2`)* | *`89.5% / 89.7% / 88.5%`* | *`1.1530`* | *`-0.66%`* | *`92.81`* | *`-6.48%`* | *Reference* | **`PASS` (Gate B)** |
| **`e3_ablation_price_only_13col`** *(no vol/spread)* | `3 / 3` | `89.2% / 89.7% / 88.9%` | **`1.1503`** | **`-0.90%`** | `93.00` | `-6.29%` | **`0.3258 / 0.0790` (NULL)** | **`PASS` (Gate B)** |
| `e3_ablation_campaign_11col` *(no explicit anchors)* | `3 / 3` | `89.2% / 89.6% / 88.7%` | `1.1580` | `-0.23%` | `93.33` | `-5.96%` | `0.0015 / 0.0015` *(worse)* | **`PASS` (Gate B)** |
| `e3_ablation_pilot_v1_8col` *(unbridged)* | `3 / 3` | `89.1% / 89.5% / 89.3%` | `1.1718` | `+0.95%` | `93.59` | `-5.70%` | `0.0015 / 0.0015` *(worse)* | **`FAIL`** (CRPS loss) |

---

## 5. Queue Completion & Next Steps

- **Queue status:** `rtx5080_e2` (`27/27`), `rtx3070_e2` (`27/27`), `rtx5080_e3` (`6/6`), and `rtx3070_e3` (`3/3`) are **100% completed**; `0` processes remain running on either GPU.
- **Full writeup:** Read [`e2_e3_campaign_results.md`](e2_e3_campaign_results.md) for fold/seed dispersion, censoring (`endpoint_marginal`), liquidity strata, likelihoods, and `72h/168h/336h/stationary` bootstrap sensitivity.
- **`E4` Prospective Governance:** The `4` remaining `E4` slots remain **unspent** and the sealed historical holdout (`1785024300`) remains **closed**. Any future `E4` execution requires freezing a live 56-day prospective window `>= 7` days post-manifest (`recursive_student_t`, choosing between parsimonious `13`-col `e3_price_only` and `19`-col `e2_matched`).
