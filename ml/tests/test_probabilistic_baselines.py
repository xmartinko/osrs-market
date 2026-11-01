"""Synthetic causal-invariance and numerical-contract tests for E1 baselines."""

import builtins
import importlib.util

import numpy as np
import pandas as pd
import pytest

from osrs_ml.probabilistic_baselines import (
    PER_ITEM_BASELINES,
    build_causal_tabular_features,
    fit_pooled_models,
    generate_per_item_forecasts,
    generate_pooled_item_forecasts,
    score_item_forecasts,
    select_strongest_calibrated_baseline,
)
from osrs_ml.probabilistic_train import (
    HORIZON,
    HOUR,
    VALIDATION_START,
    eligible_origins,
    prepare_arrays,
)

HAS_STATSMODELS = importlib.util.find_spec("statsmodels") is not None
HAS_ARCH = importlib.util.find_spec("arch") is not None
HAS_CATBOOST = importlib.util.find_spec("catboost") is not None


def _synthetic_baseline_frame(items=(10, 20)):
    rng = np.random.default_rng(2026)
    times = np.arange(VALIDATION_START - 420 * HOUR, VALIDATION_START + 96 * HOUR, HOUR)
    rows = []
    for idx, item_id in enumerate(items):
        shocks = rng.normal(0.0, 0.008 * (idx + 1), size=len(times))
        # Add realistic negative MA(1) bounce: r_t = eps_t - 0.35 * eps_{t-1}.
        bounce_ret = shocks - 0.35 * np.r_[0.0, shocks[:-1]]
        price = (200.0 * (idx + 1)) * np.exp(np.cumsum(bounce_ret))
        usable = np.ones(len(times), dtype=bool)
        # Inject missing/unusable hours in both train and validation.
        usable[80] = False
        usable[440] = False
        rows.append(
            pd.DataFrame(
                {
                    "ts": times,
                    "item_id": item_id,
                    "mid_price": price,
                    "avg_high_price": price * 1.002,
                    "avg_low_price": price * 0.998,
                    "high_price_volume": 500 + (np.arange(len(times)) * 7) % 100,
                    "low_price_volume": 450 + (np.arange(len(times)) * 5) % 100,
                    "available_at": times + HOUR + 300,
                    "usable": usable,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def test_per_item_baselines_are_strictly_invariant_to_future_validation_perturbations():
    frame_a = _synthetic_baseline_frame(items=(10,))
    target_eval_ts = VALIDATION_START + 30 * HOUR

    # Perturb everything strictly after target_eval_ts by 500x!
    frame_b = frame_a.copy()
    future = frame_b["ts"] > target_eval_ts
    frame_b.loc[future, ["mid_price", "avg_high_price", "avg_low_price"]] *= 500.0
    frame_b.loc[future, ["high_price_volume", "low_price_volume"]] *= 10_000

    train_start = int(frame_a["ts"].min())
    panel_a = prepare_arrays(frame_a, train_start=train_start, selection_end=VALIDATION_START)
    panel_b = prepare_arrays(frame_b, train_start=train_start, selection_end=VALIDATION_START)
    eval_origin_idx = int(np.flatnonzero(panel_a.times == target_eval_ts)[0])
    eval_origins = np.array([eval_origin_idx], dtype=np.int64)

    models = [
        m
        for m in PER_ITEM_BASELINES
        if (m != "arima_aicc_gaussian" or HAS_STATSMODELS)
        and (not m.startswith("ma1_garch11") or HAS_ARCH)
    ]

    pred_a = generate_per_item_forecasts(
        panel_a,
        0,
        train_start,
        VALIDATION_START,
        eval_origins,
        draws=32,
        seed=55,
        models_to_run=tuple(models),
    )
    pred_b = generate_per_item_forecasts(
        panel_b,
        0,
        train_start,
        VALIDATION_START,
        eval_origins,
        draws=32,
        seed=55,
        models_to_run=tuple(models),
    )
    assert set(pred_a.keys()) == set(models)
    for name in models:
        assert pred_a[name].shape == (1, 32, HORIZON)
        assert np.isfinite(pred_a[name]).all()
        np.testing.assert_array_equal(pred_a[name], pred_b[name], err_msg=f"Leakage in {name}")


def test_pooled_baselines_causal_invariance_and_noncrossing_quantiles():
    frame_a = _synthetic_baseline_frame(items=(10, 20))
    target_eval_ts = VALIDATION_START + 25 * HOUR
    frame_b = frame_a.copy()
    future = frame_b["ts"] > target_eval_ts
    frame_b.loc[future, ["mid_price", "avg_high_price", "avg_low_price"]] *= 250.0

    train_start = int(frame_a["ts"].min())
    val_end = int(frame_a["ts"].max()) + HOUR
    panel_a = prepare_arrays(frame_a, train_start=train_start, selection_end=VALIDATION_START)
    panel_b = prepare_arrays(frame_b, train_start=train_start, selection_end=VALIDATION_START)

    tab_a = build_causal_tabular_features(panel_a, train_start, VALIDATION_START)
    tab_b = build_causal_tabular_features(panel_b, train_start, VALIDATION_START)
    eval_idx = int(np.flatnonzero(panel_a.times == target_eval_ts)[0])
    np.testing.assert_array_equal(tab_a[:, : eval_idx + 1], tab_b[:, : eval_idx + 1])

    tr_a, _ = eligible_origins(
        panel_a, train_start=train_start, validation_start=VALIDATION_START, validation_end=val_end
    )
    tr_b, _ = eligible_origins(
        panel_b, train_start=train_start, validation_start=VALIDATION_START, validation_end=val_end
    )
    np.testing.assert_array_equal(tr_a, tr_b)

    fit_a = fit_pooled_models(
        panel_a, tab_a, tr_a, seed=17, threads=2, include_catboost=HAS_CATBOOST, max_train_rows=400
    )
    fit_b = fit_pooled_models(
        panel_b, tab_b, tr_b, seed=17, threads=2, include_catboost=HAS_CATBOOST, max_train_rows=400
    )

    eval_origins = np.array([eval_idx], dtype=np.int64)
    out_a, dq_a = generate_pooled_item_forecasts(
        fit_a, panel_a, tab_a, 0, eval_origins, draws=32, seed=91
    )
    out_b, dq_b = generate_pooled_item_forecasts(
        fit_b, panel_b, tab_b, 0, eval_origins, draws=32, seed=91
    )
    for name in out_a:
        assert np.isfinite(out_a[name]).all()
        np.testing.assert_array_equal(out_a[name], out_b[name], err_msg=f"Leakage in {name}")
    if HAS_CATBOOST:
        assert dq_a is not None and dq_b is not None
        assert np.all(np.diff(dq_a, axis=1) >= 0.0)
        np.testing.assert_array_equal(dq_a, dq_b)


def test_endpoint_marginal_cohort_admits_intermediate_gaps_and_selection_gate():
    frame = _synthetic_baseline_frame(items=(10,))
    train_start = int(frame["ts"].min())
    panel = prepare_arrays(frame, train_start=train_start, selection_end=VALIDATION_START)
    # In _synthetic_baseline_frame, index 440 is unusable!
    # Therefore origin 438 has h=1 (439) usable, h=2 (440) unusable, h=4 (442) usable, h=24 (462) usable:
    # origin 438 MUST be excluded from complete_24h, yet admitted at h=1, 4, 24 in endpoint_marginal!
    val_grid = np.array([438, 445], dtype=np.int64)
    comp_mask = np.array([False, True], dtype=bool)
    samples = np.random.default_rng(7).normal(scale=0.01, size=(2, 32, HORIZON))
    rec = score_item_forecasts(
        samples,
        np.log(panel.prices[0]),
        panel.prices[0],
        float(panel.scale[0]),
        val_grid,
        val_grid,
        {438: 0, 445: 1},
        comp_mask,
        seed=7,
    )
    assert rec["n_complete_24h"] == 1
    assert rec["endpoint_marginal"]["n_origins_h1"] == 2
    assert rec["endpoint_marginal"]["n_origins_h4"] == 2
    assert rec["endpoint_marginal"]["n_origins_h24"] == 2
    assert np.isnan(rec["panel_crps_col"][0]) and np.isfinite(rec["panel_crps_col"][1])

    mock_summary = {
        "overconfident_sharp": {
            "macro_complete_24h": {
                "primary_scaled_crps_1_4_24": 0.80,
                "coverage90_h1": 0.72,
                "coverage90_h4": 0.75,
                "coverage90_h24": 0.78,
            }
        },
        "calibrated_strong": {
            "macro_complete_24h": {
                "primary_scaled_crps_1_4_24": 0.83,
                "coverage90_h1": 0.895,
                "coverage90_h4": 0.902,
                "coverage90_h24": 0.910,
            }
        },
        "calibrated_weaker": {
            "macro_complete_24h": {
                "primary_scaled_crps_1_4_24": 0.91,
                "coverage90_h1": 0.900,
                "coverage90_h4": 0.900,
                "coverage90_h24": 0.900,
            }
        },
    }
    sel = select_strongest_calibrated_baseline(mock_summary)
    assert sel["selected_model"] == "calibrated_strong"
    assert not sel["fallback_used"]


def test_optional_dependencies_raise_explicit_importerror(monkeypatch):
    frame = _synthetic_baseline_frame(items=(10,))
    train_start = int(frame["ts"].min())
    panel = prepare_arrays(frame, train_start=train_start, selection_end=VALIDATION_START)
    eval_origins = np.array([425], dtype=np.int64)
    original_import = builtins.__import__

    def block_pkgs(name, *args, **kwargs):
        if name.split(".")[0] in {"statsmodels", "arch", "catboost"}:
            raise ModuleNotFoundError(f"blocked {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_pkgs)
    with pytest.raises(ImportError, match="statsmodels"):
        generate_per_item_forecasts(
            panel,
            0,
            train_start,
            VALIDATION_START,
            eval_origins,
            draws=8,
            seed=1,
            models_to_run=("arima_aicc_gaussian",),
        )
    with pytest.raises(ImportError, match="arch"):
        generate_per_item_forecasts(
            panel,
            0,
            train_start,
            VALIDATION_START,
            eval_origins,
            draws=8,
            seed=1,
            models_to_run=("ma1_garch11_gaussian",),
        )
    tab = build_causal_tabular_features(panel, train_start, VALIDATION_START)
    tr, _ = eligible_origins(panel, train_start=train_start, validation_start=VALIDATION_START)
    with pytest.raises(ImportError, match="catboost"):
        fit_pooled_models(
            panel, tab, tr, seed=1, threads=1, include_catboost=True, max_train_rows=80
        )
