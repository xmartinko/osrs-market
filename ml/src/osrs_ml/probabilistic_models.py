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

MODEL_NAMES = (
    "gaussian_diag",
    "gaussian_lowrank",
    "student_t",
    "direct_marginal_student_t",
    "recursive_student_t",
    "spline_flow",
)
SCALE_FLOOR = 1e-3
STUDENT_T_DF_FLOOR = 2.1
STUDENT_T_DF_MAX_OFFSET = 200.0


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
    Student-t enforces df >= 2.1 so forecast variance remains finite.
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
            degrees_of_freedom = STUDENT_T_DF_FLOOR + F.softplus(raw[:, 2 * self.horizon :]).clamp(
                max=STUDENT_T_DF_MAX_OFFSET
            )
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


class DirectMarginalStudentTModel(ProbabilisticModel):
    """Shared-encoder independent-horizon Student-t over standardized cumulative returns.

    Models cumulative horizons ``R_h = sum_{s=1..h} r_s`` directly with conditional
    location, sub-diffusive scale, and heavy-tailed degrees of freedom ``df >= 2.1``.
    Because the cumulative-sum linear map has unit determinant (``log|det J| = 0``),
    ``log_prob`` is an exact normalized density over increment space, while ``sample``
    returns first-differenced independent cumulative draws to isolate marginal skill
    from cross-horizon trajectory dependence (E2/C2 control).
    """

    def __init__(self, context_features: int, horizon: int, width: int, item_count: int):
        super().__init__(context_features, horizon, width, item_count)
        self.name = "direct_marginal_student_t"
        self.head = nn.Linear(width, 3 * horizon)
        with torch.no_grad():
            nn.init.normal_(self.head.weight, mean=0.0, std=0.02)
            nn.init.zeros_(self.head.bias)
            init_scales = [
                math.log(math.expm1(max((h + 1) ** 0.35 - SCALE_FLOOR, 0.1)))
                for h in range(horizon)
            ]
            self.head.bias[horizon : 2 * horizon].copy_(
                torch.tensor(init_scales, dtype=torch.float32)
            )
            self.head.bias[2 * horizon :].fill_(math.log(math.expm1(5.0 - STUDENT_T_DF_FLOOR)))

    def distribution(self, context: Tensor, item_index: Tensor):
        with torch.autocast(device_type=context.device.type, enabled=False):
            raw = self.head(self.encoder(context, item_index)).float()
            mean = raw[:, : self.horizon]
            scale = F.softplus(raw[:, self.horizon : 2 * self.horizon]) + SCALE_FLOOR
            df = STUDENT_T_DF_FLOOR + F.softplus(raw[:, 2 * self.horizon :]).clamp(
                max=STUDENT_T_DF_MAX_OFFSET
            )
            return Independent(StudentT(df, mean, scale, validate_args=False), 1)

    def log_prob(self, context: Tensor, target: Tensor, item_index: Tensor) -> Tensor:
        self._check_target(context, target)
        with torch.autocast(device_type=context.device.type, enabled=False):
            cum_target = torch.cumsum(target.float(), dim=-1)
            return self.distribution(context, item_index).log_prob(cum_target)

    @torch.no_grad()
    def sample(self, context: Tensor, item_index: Tensor, num_samples: int) -> Tensor:
        self._check_sample_count(num_samples)
        with torch.autocast(device_type=context.device.type, enabled=False):
            cum = self.distribution(context, item_index).sample((num_samples,))
            cum = cum.permute(1, 0, 2).contiguous()
            if self.horizon == 1:
                return cum
            return torch.cat([cum[:, :, :1], cum[:, :, 1:] - cum[:, :, :-1]], dim=-1)


