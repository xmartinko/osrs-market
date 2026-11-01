# Phase One `P1` Economic Backtest: Converting `recursive_student_t` into a Sized OSRS Grand Exchange Policy

**Last updated:** `2026-11-01T13:26:00-08:00`  
**Status:** **`COMPLETED & CLEAN-COMMIT REPRODUCED (`git_dirty: false`) — HONEST NEGATIVE ECONOMIC RESULT`**  
**Branch:** `research/osrs-phase-one-2026-11-01`  
**Preregistration manifest (committed at `ab9a736` BEFORE validation P/L):** [`p1_backtest_protocol.json`](p1_backtest_protocol.json) (`SHA-256: 88d12b89967c7ec4c56f340f0a26e2e9f75411ae7099839d1fd7d1b1d89f4ad0`)  
**Clean execution commit:** `e34821fd6dd494e7cbcc455ca8061a0048298c5f` (`git_dirty: false`; bit-for-bit identical to initial `ab9a736` -> `96d33eb` run — see Section 9)  
**Machine-readable results:** [`p1_backtest_results.json`](p1_backtest_results.json) (`SHA-256: b66149924ab94adfcbe912c6aaf1b341b3ac1a69fddf12c87b4fc272ad630298`)  
**Runner & test suite (`81 / 81` passing):** [`ml/src/osrs_ml/probabilistic_backtest.py`](../../../ml/src/osrs_ml/probabilistic_backtest.py), [`ml/tests/test_probabilistic_backtest.py`](../../../ml/tests/test_probabilistic_backtest.py)  
**Full run archive (ledgers & quantile caches outside Git):** `/home/martin/osrs-data/phase-one-20261101/runs/p1_backtest_recursive_student_t/` (VPS) & `/home/xmart/osrs-research/runs/p1_backtest_recursive_student_t/` (Desktop WSL)  
**Scope & Governance:** Development validation backtest across the three `E2/E3` validation folds (`2025-10-29` .. `2026-07-26`, `6,407` hours, `74` items). **`0` `E4` slots consumed** (`68 / 72` neural fit budget unchanged; `4 / 72` `E4` reserve untouched). **Sealed holdout (`>= 1785024300`) strictly closed (`holdout_touched: false`).** Executed on Desktop WSL2 **RTX 5080** (`1,037.3s` clean cold-start wall time; ThinkPad **RTX 3070** `root@thinkpad` online & available opportunistically).

---

## Executive Verdict

**`CRPS` and joint variogram calibration do not translate into statistically significant net Grand Exchange trading profit on the 1-hour panel.**

1. **Primary Walk-Forward Training-Selected Policy (`100M GP`, `8` GE slots, `200 bps` = `2%` directional volume cap, crossed spread + `10 bps/side` slippage + `2.00%` GE tax):**
   - Training-only selection on each fold's 21-day (`504h`) pre-validation inner window chose `H4h_edge50bps` (Fold 1), `H24h_edge50bps` (Fold 2), and `H24h_edge25bps` (Fold 3).
   - Across the pooled `270`-day (`6,407h`) validation window, the policy generated **`+830,607 GP` in gross mid-to-mid profit** (**`73.68%` gross mid hit rate**, mean gross trade return **`+7.54%`** across `19` completed round-trips), **but paid `-902,399 GP` in execution friction** (`-444,524 GP` both-side half-spread + `-42,982 GP` explicit slippage + `-414,893 GP` `2.00%` GE seller tax), finishing at **`-71,792 GP` net (`-0.0718%` return on capital; annualised hourly Sharpe `-0.086`, daily Sharpe `-0.085`, max drawdown `1.26%`, 168h block-bootstrap 95% CI `[-2,084,160 GP, +1,482,213 GP]`, one-sided $p = 1.0000$)**.
2. **All `6 / 6` Preregistered Grid Cells Fail Statistical Significance Against Cash (`0 GP`):**
   - **Every `H = 4h` cell (`0, 25, 50 bps` edge) loses money net of costs** (`-203,244 GP` to `-422,992 GP`, Sharpe `-0.34` to `-0.75`) despite **`83.3%–90.9%` gross mid hit rates** and **`66.7%–72.7%` net trade hit rates**.
   - **Every `H = 24h` cell (`0, 25, 50 bps` edge) finishes slightly positive in point estimate over 270 days** (`+1,184,045 GP = +1.18%` at `0 bps`, `+641,289 GP = +0.64%` at `25 bps` [pooled inner-training winner], `+589,057 GP = +0.59%` at `50 bps`), **but none clears 168h block-bootstrap significance against `0 GP`** ($p = 0.1224, 0.2944, 0.3058$), **all three lose money in Fold 3** (`-350,481 GP` to `-739,298 GP`), and **`66.5%` to `77.2%` of gross mid profit is consumed by spread + slippage + GE tax**.
