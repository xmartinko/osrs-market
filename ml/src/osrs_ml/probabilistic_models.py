"""Small conditional distributions over a fixed grid of normalized return increments.

``build_model(name, context_features, horizon=24, width=64, item_count=100)``
returns a PyTorch module with this API:

* ``log_prob(context[B,L,F], target[B,H], item_index[B]) -> [B]``: joint log density.
* ``loss(context, target, item_index) -> scalar``: mean negative joint log density
  divided by H, in nats per target coordinate.
* ``sample(context, item_index, num_samples) -> [B,M,H]``: complete joint paths.

Inputs and outputs use the caller's past-only normalization. This module does not
normalize, impute, build price paths, or infer fills. Context must be finite; encode
missingness/freshness explicitly as input features. Targets must be complete, finite
increment windows. Use the same target coordinates when comparing likelihoods.

Keep model parameters FP32. Probability algebra and the small encoder run in FP32,
even inside an outer autocast context; no FP16 covariance or spline computation is
performed. Optional ``spline_flow`` requires nflows; Gaussian/Student-t models do not.
"""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn
from torch.distributions import Independent, LowRankMultivariateNormal, Normal, StudentT
from torch.nn import functional as F

MODEL_NAMES = ("gaussian_diag", "gaussian_lowrank", "student_t", "spline_flow")
SCALE_FLOOR = 1e-3


class ContextEncoder(nn.Module):
    """One shared-size GRU plus item embedding, identical across distribution heads."""

    def __init__(self, context_features: int, width: int, item_count: int):
        super().__init__()
        self.context_features = context_features
        self.gru = nn.GRU(context_features, width, batch_first=True)
        embedding_width = min(16, width)
        self.item_embedding = nn.Embedding(item_count, embedding_width)
        self.projection = nn.Sequential(nn.Linear(width + embedding_width, width), nn.SiLU())

    def forward(self, context: Tensor, item_index: Tensor) -> Tensor:
        if context.ndim != 3 or context.shape[-1] != self.context_features:
            raise ValueError("context must have shape [batch, history, context_features]")
        if context.shape[0] == 0 or context.shape[1] == 0:
            raise ValueError("context batch and history must be nonempty")
        if item_index.shape != (context.shape[0],):
            raise ValueError("item_index must have shape [batch]")
        if item_index.dtype != torch.long:
            raise ValueError("item_index must use torch.long indices")
        _, hidden = self.gru(context.float())
        item = self.item_embedding(item_index)
        return self.projection(torch.cat((hidden[-1], item), dim=-1))


class ProbabilisticModel(nn.Module):
    """Base interface; observations are increments, never cumulative paths."""

    def __init__(self, context_features: int, horizon: int, width: int, item_count: int):
        super().__init__()
        self.horizon = horizon
        self.encoder = ContextEncoder(context_features, width, item_count)

    def _check_target(self, context: Tensor, target: Tensor) -> None:
        if target.shape != (context.shape[0], self.horizon):
            raise ValueError("target must have shape [batch, horizon]")

    @staticmethod
    def _check_sample_count(num_samples: int) -> None:
        if isinstance(num_samples, bool) or not isinstance(num_samples, int) or num_samples < 1:
            raise ValueError("num_samples must be a positive integer")

    def log_prob(self, context: Tensor, target: Tensor, item_index: Tensor) -> Tensor:
        raise NotImplementedError

    def loss(self, context: Tensor, target: Tensor, item_index: Tensor) -> Tensor:
        return -self.log_prob(context, target, item_index).mean() / self.horizon

    def sample(self, context: Tensor, item_index: Tensor, num_samples: int) -> Tensor:
        raise NotImplementedError


