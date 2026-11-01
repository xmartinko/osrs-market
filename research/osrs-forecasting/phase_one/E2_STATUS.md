# Phase One `E2–E4` GPU Campaign Live Status (`E2_STATUS.md`)

**Last updated:** `2026-11-01T03:20:00-08:00`  
**Branch:** `research/osrs-phase-one-2026-11-01`  
**Sealed holdout (`>= 1785024300`):** **UNTOUCHED (`holdout_touched: false`)**

---

## 1. Neural Fit Budget Accounting (`72` Total Approved)

| Stage | Budget Allocation | Consumed So Far | Completed | Failed | Remaining |
|---|---:|---:|---:|---:|---:|
| Pilot stage (`p01`–`p03` + 2 pre-opt CUDA index errors) | 5 | 5 | 3 | 2 | 0 |
| `E1` 21-baseline 3-fold CPU campaign | 0 | 0 | — (`21` CPU models) | 0 | 0 |
| **`E2` 6-architecture × 3-seed × 3-fold GPU campaign** | `<= 54` | **0** *(launching now)* | 0 | 0 | 54 |
| **`E3` controlled feature ablations (3 ablations × 3 folds)** | `<= 9` | **0** *(queued after E2)* | 0 | 0 | 9 |
| **`E4` prospective 56-day refits (future live window only)** | `<= 4` | **0** *(reserved; holdout sealed)* | 0 | 0 | 4 |
| **Total Campaign** | **72** | **5** | **3** | **2** | **67** |

---

## 2. Preregistered Promotion Gate (vs `catboost_multiquantile_copula`)

Every neural candidate is scored on the **exact identical 3-fold `complete_24h` validation cohort** (`230,657` complete 24h trajectories across `74` items; Fold 1 `106,724`, Fold 2 `68,030`, Fold 3 `55,903`) and must pass:
1. **Calibration gate:** 3-fold mean nominal 90% central interval coverage within **`[87.0%, 93.0%]`** simultaneously at `h = 1`, `h = 4`, and `h = 24`.
2. **Accuracy / Dependence gate (either A or B):**
   - **Gate A (Marginal CRPS):** `>= 2.0%` relative reduction in 3-fold `primary_macro_scaled_crps_1_4_24` (**`<= 1.1375`** vs `1.1607`) with Holm-adjusted 168h moving-block bootstrap `p < 0.05`.
   - **Gate B (Joint Variogram):** `>= 5.0%` relative reduction in 3-fold `scaled_variogram_p05_unbiased` (**`<= 94.28`** vs `99.24`) with Holm-adjusted 168h moving-block bootstrap `p < 0.05` and no marginal CRPS loss (`<= 1.1607`).

---

## 3. Current Execution State & Active Queues

- **Current phase:** Verifying unit tests (`pytest` + `ruff`) and synthetic zero-market-data GPU smoke checks, committing frozen `e2_e4_campaign_protocol.json` + `probabilistic_campaign.py` to `devstash`, then dispatching concurrent GPU queues:
  - **Queue `rtx5080_e2` (Desktop WSL2 RTX 5080, 27 fits):**
    - `spline_flow` (`campaign_v3` cumulative affine + Cholesky correlation + 4 RQ-spline coupling blocks + learnable Student-$t$ base): seeds `11, 23, 47` × folds `1, 2, 3` (`9` fits)
    - `recursive_student_t` (closed-loop 1-step autoregressive Student-$t$ rollout): seeds `11, 23, 47` × folds `1, 2, 3` (`9` fits)
    - `gaussian_lowrank` (rank-4 + diagonal Gaussian increments): seeds `11, 23, 47` × folds `1, 2, 3` (`9` fits)
  - **Queue `rtx3070_e2` (ThinkPad RTX 3070 Laptop GPU, 27 fits):**
    - `direct_marginal_student_t` (shared-encoder independent-horizon cumulative Student-$t$): seeds `11, 23, 47` × folds `1, 2, 3` (`9` fits)
    - `student_t` (independent-increment Student-$t$): seeds `11, 23, 47` × folds `1, 2, 3` (`9` fits)
    - `gaussian_diag` (independent-increment Gaussian): seeds `11, 23, 47` × folds `1, 2, 3` (`9` fits)

---

## 4. `E2` Gate Verdicts So Far

| Candidate Architecture | Seeds × Folds Done | 90% Cov (`h=1 / 4 / 24`) | Primary Macro Scaled CRPS | vs `catboost` (`1.1607`) | Unbiased Variogram | vs `catboost` (`99.24`) | Holm `p` (CRPS / Var) | Gate Verdict |
|---|:---:|:---:|---:|---:|---:|---:|:---:|:---:|
| `spline_flow` (`campaign_v3`) | `0 / 9` | pending | pending | pending | pending | pending | pending | `PENDING` |
| `recursive_student_t` | `0 / 9` | pending | pending | pending | pending | pending | pending | `PENDING` |
| `direct_marginal_student_t` | `0 / 9` | pending | pending | pending | pending | pending | pending | `PENDING` |
| `gaussian_lowrank` | `0 / 9` | pending | pending | pending | pending | pending | pending | `PENDING` |
| `student_t` | `0 / 9` | pending | pending | pending | pending | pending | pending | `PENDING` |
| `gaussian_diag` | `0 / 9` | pending | pending | pending | pending | pending | pending | `PENDING` |

---

## 5. Next Milestones
1. Complete `pytest` + synthetic GPU checks and push frozen `E2–E4` preregistration commit to `devstash`.
2. Launch `rtx5080_e2` (27 fits) and `rtx3070_e2` (27 fits) concurrently; update this file as architectures complete and gate verdicts land.
3. Run `E3` controlled feature ablations (`9` fits: `pilot_v1` 8-col, `campaign` 11-col, and `e3_price_only` 13-col no-volume/no-spread across Folds 1–3 on the top calibrated `E2` architecture).
4. Sync all run summaries/loss panels to VPS `/home/martin/osrs-data/phase-one-20261101/runs/` (outside Git), commit final `e2_e3_campaign_results.{json,md}` and updated `E2_STATUS.md`, and push to `devstash`.
