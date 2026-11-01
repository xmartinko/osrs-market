# Phase One `P1` Economic Backtest: Converting `recursive_student_t` into a Sized OSRS Grand Exchange Policy

**Last updated:** `2026-11-01T11:16:00-08:00`  
**Status:** **`MILESTONE 1 — POLICY PREREGISTERED BEFORE COMPUTING VALIDATION P/L`**  
**Branch:** `research/osrs-phase-one-2026-11-01`  
**Preregistration manifest:** [`p1_backtest_protocol.json`](p1_backtest_protocol.json)  
**Scope & Governance:** Development validation backtest across the three `E2/E3` validation folds (`2025-10-29` .. `2026-07-26`, `6,407` hours, `74` items). **`0` `E4` slots consumed** (`68 / 72` neural fit budget unchanged; `4 / 72` `E4` reserve untouched). **Sealed holdout (`>= 1785024300`) strictly closed (`holdout_touched: false`).** Desktop WSL2 **RTX 5080** is the sole active compute node (ThinkPad RTX 3070 remains powered off as retired).

---

## 1. Exact Audit of Reused Repository Cost & Execution Machinery (Rule 1)

No parallel cost or fill simulator was written. Every simulation invokes [`osrs_ml.costs`](../../../ml/src/osrs_ml/costs.py), [`osrs_ml.execution`](../../../ml/src/osrs_ml/execution.py), and [`osrs_ml.backtest`](../../../ml/src/osrs_ml/backtest.py) directly:

1. **GE Seller Tax (`osrs_ml.costs.TaxPolicy` / `DEFAULT_TAX` / `sale_proceeds`):**
   - `rate_bps = 200` (**`2.00%`** seller tax under the post-2025-05-29 Jagex GE tax rules).
   - `exempt_through_gp = 49` (`sale_gp <= 49` pays `0 GP`; `sale_gp == 50` pays `1 GP`).
   - `cap_gp = 5_000_000` (`5M GP` cap **per single unit**).
   - **Exact integer per-unit floor:** `tax_per_item(sale_gp) = min((sale_gp * 200) // 10_000, 5_000_000)` is floored per unit first, then multiplied by `quantity` (`(sale_gp - tax_per_item) * quantity`).
   - Primary evaluation uses conservative `DEFAULT_TAX` (`exempt_item_ids=()`), with a sensitivity check enabling `exempt_item_ids=(379,)` (`Lobster`, the sole item among the 74 panel items on the statutory Jagex exemption list in `battery.py`).

2. **Spread, Slippage, and Sub-GP Lot Allocation (`osrs_ml.costs.price_target` & `integer_lots`, `price_model="integer_lots_v2"`):**
   - Exact fixed-point arithmetic in `1 / 10,000` GP (`target = price_gp * 10_000 +/- (price_gp * adverse_bps + ticks * 10_000)`). Rejects `< 1 GP` targets with `UntradeablePrice("untradeable_at_granularity")` (never permits zero-GP fills).
   - `integer_lots` deterministically splits `quantity` across `floor(target / 10_000)` and `floor(target / 10_000) + 1` integer GP prices so total lot notional equals fractional bps slippage without artificial `v1` per-unit rounding inflation on low-GP runes/consumables.
   - Because `hourly.parquet` stores `avg_high_price` and `avg_low_price` as `float64` volume-weighted averages over 12 five-minute intervals while `price_target` enforces `isinstance(price_gp, Integral)`, valid positive hourly side prices are converted to `Int64` via `max(1, round(price))` (preserving `avg_high_price >= avg_low_price` on all usable rows; null/zero-volume rows remain `NA`). Both continuous `hourly.parquet` spreads and integer-lot realised spreads are reported in Section 5.