class ParametricTrajectoryModel(ProbabilisticModel):
    """Gaussian or independent Student-t increments, with a learned conditional head.

    Low-rank covariance is diag(scale**2) + factor @ factor.T, rank min(4,H).
    ``distribution`` is exposed for diagnostics and reference likelihood checks.
    """

    def __init__(self, name: str, context_features: int, horizon: int, width: int, item_count: int):
        super().__init__(context_features, horizon, width, item_count)
        self.name = name
        self.rank = min(4, horizon)
        outputs = 2 * horizon
        if name == "gaussian_lowrank":
            outputs += horizon * self.rank
        elif name == "student_t":
            outputs += horizon
        self.head = nn.Linear(width, outputs)

    def distribution(self, context: Tensor, item_index: Tensor):
        with torch.autocast(device_type=context.device.type, enabled=False):
            raw = self.head(self.encoder(context, item_index)).float()
            mean = raw[:, : self.horizon]
            scale = F.softplus(raw[:, self.horizon : 2 * self.horizon]) + SCALE_FLOOR
            if self.name == "gaussian_diag":
                return Independent(Normal(mean, scale, validate_args=False), 1)
            if self.name == "gaussian_lowrank":
                factor = raw[:, 2 * self.horizon :].reshape(-1, self.horizon, self.rank)
                factor = factor / math.sqrt(self.rank)
                return LowRankMultivariateNormal(mean, factor, scale.square(), validate_args=False)
            degrees_of_freedom = 2.0 + F.softplus(raw[:, 2 * self.horizon :])
            return Independent(StudentT(degrees_of_freedom, mean, scale, validate_args=False), 1)

    def log_prob(self, context: Tensor, target: Tensor, item_index: Tensor) -> Tensor:
        self._check_target(context, target)
        with torch.autocast(device_type=context.device.type, enabled=False):
            return self.distribution(context, item_index).log_prob(target.float())

    @torch.no_grad()
    def sample(self, context: Tensor, item_index: Tensor, num_samples: int) -> Tensor:
        self._check_sample_count(num_samples)
        with torch.autocast(device_type=context.device.type, enabled=False):
            samples = self.distribution(context, item_index).sample((num_samples,))
            return samples.permute(1, 0, 2).contiguous()


class SplineTrajectoryModel(ProbabilisticModel):
    """Four conditional rational-quadratic coupling blocks, eight bins, linear tails.

    Alternating parity masks transform both coordinate subsets. Each conditioner is
    a width-sized two-block residual MLP, conditioned on the common GRU embedding.
    A standard Gaussian base and linear tails do not assert heavy-tailed forecasts.
    """

    def __init__(self, context_features: int, horizon: int, width: int, item_count: int):
        if horizon < 2:
            raise ValueError("spline_flow needs horizon >= 2 for coupling partitions")
        try:
            from nflows.distributions.normal import StandardNormal
            from nflows.flows.base import Flow
            from nflows.nn.nets import ResidualNet
            from nflows.transforms.base import CompositeTransform
            from nflows.transforms.coupling import PiecewiseRationalQuadraticCouplingTransform
        except ImportError as exc:
            raise ImportError(
                "spline_flow requires the optional nflows package and its dependencies; "
                "use gaussian_diag/gaussian_lowrank/student_t until explicitly installed"
            ) from exc
        super().__init__(context_features, horizon, width, item_count)

        def create_conditioner(in_features: int, out_features: int):
            return ResidualNet(
                in_features=in_features,
                out_features=out_features,
                hidden_features=width,
                context_features=width,
                num_blocks=2,
                dropout_probability=0.0,
                use_batch_norm=False,
            )

        transforms = []
        for block in range(4):
            mask = (torch.arange(horizon) + block) % 2
            transforms.append(
                PiecewiseRationalQuadraticCouplingTransform(
                    mask=mask,
                    transform_net_create_fn=create_conditioner,
                    num_bins=8,
                    tails="linear",
                    tail_bound=5.0,
                )
            )
        self.flow = Flow(CompositeTransform(transforms), StandardNormal([horizon]))

    def log_prob(self, context: Tensor, target: Tensor, item_index: Tensor) -> Tensor:
        self._check_target(context, target)
        with torch.autocast(device_type=context.device.type, enabled=False):
            encoded = self.encoder(context, item_index)
            return self.flow.log_prob(target.float(), context=encoded).float()

    @torch.no_grad()
    def sample(self, context: Tensor, item_index: Tensor, num_samples: int) -> Tensor:
        self._check_sample_count(num_samples)
        with torch.autocast(device_type=context.device.type, enabled=False):
            encoded = self.encoder(context, item_index)
            return self.flow.sample(num_samples, context=encoded).float()


def build_model(
    name: str,
    context_features: int,
    horizon: int = 24,
    width: int = 64,
    item_count: int = 100,
) -> ProbabilisticModel:
    """Build an untrained model. Names are listed in ``MODEL_NAMES``.

    The caller owns seeds, devices, normalization, data splits, optimizer, and
    checkpoint metadata. No CUDA device, filesystem, or data source is touched.
    """
    if name not in MODEL_NAMES:
        raise ValueError(f"unknown model {name!r}; choose from {MODEL_NAMES}")
    dimensions = (context_features, horizon, width, item_count)
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in dimensions):
        raise ValueError(
            "context_features, horizon, width and item_count must be positive integers"
        )
    if name == "spline_flow":
        return SplineTrajectoryModel(context_features, horizon, width, item_count)
    return ParametricTrajectoryModel(name, context_features, horizon, width, item_count)
