"""Full chronological 3-fold statistical, state-space, GARCH, and tabular baselines (E1).

Implements the registered Phase One E1 baseline suite over the guarded 74-item hourly
Grand Exchange panel without touching the sealed holdout (>= 1785024300).

CLI usage:
    python -m osrs_ml.probabilistic_baselines \\
        --panel /home/xmart/osrs-research/data/hourly.parquet \\
        --protocol research/osrs-forecasting/phase_one/e1_baseline_protocol.json \\
        --output /home/xmart/osrs-research/runs/e1_baselines_3fold \\
        --report-json research/osrs-forecasting/phase_one/e1_baseline_results.json \\
        --threads 6
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.metadata
import json
import math
import os
import platform
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import linalg, optimize, special, stats

from .probabilistic_evaluation import (
    REGISTERED_INTERVAL_ALPHAS,
    energy_score,
    holm_adjust,
    interval_scores,
    paired_panel_block_bootstrap,
    pit_values,
    quantile_interval_scores,
    sample_crps,
    shuffle_horizon_dependence,
    variogram_score_both,
)
from .probabilistic_train import (
    CONTEXT,
    HOLDOUT_START,
    HORIZON,
    HOUR,
    REGISTERED_FOLDS,
    TRAIN_START,
    VALIDATION_START,
    _git_provenance,
    _json,
    eligible_origin_diagnostics,
    eligible_origins,
    file_hash,
    load_verified_panel,
    prepare_arrays,
)

QUANTILE_LEVELS = (
    0.01,
    0.025,
    0.05,
    0.10,
    0.15,
    0.25,
    0.50,
    0.75,
    0.85,
    0.90,
    0.95,
    0.975,
    0.99,
)

PER_ITEM_BASELINES = (
    "no_change",
    "gaussian_rw_std",
    "gaussian_rw_mad",
    "empirical_iid_rw",
    "empirical_block24_rw",
    "rolling_168h_gaussian",
    "rolling_168h_drift_gaussian",
    "seasonal_naive_24h",
    "seasonal_naive_168h",
    "ewma_iid_gaussian",
    "ewma_iid_student_t",
    "ets_ses_gaussian",
    "ets_ses_student_t",
    "ets_ewma_student_t",
    "ets_damped_gaussian",
    "arima_aicc_gaussian",
    "ma1_garch11_gaussian",
    "ma1_garch11_student_t",
)

POOLED_BASELINES = (
    "ridge_lag_homoskedastic",
    "ridge_lag_ewma_student_t",
    "catboost_multiquantile_copula",
)

ALL_E1_BASELINES = PER_ITEM_BASELINES + POOLED_BASELINES

TAIL_ABS_R24_THRESHOLD = 0.05
TAIL_MAX_EXCURSION_THRESHOLD = math.log(1.03)


def compute_selection_strata(frame: pd.DataFrame, manifest: dict) -> dict:
    """Compute initial-selection-year GP-notional turnover strata alongside manifest strata."""
    sel = frame[(frame["ts"] >= TRAIN_START) & (frame["ts"] < VALIDATION_START) & frame["usable"]]
    if sel.empty or int(sel["ts"].max()) >= VALIDATION_START:
        raise ValueError("Invalid initial selection slice for GP-notional stratification")
    gp_turnover = sel["mid_price"] * (sel["high_price_volume"] + sel["low_price_volume"])
    grouped = (
        sel.assign(gp_turnover=gp_turnover)
        .groupby("item_id", as_index=False)
        .agg(gp_notional=("gp_turnover", "sum"), median_price=("mid_price", "median"))
        .sort_values(["gp_notional", "item_id"], ascending=[False, True])
        .reset_index(drop=True)
    )
    n_items = len(grouped)
    high_n = math.ceil(n_items / 3)
    med_n = math.ceil((n_items - high_n) / 2)
    low_n = n_items - high_n - med_n
    strata_labels = ["high"] * high_n + ["medium"] * med_n + ["low"] * low_n
    grouped["gp_notional_stratum"] = strata_labels

    subset_12 = []
    for label in ("high", "medium", "low"):
        sub = grouped[grouped["gp_notional_stratum"] == label].reset_index(drop=True)
        if len(sub) >= 4:
            idx = np.linspace(0, len(sub) - 1, 4, dtype=int)
            subset_12.extend(int(v) for v in sub.iloc[idx]["item_id"].tolist())
        else:
            subset_12.extend(int(v) for v in sub["item_id"].tolist())

    manifest_strata = {
        int(entry["item_id"]): str(entry["liquidity_stratum"])
        for entry in manifest.get("selected_items", [])
    }
    gp_strata = {
        int(row["item_id"]): str(row["gp_notional_stratum"]) for _, row in grouped.iterrows()
    }
    gp_notional_map = {
        int(row["item_id"]): float(row["gp_notional"]) for _, row in grouped.iterrows()
    }
    median_price_map = {
        int(row["item_id"]): float(row["median_price"]) for _, row in grouped.iterrows()
    }
    return {
        "gp_notional_strata": gp_strata,
        "manifest_unit_volume_strata": manifest_strata,
        "gp_notional_by_item": gp_notional_map,
        "median_selection_price_by_item": median_price_map,
        "representative_12_item_ids": subset_12,
    }


def _unit_variance_student_t(rng: np.random.Generator, df: float, shape: tuple[int, ...]):
    """Draw zero-mean, unit-variance Student-t variates for df > 2."""
    df = max(float(df), 2.1)
    return rng.standard_t(df, size=shape) * math.sqrt((df - 2.0) / df)


def _kalman_local_level_filter(
    log_price: np.ndarray, sigma_level: float, sigma_obs: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Causal 1D local-level Kalman filter over log_price (with NaNs)."""
    n = len(log_price)
    filt_mean = np.full(n, np.nan, dtype=np.float64)
    filt_var = np.full(n, np.nan, dtype=np.float64)
    innov = np.full(n, np.nan, dtype=np.float64)
    innov_var = np.full(n, np.nan, dtype=np.float64)

    q = sigma_level * sigma_level
    r = sigma_obs * sigma_obs
    max_var = max(250.0 * q + 25.0 * r, 1.0)

    initialized = False
    m = 0.0
    p = r
    for t in range(n):
        y = float(log_price[t])
        is_valid = math.isfinite(y)
        if not initialized:
            if is_valid:
                m = y
                p = r
                initialized = True
                filt_mean[t] = m
                filt_var[t] = p
            continue
        p_pred = min(p + q, max_var)
        if is_valid:
            v = y - m
            f = p_pred + r
            k = p_pred / f
            m = m + k * v
            p = max((1.0 - k) * p_pred, 0.0)
            innov[t] = v
            innov_var[t] = f
        else:
            p = p_pred
        filt_mean[t] = m
        filt_var[t] = p
    return filt_mean, filt_var, innov, innov_var


def _fit_local_level_gaussian(
    log_price_train: np.ndarray, scale_init: float
) -> tuple[float, float]:
    """Fit (sigma_level, sigma_obs) on training log prices via exact Kalman Gaussian MLE."""
    s0 = max(scale_init, 1e-4)

    def nll(theta):
        s_lvl = math.exp(float(np.clip(theta[0], -14.0, 2.0)))
        s_obs = math.exp(float(np.clip(theta[1], -14.0, 2.0)))
        _, _, innov, innov_var = _kalman_local_level_filter(log_price_train, s_lvl, s_obs)
        mask = np.isfinite(innov) & (innov_var > 1e-18)
        if mask.sum() < 24:
            return 1e12
        v = innov[mask]
        f = innov_var[mask]
        return 0.5 * float(np.sum(np.log(2.0 * math.pi * f) + (v * v) / f))

    init = np.array([math.log(0.5 * s0), math.log(0.7 * s0)], dtype=np.float64)
    bounds = [(-13.0, 1.0), (-13.0, 1.0)]
    res = optimize.minimize(nll, init, method="L-BFGS-B", bounds=bounds)
    theta = res.x if res.success and np.all(np.isfinite(res.x)) else init
    return math.exp(float(theta[0])), math.exp(float(theta[1]))


def _fit_local_level_student_t(
    log_price_train: np.ndarray, scale_init: float
) -> tuple[float, float, float]:
    """Fit (sigma_level, sigma_obs, df) jointly via 1-step unit-variance Student-t Kalman Qlik."""
    s0 = max(scale_init, 1e-4)

    def nll(theta):
        s_lvl = math.exp(float(np.clip(theta[0], -14.0, 2.0)))
        s_obs = math.exp(float(np.clip(theta[1], -14.0, 2.0)))
        df = 2.15 + math.exp(float(np.clip(theta[2], -5.0, 4.5)))
        _, _, innov, innov_var = _kalman_local_level_filter(log_price_train, s_lvl, s_obs)
        mask = np.isfinite(innov) & (innov_var > 1e-18)
        if mask.sum() < 24:
            return 1e12
        v = innov[mask]
        # Unit-variance t_df has scale parameter sqrt(F * (df - 2) / df).
        t_scale = np.sqrt(innov_var[mask] * ((df - 2.0) / df))
        z = v / t_scale
        log_pdf = (
            special.gammaln(0.5 * (df + 1.0))
            - special.gammaln(0.5 * df)
            - 0.5 * math.log(df * math.pi)
            - np.log(t_scale)
            - 0.5 * (df + 1.0) * np.log1p((z * z) / df)
        )
        return -float(np.sum(log_pdf))

    init = np.array([math.log(0.45 * s0), math.log(0.65 * s0), math.log(3.0)], dtype=np.float64)
    bounds = [(-13.0, 1.0), (-13.0, 1.0), (-4.0, 4.2)]
    res = optimize.minimize(nll, init, method="L-BFGS-B", bounds=bounds)
    theta = res.x if res.success and np.all(np.isfinite(res.x)) else init
    return (
        math.exp(float(theta[0])),
        math.exp(float(theta[1])),
        2.15 + math.exp(float(theta[2])),
    )


def _kalman_ewma_scale(
    innov: np.ndarray, innov_var: np.ndarray, train_len: int
) -> tuple[np.ndarray, float, float]:
    """Fit causal EWMA volatility multiplier and Student-t df on standardized Kalman innovations."""
    u = np.where(np.isfinite(innov) & (innov_var > 1e-18), innov / np.sqrt(innov_var), np.nan)
    u_train = u[:train_len]

    best_lam = 0.94
    best_c = 1.0
    best_df = 5.0
    best_nll = float("inf")

    for lam in (0.88, 0.94, 0.97, 0.99):
        g2 = np.ones(len(u_train), dtype=np.float64)
        cur = 1.0
        for t in range(len(u_train)):
            g2[t] = cur
            if math.isfinite(u_train[t]):
                shock2 = min(float(u_train[t] * u_train[t]), 25.0)
                cur = lam * cur + (1.0 - lam) * shock2
            else:
                cur = lam * cur + (1.0 - lam) * 1.0
        mask = np.isfinite(u_train)
        if mask.sum() < 32:
            continue
        z_raw = u_train[mask] / np.sqrt(np.maximum(g2[mask], 1e-6))

        def _obj(params, z_vec=z_raw):
            c = math.exp(float(np.clip(params[0], -2.0, 2.0)))
            df = 2.2 + math.exp(float(np.clip(params[1], -4.0, 4.2)))
            t_scale = c * math.sqrt((df - 2.0) / df)
            zs = z_vec / t_scale
            lp = (
                special.gammaln(0.5 * (df + 1.0))
                - special.gammaln(0.5 * df)
                - 0.5 * math.log(df * math.pi)
                - math.log(t_scale)
                - 0.5 * (df + 1.0) * np.log1p((zs * zs) / df)
            )
            return -float(np.sum(lp))

        opt = optimize.minimize(
            _obj,
            np.array([0.0, math.log(3.0)]),
            method="L-BFGS-B",
            bounds=[(-1.5, 1.5), (-3.5, 4.0)],
        )
        if opt.fun < best_nll and np.all(np.isfinite(opt.x)):
            best_nll = float(opt.fun)
            best_lam = lam
            best_c = math.exp(float(opt.x[0]))
            best_df = 2.2 + math.exp(float(opt.x[1]))

    # Causal forward pass across full series; mult_next[t] uses innovations up to and including t.
    mult_next = np.ones(len(u), dtype=np.float64)
    cur = 1.0
    for t in range(len(u)):
        if math.isfinite(u[t]):
            shock2 = min(float(u[t] * u[t]), 25.0)
            cur = best_lam * cur + (1.0 - best_lam) * shock2
        else:
            cur = best_lam * cur + (1.0 - best_lam) * 1.0
        mult_next[t] = best_c * math.sqrt(max(cur, 1e-6))
    return mult_next, best_df, best_lam


