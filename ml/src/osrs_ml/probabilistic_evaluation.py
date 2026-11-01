"""CPU sample scores. Shapes: samples [batch, draw, horizon], targets [batch, horizon].

Inputs are scored in their supplied units. Convert normalized increments to cumulative
returns *before* calling these functions when scoring cumulative-return forecasts.
No function pools items or horizons silently. Lower scores are better.
"""

import math

import numpy as np

INTERVAL_ALPHAS = (0.1, 0.2, 0.5)


def _validated(samples, targets):
    samples = np.asarray(samples, dtype=np.float64)
    targets = np.asarray(targets, dtype=np.float64)
    if samples.ndim != 3 or targets.shape != (samples.shape[0], samples.shape[2]):
        raise ValueError("Expected samples [B,M,H] and targets [B,H]")
    if min(samples.shape) < 1 or not np.isfinite(samples).all() or not np.isfinite(targets).all():
        raise ValueError("Inputs must be nonempty and finite; missingness needs an explicit mask")
    return samples, targets


def sample_crps(samples, targets, *, estimator="fair"):
    """Return [B,H] CRPS in O(B H M log M) time and O(B H M) memory.

    ``fair`` uses the off-diagonal U-statistic, unbiased for population CRPS
    when draws are IID conditional on the forecast. It requires M >= 2 and an
    individual realization may be negative. ``ecdf`` scores the finite empirical
    distribution itself (includes self-pairs); it is nonnegative but biased as
    an estimator of the underlying continuous-distribution CRPS.
    """
    samples, targets = _validated(samples, targets)
    count = samples.shape[1]
    if estimator not in {"fair", "ecdf"} or (estimator == "fair" and count < 2):
        raise ValueError("Use fair with at least two draws, or ecdf")
    ordered = np.sort(samples, axis=1)
    coefficients = (2 * np.arange(count) - count + 1)[None, :, None]
    denominator = count * (count - 1) if estimator == "fair" else count * count
    pair_term = np.sum(ordered * coefficients, axis=1) / denominator
    return np.mean(np.abs(samples - targets[:, None, :]), axis=1) - pair_term


def gaussian_crps(mean, scale, targets):
    """Analytic univariate Gaussian CRPS; zero scale gives absolute error."""
    mean, scale, targets = np.broadcast_arrays(
        np.asarray(mean, dtype=float),
        np.asarray(scale, dtype=float),
        np.asarray(targets, dtype=float),
    )
    if not all(np.isfinite(a).all() for a in (mean, scale, targets)) or np.any(scale < 0):
        raise ValueError("Gaussian parameters must be finite, with nonnegative scale")
    safe_scale = np.where(scale > 0, scale, 1)
    z = (targets - mean) / safe_scale
    cdf = 0.5 * (1 + np.vectorize(math.erf, otypes=[float])(z / math.sqrt(2)))
    density = np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    score = safe_scale * (z * (2 * cdf - 1) + 2 * density - 1 / math.sqrt(math.pi))
    return np.where(scale > 0, score, np.abs(targets - mean))


def interval_scores(samples, targets, *, alphas=INTERVAL_ALPHAS):
    """Fixed-level WIS [B,H], coverage and widths [K,B,H].

    Levels must be registered before comparison. NumPy linear sample quantiles
    approximate population quantiles; WIS is proper for the supplied quantile
    forecasts, not an unbiased Monte Carlo estimator of a latent model's WIS.
    """
    samples, targets = _validated(samples, targets)
    alphas = np.asarray(alphas, dtype=float)
    if (
        alphas.ndim != 1
        or len(alphas) == 0
        or not np.isfinite(alphas).all()
        or np.any((alphas <= 0) | (alphas >= 1))
        or len(np.unique(alphas)) != len(alphas)
    ):
        raise ValueError("Interval alphas must be unique values strictly between zero and one")
    lower = np.quantile(samples, alphas / 2, axis=1, method="linear")
    upper = np.quantile(samples, 1 - alphas / 2, axis=1, method="linear")
    width = upper - lower
    interval = width + 2 / alphas[:, None, None] * (
        np.maximum(lower - targets, 0) + np.maximum(targets - upper, 0)
    )
    median = np.quantile(samples, 0.5, axis=1, method="linear")
    wis = (
        0.5 * np.abs(median - targets) + np.sum(alphas[:, None, None] / 2 * interval, axis=0)
    ) / (len(alphas) + 0.5)
    return {
        "wis": wis,
        "coverage": (targets >= lower) & (targets <= upper),
        "width": width,
        "alphas": alphas,
        "median": median,
    }


def energy_score(samples, targets):
    """Unbiased population energy-score estimate [B] using disjoint draw pairs.

    Requires IID draws and M >= 2. O(B M H), without an M-by-M distance matrix.
    Pair-term Monte Carlo variance is higher than an all-pairs U-statistic;
    compare models using the same draw count and multiple sampling seeds.
    """
    samples, targets = _validated(samples, targets)
    pairs = samples.shape[1] // 2
    if pairs < 1:
        raise ValueError("Energy score requires at least two draws")
    pair_distance = np.linalg.norm(
        samples[:, : 2 * pairs : 2] - samples[:, 1 : 2 * pairs : 2], axis=-1
    )
    return np.linalg.norm(samples - targets[:, None, :], axis=-1).mean(
        axis=1
    ) - 0.5 * pair_distance.mean(axis=1)


