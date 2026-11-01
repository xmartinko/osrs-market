# DeepSeek independent review: data_forensics

Executed2026-11-01 through OpenRouter; requested~deepseek/deepseek-flash-latest; returned model deepseek/deepseek-v4.1-flash-1017. Tool-free bounded reasoning based on supplied evidence; no independent source or archive inspection. Citation leads require principal verification. Not an experimental result.

# Forensic Review of Phase Zero Audit Design

**Tagging convention:** [F] = supplied fact; [D] = deduction from supplied facts; [H] = hypothesis/lead requiring verification.

## 1. Scope

Read-only forensic challenge to the supplied Phase Zero audit. No training, trading, or archive mutation. Reserved holdout from `1785024300` must remain unread; diagnostics below exclude reserved rows by construction. No measurements are invented; all numeric claims are either supplied [F] or explicitly flagged as unverified [H].

## 2. Key Findings

- [F] Report's 941,059,501 "observations" are physically overlapping, not independent; effective sample size is unknown and likely far smaller.
- [F] Kaggle 5m: 876,507,211 rows, 4,513 IDs, 2021–2026; canonical raw timestamp = bucket index × 300.
- [F] Post-2026-09-30 rounded mirror vs v2 decimal discrepancy; Sep-30 RuneLite→all-clients break plus guide/maxcash changes.
- [F] Direct 5m 7.17m rows; hourly 6.88m; guide history 2015–2026 is not trades.
- [F] Original 2.5m export mixes daily/hourly/change events with inferred availability; assembled-v3 is not a broad archive.
- [F] Source latest canonical ts observation; highTime/lowTime transaction ages live in `source_extra`.
- [F] Metadata lacks revision joins; broad duplicate/null rates not independently recomputed (footer/sample only).
- [F] Prior docs report 213 corrected null tests.
- [D] The audit's headline row count is a physical-row statistic, not an information statistic; any CI built on it is mis-scaled.
- [D] Mixed daily/hourly/change events with inferred availability create non-uniform observation density — a latent sampling-process confound, not mere noise.
- [H] The Sep-30 client break plausibly induces a regime shift in both price and volume semantics; unverified.

## 3. Math (identifiability gates)

Let $N_p$ = physical rows, $N_e$ = effective independent observations. Report uses $N_p$; inference requires $N_e$. [D]

- **Duplicate gate:** require per-(ID, ts) uniqueness after canonicalization; report duplicate rate $\delta$ with CI. [F] not recomputed.
- **Staleness/latency gate:** define $\ell = t_{\text{obs}} - t_{\text{event}}$ from `source_extra` high/low ages; require $\ell$ distribution reported per regime. [F] fields exist; [H] distribution unknown.
- **Lifecycle gate:** item availability intervals must be explicit; zero-volume rows are censoring, not zeros. [D]
- **Zero-volume gate:** separate structural zeros (no trade) from missing (no observation). [D]
- **Observational identifiability:** without order book or own fills [F], only price-path and aggregate-volume functionals are identifiable; execution economics are not. [D]
- **CRPS gate:** 2% relative improvement with CI lower bound >0 requires $N_e$-based bootstrap; time-block bootstrap (7d, 3/14d sensitivity) is appropriate [F] but must resample whole cross-sections. [D]

## 4. Citations (leads only — not independently read)

- [H] https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices — canonical timestamp/guide semantics lead.
- [H] https://arxiv.org/abs/2410.03024 — methodological lead (verify relevance before citing).
- [H] https://arxiv.org/abs/2402.06293 — methodological lead (verify relevance before citing).

No browsing/filesystem access; none of the above is claimed as read.

## 5. Assumptions

- [F] Canonical raw timestamp = bucket × 300 for 5m.
- [D] `source_extra` high/low ages are trustworthy enough to bound latency; unverified.
- [H] Post-Sep-30 mirror is a deterministic transform of v2 decimals; if not, both series are contaminated.

## 6. Limits

- [F] No real order book, no own fills → no executable-fill claims.
- [F] Broad duplicate/null rates unverified beyond footer/sample.
- [D] Effective sample size unknown; all CI widths provisional.
- [D] Guide history 2015–2026 is not trades; cannot anchor price realism pre-2021.
- [H] 213 corrected null tests: multiplicity handling unverified.

## 7. Competitors (baselines)

[F] Random walk, empirical innovations, Student-t, ridge, CatBoost; then low-rank Gaussian → 4-block spline flow, same encoder, dependence ablations (independent horizons, recursive Gaussian copula, shuffled path). [D] Random walk is the honest null; any model must beat it on CRPS with $N_e$-corrected CI.

## 8. Falsifiable Experiments (read-only, holdout-excluded)

1. **Duplicate/null recompute** on non-reserved rows: per-ID, per-regime $\delta$, null rate, with block-bootstrap CI. Falsifies "clean archive" if $\delta$ CI lower >0.5%. [D]
2. **Latency distribution** from `source_extra` ages, split pre/post 2026-09-30. Falsifies stationarity if KS test rejects. [D]
3. **Zero-volume decomposition**: structural vs missing by ID-hour. Falsifies "volume is informative" if structural share dominates. [D]
4. **Effective-N estimate** via autocorrelation/long-memory fit on non-reserved series. Falsifies report's CI scaling. [D]
5. **Mirror-vs-v2 reconciliation** on post-Sep-30 overlap: exact decimal match rate. Falsifies mirror usability if mismatch >0. [D]
6. **Regime break test** at Sep-30 on price/volume moments. Falsifies "single regime" assumption. [D]
7. **CRPS power analysis** using $N_e$: minimum detectable 2% effect. Falsifies feasibility of stated gate if underpowered. [D]

## 9. Cost

[D] All diagnostics are CPU-only, read-only, non-reserved-row scans; no GPU (5080/3070/1070) needed. Dominant cost is I/O over 48GB archive; parallelizable by ID. No training, no trading, no archive writes. [F] GPUs reserved for later phases only.

## 10. Confidence / Recommendation

- **Confidence:** High that headline 941M is non-independent [F+D]; medium on regime-break severity [H]; low on effective-N magnitude [H].
- **Recommendation:** [D] Do not proceed to modeling gates until diagnostics 1–4 and 7 pass. Treat all supplied CIs as provisional. Keep holdout sealed. No efficacy established [F]; economic scenarios remain non-executable [F].
