"""Development folds never expose final holdout observations or labels."""

from dataclasses import asdict, dataclass
from itertools import pairwise

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Fold:
    regime: str
    number: int
    validation_start: int
    validation_end: int  # exclusive; also caps evaluation labels
    holdout_start: int

    def metadata(self):
        return asdict(self)


def walk_forward_folds(frame: pd.DataFrame, folds: int = 2) -> list[Fold]:
    times = np.sort(frame.available_at.unique().astype(np.int64))
    if len(times) < 40:
        raise ValueError("Need at least 40 timestamps")
    # Freeze the most recent 20% globally, before looking at model performance.
    holdout = int(times[int(len(times) * 0.8)])
    development = frame[frame.available_at < holdout]
    result = []
    for regime, group in development.groupby("regime", sort=True):
        regime_times = np.sort(group.available_at.unique().astype(np.int64))
        if len(regime_times) < 40:
            continue
        edges = np.linspace(len(regime_times) // 2, len(regime_times), folds + 1, dtype=int)
        for number, (left, right) in enumerate(pairwise(edges)):
            end = (
                int(regime_times[right]) if right < len(regime_times) else int(regime_times[-1]) + 1
            )
            result.append(
                Fold(str(regime), number, int(regime_times[left]), min(end, holdout), holdout)
            )
    if not result:
        raise ValueError("Insufficient development data")
    return result


def split_fold(frame: pd.DataFrame, fold: Fold) -> tuple[pd.DataFrame, pd.DataFrame]:
    same_regime = frame.regime == fold.regime
    train = frame[
        same_regime
        & (frame.available_at < fold.validation_start)
        & (frame.label_end < fold.validation_start)
    ].copy()
    validation = frame[
        same_regime
        & (frame.available_at >= fold.validation_start)
        & (frame.available_at < fold.validation_end)
    ].copy()
    # Label values outside this validation period are NEVER used for forecast errors.
    invalid = validation.label_end.isna() | (validation.label_end >= fold.validation_end)
    validation.loc[
        invalid, ["target_return", "target_log_volume", "target_volatility", "target_net_per_hour"]
    ] = np.nan
    if train.empty or validation.empty:
        raise ValueError("Insufficient purged train/validation observations")
    return train, validation
