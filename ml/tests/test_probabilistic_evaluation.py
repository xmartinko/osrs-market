import math

import numpy as np
import pytest

from osrs_ml.probabilistic_evaluation import (
    REGISTERED_INTERVAL_ALPHAS,
    energy_score,
    gaussian_crps,
    holm_adjust,
    interval_scores,
    paired_block_bootstrap,
    paired_panel_block_bootstrap,
    pit_values,
    quantile_interval_scores,
    random_walk_samples,
    sample_crps,
    shuffle_horizon_dependence,
    student_t_crps,
    variogram_score,
)


def test_sorted_crps_matches_brute_force_fair_and_ecdf():
    rng = np.random.default_rng(123)
    samples, targets = rng.normal(size=(3, 9, 4)), rng.normal(size=(3, 4))
    distances = np.abs(samples[:, :, None, :] - samples[:, None, :, :]).sum(axis=(1, 2))
    first = np.abs(samples - targets[:, None, :]).mean(axis=1)
    np.testing.assert_allclose(sample_crps(samples, targets), first - distances / (2 * 9 * 8))
    np.testing.assert_allclose(
        sample_crps(samples, targets, estimator="ecdf"), first - distances / (2 * 9 * 9)
    )
    assert np.all(sample_crps(samples, targets, estimator="ecdf") >= 0)


def test_gaussian_reference_and_iid_sample_convergence():
    expected = (math.sqrt(2) - 1) / math.sqrt(math.pi)
    assert gaussian_crps(0, 1, 0) == pytest.approx(expected)
    np.testing.assert_allclose(gaussian_crps([0, 1], [0, 0], [2, 4]), [2, 3])
    samples = np.random.default_rng(15).normal(size=(1, 100_000, 1))
    assert sample_crps(samples, [[0]])[0, 0] == pytest.approx(expected, abs=0.005)


def test_student_t_crps_matches_large_iid_monte_carlo():
    rng = np.random.default_rng(2026)
    for df, loc, scale, y in ((3.2, 0.4, 1.7, -0.8), (8.5, -1.0, 0.5, 0.2)):
        draws = loc + scale * rng.standard_t(df, size=(1, 120_000, 1))
        mc = sample_crps(draws, [[y]])[0, 0]
        analytic = float(student_t_crps(df, loc, scale, y))
        assert analytic == pytest.approx(mc, abs=0.01)
    assert float(student_t_crps(4.0, 2.5, 0.0, 1.0)) == pytest.approx(1.5)
    with pytest.raises(ValueError):
        student_t_crps(1.0, 0.0, 1.0, 0.0)


def test_point_forecasts_perfect_and_missed():
    samples = np.full((2, 10, 3), 4.0)
    perfect = np.full((2, 3), 4.0)
    for score in (sample_crps, energy_score, variogram_score):
        np.testing.assert_array_equal(score(samples, perfect), 0)
    np.testing.assert_array_equal(variogram_score(samples, perfect, estimator="unbiased"), 0)
    result = interval_scores(samples, perfect)
    np.testing.assert_array_equal(result["wis"], 0)
    assert result["coverage"].all()
    missed = np.full((2, 3), 6.0)
    np.testing.assert_allclose(interval_scores(samples, missed)["wis"], 2)
    np.testing.assert_allclose(sample_crps(samples, missed), 2)
    np.testing.assert_allclose(energy_score(samples, missed), math.sqrt(12))


def test_interval_score_matches_known_symmetric_quantiles():
    # Linear quantiles of this fixture: median=0, central 50% interval=[-1,1].
    samples = np.array([-2, -1, 0, 1, 2], dtype=float)[None, :, None]
    inside = interval_scores(samples, [[0]], alphas=(0.5,))
    assert inside["wis"][0, 0] == pytest.approx(1 / 3)
    assert inside["coverage"].all()
    outside = interval_scores(samples, [[3]], alphas=(0.5,))
    assert outside["wis"][0, 0] == pytest.approx((1.5 + 0.25 * 10) / 1.5)
    assert not outside["coverage"].any()