3. **Order Lifecycle, Latency, 4-Hour GE Buy Limits, and Volume-Bounded Fills (`osrs_ml.backtest.simulate`):**
   - **Primary Execution Mode (`p1_crossed_moderate_200bps`):** `ExecutionAssumptions(passive_prices=False, fill_model="bucket_proxy_v1", price_model="integer_lots_v2", participation_bps=200, slippage_bps=10, latency_seconds=300, max_freshness_seconds=7500, buy_timeout_seconds=7500, terminal_haircut_bps=100, allow_unknown_metadata=False)`.
     - **Buys** cross the spread to pay future post-latency bucket's **`avg_high_price` (ask) `+ 10 bps` slippage**, capped by a hard GE offer escrow ceiling `buy_ceiling = ceil(ask_t * 1.0010)` (matching real OSRS GE limit-ceiling offers: if future ask jumps above `buy_ceiling`, the offer does not chase unbounded prices and expires after `buy_timeout_seconds = 7,500s`).
     - **Sells** (submitted only once `now >= first_fill + holding_seconds`) cross the spread to receive future post-latency bucket's **`avg_low_price` (bid) `- 10 bps` slippage minus `2.00%` GE tax**.
     - **Total round-trip cost charged:** **Both sides of the market spread** (`ask_buy - bid_sell`, ~`1.79%` median) + **`20 bps` (`0.20%`) slippage** + **`2.00%` GE tax** = **`~3.99%` round-trip cost wall**!
   - **Whole-Bucket Causal Latency (`origin + 3,900s`):** Hourly bucket `[t, t + 3600)` becomes available at `available_at = t + 3900`. `backtest.py` requires `int(row["timestamp"]) >= submitted + 300`, so bucket `h = 1` (`timestamp = t + 3600 < t + 4200`, which started `5` minutes prior to decision time) **never fills**; the earliest executable fill bucket is `h = 2` (`timestamp = t + 7200`).
   - **4-Hour (`14,400s`) GE Buy Limit:** `backtest.py` tracks per-item cumulative bought units in a `14,400s` rolling window anchored on the **first buy fill** (`windows[item] = (first_fill_ts, used_units)`), capping fills at `items.parquet` `buy_limit` (`73 / 74` items known; `1` item with missing `buy_limit` is automatically blocked from buying).
   - **Volume-Based Fill Fraction:** Each eligible 1-hour bucket can fill at most `side_price_volume * participation_bps // 10_000` (`2.0%` of observed directional hourly volume in primary `200 bps`; `0.5%` = `50 bps` and `5.0%` = `500 bps` reported as sensitivities).
   - **Unsold End-of-Fold Inventory Mark:** Marked conservatively at `avg_low_price * (1 - 10 bps) * (1 - 100 bps terminal haircut) - 2.00% GE tax` (never counted as a completed sale).
   - **Secondary Passive Contrast (`p1_passive_v3_200bps`):** `passive_prices=True, fill_model="volume_bounded_v3", volume_qualification="mean_proxy"` (exact `battery_v1` configuration) evaluated under the **same** strict both-side-spread entry filter and paired against Null Controls to separate passive market-making spread capture from directional forecast alpha.

---

## 2. Preregistered Policy Specification (`recursive_student_t` -> Entry, Exit, Sizing)

1. **Causal Inference Cohort (Zero `complete_24h` Lookahead):**
   - For each Fold $f \in \{1, 2, 3\}$, we load the three frozen `E2` checkpoints `e2_recursive_student_t_f{f}_s{11,23,47}` and draw `256` 24-hour log-return trajectories per seed (`S = 768` pooled paths per `(item, origin)`) at **every causally usable hourly origin** (`origin >= 167`, `usable == True`, `high_price_volume > 0`, `low_price_volume > 0`), **never** conditioning on whether future target hours `t + 1 .. t + 24` are complete.
2. **Expected Net Edge After GE Tax and Both-Side Spread (`h = 1, 4, 24` Quantiles):**
   - From the `768` pooled cumulative log-return paths at horizons $h \in \{1, 4, 24\}$, extract empirical quantiles $q_{\tau, h}$ for $\tau \in \{0.10, 0.25, 0.50, 0.75, 0.90\}$ and $\text{IQR}_H = q_{75, H} - q_{25, H}$.
   - Estimated post-latency ask entry price: $P_{\text{buy}}^{\text{est}} = \text{ceil}(\text{ask}_t \cdot \exp(\max(0, q_{50, h=1})) \cdot 1.0010)$.
   - Estimated post-slippage bid exit price at quantile $\tau$ and holding horizon $H \in \{4, 24\}$: $P_{\text{sell}}^{\text{est}}(\tau, H) = \max(1, \text{floor}(\text{bid}_t \cdot \exp(q_{\tau, H}) \cdot 0.9990))$.
   - Expected net return after GE tax and both-side spread:
     $$e_{\text{net}}(i, t; H) = \frac{1}{5} \sum_{\tau \in \{.10,.25,.50,.75,.90\}} \text{costs.net\_return}\!\big(P_{\text{buy}}^{\text{est}}, P_{\text{sell}}^{\text{est}}(\tau, H), \text{DEFAULT\_TAX}\big)$$
