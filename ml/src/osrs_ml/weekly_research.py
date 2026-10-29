"""Frozen earlier-only weekly price diagnostics; no execution or holdout claims."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .data import sha256
from .diagnostics import atomic_json
from .uncertainty import block_indices, empirical_interval, normality
from .weekly_ingest import WEEK, external_directory

FEATURES = (
    "spread_fraction", "log_price", "log_volume", "return_1w", "return_4w", "volatility_4w",
)
RULES = ("ridge", "momentum_1w", "reversal_1w", "momentum_4w", "reversal_4w",
         "spread", "volume")


def epoch(year):
    return int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())


def features(panel):
    """Only observed market values and exact causal lags enter the feature matrix."""
    f = panel.sort_values(["item_id", "timestamp"]).reset_index(drop=True).copy()
    if f.duplicated(["item_id", "timestamp"]).any():
        raise ValueError("Duplicate item/week")
    for col in ("overallPrice", "buyingPrice", "sellingPrice", "buyingCompleted", "sellingCompleted"):
        f[col] = f[col].to_numpy(dtype=float, na_value=np.nan)
    valid = (f[["overallPrice", "buyingPrice", "sellingPrice", "buyingCompleted",
                "sellingCompleted"]] > 0).all(axis=1)
    f["price"] = f.overallPrice.where(valid)
    f["spread_fraction"] = ((f.buyingPrice - f.sellingPrice) / f.price).where(valid)
    f["log_price"] = np.log(f.price)
    f["volume"] = (f.buyingCompleted + f.sellingCompleted).where(valid)
    f["log_volume"] = np.log1p(f.volume)
    g = f.groupby("item_id", sort=False)
    observed = f.set_index(["item_id", "timestamp"]).price
    for horizon in (1, 4):
        previous = pd.MultiIndex.from_arrays([f.item_id, f.timestamp - horizon * WEEK])
        past = observed.reindex(previous).to_numpy()
        f[f"return_{horizon}w"] = f.price / past - 1
    f["log_return"] = np.log1p(f.return_1w)
    f["volatility_4w"] = f.groupby("item_id", sort=False).log_return.transform(
        lambda x: x.rolling(4, min_periods=4).std())
    f.loc[f.timestamp - g.timestamp.shift(4) != 4 * WEEK, "volatility_4w"] = np.nan
    return f


def labels(f, horizon):
    """Lookup exact future observations; no row-shift horizon across gaps."""
    index = pd.MultiIndex.from_arrays([f.item_id, f.timestamp + horizon * WEEK])
    future = f.set_index(["item_id", "timestamp"]).price.reindex(index).to_numpy()
    tax = np.minimum(np.floor(future * .02), 5_000_000)
    tax = np.where(future < 50, 0, tax)
    out = f.copy()
    out["target"] = future / f.price.to_numpy() - 1
    out["target_tax"] = (future - tax) / f.price.to_numpy() - 1
    out["label_end"] = f.timestamp + (horizon + 1) * WEEK + 300
    return out


def matrix(f):
    return f[list(FEATURES)].to_numpy(dtype=float, na_value=np.nan)


def fit_rank(train, test):
    """Train-only preprocessing and ridge=1; inputs cannot include dates or item ids."""
    x, z = matrix(train), matrix(test)
    medians = np.nanmedian(x, axis=0)
    if not np.isfinite(medians).all():
        raise ValueError("An allowed feature has no training observations")
    x = np.where(np.isfinite(x), x, medians)
    z = np.where(np.isfinite(z), z, medians)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    x, z = (x - mean) / scale, (z - mean) / scale
    y = train.groupby("timestamp").target.rank(pct=True).to_numpy() - .5
    intercept = y.mean()
    beta = np.linalg.solve(x.T @ x + np.eye(len(FEATURES)), x.T @ (y - intercept))
    return z @ beta + intercept, dict(features=list(FEATURES), medians=medians.tolist(),
                                      mean=mean.tolist(), scale=scale.tolist(), beta=beta.tolist(),
                                      intercept=float(intercept), penalty=1)


def correlation(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    valid = np.isfinite(a) & np.isfinite(b)
    a, b = a[valid], b[valid]
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return np.nan
    return float(stats.spearmanr(a, b).statistic)


def weekly_scores(test, predicted):
    f = test.copy()
    f["ridge"] = predicted
    for h in (1, 4):
        f[f"momentum_{h}w"] = f[f"return_{h}w"]
        f[f"reversal_{h}w"] = -f[f"return_{h}w"]
    f["spread"], f["volume"] = f.spread_fraction, f.log_volume
    rows = []
    for timestamp, group in f.groupby("timestamp", sort=True):
        for rule in RULES:
            part = group[np.isfinite(group[rule]) & np.isfinite(group.target)]
            if len(part) < 20:
                continue
            # Fractional ranks avoid selecting arbitrary ids at a tied cutoff.
            chosen = part[part[rule] >= part[rule].quantile(.9)]
            rows.append(dict(timestamp=int(timestamp), rule=rule, items=len(part), top_items=len(chosen),
                             rank_correlation=correlation(part[rule], part.target),
                             top_excess=float(chosen.target.mean() - part.target.mean()),
                             top_excess_tax=float(chosen.target_tax.mean() - part.target_tax.mean()),
                             top_return_tax=float(chosen.target_tax.mean()),
                             universe_return_tax=float(part.target_tax.mean())))
    return pd.DataFrame(rows, columns=[
        "timestamp", "rule", "items", "top_items", "rank_correlation", "top_excess",
        "top_excess_tax", "top_return_tax", "universe_return_tax",
    ])


def weekly_interval(values, indices):
    x = np.asarray(values, dtype=float)
    if np.isfinite(x).sum() < 2:
        return dict(mean=None, lower=None, upper=None)
    means = np.nanmean(x[indices], axis=1)
    lower, upper = empirical_interval(means[np.isfinite(means)])
    return dict(mean=float(np.nanmean(x)), lower=float(lower), upper=float(upper))


def summarize_era(scores, year, horizon, grid):
    rows = []
    for block in (4, 8):
        indices = block_indices(len(grid), block)
        for rule in RULES:
            group = scores[scores.rule == rule]
            weekly = group.set_index("timestamp").reindex(grid)
            for metric in ("rank_correlation", "top_excess", "top_excess_tax", "top_return_tax",
                           "universe_return_tax"):
                n = int(weekly[metric].notna().sum())
                rows.append(dict(year=year, horizon_weeks=horizon, rule=rule,
                                 block_weeks=block, metric=metric, weeks=n,
                                 adequate=n >= 20, **weekly_interval(weekly[metric], indices)))
    return rows


def normality_diagnostics(f, output):
    train = f[(f.timestamp >= epoch(2017)) & (f.available_at < epoch(2020))]
    cuts = train.volume.dropna().quantile([1 / 3, 2 / 3]).to_numpy()
    identified = bool(np.isfinite(cuts).all() and len(np.unique(cuts)) == 2)
    atomic_json(output / "liquidity-bands.json", dict(
        training_years=[2017, 2019], identified=identified,
        cuts=[float(c) if np.isfinite(c) else None for c in cuts],
        reason="train_only_terciles" if identified else "insufficient_or_tied_training_volumes"))
    f = f.copy()
    f["band"] = np.searchsorted(cuts, f.volume.to_numpy()) if identified else -1
    f.loc[f.volume.isna(), "band"] = -1
    grid = np.arange(f.timestamp.min(), f.timestamp.max() + WEEK, WEEK)
    rows, bands = [], []
    # Whole-week indices preserve missing slots without creating market observations.
    resamples = {b: block_indices(len(grid), b) for b in (4, 8)}
    for item_id, part in f.groupby("item_id", sort=True):
        for metric in ("log_return", "spread_fraction"):
            valid = part.loc[np.isfinite(part[metric]), ["timestamp", metric]]
            x = valid[metric].to_numpy()
            screen = normality(x)
            adjacent = np.diff(valid.timestamp.to_numpy()) == WEEK
            if adjacent.sum() >= 3 and np.ptp(x[:-1][adjacent]) and np.ptp(x[1:][adjacent]):
                lag = float(np.corrcoef(x[:-1][adjacent], x[1:][adjacent])[0, 1])
            else:
                lag = None
            screen["lag1"] = lag
            screen["gaussian_eligible"] = bool(screen["p_value"] is not None and
                                               screen["p_value"] >= .05 and len(x) >= 30 and
                                               lag is not None and abs(lag) <= .1)
            base = dict(item_id=int(item_id), metric=metric, **screen)
            if len(x) < 20 or np.ptp(x) == 0:
                rows.append(dict(**base, block_weeks=0, method="insufficient_or_constant",
                                 mean=float(x.mean()) if len(x) else None, lower=None, upper=None))
            elif screen["gaussian_eligible"]:
                half = stats.t.ppf(.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x))
                rows.append(dict(**base, block_weeks=0, method="gaussian_mean_t_after_screen",
                                 mean=float(x.mean()), lower=float(x.mean() - half),
                                 upper=float(x.mean() + half)))
            else:
                series = valid.set_index("timestamp")[metric].reindex(grid).to_numpy()
                for block, indices in resamples.items():
                    rows.append(dict(**base, block_weeks=block, method="empirical_whole_week_blocks",
                                     **weekly_interval(series, indices)))
    pd.DataFrame(rows).to_csv(output / "item-normality-intervals.csv", index=False)
    for band, part in f[f.band >= 0].groupby("band"):
        for metric in ("log_return", "spread_fraction"):
            screen = normality(part.sort_values(["timestamp", "item_id"])[metric])
            series = part.groupby("timestamp")[metric].mean().reindex(grid).to_numpy()
            weekly_screen = normality(series)
            for block, indices in resamples.items():
                bands.append(dict(band=int(band), metric=metric, block_weeks=block,
                                  **screen, weekly_lag1=weekly_screen["lag1"],
                                  method="empirical_whole_week_blocks",
                                  **weekly_interval(series, indices)))
    pd.DataFrame(bands).to_csv(output / "band-normality-intervals.csv", index=False)
    print("Normality per item (unique series):", flush=True)
    print(pd.DataFrame(rows).drop_duplicates(["item_id", "metric"])
          .groupby(["metric", "gaussian_eligible"]).size().to_string(), flush=True)


def stability(f, output):
    data = f.copy()
    data["year"] = pd.to_datetime(data.timestamp, unit="s", utc=True).dt.year
    tax = np.minimum(np.floor(data.buyingPrice * .02), 5_000_000)
    tax = np.where(data.buyingPrice < 50, 0, tax)
    data["margin_tax"] = ((data.buyingPrice - tax - data.sellingPrice) /
                          data.sellingPrice).where(data.price.notna())
    cols = ["spread_fraction", "margin_tax", "volume", "return_1w", "return_4w"]
    medians = data.groupby(["year", "item_id"])[cols].median()
    rows = []
    years = sorted(data.year.unique())
    for i, a in enumerate(years):
        for b in years[i + 1:]:
            for metric in cols:
                joined = pd.concat([medians.loc[a, metric], medians.loc[b, metric]], axis=1,
                                   keys=["a", "b"]).dropna()
                rows.append(dict(earlier_year=int(a), later_year=int(b), metric=metric,
                                 common_items=len(joined), rank_correlation=correlation(joined.a, joined.b)))
    pd.DataFrame(rows).to_csv(output / "annual-ranking-stability.csv", index=False)
    annual = data.groupby("year").agg(items=("item_id", "nunique"), rows=("item_id", "size"),
                                         mean_spread=("spread_fraction", "mean"),
                                         median_spread=("spread_fraction", "median"),
                                         mean_margin_tax=("margin_tax", "mean"),
                                         median_margin_tax=("margin_tax", "median"))
    annual.to_csv(output / "annual-margins.csv")


def run(source, output, acknowledged):
    output = external_directory(output, acknowledged)
    source_manifest = json.loads((source / "run.json").read_text())
    if source_manifest["status"] != "complete" or source_manifest["holdout_read"]:
        raise ValueError("Require complete sealed archive")
    panel_path = source / "weekly.parquet"
    if sha256(panel_path) != source_manifest["panel_sha256"]:
        raise ValueError("Panel checksum mismatch")
    panel = pd.read_parquet(panel_path)
    cutoff = source_manifest["holdout_start"]
    if not ((panel.available_at < cutoff) &
            (panel.available_at == panel.timestamp + WEEK + 300)).all():
        raise ValueError("Panel contains sealed or misdated observations")
    if panel.timestamp.mod(WEEK).nunique() != 1:
        raise ValueError("Inconsistent weekly grid; cannot silently align timestamps")
    manifest = dict(status="running", holdout_read=False, holdout_start=cutoff,
                    panel_sha256=sha256(panel_path), source_manifest_sha256=sha256(source / "run.json"),
                    protocol_sha256=sha256(Path(__file__).resolve().parents[3] /
                                           "docs/deep-history-protocol.md"),
                    code_sha256=sha256(Path(__file__)), features=list(FEATURES),
                    horizons=[1, 4], blocks=[4, 8], draws=2000, seed=42, models=[])
    if (output / "run.json").exists():
        saved = json.loads((output / "run.json").read_text())
        for key in ("panel_sha256", "source_manifest_sha256", "code_sha256", "protocol_sha256"):
            if saved[key] != manifest[key]:
                raise ValueError(f"Analysis resume provenance changed: {key}")
        if saved["status"] == "complete":
            print("Analysis already complete; immutable cached result retained", flush=True)
            return
    atomic_json(output / "run.json", manifest)
    f = features(panel)
    del panel
    summaries = []
    for horizon in (1, 4):
        labeled = labels(f, horizon)
        last_year = datetime.fromtimestamp(cutoff, timezone.utc).year
        for year in range(2020, last_year + 1):
            start, end = epoch(year), min(epoch(year + 1), cutoff)
            train = labeled[(labeled.timestamp >= epoch(2017)) &
                            (labeled.available_at < start) & (labeled.label_end < start) &
                            labeled.target.notna()]
            test = labeled[(labeled.available_at >= start) & (labeled.available_at < end) &
                           (labeled.label_end < end) & labeled.target.notna()]
            score_path = output / f"weekly-scores-{year}-h{horizon}.parquet"
            model_path = output / f"fit-{year}-h{horizon}.json"
            if model_path.exists():
                model = json.loads(model_path.read_text())
                if sha256(score_path) != model["scores_sha256"]:
                    raise ValueError("Cached weekly scores checksum mismatch")
                scores = pd.read_parquet(score_path)
            else:
                identified = bool(not train.empty and np.isfinite(matrix(train)).any(axis=0).all())
                if identified and not test.empty:
                    predicted, model = fit_rank(train, test)
                    model["identified"] = True
                else:
                    predicted = np.full(len(test), np.nan)
                    model = dict(identified=False, features=list(FEATURES),
                                 reason="insufficient_training_or_test_observations")
                model.update(year=year, horizon_weeks=horizon, train_rows=len(train), test_rows=len(test),
                             max_train_label_end=int(train.label_end.max()) if len(train) else None,
                             test_start=start,
                             max_test_label_end=int(test.label_end.max()) if len(test) else None,
                             test_end=end)
                scores = weekly_scores(test, predicted)
                temporary = score_path.with_suffix(".partial.parquet")
                scores.to_parquet(temporary, index=False)
                temporary.replace(score_path)
                model["scores_sha256"] = sha256(score_path)
                atomic_json(model_path, model)
            manifest["models"].append(model)
            era_dates = labeled.loc[(labeled.available_at >= start) &
                                    (labeled.available_at < end) & (labeled.label_end < end), "timestamp"]
            if era_dates.empty:
                offset = int(f.timestamp.iloc[0]) % WEEK
                first = ((start - WEEK - 300 - offset) // WEEK + 1) * WEEK + offset
                grid = np.arange(first, max(first + WEEK, end - (horizon + 1) * WEEK - 300), WEEK)
            else:
                grid = np.arange(era_dates.min(), era_dates.max() + WEEK, WEEK)
            summaries.extend(summarize_era(scores, year, horizon, grid))
            pd.DataFrame(summaries).to_csv(output / "era-intervals.csv", index=False)
            atomic_json(output / "run.json", manifest)
            print(f"Earlier-only horizon={horizon} year={year}: train={len(train)} test={len(test)} "
                  f"weeks={len(grid)}; train labels < {start}; holdout NOT read", flush=True)
    stability(f, output)
    if not (output / "normality-complete.json").exists():
        normality_diagnostics(f, output)
        atomic_json(output / "normality-complete.json", dict(
            item_sha256=sha256(output / "item-normality-intervals.csv"),
            band_sha256=sha256(output / "band-normality-intervals.csv")))
    else:
        normality_cache = json.loads((output / "normality-complete.json").read_text())
        if (normality_cache["item_sha256"] != sha256(output / "item-normality-intervals.csv") or
                normality_cache["band_sha256"] != sha256(output / "band-normality-intervals.csv")):
            raise ValueError("Cached normality checksum mismatch")
    result = pd.DataFrame(summaries)
    screen = result[result.metric.isin(["rank_correlation", "top_excess_tax"])]
    verdict = screen.groupby(["horizon_weeks", "rule"]).agg(
        adequate=("adequate", "all"), minimum_lower=("lower", "min"), tests=("lower", "count"))
    verdict["survives_all_eras"] = verdict.adequate & (verdict.minimum_lower > 0)
    verdict.to_csv(output / "all-era-screen.csv")
    manifest.update(status="complete", summary_sha256=sha256(output / "era-intervals.csv"))
    atomic_json(output / "run.json", manifest)
    print(verdict.to_string(), flush=True)
    print("Completed weekly diagnostics; price returns are NOT executable profits; holdout NOT read", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-private-research", action="store_true")
    args = parser.parse_args()
    run(args.source, args.output, args.acknowledge_private_research)


if __name__ == "__main__":
    main()