def test_quantile_interval_scores_and_pit_midrank():
    levels = np.array([0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975])
    q = np.tile(levels[None, :, None] * 10.0, (2, 1, 3))
    targets = np.full((2, 3), 5.0)
    res = quantile_interval_scores(q, levels, targets, alphas=REGISTERED_INTERVAL_ALPHAS)
    assert res["coverage"].shape == (4, 2, 3)
    assert res["coverage"].all()
    crossing = q.copy()
    crossing[0, 1, 0], crossing[0, -2, 0] = 9.0, 1.0
    with pytest.raises(ValueError):
        quantile_interval_scores(crossing, levels, targets, alphas=(0.1,))
    tied_samples = np.zeros((1, 10, 2))
    np.testing.assert_allclose(pit_values(tied_samples, [[0.0, 1.0]]), [[0.5, 1.0]])


def test_energy_disjoint_pairs_formula_and_odd_draw():
    samples = np.arange(15, dtype=float).reshape(1, 5, 3)
    target = np.zeros((1, 3))
    expected = np.linalg.norm(samples, axis=-1).mean() - 0.5 * np.mean(
        [
            np.linalg.norm(samples[0, 0] - samples[0, 1]),
            np.linalg.norm(samples[0, 2] - samples[0, 3]),
        ]
    )
    assert energy_score(samples, target)[0] == pytest.approx(expected)


def test_unbiased_variogram_removes_finite_draw_bias():
    # When samples and targets come from the exact same distribution, population
    # E[(|Y_i - Y_j|^p - E|X_i - X_j|^p)^2] equals Var(|Y_i - Y_j|^p).
    rng = np.random.default_rng(99)
    n_cases, m_draws = 3000, 6
    samples = rng.normal(scale=2.0, size=(n_cases, m_draws, 2))
    targets = rng.normal(scale=2.0, size=(n_cases, 2))
    ref_draws = rng.normal(scale=2.0, size=(200_000, 2))
    pop_score = float(np.var(np.abs(ref_draws[:, 0] - ref_draws[:, 1]) ** 0.5))

    plugin_mean = float(variogram_score(samples, targets, estimator="plugin").mean())
    unbiased_mean = float(variogram_score(samples, targets, estimator="unbiased").mean())
    # Plug-in inflates score by +pop_score / m_draws (~16.7% positive bias at M=6).
    assert plugin_mean - pop_score > 0.12 * pop_score
    assert abs(unbiased_mean - pop_score) < 0.04 * pop_score


def test_shuffle_preserves_marginals_and_exposes_wrong_covariance():
    signs = np.tile(np.array([-1.0, 1.0]), 1000)
    joint = np.broadcast_to(signs[None, :, None], (2, 2000, 3)).copy()
    shuffled = shuffle_horizon_dependence(joint, seed=3)
    np.testing.assert_array_equal(np.sort(joint, axis=1), np.sort(shuffled, axis=1))
    targets = np.array([[1, 1, 1], [-1, -1, -1]], dtype=float)
    np.testing.assert_array_equal(sample_crps(joint, targets), sample_crps(shuffled, targets))
    np.testing.assert_array_equal(
        interval_scores(joint, targets)["wis"], interval_scores(shuffled, targets)["wis"]
    )
    np.testing.assert_array_equal(variogram_score(joint, targets), 0)
    assert np.all(variogram_score(shuffled, targets) > 1)
    # This synthetic covariance diagnostic is not evidence of market skill.
    np.testing.assert_array_equal(shuffle_horizon_dependence(joint, seed=3), shuffled)


