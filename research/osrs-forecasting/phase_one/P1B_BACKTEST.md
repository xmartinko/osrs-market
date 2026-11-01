# Phase One `P1b` Historical `300s` Execution-Resolution Backtest (`300s` vs `3600s` Ceteris-Paribus Contrast)

**Last updated:** `2026-11-01T15:12:00-08:00`  
**Status:** **`COMPLETED FROM CLEAN COMMIT (`git_dirty: false`) — LATENCY RELIEVES FILLS (`P_fill`, `P_expiry` PASS), SPREAD + GE TAX WALL STILL BLOCKS PROFITABILITY (`P_spread`, `P_pnl` FAIL -> CASE 2)`**  
**Branch:** `research/osrs-phase-one-2026-11-01`  
**Preregistration manifest (committed & pushed at `e0e3ac55` BEFORE scanning any `P1b` rows or computing P/L):** [`p1b_backtest_protocol.json`](p1b_backtest_protocol.json) (`SHA-256: 0a0f0995fcf804c2e707b3e1cec1b2b705642dbc4d16fb3e5c206792385140d5`)  
**Clean execution commit:** `47ba2a7a76b2118ca58430fdd7d62c130db2289a` (`git_dirty: false`)  
**Machine-readable results:** [`p1b_backtest_results.json`](p1b_backtest_results.json) (`SHA-256: 9220c560998c5057857ddc95339173ee7de210dc94add34c5f4fac36ddf025ce`)  
**Parent `3600s` baseline (`P1`):** [`P1_BACKTEST.md`](P1_BACKTEST.md), [`p1_backtest_results.json`](p1_backtest_results.json) (`SHA-256: b66149924ab94adfcbe912c6aaf1b341b3ac1a69fddf12c87b4fc272ad630298`)  
**Runner & test suite (`85 / 85` passing, `ruff` clean):** [`ml/src/osrs_ml/probabilistic_backtest_p1b.py`](../../../ml/src/osrs_ml/probabilistic_backtest_p1b.py), [`ml/tests/test_probabilistic_backtest_p1b.py`](../../../ml/tests/test_probabilistic_backtest_p1b.py)  
**Full run archive (ledgers & quantile caches outside Git):** `/home/martin/osrs-data/phase-one-20261101/runs/p1b_backtest_recursive_student_t/` (VPS) & `/home/xmart/osrs-research/runs/p1b_backtest_recursive_student_t/` (Desktop WSL; tarball `SHA-256: 4e6f3542e1689831531b27f6f9e91bb6ca8438507f69dc47b954ec1463972ede`)  
**Scope & Governance:** Retrospective execution-resolution experiment across the identical three `E2/E3/P1` validation folds (`2025-10-29` .. `2026-07-26`, `6,480` hours, `74` items). **`0` `E4` slots consumed** (`68 / 72` neural fit budget unchanged; `4 / 72` `E4` reserve untouched). **Sealed holdout (`>= 1785024300`) strictly untouched** (`holdout_touched: false`; DuckDB Parquet pushdown enforced `ts < 1785024000 < 1785024300`, observed `max(ts) = 1785023700`).

---

## Executive Falsification Verdict

`P1b` tested whether `P1`'s `79.12%` zero-fill ceiling-expiry loss, `6.72%` unit fill rate, `2.64%` realised round-trip spread, and `-71,792 GP` net P/L were caused by **`3600s` whole-bucket execution latency (`~7,200s` post-submission wait to `h = 2`)** rather than the Grand Exchange spread + `2.00%` tax wall itself. Holding the preregistered policy, frozen `recursive_student_t` 768-path quantiles (`80febc95...`, `c97c26bd...`, `014ffebf...`), hourly signal timestamps (`t_hour + 3900`), and [`osrs_ml.{costs,execution,backtest}`](../../../ml/src/osrs_ml/backtest.py) machinery **100% unchanged** while resolving execution on verified historical **`300s` bars** (`prices_5m_p1b.parquet`, `SHA-256: 2fbe998b...`, cutting median first-fill wait from **`7,200s` to `900s`**) yields an unambiguous **`Case 2` verdict across all three preregistered evaluation arms**:

| Preregistered Falsifiable Prediction | Threshold | **Walk-Forward (`P1b` Selected)** (`P1` -> `P1b`) | **Walk-Forward (`P1`-Fixed Cells Ceteris Paribus)** (`P1` -> `P1b`) | **Unfiltered `H24h_edge0bps`** (`P1` -> `P1b`) | Outcome |
|---|---|---:|---:|---:|:---:|
| **`P_fill`:** Unit fill rate (`%` of requested units filled) | **`>= 15.0%`** | `6.72%` -> **`19.23%`** (`+12.51 pp`) | `6.72%` -> **`19.47%`** (`+12.75 pp`) | `8.91%` -> **`22.31%`** (`+13.40 pp`) | **`PASS` (`3/3`)** |
| **`P_expiry`:** Zero-fill buy ceiling-expiry rate | **`<= 50.0%`** | `79.12%` -> **`27.21%`** (`-51.91 pp`) | `79.12%` -> **`20.00%`** (`-59.12 pp`) | `75.38%` -> **`26.23%`** (`-49.16 pp`) | **`PASS` (`3/3`)** |
| **`P_spread`:** Median realised RT spread + `20 bps` slip | **`< 2.00%`** | `2.64%` -> **`2.59%`** (`-0.05 pp`) | `2.64%` -> **`2.87%`** (`+0.24 pp`) | `2.55%` -> **`2.53%`** (`-0.02 pp`) | **`FAIL` (`0/3`)** |
| **`P_pnl`:** Net P/L `> 0 GP` & 168h bootstrap `p < 0.05` | **`> 0`, `p < .05`** | `-71,792` -> **`-201,361 GP`** (`p = 1.0000`) | `-71,792` -> **`-614,599 GP`** (`p = 1.0000`) | `+1,184,045` -> **`+483,470 GP`** (`p = 0.3493`) | **`FAIL` (`0/3`)** |
| **Preregistered Decision-Matrix Classification** | — | **`Case 2`** | **`Case 2`** | **`Case 2`** | **Unanimous `Case 2`** |