def _kalman_damped_trend_filter(
    log_price: np.ndarray, sigma_level: float, sigma_slope: float, phi: float, sigma_obs: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Causal 2D damped-trend state-space filter: y_t = l_t + eps_t, l_t = l_{t-1} + phi*b_{t-1} + xi_t."""
    n = len(log_price)
    m0 = np.full(n, np.nan, dtype=np.float64)
    m1 = np.zeros(n, dtype=np.float64)
    c00 = np.full(n, np.nan, dtype=np.float64)
    c01 = np.zeros(n, dtype=np.float64)
    c11 = np.zeros(n, dtype=np.float64)
    nll_terms = np.full(n, np.nan, dtype=np.float64)

    q0 = sigma_level * sigma_level
    q1 = sigma_slope * sigma_slope
    r = sigma_obs * sigma_obs
    max_var = max(250.0 * (q0 + q1) + 25.0 * r, 1.0)

    initialized = False
    l_est = 0.0
    b_est = 0.0
    p00 = r
    p01 = 0.0
    p11 = q1 + 1e-8

    for t in range(n):
        y = float(log_price[t])
        is_valid = math.isfinite(y)
        if not initialized:
            if is_valid:
                l_est = y
                b_est = 0.0
                p00 = r
                p01 = 0.0
                p11 = q1 + 1e-8
                initialized = True
                m0[t], m1[t] = l_est, b_est
                c00[t], c01[t], c11[t] = p00, p01, p11
            continue

        # Predict state: [1, phi; 0, phi]
        l_pred = l_est + phi * b_est
        b_pred = phi * b_est
        pp00 = min(p00 + 2.0 * phi * p01 + phi * phi * p11 + q0, max_var)
        pp01 = phi * (p01 + phi * p11)
        pp11 = min(phi * phi * p11 + q1, max_var)

        if is_valid:
            v = y - l_pred
            f = pp00 + r
            k0 = pp00 / f
            k1 = pp01 / f
            l_est = l_pred + k0 * v
            b_est = b_pred + k1 * v
            p00 = max((1.0 - k0) * pp00, 0.0)
            p01 = (1.0 - k0) * pp01
            p11 = max(pp11 - k1 * pp01, 0.0)
            nll_terms[t] = 0.5 * (math.log(2.0 * math.pi * f) + (v * v) / f)
        else:
            l_est, b_est = l_pred, b_pred
            p00, p01, p11 = pp00, pp01, pp11

        m0[t], m1[t] = l_est, b_est
        c00[t], c01[t], c11[t] = p00, p01, p11

    return m0, m1, c00, c01, c11, nll_terms


def _fit_damped_trend_gaussian(
    log_price_train: np.ndarray, scale_init: float
) -> tuple[float, float, float, float]:
    s0 = max(scale_init, 1e-4)

    def nll(theta):
        s_lvl = math.exp(float(np.clip(theta[0], -14.0, 2.0)))
        s_slp = math.exp(float(np.clip(theta[1], -16.0, 0.0)))
        phi = 0.50 + 0.49 * special.expit(float(np.clip(theta[2], -8.0, 8.0)))
        s_obs = math.exp(float(np.clip(theta[3], -14.0, 2.0)))
        _, _, _, _, _, terms = _kalman_damped_trend_filter(
            log_price_train, s_lvl, s_slp, phi, s_obs
        )
        mask = np.isfinite(terms)
        if mask.sum() < 24:
            return 1e12
        return float(np.sum(terms[mask]))

    init = np.array(
        [math.log(0.45 * s0), math.log(0.05 * s0), 0.5, math.log(0.65 * s0)], dtype=np.float64
    )
    bounds = [(-13.0, 1.0), (-15.0, -1.0), (-6.0, 6.0), (-13.0, 1.0)]
    res = optimize.minimize(nll, init, method="L-BFGS-B", bounds=bounds, options={"maxiter": 60})
    theta = res.x if res.success and np.all(np.isfinite(res.x)) else init
    return (
        math.exp(float(theta[0])),
        math.exp(float(theta[1])),
        0.50 + 0.49 * float(special.expit(float(theta[2]))),
        math.exp(float(theta[3])),
    )


def _fit_ewma_iid(
    log_price: np.ndarray, train_len: int, rw_scale: float
) -> tuple[np.ndarray, float, float]:
    """Fit causal RiskMetrics-style EWMA volatility and Student-t (c, df) on training window."""
    valid_idx = np.flatnonzero(np.isfinite(log_price))
    bridged_shock = np.full(len(log_price), np.nan, dtype=np.float64)
    if len(valid_idx) >= 2:
        gaps = np.diff(valid_idx).astype(np.float64)
        bridged_shock[valid_idx[1:]] = np.diff(log_price[valid_idx]) / np.sqrt(gaps)

    base_var = max(rw_scale * rw_scale, 1e-8)
    best_lam = 0.94
    best_nll = float("inf")
    for lam in (0.85, 0.90, 0.94, 0.97, 0.99):
        var_pred = base_var
        nll = 0.0
        cnt = 0
        for t in range(train_len):
            s = bridged_shock[t]
            if math.isfinite(s):
                nll += 0.5 * (math.log(2.0 * math.pi * var_pred) + (s * s) / var_pred)
                cnt += 1
                var_pred = lam * var_pred + (1.0 - lam) * min(s * s, 25.0 * base_var)
            else:
                var_pred = lam * var_pred + (1.0 - lam) * base_var
        if cnt >= 24 and nll < best_nll:
            best_nll = nll
            best_lam = lam

    # Compute sigma_next[t] = conditional 1-step std at origin t (using shocks <= t).
    sigma_next = np.full(len(log_price), math.sqrt(base_var), dtype=np.float64)
    std_train = []
    cur_var = base_var
    for t in range(len(log_price)):
        s = bridged_shock[t]
        if math.isfinite(s):
            if t < train_len:
                std_train.append(s / math.sqrt(max(cur_var, 1e-12)))
            cur_var = best_lam * cur_var + (1.0 - best_lam) * min(s * s, 25.0 * base_var)
        else:
            cur_var = best_lam * cur_var + (1.0 - best_lam) * base_var
        sigma_next[t] = max(math.sqrt(cur_var), 1e-4)

    z_arr = np.asarray(std_train, dtype=np.float64)
    if len(z_arr) >= 32:

        def _t_nll(params):
            c = math.exp(float(np.clip(params[0], -2.0, 2.0)))
            df = 2.2 + math.exp(float(np.clip(params[1], -4.0, 4.2)))
            t_sc = c * math.sqrt((df - 2.0) / df)
            zs = z_arr / t_sc
            lp = (
                special.gammaln(0.5 * (df + 1.0))
                - special.gammaln(0.5 * df)
                - 0.5 * math.log(df * math.pi)
                - math.log(t_sc)
                - 0.5 * (df + 1.0) * np.log1p((zs * zs) / df)
            )
            return -float(np.sum(lp))

        opt = optimize.minimize(
            _t_nll,
            np.array([0.0, math.log(3.0)]),
            method="L-BFGS-B",
            bounds=[(-1.5, 1.5), (-3.5, 4.0)],
        )
        if np.all(np.isfinite(opt.x)):
            t_mult = math.exp(float(opt.x[0]))
            t_df = 2.2 + math.exp(float(opt.x[1]))
        else:
            t_mult, t_df = 1.0, 5.0
    else:
        t_mult, t_df = 1.0, 5.0

    return sigma_next, t_mult, t_df


def _simulate_arima_aicc(
    log_price: np.ndarray,
    train_len: int,
    eval_origins: np.ndarray,
    draws: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, tuple[int, int, int]]:
    """Fit ARIMA(p,1,q) by training AICc via SARIMAX and simulate causal validation paths."""
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
    except ImportError as exc:
        raise ImportError("arima_aicc_gaussian requires optional statsmodels package") from exc

    y_train = log_price[:train_len]
    candidate_orders = ((0, 1, 1), (1, 1, 0), (1, 1, 1), (2, 1, 1))
    best_order = (0, 1, 1)
    best_params = None
    best_aicc = float("inf")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for order in candidate_orders:
            try:
                mod = SARIMAX(
                    y_train,
                    order=order,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                )
                fit = mod.fit(disp=False, maxiter=80)
                if np.all(np.isfinite(fit.params)) and math.isfinite(fit.aicc):
                    if fit.aicc < best_aicc:
                        best_aicc = float(fit.aicc)
                        best_order = order
                        best_params = fit.params.copy()
            except Exception:
                continue

        if best_params is None:
            mod = SARIMAX(
                y_train, order=(0, 1, 1), enforce_stationarity=False, enforce_invertibility=False
            )
            fit = mod.fit(disp=False, maxiter=50)
            best_params = fit.params.copy()

        full_mod = SARIMAX(
            log_price,
            order=best_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        filtered = full_mod.filter(best_params)

    fr = filtered.filter_results
    transition = np.asarray(fr.transition[:, :, 0], dtype=np.float64)
    design = np.asarray(fr.design[:, :, 0], dtype=np.float64)
    selection = np.asarray(fr.selection[:, :, 0], dtype=np.float64)
    state_cov = np.asarray(fr.state_cov[:, :, 0], dtype=np.float64)
    obs_cov = float(fr.obs_cov[0, 0, 0]) if fr.obs_cov.size else 0.0

    # Symmetrize and factorize R @ Q @ R.T cleanly.
    rqr = selection @ state_cov @ selection.T
    rqr = 0.5 * (rqr + rqr.T)
    eigvals, eigvecs = np.linalg.eigh(rqr)
    eigvals = np.maximum(eigvals, 0.0)
    shock_proj = eigvecs @ np.diag(np.sqrt(eigvals))

    state_dim = transition.shape[0]
    n_orig = len(eval_origins)
    a_orig = np.asarray(fr.filtered_state[:, eval_origins], dtype=np.float64).T  # [B, S]
    p_orig = np.asarray(fr.filtered_state_cov[:, :, eval_origins], dtype=np.float64).transpose(
        2, 0, 1
    )  # [B, S, S]

    # Sample initial posterior state alpha_t ~ N(a_{t|t}, P_{t|t}).
    states = np.empty((n_orig, draws, state_dim), dtype=np.float64)
    z_init = rng.normal(size=(n_orig, draws, state_dim))
    for b in range(n_orig):
        cov_b = 0.5 * (p_orig[b] + p_orig[b].T)
        vals, vecs = np.linalg.eigh(cov_b)
        vals = np.clip(vals, 0.0, 1.0)
        chol_b = vecs @ np.diag(np.sqrt(vals))
        states[b] = a_orig[b][None, :] + z_init[b] @ chol_b.T

    y_base = log_price[eval_origins][:, None]
    paths = np.empty((n_orig, draws, HORIZON), dtype=np.float64)
    obs_std = math.sqrt(max(obs_cov, 0.0))
    z_vec = design.reshape(-1)

    for h in range(HORIZON):
        eta = rng.normal(size=(n_orig, draws, state_dim)) @ shock_proj.T
        states = np.einsum("ij,bmj->bmi", transition, states) + eta
        y_sim = np.einsum("i,bmi->bm", z_vec, states)
        if obs_std > 0:
            y_sim = y_sim + rng.normal(scale=obs_std, size=(n_orig, draws))
        paths[:, :, h] = y_sim - y_base
    return paths, best_order


def _fit_ma1_mean(returns: np.ndarray, train_len: int) -> tuple[float, float, np.ndarray]:
    """Fit causal MA(1) bounce filter r_t = mu + eps_t + theta * eps_{t-1} on training returns."""
    r_train = returns[:train_len]
    valid_train = r_train[np.isfinite(r_train)]
    mu = float(np.median(valid_train)) if len(valid_train) else 0.0

    def sse(theta_arr):
        theta = float(np.clip(theta_arr[0], -0.95, 0.95))
        eps_prev = 0.0
        loss = 0.0
        for t in range(train_len):
            rt = r_train[t]
            if math.isfinite(rt):
                eps = float(rt) - mu - theta * eps_prev
                loss += eps * eps
                eps_prev = eps
            else:
                eps_prev = 0.0
        return loss

    res = optimize.minimize(sse, np.array([-0.25]), method="L-BFGS-B", bounds=[(-0.92, 0.92)])
    theta = float(res.x[0]) if res.success and np.all(np.isfinite(res.x)) else 0.0

    eps_all = np.full(len(returns), np.nan, dtype=np.float64)
    eps_prev = 0.0
    for t in range(len(returns)):
        rt = returns[t]
        if math.isfinite(rt):
            eps = float(rt) - mu - theta * eps_prev
            eps_all[t] = eps
            eps_prev = eps
        else:
            eps_prev = 0.0
    return mu, theta, eps_all


def _simulate_ma1_garch11(
    log_price: np.ndarray,
    returns: np.ndarray,
    train_len: int,
    eval_origins: np.ndarray,
    draws: int,
    dist_name: str,
    rw_scale: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Fit causal MA(1)-GARCH(1,1) (Gaussian or Student-t) via arch on train and simulate paths."""
    try:
        from arch import arch_model
    except ImportError as exc:
        raise ImportError("ma1_garch11 baselines require optional arch package") from exc

    mu, theta, eps_all = _fit_ma1_mean(returns, train_len)
    eps_train = eps_all[:train_len]
    clean_eps = eps_train[np.isfinite(eps_train)]
    scale_factor = 100.0
    fallback_var = max(float(np.var(clean_eps)) if len(clean_eps) >= 24 else rw_scale**2, 1e-8)

    omega = 0.05 * fallback_var
    alpha = 0.10
    beta = 0.85
    df = 6.0

    if len(clean_eps) >= 64:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                am = arch_model(
                    clean_eps * scale_factor,
                    mean="Zero",
                    vol="GARCH",
                    p=1,
                    o=0,
                    q=1,
                    dist="normal" if dist_name == "gaussian" else "t",
                    rescale=False,
                )
                res = am.fit(disp="off", show_warning=False)
                params = res.params
                if np.all(np.isfinite(params)):
                    om = float(params["omega"]) / (scale_factor * scale_factor)
                    al = float(params["alpha[1]"])
                    be = float(params["beta[1]"])
                    if om > 0 and al >= 0 and be >= 0 and (al + be) < 0.999:
                        omega, alpha, beta = om, al, be
                    if dist_name == "student_t" and "nu" in params:
                        df = float(np.clip(params["nu"], 2.2, 60.0))
            except Exception:
                pass

    uncond_var = omega / max(1.0 - alpha - beta, 0.02)
    uncond_var = float(np.clip(uncond_var, 1e-9, 25.0 * fallback_var))
    max_shock2 = 25.0 * uncond_var

    # Causal forward GARCH variance & innovation state using bridged shock across gaps when needed.
    valid_idx = np.flatnonzero(np.isfinite(log_price))
    bridged_var_shock = np.full(len(log_price), np.nan, dtype=np.float64)
    if len(valid_idx) >= 2:
        gaps = np.diff(valid_idx).astype(np.float64)
        bridged_var_shock[valid_idx[1:]] = (np.diff(log_price[valid_idx]) - gaps * mu) / np.sqrt(
            gaps
        )

    sigma2_next = np.full(len(log_price), uncond_var, dtype=np.float64)
    eps_state = np.zeros(len(log_price), dtype=np.float64)
    cur_var = uncond_var
    for t in range(len(log_price)):
        e = eps_all[t]
        if math.isfinite(e):
            eps_state[t] = e
            shock2 = min(e * e, max_shock2)
            cur_var = omega + alpha * shock2 + beta * cur_var
        elif math.isfinite(bridged_var_shock[t]):
            eps_state[t] = 0.0
            shock2 = min(bridged_var_shock[t] ** 2, max_shock2)
            cur_var = omega + alpha * shock2 + beta * cur_var
        else:
            eps_state[t] = 0.0
            cur_var = omega + (alpha + beta) * cur_var
        cur_var = min(max(cur_var, 1e-10), 50.0 * uncond_var)
        sigma2_next[t] = cur_var

    n_orig = len(eval_origins)
    var_h = np.broadcast_to(sigma2_next[eval_origins][:, None], (n_orig, draws)).copy()
    eps_prev = np.broadcast_to(eps_state[eval_origins][:, None], (n_orig, draws)).copy()
    inc_paths = np.empty((n_orig, draws, HORIZON), dtype=np.float64)

    for h in range(HORIZON):
        if dist_name == "gaussian":
            z = rng.normal(size=(n_orig, draws))
        else:
            z = _unit_variance_student_t(rng, df, (n_orig, draws))
        eps_cur = np.sqrt(var_h) * z
        inc_paths[:, :, h] = mu + eps_cur + theta * eps_prev
        eps_prev = eps_cur
        var_h = np.minimum(
            omega + alpha * np.minimum(eps_cur * eps_cur, max_shock2) + beta * var_h,
            50.0 * uncond_var,
        )

    return np.cumsum(inc_paths, axis=-1)


def iter_per_item_forecasts(
    panel,
    item_idx: int,
    train_start: int,
    validation_start: int,
    eval_origins: np.ndarray,
    draws: int,
    seed: int,
    *,
    models_to_run: tuple[str, ...] = PER_ITEM_BASELINES,
):
    """Yield ``(model_name, paths [B, M, H])`` one baseline at a time to bound peak RSS."""
    times = panel.times
    log_price = np.log(panel.prices[item_idx])
    returns = panel.returns[item_idx]
    scale_mad = float(panel.scale[item_idx])
    scale_std = float(panel.rw_scale[item_idx])

    train_time_mask = (times >= train_start) & (times < validation_start)
    train_indices = np.flatnonzero(train_time_mask)
    if len(train_indices) == 0:
        raise ValueError("Empty training time slice")
    train_start_idx = int(train_indices[0])
    val_start_idx = int(train_indices[-1]) + 1

    # Slice causal series starting at train_start_idx so trailing folds use strictly trailing year.
    sub_log_price = log_price[train_start_idx:]
    sub_returns = returns[train_start_idx:]
    sub_train_len = val_start_idx - train_start_idx
    sub_eval_origins = eval_origins - train_start_idx

    n_orig = len(eval_origins)

    if "no_change" in models_to_run:
        yield "no_change", np.zeros((n_orig, draws, HORIZON), dtype=np.float64)

    if "gaussian_rw_std" in models_to_run:
        rng = np.random.default_rng(seed + 1001)
        yield (
            "gaussian_rw_std",
            np.cumsum(rng.normal(scale=scale_std, size=(n_orig, draws, HORIZON)), axis=-1),
        )

    if "gaussian_rw_mad" in models_to_run:
        rng = np.random.default_rng(seed + 1002)
        yield (
            "gaussian_rw_mad",
            np.cumsum(rng.normal(scale=scale_mad, size=(n_orig, draws, HORIZON)), axis=-1),
        )

    r_train_valid = sub_returns[:sub_train_len]
    r_train_valid = r_train_valid[np.isfinite(r_train_valid)]
    r_train_centered = r_train_valid - np.mean(r_train_valid)

    if "empirical_iid_rw" in models_to_run:
        rng = np.random.default_rng(seed + 1003)
        idx = rng.integers(len(r_train_centered), size=(n_orig, draws, HORIZON))
        yield "empirical_iid_rw", np.cumsum(r_train_centered[idx], axis=-1)

    if "empirical_block24_rw" in models_to_run:
        rng = np.random.default_rng(seed + 1004)
        # Strictly purged training 24h blocks: o + HORIZON < sub_train_len.
        block_paths = []
        for o in range(0, max(sub_train_len - HORIZON, 0)):
            if (
                np.isfinite(sub_log_price[o])
                and np.isfinite(sub_log_price[o + 1 : o + HORIZON + 1]).all()
            ):
                block_paths.append(sub_log_price[o + 1 : o + HORIZON + 1] - sub_log_price[o])
        if len(block_paths) >= 16:
            bank = np.asarray(block_paths, dtype=np.float64)
            choice = rng.integers(len(bank), size=(n_orig, draws))
            yield "empirical_block24_rw", bank[choice]
        else:
            idx = rng.integers(len(r_train_centered), size=(n_orig, draws, HORIZON))
            yield "empirical_block24_rw", np.cumsum(r_train_centered[idx], axis=-1)

    if "rolling_168h_gaussian" in models_to_run or "rolling_168h_drift_gaussian" in models_to_run:
        local_std = np.empty(n_orig, dtype=np.float64)
        local_mean = np.zeros(n_orig, dtype=np.float64)
        for b, orig in enumerate(eval_origins):
            window = returns[max(0, orig - CONTEXT + 1) : orig + 1]
            fin = window[np.isfinite(window)]
            if len(fin) >= 12:
                local_std[b] = max(float(np.std(fin, ddof=1)), 1e-4)
                local_mean[b] = float(np.mean(fin))
            else:
                local_std[b] = scale_std
                local_mean[b] = 0.0
        if "rolling_168h_gaussian" in models_to_run:
            rng = np.random.default_rng(seed + 1005)
            shocks = rng.normal(size=(n_orig, draws, HORIZON)) * local_std[:, None, None]
            yield "rolling_168h_gaussian", np.cumsum(shocks, axis=-1)
        if "rolling_168h_drift_gaussian" in models_to_run:
            rng = np.random.default_rng(seed + 1006)
            shocks = (
                rng.normal(size=(n_orig, draws, HORIZON)) * local_std[:, None, None]
                + local_mean[:, None, None]
            )
            yield "rolling_168h_drift_gaussian", np.cumsum(shocks, axis=-1)

    for lag_hours, model_name, seed_off in (
        (24, "seasonal_naive_24h", 1007),
        (168, "seasonal_naive_168h", 1008),
    ):
        if model_name not in models_to_run:
            continue
        rng = np.random.default_rng(seed + seed_off)
        residuals = []
        for o in range(lag_hours, max(sub_train_len - HORIZON, lag_hours)):
            if (
                np.isfinite(sub_log_price[o])
                and np.isfinite(sub_log_price[o + 1 : o + HORIZON + 1]).all()
                and np.isfinite(sub_log_price[o - lag_hours])
                and np.isfinite(
                    sub_log_price[o - lag_hours + 1 : o - lag_hours + HORIZON + 1]
                ).all()
            ):
                act = sub_log_price[o + 1 : o + HORIZON + 1] - sub_log_price[o]
                seas = (
                    sub_log_price[o - lag_hours + 1 : o - lag_hours + HORIZON + 1]
                    - sub_log_price[o - lag_hours]
                )
                residuals.append(act - seas)

        point_seas = np.zeros((n_orig, HORIZON), dtype=np.float64)
        for b, orig in enumerate(eval_origins):
            base_idx = orig - lag_hours
            if base_idx >= 0 and np.isfinite(log_price[base_idx]):
                hist_seg = log_price[base_idx + 1 : base_idx + HORIZON + 1]
                point_seas[b] = np.where(np.isfinite(hist_seg), hist_seg - log_price[base_idx], 0.0)
        if len(residuals) >= 16:
            res_bank = np.asarray(residuals, dtype=np.float64)
            choice = rng.integers(len(res_bank), size=(n_orig, draws))
            yield model_name, point_seas[:, None, :] + res_bank[choice]
        else:
            shocks = np.cumsum(rng.normal(scale=scale_std, size=(n_orig, draws, HORIZON)), axis=-1)
            yield model_name, point_seas[:, None, :] + shocks

    if "ewma_iid_gaussian" in models_to_run or "ewma_iid_student_t" in models_to_run:
        sigma_next, t_mult, t_df = _fit_ewma_iid(sub_log_price, sub_train_len, scale_std)
        sig_orig = sigma_next[sub_eval_origins][:, None, None]
        if "ewma_iid_gaussian" in models_to_run:
            rng = np.random.default_rng(seed + 1009)
            yield (
                "ewma_iid_gaussian",
                np.cumsum(rng.normal(size=(n_orig, draws, HORIZON)) * sig_orig, axis=-1),
            )
        if "ewma_iid_student_t" in models_to_run:
            rng = np.random.default_rng(seed + 1010)
            shocks = _unit_variance_student_t(rng, t_df, (n_orig, draws, HORIZON)) * (
                sig_orig * t_mult
            )
            yield "ewma_iid_student_t", np.cumsum(shocks, axis=-1)

    if "ets_ses_gaussian" in models_to_run:
        rng = np.random.default_rng(seed + 1011)
        s_lvl, s_obs = _fit_local_level_gaussian(sub_log_price[:sub_train_len], scale_mad)
        f_mean, f_var, _, _ = _kalman_local_level_filter(sub_log_price, s_lvl, s_obs)
        lvl_diff = (f_mean[sub_eval_origins] - sub_log_price[sub_eval_origins])[:, None]
        p_std = np.sqrt(np.maximum(f_var[sub_eval_origins], 0.0))[:, None]
        l0 = lvl_diff + rng.normal(size=(n_orig, draws)) * p_std
        rw = np.cumsum(rng.normal(scale=s_lvl, size=(n_orig, draws, HORIZON)), axis=-1)
        obs = rng.normal(scale=s_obs, size=(n_orig, draws, HORIZON))
        yield "ets_ses_gaussian", l0[:, :, None] + rw + obs

    if "ets_ses_student_t" in models_to_run or "ets_ewma_student_t" in models_to_run:
        s_lvl_t, s_obs_t, df_t = _fit_local_level_student_t(
            sub_log_price[:sub_train_len], scale_mad
        )
        f_mean_t, f_var_t, innov_t, innov_var_t = _kalman_local_level_filter(
            sub_log_price, s_lvl_t, s_obs_t
        )
        lvl_diff_t = (f_mean_t[sub_eval_origins] - sub_log_price[sub_eval_origins])[:, None]
        p_std_t = np.sqrt(np.maximum(f_var_t[sub_eval_origins], 0.0))[:, None]

        if "ets_ses_student_t" in models_to_run:
            rng = np.random.default_rng(seed + 1012)
            l0 = lvl_diff_t + _unit_variance_student_t(rng, df_t, (n_orig, draws)) * p_std_t
            rw = np.cumsum(
                _unit_variance_student_t(rng, df_t, (n_orig, draws, HORIZON)) * s_lvl_t, axis=-1
            )
            obs = _unit_variance_student_t(rng, df_t, (n_orig, draws, HORIZON)) * s_obs_t
            yield "ets_ses_student_t", l0[:, :, None] + rw + obs

        if "ets_ewma_student_t" in models_to_run:
            rng = np.random.default_rng(seed + 1013)
            mult_next, df_ewma, _ = _kalman_ewma_scale(innov_t, innov_var_t, sub_train_len)
            g = mult_next[sub_eval_origins][:, None]
            l0 = lvl_diff_t + _unit_variance_student_t(rng, df_ewma, (n_orig, draws)) * (
                p_std_t * g
            )
            rw = np.cumsum(
                _unit_variance_student_t(rng, df_ewma, (n_orig, draws, HORIZON))
                * (s_lvl_t * g[:, :, None]),
                axis=-1,
            )
            obs = _unit_variance_student_t(rng, df_ewma, (n_orig, draws, HORIZON)) * (
                s_obs_t * g[:, :, None]
            )
            yield "ets_ewma_student_t", l0[:, :, None] + rw + obs

    if "ets_damped_gaussian" in models_to_run:
        rng = np.random.default_rng(seed + 1014)
        s_lvl, s_slp, phi, s_obs = _fit_damped_trend_gaussian(
            sub_log_price[:sub_train_len], scale_mad
        )
        m0, m1, c00, c01, c11, _ = _kalman_damped_trend_filter(
            sub_log_price, s_lvl, s_slp, phi, s_obs
        )
        states = np.empty((n_orig, draws, 2), dtype=np.float64)
        z_init = rng.normal(size=(n_orig, draws, 2))
        for b, sub_o in enumerate(sub_eval_origins):
            cov = np.array([[c00[sub_o], c01[sub_o]], [c01[sub_o], c11[sub_o]]], dtype=np.float64)
            vals, vecs = np.linalg.eigh(0.5 * (cov + cov.T))
            chol = vecs @ np.diag(np.sqrt(np.clip(vals, 0.0, 1.0)))
            mean_state = np.array([m0[sub_o], m1[sub_o]], dtype=np.float64)
            states[b] = mean_state[None, :] + z_init[b] @ chol.T
        y_base = sub_log_price[sub_eval_origins][:, None]
        paths = np.empty((n_orig, draws, HORIZON), dtype=np.float64)
        for h in range(HORIZON):
            xi = rng.normal(scale=s_lvl, size=(n_orig, draws))
            zeta = rng.normal(scale=s_slp, size=(n_orig, draws))
            next_l = states[:, :, 0] + phi * states[:, :, 1] + xi
            next_b = phi * states[:, :, 1] + zeta
            states[:, :, 0] = next_l
            states[:, :, 1] = next_b
            paths[:, :, h] = next_l + rng.normal(scale=s_obs, size=(n_orig, draws)) - y_base
        yield "ets_damped_gaussian", paths

    if "arima_aicc_gaussian" in models_to_run:
        rng = np.random.default_rng(seed + 1015)
        paths, _ = _simulate_arima_aicc(sub_log_price, sub_train_len, sub_eval_origins, draws, rng)
        yield "arima_aicc_gaussian", paths

    if "ma1_garch11_gaussian" in models_to_run:
        rng = np.random.default_rng(seed + 1016)
        yield (
            "ma1_garch11_gaussian",
            _simulate_ma1_garch11(
                sub_log_price,
                sub_returns,
                sub_train_len,
                sub_eval_origins,
                draws,
                "gaussian",
                scale_std,
                rng,
            ),
        )

    if "ma1_garch11_student_t" in models_to_run:
        rng = np.random.default_rng(seed + 1017)
        yield (
            "ma1_garch11_student_t",
            _simulate_ma1_garch11(
                sub_log_price,
                sub_returns,
                sub_train_len,
                sub_eval_origins,
                draws,
                "student_t",
                scale_std,
                rng,
            ),
        )


def generate_per_item_forecasts(
    panel,
    item_idx: int,
    train_start: int,
    validation_start: int,
    eval_origins: np.ndarray,
    draws: int,
    seed: int,
    *,
    models_to_run: tuple[str, ...] = PER_ITEM_BASELINES,
) -> dict[str, np.ndarray]:
    """Generate [B, M, H] cumulative log-return forecasts for one item strictly causally."""
    return dict(
        iter_per_item_forecasts(
            panel,
            item_idx,
            train_start,
            validation_start,
            eval_origins,
            draws,
            seed,
            models_to_run=models_to_run,
        )
    )


def build_causal_tabular_features(panel, train_start: int, validation_start: int) -> np.ndarray:
    """Build [N_items, T, 24] strictly causal lag/EWMA/microstructure features."""
    n_items, n_times = panel.prices.shape
    tab = np.zeros((n_items, n_times, 24), dtype=np.float32)
    train_mask = (panel.times >= train_start) & (panel.times < validation_start)

    dow_angles = 2.0 * np.pi * ((panel.times // HOUR) % 168) / 168.0
    dow_sin = np.sin(dow_angles).astype(np.float32)
    dow_cos = np.cos(dow_angles).astype(np.float32)

    # Feature indices in panel.features (campaign v2):
    # 0: scaled_return, 1: scaled_log_volume, 2: spread, 3: missing_return,
    # 4: missing_volume, 5: missing_price, 6: hour_sin, 7: hour_cos,
    # 8: bridged_scaled_return, 9: freshness_age_log1p, 10: inverted_side
    has_campaign = panel.features.shape[-1] >= 11

    for i in range(n_items):
        price = panel.prices[i]
        log_p = np.log(price)
        scale_i = float(panel.scale[i])
        train_prices = price[train_mask & np.isfinite(price)]
        log_med_price = math.log(max(float(np.median(train_prices)), 1.0))
        log_scale = math.log(max(scale_i, 1e-4))

        bridged = panel.features[i, :, 8] if has_campaign else panel.features[i, :, 0]
        vol_feat = panel.features[i, :, 1]
        spread_feat = panel.features[i, :, 2]
        miss_price = panel.features[i, :, 5]
        inv_feat = panel.features[i, :, 10] if has_campaign else np.zeros(n_times, dtype=np.float32)
        age_feat = panel.features[i, :, 9] if has_campaign else miss_price

        # Lags of standardized bridged return: 0, 1, 2, 3, 5, 11.
        for col, lag in enumerate((0, 1, 2, 3, 5, 11)):
            if lag == 0:
                tab[i, :, col] = bridged
            else:
                tab[i, lag:, col] = bridged[:-lag]

        # Causal EWMA anchor deviations & realized volatility ratios & liquidity states.
        alphas_anchor = [1.0 - math.exp(-1.0 / tau) for tau in (4.0, 12.0, 24.0, 72.0)]
        norms_anchor = [scale_i * math.sqrt(tau) for tau in (4.0, 12.0, 24.0, 72.0)]
        alphas_vol = [1.0 - math.exp(-1.0 / tau) for tau in (6.0, 24.0, 168.0)]
        alpha_24 = 1.0 - math.exp(-1.0 / 24.0)

        anc = [0.0, 0.0, 0.0, 0.0]
        anc_init = False
        v2 = [1.0, 1.0, 1.0]
        ewma_vol = 0.0
        ewma_miss = 0.0
        ewma_inv = 0.0

        for t in range(n_times):
            lp = float(log_p[t])
            is_ok = math.isfinite(lp)
            b_val = float(bridged[t])
            b_sq = min(b_val * b_val, 36.0)

            if is_ok:
                if not anc_init:
                    anc = [lp, lp, lp, lp]
                    anc_init = True
                else:
                    for k in range(4):
                        anc[k] = (1.0 - alphas_anchor[k]) * anc[k] + alphas_anchor[k] * lp
                for k in range(4):
                    tab[i, t, 6 + k] = (lp - anc[k]) / norms_anchor[k]
                for k in range(3):
                    v2[k] = (1.0 - alphas_vol[k]) * v2[k] + alphas_vol[k] * b_sq
            else:
                for k in range(3):
                    v2[k] = (1.0 - alphas_vol[k]) * v2[k] + alphas_vol[k] * 1.0

            for k in range(3):
                tab[i, t, 10 + k] = math.sqrt(max(v2[k], 1e-4))

            ewma_vol = (1.0 - alpha_24) * ewma_vol + alpha_24 * float(vol_feat[t])
            ewma_miss = (1.0 - alpha_24) * ewma_miss + alpha_24 * float(miss_price[t])
            ewma_inv = (1.0 - alpha_24) * ewma_inv + alpha_24 * float(inv_feat[t])

            tab[i, t, 13] = vol_feat[t]
            tab[i, t, 14] = ewma_vol
            tab[i, t, 15] = np.clip(float(spread_feat[t]) / scale_i, -20.0, 20.0)
            tab[i, t, 16] = age_feat[t]
            tab[i, t, 17] = ewma_miss
            tab[i, t, 18] = ewma_inv

        tab[i, :, 19] = panel.features[i, :, 6]
        tab[i, :, 20] = panel.features[i, :, 7]
        tab[i, :, 21] = dow_sin
        tab[i, :, 22] = dow_cos
        tab[i, :, 23] = log_med_price * 0.1 + log_scale * 0.1

    if not np.isfinite(tab).all():
        raise ValueError("Nonfinite causal tabular baseline features")
    return tab


def _stratified_train_subsample(
    train_origins: np.ndarray, n_items: int, max_rows: int, seed: int
) -> np.ndarray:
    """Deterministically sample up to max_rows training origins balanced across items."""
    if len(train_origins) <= max_rows:
        return train_origins
    rng = np.random.default_rng(seed)
    per_item_cap = max(max_rows // max(n_items, 1), 1)
    selected = []
    for item in range(n_items):
        rows = train_origins[train_origins[:, 0] == item]
        if len(rows) <= per_item_cap:
            selected.append(rows)
        else:
            pick = np.sort(rng.choice(len(rows), per_item_cap, replace=False))
            selected.append(rows[pick])
    merged = np.vstack(selected)
    # Sort chronologically by origin index, then item index, so internal validation splits stay causal.
    order = np.lexsort((merged[:, 0], merged[:, 1]))
    return merged[order]


@dataclass
class FittedPooledModels:
    ridge_weights: np.ndarray  # [25, 24]
    ridge_cov_chol: np.ndarray  # [24, 24]
    ridge_corr_chol: np.ndarray  # [24, 24]
    ridge_std_diag: np.ndarray  # [24]
    ridge_t_df: float
    catboost_models: list | None
    copula_chol: np.ndarray | None
    ridge_alpha: float


def fit_pooled_models(
    panel,
    tab_features: np.ndarray,
    train_origins: np.ndarray,
    seed: int,
    threads: int,
    *,
    include_catboost: bool = True,
    max_train_rows: int = 84_000,
) -> FittedPooledModels:
    """Fit pooled Ridge and CatBoost MultiQuantile + Gaussian rank copula strictly on train."""
    sampled = _stratified_train_subsample(train_origins, len(panel.item_ids), max_train_rows, seed)
    items = sampled[:, 0]
    origins = sampled[:, 1]
    x_all = tab_features[items, origins].astype(np.float64)
    log_p = np.log(panel.prices)
    y_all = np.empty((len(sampled), HORIZON), dtype=np.float64)
    for b, (it, orig) in enumerate(sampled):
        y_all[b] = (log_p[it, orig + 1 : orig + HORIZON + 1] - log_p[it, orig]) / panel.scale[it]

    # Chronological 80/20 split inside purged training origins (with 24h purge gap).
    split_origin = int(np.quantile(origins, 0.80))
    inner_tr = origins + HORIZON < split_origin
    inner_va = origins >= split_origin
    if inner_tr.sum() < 128 or inner_va.sum() < 32:
        cut = max(int(0.8 * len(sampled)), 1)
        inner_tr = np.arange(len(sampled)) < cut
        inner_va = ~inner_tr

    def _fit_ridge_w(x_mat, y_mat, alpha):
        design = np.column_stack([np.ones(len(x_mat)), x_mat])
        gram = design.T @ design
        reg = np.eye(gram.shape[0]) * alpha
        reg[0, 0] = 1e-6
        return linalg.solve(gram + reg, design.T @ y_mat, assume_a="pos")

    best_alpha = 100.0
    best_mse = float("inf")
    x_tr_in, y_tr_in = x_all[inner_tr], y_all[inner_tr]
    x_va_in, y_va_in = x_all[inner_va], y_all[inner_va]
    val_design_in = np.column_stack([np.ones(len(x_va_in)), x_va_in])
    for alpha in (10.0, 100.0, 1000.0, 10_000.0):
        w_try = _fit_ridge_w(x_tr_in, y_tr_in, alpha)
        mse = float(np.mean((y_va_in - val_design_in @ w_try) ** 2))
        if mse < best_mse:
            best_mse = mse
            best_alpha = alpha

    ridge_w = _fit_ridge_w(x_all, y_all, best_alpha)
    full_design = np.column_stack([np.ones(len(x_all)), x_all])
    res_all = y_all - full_design @ ridge_w
    cov = np.cov(res_all, rowvar=False, ddof=1)
    cov = 0.5 * (cov + cov.T) + 1e-5 * np.eye(HORIZON)
    ridge_cov_chol = np.linalg.cholesky(cov)

    std_diag = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std_diag, std_diag)
    corr = 0.96 * (0.5 * (corr + corr.T)) + 0.04 * np.eye(HORIZON)
    np.fill_diagonal(corr, 1.0)
    ridge_corr_chol = np.linalg.cholesky(corr)

    # Fit Student-t df on standardized 1h & 24h Ridge residuals normed by causal 24h vol ratio.
    vol_ratio_all = np.clip(x_all[:, 11], 0.25, 4.0)
    z_res = (
        res_all[:, [0, 3, 23]] / (std_diag[[0, 3, 23]][None, :] * vol_ratio_all[:, None])
    ).ravel()
    if len(z_res) >= 64:

        def _r_nll(param):
            df = 2.2 + math.exp(float(np.clip(param[0], -4.0, 4.2)))
            sc = math.sqrt((df - 2.0) / df)
            zs = z_res / sc
            lp = (
                special.gammaln(0.5 * (df + 1.0))
                - special.gammaln(0.5 * df)
                - 0.5 * math.log(df * math.pi)
                - math.log(sc)
                - 0.5 * (df + 1.0) * np.log1p((zs * zs) / df)
            )
            return -float(np.sum(lp))

        opt = optimize.minimize(
            _r_nll, np.array([math.log(4.0)]), method="L-BFGS-B", bounds=[(-3.5, 4.0)]
        )
        ridge_t_df = 2.2 + math.exp(float(opt.x[0])) if np.all(np.isfinite(opt.x)) else 5.0
    else:
        ridge_t_df = 5.0

    cb_models = None
    copula_chol = None
    if include_catboost:
        try:
            from catboost import CatBoostRegressor
        except ImportError as exc:
            raise ImportError(
                "catboost_multiquantile_copula requires optional catboost package"
            ) from exc

        alpha_str = ",".join(f"{q:.3f}".rstrip("0").rstrip(".") for q in QUANTILE_LEVELS)
        loss_fn = f"MultiQuantile:alpha={alpha_str}"
        cb_models = []
        x_cb = x_all.astype(np.float32)

        # Estimate copula correlation on inner chronological holdout before final full-train refit,
        # or on out-of-sample inner split when large enough, otherwise regularized empirical PIT.
        q_levels_arr = np.asarray(QUANTILE_LEVELS, dtype=np.float64)
        pit_norm = np.empty((len(x_va_in), HORIZON), dtype=np.float64)
        use_inner_copula = len(x_tr_in) >= 2000 and len(x_va_in) >= 500
        x_tr_cb = x_tr_in.astype(np.float32)
        x_va_cb = x_va_in.astype(np.float32)

        for h in range(HORIZON):
            if use_inner_copula:
                cb_in = CatBoostRegressor(
                    loss_function=loss_fn,
                    iterations=120,
                    depth=5,
                    learning_rate=0.08,
                    l2_leaf_reg=5.0,
                    random_seed=seed + 200 + h,
                    thread_count=threads,
                    verbose=False,
                    allow_writing_files=False,
                )
                cb_in.fit(x_tr_cb, y_tr_in[:, h])
                q_va = np.sort(np.asarray(cb_in.predict(x_va_cb), dtype=np.float64), axis=1)
                pit_u = _empirical_quantile_pit(q_va, q_levels_arr, y_va_in[:, h])
                pit_norm[:, h] = stats.norm.ppf(np.clip(pit_u, 1e-4, 1.0 - 1e-4))

            cb_full = CatBoostRegressor(
                loss_function=loss_fn,
                iterations=220,
                depth=5,
                learning_rate=0.06,
                l2_leaf_reg=5.0,
                random_seed=seed + 500 + h,
                thread_count=threads,
                verbose=False,
                allow_writing_files=False,
            )
            cb_full.fit(x_cb, y_all[:, h])
            cb_models.append(cb_full)

        if use_inner_copula and np.isfinite(pit_norm).all():
            c_mat = np.corrcoef(pit_norm, rowvar=False)
            c_mat = np.where(np.isfinite(c_mat), c_mat, 0.0)
            c_mat = 0.92 * (0.5 * (c_mat + c_mat.T)) + 0.08 * np.eye(HORIZON)
            np.fill_diagonal(c_mat, 1.0)
            vals, vecs = np.linalg.eigh(c_mat)
            vals = np.maximum(vals, 1e-4)
            c_pd = vecs @ np.diag(vals) @ vecs.T
            d_inv = 1.0 / np.sqrt(np.diag(c_pd))
            c_pd = c_pd * np.outer(d_inv, d_inv)
            copula_chol = np.linalg.cholesky(c_pd)
        else:
            copula_chol = ridge_corr_chol.copy()

    return FittedPooledModels(
        ridge_weights=ridge_w,
        ridge_cov_chol=ridge_cov_chol,
        ridge_corr_chol=ridge_corr_chol,
        ridge_std_diag=std_diag,
        ridge_t_df=ridge_t_df,
        catboost_models=cb_models,
        copula_chol=copula_chol,
        ridge_alpha=best_alpha,
    )


def _empirical_quantile_pit(q_sorted: np.ndarray, levels: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Invert monotone quantile curve [B, Q] at observed target y [B] into U in (0, 1)."""
    u = np.empty(len(y), dtype=np.float64)
    z01 = float(stats.norm.ppf(levels[0]))
    z10 = float(stats.norm.ppf(levels[3]))
    z90 = float(stats.norm.ppf(levels[-4]))
    z99 = float(stats.norm.ppf(levels[-1]))
    for b in range(len(y)):
        qb = q_sorted[b]
        yb = float(y[b])
        if yb <= qb[0]:
            slope = max((qb[3] - qb[0]) / (z10 - z01), 1e-5)
            z = z01 + (yb - qb[0]) / slope
            u[b] = float(stats.norm.cdf(max(z, -4.5)))
        elif yb >= qb[-1]:
            slope = max((qb[-1] - qb[-4]) / (z99 - z90), 1e-5)
            z = z99 + (yb - qb[-1]) / slope
            u[b] = float(stats.norm.cdf(min(z, 4.5)))
        else:
            u[b] = float(np.interp(yb, qb, levels))
    return u


def _invert_quantiles_with_gaussian_tails(
    q_sorted: np.ndarray, levels: np.ndarray, u_draws: np.ndarray, z_draws: np.ndarray
) -> np.ndarray:
    """Map correlated uniforms u_draws [B, M, H] (and z_draws = Phi^-1(u)) through q_sorted [B, Q, H]."""
    b_sz, m_sz, h_sz = u_draws.shape
    samples = np.empty((b_sz, m_sz, h_sz), dtype=np.float64)
    z_low = float(stats.norm.ppf(levels[0]))
    z_low_ref = float(stats.norm.ppf(levels[3]))
    z_high_ref = float(stats.norm.ppf(levels[-4]))
    z_high = float(stats.norm.ppf(levels[-1]))

    # Vectorize piecewise linear interpolation over quantile grid via searchsorted on levels.
    idx_hi = np.clip(np.searchsorted(levels, u_draws, side="right"), 1, len(levels) - 1)
    idx_lo = idx_hi - 1
    p_lo = levels[idx_lo]
    p_hi = levels[idx_hi]
    frac = (u_draws - p_lo) / np.maximum(p_hi - p_lo, 1e-12)

    q_bhq = np.transpose(q_sorted, (0, 2, 1))  # [B, H, Q]
    idx_lo_bh = np.transpose(idx_lo, (0, 2, 1))  # [B, H, M]
    idx_hi_bh = np.transpose(idx_hi, (0, 2, 1))
    val_lo = np.transpose(np.take_along_axis(q_bhq, idx_lo_bh, axis=2), (0, 2, 1))
    val_hi = np.transpose(np.take_along_axis(q_bhq, idx_hi_bh, axis=2), (0, 2, 1))
    interp = val_lo + frac * (val_hi - val_lo)

    q_min = q_sorted[:, 0:1, :]
    q_low_ref = q_sorted[:, 3:4, :]
    q_high_ref = q_sorted[:, -4:-3, :]
    q_max = q_sorted[:, -1:, :]
    slope_left = np.maximum((q_low_ref - q_min) / (z_low_ref - z_low), 1e-5)
    slope_right = np.maximum((q_max - q_high_ref) / (z_high - z_high_ref), 1e-5)

    left_extrap = q_min + slope_left * (z_draws - z_low)
    right_extrap = q_max + slope_right * (z_draws - z_high)
    samples = np.where(
        u_draws < levels[0],
        left_extrap,
        np.where(u_draws > levels[-1], right_extrap, interp),
    )
    return samples


def generate_pooled_item_forecasts(
    fitted: FittedPooledModels,
    panel,
    tab_features: np.ndarray,
    item_idx: int,
    eval_origins: np.ndarray,
    draws: int,
    seed: int,
) -> tuple[dict[str, np.ndarray], np.ndarray | None]:
    """Generate pooled baseline forecasts [B, M, H] (and direct CatBoost quantiles [B, Q, H]) for one item."""
    n_orig = len(eval_origins)
    scale_i = float(panel.scale[item_idx])
    x_item = tab_features[item_idx, eval_origins].astype(np.float64)
    design = np.column_stack([np.ones(n_orig), x_item])
    y_hat_scaled = design @ fitted.ridge_weights  # [B, H]
    y_hat = y_hat_scaled * scale_i

    out: dict[str, np.ndarray] = {}
    rng_hom = np.random.default_rng(seed + 2001)
    z_hom = rng_hom.normal(size=(n_orig, draws, HORIZON))
    out["ridge_lag_homoskedastic"] = y_hat[:, None, :] + (z_hom @ fitted.ridge_cov_chol.T) * scale_i

    rng_het = np.random.default_rng(seed + 2002)
    vol_ratio = np.clip(x_item[:, 11], 0.25, 4.0)[:, None, None]
    # Multivariate Student-t shock via shared chi-square radial scale per trajectory draw.
    z_corr = rng_het.normal(size=(n_orig, draws, HORIZON)) @ fitted.ridge_corr_chol.T
    df = fitted.ridge_t_df
    chi = rng_het.chisquare(df, size=(n_orig, draws, 1))
    radial = np.sqrt((df - 2.0) / np.maximum(chi, 1e-6))
    t_shocks = z_corr * radial * fitted.ridge_std_diag[None, None, :] * vol_ratio * scale_i
    out["ridge_lag_ewma_student_t"] = y_hat[:, None, :] + t_shocks

    direct_quantiles = None
    if fitted.catboost_models is not None and fitted.copula_chol is not None:
        x_cb = x_item.astype(np.float32)
        q_pred = np.empty((n_orig, len(QUANTILE_LEVELS), HORIZON), dtype=np.float64)
        for h, cb in enumerate(fitted.catboost_models):
            raw_q = np.asarray(cb.predict(x_cb), dtype=np.float64)
            if raw_q.ndim == 1:
                raw_q = raw_q[:, None]
            # Enforce monotone non-crossing quantile order across all 13 levels.
            q_pred[:, :, h] = np.sort(raw_q, axis=1) * scale_i

        rng_cb = np.random.default_rng(seed + 2003)
        z_cop = rng_cb.normal(size=(n_orig, draws, HORIZON)) @ fitted.copula_chol.T
        u_cop = special.ndtr(z_cop)
        levels_arr = np.asarray(QUANTILE_LEVELS, dtype=np.float64)
        out["catboost_multiquantile_copula"] = _invert_quantiles_with_gaussian_tails(
            q_pred, levels_arr, u_cop, z_cop
        )
        direct_quantiles = q_pred

    return out, direct_quantiles


def score_item_forecasts(
    samples: np.ndarray,
    log_price_item: np.ndarray,
    price_item: np.ndarray,
    item_scale: float,
    eval_origins: np.ndarray,
    val_grid_origins: np.ndarray,
    origin_to_grid_pos: dict[int, int],
    complete_mask_eval: np.ndarray,
    seed: int,
    *,
    direct_quantiles: np.ndarray | None = None,
) -> dict:
    """Compute complete_24h, stride_24h, endpoint_marginal, GP-domain, tail, and bootstrap row metrics."""
    n_grid = len(val_grid_origins)
    panel_crps_col = np.full(n_grid, np.nan, dtype=np.float64)
    panel_var_col = np.full(n_grid, np.nan, dtype=np.float64)

    comp_idx = np.flatnonzero(complete_mask_eval)
    comp_origins = eval_origins[comp_idx]
    comp_samples = samples[comp_idx]  # [B_c, M, H]
    n_comp = len(comp_origins)

    result: dict = {
        "n_eval_usable_origins": int(len(eval_origins)),
        "n_complete_24h": int(n_comp),
        "item_scale": float(item_scale),
    }

    if n_comp > 0:
        base_prices = price_item[comp_origins]
        actual_comp = (
            log_price_item[comp_origins[:, None] + np.arange(1, HORIZON + 1)]
            - log_price_item[comp_origins, None]
        )

        crps_unscaled = sample_crps(comp_samples, actual_comp)
        crps_scaled = crps_unscaled / item_scale
        intervals_unscaled = interval_scores(
            comp_samples, actual_comp, alphas=REGISTERED_INTERVAL_ALPHAS
        )
        wis_scaled = intervals_unscaled["wis"] / item_scale

        # Energy score and p=0.5 variogram score are positively homogeneous of degree 1.
        es_unscaled = energy_score(comp_samples, actual_comp)
        es_scaled = es_unscaled / item_scale
        vs_plugin_unscaled, vs_unbiased_unscaled = variogram_score_both(comp_samples, actual_comp)
        vs_plugin_scaled = vs_plugin_unscaled / item_scale
        vs_unbiased_scaled = vs_unbiased_unscaled / item_scale

        shuffled_unscaled = shuffle_horizon_dependence(comp_samples, seed=seed + 77)
        vs_shuffled_unbiased = variogram_score_both(shuffled_unscaled, actual_comp)[1] / item_scale
        del shuffled_unscaled

        pits = pit_values(comp_samples, actual_comp)
        primary_per_origin = crps_scaled[:, [0, 3, 23]].mean(axis=1)

        for b, orig in enumerate(comp_origins):
            pos = origin_to_grid_pos.get(int(orig))
            if pos is not None:
                panel_crps_col[pos] = primary_per_origin[b]
                panel_var_col[pos] = vs_unbiased_scaled[b]

        # Tail event Brier scores on complete_24h.
        prob_abs_r24 = np.mean(np.abs(comp_samples[:, :, 23]) >= TAIL_ABS_R24_THRESHOLD, axis=1)
        obs_abs_r24 = (np.abs(actual_comp[:, 23]) >= TAIL_ABS_R24_THRESHOLD).astype(np.float64)
        brier_abs_r24 = float(np.mean((prob_abs_r24 - obs_abs_r24) ** 2))

        prob_max_exc = np.mean(np.max(comp_samples, axis=2) >= TAIL_MAX_EXCURSION_THRESHOLD, axis=1)
        obs_max_exc = (np.max(actual_comp, axis=1) >= TAIL_MAX_EXCURSION_THRESHOLD).astype(
            np.float64
        )
        brier_max_exc = float(np.mean((prob_max_exc - obs_max_exc) ** 2))

        # GP-domain accuracy at h in {1, 4, 24}.
        gp_samples_sub = base_prices[:, None, None] * np.exp(
            np.clip(comp_samples[:, :, [0, 3, 23]], -5.0, 5.0)
        )
        gp_actual_sub = base_prices[:, None] * np.exp(actual_comp[:, [0, 3, 23]])
        gp_crps_sub = sample_crps(gp_samples_sub, gp_actual_sub)
        gp_med_sub = np.median(gp_samples_sub, axis=1)
        gp_mae_sub = np.abs(gp_med_sub - gp_actual_sub)

        comp_metrics = {
            "primary_scaled_crps_1_4_24": float(np.mean(primary_per_origin)),
            "scaled_wis_1_4_24": float(np.mean(wis_scaled[:, [0, 3, 23]])),
            "scaled_energy": float(np.mean(es_scaled)),
            "scaled_variogram_p05_plugin": float(np.mean(vs_plugin_scaled)),
            "scaled_variogram_p05_unbiased": float(np.mean(vs_unbiased_scaled)),
            "scaled_variogram_shuffled_unbiased": float(np.mean(vs_shuffled_unbiased)),
            "horizon_shuffle_variogram_gain": float(
                np.mean(vs_shuffled_unbiased - vs_unbiased_scaled)
            ),
            "unscaled_energy": float(np.mean(es_unscaled)),
            "unscaled_variogram_p05_plugin": float(np.mean(vs_plugin_unscaled)),
            "unscaled_variogram_p05_unbiased": float(np.mean(vs_unbiased_unscaled)),
            "brier_abs_r24_ge_0p05": brier_abs_r24,
            "event_rate_abs_r24_ge_0p05": float(np.mean(obs_abs_r24)),
            "brier_max_r_ge_log1p03": brier_max_exc,
            "event_rate_max_r_ge_log1p03": float(np.mean(obs_max_exc)),
        }

        nominal_labels = {0.05: "95", 0.1: "90", 0.2: "80", 0.5: "50"}
        for h_pos, hour in enumerate((1, 4, 24)):
            idx = hour - 1
            comp_metrics[f"scaled_crps_h{hour}"] = float(np.mean(crps_scaled[:, idx]))
            comp_metrics[f"unscaled_crps_h{hour}"] = float(np.mean(crps_unscaled[:, idx]))
            comp_metrics[f"scaled_wis_h{hour}"] = float(np.mean(wis_scaled[:, idx]))
            comp_metrics[f"unscaled_wis_h{hour}"] = float(
                np.mean(intervals_unscaled["wis"][:, idx])
            )
            comp_metrics[f"mae_logret_h{hour}"] = float(
                np.mean(np.abs(intervals_unscaled["median"][:, idx] - actual_comp[:, idx]))
            )
            comp_metrics[f"gp_crps_h{hour}"] = float(np.mean(gp_crps_sub[:, h_pos]))
            comp_metrics[f"gp_rel_crps_h{hour}"] = float(
                np.mean(gp_crps_sub[:, h_pos] / base_prices)
            )
            comp_metrics[f"gp_mae_h{hour}"] = float(np.mean(gp_mae_sub[:, h_pos]))
            comp_metrics[f"pit_mean_h{hour}"] = float(np.mean(pits[:, idx]))
            comp_metrics[f"pit_std_h{hour}"] = float(np.std(pits[:, idx], ddof=0))
            hist, _ = np.histogram(pits[:, idx], bins=10, range=(0.0, 1.0))
            comp_metrics[f"pit_l1_h{hour}"] = float(np.sum(np.abs(hist / n_comp - 0.1)))
            for a_idx, alpha in enumerate(REGISTERED_INTERVAL_ALPHAS):
                lbl = nominal_labels[float(alpha)]
                comp_metrics[f"coverage{lbl}_h{hour}"] = float(
                    np.mean(intervals_unscaled["coverage"][a_idx, :, idx])
                )
                comp_metrics[f"scaled_width{lbl}_h{hour}"] = float(
                    np.mean(intervals_unscaled["width"][a_idx, :, idx] / item_scale)
                )
                comp_metrics[f"unscaled_width{lbl}_h{hour}"] = float(
                    np.mean(intervals_unscaled["width"][a_idx, :, idx])
                )

        if direct_quantiles is not None:
            dq_comp = direct_quantiles[comp_idx]
            dq_scores = quantile_interval_scores(
                dq_comp, QUANTILE_LEVELS, actual_comp, alphas=REGISTERED_INTERVAL_ALPHAS
            )
            comp_metrics["direct_quantile_scaled_wis_1_4_24"] = float(
                np.mean(dq_scores["wis"][:, [0, 3, 23]] / item_scale)
            )

        result["complete_24h"] = comp_metrics

        # Non-overlapping 24h stride sensitivity (every 24th grid step -> origin_ts % 86400 == 0).
        stride_sel = (comp_origins % 24) == 0
        if np.any(stride_sel):
            result["stride_24h"] = {
                "n_origins": int(np.sum(stride_sel)),
                "primary_scaled_crps_1_4_24": float(np.mean(primary_per_origin[stride_sel])),
                "scaled_variogram_p05_unbiased": float(np.mean(vs_unbiased_scaled[stride_sel])),
                "coverage90_h24": float(np.mean(intervals_unscaled["coverage"][1, stride_sel, 23])),
            }
        else:
            result["stride_24h"] = None
    else:
        result["complete_24h"] = None
        result["stride_24h"] = None

    # Endpoint marginal cohort for h in {1, 4, 24}: requires usable[t] & usable[t+h] only.
    endpoint_metrics: dict[str, float | int] = {}
    ep_scaled_crps_list = []
    for hour in (1, 4, 24):
        idx = hour - 1
        ep_targets = log_price_item[eval_origins + hour] - log_price_item[eval_origins]
        ep_ok = np.isfinite(ep_targets)
        n_ep = int(np.sum(ep_ok))
        endpoint_metrics[f"n_origins_h{hour}"] = n_ep
        if n_ep > 0:
            sub_s = samples[ep_ok, :, idx : idx + 1]
            sub_t = ep_targets[ep_ok, None]
            c_ep = sample_crps(sub_s, sub_t)[:, 0] / item_scale
            iv_ep = interval_scores(sub_s, sub_t, alphas=(0.1,))
            val_c = float(np.mean(c_ep))
            endpoint_metrics[f"scaled_crps_h{hour}"] = val_c
            endpoint_metrics[f"coverage90_h{hour}"] = float(np.mean(iv_ep["coverage"][0, :, 0]))
            ep_scaled_crps_list.append(val_c)
    if len(ep_scaled_crps_list) == 3:
        endpoint_metrics["primary_scaled_crps_1_4_24"] = float(np.mean(ep_scaled_crps_list))
    result["endpoint_marginal"] = endpoint_metrics
    result["panel_crps_col"] = panel_crps_col
    result["panel_var_col"] = panel_var_col
    return result


def _per_item_worker(args_tuple):
    (
        panel,
        item_idx,
        train_start,
        validation_start,
        eval_origins,
        val_grid_origins,
        complete_mask_eval,
        draws,
        seed,
        models_to_run,
    ) = args_tuple
    origin_to_grid_pos = {int(o): idx for idx, o in enumerate(val_grid_origins)}
    log_price_item = np.log(panel.prices[item_idx])
    price_item = panel.prices[item_idx]
    item_scale = float(panel.scale[item_idx])
    scored = {}
    for name, paths in iter_per_item_forecasts(
        panel,
        item_idx,
        train_start,
        validation_start,
        eval_origins,
        draws,
        seed + item_idx * 31,
        models_to_run=models_to_run,
    ):
        scored[name] = score_item_forecasts(
            paths,
            log_price_item,
            price_item,
            item_scale,
            eval_origins,
            val_grid_origins,
            origin_to_grid_pos,
            complete_mask_eval,
            seed + item_idx * 31,
        )
        del paths
    return item_idx, scored


def _aggregate_item_summaries(
    per_item_records: list[dict],
    item_ids: np.ndarray,
    strata_info: dict,
) -> dict:
    """Aggregate per-item metrics into item-macro, pooled, GP-stratum, manifest-stratum, and 12-item views."""
    active_comp = [r["complete_24h"] for r in per_item_records if r["complete_24h"] is not None]
    if not active_comp:
        raise ValueError("No items with complete_24h validation origins")

    comp_keys = list(active_comp[0].keys())
    macro_comp = {k: float(np.mean([rec[k] for rec in active_comp if k in rec])) for k in comp_keys}

    # Origin-weighted pooled unscaled metrics (for comparison with pilot_results.json).
    weights = np.array(
        [r["n_complete_24h"] for r in per_item_records if r["complete_24h"] is not None],
        dtype=np.float64,
    )
    total_w = float(np.sum(weights))
    pooled_keys = [
        "unscaled_crps_h1",
        "unscaled_crps_h4",
        "unscaled_crps_h24",
        "unscaled_wis_h1",
        "unscaled_wis_h4",
        "unscaled_wis_h24",
        "unscaled_energy",
        "unscaled_variogram_p05_plugin",
        "unscaled_variogram_p05_unbiased",
        "coverage90_h1",
        "coverage90_h4",
        "coverage90_h24",
        "mae_logret_h1",
        "mae_logret_h4",
        "mae_logret_h24",
    ]
    pooled_comp = {
        k: float(np.sum(weights * np.array([rec[k] for rec in active_comp])) / total_w)
        for k in pooled_keys
    }

    # Endpoint marginal macro average & censoring delta.
    ep_recs = [
        r["endpoint_marginal"]
        for r in per_item_records
        if "primary_scaled_crps_1_4_24" in r["endpoint_marginal"]
    ]
    endpoint_macro = {}
    if ep_recs:
        for k in (
            "primary_scaled_crps_1_4_24",
            "scaled_crps_h1",
            "scaled_crps_h4",
            "scaled_crps_h24",
            "coverage90_h1",
            "coverage90_h4",
            "coverage90_h24",
        ):
            endpoint_macro[k] = float(np.mean([rec[k] for rec in ep_recs]))
        endpoint_macro["total_origins_h24"] = int(
            sum(r["endpoint_marginal"]["n_origins_h24"] for r in per_item_records)
        )
        endpoint_macro["censoring_delta_primary_crps_vs_complete24h"] = float(
            endpoint_macro["primary_scaled_crps_1_4_24"] - macro_comp["primary_scaled_crps_1_4_24"]
        )

    # Stride-24h non-overlapping sensitivity.
    st_recs = [r["stride_24h"] for r in per_item_records if r["stride_24h"] is not None]
    stride_macro = (
        {
            "primary_scaled_crps_1_4_24": float(
                np.mean([rec["primary_scaled_crps_1_4_24"] for rec in st_recs])
            ),
            "scaled_variogram_p05_unbiased": float(
                np.mean([rec["scaled_variogram_p05_unbiased"] for rec in st_recs])
            ),
            "coverage90_h24": float(np.mean([rec["coverage90_h24"] for rec in st_recs])),
            "total_origins": int(sum(rec["n_origins"] for rec in st_recs)),
        }
        if st_recs
        else {}
    )

    def _slice_macro(target_ids: set[int]) -> dict:
        sub = [
            per_item_records[pos]["complete_24h"]
            for pos, iid in enumerate(item_ids)
            if int(iid) in target_ids and per_item_records[pos]["complete_24h"] is not None
        ]
        if not sub:
            return {}
        return {
            "item_count": len(sub),
            "primary_scaled_crps_1_4_24": float(
                np.mean([x["primary_scaled_crps_1_4_24"] for x in sub])
            ),
            "scaled_crps_h1": float(np.mean([x["scaled_crps_h1"] for x in sub])),
            "scaled_crps_h4": float(np.mean([x["scaled_crps_h4"] for x in sub])),
            "scaled_crps_h24": float(np.mean([x["scaled_crps_h24"] for x in sub])),
            "scaled_variogram_p05_unbiased": float(
                np.mean([x["scaled_variogram_p05_unbiased"] for x in sub])
            ),
            "coverage90_h1": float(np.mean([x["coverage90_h1"] for x in sub])),
            "coverage90_h4": float(np.mean([x["coverage90_h4"] for x in sub])),
            "coverage90_h24": float(np.mean([x["coverage90_h24"] for x in sub])),
        }

    gp_strata_map = strata_info["gp_notional_strata"]
    man_strata_map = strata_info["manifest_unit_volume_strata"]
    by_gp_stratum = {
        label: _slice_macro({iid for iid, s in gp_strata_map.items() if s == label})
        for label in ("high", "medium", "low")
    }
    by_manifest_stratum = {
        label: _slice_macro({iid for iid, s in man_strata_map.items() if s == label})
        for label in ("high", "medium", "low")
    }
    subset_12_macro = _slice_macro(set(strata_info["representative_12_item_ids"]))

    return {
        "total_complete_24h_origins": int(total_w),
        "macro_complete_24h": macro_comp,
        "pooled_unscaled_complete_24h": pooled_comp,
        "endpoint_marginal_macro": endpoint_macro,
        "stride_24h_macro": stride_macro,
        "by_gp_notional_stratum": by_gp_stratum,
        "by_manifest_unit_volume_stratum": by_manifest_stratum,
        "subset_12_items_macro": subset_12_macro,
    }


def select_strongest_calibrated_baseline(three_fold_summary: dict[str, dict]) -> dict:
    """Apply frozen strongest-calibrated-baseline rule from e1_baseline_protocol.json."""
    eligible = []
    all_candidates = []
    for name, summary in three_fold_summary.items():
        m = summary["macro_complete_24h"]
        covs = (m["coverage90_h1"], m["coverage90_h4"], m["coverage90_h24"])
        max_dev = max(abs(c - 0.90) for c in covs)
        in_gate = all(0.87 <= c <= 0.93 for c in covs)
        entry = {
            "model": name,
            "primary_macro_scaled_crps_1_4_24": m["primary_scaled_crps_1_4_24"],
            "coverage90_h1": covs[0],
            "coverage90_h4": covs[1],
            "coverage90_h24": covs[2],
            "max_abs_coverage90_deviation": max_dev,
            "passes_coverage90_gate_all_horizons": in_gate,
        }
        all_candidates.append(entry)
        if in_gate:
            eligible.append(entry)

    all_candidates.sort(key=lambda d: d["primary_macro_scaled_crps_1_4_24"])
    if eligible:
        eligible.sort(key=lambda d: d["primary_macro_scaled_crps_1_4_24"])
        winner = eligible[0]
        fallback_used = False
    else:
        best_crps = all_candidates[0]["primary_macro_scaled_crps_1_4_24"]
        near_best = [
            d for d in all_candidates if d["primary_macro_scaled_crps_1_4_24"] <= 1.01 * best_crps
        ]
        near_best.sort(
            key=lambda d: (
                d["max_abs_coverage90_deviation"],
                d["primary_macro_scaled_crps_1_4_24"],
            )
        )
        winner = near_best[0]
        fallback_used = True

    return {
        "selected_model": winner["model"],
        "fallback_used": fallback_used,
        "selected_metrics": winner,
        "eligible_calibrated_count": len(eligible),
        "ranked_all_models": all_candidates,
    }


def evaluate_e1_campaign(
    panel_path: str | Path,
    protocol_path: str | Path,
    output_dir: str | Path,
    *,
    report_json_path: str | Path | None = None,
    threads: int = 6,
    draws: int = 256,
    base_seed: int = 11,
    per_item_models: tuple[str, ...] = PER_ITEM_BASELINES,
    include_pooled: bool = True,
    include_catboost: bool = True,
) -> dict:
    """Execute the full chronological 3-fold E1 baseline evaluation and write artifacts."""
    if threads < 1 or threads > 8:
        raise ValueError("threads must lie in 1..8 to preserve workstation responsiveness")
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()

    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    protocol_hash = file_hash(protocol_path)
    frame, manifest, manifest_hash = load_verified_panel(panel_path)
    if manifest["sha256"] != protocol["panel_sha256"]:
        raise ValueError("Panel SHA256 does not match frozen e1_baseline_protocol.json")
    delay_seconds = int(manifest["availability_delay_seconds"])
    strata_info = compute_selection_strata(frame, manifest)

    code_commit, git_dirty = _git_provenance()
    package_freeze = sorted(
        f"{dist.metadata['Name']}=={dist.version}" for dist in importlib.metadata.distributions()
    )
    (output / "environment.txt").write_text("\n".join(package_freeze) + "\n", encoding="utf-8")

    status = {
        "status": "running",
        "experiment_id": "E1",
        "started_unix": started,
        "neural_fit_slots_consumed": 0,
        "threads": threads,
        "draws": draws,
    }
    _json(output / "status.json", status)

    active_models = list(per_item_models)
    if include_pooled:
        active_models.extend(["ridge_lag_homoskedastic", "ridge_lag_ewma_student_t"])
        if include_catboost:
            active_models.append("catboost_multiquantile_copula")

    fold_summaries: dict[int, dict] = {}
    fold_cohort_diagnostics: dict[int, dict] = {}
    concat_crps_panels: dict[str, list[np.ndarray]] = {m: [] for m in active_models}
    concat_var_panels: dict[str, list[np.ndarray]] = {m: [] for m in active_models}

    for fold_id in (1, 2, 3):
        fold_t0 = time.time()
        train_start, val_start, val_end = REGISTERED_FOLDS[fold_id]
        fold_seed = base_seed + fold_id * 1000

        panel = prepare_arrays(
            frame,
            train_start=train_start,
            selection_end=val_start,
            feature_set="campaign",
            availability_delay_seconds=delay_seconds,
        )
        train_origins, val_origins = eligible_origins(
            panel,
            train_start=train_start,
            validation_start=val_start,
            validation_end=val_end,
            delay_seconds=delay_seconds,
        )
        cohort_diag = eligible_origin_diagnostics(
            panel,
            train_start=train_start,
            validation_start=val_start,
            validation_end=val_end,
            delay_seconds=delay_seconds,
        )
        fold_cohort_diagnostics[fold_id] = cohort_diag

        # Contiguous hourly calendar grid of validation origins in this fold.
        cand_origins = np.arange(CONTEXT - 1, len(panel.times) - HORIZON, dtype=np.int64)
        cand_ts = panel.times[cand_origins]
        final_avail = panel.times[cand_origins + HORIZON] + HOUR + delay_seconds
        val_cutoff = min(val_end + HOUR + delay_seconds, HOLDOUT_START)
        val_grid_mask = (cand_ts >= val_start) & (cand_ts < val_end) & (final_avail < val_cutoff)
        val_grid_origins = cand_origins[val_grid_mask]
        n_grid = len(val_grid_origins)
        n_items = len(panel.item_ids)

        valid_returns = np.isfinite(panel.returns)
        bad_prefix = np.concatenate(
            [np.zeros((n_items, 1), dtype=np.int64), np.cumsum(~valid_returns, axis=1)], axis=1
        )

        per_item_by_model: dict[str, list[dict | None]] = {
            m: [None] * n_items for m in active_models
        }
        crps_panel_fold = {
            m: np.full((n_grid, n_items), np.nan, dtype=np.float64) for m in active_models
        }
        var_panel_fold = {
            m: np.full((n_grid, n_items), np.nan, dtype=np.float64) for m in active_models
        }

        if per_item_models:
            worker_tasks = []
            for item_idx in range(n_items):
                usable_at_grid = panel.usable[item_idx, val_grid_origins]
                eval_origins = val_grid_origins[usable_at_grid]
                comp_eval = (
                    bad_prefix[item_idx, eval_origins + HORIZON + 1]
                    - bad_prefix[item_idx, eval_origins + 1]
                ) == 0
                worker_tasks.append(
                    (
                        panel,
                        item_idx,
                        train_start,
                        val_start,
                        eval_origins,
                        val_grid_origins,
                        comp_eval,
                        draws,
                        fold_seed,
                        per_item_models,
                    )
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
                for item_idx, item_res in pool.map(_per_item_worker, worker_tasks):
                    for m_name, m_rec in item_res.items():
                        crps_panel_fold[m_name][:, item_idx] = m_rec.pop("panel_crps_col")
                        var_panel_fold[m_name][:, item_idx] = m_rec.pop("panel_var_col")
                        per_item_by_model[m_name][item_idx] = m_rec

        pooled_meta = {}
        if include_pooled:
            tab_features = build_causal_tabular_features(panel, train_start, val_start)
            fitted_pooled = fit_pooled_models(
                panel,
                tab_features,
                train_origins,
                fold_seed,
                threads,
                include_catboost=include_catboost,
            )
            pooled_meta["ridge_alpha"] = fitted_pooled.ridge_alpha
            pooled_meta["ridge_student_t_df"] = fitted_pooled.ridge_t_df
            origin_to_grid_pos = {int(o): idx for idx, o in enumerate(val_grid_origins)}

            for item_idx in range(n_items):
                usable_at_grid = panel.usable[item_idx, val_grid_origins]
                eval_origins = val_grid_origins[usable_at_grid]
                comp_eval = (
                    bad_prefix[item_idx, eval_origins + HORIZON + 1]
                    - bad_prefix[item_idx, eval_origins + 1]
                ) == 0
                p_forecasts, direct_q = generate_pooled_item_forecasts(
                    fitted_pooled,
                    panel,
                    tab_features,
                    item_idx,
                    eval_origins,
                    draws,
                    fold_seed + item_idx * 31,
                )
                log_price_item = np.log(panel.prices[item_idx])
                price_item = panel.prices[item_idx]
                item_scale = float(panel.scale[item_idx])
                for m_name, paths in p_forecasts.items():
                    dq = direct_q if m_name == "catboost_multiquantile_copula" else None
                    m_rec = score_item_forecasts(
                        paths,
                        log_price_item,
                        price_item,
                        item_scale,
                        eval_origins,
                        val_grid_origins,
                        origin_to_grid_pos,
                        comp_eval,
                        fold_seed + item_idx * 31,
                        direct_quantiles=dq,
                    )
                    crps_panel_fold[m_name][:, item_idx] = m_rec.pop("panel_crps_col")
                    var_panel_fold[m_name][:, item_idx] = m_rec.pop("panel_var_col")
                    per_item_by_model[m_name][item_idx] = m_rec

        # Persist compact loss matrices outside Git for auditability without raw prices.
        np.savez_compressed(
            output / f"fold{fold_id}_loss_panels.npz",
            val_grid_origin_ts=panel.times[val_grid_origins],
            item_ids=panel.item_ids,
            item_scales=panel.scale,
            **{f"crps__{m}": crps_panel_fold[m] for m in active_models},
            **{f"var__{m}": var_panel_fold[m] for m in active_models},
        )

        fold_models_agg = {}
        for m_name in active_models:
            recs = [r for r in per_item_by_model[m_name] if r is not None]
            fold_models_agg[m_name] = _aggregate_item_summaries(recs, panel.item_ids, strata_info)
            concat_crps_panels[m_name].append(crps_panel_fold[m_name])
            concat_var_panels[m_name].append(var_panel_fold[m_name])

        fold_summaries[fold_id] = {
            "fold": fold_id,
            "train_start_unix": train_start,
            "validation_start_unix": val_start,
            "validation_end_exclusive_unix": val_end,
            "elapsed_seconds": time.time() - fold_t0,
            "pooled_hyperparameters": pooled_meta,
            "cohort_diagnostics": cohort_diag,
            "models": fold_models_agg,
        }
        print(
            json.dumps(
                {
                    "event": "fold_completed",
                    "fold": fold_id,
                    "elapsed_seconds": round(fold_summaries[fold_id]["elapsed_seconds"], 2),
                }
            ),
            flush=True,
        )

    # Equal 3-fold aggregation across chronological folds.
    three_fold_models: dict[str, dict] = {}
    for m_name in active_models:
        f_list = [fold_summaries[f]["models"][m_name] for f in (1, 2, 3)]
        macro_keys = list(f_list[0]["macro_complete_24h"].keys())
        macro_mean = {
            k: float(np.mean([f["macro_complete_24h"][k] for f in f_list])) for k in macro_keys
        }
        macro_fold_std = {
            "primary_scaled_crps_1_4_24_fold_std": float(
                np.std([f["macro_complete_24h"]["primary_scaled_crps_1_4_24"] for f in f_list])
            ),
            "primary_scaled_crps_by_fold": [
                float(f["macro_complete_24h"]["primary_scaled_crps_1_4_24"]) for f in f_list
            ],
        }
        pooled_keys = list(f_list[0]["pooled_unscaled_complete_24h"].keys())
        pooled_mean = {
            k: float(np.mean([f["pooled_unscaled_complete_24h"][k] for f in f_list]))
            for k in pooled_keys
        }
        ep_keys = [k for k in f_list[0]["endpoint_marginal_macro"] if not k.startswith("total_")]
        ep_mean = {
            k: float(np.mean([f["endpoint_marginal_macro"][k] for f in f_list])) for k in ep_keys
        }
        st_keys = [k for k in f_list[0]["stride_24h_macro"] if not k.startswith("total_")]
        st_mean = {k: float(np.mean([f["stride_24h_macro"][k] for f in f_list])) for k in st_keys}
        gp_strat_mean = {
            lbl: {
                k: float(np.mean([f["by_gp_notional_stratum"][lbl][k] for f in f_list]))
                for k in f_list[0]["by_gp_notional_stratum"][lbl]
                if k != "item_count"
            }
            for lbl in ("high", "medium", "low")
        }
        man_strat_mean = {
            lbl: {
                k: float(np.mean([f["by_manifest_unit_volume_stratum"][lbl][k] for f in f_list]))
                for k in f_list[0]["by_manifest_unit_volume_stratum"][lbl]
                if k != "item_count"
            }
            for lbl in ("high", "medium", "low")
        }
        sub12_mean = {
            k: float(np.mean([f["subset_12_items_macro"][k] for f in f_list]))
            for k in f_list[0]["subset_12_items_macro"]
            if k != "item_count"
        }

        three_fold_models[m_name] = {
            "macro_complete_24h": macro_mean,
            "fold_dispersion": macro_fold_std,
            "pooled_unscaled_complete_24h": pooled_mean,
            "endpoint_marginal_macro": ep_mean,
            "stride_24h_macro": st_mean,
            "by_gp_notional_stratum": gp_strat_mean,
            "by_manifest_unit_volume_stratum": man_strat_mean,
            "subset_12_items_macro": sub12_mean,
        }

    selection = select_strongest_calibrated_baseline(three_fold_models)
    winner_name = selection["selected_model"]

    # Paired temporal block bootstrap across concatenated 3-fold calendar grid [T_all, 74]
    # (note: fold validation target windows are mutually disjoint; we also check block sensitivities).
    stacked_crps = {m: np.vstack(concat_crps_panels[m]) for m in active_models}
    stacked_var = {m: np.vstack(concat_var_panels[m]) for m in active_models}

    bootstrap_vs_rw: dict[str, dict] = {}
    raw_p_vs_rw = []
    rw_names = []
    if "gaussian_rw_std" in stacked_crps:
        for idx, m_name in enumerate(active_models):
            if m_name == "gaussian_rw_std":
                continue
            b_res = paired_panel_block_bootstrap(
                stacked_crps[m_name],
                stacked_crps["gaussian_rw_std"],
                block_length=168,
                repetitions=2000,
                seed=base_seed + 5000 + idx,
                scheme="moving",
            )
            bootstrap_vs_rw[m_name] = b_res
            raw_p_vs_rw.append(b_res["centered_two_sided_tail"])
            rw_names.append(m_name)
        if raw_p_vs_rw:
            adj_p = holm_adjust(raw_p_vs_rw)
            for m_name, p_adj in zip(rw_names, adj_p, strict=True):
                bootstrap_vs_rw[m_name]["holm_adjusted_two_sided_tail"] = float(p_adj)

    bootstrap_vs_winner: dict[str, dict] = {}
    raw_p_vs_win = []
    win_names = []
    for idx, m_name in enumerate(active_models):
        if m_name == winner_name:
            continue
        b_crps = paired_panel_block_bootstrap(
            stacked_crps[m_name],
            stacked_crps[winner_name],
            block_length=168,
            repetitions=2000,
            seed=base_seed + 6000 + idx,
            scheme="moving",
        )
        b_var = paired_panel_block_bootstrap(
            stacked_var[m_name],
            stacked_var[winner_name],
            block_length=168,
            repetitions=2000,
            seed=base_seed + 7000 + idx,
            scheme="moving",
        )
        bootstrap_vs_winner[m_name] = {"primary_crps": b_crps, "unbiased_variogram": b_var}
        raw_p_vs_win.append(b_crps["centered_two_sided_tail"])
        win_names.append(m_name)
    if raw_p_vs_win:
        adj_p_win = holm_adjust(raw_p_vs_win)
        for m_name, p_adj in zip(win_names, adj_p_win, strict=True):
            bootstrap_vs_winner[m_name]["primary_crps"]["holm_adjusted_two_sided_tail"] = float(
                p_adj
            )

    # Block-length (72h, 336h) & stationary-bootstrap sensitivity for winner vs gaussian_rw_std and runner-up.
    sensitivity_boot = {}
    if "gaussian_rw_std" in stacked_crps and winner_name != "gaussian_rw_std":
        for blk in (72, 168, 336):
            sensitivity_boot[f"winner_vs_gaussian_rw_std_moving_{blk}h"] = (
                paired_panel_block_bootstrap(
                    stacked_crps[winner_name],
                    stacked_crps["gaussian_rw_std"],
                    block_length=blk,
                    repetitions=2000,
                    seed=base_seed + 8000 + blk,
                    scheme="moving",
                )
            )
        sensitivity_boot["winner_vs_gaussian_rw_std_stationary_168h"] = (
            paired_panel_block_bootstrap(
                stacked_crps[winner_name],
                stacked_crps["gaussian_rw_std"],
                block_length=168,
                repetitions=2000,
                seed=base_seed + 8999,
                scheme="stationary",
            )
        )

    elapsed_total = time.time() - started
    aggregate_report = {
        "experiment_id": "E1",
        "completed_at_unix": time.time(),
        "elapsed_wall_seconds": elapsed_total,
        "cpu_threads_used": threads,
        "estimated_cpu_hours_consumed": (elapsed_total * threads) / 3600.0,
        "neural_fit_slots_consumed": 0,
        "panel_sha256": manifest["sha256"],
        "panel_manifest_sha256": manifest_hash,
        "protocol_sha256": protocol_hash,
        "code_commit": code_commit,
        "git_dirty": git_dirty,
        "host": platform.node(),
        "python": platform.python_version(),
        "protected_holdout_start": HOLDOUT_START,
        "holdout_touched": False,
        "sample_paths_per_origin": draws,
        "liquidity_stratification_metadata": {
            "representative_12_item_ids": strata_info["representative_12_item_ids"],
            "gp_notional_strata_counts": {
                lbl: sum(1 for v in strata_info["gp_notional_strata"].values() if v == lbl)
                for lbl in ("high", "medium", "low")
            },
        },
        "strongest_calibrated_baseline": selection,
        "three_fold_mean_summary": three_fold_models,
        "paired_bootstrap_vs_gaussian_rw_std_168h": bootstrap_vs_rw,
        "paired_bootstrap_vs_strongest_baseline_168h": bootstrap_vs_winner,
        "bootstrap_sensitivity_checks": sensitivity_boot,
        "per_fold_summaries": {
            str(f): {k: v for k, v in fold_summaries[f].items() if k != "cohort_diagnostics"}
            for f in (1, 2, 3)
        },
        "per_fold_cohort_survival": {
            str(f): {
                k: v
                for k, v in fold_cohort_diagnostics[f].items()
                if k != "per_item_validation_survival"
            }
            for f in (1, 2, 3)
        },
    }

    _json(output / "e1_summary.json", aggregate_report)
    if report_json_path is not None:
        _json(Path(report_json_path), aggregate_report)

    status.update(
        status="completed",
        elapsed_seconds=elapsed_total,
        strongest_calibrated_baseline=winner_name,
        artifacts_sha256={
            p.name: file_hash(p)
            for p in output.iterdir()
            if p.is_file() and p.name != "status.json"
        },
    )
    _json(output / "status.json", status)
    return aggregate_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-json", default=None)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--num-samples", type=int, default=256)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    summary = evaluate_e1_campaign(
        args.panel,
        args.protocol,
        args.output,
        report_json_path=args.report_json,
        threads=args.threads,
        draws=args.num_samples,
        base_seed=args.seed,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "elapsed_wall_seconds": summary["elapsed_wall_seconds"],
                "strongest_calibrated_baseline": summary["strongest_calibrated_baseline"][
                    "selected_model"
                ],
                "primary_macro_scaled_crps_1_4_24": summary["strongest_calibrated_baseline"][
                    "selected_metrics"
                ]["primary_macro_scaled_crps_1_4_24"],
            }
        )
    )


if __name__ == "__main__":
    main()
