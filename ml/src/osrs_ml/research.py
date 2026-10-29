"""Frozen daily experiment, purged expanding fits, and one recorded holdout access."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from .backtest import simulate
from .cli import git_metadata, write_json
from .costs import sale_proceeds
from .data import REGIME_BREAK, load_snapshot, sha256
from .execution import PRESETS, PortfolioPolicy

DAY = 86400
MODELS = ["no_trade", "no_change", "raw_spread", "spread_volume", "catboost"]
FEATURES = [
    "return_1d",
    "return_7obs",
    "return_30obs",
    "volatility_7obs",
    "log_price",
    "spread_fraction",
    "log_volume",
    "log_volume_7obs",
    "gap_days",
    "history_rows",
    "high_missing",
    "low_missing",
    "item",
]


def daily_features(frame: pd.DataFrame, *, labels: bool = True) -> pd.DataFrame:
    f = frame.sort_values(["item_id", "available_at"]).copy().reset_index(drop=True)
    high = f.avg_high_price.to_numpy(dtype=float, na_value=np.nan)
    low = f.avg_low_price.to_numpy(dtype=float, na_value=np.nan)
    bad = f.inverted_spread.fillna(False).to_numpy(dtype=bool)
    high[bad], low[bad] = np.nan, np.nan
    f["price"] = (high + low) / 2
    f["high"] = high
    f["low"] = low
    g = f.groupby("item_id", sort=False)
    f["gap_days"] = g.available_at.diff().astype(float) / DAY
    f["return_1d"] = (f.price / g.price.shift(1) - 1).where(f.gap_days == 1)
    f["return_7obs"] = f.price / g.price.shift(7) - 1
    f["return_30obs"] = f.price / g.price.shift(30) - 1
    f["volatility_7obs"] = f.groupby("item_id").return_1d.transform(
        lambda s: s.rolling(7, min_periods=2).std()
    )
    volume = (f.high_price_volume + f.low_price_volume).astype(float)
    f["log_volume"] = np.log1p(volume)
    f["log_volume_7obs"] = np.log1p(
        volume.groupby(f.item_id).transform(lambda s: s.rolling(7, min_periods=1).mean())
    )
    f["log_price"] = np.log(f.price)
    f["spread_fraction"] = (high - low) / f.price
    f["high_missing"] = np.isnan(high).astype(int)
    f["low_missing"] = np.isnan(low).astype(int)
    f["history_rows"] = g.cumcount() + 1
    f["item"] = f.item_id.astype(str)
    # Forecast target is tax-aware instantaneous entry/exit return, normalized for scale.
    # Its score converts back to per-unit gp/hour for ranking.
    if labels:
        end = g.available_at.shift(-1)
        future_low = g.low.shift(-1).to_numpy(dtype=float)
        valid = (end - f.available_at == DAY) & np.isfinite(high) & np.isfinite(future_low)
        proceeds = np.array(
            [
                sale_proceeds(int(p), 1, item_id=int(i)) if np.isfinite(p) else np.nan
                for p, i in zip(future_low, f.item_id, strict=True)
            ]
        )
        f["label_end"] = end.where(valid)
        f["target"] = proceeds / high - 1
        f.loc[~valid, "target"] = np.nan
    return f


def matrix(f):
    x = f[FEATURES].copy()
    for col in FEATURES:
        if col != "item":
            x[col] = x[col].astype(float).replace([np.inf, -np.inf], np.nan)
    return x


def forecasts(train, validation, config, output):
    """One global baseline; no cross-item, event, or current metadata features."""
    output.mkdir()
    valid = train.target.notna() & (train.history_rows >= 14)
    x, y = matrix(train.loc[valid]), train.loc[valid, "target"].astype(float)
    if len(y) < 100:
        raise ValueError("Insufficient purged training labels")
    bounds = y.quantile([0.005, 0.995]).to_list()
    y = y.clip(*bounds)  # Train-only robustification; errors use original, unclipped outcomes.
    params = {
        **config["catboost"],
        "random_seed": config["seed"],
        "verbose": False,
        "allow_writing_files": False,
    }
    model = CatBoostRegressor(**params, loss_function="RMSE")
    model.fit(x, y, cat_features=["item"])
    model.save_model(str(output / "net_return.cbm"))
    quantile = CatBoostRegressor(**params, loss_function="MultiQuantile:alpha=0.1,0.5,0.9")
    quantile.fit(x, y, cat_features=["item"])
    quantile.save_model(str(output / "quantiles.cbm"))
    write_json(
        output / "training.json",
        {
            "rows": len(y),
            "items": train.loc[valid].item_id.nunique(),
            "max_label_end": int(train.loc[valid].label_end.max()),
            "clip_bounds": bounds,
            "features": FEATURES,
            "parameters": params,
        },
    )
    vx = matrix(validation)
    predicted = model.predict(vx)
    q = quantile.predict(vx)
    high = validation.high.to_numpy(dtype=float)
    low = validation.low.to_numpy(dtype=float)
    sell_high = np.array(
        [
            sale_proceeds(int(p), 1, item_id=int(i)) if np.isfinite(p) else np.nan
            for p, i in zip(high, validation.item_id, strict=True)
        ]
    )
    sell_low = np.array(
        [
            sale_proceeds(int(p), 1, item_id=int(i)) if np.isfinite(p) else np.nan
            for p, i in zip(low, validation.item_id, strict=True)
        ]
    )
    result = validation[["item_id", "available_at"]].copy()
    result["predicted_return"] = predicted
    result["q10"], result["q50"], result["q90"] = q.T
    result["no_trade"] = -np.inf
    result["no_change"] = (sell_low - high) / 24
    result["raw_spread"] = sell_high - low
    # Literal spread × volume, using the smaller observed side as the capacity proxy.
    result["spread_volume"] = (sell_high - low) * np.minimum(
        validation.high_price_volume.astype(float), validation.low_price_volume.astype(float)
    )
    result["catboost"] = predicted * high / 24
    result.loc[validation.history_rows < 14, MODELS] = -np.inf
    result.to_parquet(output / "predictions.parquet", index=False)
    truth = validation.target.to_numpy(dtype=float)
    usable = np.isfinite(truth)
    errors = {"n": int(usable.sum())}
    if usable.any():
        errors["return_mae"] = float(np.abs(predicted[usable] - truth[usable]).mean())
        errors["no_change_mae"] = float(np.abs(truth[usable]).mean())
        errors["interval_80_coverage"] = float(
            ((truth[usable] >= q[usable, 0]) & (truth[usable] <= q[usable, 2])).mean()
        )
        for j, alpha in enumerate([0.1, 0.5, 0.9]):
            delta = truth[usable] - q[usable, j]
            errors[f"pinball_{alpha}"] = float(
                np.maximum(alpha * delta, (alpha - 1) * delta).mean()
            )
    write_json(output / "errors.json", errors)
    return result, errors


def execute(validation, predictions, config, root, phase, fold):
    portfolio = PortfolioPolicy(
        initial_cash_gp=config["cash_gp"],
        offer_slots=config["offer_slots"],
        allocation_bps=config["allocation_bps"],
        holding_seconds=DAY,
    )
    rows = []
    for limits in ["unknown_limits_strict", "current_limits_sensitivity"]:
        observations = validation.copy()
        if limits == "current_limits_sensitivity":
            observations["buy_limit"] = observations.buy_limit_current
        for name, overrides in config["execution"].items():
            policy = replace(PRESETS[name], **overrides, allow_unknown_metadata=True)
            for model in MODELS:
                path = root / limits / name / model
                path.mkdir(parents=True)
                scores = dict(
                    zip(
                        zip(
                            predictions.item_id.astype(int),
                            predictions.available_at.astype(int),
                            strict=True,
                        ),
                        predictions[model].astype(float),
                        strict=True,
                    )
                )
                result = simulate(observations, scores, policy, portfolio)
                metrics = result.metrics
                # A fixed 7-day moving-block bootstrap describes temporal uncertainty,
                # not independent trades. Sparse daily returns yield very wide intervals.
                equity = np.array([p["equity_gp"] for p in result.equity], dtype=float)
                pnl = np.diff(equity, prepend=portfolio.initial_cash_gp)
                rng = np.random.default_rng(config["seed"])
                blocks = np.array(
                    [np.take(pnl, np.arange(i, i + 7) % len(pnl)) for i in range(len(pnl))]
                )
                draws = blocks[rng.integers(0, len(blocks), (500, (len(pnl) + 6) // 7))]
                totals = draws.reshape(500, -1)[:, : len(pnl)].sum(axis=1)
                metrics["bootstrap_net_gp_p05"] = float(np.quantile(totals, 0.05))
                metrics["bootstrap_net_gp_p95"] = float(np.quantile(totals, 0.95))
                metrics["daily_pnl_cvar_10"] = float(np.sort(pnl)[: max(1, len(pnl) // 10)].mean())
                metrics["regime_net_gp"] = {}
                for regime, mask in [
                    (
                        "pre_2026_09_30",
                        np.array([p["timestamp"] < REGIME_BREAK for p in result.equity]),
                    ),
                    (
                        "post_2026_09_30",
                        np.array([p["timestamp"] >= REGIME_BREAK for p in result.equity]),
                    ),
                ]:
                    metrics["regime_net_gp"][regime] = float(pnl[mask].sum())
                write_json(path / "metrics.json", metrics)
                for kind in ["fills", "orders", "equity"]:
                    pd.DataFrame(getattr(result, kind)).to_parquet(
                        path / f"{kind}.parquet", index=False
                    )
                rows.append(
                    {
                        "phase": phase,
                        "fold": fold,
                        "limits": limits,
                        "preset": name,
                        "model": model,
                        **{
                            k: v
                            for k, v in metrics.items()
                            if k not in ["execution", "portfolio", "tax", "regime_net_gp"]
                        },
                    }
                )
                print(
                    f"{phase} fold={fold} {limits} {name} {model}: "
                    f"{metrics['net_gp']} gp; {metrics['net_gp_per_hour']:.2f} gp/h",
                    flush=True,
                )
    return rows


def experiment(panel: Path, output: Path, config_path: Path, *, holdout: bool = False):
    if holdout:
        metadata = json.loads((output / "run.json").read_text())
        selection = json.loads((output / "selection.json").read_text())
        if metadata["status"] != "development_complete" or selection["sha256"] != sha256(
            output / "results.parquet"
        ):
            raise ValueError("Complete, unchanged development selection required before holdout")
        if metadata["panel_sha256"] != sha256(panel) or metadata["config_sha256"] != sha256(
            config_path
        ):
            raise ValueError("Panel/config changed after selection")
        if metadata["git"]["commit"] != git_metadata()["commit"] or git_metadata()["dirty"]:
            raise ValueError("Run holdout with the same clean committed implementation")
        # Exclusive marker means a failed/partial opening is still an access, never quietly repeated.
        with (output / "holdout_access.json").open("x") as stream:
            json.dump({"selection": selection, "git": git_metadata()}, stream, indent=2)
    else:
        output.mkdir(parents=True, exist_ok=False)
    config = json.loads(config_path.read_text())
    frame = load_snapshot(panel, allow_unknown_metadata=True)
    keep = [
        "item_id",
        "timestamp",
        "available_at",
        "avg_high_price",
        "avg_low_price",
        "high_price_volume",
        "low_price_volume",
        "buy_limit",
        "buy_limit_current",
        "inverted_spread",
        "interval_unknown",
        "resolution_seconds",
        "source_interval_seconds",
        "high_freshness_seconds",
        "low_freshness_seconds",
        "source",
    ]
    frame = frame[keep]
    if not frame.resolution_seconds.eq(DAY).all() or not frame.source.eq("wiki").all():
        raise ValueError("This experiment requires one strict Wiki daily panel")
    end = int(frame.available_at.max()) + DAY
    cutoff = end - config["holdout_days"] * DAY
    if not holdout:
        metadata = {
            "status": "running",
            "git": git_metadata(),
            "panel_sha256": sha256(panel),
            "config_sha256": sha256(config_path),
            "config": config,
            "holdout_start": cutoff,
            "holdout_end": end,
            "holdout_evaluated": False,
            "source": "wiki",
            "availability": "inferred event-time, not ingestion replay",
            "lock_sha256": sha256(Path(__file__).resolve().parents[2] / "uv.lock"),
        }
        write_json(output / "run.json", metadata)
    development = frame[frame.available_at < cutoff].copy()
    del frame
    features = daily_features(development)
    del development
    rows = []
    if holdout:
        # Only after the durable selection/access marker do we construct holdout features.
        frame = load_snapshot(panel, allow_unknown_metadata=True)
        frame = frame[keep]
        # Only the last 30 pre-holdout observations are needed for causal windows.
        frame = pd.concat(
            [
                frame[frame.available_at < cutoff].groupby("item_id").tail(30),
                frame[frame.available_at >= cutoff],
            ],
            ignore_index=True,
        )
        all_features = daily_features(frame)
        del frame
        validation = all_features[all_features.available_at >= cutoff].copy()
        validation.loc[validation.label_end >= end, "target"] = np.nan
        train = features[(features.label_end < cutoff) & features.target.notna()]
        path = output / "holdout"
        path.mkdir()
        prediction, _ = forecasts(train, validation, config, path / "forecast")
        rows.extend(execute(validation, prediction, config, path, "holdout", 0))
        pd.DataFrame(rows).to_parquet(path / "results.parquet", index=False)
        metadata.update(
            status="complete", holdout_evaluated=True, selected_model=selection["model"]
        )
    else:
        starts = [
            cutoff - (config["folds"] - i) * config["fold_days"] * DAY
            for i in range(config["folds"])
        ]
        metadata["folds"] = []
        for i, start in enumerate(starts):
            stop = start + config["fold_days"] * DAY
            train = features[(features.available_at < start) & (features.label_end < start)]
            validation = features[
                (features.available_at >= start) & (features.available_at < stop)
            ].copy()
            validation.loc[validation.label_end >= stop, "target"] = np.nan
            metadata["folds"].append(
                {
                    "start": start,
                    "end": stop,
                    "train_rows": len(train),
                    "train_max_label_end": int(train.label_end.max()),
                }
            )
            path = output / f"fold{i}"
            path.mkdir()
            prediction, _ = forecasts(train, validation, config, path / "forecast")
            rows.extend(execute(validation, prediction, config, path, "development", i))
            # Save every completed fold before starting the next fit.
            pd.DataFrame(rows).to_parquet(output / "results.parquet", index=False)
            write_json(output / "run.json", metadata)
        results = pd.DataFrame(rows)
        candidates = results[
            (results.limits == "current_limits_sensitivity") & (results.preset == "moderate")
        ]
        gp = candidates.groupby("model").net_gp.sum()
        selected = sorted(gp.index, key=lambda m: (-gp[m], m != "no_trade", m))[0]
        write_json(
            output / "selection.json",
            {
                "model": selected,
                "development_net_gp": gp.to_dict(),
                "sha256": sha256(output / "results.parquet"),
                "protocol": config["selection"],
            },
        )
        metadata["status"] = "development_complete"
    write_json(output / "run.json", metadata)
    summary = (
        pd.DataFrame(rows)
        .groupby(["limits", "preset", "model"])
        .agg(
            net_gp=("net_gp", "sum"),
            hours=("elapsed_hours", "sum"),
            drawdown=("max_drawdown", "max"),
            fill_rate=("fill_rate", "mean"),
        )
    )
    summary["gp_hour"] = summary.net_gp / summary.hours
    print(summary.to_string(), flush=True)
