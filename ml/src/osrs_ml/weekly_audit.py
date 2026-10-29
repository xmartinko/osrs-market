"""Post-run source and bootstrap diagnostics; never refit, filter or select a rule."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import sha256
from .diagnostics import atomic_json
from .uncertainty import block_indices
from .weekly_ingest import WEEK, external_directory
from .weekly_research import epoch, features, labels, matrix


def run(source, research, output, acknowledged):
    output = external_directory(output, acknowledged)
    manifest = json.loads((research / "run.json").read_text())
    if manifest["status"] != "complete" or manifest["holdout_read"]:
        raise ValueError("Require complete sealed weekly analysis")
    if sha256(source / "weekly.parquet") != manifest["panel_sha256"]:
        raise ValueError("Panel checksum mismatch")
    panel = pd.read_parquet(source / "weekly.parquet", columns=[
        "item_id", "timestamp", "available_at", "overallPrice", "buyingPrice", "sellingPrice",
        "buyingCompleted", "sellingCompleted",
    ])
    if not (panel.available_at < manifest["holdout_start"]).all():
        raise ValueError("Sealed observations in panel")
    f = features(panel).drop(columns=["overallPrice", "buyingCompleted", "sellingCompleted"])
    del panel
    valid = f.price.notna()
    lo, hi = np.minimum(f.buyingPrice, f.sellingPrice), np.maximum(f.buyingPrice, f.sellingPrice)
    ratio = lo / f.price
    f["below_10x"], f["below_100x"] = ratio > 10, ratio > 100
    f["outside_band"] = valid & ((f.price < lo) | (f.price > hi))
    annual = []
    for year, group in f.groupby(pd.to_datetime(f.timestamp, unit="s", utc=True).dt.year):
        annual.append(dict(year=int(year), eligible=int(group.price.notna().sum()),
                           outside_band=int(group.outside_band.sum()),
                           overall_10x_below_sides=int(group.below_10x.sum()),
                           overall_100x_below_sides=int(group.below_100x.sum())))
    pd.DataFrame(annual).to_csv(output / "source-consistency-by-year.csv", index=False)
    result = dict(status="running", holdout_read=False, panel_sha256=manifest["panel_sha256"],
                  research_manifest_sha256=sha256(research / "run.json"), code_sha256=sha256(Path(__file__)),
                  qualification="Post-run audit only; frozen results unchanged; no refit or filtering",
                  eligible_rows=int(valid.sum()), outside_side_mean_band=int(f.outside_band.sum()),
                  overall_10x_below_both_sides=int(f.below_10x.sum()),
                  overall_100x_below_both_sides=int(f.below_100x.sum()),
                  overall_10x_above_both_sides=int((f.price / hi > 10).sum()), horizons=[])
    dominance = []
    for horizon in (1, 4):
        labeled = labels(f, horizon)
        extreme = labeled.target.notna() & (labeled.target > 100)
        result["horizons"].append(dict(
            horizon_weeks=horizon, observed_pairs=int(labeled.target.notna().sum()),
            returns_over_10000_percent=int(extreme.sum()),
            entry_overall_10x_below_both_sides=int((extreme & labeled.below_10x).sum()),
            maximum_observed_price_ratio=float((labeled.target + 1).max())))
        for model in [m for m in manifest["models"] if m["horizon_weeks"] == horizon]:
            year = model["year"]
            test = labeled[(labeled.available_at >= epoch(year)) &
                           (labeled.label_end < model["test_end"]) & labeled.target.notna()].copy()
            x = matrix(test)
            x = np.where(np.isfinite(x), x, np.array(model["medians"]))
            test["ridge"] = ((x - model["mean"]) / model["scale"]) @ np.array(model["beta"]) + model["intercept"]
            test["reversal_1w"], test["reversal_4w"] = -test.return_1w, -test.return_4w
            saved = pd.read_parquet(research / f"weekly-scores-{year}-h{horizon}.parquet")
            for rule in ("ridge", "reversal_1w", "reversal_4w"):
                total, rare = [], []
                for timestamp, group in test.groupby("timestamp"):
                    part = group[np.isfinite(group[rule]) & np.isfinite(group.target)]
                    if len(part) < 20:
                        continue
                    chosen = part[part[rule] >= part[rule].quantile(.9)]
                    excess = float(chosen.target_tax.mean() - part.target_tax.mean())
                    reference = saved[(saved.timestamp == timestamp) & (saved.rule == rule)].iloc[0]
                    if not np.isclose(excess, reference.top_excess_tax, rtol=1e-10, atol=1e-10):
                        raise ValueError("Frozen score replay differs; no audit inference permitted")
                    contribution = (chosen.target_tax.where(chosen.target > 100, 0).mean() -
                                    part.target_tax.where(part.target > 100, 0).mean())
                    total.append(excess)
                    rare.append(float(contribution))
                dominance.append(dict(year=year, horizon_weeks=horizon, rule=rule,
                                      frozen_excess_tax=float(np.mean(total)),
                                      extreme_contribution=float(np.mean(rare)),
                                      extreme_share=float(np.mean(rare) / np.mean(total))))
        del labeled, test, x
    pd.DataFrame(dominance).to_csv(output / "extreme-return-contributions.csv", index=False)
    # Audit missing-resample mass without changing the reported conditional intervals.
    grid = np.arange(f.timestamp.min(), f.timestamp.max() + WEEK, WEEK)
    counts = {}
    for block in (4, 8):
        indices = block_indices(len(grid), block)
        count = np.zeros((2000, len(grid)), dtype=np.uint16)
        np.add.at(count, (np.arange(2000)[:, None], indices), 1)
        counts[block] = count
    screens = pd.read_csv(research / "item-normality-intervals.csv")
    empirical = set(map(tuple, screens[screens.method == "empirical_whole_week_blocks"]
                        [["item_id", "metric"]].drop_duplicates().to_numpy()))
    empty = []
    for item_id, group in f.groupby("item_id"):
        for metric in ("log_return", "spread_fraction"):
            if (item_id, metric) not in empirical:
                continue
            present = np.isfinite(group.set_index("timestamp")[metric].reindex(grid).to_numpy())
            for block, count in counts.items():
                missing = int((count[:, present].sum(axis=1) == 0).sum())
                if missing:
                    empty.append(dict(item_id=int(item_id), metric=metric, block_weeks=block,
                                      empty_draws=missing, attempted_draws=2000))
    empty_frame = pd.DataFrame(empty, columns=["item_id", "metric", "block_weeks", "empty_draws",
                                              "attempted_draws"])
    empty_frame.to_csv(output / "empty-item-resamples.csv", index=False)
    if empty:
        summary = empty_frame.groupby(["metric", "block_weeks"]).agg(
            affected_series=("item_id", "size"), empty_draws=("empty_draws", "sum"),
            maximum_empty_draws=("empty_draws", "max"))
        summary.to_csv(output / "empty-resample-summary.csv")
        print("Per-item CIs condition on nonempty draws; missing-resample audit:", flush=True)
        print(summary.to_string(), flush=True)
    result.update(status="complete", frozen_weekly_scores_reproduced=True,
                  affected_per_item_block_cases=len(empty),
                  missing_resample_scope="Per-item mean CIs only; daily and era CIs unaffected")
    atomic_json(output / "run.json", result)
    print(json.dumps(result, indent=2), flush=True)
    print(pd.DataFrame(dominance).groupby(["horizon_weeks", "rule"]).extreme_share
          .agg(["min", "max"]).to_string(), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-private-research", action="store_true")
    args = parser.parse_args()
    run(args.source, args.research, args.output, args.acknowledge_private_research)


if __name__ == "__main__":
    main()