3. **Entry & Exit Conditions:**
   - **Entry** requires simultaneously:
     1. $e_{\text{net}}(i, t; H) > \theta_{\text{edge}}$ ($\theta_{\text{edge}} \in \{0, 25, 50\}$ bps),
     2. Median net return $\text{costs.net\_return}(P_{\text{buy}}^{\text{est}}, P_{\text{sell}}^{\text{est}}(0.50, H), \text{DEFAULT\_TAX}) > 0$,
     3. `h = 1` crash & ceiling-fillability guard: $-0.05 < q_{10, h=1} \le 0.005$,
     4. Cross-horizon path alignment: $q_{50, h=24} \ge 0$ when $H = 4$; $q_{50, h=4} \ge -0.01$ when $H = 24$,
     5. End-of-window buffer: `available_at < window_end - (H + 3) * 3600`.
   - Eligible candidates at each timestamp are ranked by `score = e_net(i, t; H) / max(IQR_H, 0.005)`.
   - **Exit** is triggered causally by `backtest.simulate` once `now >= first_fill + H * 3600` (`4h = 14,400s` aligned with the 4-hour GE limit cycle, or `24h = 86,400s` aligned with the 24h trajectory).
4. **Position Sizing & Capital Constraints:**
   - **Primary Capital:** `initial_cash_gp = 100,000,000` (`100M GP`) across `offer_slots = 8` GE slots (`max_slot_allocation_bps = 1250` = `12.5M GP` per slot so all `73` known-limit items up to `Berserker ring` ~`4.7M GP` can trade; `DEFAULT_PORTFOLIO` `10M GP` reported as sensitivity).
   - **Dynamic Inverse-IQR / Edge Sizing (`allocation_bps`):**
     $$\text{alloc\_bps}(i, t) = \text{clip}\!\left(\left\lfloor 1250 \cdot \min\!\big(1, \frac{e_{\text{net}}}{0.01}\big) \cdot \min\!\big(1, \frac{0.02}{\max(\text{IQR}_H, 0.005)}\big) \right\rfloor, 100, 1250\right)$$
5. **Training-Only `2 × 3 = 6`-Cell Tuning Grid & Null Controls:**
   - **Grid (`6` cells):** `H in {4, 24}` hours × `min_net_edge_bps in {0, 25, 50}` bps, tuned **strictly inside each fold's 21-day (`504h`) pre-validation inner training window** (`[val_start - 21d, val_start)`), which was held out of gradient updates during `E2` training. **Every cell is reported on outer validation whether it wins or loses.**
   - **Null Controls (identical executor, cost wall, and sizing formula):**
     1. `null_time_shuffled` (`5` deterministic `168h`-block / circular time-shifts of predicted quantile vectors within each `(fold, item)` evaluated against true current `ask_t / bid_t`),
     2. `null_sign_flipped` ($q_{\tau, h} \mapsto -q_{1-\tau, h}$, inverting directional forecasts),
     3. `null_detrended_zero_drift` ($q_{\tau, h} \mapsto q_{\tau, h} - q_{50, h}$, removing conditional drift).

---

## 3. Execution Log (Updating Live)

- `[2026-11-01T11:16-08:00]` Milestone 1 preregistered (`p1_backtest_protocol.json` + `P1_BACKTEST.md`) prior to any validation P/L computation. Next: commit & push Milestone 1 to `devstash`, then implement `ml/src/osrs_ml/probabilistic_backtest.py` + unit tests, extract GPU quantiles on RTX 5080, run inner-training selection + full 6-cell validation + 3 null controls, and record complete results below.