### Three Key Findings

1. **`3600s` Whole-Bucket Latency *Was* Causing the Fill Bottleneck (`P_fill` & `P_expiry` Confirmed):**
   - Resolving execution on `300s` bars cut median first-fill latency by **`87.5%`** (`7,200s` -> **`900s`**, the very first post-latency `300s` bucket `[t_hour+4200, t_hour+4500)`), slashed zero-fill ceiling expiries by **`-49` to `-59` percentage points** (`79.1%` -> **`20.0%–27.2%`**), nearly **tripled unit fill rates** (`6.72%` -> **`19.23%–19.47%`**), and increased completed walk-forward round-trips **`5.6x`** (`19` -> **`107`**; `19` -> **`68`** under `P1`-fixed cells).
2. **Faster Fills Exposed the True Binding Constraint — The GE Spread + `2%` Tax Wall (`P_spread` & `P_pnl` Falsified):**
   - Executing `5.6x` more trades on `300s` bars scaled **gross mid-to-mid profit `4.57x`** (`+830,607 GP` -> **`+3,796,593 GP`**, with **`82.24%` gross mid hit rate** across `107` trades and **`81.5%–96.3%` across all `6` grid cells**), proving that the previously uncaptured fast-rebound signals had genuine positive gross directionality.
   - **However, total execution friction scaled `4.43x`** (`-902,399 GP` -> **`-3,997,954 GP`**: `-2,101,755 GP` pure both-side half-spread + `-180,906 GP` explicit slippage + `-1,715,293 GP` `2.00%` GE tax = **`105.3%` of gross profit**), pushing net walk-forward P/L to **`-201,361 GP` (`-0.20%`, Sharpe `-0.110`, $p = 1.0000$)** and pure ceteris-paribus `P1`-fixed-cell net P/L to **`-614,599 GP` (`-0.61%`, Sharpe `-0.463`, paired `P1b - P1` = `-542,807 GP`)**. **Zero of the `6` grid cells clear `p < 0.05` against cash (`min p = 0.3493`), and every cell loses `-1.07M` to `-1.73M GP` in Fold 3.**
3. **Why Realised Spread Stayed at `2.53%–2.87%` Instead of Compressing to `0.79%`: The 60-Minute VWAP Non-Synchronicity Illusion:**
   - In `P1`, the `0.79%` median spread observed at hourly signal origins looked like a tight executable spread that widened to `2.64%` over the `2h` wait.
   - Measuring the **contemporaneous `300s` spread at the exact same submission timestamp (`now = t_hour + 3900`, bar `ts = t_hour + 3300`)** disproves that interpretation: at the exact moment those `147` orders are submitted, the hourly VWAP spread is **`0.88%` median (`0.79%` on completed trades)**, **whereas the contemporaneous `300s` bid-ask spread is ALREADY `1.98%` median (`2.09%` on completed trades; `2.32%` on `P1`-fixed cells)**!
   - Non-synchronous 60-minute VWAP aggregation across an intra-hour dip (`avg_low_1h` weighted early in the hour, `avg_high_1h` weighted late after a drop) creates an **illusory narrow hourly spread** while the true instantaneous 5-minute Grand Exchange spread remains **`~2.0%–2.3%`** (`+ 2.00%` GE tax + `0.20%` slippage = **`4.34%–4.65%` realised round-trip cost wall**).

---

## 1. Explicit Methodological Scope, Data Provenance, & Limitations