3. **Null Controls Prove Real Signal vs Crushing Cost & Latency Wall:**
   - Driving the **exact same policy, sizing, and executor** with time-shuffled or sign-flipped signals produces catastrophic losses: on `H24h_edge0bps`, `null_time_shuffled` (`5` replicates) loses **`-2,353,053 GP` (`-2.35%`, `11.0%` net hit rate, `45.5%` gross hit rate, Sharpe `-3.65`; paired `signal - shuffled` = `+3,537,098 GP`, $p = 0.0025$)** and `null_sign_flipped` loses **`-7,704,484 GP` (`-7.70%`, Sharpe `-4.58`; paired $p = 0.0020$)**, while `null_detrended_zero_drift` sits in cash (`0` signals, `0 GP`, paired $p = 0.1314$).
   - Thus `recursive_student_t` captures **genuine conditional mean-reversion directionality** (`74%–91%` gross mid hit rate vs `~46%` random), **yet two microstructural walls prevent monetizing it on hourly bars:**
     1. **Winner's Curse / Ceiling Expiry During `h = 1` Latency:** Because hourly bucket `[t, t+3600)` publishes at `t + 3900s` (`+300s` execution latency -> earliest fill bucket `h = 2` at `t + 7200s`), **`79.1%` (`72 / 91`) of walk-forward buy orders (`75.4%` = `147 / 195` on `H24h_edge0bps`) expire unfilled** because the ask price **already snapped up by a median of `+5.64%` (`p90 = +12.22%`) above the origin ceiling before `h = 2`**.
     2. **Spread Mean-Reversion Between Decision and Fill (`2.64%` Realised vs `0.99%` Modelled):** Entry signals fire when origin spreads are temporarily compressed (median **`0.79%`** WF / **`0.99%`** `H24h_edge0bps`). By the time fills execute in `h >= 2` and `h + H`, fill-bucket spreads revert to **`2.39%`**, pushing **realised round-trip spread + slippage to `2.64%` median (`2.94%` mean)** and **total realised round-trip cost incl. `2%` GE tax to `4.54%` median (`4.76%` mean)** — nearly **`1.7–2.7x`** the spread observed at signal origin.

---

## 1. Exact Audit of Reused Repository Cost & Execution Machinery (Rule 1)

No parallel cost or fill simulator was written. Every simulation invokes [`osrs_ml.costs`](../../../ml/src/osrs_ml/costs.py), [`osrs_ml.execution`](../../../ml/src/osrs_ml/execution.py), and [`osrs_ml.backtest`](../../../ml/src/osrs_ml/backtest.py) directly:

1. **GE Seller Tax (`osrs_ml.costs.TaxPolicy` / `DEFAULT_TAX` / `sale_proceeds`):**
   - `rate_bps = 200` (**`2.00%`** seller tax under post-2025-05-29 Jagex GE rules), `exempt_through_gp = 49` (`<= 49 GP` pays `0 GP`; `50 GP` pays `1 GP`), `cap_gp = 5_000_000` (`5M GP` cap **per single unit**).
   - **Exact integer per-unit floor:** `tax_per_item(sale_gp) = min((sale_gp * 200) // 10_000, 5_000_000)` is floored per unit before multiplying by `quantity`. Primary runs use conservative `DEFAULT_TAX` (`exempt_item_ids=()`), with `exempt_item_ids=(379,)` (`Lobster`) tested in Section 8.
2. **Spread, Slippage, and Sub-GP Lot Allocation (`osrs_ml.costs.price_target` & `integer_lots`, `price_model="integer_lots_v2"`):**
   - Exact `1 / 10,000` GP fixed-point arithmetic (`target = price_gp * 10_000 +/- (price_gp * adverse_bps + ticks * 10_000)`), rejecting `< 1 GP` fills with `UntradeablePrice`. `integer_lots` deterministically splits `quantity` across adjacent integer GP prices so multi-unit fills pay exact fractional bps slippage without `1 GP` rounding distortion on runes/consumables.
   - Positive `float64` `hourly.parquet` side prices (`avg_high_price`, `avg_low_price`) are converted via `max(1, round(price))` to `Int64` as required by `price_target`; Section 7 verifies that continuous vs integer fill-bucket spreads differ by `< 0.02%` (`2.37%` vs `2.39%` median).
3. **Order Lifecycle, Whole-Bucket Latency, 4-Hour GE Buy Limits, and Volume-Bounded Fills (`osrs_ml.backtest.simulate`):**
   - **Primary Execution (`p1_crossed_moderate_200bps`):** `passive_prices=False, fill_model="bucket_proxy_v1", price_model="integer_lots_v2", participation_bps=200, slippage_bps=10, latency_seconds=300, max_freshness_seconds=7500, buy_timeout_seconds=7500, terminal_haircut_bps=100, allow_unknown_metadata=False`.
   - **Buys** cross to pay future post-latency bucket's **`avg_high_price` (ask) `+ 10 bps`**, guarded by `buy_ceiling = ceil(ask_t * 1.0010)` (offers do not chase runaway asks above ceiling and expire after `7,500s`). **Sells** (submitted once `now >= first_fill + H * 3600`) cross to receive future post-latency bucket's **`avg_low_price` (bid) `- 10 bps` minus `2.00%` GE tax**.
   - **Whole-Bucket Causal Latency (`origin + 3,900s`):** Bucket `[t, t+3600)` publishes at `available_at = t + 3900`. Because `backtest.py` requires `row["timestamp"] >= submitted + 300`, bucket `h = 1` (`timestamp = t + 3600 < t + 4200`) **never fills**; earliest executable fill is `h = 2` (`timestamp = t + 7200`).
   - **4-Hour (`14,400s`) GE Buy Limit & Volume Cap:** Cumulative buys per item in each `14,400s` window anchored on `first_fill_ts` are capped at `items.parquet` `buy_limit` (`73 / 74` items known; `1` unknown item blocked), and each hourly bucket fills at most `side_price_volume * participation_bps // 10_000` (`2.0%` of directional hourly volume). Unsold end-of-fold inventory is marked at `bid * (1 - 10 bps) * (1 - 100 bps haircut) - 2% GE tax`.