def test_random_walk_controls_use_history_only_and_seeded_draws():
    history = np.array([[-2, 0, 2], [10, 10, 10]], dtype=float)
    gaussian = random_walk_samples(history, horizon=4, draws=30_000, seed=9)
    assert gaussian.shape == (2, 30_000, 4)
    assert abs(gaussian[0].mean()) < 0.03
    np.testing.assert_array_equal(gaussian[1], 0)
    empirical = random_walk_samples(history, horizon=4, draws=20, family="empirical", seed=9)
    assert set(np.unique(empirical[0])) <= {-2, 0, 2}
    np.testing.assert_array_equal(empirical[1], 0)
    drift = random_walk_samples(
        history, horizon=4, draws=20, family="empirical", seed=9, drift=True
    )
    np.testing.assert_array_equal(drift[1], 10)
    cumulative = random_walk_samples(
        history, horizon=4, draws=20, family="empirical", seed=9, cumulative=True
    )
    np.testing.assert_array_equal(cumulative, np.cumsum(empirical, axis=-1))


def test_bootstrap_preserves_cross_section_and_detects_known_effect():
    rng = np.random.default_rng(32)
    temporal = rng.normal(0, 0.05, 120)
    first = np.column_stack([temporal - 1, temporal + 1])
    second = np.ones_like(first)
    result = paired_block_bootstrap(first, second, block_length=7, repetitions=300, seed=42)
    aggregated = paired_block_bootstrap(
        first.mean(axis=1), second.mean(axis=1), block_length=7, repetitions=300, seed=42
    )
    np.testing.assert_allclose(result["bootstrap_means"], aggregated["bootstrap_means"])
    assert result["interval"][1] < 0
    assert result["diagnostic_only"]
    null = paired_block_bootstrap(first, first, block_length=7, repetitions=300)
    np.testing.assert_array_equal(null["interval"], [0, 0])
    assert null["centered_two_sided_tail"] == 1


def test_paired_panel_block_bootstrap_handles_incomplete_panels_and_holm():
    rng = np.random.default_rng(77)
    base = 1.0 + rng.normal(0, 0.04, size=(180, 5))
    cand = base * 0.85
    # Inject both simultaneous outage rows (all items NaN) and idiosyncratic item NaNs.
    base[40:48, :] = np.nan
    cand[40:48, :] = np.nan
    base[10:25, 2] = np.nan
    cand[10:25, 2] = np.nan

    moving = paired_panel_block_bootstrap(
        cand, base, block_length=12, repetitions=400, seed=11, scheme="moving"
    )
    stat = paired_panel_block_bootstrap(
        cand, base, block_length=12, repetitions=400, seed=11, scheme="stationary"
    )
    assert moving["difference_interval"][1] < 0
    assert moving["relative_gain_interval"][0] > 0.10
    assert stat["difference_interval"][1] < 0
    assert moving["active_items"] == 5

    mismatched = cand.copy()
    mismatched[0, 0] = np.nan
    with pytest.raises(ValueError, match="identical missingness"):
        paired_panel_block_bootstrap(mismatched, base, block_length=12)

    adjusted = holm_adjust([0.04, 0.005, 0.20, 0.015])
    np.testing.assert_allclose(adjusted, [0.08, 0.02, 0.20, 0.045])


@pytest.mark.parametrize("scorer", [sample_crps, energy_score, variogram_score, interval_scores])
def test_score_shape_and_missingness_rejected(scorer):
    with pytest.raises(ValueError):
        scorer(np.ones((2, 4, 3)), np.ones((2, 4)))
    with pytest.raises(ValueError):
        scorer(np.full((2, 4, 3), np.nan), np.ones((2, 3)))


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        sample_crps(np.ones((1, 1, 1)), [[1]])
    np.testing.assert_array_equal(sample_crps(np.ones((1, 1, 1)), [[2]], estimator="ecdf"), [[1]])
    with pytest.raises(ValueError):
        interval_scores(np.ones((1, 2, 1)), [[1]], alphas=(0.1, 0.1))
    with pytest.raises(ValueError):
        paired_block_bootstrap([1], [0], block_length=2)
    with pytest.raises(ValueError):
        gaussian_crps(0, -1, 0)
    with pytest.raises(ValueError):
        variogram_score(np.ones((1, 2, 2)), [[1, 1]], weights=[[0, 1], [2, 0]])
    with pytest.raises(ValueError):
        variogram_score(np.ones((1, 1, 2)), [[1, 1]], estimator="unbiased")
