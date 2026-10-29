"""Empirical uncertainty for sealed development ledgers, never synthetic training."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .data import sha256
from .diagnostics import atomic_json
from .weekly_ingest import external_directory


def block_indices(n, block, draws=2000, seed=42):
    if n < 1 or block < 1 or draws < 1:
        raise ValueError("Positive sample, block and draw counts required")
    starts = np.random.default_rng(seed).integers(0, n, size=(draws, (n + block - 1) // block))
    return ((starts[..., None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]


def empirical_interval(values):
    """Order statistics handle a no-positive-sample infinity atom without interpolation."""
    return np.quantile(values, [.025, .975], method="inverted_cdf")


def first_positive(totals, shares, active):
    if totals.shape[-1] != len(shares) or len(active) != len(shares):
        raise ValueError("Share/activation shape mismatch")
    qualifies = (totals > 0) & np.asarray(active) & (np.asarray(shares) > 0)
    return np.min(np.where(qualifies, np.asarray(shares, dtype=float), np.inf), axis=-1)


def normality(values):
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    result = {"n": len(x), "p_value": None, "lag1": None, "gaussian_eligible": False}
    if len(x) < 20 or np.ptp(x) == 0:
        return {**result, "reason": "insufficient_or_constant"}
    p = float(stats.normaltest(x).pvalue)
    lag = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    return {**result, "p_value": p, "lag1": lag,
            "gaussian_eligible": bool(p >= .05 and len(x) >= 30 and abs(lag) <= .1),
            "reason": "tested_nonrejection_is_not_proof"}


def mean_interval(values, *, block=4):
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    test = normality(x)
    if len(x) < 2:
        return {**test, "mean": None, "lower": None, "upper": None, "method": "insufficient"}
    if test["gaussian_eligible"]:
        half = stats.t.ppf(.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x))
        lower, upper = x.mean() - half, x.mean() + half
        method = "gaussian_mean_t_interval_after_normality_and_lag_screen"
    else:
        lower, upper = empirical_interval(x[block_indices(len(x), block)].mean(axis=1))
        method = f"empirical_circular_block_{block}"
    return {**test, "mean": float(x.mean()), "lower": float(lower), "upper": float(upper),
            "method": method}


def threshold_summary(values):
    lower, upper = empirical_interval(values)
    return {"lower_bps": None if np.isinf(lower) else float(lower),
            "upper_bps": None if np.isinf(upper) else float(upper),
            "lower_infinite": bool(np.isinf(lower)), "upper_infinite": bool(np.isinf(upper)),
            "no_positive_sample_fraction": float(np.isinf(values).mean())}


def daily_uncertainty(source, output, acknowledged):
    output = external_directory(output, acknowledged)
    if (output / "run.json").exists():
        raise FileExistsError("Use a new uncertainty output directory")
    manifest = json.loads((source / "run.json").read_text())
    if (manifest["status"] != "complete" or manifest["completed_scenarios"] != 810
            or manifest["holdout_read"] or manifest["price_model"] != "integer_lots_v2"):
        raise ValueError("Require complete corrected development participation experiment")
    results = pd.read_parquet(source / "results.parquet")
    if sha256(source / "results.parquet") != manifest["result_sha256"]:
        raise ValueError("Results checksum mismatch")
    if any(f["end"] > manifest["holdout_start"] for f in manifest["folds"]):
        raise ValueError("Development folds overlap holdout")
    provenance = {"status": "running", "source_manifest_sha256": sha256(source / "run.json"),
                  "code_sha256": sha256(Path(__file__)), "holdout_read": False,
                  "draws": 2000, "seed": 42, "blocks_days": [7, 14],
                  "qualification": "Conditional marked-equity paths; not an executable resampled account",
                  "threshold": "First positive frozen-grid sample; infinity=no positive; original activity gate"}
    atomic_json(output / "run.json", provenance)
    rows, thresholds, hashes = [], [], {}
    keys = ["qualification", "preset", "model"]
    for identity, group in results.groupby(keys, sort=True):
        shares = sorted(group.participation_bps.unique())
        for block in [7, 14]:
            all_totals, all_active = [], []
            for fold in range(3):
                part = group[group.fold == fold].set_index("participation_bps").loc[shares]
                increments, timestamps = [], None
                for share in shares:
                    relative = Path(f"fold{fold}/{identity[0]}/{identity[1]}/p{share:05d}/{identity[2]}/equity.parquet")
                    path = source / relative
                    curve = pd.read_parquet(path)
                    times = curve.timestamp.to_numpy()
                    boundary = manifest["folds"][fold]
                    if not ((times >= boundary["start"]) & (times < boundary["end"])).all():
                        raise ValueError("Equity outside development fold")
                    if len(times) != len(np.unique(times)) or not np.all(np.diff(times) == 86400):
                        raise ValueError("Require unique contiguous daily equity")
                    if timestamps is not None and not np.array_equal(times, timestamps):
                        raise ValueError("Unpaired scenario timestamps")
                    timestamps = times
                    pnl = np.diff(curve.equity_gp.to_numpy(dtype=float),
                                  prepend=manifest["portfolio"]["initial_cash_gp"])
                    if pnl.sum() != part.loc[share, "net_gp"]:
                        raise ValueError("Equity/summary profit mismatch")
                    increments.append(pnl)
                    hashes[str(relative)] = sha256(path)
                increments = np.asarray(increments).T
                indices = block_indices(len(increments), block, seed=42 + fold)
                totals = increments[indices].sum(axis=1)
                active = (part.buy_units_filled.to_numpy() > 0) & (part.sell_units_filled.to_numpy() > 0)
                all_totals.append(totals)
                all_active.append(active)
                base = dict(zip(keys, identity, strict=True)) | {"block_days": block, "fold": fold}
                thresholds.append({**base, **threshold_summary(first_positive(totals, shares, active))})
                for j, share in enumerate(shares):
                    lower, upper = empirical_interval(totals[:, j])
                    rows.append({**base, "participation_bps": share,
                                 "net_gp": int(part.loc[share, "net_gp"]),
                                 "lower_gp": float(lower), "upper_gp": float(upper),
                                 "positive_fraction": float((totals[:, j] > 0).mean()),
                                 "original_buys_and_sales": bool(active[j]),
                                 "method": "paired_empirical_circular_block"})
            joint = np.minimum.reduce(all_totals)
            active = np.logical_and.reduce(all_active)
            thresholds.append({**dict(zip(keys, identity, strict=True)), "block_days": block,
                               "fold": "all", **threshold_summary(first_positive(joint, shares, active))})
    pd.DataFrame(rows).to_csv(output / "profit-intervals.csv", index=False)
    pd.DataFrame(thresholds).to_csv(output / "first-positive-grid-intervals.csv", index=False)
    provenance.update(status="complete", ledger_sha256=hashes,
                      rows=len(rows), threshold_rows=len(thresholds))
    atomic_json(output / "run.json", provenance)
    head = pd.DataFrame(rows)
    print(head[(head.model == "catboost") & (head.qualification == "mean_proxy") &
               (head.participation_bps == 100)].to_string(index=False), flush=True)
    print(pd.DataFrame(thresholds).query("model == 'catboost' and qualification == 'mean_proxy'")
          .to_string(index=False), flush=True)
    print(f"Completed {len(rows)} conditional profit CIs; holdout NOT read", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-private-research", action="store_true")
    args = parser.parse_args()
    daily_uncertainty(args.source, args.output, args.acknowledge_private_research)


if __name__ == "__main__":
    main()