---

## 2. Empirical Cost Wall on the Three Validation Folds vs Reference Context (Rule 5)

Measured directly across all `456,611` causal usable item-hours (`high_price_volume > 0`, `low_price_volume > 0`, `ask >= bid >= 1`) in `2025-10-29` .. `2026-07-26`:

| Microstructure / Cost-Wall Quantity | Martin's Full-Panel Context | Validation Folds (`2025-10-29`..`2026-07-26`) | Notes |
|---|---:|---:|---|
| Quoted spread `p50` (continuous / integer) | `1.79%` | **`1.96%` / `1.93%`** | `p25 = 1.27%`, `p75 = 2.66%`, mean `2.82%` (`456,611` item-hours) |
| Quoted spread `p90` (continuous / integer) | `3.71%` | **`3.89%` / `3.78%`** | Validation period is slightly wider than year-1 training |
| Median `|24h|` midpoint move (`p50` / `p90`) | `1.15%` | **`1.12%` / `4.75%`** | `|4h|` midpoint move: `p50 = 0.68%`, `p75 = 1.44%`, `p90 = 2.87%` |
| Crossed round-trip cost wall (`spread + 2% tax + 20 bps slip`) | `~3.8%` | **`4.34%` median** (`p25 = 3.62%`, `p90 = 6.90%`) | `~3.96%` before `20 bps` explicit slippage |
| `24h` item-hours clearing `2.00%` GE tax alone | `~32%` *(two-sided)* | **`14.37%` long-only** (`~28.7%` two-sided) | Grand Exchange is strictly long-only (no short selling) |
| `24h` item-hours clearing `spread + 2% GE tax` | `12.4%` *(two-sided)* | **`4.78%` long-only** (`~9.6%` two-sided) | **`3.64%` long-only** after adding `20 bps` slippage |
| `4h` item-hours clearing `spread + 2% GE tax + 20 bps slip` | — | **`0.89%` long-only** | Fewer than `1 in 110` 4-hour item windows clear the full crossed wall |

---

## 3. Preregistered Policy & Causal Signal Funnel (Rule 2)

At every causally usable origin (`557,586` inner+outer origins across the 3 folds; `0` lookahead on `complete_24h`), `256` paths × `3` seeds (`S = 768` pooled paths from frozen `e2_recursive_student_t_f{1,2,3}_s{11,23,47}`) yield cumulative log-return quantiles $q_{\tau, h}$ ($\tau \in \{.10, .25, .50, .75, .90\}$, $h \in \{1, 4, 24\}$):
- Estimated post-latency entry ask $P_{\text{buy}}^{\text{est}} = \lceil \text{ask}_t \exp(\max(0, q_{50, 1})) \cdot 1.0010 \rceil$; exit bid $P_{\text{sell}}^{\text{est}}(\tau, H) = \max(1, \lfloor \text{bid}_t \exp(q_{\tau, H}) \cdot 0.9990 \rfloor)$.
- Expected net edge $e_{\text{net}}(i, t; H) = \frac{1}{5}\sum_{\tau} \text{costs.net\_return}(P_{\text{buy}}^{\text{est}}, P_{\text{sell}}^{\text{est}}(\tau, H), \text{DEFAULT\_TAX})$.
- **Entry gates:** $e_{\text{net}} > \theta_{\text{edge}}$, median net return $> 0$, $-0.05 < q_{10, 1} \le 0.005$ (`h=1` crash & ceiling-fillability guard), cross-horizon sign alignment ($q_{50, 24} \ge 0$ for $H=4$; $q_{50, 4} \ge -0.01$ for $H=24$), and end-of-window buffer `available_at < window_end - (H + 3)h`. Ranked by `e_net / max(IQR_H, 0.005)`, dynamically sized in `[100, 1250] bps` of `100M GP` across `8` GE slots.

Because `recursive_student_t` is well-calibrated (`89%` 90%-interval coverage in `E2`), **its own quantiles reject `99.95%` of item-hours as negative-expectation after spread + GE tax**:
- Fold 1 (`152,641` origins, `H4h_edge50bps`): `55` (`0.036%`) pass `median_net > 0` -> `19` pass `e_net > 50 bps` -> **`15` signals** (`13` submitted, `12` expired unfilled, `1` completed round-trip).
- Fold 2 (`150,541` origins, `H24h_edge50bps`): `63` (`0.042%`) pass `median_net > 0` -> `46` pass `e_net > 50 bps` -> **`42` signals** (`32` submitted, `24` expired unfilled, `8` completed round-trips).
- Fold 3 (`147,944` origins, `H24h_edge25bps`): `87` (`0.059%`) pass `median_net > 0` -> `71` pass `e_net > 25 bps` -> **`68` signals** (`46` submitted, `36` expired unfilled, `10` completed round-trips).

