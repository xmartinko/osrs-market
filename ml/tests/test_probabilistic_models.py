"""CPU unit fixtures test numerical contracts, never market performance."""

import importlib.util

import pytest

torch = pytest.importorskip("torch")

from osrs_ml.probabilistic_models import STUDENT_T_DF_FLOOR, build_model  # noqa: E402


def batch(horizon=24):
    generator = torch.Generator().manual_seed(19)
    context = torch.randn(3, 8, 5, generator=generator)
    target = torch.randn(3, horizon, generator=generator)
    items = torch.tensor([0, 2, 3])
    return context, target, items


@pytest.mark.parametrize(
    "name",
    [
        "gaussian_diag",
        "gaussian_lowrank",
        "student_t",
        "direct_marginal_student_t",
        "recursive_student_t",
    ],
)
def test_joint_likelihood_samples_and_finite_backward(name):
    torch.manual_seed(7)
    model = build_model(name, 5, item_count=4)
    context, target, items = batch()
    log_prob = model.log_prob(context, target, items)
    assert log_prob.shape == (3,)
    assert torch.isfinite(log_prob).all()
    loss = model.loss(context, target, items)
    torch.testing.assert_close(loss, -log_prob.mean() / 24)
    loss.backward()
    for parameter in model.parameters():
        assert parameter.grad is not None
        assert torch.isfinite(parameter.grad).all()
    samples = model.sample(context, items, 11)
    assert samples.shape == (3, 11, 24)
    assert torch.isfinite(samples).all()
    assert not samples.requires_grad


def test_student_t_df_floor_guarantees_finite_variance():
    model = build_model("student_t", 5, horizon=4, width=8, item_count=4)
    with torch.no_grad():
        model.head.weight.zero_()
        model.head.bias.fill_(-50.0)
    context, _, items = batch(horizon=4)
    dist = model.distribution(context, items)
    assert (dist.base_dist.df >= STUDENT_T_DF_FLOOR).all()
    assert torch.isfinite(dist.variance).all()


@pytest.mark.parametrize("name", ["gaussian_diag", "gaussian_lowrank"])
def test_joint_gaussian_density_matches_dense_reference_and_covariance_is_positive(name):
    torch.manual_seed(11)
    model = build_model(name, 5, horizon=6, width=8, item_count=4)
    context, target, items = batch(horizon=6)
    distribution = model.distribution(context, items)
    if name == "gaussian_diag":
        mean = distribution.base_dist.loc
        covariance = torch.diag_embed(distribution.base_dist.scale.square())
    else:
        mean = distribution.loc
        covariance = distribution.covariance_matrix
    cholesky, info = torch.linalg.cholesky_ex(covariance)
    assert (info == 0).all()
    assert (cholesky.diagonal(dim1=-2, dim2=-1) > 0).all()
    reference = torch.distributions.MultivariateNormal(mean, covariance_matrix=covariance)
    torch.testing.assert_close(
        model.log_prob(context, target, items), reference.log_prob(target), rtol=2e-5, atol=2e-5
    )


def test_distribution_algebra_remains_float32_under_cpu_autocast():
    model = build_model("gaussian_lowrank", 5, width=8, item_count=4)
    context, target, items = batch()
    with torch.autocast("cpu", dtype=torch.bfloat16):
        loss = model.loss(context, target, items)
        samples = model.sample(context, items, 2)
    assert loss.dtype == torch.float32
    assert samples.dtype == torch.float32
    assert torch.isfinite(loss)


def test_lowrank_sampling_retains_cross_horizon_dependence():
    # A known covariance fixture checks the actual joint sampler, not chart appearance.
    torch.manual_seed(23)
    model = build_model("gaussian_lowrank", 5, horizon=4, width=8, item_count=4)
    with torch.no_grad():
        model.head.weight.zero_()
        model.head.bias.zero_()
        model.head.bias[4:8].fill_(-3)
        model.head.bias[8:].fill_(2)
    context, _, items = batch(horizon=4)
    samples = model.sample(context[:1], items[:1], 4000)[0]
    correlation = torch.corrcoef(samples.T)
    assert correlation[0, 1] > 0.95


def test_invalid_inputs_fail_with_actionable_errors():
    with pytest.raises(ValueError, match="unknown model"):
        build_model("unknown", 5)
    with pytest.raises(ValueError, match="positive integers"):
        build_model("gaussian_diag", 0)
    model = build_model("gaussian_diag", 5, item_count=4)
    context, target, items = batch()
    with pytest.raises(ValueError, match="target"):
        model.loss(context, target[:, :-1], items)
    with pytest.raises(ValueError, match="positive integer"):
        model.sample(context, items, 0)
    with pytest.raises(ValueError, match="torch.long"):
        model.loss(context, target, items.float())


def test_optional_spline_flow_roundtrip_density_and_backward():
    if importlib.util.find_spec("nflows") is None:
        pytest.skip("optional nflows dependency is absent")
    model = build_model("spline_flow", 5, horizon=6, width=8, item_count=4)
    context, target, items = batch(horizon=6)
    encoded = model.encoder(context, items)
    noise, forward_logdet = model.flow._transform(target, context=encoded)
    restored, inverse_logdet = model.flow._transform.inverse(noise, context=encoded)
    torch.testing.assert_close(restored, target, rtol=2e-4, atol=2e-4)
    torch.testing.assert_close(forward_logdet + inverse_logdet, torch.zeros(3), atol=2e-4, rtol=0)
    model.loss(context, target, items).backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
    samples = model.sample(context, items, 7)
    assert samples.shape == (3, 7, 6)
    assert torch.isfinite(samples).all()
    assert torch.isfinite(model.log_prob(context, samples[:, 0], items)).all()


def test_spline_flow_extreme_tails_propagate_gradient_to_affine_and_encoder():
    if importlib.util.find_spec("nflows") is None:
        pytest.skip("optional nflows dependency is absent")
    torch.manual_seed(31)
    model = build_model("spline_flow", 5, horizon=6, width=16, item_count=4)
    context, _, items = batch(horizon=6)
    # Initialize non-zero affine weights so encoder receives gradients on extreme tail targets.
    with torch.no_grad():
        affine = model.flow._transform._transforms[0]
        affine.head.weight.normal_(0.0, 0.05)
    extreme_target = torch.full((3, 6), 12.0)  # Far outside [-6, 6] spline box.
    loss = model.loss(context, extreme_target, items)
    loss.backward()
    assert affine.head.bias.grad is not None
    assert affine.head.bias.grad.abs().max() > 1.0
    encoder_grad_norm = sum(p.grad.abs().sum().item() for p in model.encoder.parameters())
    assert encoder_grad_norm > 0.0

    # Verify legacy pilot_v1 variant remains constructible for archived pilot checkpoints.
    legacy = build_model(
        "spline_flow", 8, horizon=24, width=64, item_count=74, spline_variant="pilot_v1"
    )
    assert sum(p.numel() for p in legacy.parameters()) == 211_888


def test_missing_spline_dependency_has_explicit_error(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def without_nflows(name, *args, **kwargs):
        if name.startswith("nflows"):
            raise ModuleNotFoundError("test fixture: nflows unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_nflows)
    with pytest.raises(ImportError, match="optional nflows"):
        build_model("spline_flow", 5)