class RecursiveStudentTModel(ProbabilisticModel):
    """Shared-encoder closed-loop 1-step Student-t autoregressive rollout model (E2/C2 control).

    Evaluates exact chain-rule joint log-likelihood ``sum_s log p(r_s | c_t, r_{1..s-1})``
    and generates closed-loop trajectories using the identical deterministic causal
    feature-transition map ``_advance_feature_step`` in both training and sampling.
    """

    def __init__(self, context_features: int, horizon: int, width: int, item_count: int):
        super().__init__(context_features, horizon, width, item_count)
        self.name = "recursive_student_t"
        self.context_features = context_features
        self.head = nn.Linear(width, 3)
        with torch.no_grad():
            nn.init.normal_(self.head.weight, mean=0.0, std=0.02)
            self.head.bias[0] = 0.0
            self.head.bias[1] = math.log(math.expm1(max(0.85 - SCALE_FLOOR, 0.1)))
            self.head.bias[2] = math.log(math.expm1(5.0 - STUDENT_T_DF_FLOOR))

        self._cos_1h = math.cos(2.0 * math.pi / 24.0)
        self._sin_1h = math.sin(2.0 * math.pi / 24.0)
        self._cos_1w = math.cos(2.0 * math.pi / 168.0)
        self._sin_1w = math.sin(2.0 * math.pi / 168.0)
        self._decay_4 = math.exp(-1.0 / 4.0)
        self._decay_24 = math.exp(-1.0 / 24.0)
        self._decay_72 = math.exp(-1.0 / 72.0)

    def _step_dist(self, hidden_top: Tensor, item_emb: Tensor) -> StudentT:
        projected = self.encoder.projection(torch.cat((hidden_top, item_emb), dim=-1))
        raw = self.head(projected).float()
        mean = raw[:, 0]
        scale = F.softplus(raw[:, 1]) + SCALE_FLOOR
        df = STUDENT_T_DF_FLOOR + F.softplus(raw[:, 2]).clamp(max=STUDENT_T_DF_MAX_OFFSET)
        return StudentT(df, mean, scale, validate_args=False)

    def _advance_feature_step(self, prev_feat: Tensor, step_return: Tensor) -> Tensor:
        f_dim = self.context_features
        r_c = step_return.float().clamp(-25.0, 25.0)
        z = torch.zeros_like(r_c)
        if f_dim == 13:
            # Exact causal recurrence for E3_PRICE_ONLY_FEATURES (13 price-only columns).
            h_sin, h_cos = prev_feat[:, 3], prev_feat[:, 4]
            w_sin, w_cos = prev_feat[:, 7], prev_feat[:, 8]
            d4 = (self._decay_4 * (prev_feat[:, 9] + r_c * 0.5)).clamp(-20.0, 20.0)
            d24 = (self._decay_24 * (prev_feat[:, 10] + r_c / math.sqrt(24.0))).clamp(-20.0, 20.0)
            d72 = (self._decay_72 * (prev_feat[:, 11] + r_c / math.sqrt(72.0))).clamp(-20.0, 20.0)
            v2_prev = (prev_feat[:, 12] + 1.0).clamp(min=0.05).square()
            v2_next = self._decay_24 * v2_prev + (1.0 - self._decay_24) * r_c.square().clamp(
                max=36.0
            )
            return torch.stack(
                [
                    r_c,
                    z,
                    z,
                    h_sin * self._cos_1h + h_cos * self._sin_1h,
                    h_cos * self._cos_1h - h_sin * self._sin_1h,
                    r_c,
                    z,
                    w_sin * self._cos_1w + w_cos * self._sin_1w,
                    w_cos * self._cos_1w - w_sin * self._sin_1w,
                    d4,
                    d24,
                    d72,
                    torch.sqrt(v2_next) - 1.0,
                ],
                dim=-1,
            )
        cols = [r_c]
        if f_dim > 1:
            cols.append(prev_feat[:, 1] * self._decay_24)
        if f_dim > 2:
            cols.append(prev_feat[:, 2] * self._decay_24)
        for idx in (3, 4, 5):
            if f_dim > idx:
                cols.append(torch.zeros_like(r_c))
        if f_dim > 7:
            h_sin, h_cos = prev_feat[:, 6], prev_feat[:, 7]
            cols.append(h_sin * self._cos_1h + h_cos * self._sin_1h)
            cols.append(h_cos * self._cos_1h - h_sin * self._sin_1h)
        elif f_dim > 6:
            cols.append(prev_feat[:, 6])
        if f_dim > 8:
            cols.append(r_c)
        if f_dim > 9:
            cols.append(torch.zeros_like(r_c))
        if f_dim > 10:
            cols.append(torch.zeros_like(r_c))
        if f_dim > 12:
            w_sin, w_cos = prev_feat[:, 11], prev_feat[:, 12]
            cols.append(w_sin * self._cos_1w + w_cos * self._sin_1w)
            cols.append(w_cos * self._cos_1w - w_sin * self._sin_1w)
        elif f_dim > 11:
            cols.append(prev_feat[:, 11])
        if f_dim > 13:
            cols.append(prev_feat[:, 13] * self._decay_24)
        if f_dim > 14:
            cols.append(prev_feat[:, 14] * self._decay_4)
        if f_dim > 15:
            d4 = (self._decay_4 * (prev_feat[:, 15] + r_c * 0.5)).clamp(-20.0, 20.0)
            cols.append(d4)
        if f_dim > 16:
            d24 = (self._decay_24 * (prev_feat[:, 16] + r_c / math.sqrt(24.0))).clamp(-20.0, 20.0)
            cols.append(d24)
        if f_dim > 17:
            d72 = (self._decay_72 * (prev_feat[:, 17] + r_c / math.sqrt(72.0))).clamp(-20.0, 20.0)
            cols.append(d72)
        if f_dim > 18:
            v2_prev = (prev_feat[:, 18] + 1.0).clamp(min=0.05).square()
            v2_next = self._decay_24 * v2_prev + (1.0 - self._decay_24) * r_c.square().clamp(
                max=36.0
            )
            cols.append(torch.sqrt(v2_next) - 1.0)
        for extra in range(len(cols), f_dim):
            cols.append(prev_feat[:, extra] * self._decay_24)
        return torch.stack(cols[:f_dim], dim=-1)

    def log_prob(self, context: Tensor, target: Tensor, item_index: Tensor) -> Tensor:
        self._check_target(context, target)
        if context.ndim != 3 or context.shape[-1] != self.context_features:
            raise ValueError("context must have shape [batch, history, context_features]")
        if context.shape[0] == 0 or context.shape[1] == 0:
            raise ValueError("context batch and history must be nonempty")
        if item_index.shape != (context.shape[0],) or item_index.dtype != torch.long:
            raise ValueError("item_index must use torch.long indices of shape [batch]")

        with torch.autocast(device_type=context.device.type, enabled=False):
            ctx = context.float()
            tgt = target.float()
            _, hidden = self.encoder.gru(ctx)
            item_emb = self.encoder.item_embedding(item_index)
            cur_feat = ctx[:, -1, :]
            total_lp = self._step_dist(hidden[-1], item_emb).log_prob(tgt[:, 0])
            for step in range(self.horizon - 1):
                cur_feat = self._advance_feature_step(cur_feat, tgt[:, step])
                _, hidden = self.encoder.gru(cur_feat[:, None, :], hidden)
                total_lp = total_lp + self._step_dist(hidden[-1], item_emb).log_prob(
                    tgt[:, step + 1]
                )
            return total_lp

    @torch.no_grad()
    def sample(self, context: Tensor, item_index: Tensor, num_samples: int) -> Tensor:
        self._check_sample_count(num_samples)
        if context.ndim != 3 or context.shape[-1] != self.context_features:
            raise ValueError("context must have shape [batch, history, context_features]")
        if context.shape[0] == 0 or context.shape[1] == 0:
            raise ValueError("context batch and history must be nonempty")
        if item_index.shape != (context.shape[0],) or item_index.dtype != torch.long:
            raise ValueError("item_index must use torch.long indices of shape [batch]")

        with torch.autocast(device_type=context.device.type, enabled=False):
            batch_sz = context.shape[0]
            ctx = context.float()
            _, hidden0 = self.encoder.gru(ctx)
            hidden = hidden0.repeat_interleave(num_samples, dim=1)
            item_emb = self.encoder.item_embedding(item_index).repeat_interleave(num_samples, dim=0)
            cur_feat = ctx[:, -1, :].repeat_interleave(num_samples, dim=0)
            draws = []
            for step in range(self.horizon):
                if step > 0:
                    _, hidden = self.encoder.gru(cur_feat[:, None, :], hidden)
                step_draw = self._step_dist(hidden[-1], item_emb).sample().clamp(-50.0, 50.0)
                draws.append(step_draw)
                if step + 1 < self.horizon:
                    cur_feat = self._advance_feature_step(cur_feat, step_draw)
            stacked = torch.stack(draws, dim=-1)
            return stacked.reshape(batch_sz, num_samples, self.horizon).contiguous()