---

## 4. Preregistered `2 × 3 = 6`-Cell Grid: Inner-Training Tuning vs Full Outer Validation (Rule 6)

### 4.1 Inner 21-Day (`504h`) Pre-Validation Training Selection (Zero Validation Peek)

| Grid Cell (`H`, `min_net_edge`) | Inner Fold 1 Net GP | Inner Fold 2 Net GP | Inner Fold 3 Net GP | Pooled Inner Net GP (`%`) | Inner Signals / Sub / Exp / Trades | Inner Net / Gross Hit `%` | Inner Turnover | Inner Hourly Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `H4h_edge0bps` | `+5,394` | `0` | `0` | `+5,394` (`+0.005%`) | `18 / 13 / 10 / 3` | `66.7% / 66.7%` | `0.0053x` | `+0.912` |
| `H4h_edge25bps` | `+5,394` | `0` | `0` | `+5,394` (`+0.005%`) | `17 / 12 / 9 / 3` | `66.7% / 66.7%` | `0.0053x` | `+0.912` |
| `H4h_edge50bps` *(Fold 1 pick)* | **`+5,394`** | `0` | `0` | `+5,394` (`+0.005%`) | `14 / 9 / 6 / 3` | `66.7% / 66.7%` | `0.0053x` | `+0.912` |
| `H24h_edge0bps` *(Active `>=10` ref)* | `-54,228` | `+11,575` | `+240,727` | `+198,074` (`+0.198%`) | `68 / 52 / 41 / 11` | `36.4% / 72.7%` | `0.2153x` | `+0.827` |
| **`H24h_edge25bps`** *(Fold 3 & Pooled pick)* | `+2,201` | `+11,575` | **`+279,626`** | **`+293,402` (`+0.293%`)** | `63 / 48 / 39 / 9` | `44.4% / 88.9%` | `0.1840x` | **`+1.247`** |
| `H24h_edge50bps` *(Fold 2 pick)* | `+2,201` | **`+11,575`** | `0` | `+13,776` (`+0.014%`) | `53 / 39 / 31 / 8` | `37.5% / 87.5%` | `0.0984x` | `+0.078` |

*(Per-fold tie-breaker `max net_gp -> lower turnover -> larger H -> higher min_edge_bps` selected `H4h_edge50bps` on Fold 1, `H24h_edge50bps` on Fold 2, and `H24h_edge25bps` on Fold 3.)*

### 4.2 Complete Outer-Validation Results Across ALL `6` Grid Cells + Walk-Forward Policy (`270d`, `100M GP`)

Every preregistered cell is reported below without post-hoc filtering:

| Policy / Grid Cell | Fold 1 Net GP | Fold 2 Net GP | Fold 3 Net GP | Pooled Net P/L (`%` Cap) | Gross Mid P/L -> Spread+Slip+Tax Drag | Signals / Sub / Exp / **Trades** (Fill `%`) | Turnover (`2-way`) | Hit Rate (Net / Gross Mid) | Sharpe (`Trade` / `Hourly` / `Daily`) | Max DD (`GP` / `%`) | 168h Bootstrap 95% CI (`p > 0`) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Walk-Forward Selected** *(Primary)* | `+402,555` | `+264,951` | `-739,298` | **`-71,792` (`-0.07%`)** | `+830,607` -> **`-902,399`** | `125 / 91 / 72 /` **`19`** (`6.72%`) | `0.426x` | `63.2% / 73.7%` | `+0.225 / -0.086 / -0.085` | `1.27M` (`1.26%`) | `[-2.08M, +1.48M]` (`p = 1.0000`) |
| `H4h_edge0bps` | `+512,538` | `+140,646` | `-856,428` | **`-203,244` (`-0.20%`)** | `+513,509` -> `-716,753` | `82 / 67 / 53 /` **`14`** (`6.32%`) | `0.265x` | `71.4% / 85.7%` | `+0.313 / -0.343 / -0.246` | `1.03M` (`1.02%`) | `[-2.31M, +1.37M]` (`p = 1.0000`) |
| `H4h_edge25bps` | `+515,663` | `+140,646` | `-874,099` | **`-217,790` (`-0.22%`)** | `+390,320` -> `-608,110` | `63 / 52 / 41 /` **`11`** (`6.25%`) | `0.210x` | `72.7% / 90.9%` | `+0.355 / -0.374 / -0.264` | `0.96M` (`0.95%`) | `[-2.35M, +1.34M]` (`p = 1.0000`) |
| `H4h_edge50bps` | `+402,555` | `+48,552` | `-874,099` | **`-422,992` (`-0.42%`)** | `+73,288` -> `-496,280` | `43 / 38 / 32 /` **`6`** (`4.33%`) | `0.166x` | `66.7% / 83.3%` | `+0.055 / -0.746 / -0.524` | `0.95M` (`0.95%`) | `[-2.54M, +1.01M]` (`p = 1.0000`) |
| `H24h_edge0bps` *(Active ref)* | `+1,094,774` | `+439,752` | `-350,481` | **`+1,184,045` (`+1.18%`)** | `+3,535,676` -> **`-2,351,631`** | `284 / 195 / 147 /` **`48`** (`8.91%`) | `1.055x` | `56.3% / 75.0%` | `+0.177 / +0.478 / +1.286` | `2.75M` (`2.67%`) | `[-0.60M, +3.32M]` (`p = 0.1224`) |
| `H24h_edge25bps` *(Pooled inner pick)* | `+1,090,768` | `+289,819` | `-739,298` | **`+641,289` (`+0.64%`)** | `+2,815,386` -> `-2,174,097` | `258 / 181 / 138 /` **`43`** (`7.70%`) | `0.951x` | `53.5% / 74.4%` | `+0.210 / +0.264 / +0.620` | `2.77M` (`2.70%`) | `[-1.78M, +3.06M]` (`p = 0.2944`) |
| `H24h_edge50bps` | `+1,014,051` | `+264,951` | `-689,945` | **`+589,057` (`+0.59%`)** | `+2,429,967` -> `-1,840,910` | `229 / 158 / 122 /` **`36`** (`7.61%`) | `0.804x` | `55.6% / 80.6%` | `+0.256 / +0.245 / +0.576` | `2.79M` (`2.72%`) | `[-1.75M, +2.97M]` (`p = 0.3058`) |

