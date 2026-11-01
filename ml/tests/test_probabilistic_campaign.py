"""Unit tests for the E2-E3 neural campaign runner, causal features, and gate verdicts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from osrs_ml.probabilistic_campaign import (  # noqa: E402
    E2_MATCHED_FEATURES,
    E3_PRICE_ONLY_FEATURES,
    build_campaign_panel,
    evaluate_campaign_gates,
    extract_windows,
    run_campaign_fit,
    split_inner_train_val,
)
from osrs_ml.probabilistic_models import build_model  # noqa: E402
from osrs_ml.probabilistic_train import (  # noqa: E402
    HOLDOUT_START,
    HOUR,
    REGISTERED_FOLDS,
    TRAIN_START,
    VALIDATION_START,
    eligible_origins,
)


def _synthetic_frame():
    t0 = VALIDATION_START - 420 * HOUR
    times = np.arange(t0, VALIDATION_START + 90 * HOUR, HOUR)
    rows = []
    for idx, item_id in enumerate((42, 99)):
        phase = 0.3 * idx
        log_p = 4.6 + 0.008 * np.sin(np.arange(len(times)) / 6.0 + phase)
        price = np.exp(log_p)
        rows.append(
            pd.DataFrame(
                {
                    "ts": times,
                    "item_id": item_id,
                    "mid_price": price,
                    "avg_high_price": price * 1.002,
                    "avg_low_price": price * 0.998,
                    "high_price_volume": 250.0 + (np.arange(len(times)) % 12) * 10.0,
                    "low_price_volume": 200.0 + (np.arange(len(times)) % 8) * 10.0,
                    "available_at": times + HOUR + 300,
                    "usable": True,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def test_e2_matched_and_price_only_features_strictly_causal():
    orig = _synthetic_frame()
    pert = orig.copy()
    fut = pert["ts"] >= VALIDATION_START
    pert.loc[fut, ["mid_price", "avg_high_price", "avg_low_price"]] *= 500.0
    pert.loc[fut, ["high_price_volume", "low_price_volume"]] *= 10_000.0

    for fset, expected_cols in (
        ("e2_matched", E2_MATCHED_FEATURES),
        ("e3_price_only", E3_PRICE_ONLY_FEATURES),
    ):
        p1 = build_campaign_panel(orig, feature_set=fset)
        p2 = build_campaign_panel(pert, feature_set=fset)
        assert p1.feature_names == expected_cols
        hist = p1.times < VALIDATION_START
        np.testing.assert_array_equal(p1.features[:, hist], p2.features[:, hist])
        np.testing.assert_array_equal(p1.scale, p2.scale)

        tr, va = eligible_origins(p1)
        ctx_vec, tgt_vec, itm_vec = extract_windows(p1, tr[:5])
        ctx_ref, tgt_ref, itm_ref = p1.windows(tr[:5])
        np.testing.assert_allclose(ctx_vec, ctx_ref, rtol=1e-6, atol=1e-6)
        np.testing.assert_allclose(tgt_vec, tgt_ref, rtol=1e-6, atol=1e-6)
        np.testing.assert_array_equal(itm_vec, itm_ref)

        in_tr, in_va = split_inner_train_val(p1, tr, VALIDATION_START, inner_val_days=3, seed=11)
        assert len(in_tr) > 0 and len(in_va) > 0
        # Verify strict 24h target purge between inner_train and inner_val.
        assert int(in_tr[:, 1].max()) + 24 < int(in_va[:, 1].min())


def test_spline_campaign_v3_roundtrip_and_recursive_19_features():
    pytest.importorskip("nflows")
    torch.manual_seed(17)
    ctx = torch.randn(4, 12, 19)
    tgt = torch.randn(4, 6) * 4.0
    items = torch.tensor([0, 1, 0, 1], dtype=torch.long)

    flow_m = build_model(
        "spline_flow", 19, horizon=6, width=16, item_count=4, spline_variant="campaign_v3"
    )
    enc = flow_m.encoder(ctx, items)
    z, ld_f = flow_m.flow._transform(tgt, context=enc)
    rec, ld_i = flow_m.flow._transform.inverse(z, context=enc)
    torch.testing.assert_close(rec, tgt, rtol=2e-4, atol=2e-4)
    torch.testing.assert_close(ld_f + ld_i, torch.zeros(4), atol=2e-4, rtol=0.0)
    loss = flow_m.loss(ctx, tgt, items)
    loss.backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in flow_m.parameters())
    samp = flow_m.sample(ctx, items, 5)
    assert samp.shape == (4, 5, 6)
    assert torch.isfinite(samp).all()

    rec_m = build_model("recursive_student_t", 19, horizon=6, width=16, item_count=4)
    r_loss = rec_m.loss(ctx, tgt, items)
    r_loss.backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in rec_m.parameters())
    r_samp = rec_m.sample(ctx, items, 5)
    assert r_samp.shape == (4, 5, 6)
    assert torch.isfinite(r_samp).all()


def test_end_to_end_cpu_campaign_fit_and_gate_evaluator(tmp_path):
    # Build minimal verified Fold 1-3 panel strictly < HOLDOUT_START for CPU integration test.
    tr1, va1, _ = REGISTERED_FOLDS[1]
    _, _, va3_end = REGISTERED_FOLDS[3]
    # Sparse 2-item panel covering full grid with deterministic smooth wave.
    times = np.arange(TRAIN_START, va3_end, HOUR)
    frames = []
    for idx, iid in enumerate((10, 20)):
        lp = 5.0 + 0.01 * np.sin(np.arange(len(times)) / (12.0 + idx))
        pr = np.exp(lp)
        frames.append(
            pd.DataFrame(
                {
                    "ts": times,
                    "item_id": iid,
                    "mid_price": pr,
                    "avg_high_price": pr * 1.001,
                    "avg_low_price": pr * 0.999,
                    "high_price_volume": 100.0,
                    "low_price_volume": 100.0,
                    "available_at": times + HOUR + 300,
                    "usable": True,
                }
            )
        )
    df = pd.concat(frames, ignore_index=True)
    panel_file = tmp_path / "hourly.parquet"
    df.to_parquet(panel_file, index=False)
    sha = hashlib.sha256(panel_file.read_bytes()).hexdigest()
    manifest = {
        "sha256": sha,
        "holdout_start": HOLDOUT_START,
        "selection_end_exclusive": VALIDATION_START,
        "start": TRAIN_START,
        "end_exclusive": int(times.max()) + HOUR,
        "quality": {"max_ts": int(times.max())},
        "availability_delay_seconds": 300,
        "gates": {"development_only": True},
        "selected_ids": [10, 20],
        "selected_items": [
            {"item_id": 10, "liquidity_stratum": "high"},
            {"item_id": 20, "liquidity_stratum": "low"},
        ],
    }
    panel_file.with_suffix(".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    specs = [
        {
            "experiment_id": "E2",
            "candidate_id": "direct_marginal_student_t",
            "fit_id": f"t_dm_f{f}_s11",
            "model": "direct_marginal_student_t",
            "feature_set": "e2_matched",
            "fold": f,
            "seed": 11,
        }
        for f in (1, 2, 3)
    ]
    proto = {
        "protected_holdout_start": HOLDOUT_START,
        "panel_sha256": sha,
        "queues": {"cpu_test": specs},
    }
    proto_file = tmp_path / "proto.json"
    proto_file.write_text(json.dumps(proto), encoding="utf-8")

    runs_dir = tmp_path / "runs"
    e1_dir = tmp_path / "e1_runs"
    e1_dir.mkdir()

    for spec in specs:
        st = run_campaign_fit(
            panel_path=panel_file,
            protocol_path=proto_file,
            experiment_id="E2",
            fit_id=spec["fit_id"],
            model_name=spec["model"],
            fold_id=spec["fold"],
            seed=11,
            output_dir=runs_dir / spec["fit_id"],
            device_name="cpu",
            feature_set="e2_matched",
            width=8,
            max_steps=4,
            batch_size=16,
            eval_every=2,
            min_steps=2,
            patience_checks=2,
            num_samples=8,
            torch_threads=1,
            score_threads=1,
        )
        assert st["status"] == "completed"
        assert (
            Path(st["code_tree"]) / "ml" / "src" / "osrs_ml" / "probabilistic_campaign.py"
        ).is_file()
        assert "probabilistic_models.py" in st["source_module_sha256"]
        meta_doc = json.loads((runs_dir / spec["fit_id"] / "metadata.json").read_text())
        assert meta_doc["code_tree"] == st["code_tree"]
        assert meta_doc["authoritative_git_tree"] == "C:/Users/xmart/osrs-phase-one"
        assert meta_doc["source_module_sha256"] == st["source_module_sha256"]
        with np.load(runs_dir / spec["fit_id"] / "loss_panel.npz") as lp:
            # Create synthetic E1 reference panel with identical NaN mask and worse loss.
            np.savez_compressed(
                e1_dir / f"fold{spec['fold']}_loss_panels.npz",
                crps__catboost_multiquantile_copula=lp["crps_panel"] * 1.15,
                var__catboost_multiquantile_copula=lp["var_panel"] * 1.15,
            )

    e1_json = tmp_path / "e1_res.json"
    # Read candidate 3-fold mean so synthetic baseline is +15% higher.
    c_vals = []
    v_vals = []
    for f in (1, 2, 3):
        ev = json.loads((runs_dir / f"t_dm_f{f}_s11" / "fold_eval_summary.json").read_text())
        c_vals.append(ev["macro_complete_24h"]["primary_scaled_crps_1_4_24"])
        v_vals.append(ev["macro_complete_24h"]["scaled_variogram_p05_unbiased"])
    e1_json.write_text(
        json.dumps(
            {
                "strongest_calibrated_baseline": {
                    "selected_model": "catboost_multiquantile_copula"
                },
                "three_fold_mean_summary": {
                    "catboost_multiquantile_copula": {
                        "macro_complete_24h": {
                            "primary_scaled_crps_1_4_24": float(np.mean(c_vals) * 1.15),
                            "scaled_variogram_p05_unbiased": float(np.mean(v_vals) * 1.15),
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    gate_report = evaluate_campaign_gates(
        protocol_path=proto_file,
        runs_roots=[runs_dir],
        e1_runs_dir=e1_dir,
        e1_results_json=e1_json,
        repetitions=100,
    )
    verdict = gate_report["gate_verdicts"]["direct_marginal_student_t"]
    assert verdict["relative_crps_reduction_vs_catboost"] > 0.05
    assert gate_report["fit_slots_completed"] == 3
