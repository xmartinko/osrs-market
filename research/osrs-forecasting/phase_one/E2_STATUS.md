# Phase One `E2–E4` GPU Campaign Live Status (`E2_STATUS.md`)

**Last updated:** `2026-11-01T06:11:53-08:00`  
**Branch:** `research/osrs-phase-one-2026-11-01`  
**Evaluated commit:** `52e18603e631bd4ba79ce1621f1145b076f8f912` (`git_dirty: false`)  
**Authoritative Git tree:** `C:/Users/xmart/osrs-phase-one` -> synced & SHA-256 verified on WSL (`/home/xmart/osrs-research/code`) and ThinkPad (`/home/martin/osrs-research/code`)  
**Sealed holdout (`>= 1785024300`):** **UNTOUCHED (`holdout_touched: false`)**

---

## 1. Neural Fit Budget Accounting (`72` Total Approved)

| Stage | Budget Allocation | Consumed So Far | Completed | Failed | Remaining |
|---|---:|---:|---:|---:|---:|
| Pilot stage (`p01`–`p03` + 2 pre-opt CUDA index errors) | 5 | 5 | 3 | 2 | 0 |
| `E1` 21-baseline 3-fold CPU campaign | 0 | 0 | — (`21` CPU models) | 0 | 0 |
| **`E2` 6-architecture × 3-seed × 3-fold GPU campaign** | `<= 54` | **54** | 54 | 0 | 0 |
| **`E3` controlled feature ablations (3 ablations × 3 folds)** | `<= 9` | **0** | 0 | 0 | 9 |
| **`E4` prospective 56-day refits (future live window only)** | `<= 4` | **0** *(reserved; holdout sealed)* | 0 | 0 | 4 |
| **Total Campaign** | **72** | **59** | **57** | **2** | **13** |

---

## 2. Preregistered Promotion Gate (vs `catboost_multiquantile_copula`)

Every neural candidate is scored on the **exact identical 3-fold `complete_24h` validation cohort** (`230,657` complete 24h trajectories across `74` items; Fold 1 `106,724`, Fold 2 `68,030`, Fold 3 `55,903`) and must pass:
1. **Calibration gate:** 3-fold mean nominal 90% central interval coverage within **`[87.0%, 93.0%]`** simultaneously at `h = 1`, `h = 4`, and `h = 24`.
2. **Accuracy / Dependence gate (either A or B):**
   - **Gate A (Marginal CRPS):** `>= 2.0%` relative reduction in 3-fold `primary_macro_scaled_crps_1_4_24` (**`<= 1.1375`** vs `1.1607`) with Holm-adjusted 168h moving-block bootstrap `p < 0.05`.
   - **Gate B (Joint Variogram):** `>= 5.0%` relative reduction in 3-fold `scaled_variogram_p05_unbiased` (**`<= 94.28`** vs `99.24`) with Holm-adjusted 168h moving-block bootstrap `p < 0.05` and no marginal CRPS loss (`<= 1.1607`).

---

## 3. Live Queue Progress & Provenance

- **Desktop WSL2 RTX 5080 (`rtx5080_e2`):** status `completed`, fit `27/27` (`done`), `code_tree=/home/xmart/osrs-research/code`, `code_commit=52e18603e631bd4ba79ce1621f1145b076f8f912`
- **ThinkPad RTX 3070 (`rtx3070_e2`):** status `unknown`, fit `0/27` (`done`), `code_tree=/home/martin/osrs-research/code`, `code_commit=52e18603e631bd4ba79ce1621f1145b076f8f912`

---

## 4. `E2` Gate Verdicts

| Candidate Architecture | Fits Done | 90% Cov (`h=1 / 4 / 24`) | Primary Macro Scaled CRPS | vs `catboost` (`1.1607`) | Unbiased Variogram | vs `catboost` (`99.24`) | Holm `p` (CRPS / Var) | Gate Verdict |
|---|:---:|:---:|---:|---:|---:|---:|:---:|:---:|
| `spline_flow` (`campaign_v3`) | `9 / 9` | `89.6% / 90.6% / 90.8%` | `1.1668` | `+0.53%` | `94.38` | `-4.90%` | `0.0030 / 0.0030` | **`FAIL`** (CRPS/Var) |
| `recursive_student_t` | `9 / 9` | `89.4% / 89.6% / 88.8%` | `1.1507` | `-0.86%` | `92.90` | `-6.40%` | `0.0030 / 0.0030` | **`PASS`** (Gate B Joint Var) |
| `direct_marginal_student_t` | `9 / 9` | `89.2% / 89.4% / 89.2%` | `1.1508` | `-0.85%` | `136.30` | `+37.33%` | `0.0030 / 0.0030` | **`FAIL`** (CRPS/Var) |
| `gaussian_lowrank` | `9 / 9` | `89.9% / 94.8% / 98.2%` | `1.3148` | `+13.27%` | `134.67` | `+35.70%` | `0.0030 / 0.0030` | **`FAIL`** (cov90, CRPS/Var) |
| `student_t` | `9 / 9` | `88.6% / 95.7% / 98.4%` | `1.3152` | `+13.32%` | `135.99` | `+37.03%` | `0.0030 / 0.0030` | **`FAIL`** (cov90, CRPS/Var) |
| `gaussian_diag` | `9 / 9` | `89.8% / 95.6% / 98.4%` | `1.3337` | `+14.91%` | `140.54` | `+41.61%` | `0.0030 / 0.0030` | **`FAIL`** (cov90, CRPS/Var) |

---

## Next Steps in Queue
- Complete remaining `E2` fits across `rtx5080_e2` and `rtx3070_e2`, updating gate verdicts and pushing milestone updates to `devstash`.
- Dispatch `E3` 9-fit feature-set ablation (`pilot_v1` 8-col, `campaign` 11-col, `e3_price_only` 13-col × Folds 1–3) on RTX 5080 once `E2` finishes.
- Keep `E4` (`4` slots) unspent in reserve unless/until a future live 56-day prospective window opens after gate clearance; keep sealed holdout `1785024300` closed.