### 4.3 Gross-to-Net Cost Decomposition Bridge (Completed Round-Trips)

| Policy | Completed Trades | Gross Mid-to-Mid P/L (`GP`) | Pure Both-Side Half-Spread (`GP`) | Explicit `10 bps/side` Slippage (`GP`) | `2.00%` GE Seller Tax (`GP`) | Net Realised P/L (`GP`) | Share of Gross Alpha Eaten by Costs |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Walk-Forward Selected** | `19` | **`+830,607`** | `-444,524` | `-42,982` | `-414,893` | **`-71,792`** | **`108.6%`** |
| `H4h_edge0bps` | `14` | `+513,509` | `-443,502` | `-26,668` | `-246,583` | `-203,244` | `139.6%` |
| `H24h_edge0bps` | `48` | **`+3,535,676`** | `-1,219,142` | `-106,468` | `-1,026,021` | **`+1,184,045`** | **`66.5%`** |
| `H24h_edge25bps` *(Pooled inner)* | `43` | `+2,815,386` | `-1,154,618` | `-95,922` | `-923,557` | `+641,289` | `77.2%` |

*(Zero positions remained open at the end of any fold across all 6 cells, so `realized_gp == net_gp` everywhere.)*

---

## 5. Null Controls: Signal Attribution vs Sample & Execution Artifacts (Rule 3)

Every null control passes transformed quantiles into the **identical** `build_policy_signals` + `backtest.simulate` pipeline:

| Policy Spec | Control Arm | Pooled Net P/L (`GP` / `%`) | Completed Trades | Net Hit `%` | Gross Mid Hit `%` | Hourly Sharpe | Paired `(Signal - Control)` $\Delta$ GP | Paired 168h 95% CI (`p > 0`) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **Walk-Forward Selected** | **`recursive_student_t` Signal** | **`-71,792` (`-0.07%`)** | `19` | `63.2%` | `73.7%` | `-0.086` | — | — |
| | `null_time_shuffled` (`5` reps mean ± SD) | **`-839,200 ± 352,833` (`-0.84%`)** *(range `[-1.27M, -0.44M]`)* | `41.8` | `9.4%` | `46.5%` | `-2.377` | **`+767,408`** | `[-1.30M, +2.35M]` (`p = 0.1989`) |
| | `null_sign_flipped` | **`-1,710,267` (`-1.71%`)** | `54` | `7.4%` | `25.9%` | `-3.655` | **`+1,638,475`** | `[-0.43M, +3.65M]` (`p = 0.0555`) |
| | `null_detrended_zero_drift` | **`0` (`0.00%`)** | `0` | — | — | `0.000` | **`-71,792`** | `[-2.11M, +1.47M]` (`p = 1.0000`) |
| **`H24h_edge0bps`** *(Active `H=24h`)* | **`recursive_student_t` Signal** | **`+1,184,045` (`+1.18%`)** | `48` | `56.3%` | `75.0%` | `+0.478` | — | — |
| | `null_time_shuffled` (`5` reps mean ± SD) | **`-2,353,053 ± 372,288` (`-2.35%`)** *(range `[-2.84M, -1.90M]`)* | `83.4` | `11.0%` | `45.5%` | `-3.650` | **`+3,537,098`** | **`[+1.51M, +5.87M]` (`p = 0.0025`)** |
| | `null_sign_flipped` | **`-7,704,484` (`-7.70%`)** | `173` | `13.3%` | `34.7%` | `-4.575` | **`+8,888,529`** | **`[+4.28M, +14.21M]` (`p = 0.0020`)** |
| | `null_detrended_zero_drift` | **`0` (`0.00%`)** | `0` | — | — | `0.000` | `+1,184,045` | `[-0.70M, +3.22M]` (`p = 0.1314`) |
| **`H4h_edge0bps`** *(Active `H=4h`)* | **`recursive_student_t` Signal** | **`-203,244` (`-0.20%`)** | `14` | `71.4%` | `85.7%` | `-0.343` | — | — |
| | `null_time_shuffled` (`5` reps mean ± SD) | **`-449,272 ± 193,605` (`-0.45%`)** *(range `[-0.77M, -0.25M]`)* | `26.8` | `8.0%` | `52.9%` | `-2.183` | `+246,028` | `[-2.00M, +1.84M]` (`p = 0.4403`) |
| | `null_sign_flipped` | **`-939,874` (`-0.94%`)** | `31` | `0.0%` | `19.4%` | `-3.980` | `+736,630` | `[-1.30M, +2.47M]` (`p = 0.2144`) |
| | `null_detrended_zero_drift` | **`0` (`0.00%`)** | `0` | — | — | `0.000` | `-203,244` | `[-2.44M, +1.43M]` (`p = 1.0000`) |

