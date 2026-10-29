"""Global CatBoost baseline and comparators; no cross-item or event features yet."""

from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from .costs import sale_proceeds
from .features import FULL_FEATURES, PRICE_FEATURES

TARGETS = ["return", "log_volume", "volatility", "net_per_hour"]
BASELINES = ["no_trade", "no_change", "spread_volume", "catboost"]


def matrix(frame: pd.DataFrame, track: str) -> pd.DataFrame:
    columns = PRICE_FEATURES if track == "price_only" else FULL_FEATURES
    values = frame[columns].copy()
    for column in columns:
        if column != "item":
            values[column] = values[column].astype(float)
    return values


def predict(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    track: str,
    model: str,
    horizon_seconds: int,
    model_dir: Path | None = None,
) -> pd.DataFrame:
    output = validation[["item_id", "available_at"]].copy()
    if model == "catboost":
        x = matrix(train, track)
        vx = matrix(validation, track)
        for target in TARGETS:
            valid = train[f"target_{target}"].notna()
            estimator = CatBoostRegressor(
                iterations=60,
                depth=5,
                learning_rate=0.07,
                loss_function="RMSE",
                random_seed=42,
                thread_count=2,
                verbose=False,
                allow_writing_files=False,
            )
            estimator.fit(
                x[valid],
                train.loc[valid, f"target_{target}"].astype(float),
                cat_features=["item"] if "item" in x else [],
            )
            output[f"predicted_{target}"] = estimator.predict(vx)
            if model_dir:
                model_dir.mkdir(parents=True, exist_ok=True)
                estimator.save_model(str(model_dir / f"{target}.cbm"))
        output["score"] = output.predicted_net_per_hour
    else:
        output["predicted_return"] = 0.0  # Random walk / no-change forecast.
        output["predicted_log_volume"] = np.log1p(
            validation.recent_volume.to_numpy(dtype=float) * (horizon_seconds / 3600)
        )
        output["predicted_volatility"] = validation.past_volatility.to_numpy(dtype=float)
        net = []
        for row in validation.to_dict("records"):
            high, low = row["avg_high_price"], row["avg_low_price"]
            if pd.isna(high) or pd.isna(low):
                net.append(float("nan"))
                continue
            # Spread baseline hypothesizes buying at low and selling at high;
            # the common executor still enforces high buys and low sells.
            entry, exit_ = (
                (int(low), int(high)) if model == "spread_volume" else (int(high), int(low))
            )
            net.append(
                (sale_proceeds(exit_, 1, item_id=int(row["item_id"])) / entry - 1)
                / (horizon_seconds / 3600)
            )
        output["predicted_net_per_hour"] = net
        output["score"] = (
            output.predicted_net_per_hour.to_numpy(dtype=float)
            * np.log1p(validation.recent_volume.to_numpy(dtype=float))
            if model == "spread_volume"
            else output.predicted_net_per_hour
        )
        if model == "no_trade":
            output["score"] = -np.inf
    return output


def forecast_errors(validation: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    result = {}
    for target in TARGETS:
        truth = validation[f"target_{target}"].to_numpy(dtype=float)
        predicted = predictions[f"predicted_{target}"].to_numpy(dtype=float)
        valid = np.isfinite(truth) & np.isfinite(predicted)
        result[f"{target}_mae"] = (
            float(np.abs(truth[valid] - predicted[valid]).mean()) if valid.any() else None
        )
        result[f"{target}_n"] = int(valid.sum())
    return result