def variogram_score(samples, targets, *, power=0.5, weights=None):
    """Return [B] variogram score, summing each unordered horizon pair once.

    Default power .5. Horizon scaling must be frozen across models. This is a
    proper but not strictly proper score; its finite-sample plug-in square has
    Monte Carlo bias. Use common draw counts and report MC sensitivity.
    """
    samples, targets = _validated(samples, targets)
    horizon = samples.shape[2]
    if not np.isfinite(power) or not 0 < power < 2:
        raise ValueError("Variogram power must lie strictly between zero and two")
    weights = np.ones((horizon, horizon)) if weights is None else np.asarray(weights, dtype=float)
    if (
        weights.shape != (horizon, horizon)
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
        or not np.allclose(weights, weights.T)
    ):
        raise ValueError("Weights must be a finite nonnegative symmetric [H,H] matrix")
    result = np.zeros(samples.shape[0])
    for left in range(horizon):
        for right in range(left + 1, horizon):
            forecast = np.mean(np.abs(samples[:, :, left] - samples[:, :, right]) ** power, axis=1)
            observed = np.abs(targets[:, left] - targets[:, right]) ** power
            result += weights[left, right] * (observed - forecast) ** 2
    return result


def shuffle_horizon_dependence(samples, *, seed=0):
    """Preserve every empirical marginal while destroying draw-level alignment."""
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 3 or min(samples.shape) < 1 or not np.isfinite(samples).all():
        raise ValueError("Expected nonempty finite [B,M,H] samples")
    rng = np.random.default_rng(seed)
    result = samples.copy()
    for batch in range(samples.shape[0]):
        for horizon in range(samples.shape[2]):
            result[batch, :, horizon] = samples[batch, rng.permutation(samples.shape[1]), horizon]
    return result


def random_walk_samples(
    history_increments, *, horizon, draws, family="gaussian", seed=0, drift=False, cumulative=False
):
    """Zero-drift Gaussian or empirical-innovation RW, conditioned on history only.

    History is finite [B,L] increments, L >= 2. Gaussian uses sample variance;
    empirical independently resamples centered historical increments, retaining
    tails but not serial dependence. ``drift=True`` uses the historical mean.
    Output [B,M,H] increments, or cumulative increments if explicitly requested.
    """
    history = np.asarray(history_increments, dtype=float)
    if (
        history.ndim != 2
        or history.shape[0] < 1
        or history.shape[1] < 2
        or not np.isfinite(history).all()
    ):
        raise ValueError("History must be finite [B,L] with L >= 2")
    if (
        not isinstance(horizon, (int, np.integer))
        or not isinstance(draws, (int, np.integer))
        or horizon < 1
        or draws < 1
        or family not in {"gaussian", "empirical"}
    ):
        raise ValueError("Positive integer horizon/draws and gaussian/empirical family required")
    rng = np.random.default_rng(seed)
    mean = history.mean(axis=1, keepdims=True)
    if family == "gaussian":
        result = (
            rng.normal(size=(history.shape[0], draws, horizon))
            * history.std(axis=1, ddof=1)[:, None, None]
        )
    else:
        indices = rng.integers(history.shape[1], size=(history.shape[0], draws, horizon))
        result = np.take_along_axis((history - mean)[:, None, :], indices, axis=2)
    if drift:
        result += mean[:, :, None]
    return np.cumsum(result, axis=2) if cumulative else result


def paired_block_bootstrap(
    loss_a, loss_b, *, block_length, repetitions=2000, confidence=0.95, seed=0
):
    """Exploratory paired circular-block bootstrap of mean loss_a - loss_b.

    Input [time,item] (or [time]) requires aligned finite observations. Aggregate
    the full cross-section first, then resample contiguous time blocks together.
    Negative differences favor A. This diagnostic does not correct multiplicity
    or supply evidence from independent regimes; freeze block length upstream.
    """
    first, second = np.asarray(loss_a, dtype=float), np.asarray(loss_b, dtype=float)
    if (
        first.shape != second.shape
        or first.ndim not in (1, 2)
        or first.size == 0
        or not np.isfinite(first).all()
        or not np.isfinite(second).all()
    ):
        raise ValueError("Paired losses must have matching nonempty finite [T] or [T,N] shape")
    count = len(first)
    if (
        not isinstance(block_length, (int, np.integer))
        or not 1 <= block_length <= count
        or not isinstance(repetitions, (int, np.integer))
        or repetitions < 2
        or not 0 < confidence < 1
    ):
        raise ValueError(
            "Require 1 <= integer block length <= T, repetitions >= 2, 0 < confidence < 1"
        )
    difference = first - second
    temporal = difference if first.ndim == 1 else difference.mean(axis=1)
    estimate = temporal.mean()
    rng = np.random.default_rng(seed)
    means = np.empty(repetitions)
    blocks = math.ceil(count / block_length)
    offsets = np.arange(block_length)
    for repetition in range(repetitions):
        starts = rng.integers(count, size=blocks)
        indices = ((starts[:, None] + offsets) % count).ravel()[:count]
        means[repetition] = temporal[indices].mean()
    alpha = (1 - confidence) / 2
    # Centered bootstrap approximates the null; this is not a confirmatory p-value.
    tail = (1 + np.count_nonzero(np.abs(means - estimate) >= abs(estimate))) / (repetitions + 1)
    return {
        "mean_difference": float(estimate),
        "interval": np.quantile(means, [alpha, 1 - alpha]),
        "bootstrap_means": means,
        "centered_two_sided_tail": float(tail),
        "time_points": count,
        "effective_blocks_approx": count / block_length,
        "block_length": int(block_length),
        "diagnostic_only": True,
    }