**Null-Control Interpretation:** Random timing (`null_time_shuffled`) yields an `~8%–11%` net trade hit rate (matching the raw unconditional market cost-wall survival rate!) and loses `-0.84M` to `-2.35M GP` (`Sharpe -2.38` to `-3.65`). Inverting the forecast (`null_sign_flipped`) loses `-7.70M GP` (`p = 0.0020`). The neural forecast genuinely shifts gross mid hit rates from `~46%` to `74%–86%` (`p = 0.0025` on `H24h`), yet **cannot statistically beat holding cash (`null_detrended_zero_drift = 0 GP`, $p \ge 0.1314$)** after paying Grand Exchange costs.

---

## 6. Distribution of Realised Spread vs Modelled Spread & Latency Adverse Selection (Rule 4)

### 6.1 Primary Walk-Forward Policy (`19` Completed Trades, `91` Submitted Orders, `72` Unfilled Expiries)

| Spread / Cost / Shortfall Distribution (`%`) | `count` | `mean` | `std` | `p10` | `p25` | **`p50` (Median)** | `p75` | `p90` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Submitted buy-order quoted spread at decision origin | `91` | `1.08%` | `1.17%` | `0.00%` | `0.36%` | **`0.67%`** | `1.57%` | `2.41%` |
| **Expired-unfilled `h>=2` adverse ask jump vs origin ask** | **`72`** | **`+6.34%`** | `5.54%` | `+0.88%` | `+3.24%` | **`+5.64%`** | `+8.49%` | **`+12.22%`** |
| Fill-bucket quoted spread (`continuous` `hourly.parquet`) | `148` | `2.56%` | `1.89%` | `0.60%` | `1.44%` | **`2.37%`** | `3.31%` | `4.17%` |
| Fill-bucket quoted spread (`integer` rounded `Int64`) | `148` | `2.51%` | `1.72%` | `0.64%` | `1.43%` | **`2.39%`** | `3.31%` | `4.14%` |
| Completed trades: **Quoted spread at decision origin** | `19` | `1.31%` | `1.48%` | `0.35%` | `0.49%` | **`0.79%`** | `1.69%` | `2.32%` |
| Completed trades: **Modelled RT spread + `20 bps` slip at origin** | `19` | `1.51%` | `1.48%` | `0.55%` | `0.69%` | **`0.99%`** | `1.89%` | `2.52%` |
| Completed trades: **Realised RT spread + slippage paid** | `19` | **`2.94%`** | `1.53%` | `1.77%` | `2.04%` | **`2.64%`** | `3.37%` | **`3.77%`** |
| Completed trades: **Realised total RT cost incl. `2%` GE tax** | `19` | **`4.76%`** | `1.54%` | `3.50%` | `3.82%` | **`4.54%`** | `5.17%` | **`5.69%`** |
| Completed trades: Buy latency shortfall `(buy_vwap - ask_t) / mid_t` | `19` | `-1.91%` | `3.24%` | `-6.40%` | `-1.56%` | **`-0.23%`** | `+0.03%` | `+0.10%` |
| Completed trades: Sell latency shortfall `(bid_sub - sell_vwap) / mid` | `19` | `-0.56%` | `1.92%` | `-3.14%` | `-2.02%` | **`-0.26%`** | `+0.33%` | `+1.93%` |

### 6.2 Active `H24h_edge0bps` Reference (`48` Completed Trades, `195` Submitted Orders, `147` Unfilled Expiries)

| Spread / Cost / Shortfall Distribution (`%`) | `count` | `mean` | `std` | `p10` | `p25` | **`p50` (Median)** | `p75` | `p90` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Submitted buy-order quoted spread at decision origin | `195` | `1.23%` | `1.24%` | `0.00%` | `0.42%` | **`0.88%`** | `1.73%` | `2.86%` |
| **Expired-unfilled `h>=2` adverse ask jump vs origin ask** | **`147`** | **`+5.52%`** | `5.13%` | `+0.72%` | `+2.53%` | **`+5.28%`** | `+8.20%` | **`+10.62%`** |
| Fill-bucket quoted spread (`continuous` / `integer`) | `344` | `2.56% / 2.55%` | `1.89% / 1.82%` | `0.81% / 0.84%` | `1.50% / 1.52%` | **`2.34% / 2.35%`** | `3.11% / 3.11%` | `4.14% / 4.08%` |
| Completed trades: **Modelled RT spread + `20 bps` slip at origin** | `48` | `1.57%` | `1.46%` | `0.35%` | `0.69%` | **`1.19%`** | `1.98%` | `2.78%` |
| Completed trades: **Realised RT spread + slippage paid** | `48` | **`2.77%`** | `1.30%` | `1.56%` | `1.91%` | **`2.55%`** | `3.13%` | **`3.96%`** |
| Completed trades: **Realised total RT cost incl. `2%` GE tax** | `48` | **`4.60%`** | `1.27%` | `3.46%` | `3.75%` | **`4.43%`** | `4.95%` | **`5.64%`** |