1. **Retrospective Execution Contrast (`Not Prospective`, `Not E4`):** `P1b` evaluates historical `300s` execution bars on the same three development validation windows (`2025-10-29T00:00Z` .. `2026-07-26T00:00Z`) used in `E1/E2/E3/P1`. It consumes **`0` `E4` slots** and never accesses sealed holdout timestamps (`>= 1785024300`).
2. **Staged `300s` Input Verification & Holdout Pushdown Guard:**
   - Staged file: `/home/xmart/osrs-research/data/p1b_5m/prices_5m_p1b.parquet` (`1,366,990,873` bytes, `160,997,249` footer rows, verified `SHA-256: 2fbe998bc7b798570cb01adf7f692446aaf9ff1b7bf741e7c8859e0695a04fed`, footer `SHA-256: 2a931ca4...`).
   - Because the staged file spans through `2026-08-14`, [`load_verified_5m_execution_bars`](../../../ml/src/osrs_ml/probabilistic_backtest_p1b.py#L97-L162) enforces `item_id IN (74 selected_ids) AND ts >= 1759622400 AND ts < 1785024000 AND ts < 1785024300` inside DuckDB Parquet predicate pushdown *before* Python materialization (`6,226,398` rows scanned; verified `min_ts = 1759622400`, `max_ts = 1785023700 < 1785024000 < 1785024300`).
3. **Averaged `300s` Quotes & Non-Imputed Null `mid_price` Limitation:**
   - Derived from `kaggle-5m` canonical 5-minute buckets, `avg_high_price` and `avg_low_price` are **5-minute volume-weighted directional trade averages**; they cannot observe intra-5-minute limit-order book depth, resting queue priority, or tick-by-tick fill ordering within a `300s` bucket.
   - Across the `5,718,275` present validation rows (`99.37%` of all `5,754,240` `74 × 77,760` `300s` cells), **`463,917` one-sided rows (`8.06%` of grid cells: `3.32%` ask-only, `4.73%` bid-only) have `mid_price = NULL`**, plus `41,439` cells (`0.72%`) where neither side printed. `mid_price` and missing directional volumes are **never imputed**: causal last-print side prices carry forward with exact staleness `delay_seconds + (ts - last_side_ts)` (`source_interval_seconds = 300`), while unprinted side volumes stay strictly `0` so zero-volume sides never fill.

---

## 2. Empirical `300s` vs `3600s` Market Microstructure & Cost Wall (`2025-10-29` .. `2026-07-26`)

| Microstructure / Cost-Wall Quantity (`74` Items, `270` Val Days) | **`P1` (`3600s` Hourly Bars)** | **`P1b` (`300s` 5-Minute Bars)** | Microstructural Interpretation |
|---|---:|---:|---|
| Total item-bar grid cells in `[1761696000, 1785024000)` | `479,520` | **`5,754,240`** | `12x` finer temporal resolution |
| Two-sided active cells (`hvol > 0 & lvol > 0`, `mid_price` non-null) | `456,611` (`95.22%` usable) | **`5,249,172` (`91.22%`)** (`5,093,218` non-inverted `ask >= bid`) | `3.32%` ask-only + `4.73%` bid-only + `0.72%` empty (`2.71%` inverted 5m bars excluded) |
| Quoted spread `p25 / p50 / p75 / p90` (`continuous`) | `1.27% /` **`1.96%`** `/ 2.66% / 3.89%` | `0.96% /` **`1.91%`** `/ 2.81% / 4.01%` | Median 5m spread (`1.91%`) matches hourly (`1.96%`), with wider `p90` (`4.01%`) |
| Crossed RT cost wall (`spread + 2% GE tax + 20 bps slip`, `p50 / p90`) | **`4.34%`** `/ 6.90%` | **`4.37%`** `/ 7.02%` | Unconditional round-trip cost wall is invariant (`~4.35%` median) |
| `|4h|` midpoint move `p50 / p90` | `0.68% / 2.87%` | **`0.83% / 3.17%`** | Hourly VWAP slightly smooths 4h point-to-point endpoints |
| `|24h|` midpoint move `p50 / p90` | `1.12% / 4.75%` | **`1.25% / 5.05%`** | Median 24h move (`1.25%`) is `< 0.3x` of the `4.37%` RT cost wall |
| `24h` pairs clearing `2.00%` GE tax alone (long-only) | `14.37%` | **`16.04%`** | `< 1 in 6` 24h windows beat seller tax alone |
| `24h` pairs clearing `spread + 2% GE tax` (long-only) | `4.78%` | **`5.86%`** | **`4.38%`** after `+20 bps` slippage (`3.64%` on hourly) |
| `4h` pairs clearing `spread + 2% GE tax + 20 bps slip` (long-only) | `0.89%` | **`1.46%`** | `< 1 in 68` 4h item windows clear the crossed cost wall |

---

## 3. Side-by-Side `P1` (`3600s`) vs `P1b` (`300s`) Performance Across All Policy Arms

### 3.1 Inner 21-Day (`504h`) Pre-Validation Training Grid on `300s` Bars (Zero Validation Peek)

| Grid Cell (`H`, `min_net_edge`) | Inner Fold 1 Net GP | Inner Fold 2 Net GP | Inner Fold 3 Net GP | Pooled Inner `300s` Net GP (`%`) | `P1` (`3600s`) Inner Net GP | Inner `300s` Sig / Sub / Exp0 / **Trades** (Fill `%`) | Inner Hit (Net / Gross) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `H4h_edge0bps` | `+26,995` | `+5,033` | `+4,645` | `+36,673` (`+0.037%`) | `+5,394` | `18 / 13 / 2 /` **`11`** (`3.40%`) | `63.6% / 90.9%` |
| `H4h_edge25bps` | `+26,995` | `+5,033` | `+4,906` | `+36,934` (`+0.037%`) | `+5,394` | `17 / 12 / 2 /` **`10`** (`3.39%`) | `70.0% / 90.0%` |
| `H4h_edge50bps` | `+17,889` | `+5,033` | `+4,906` | `+27,828` (`+0.028%`) | `+5,394` | `14 / 9 / 2 /` **`7`** (`2.95%`) | `71.4% / 85.7%` |
| `H24h_edge0bps` | `+100,949` | `+6,460` | `+322,013` | `+429,422` (`+0.429%`) | `+198,074` | `68 / 47 / 10 /` **`37`** (`22.91%`) | `54.1% / 78.4%` |
| **`H24h_edge25bps`** *(Fold 3 & Pooled pick)* | `+102,659` | `+6,460` | **`+342,974`** | **`+452,093` (`+0.452%`)** | `+293,402` | `63 / 43 / 9 /` **`34`** (`23.01%`) | `58.8% / 76.5%` |
| **`H24h_edge50bps`** *(Fold 1 & Fold 2 pick)* | **`+153,502`** | **`+46,370`** | `+120,441` | `+320,313` (`+0.320%`) | `+13,776` | `53 / 35 / 7 /` **`28`** (`12.04%`) | `60.7% / 78.6%` |

*(Causal 21d training selection on `300s` bars chose `{1: H24h_edge50bps, 2: H24h_edge50bps, 3: H24h_edge25bps}` — identical to `P1` on Folds 2 & 3, and switching Fold 1 from `H4h_edge50bps` to `H24h_edge50bps`. Both `P1b`-selected walk-forward AND `P1`-fixed-cell ceteris-paribus walk-forward `{1: H4h_edge50bps, 2: H24h_edge50bps, 3: H24h_edge25bps}` are reported below.)*

### 3.2 Direct Head-to-Head Contrast: `P1` (`3600s`) vs `P1b` (`300s`) Across Primary & Reference Arms (`270d`, `100M GP`)

| Metric | **`P1` Walk-Forward (`3600s`)** | **`P1b` `P1`-Fixed Cells (`300s` Pure Ceteris Paribus)** | **`P1b` Walk-Forward (`300s` Selected)** | **`P1` `H24h_edge0bps` (`3600s`)** | **`P1b` `H24h_edge0bps` (`300s`)** |
|---|---:|---:|---:|---:|---:|
| Fold 1 / Fold 2 / Fold 3 Net GP | `+403k / +265k / -739k` | `+598k / +519k / -1,732k` | `+1,011k / +519k / -1,732k` | `+1,095k / +440k / -350k` | `+907k / +697k / -1,121k` |
| **Pooled Net P/L (`GP` / `%` Capital)** | **`-71,792` (`-0.07%`)** | **`-614,599` (`-0.61%`)** | **`-201,361` (`-0.20%`)** | **`+1,184,045` (`+1.18%`)** | **`+483,470` (`+0.48%`)** |
| **Completed Gross Mid-to-Mid P/L (`GP`)** | `+830,607` | **`+1,620,339`** (`1.95x`) | **`+3,796,593`** (`4.57x`) | `+3,535,676` | **`+5,455,417`** (`1.54x`) |
| Pure Both-Side Half-Spread Cost (`GP`) | `-444,524` | `-1,189,149` | `-2,101,755` | `-1,219,142` | `-2,604,477` |
| Explicit `10 bps/side` Slippage (`GP`) | `-42,982` | `-100,427` | `-180,906` | `-106,468` | `-225,891` |
| `2.00%` GE Seller Tax (`GP`) | `-414,893` | `-945,362` | `-1,715,293` | `-1,026,021` | `-2,141,579` |
| **Total Friction Paid (`%` of Gross Alpha)** | `-902,399` (**`108.6%`**) | `-2,234,938` (**`137.9%`**) | `-3,997,954` (**`105.3%`**) | `-2,351,631` (**`66.5%`**) | `-4,971,947` (**`91.1%`**) |
| Selected Signals / Buy Orders Submitted | `125 / 91` | `125 / 85` | `233 / 147` | `284 / 195` | `284 / 183` |
| **Zero-Fill Ceiling Expiries (`%` of Sub)** | `72` (**`79.12%`**) | `17` (**`20.00%`**) | `40` (**`27.21%`**) | `147` (**`75.38%`**) | `48` (**`26.23%`**) |
| **Completed Round-Trips** (`End Inv = 0`) | **`19`** | **`68`** (`3.58x`) | **`107`** (`5.63x`) | **`48`** | **`135`** (`2.81x`) |
| **Unit Fill Rate (`%` of Requested Units)** | **`6.72%`** | **`19.47%`** (`2.90x`) | **`19.23%`** (`2.86x`) | **`8.91%`** | **`22.31%`** (`2.50x`) |
| **First Buy Fill Wait `p50` / Unit Mean (`s`)** | **`7,200s` / `7,200s`** | **`900s` / `3,550s`** | **`900s` / `3,312s`** | **`7,200s` / `7,200s`** | **`900s` / `3,126s`** |
| Two-Way Turnover (`x` Initial Cash) | `0.426x` | **`1.005x`** | **`1.807x`** | `1.055x` | **`2.255x`** |
| **Gross Mid Hit Rate / Net Hit Rate (`%`)** | `73.68% / 63.16%` | **`80.88%` / `54.41%`** | **`82.24%` / `55.14%`** | `75.00% / 56.25%` | **`81.48%` / `54.07%`** |
| Mean Gross / Mean Net Trade Return (`%`) | `+7.54% / +2.46%` | `+6.10% / +0.99%` | `+5.86% / +1.00%` | `+6.55% / +1.66%` | `+5.56% / +0.76%` |
| HourlyOrigin Spread `p50` -> `300s` Sub `p50` | `0.79%` -> *(same)* | `0.65%` -> **`2.32%`** | `0.79%` -> **`2.09%`** | `0.99%` -> *(same)* | `0.76%` -> **`2.12%`** |
| **Realised RT Spread + Slip `p50` (Total incl Tax)** | **`2.64%`** (`4.54%`) | **`2.87%`** (`4.65%`) | **`2.59%`** (`4.34%`) | **`2.55%`** (`4.43%`) | **`2.53%`** (`4.37%`) |
| Sharpe (`Per-Trade` / `Hourly` / `Daily`) | `+0.225 / -0.086 / -0.085` | `+0.128 / -0.463 / -0.617` | `+0.122 / -0.110 / -0.157` | `+0.177 / +0.478 / +1.286` | `+0.095 / +0.301 / +0.443` |
| Max Drawdown (`GP` / `%`) | `1.27M` (`1.26%`) | `2.36M` (`2.34%`) | `2.36M` (`2.33%`) | `2.75M` (`2.67%`) | `1.69M` (`1.67%`) |
| 168h Block-Bootstrap 95% CI (`p > 0`) | `[-2.08M, +1.48M]` (`1.00`) | `[-3.68M, +1.72M]` (`1.00`) | `[-3.49M, +2.78M]` (`1.00`) | `[-0.60M, +3.32M]` (`0.122`) | `[-1.89M, +3.02M]` (**`0.349`**) |
| Paired `P1b (300s) - P1 (3600s)` $\Delta$ GP (`CI`) | — | **`-542,807`** (`[-1.95M, +0.59M]`) | **`-129,569`** (`[-1.84M, +1.71M]`) | — | **`-700,575`** (`[-2.49M, +0.90M]`) |

### 3.3 Full `6`-Cell Outer-Validation Grid on `300s` Bars (`270d`, `100M GP`)

| Grid Cell | Fold 1 Net GP | Fold 2 Net GP | Fold 3 Net GP | **`P1b` (`300s`) Net GP (`%`)** | `P1` (`3600s`) Net GP | Gross Mid P/L -> Total Costs | Sig / Sub / Exp0 / **Trades** (Fill `%`) | Hit (`Net / Gross`) | Hourly Sharpe | 168h `p > 0` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `H4h_edge0bps` | `+748,026` | `+251,597` | `-1,212,370` | **`-212,747` (`-0.21%`)** | `-203,244` | `+1,049,807` -> `-1,262,554` | `82 / 63 / 18 /` **`45`** (`16.28%`) | `62.2% / 86.7%` | `-0.256` | `1.0000` |
| `H4h_edge25bps` | `+697,462` | `+301,023` | `-1,069,483` | **`-70,998` (`-0.07%`)** | `-217,790` | `+974,434` -> `-1,045,432` | `63 / 50 / 12 /` **`38`** (`15.38%`) | `68.4% / 92.1%` | `-0.089` | `1.0000` |
| `H4h_edge50bps` | `+597,871` | `+160,399` | `-1,069,483` | **`-311,213` (`-0.31%`)** | `-422,992` | `+469,109` -> `-780,322` | `43 / 36 / 9 /` **`27`** (`12.36%`) | `74.1% /` **`96.3%`** | `-0.419` | `1.0000` |
| `H24h_edge0bps` | `+907,163` | `+697,030` | `-1,120,723` | **`+483,470` (`+0.48%`)** | `+1,184,045` | `+5,455,417` -> `-4,971,947` | `284 / 183 / 48 /` **`135`** (`22.31%`) | `54.1% / 81.5%` | `+0.301` | `0.3493` |
| `H24h_edge25bps` *(Pooled pick)* | `+944,876` | `+503,483` | `-1,731,923` | **`-283,564` (`-0.28%`)** | `+641,289` | `+4,288,828` -> `-4,572,392` | `258 / 167 / 42 /` **`125`** (`20.49%`) | `55.2% / 81.6%` | `-0.152` | `1.0000` |
| `H24h_edge50bps` | `+1,011,109` | `+519,453` | `-1,506,032` | **`+24,530` (`+0.02%`)** | `+589,057` | `+3,831,066` -> `-3,806,536` | `229 / 144 / 40 /` **`104`** (`17.82%`) | `56.7% / 84.6%` | `+0.026` | `0.5362` |

---

## 4. Exact 5-Way Unfilled-Expiry Decomposition & Spread Non-Synchronicity Analysis

### 4.1 5-Way Partition of Zero-Fill Buy Expiries (`P1` `3600s` vs `P1b` `300s`)

Every `buy_expired (filled == 0)` order was partitioned across its post-latency timeout window (`[submitted + 300s, submitted + 7500s)`):

| Policy Arm | Total Submitted | **Total Zero-Fill Expiries (`%`)** | **(1) Price `> Ceiling` on All Active Prints** | **(2) `5m` Integer Lot Floor (`0 < 5m_vol < 50`, `cum >= 50`)** | **(3) Low Cumulative Compatible Vol (`< 50` units)** | **(4) Zero Fresh Prints in Window** | First Eligible Bar Ask Jump `p50` (`p90`) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `P1` WF (`3600s`) | `91` | **`72` (`79.12%`)** | `62` (`86.1%`) | `0` (`0.0%`) | `0` (`0.0%`) | `10` (`13.9%`) | **`+5.64%`** (`+12.22%`) |
| **`P1b` `P1`-Fixed (`300s`)** | `85` | **`17` (`20.00%`)** | `16` (`94.1%`) | **`0` (`0.0%`)** | `1` (`5.9%`) | `0` (`0.0%`) | **`+1.63%`** (`+7.06%`) |
| **`P1b` WF (`300s`)** | `147` | **`40` (`27.21%`)** | `37` (`92.5%`) | **`0` (`0.0%`)** | `3` (`7.5%`) | `0` (`0.0%`) | **`+2.25%`** (`+7.32%`) |
| `P1` `H24h_edge0bps` (`3600s`) | `195` | **`147` (`75.38%`)** | `130` (`88.4%`) | `0` (`0.0%`) | `0` (`0.0%`) | `17` (`11.6%`) | **`+5.28%`** (`+10.62%`) |
| **`P1b` `H24h_edge0bps` (`300s`)** | `183` | **`48` (`26.23%`)** | `45` (`93.8%`) | **`0` (`0.0%`)** | `3` (`6.2%`) | `0` (`0.0%`) | **`+2.63%`** (`+7.29%`) |

- **Zero 5-minute integer-capacity quantization artifact (`0 / 40`, `0 / 17`, `0 / 48`):** In the 74-item high-liquidity universe, `2%` (`200 bps`) of a `300s` bucket's volume never caused artificial sub-1-unit rounding expiries when cumulative price-compatible volume was sufficient.
- **22 fill opportunities instead of 1:** On `3600s` bars, an order submitted at `t_hour + 3900` had only **1** eligible hourly bar (`h = 2`) before expiring at `+7,500s`. On `300s` bars, it has **22** consecutive `300s` bars starting at `t_hour + 4200` (`avail = t_hour + 4800`), so `75%` of filled positions get their first fill at the **minimum possible `900s` wait** (`p10 = 900s, p25 = 900s, p50 = 900s, p75 = 1,350s`).

### 4.2 Spread & Shortfall Distributions on `P1b` Walk-Forward (`107` Completed Trades, `5,539` Fill Events)

| Spread / Cost / Latency Distribution | `count` | `mean` | `std` | `p10` | `p25` | **`p50` (Median)** | `p75` | `p90` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Hourly VWAP origin spread (`hourly.parquet` at `t_hour + 3900`) | `147` | `1.20%` | `1.19%` | `0.00%` | `0.38%` | **`0.88%`** | `1.72%` | `2.86%` |
| **Contemporaneous `300s` spread at exact submission (`t_hour + 3900`)** | **`147`** | **`2.93%`** | `2.96%` | `0.45%` | `0.98%` | **`1.98%`** | `3.92%` | **`6.49%`** |
| Fill-bar `300s` spread (`continuous`, non-null `mid_price`, `96.6%` of fills) | `5,353` | `2.53%` | `2.23%` | `0.40%` | `1.07%` | **`2.18%`** | `3.36%` | `4.68%` |
| Fill-bar `300s` spread (`integer` causal BBO) | `5,539` | `2.53%` | `2.23%` | `0.37%` | `1.07%` | **`2.18%`** | `3.36%` | `4.69%` |
| Completed trades: **Hourly origin modelled RT spread + `20 bps` slip** | `107` | `1.32%` | `1.20%` | `0.20%` | `0.48%` | **`0.99%`** | `1.89%` | `2.66%` |
| Completed trades: **`300s` submission modelled RT spread + `20 bps` slip** | `107` | **`3.12%`** | `2.81%` | `0.70%` | `1.22%` | **`2.29%`** | `4.06%` | `6.38%` |
| Completed trades: **Realised RT spread + slippage paid** | `107` | **`2.95%`** | `1.58%` | `1.32%` | `1.91%` | **`2.59%`** | `3.62%` | `5.14%` |
| Completed trades: **Realised total RT cost incl. `2%` GE tax** | `107` | **`4.66%`** | `1.42%` | `3.17%` | `3.71%` | **`4.34%`** | `5.25%` | `6.61%` |
| Completed trades: Buy shortfall vs `300s` submission ask | `107` | `-1.16%` | `1.95%` | `-3.77%` | `-1.31%` | **`-0.26%`** | `+0.05%` | `+0.10%` |
| Completed trades: Buy shortfall vs **hourly VWAP** origin ask | `107` | `+0.42%` | `4.02%` | `-3.73%` | `-1.33%` | **`-0.13%`** | `+2.13%` | **`+6.07%`** |
| Completed trades: First buy fill wait (`seconds` after `t_hour + 3900`) | `107` | `1,469s` | `1,249s` | **`900s`** | **`900s`** | **`900s`** | `1,350s` | `2,700s` |

**Why Faster Execution Lowered Net Return per Trade (`+2.46%` in `P1` -> `+1.00%` in `P1b`) and Worsened Fold 3 (`-739k` -> `-1,732k`):**
1. **Asymmetric Convexity of Losses vs Capped Small Rebounds:** The fast `1h–4h` mean-reversion rebounds captured by `300s` fills average `+5.86%` gross mid-to-mid (`82.2%` gross hit rate), which barely clears a **`4.34%–4.66%`** realised spread + `2%` GE tax wall (`~+1.0%` mean net per trade). Meanwhile, during Fold 3's structural regime shifts (`2026-04-27` .. `2026-07-26`), higher `300s` fill rates (`19.2%` vs `6.7%`) put **`4.2x` more capital into inventory (`1.81x` vs `0.43x` turnover)** right into persistent multi-day drawdowns where both the downward move *and* the `~4.6%` round-trip cost wall compound!

---

## 5. Null Controls on `300s` Bars: Stronger Signal Separation, Same Cash Ceiling

| `300s` Policy Spec | Control Arm | Pooled Net P/L (`GP` / `%`) | Completed Trades (Fill `%`) | Net Hit `%` | Gross Mid Hit `%` | Hourly Sharpe | Paired `(Signal - Control)` $\Delta$ GP | Paired 168h 95% CI (`p > 0`) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **`P1b` Walk-Forward** | **`recursive_student_t` Signal** | **`-201,361` (`-0.20%`)** | `107` (`19.2%`) | `55.1%` | **`82.2%`** | `-0.110` | — | — |
| | `null_time_shuffled` (`5` reps mean ± SD) | **`-3,637,422 ± 283,503` (`-3.64%`)** | `127.2` (`25.8%`) | **`12.5%`** | `58.8%` | `-3.135` | **`+3,436,061`** | **`[-0.37M, +6.82M]` (`p = 0.0240`)** |
| | `null_sign_flipped` | **`-9,445,473` (`-9.45%`)** | `174` (`16.1%`) | `12.1%` | `34.5%` | `-3.192` | **`+9,244,112`** | **`[+3.17M, +15.34M]` (`p = 0.0025`)** |
| | `null_detrended_zero_drift` | **`0` (`0.00%`)** | `0` (`0.0%`) | — | — | `0.000` | `-201,361` | `[-3.71M, +2.58M]` (`p = 1.0000`) |
| **`P1`-Fixed Cells** | **`recursive_student_t` Signal** | **`-614,599` (`-0.61%`)** | `68` (`19.5%`) | `54.4%` | **`80.9%`** | `-0.463` | — | — |
| | `null_time_shuffled` (`5` reps mean ± SD) | **`-1,495,693 ± 295,329` (`-1.50%`)** | `75.6` (`20.5%`) | `11.1%` | `61.5%` | `-2.387` | `+881,094` | `[-2.33M, +3.20M]` (`p = 0.2864`) |
| | `null_sign_flipped` | **`-1,815,878` (`-1.82%`)** | `63` (`12.2%`) | `12.7%` | `33.3%` | `-2.864` | `+1,201,279` | `[-1.86M, +3.73M]` (`p = 0.2079`) |
| | `null_detrended_zero_drift` | **`0` (`0.00%`)** | `0` (`0.0%`) | — | — | `0.000` | `-614,599` | `[-3.90M, +1.66M]` (`p = 1.0000`) |
| **`H24h_edge0bps`** | **`recursive_student_t` Signal** | **`+483,470` (`+0.48%`)** | `135` (`22.3%`) | `54.1%` | **`81.5%`** | `+0.301` | — | — |
| | `null_time_shuffled` (`5` reps mean ± SD) | **`-4,198,328 ± 406,770` (`-4.20%`)** | `153.8` (`27.3%`) | **`12.2%`** | `57.7%` | `-3.556` | **`+4,681,798`** | **`[+1.87M, +7.76M]` (`p = 0.0020`)** |
| | `null_sign_flipped` | **`-9,513,025` (`-9.51%`)** | `211` (`18.2%`) | `12.8%` | `37.0%` | `-3.138` | **`+9,996,495`** | **`[+5.04M, +15.10M]` (`p = 0.0005`)** |
| | `null_detrended_zero_drift` | **`0` (`0.00%`)** | `0` (`0.0%`) | — | — | `0.000` | `+483,470` | `[-1.97M, +2.94M]` (`p = 0.3483`) |

---

## 6. Execution, Timing, Liquidity, Capital, & Passive-Order Sensitivities on `300s` Bars

| `300s` Sensitivity Arm | **`P1b` Walk-Forward** (`Net GP` / Fill `%` / Exp0 `%` / Sharpe) | **`P1`-Fixed Cells** (`Net GP` / Fill `%` / Exp0 `%` / Sharpe) | **`H24h_edge0bps`** (`Net GP` / Fill `%` / Exp0 `%` / Sharpe) | **`H4h_edge0bps`** (`Net GP` / Fill `%` / Exp0 `%` / Sharpe) |
|---|---|---|---|---|
| `participation_bps = 50` (`0.5%` 5m vol) | `-539,628` (`5.83%`, `29.3%`, `-0.49`) | `-976,919` (`5.54%`, `23.5%`, `-1.04`) | `+173,129` (`8.30%`, `28.6%`, `+0.18`) | `-615,362` (`5.79%`, `30.2%`, `-1.00`) |
| **`participation_bps = 200` (`2.0%` Primary)** | **`-201,361` (`19.23%`, `27.2%`, `-0.11`)** | **`-614,599` (`19.47%`, `20.0%`, `-0.46`)** | **`+483,470` (`22.31%`, `26.2%`, `+0.30`)** | **`-212,747` (`16.28%`, `28.6%`, `-0.26`)** |
| `participation_bps = 500` (`5.0%` 5m vol) | `-621,170` (`33.70%`, `26.0%`, `-0.25`) | `-716,558` (`33.90%`, `20.0%`, `-0.41`) | `-23,738` (`35.85%`, `25.3%`, `+0.01`) | `-73,993` (`27.75%`, `27.0%`, `-0.07`) |
| **Tight `1,800s` (`30m`) timeout & freshness** *(mean wait `~1,200s`)* | **`-692,980`** (`4.28%`, `43.9%`, `-0.77`) | **`-999,770`** (`3.63%`, `35.9%`, `-1.45`) | `+183,381` (`6.89%`, `41.2%`, `+0.23`, `p=.44`) | **`-858,838`** (`4.87%`, `41.8%`, `-1.27`) |
| **`0s` `300s`-bar publication delay (`ts + 300`)** *(first fill `600s`)* | **`-754,750`** (`23.12%`, `19.5%`, `-0.18`) | **`-1,219,577`** (`23.03%`, `15.1%`, `-0.73`) | **`-228,399`** (`25.29%`, `19.6%`, `-0.04`) | `-220,863` (`19.23%`, `23.1%`, `-0.16`) |
| `initial_cash_gp = 10M GP` | `-2,731` (`39.32%`, `27.2%`, `+0.02`) | `+27,561` (`39.38%`, `20.0%`, `+0.12`, `p=.48`) | `+43,387` (`40.47%`, `26.4%`, `+0.15`, `p=.44`) | `+112,564` (`43.08%`, `28.6%`, `+0.86`, `p=.19`) |
| `Lobster` (`id=379`) statutory tax-exempt | `-195,151` (`18.32%`, `25.0%`, `-0.11`) | `-601,362` (`18.39%`, `17.5%`, `-0.45`) | `+489,680` (`21.29%`, `24.5%`, `+0.31`, `p=.35`) | `-204,989` (`15.37%`, `25.0%`, `-0.25`) |
| **`passive_v3_200bps` (`volume_bounded_v3`)** | **`+149,706` (`+0.15%`, `14.8%`, `sh +0.08`, `p=.42` vs `0`, `p=.087` vs `-1.83M` shuf)** | `-496,497` (`15.0%`, `sh -0.40`) | **`+1,182,214` (`+1.18%`, `16.9%`, `sh +0.48`, `p=.16` vs `0`, `p=.011` vs `-2.02M` shuf)** | `-379,350` (`12.4%`, `sh -0.51`) |

- **Even `0s` publication lag (`600s` fill latency) and `30m` tight intraday timeouts lose money (`-693k` to `-1.22M GP`):** Eliminating slow fills or cutting the 5-minute publication delay increases fill rates (`23%–25%`) and drops zero-fill expiries as low as **`15.1%`**, yet degrades net P/L further because every extra crossed fill pays the `~4.34%–4.66%` spread + GE tax wall.
- **Passive `300s` execution (`passive_v3_200bps`) improves materially over `3600s` passive execution (`+150k GP` vs `-976k GP` WF), yet remains economically negligible (`+0.15%` to `+1.18%` over 9 months, `p >= 0.16` vs cash):** Resting passive quotes on `300s` bars avoids crossing the spread on filled trades, but still suffers adverse fill selection (missing rebounds that never dip back to `bid_t` while filling 100% of continued selloffs) and still pays the mandatory `2.00%` GE seller tax on every exit.

---

## 7. Overall Synthesis for Phase One (`E1` -> `E2` -> `E3` -> `P1` -> `P1b`)

1. **Statistical Forecasting Question (`E1`–`E3`): Answered Positively (Narrowly).** Closed-loop `recursive_student_t` (including parsimonious `13`-col `e3_price_only`) genuinely improves multi-horizon path calibration (`Gate B` variogram `-6.40%`, `p_holm = 0.0030`) and directional gross return prediction (`81%–96%` gross mid hit rate; `p = 0.0020–0.0240` vs time-shuffled null controls).
2. **Economic Monetisation & Execution-Latency Question (`P1` -> `P1b`): Answered Negatively & Diagnosed Completely.**
   - `P1` (`3600s` bars) showed hourly crossed execution loses `-71,792 GP` with `79.1%` ceiling expiries.
   - `P1b` (`300s` bars) proved that cutting observation-to-fill latency from `7,200s` to `900s` **solves the fill & ceiling-expiry bottleneck (`6.7%` -> `19.2%` unit fill rate; `79.1%` -> `20.0%–27.2%` zero-fill expiry)**, **yet still fails to clear zero net profit (`-201,361 GP` WF; `-614,599 GP` `P1`-fixed; `+483,470 GP`, `p = 0.349` on `H24h_edge0bps`)** because the hourly origin's `0.79%` spread was a 60-minute VWAP non-synchronicity illusion and the true contemporaneous `300s` spread (`~2.0%–2.3%`) plus `2.00%` GE tax (`~4.35%–4.66%` round-trip wall) exceeds `recursive_student_t`'s `1h–24h` conditional drift on crossed directional trades.
   - Any viable future OSRS trading architecture cannot rely on crossing spreads from `1h` mean-reversion forecasts; it would require either **true `5m`-origin spread-making / passive market-making models** explicitly predicting queue fill probability + spread capture, or **multi-day (`>= 72h–168h`) regime/update-driven catalysts** whose amplitude substantially exceeds the `~4.4%` GE cost wall.
3. **Clean Provenance & Governance:** Executed at clean commit `47ba2a7a76b2118ca58430fdd7d62c130db2289a` (`git_dirty: false`), `0` `E4` slots consumed (`4 / 72` untouched), and sealed holdout `1785024300` completely untouched (`holdout_touched: false`).
