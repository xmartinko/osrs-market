"""Causal features and timestamp-horizon labels, without assuming a constant step."""

import numpy as np
import pandas as pd

from .costs import net_return, tax_per_item

PRICE_FEATURES = ["return_previous", "return_1h", "return_4h", "past_volatility"]
FULL_FEATURES = PRICE_FEATURES + [
    "spread_fraction",
    "recent_volume",
    "high_freshness",
    "low_freshness",
    "buy_limit_feature",
    "tax_fraction",
    "item",
]


def build_features(frame: pd.DataFrame, horizon_seconds: int) -> pd.DataFrame:
    if horizon_seconds not in (3600, 14_400, 86_400):
        raise ValueError("Supported horizons: 1h, 4h, 24h")
    parts = []
    for item, raw in frame.groupby("item_id", sort=True):
        raw = raw.sort_values("available_at").copy().reset_index(drop=True)
        high = raw.avg_high_price.to_numpy(dtype=float, na_value=np.nan)
        low = raw.avg_low_price.to_numpy(dtype=float, na_value=np.nan)
        mid = (high + low) / 2
        times = raw.available_at.to_numpy(dtype=np.int64)
        returns = np.r_[np.nan, mid[1:] / mid[:-1] - 1]
        raw["return_previous"] = returns
        for seconds, name in [(3600, "return_1h"), (14_400, "return_4h")]:
            indices = np.searchsorted(times, times - seconds, side="right") - 1
            raw[name] = [
                mid[i] / mid[j] - 1 if j >= 0 and np.isfinite(mid[j]) else np.nan
                for i, j in enumerate(indices)
            ]
        time_index = pd.to_datetime(times, unit="s", utc=True)
        raw["past_volatility"] = pd.Series(returns, index=time_index).rolling("4h").std().to_numpy()
        volume = (raw.high_price_volume + raw.low_price_volume).to_numpy(dtype=float)
        raw["recent_volume"] = pd.Series(volume, index=time_index).rolling("1h").sum().to_numpy()
        raw["spread_fraction"] = (high - low) / mid
        raw["high_freshness"] = raw.high_freshness_seconds.to_numpy(dtype=float, na_value=np.nan)
        raw["low_freshness"] = raw.low_freshness_seconds.to_numpy(dtype=float, na_value=np.nan)
        raw["buy_limit_feature"] = raw.buy_limit.to_numpy(dtype=float, na_value=np.nan)
        raw["tax_fraction"] = [
            tax_per_item(int(p), item_id=int(item)) / int(p) if not pd.isna(p) else np.nan
            for p in raw.avg_low_price
        ]
        raw["item"] = str(item)
        ends = np.searchsorted(times, times + horizon_seconds, side="left")
        label_ends, return_labels, volume_labels, volatility_labels, net_labels = [], [], [], [], []
        for i, j in enumerate(ends):
            # A missing bucket must not stretch a 1h target into a multi-day target.
            valid = (
                j < len(times)
                and times[j] <= times[i] + horizon_seconds + 600
                and np.isfinite(mid[i])
                and np.isfinite(mid[j])
                and np.isfinite(high[i])
                and np.isfinite(low[j])
                and raw.regime.iloc[i] == raw.regime.iloc[j]
            )
            label_ends.append(int(times[j]) if valid else None)
            return_labels.append(mid[j] / mid[i] - 1 if valid else np.nan)
            volume_labels.append(float(np.log1p(volume[i + 1 : j + 1].sum())) if valid else np.nan)
            volatility_labels.append(float(np.nanstd(returns[i + 1 : j + 1])) if valid else np.nan)
            net_labels.append(
                net_return(
                    int(raw.avg_high_price.iloc[i]),
                    int(raw.avg_low_price.iloc[j]),
                    item_id=int(item),
                )
                / (horizon_seconds / 3600)
                if valid
                else np.nan
            )
        raw["label_end"] = pd.array(label_ends, dtype="int64[pyarrow]")
        raw["target_return"] = return_labels
        raw["target_log_volume"] = volume_labels
        raw["target_volatility"] = volatility_labels
        raw["target_net_per_hour"] = net_labels
        parts.append(raw)
    return pd.concat(parts, ignore_index=True)
