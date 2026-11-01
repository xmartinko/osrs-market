"""CPU sample and analytical proper scores.

Shapes: ``samples [batch, draw, horizon]``, ``targets [batch, horizon]``.
Inputs are scored in their supplied units. Convert normalized increments to cumulative
returns *before* calling these functions when scoring cumulative-return forecasts.
No function pools items or horizons silently unless explicitly invoked via panel helpers.
Lower proper scores (CRPS, WIS, Energy, Variogram, Brier) are better.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import special

INTERVAL_ALPHAS = (0.1, 0.2, 0.5)
REGISTERED_INTERVAL_ALPHAS = (0.05, 0.1, 0.2, 0.5)


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
    safe_scale = np.where(scale > 0, scale, 1.0)
    z = (targets - mean) / safe_scale
    cdf = 0.5 * (1.0 + special.erf(z / math.sqrt(2.0)))
    density = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    score = safe_scale * (z * (2.0 * cdf - 1.0) + 2.0 * density - 1.0 / math.sqrt(math.pi))
    return np.where(scale > 0, score, np.abs(targets - mean))


def student_t_crps(df, mean, scale, targets):
    """Analytic location-scale Student-t CRPS (Jordan, Krueger & Lerch 2019).

    Requires finite ``df > 1`` and ``scale >= 0``; ``scale == 0`` gives ``|y - mean|``.
    Note ``scale`` is the Student-t scale parameter (not standard deviation).
    """
    df, mean, scale, targets = np.broadcast_arrays(
        np.asarray(df, dtype=float),
        np.asarray(mean, dtype=float),
        np.asarray(scale, dtype=float),
        np.asarray(targets, dtype=float),
    )
    if (
        not all(np.isfinite(a).all() for a in (df, mean, scale, targets))
        or np.any(df <= 1.0)
        or np.any(scale < 0.0)
    ):
        raise ValueError("Student-t CRPS requires finite parameters with df > 1 and scale >= 0")
    safe_scale = np.where(scale > 0, scale, 1.0)
    z = (targets - mean) / safe_scale
    # Standardized Student-t CDF and PDF via regularized incomplete beta / log-gamma.
    x = df / (df + z * z)
    half_ibeta = 0.5 * special.betainc(0.5 * df, 0.5, x)
    cdf = np.where(z >= 0, 1.0 - half_ibeta, half_ibeta)
    log_pdf = (
        special.gammaln(0.5 * (df + 1.0))
        - special.gammaln(0.5 * df)
        - 0.5 * np.log(df * math.pi)
        - 0.5 * (df + 1.0) * np.log1p((z * z) / df)
    )
    pdf = np.exp(log_pdf)
    log_beta_ratio = special.betaln(0.5, df - 0.5) - 2.0 * special.betaln(0.5, 0.5 * df)
    dispersion_const = (2.0 * np.sqrt(df) / (df - 1.0)) * np.exp(log_beta_ratio)
    unit_crps = z * (2.0 * cdf - 1.0) + 2.0 * pdf * ((df + z * z) / (df - 1.0)) - dispersion_const
    return np.where(scale > 0, safe_scale * unit_crps, np.abs(targets - mean))


def _validate_alphas(alphas):
    alphas = np.asarray(alphas, dtype=float)
    if (
        alphas.ndim != 1
        or len(alphas) == 0
        or not np.isfinite(alphas).all()
        or np.any((alphas <= 0) | (alphas >= 1))
        or len(np.unique(alphas)) != len(alphas)
    ):
        raise ValueError("Interval alphas must be unique values strictly between zero and one")
    return alphas


def interval_scores(samples, targets, *, alphas=INTERVAL_ALPHAS):
    """Fixed-level WIS [B,H], coverage and widths [K,B,H].

    Levels must be registered before comparison. NumPy linear sample quantiles
    approximate population quantiles; WIS is proper for the supplied quantile
    forecasts, not an unbiased Monte Carlo estimator of a latent model's WIS.
    """
    samples, targets = _validated(samples, targets)
    alphas = _validate_alphas(alphas)
    lower = np.quantile(samples, alphas / 2, axis=1, method="linear")
    upper = np.quantile(samples, 1 - alphas / 2, axis=1, method="linear")
    median = np.quantile(samples, 0.5, axis=1, method="linear")
    return _interval_summary(lower, upper, median, targets, alphas)


def quantile_interval_scores(
    quantiles, quantile_levels, targets, *, alphas=REGISTERED_INTERVAL_ALPHAS
):
    """Exact WIS, coverage, and widths directly from predicted quantiles [B,Q,H]."""
    quantiles = np.asarray(quantiles, dtype=np.float64)
    levels = np.asarray(quantile_levels, dtype=np.float64)
    targets = np.asarray(targets, dtype=np.float64)
    alphas = _validate_alphas(alphas)
    if (
        quantiles.ndim != 3
        or levels.ndim != 1
        or quantiles.shape[1] != len(levels)
        or targets.shape != (quantiles.shape[0], quantiles.shape[2])
        or min(quantiles.shape) < 1
        or not np.isfinite(quantiles).all()
        or not np.isfinite(targets).all()
    ):
        raise ValueError("Expected finite quantiles [B,Q,H], levels [Q], and targets [B,H]")
    if np.any(np.diff(levels) <= 0) or levels[0] <= 0 or levels[-1] >= 1:
        raise ValueError("quantile_levels must be strictly increasing in (0, 1)")

    def _lookup(prob):
        matches = np.flatnonzero(np.isclose(levels, prob, atol=1e-9, rtol=0.0))
        if len(matches) != 1:
            raise ValueError(f"Required quantile level {prob} missing from quantile_levels")
        return quantiles[:, matches[0], :]

    lower = np.stack([_lookup(alpha / 2.0) for alpha in alphas], axis=0)
    upper = np.stack([_lookup(1.0 - alpha / 2.0) for alpha in alphas], axis=0)
    median = _lookup(0.5)
    return _interval_summary(lower, upper, median, targets, alphas)


def _interval_summary(lower, upper, median, targets, alphas):
    width = upper - lower
    if np.any(width < -1e-12):
        raise ValueError("Crossing quantile intervals encountered (upper < lower)")
    width = np.maximum(width, 0.0)
    interval = width + 2.0 / alphas[:, None, None] * (
        np.maximum(lower - targets, 0.0) + np.maximum(targets - upper, 0.0)
    )
    wis = (
        0.5 * np.abs(median - targets) + np.sum(alphas[:, None, None] / 2.0 * interval, axis=0)
    ) / (len(alphas) + 0.5)
    return {
        "wis": wis,
        "coverage": (targets >= lower) & (targets <= upper),
        "width": width,
        "alphas": alphas,
        "median": median,
    }


def pit_values(samples, targets):
    """Mid-rank empirical probability integral transform values [B,H] in [0, 1]."""
    samples, targets = _validated(samples, targets)
    less = np.mean(samples < targets[:, None, :], axis=1)
    equal = np.mean(samples == targets[:, None, :], axis=1)
    return less + 0.5 * equal


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


def variogram_score(samples, targets, *, power=0.5, weights=None, estimator="plugin"):
    """Return [B] variogram score, summing each unordered horizon pair once.

    ``estimator="plugin"`` retains the standard nonnegative sample-mean square
    (backward compatible, with ``+Var(|X_i - X_j|^p)/M`` finite-draw bias).
    ``estimator="unbiased"`` subtracts ``sample_var(|X_i - X_j|^p, ddof=1) / M``
    (requires IID draws and M >= 2), removing dispersion-dependent Monte Carlo bias.
    """
    samples, targets = _validated(samples, targets)
    draws = samples.shape[1]
    horizon = samples.shape[2]
    if estimator not in {"plugin", "unbiased"} or (estimator == "unbiased" and draws < 2):
        raise ValueError("estimator must be 'plugin' or 'unbiased' (with at least two draws)")
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
            weight = weights[left, right]
            if weight == 0:
                continue
            diff_p = np.abs(samples[:, :, left] - samples[:, :, right]) ** power
            forecast = np.mean(diff_p, axis=1)
            observed = np.abs(targets[:, left] - targets[:, right]) ** power
            term = (observed - forecast) ** 2
            if estimator == "unbiased":
                term = term - np.var(diff_p, axis=1, ddof=1) / draws
            result += weight * term
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


def _resample_time_weights(
    count: int, block_length: int, repetitions: int, scheme: str, rng
) -> np.ndarray:
    """Return [repetitions, count] integer frequency weights on an intact calendar grid."""
    weights = np.zeros((repetitions, count), dtype=np.float64)
    if scheme == "moving":
        blocks = math.ceil(count / block_length)
        offsets = np.arange(block_length)
        max_start = count - block_length
        for rep in range(repetitions):
            starts = rng.integers(0, max_start + 1, size=blocks)
            indices = (starts[:, None] + offsets).ravel()[:count]
            weights[rep] = np.bincount(indices, minlength=count)
        return weights
    if scheme == "circular":
        blocks = math.ceil(count / block_length)
        offsets = np.arange(block_length)
        for rep in range(repetitions):
            starts = rng.integers(0, count, size=blocks)
            indices = ((starts[:, None] + offsets) % count).ravel()[:count]
            weights[rep] = np.bincount(indices, minlength=count)
        return weights
    if scheme == "stationary":
        # Non-wrapping Politis-Romano geometric block lengths with mean ``block_length``.
        stop_prob = 1.0 / block_length
        for rep in range(repetitions):
            indices = np.empty(count, dtype=np.int64)
            pos = int(rng.integers(0, count))
            for step in range(count):
                indices[step] = pos
                if pos + 1 >= count or rng.random() < stop_prob:
                    pos = int(rng.integers(0, count))
                else:
                    pos += 1
            weights[rep] = np.bincount(indices, minlength=count)
        return weights
    raise ValueError("scheme must be 'moving', 'stationary', or 'circular'")


def paired_panel_block_bootstrap(
    loss_a,
    loss_b,
    *,
    block_length: int,
    repetitions: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
    scheme: str = "moving",
    aggregation: str = "item_macro",
):
    """Paired temporal block bootstrap for incomplete [T,N] panels on an intact calendar grid.

    Missing/ineligible cells are encoded as ``NaN`` and must match identically between
    ``loss_a`` and ``loss_b`` (strictly paired origins). Resampling operates on calendar
    time blocks ``0..T-1`` across all items simultaneously, preserving cross-sectional
    co-movement and shared outages without wrapping across fold boundaries when
    ``scheme='moving'`` or ``scheme='stationary'``.
    """
    first = np.asarray(loss_a, dtype=np.float64)
    second = np.asarray(loss_b, dtype=np.float64)
    if first.shape != second.shape or first.ndim not in (1, 2) or first.size == 0:
        raise ValueError("Paired panel losses must have matching nonempty [T] or [T,N] shape")
    if first.ndim == 1:
        first = first[:, None]
        second = second[:, None]
    nan_a, nan_b = np.isnan(first), np.isnan(second)
    if not np.array_equal(nan_a, nan_b):
        raise ValueError("Paired panel losses must have identical missingness masks")
    if np.isinf(first).any() or np.isinf(second).any():
        raise ValueError("Infinite loss values are not permitted")
    valid = (~nan_a).astype(np.float64)
    if valid.sum() == 0:
        raise ValueError("Panel contains zero valid paired observations")
    count = first.shape[0]
    if (
        isinstance(block_length, bool)
        or not isinstance(block_length, (int, np.integer))
        or not 1 <= block_length <= count
        or isinstance(repetitions, bool)
        or not isinstance(repetitions, (int, np.integer))
        or repetitions < 2
        or not 0 < confidence < 1
        or aggregation not in {"item_macro", "pooled"}
    ):
        raise ValueError("Invalid bootstrap parameters or aggregation mode")

    val_a = np.where(~nan_a, first, 0.0)
    val_b = np.where(~nan_b, second, 0.0)
    item_counts = valid.sum(axis=0)
    active_items = item_counts > 0
    if not np.any(active_items):
        raise ValueError("No active items with valid observations")

    if aggregation == "item_macro":
        mean_a = float(np.mean(val_a[:, active_items].sum(axis=0) / item_counts[active_items]))
        mean_b = float(np.mean(val_b[:, active_items].sum(axis=0) / item_counts[active_items]))
    else:
        mean_a = float(val_a.sum() / valid.sum())
        mean_b = float(val_b.sum() / valid.sum())

    estimate_diff = mean_a - mean_b
    estimate_rel_gain = (mean_b - mean_a) / mean_b if mean_b > 0 else float("nan")

    rng = np.random.default_rng(seed)
    weights = _resample_time_weights(count, int(block_length), int(repetitions), scheme, rng)
    boot_sum_a = weights @ val_a
    boot_sum_b = weights @ val_b
    boot_cnt = weights @ valid

    if aggregation == "item_macro":
        has_obs = boot_cnt > 0
        safe_cnt = np.where(has_obs, boot_cnt, 1.0)
        active_per_rep = np.maximum(has_obs.sum(axis=1), 1)
        boot_mean_a = np.where(has_obs, boot_sum_a / safe_cnt, 0.0).sum(axis=1) / active_per_rep
        boot_mean_b = np.where(has_obs, boot_sum_b / safe_cnt, 0.0).sum(axis=1) / active_per_rep
    else:
        total_cnt = np.maximum(boot_cnt.sum(axis=1), 1.0)
        boot_mean_a = boot_sum_a.sum(axis=1) / total_cnt
        boot_mean_b = boot_sum_b.sum(axis=1) / total_cnt

    boot_diffs = boot_mean_a - boot_mean_b
    with np.errstate(divide="ignore", invalid="ignore"):
        boot_rel_gains = np.where(
            boot_mean_b > 0, (boot_mean_b - boot_mean_a) / boot_mean_b, np.nan
        )

    alpha = (1.0 - confidence) / 2.0
    diff_ci = np.quantile(boot_diffs, [alpha, 1.0 - alpha])
    finite_rel = boot_rel_gains[np.isfinite(boot_rel_gains)]
    rel_ci = (
        np.quantile(finite_rel, [alpha, 1.0 - alpha]).tolist()
        if len(finite_rel) >= 2
        else [float("nan"), float("nan")]
    )
    tail = (1 + np.count_nonzero(np.abs(boot_diffs - estimate_diff) >= abs(estimate_diff))) / (
        repetitions + 1
    )
    return {
        "mean_a": mean_a,
        "mean_b": mean_b,
        "mean_difference": float(estimate_diff),
        "difference_interval": diff_ci.tolist(),
        "relative_gain_vs_b": float(estimate_rel_gain),
        "relative_gain_interval": rel_ci,
        "centered_two_sided_tail": float(tail),
        "time_points": int(count),
        "active_items": int(active_items.sum()),
        "valid_pairs": int(valid.sum()),
        "block_length": int(block_length),
        "scheme": scheme,
        "aggregation": aggregation,
    }


def holm_adjust(p_values):
    """Step-down Holm-Bonferroni multiplicity adjustment preserving input order."""
    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1 or len(p) == 0 or not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("p_values must be a nonempty 1D array in [0, 1]")
    m = len(p)
    order = np.argsort(p)
    scaled = (m - np.arange(m)) * p[order]
    enforced = np.maximum.accumulate(np.minimum(scaled, 1.0))
    adjusted = np.empty(m, dtype=np.float64)
    adjusted[order] = enforced
    return adjusted