**Why Realised Spread (`2.64%` WF / `2.55%` `H24h`) Exceeds Modelled Spread (`0.99%` / `1.19%`) by `+1.36` to `+1.65` Percentage Points:**
1. **Spread-Compression Selection Bias at Entry:** Conditioning on high expected net return selects origin hours where the quoted spread happens to be unusually tight (`0.67%–0.88%` median vs `1.96%` market median), often because ask dipped temporarily toward bid.
2. **Spread Reversion by Fill Time (`h >= 2` and `h + H`):** Over the `>= 1h05m` causal delay before buy fill and the `4h`/`24h` holding period before sell fill, the bid-ask spread reverts to `2.35%–2.39%`, so the trader pays a normal/wide half-spread on exit (and on delayed entry) rather than the compressed origin spread.
3. **Fast-Rebound Truncation (`75%–79%` Ceiling Expiry):** Whenever the predicted mean-reversion rebound occurs immediately inside `h = 1` (`+5.64%` median ask jump), the causal trader cannot get filled at `h = 2` without chasing (`buy_expired_unfilled`), selectively filtering out the cleanest fast winners and leaving filled trades on slower trajectories!

---

## 7. Liquidity, Capital, Statutory Exemption, & Passive Limit-Order Sensitivities

| Sensitivity Arm | **Walk-Forward Selected** (`Net GP` / `%` / Fill `%` / Sharpe) | **`H24h_edge0bps`** (`Net GP` / `%` / Fill `%` / Sharpe) | **`H4h_edge0bps`** (`Net GP` / `%` / Fill `%` / Sharpe) |
|---|---|---|---|
| `participation_bps = 50` (`0.5%` vol cap) | `-209,707 GP` (`-0.21%`, fill `2.02%`, `sh -0.35`) | `+408,081 GP` (`+0.41%`, fill `3.45%`, `sh +0.34`) | `-254,706 GP` (`-0.25%`, fill `2.21%`, `sh -0.76`) |
| **`participation_bps = 200` (`2.0%` Primary)** | **`-71,792 GP` (`-0.07%`, fill `6.72%`, `sh -0.09`)** | **`+1,184,045 GP` (`+1.18%`, fill `8.91%`, `sh +0.48`)** | **`-203,244 GP` (`-0.20%`, fill `6.32%`, `sh -0.34`)** |
| `participation_bps = 500` (`5.0%` vol cap) | `+119,037 GP` (`+0.12%`, fill `13.28%`, `sh +0.13`) | `+1,318,902 GP` (`+1.32%`, fill `13.99%`, `sh +0.50`) | `-34,665 GP` (`-0.03%`, fill `10.28%`, `sh -0.05`) |
| `initial_cash_gp = 10M GP` (`DEFAULT_PORTFOLIO`) | `+114,058 GP` (`+1.14%`, fill `15.66%`, `sh +0.70`) | `+212,397 GP` (`+2.12%`, fill `15.42%`, `sh +0.69`) | `+44,354 GP` (`+0.44%`, fill `17.89%`, `sh +0.43`) |
| `Lobster` (`id=379`) statutory tax-exempt | `-65,438 GP` (`-0.07%`, `23` tr, `sh -0.08`) | `+1,179,919 GP` (`+1.18%`, `53` tr, `sh +0.48`) | `-199,224 GP` (`-0.20%`, `18` tr, `sh -0.34`) |
| **`passive_v3_200bps` (`volume_bounded_v3`)** | **`-976,124 GP` (`-0.98%`, `28` tr, `sh -0.86`)** *(shuffled `-667k`, `p = 1.00`)* | **`+369,817 GP` (`+0.37%`, `62` tr, `sh +0.15`)** *(shuffled `-1.75M`, `p = 0.0585`)* | **`-665,823 GP` (`-0.67%`, `19` tr, `sh -0.69`)** *(shuffled `-373k`, `p = 1.00`)* |

- **Why passive limit orders (`passive_v3_200bps`) underperform crossed execution on directional rebound signals:** Resting a passive buy at `avg_low_price` when `recursive_student_t` forecasts an immediate rebound intensifies adverse fill selection — the passive bid only fills if the item continues falling *through* the bid in `h >= 2` instead of rebounding.
- **Why `10M GP` capital shows higher `%` return (`+1.14%` WF / `+2.12%` `H24h_edge0bps` over 270 days):** Smaller order sizes (`<= 1.25M GP/slot`) suffer less 4-hour GE `buy_limit` truncation (`15.7%` vs `6.7%` unit fill rate), **yet `+114k` to `+212k GP` over 9 months (`~420 GP` to `~785 GP` per day!) is economically trivial.**