class SplineTrajectoryModel(ProbabilisticModel):
    """Conditional affine + rational-quadratic coupling spline flow over trajectories.

    ``spline_variant="campaign_v2"`` (default) prepends a learned conditional diagonal
    location-scale transform (initialized to the identity) before four rational-quadratic
    coupling blocks interleaved with deterministic cross-horizon permutations.

    ``spline_variant="campaign_v3"`` maps increments into cumulative-return coordinates
    (unit Jacobian), applies sub-diffusively initialized conditional horizon location-scale,
    whitens cross-horizon correlation via a regularized rank-6 conditional Cholesky factor,
    and models residual marginal/joint non-Gaussianity with four near-identity 8-bin
    rational-quadratic spline coupling blocks over a learnable unit-variance Student-t base.

    ``spline_variant="pilot_v1"`` preserves the archived pilot checkpoint layout.
    """

    def __init__(
        self,
        context_features: int,
        horizon: int,
        width: int,
        item_count: int,
        *,
        spline_variant: str = "campaign_v2",
    ):
        if horizon < 2:
            raise ValueError("spline_flow needs horizon >= 2 for coupling partitions")
        if spline_variant not in {"campaign_v3", "campaign_v2", "pilot_v1"}:
            raise ValueError("spline_variant must be 'campaign_v3', 'campaign_v2', or 'pilot_v1'")
        try:
            from nflows.distributions.base import Distribution
            from nflows.distributions.normal import StandardNormal
            from nflows.flows.base import Flow
            from nflows.nn.nets import ResidualNet
            from nflows.transforms.base import CompositeTransform, Transform
            from nflows.transforms.coupling import PiecewiseRationalQuadraticCouplingTransform
            from nflows.transforms.permutations import Permutation
        except ImportError as exc:
            raise ImportError(
                "spline_flow requires the optional nflows package and its dependencies; "
                "use gaussian_diag/gaussian_lowrank/student_t until explicitly installed"
            ) from exc
        super().__init__(context_features, horizon, width, item_count)
        self.spline_variant = spline_variant

        class _CumsumTransform(Transform):
            """Unimodular bijection mapping increments r -> cumulative returns R (log|det|=0)."""

            def forward(self, inputs: Tensor, context: Tensor | None = None):
                outputs = torch.cumsum(inputs.float(), dim=-1)
                return outputs, inputs.new_zeros(inputs.shape[0], dtype=torch.float32)

            def inverse(self, inputs: Tensor, context: Tensor | None = None):
                x = inputs.float()
                outputs = torch.cat([x[:, :1], x[:, 1:] - x[:, :-1]], dim=-1)
                return outputs, inputs.new_zeros(inputs.shape[0], dtype=torch.float32)

        class _ConditionalAffineTransform(Transform):
            """Data-to-spline conditional standardization y -> (y - loc(c)) / scale(c)."""

            def __init__(self, features: int, cond_width: int, *, subdiffusive_init: bool = False):
                super().__init__()
                self.features = features
                self.head = nn.Linear(cond_width, 2 * features)
                if subdiffusive_init:
                    nn.init.normal_(self.head.weight, mean=0.0, std=1e-3)
                    nn.init.zeros_(self.head.bias)
                    offsets = [
                        math.log(math.expm1(max((h + 1) ** 0.35 - SCALE_FLOOR, 0.1)))
                        for h in range(features)
                    ]
                    self.register_buffer(
                        "_scale_offset_vec", torch.tensor(offsets, dtype=torch.float32)
                    )
                    self._use_vec = True
                else:
                    nn.init.zeros_(self.head.weight)
                    nn.init.zeros_(self.head.bias)
                    self._scale_offset = math.log(math.expm1(1.0 - SCALE_FLOOR))
                    self._use_vec = False

            def _params(self, context: Tensor) -> tuple[Tensor, Tensor]:
                if context is None:
                    raise ValueError("ConditionalAffineTransform requires context")
                raw = self.head(context.float())
                loc = raw[:, : self.features]
                offset = self._scale_offset_vec if self._use_vec else self._scale_offset
                scale = F.softplus(raw[:, self.features :] + offset) + SCALE_FLOOR
                return loc, scale

            def forward(self, inputs: Tensor, context: Tensor | None = None):
                loc, scale = self._params(context)
                outputs = (inputs.float() - loc) / scale
                logabsdet = -torch.log(scale).sum(dim=-1)
                return outputs, logabsdet

            def inverse(self, inputs: Tensor, context: Tensor | None = None):
                loc, scale = self._params(context)
                outputs = inputs.float() * scale + loc
                logabsdet = torch.log(scale).sum(dim=-1)
                return outputs, logabsdet

        class _ConditionalCorrCholeskyTransform(Transform):
            """Deterministic pure-PyTorch conditional correlation Cholesky whitening w -> C(c)^-1 w."""

            def __init__(self, features: int, cond_width: int, rank: int = 6):
                super().__init__()
                self.features = features
                self.rank = min(rank, features)
                self.head = nn.Linear(cond_width, features * (self.rank + 1))
                nn.init.normal_(self.head.weight, mean=0.0, std=1e-3)
                nn.init.zeros_(self.head.bias)
                self.register_buffer("_eye", torch.eye(features, dtype=torch.float32))

            def _chol(self, context: Tensor) -> Tensor:
                if context is None:
                    raise ValueError("ConditionalCorrCholeskyTransform requires context")
                raw = self.head(context.float())
                f_part = raw[:, : self.features * self.rank].reshape(
                    -1, self.features, self.rank
                ) / math.sqrt(self.rank)
                d_part = F.softplus(raw[:, self.features * self.rank :]) + 0.35
                cov = torch.matmul(f_part, f_part.transpose(-1, -2)) + torch.diag_embed(
                    d_part.square()
                )
                inv_std = torch.rsqrt(cov.diagonal(dim1=-2, dim2=-1).clamp(min=1e-6))
                corr = cov * (inv_std[:, :, None] * inv_std[:, None, :])
                corr_reg = 0.96 * corr + 0.04 * self._eye

                n_batch = corr_reg.shape[0]
                cols: list[Tensor] = []
                for j in range(self.features):
                    diag_j = corr_reg[:, j, j]
                    if j > 0:
                        prev_row = torch.stack([cols[k][:, j] for k in range(j)], dim=-1)
                        diag_j = diag_j - (prev_row * prev_row).sum(dim=-1)
                    l_jj = torch.sqrt(diag_j.clamp(min=1e-5))
                    if j + 1 < self.features:
                        sub = corr_reg[:, j + 1 :, j]
                        if j > 0:
                            prev_sub = torch.stack([cols[k][:, j + 1 :] for k in range(j)], dim=-1)
                            sub = sub - (prev_sub * prev_row[:, None, :]).sum(dim=-1)
                        col_below = sub / l_jj[:, None]
                        col = torch.cat(
                            [corr_reg.new_zeros((n_batch, j)), l_jj[:, None], col_below], dim=-1
                        )
                    else:
                        col = torch.cat([corr_reg.new_zeros((n_batch, j)), l_jj[:, None]], dim=-1)
                    cols.append(col)
                return torch.stack(cols, dim=-1)

            def forward(self, inputs: Tensor, context: Tensor | None = None):
                chol = self._chol(context)
                x = inputs.float()
                u_cols: list[Tensor] = []
                for j in range(self.features):
                    rhs = x[:, j]
                    if j > 0:
                        u_prev = torch.stack(u_cols, dim=-1)
                        rhs = rhs - (chol[:, j, :j] * u_prev).sum(dim=-1)
                    u_cols.append(rhs / chol[:, j, j])
                outputs = torch.stack(u_cols, dim=-1)
                logabsdet = -torch.log(chol.diagonal(dim1=-2, dim2=-1)).sum(dim=-1)
                return outputs, logabsdet

            def inverse(self, inputs: Tensor, context: Tensor | None = None):
                chol = self._chol(context)
                outputs = torch.einsum("bij,bj->bi", chol, inputs.float())
                logabsdet = torch.log(chol.diagonal(dim1=-2, dim2=-1)).sum(dim=-1)
                return outputs, logabsdet

        class _LearnableUnitVarStudentTBase(Distribution):
            """Independent unit-variance Student-t base density with learnable per-horizon df."""

            def __init__(self, features: int, df_floor: float = 2.5, init_df: float = 5.0):
                super().__init__()
                self.features = features
                self.df_floor = df_floor
                init_raw = math.log(math.expm1(max(init_df - df_floor, 0.2)))
                self.raw_df = nn.Parameter(torch.full((features,), init_raw, dtype=torch.float32))

            def _dist(self, batch_shape: tuple[int, ...], device: torch.device) -> StudentT:
                df = self.df_floor + F.softplus(self.raw_df.to(device)).clamp(
                    max=STUDENT_T_DF_MAX_OFFSET
                )
                t_scale = torch.sqrt((df - 2.0) / df)
                shape = (*batch_shape, self.features)
                return StudentT(
                    df.expand(shape),
                    torch.zeros(shape, device=device, dtype=torch.float32),
                    t_scale.expand(shape),
                    validate_args=False,
                )

            def _log_prob(self, inputs: Tensor, context: Tensor | None):
                x = inputs.float()
                return self._dist((x.shape[0],), x.device).log_prob(x).sum(dim=-1)

            def _sample(self, num_samples: int, context: Tensor | None):
                if context is None:
                    return self._dist((num_samples,), self.raw_df.device).sample()
                ctx_sz = context.shape[0]
                return self._dist((ctx_sz, num_samples), context.device).sample()

        if spline_variant == "pilot_v1":
            conditioner_hidden = width
            conditioner_blocks = 2
            tail_bound = 5.0
        else:
            conditioner_hidden = max(16, (3 * width) // 8)
            conditioner_blocks = 1
            tail_bound = 6.0

        near_identity_spline = spline_variant == "campaign_v3"

        def create_conditioner(in_features: int, out_features: int):
            net = ResidualNet(
                in_features=in_features,
                out_features=out_features,
                hidden_features=conditioner_hidden,
                context_features=width,
                num_blocks=conditioner_blocks,
                dropout_probability=0.0,
                use_batch_norm=False,
            )
            if near_identity_spline:
                nn.init.normal_(net.final_layer.weight, mean=0.0, std=1e-3)
                nn.init.zeros_(net.final_layer.bias)
            return net

        transforms = []
        if spline_variant == "campaign_v3":
            transforms.append(_CumsumTransform())
            transforms.append(_ConditionalAffineTransform(horizon, width, subdiffusive_init=True))
            transforms.append(_ConditionalCorrCholeskyTransform(horizon, width, rank=6))
        elif spline_variant == "campaign_v2":
            transforms.append(_ConditionalAffineTransform(horizon, width))
        perm_gen = torch.Generator().manual_seed(1729)
        for block in range(4):
            if spline_variant in {"campaign_v2", "campaign_v3"} and block > 0 and horizon >= 4:
                transforms.append(Permutation(torch.randperm(horizon, generator=perm_gen)))
            mask = (torch.arange(horizon) + block) % 2
            transforms.append(
                PiecewiseRationalQuadraticCouplingTransform(
                    mask=mask,
                    transform_net_create_fn=create_conditioner,
                    num_bins=8,
                    tails="linear",
                    tail_bound=tail_bound,
                )
            )
        base_dist = (
            _LearnableUnitVarStudentTBase(horizon)
            if spline_variant == "campaign_v3"
            else StandardNormal([horizon])
        )
        self.flow = Flow(CompositeTransform(transforms), base_dist)

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
    *,
    spline_variant: str = "campaign_v2",
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
        return SplineTrajectoryModel(
            context_features, horizon, width, item_count, spline_variant=spline_variant
        )
    if name == "direct_marginal_student_t":
        return DirectMarginalStudentTModel(context_features, horizon, width, item_count)
    if name == "recursive_student_t":
        return RecursiveStudentTModel(context_features, horizon, width, item_count)
    return ParametricTrajectoryModel(name, context_features, horizon, width, item_count)
