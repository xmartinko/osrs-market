import math

import numpy as np
import pytest

from osrs_ml.probabilistic_evaluation import (
    energy_score,
    gaussian_crps,
    interval_scores,
    paired_block_bootstrap,
    random_walk_samples,
    sample_crps,
    shuffle_horizon_dependence,
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


def test_point_forecasts_perfect_and_missed():
    samples = np.full((2, 10, 3), 4.0)
    perfect = np.full((2, 3), 4.0)
    for score in (sample_crps, energy_score, variogram_score):
        np.testing.assert_array_equal(score(samples, perfect), 0)
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