---

## 8. Implications for Phase One & Follow-Up Execution-Resolution Test (`P1b`)

1. **Statistical Forecast Validity Confirmed, Hourly Trading Alpha Rejected:** `recursive_student_t` is a genuine statistical improvement on multi-horizon trajectory calibration (`Gate B` variogram `-6.40%`) and directional gross return forecasting (`p = 0.0025` vs time-shuffled null), **but an hourly-bar Grand Exchange strategy cannot monetize `~1.12%` median 24h moves across a `4.34%–4.54%` realised round-trip spread+tax wall and a `>= 1h05m` (`~4,200s`) whole-bucket latency gap.**
2. **Latency vs Spread Is Directly Testable on Historical `300s` Bars (`P1b` — No Live Wait Required):** Testing whether the `79.1%` ceiling-expiry loss and `2.64%` delayed-fill spread are caused by `3600s` whole-bucket execution latency (`~4,200s` observation-to-fill) rather than the spread wall itself **does not require waiting for a live prospective window**: the repository's canonical `300s` mirror (`kaggle-5m/canonical-v2/main/prices_5m`, `2021–2026`) and `assembled-v3/intraday_5m.parquet` already span the exact three validation folds (`2025-10-29` .. `2026-07-26`). Follow-up experiment **`P1b`** holds the preregistered policy, `recursive_student_t` quantiles, and `osrs_ml.{costs,execution,backtest}` machinery fixed while resolving execution on `300s` bars (`~600–900s` observation-to-fill latency), while explicitly accounting for the averaged-bar limitation (`300s` bucket means still cannot observe intra-bar limit-order queue priority).
3. **Governance:** `0` `E4` slots were used (`4 / 72` remain untouched) and sealed holdout `1785024300` remains strictly closed (`holdout_touched: false`).

---

## 9. Git Provenance Reconciliation & Clean-Commit Reproduction (`git_dirty: false`)

1. **Exact Enumeration of Working-Tree State During Initial `ab9a736` Run:**
   - At initial execution time (`code_commit = ab9a7364e3a066a8454498b1ef28651ca39e3914`, the preregistration commit), **`0` tracked files were modified** in `/home/xmart/osrs-research/code`.
   - Exactly **`2` untracked new files** existed in `/home/xmart/osrs-research/code`:
     1. `?? ml/src/osrs_ml/probabilistic_backtest.py` (`SHA-256: a81f9d9b0e89e13076ff3adb20c85eaf82492b72a34e5e68c0b51e8fbdd7a628`) — **in the execution path** (`__main__` entrypoint for `P1`), untracked at `ab9a736` solely because `p1_backtest_protocol.json` was committed first at `ab9a736` before committing the runner + results together at `96d33eb9dbfbf0f293247cccf777f70a277c65e3` with the identical `SHA-256`.
     2. `?? ml/tests/test_probabilistic_backtest.py` (`SHA-256: 9256e9cfbc466d5eaa8158b26bdfeb01ad8a5a932549b123576055f25f958cad`) — pytest unit suite only (outside the `P1` import/execution path), likewise committed byte-identically at `96d33eb`.
2. **Complete Import-Closure SHA-256 Verification (`ab9a736` vs `96d33eb` vs `e34821f`):**
   - Every dependency imported by `osrs_ml.probabilistic_backtest` had identical Git blob SHA-256 digests across `ab9a736`, `96d33eb`, and `e34821f`: `backtest.py` (`90a3b4bb...`), `costs.py` (`cc32a66f...`), `execution.py` (`0c8e9277...`), `probabilistic_campaign.py` (`c223a0a4...`), `probabilistic_models.py` (`9a57b1ac...`), `probabilistic_train.py` (`a662eee8...`), `probabilistic_evaluation.py` (`775e3969...`), `probabilistic_baselines.py` (`b97eac15...`), `probabilistic_data.py` (`8f2423bc...`), and `__init__.py` (`72b4328f...`).
3. **Cold-Start Clean-Commit Reproduction (`e34821fd6dd494e7cbcc455ca8061a0048298c5f`, `git_dirty: false`):**
   - Because `probabilistic_backtest.py` was `__main__`, the entire `P1` pipeline was re-executed from cold start (fresh output directory with zero cached quantiles, full RTX 5080 Monte Carlo trajectory sampling from the 9 frozen `E2` checkpoints, plus all grid cells, null controls, and sensitivities) on strictly clean commit `e34821fd6dd494e7cbcc455ca8061a0048298c5f` (`git status --porcelain == ""` verified before and after execution).
   - **Bitwise & Numerical Parity Confirmed:** [`p1_backtest_results.json`](p1_backtest_results.json) now records `"code_commit": "e34821fd6dd494e7cbcc455ca8061a0048298c5f"` and `"git_dirty": false`; all `6` `source_module_sha256` digests, all `3` compressed GPU quantile cache hashes (`80febc95...`, `c97c26bd...`, `014ffebf...`), and **100% of numerical results across every metric, grid cell, null control, and sensitivity arm matched the initial run identically (`diff = 0`)**.
