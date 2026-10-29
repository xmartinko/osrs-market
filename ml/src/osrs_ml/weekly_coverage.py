"""Aggregate complete-archive breadth and missingness without sealed market values."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import sha256
from .diagnostics import atomic_json
from .weekly_ingest import WEEK, external_directory

YEAR = 365.25 * 86400


def run(source, output, acknowledged):
    output = external_directory(output, acknowledged)
    manifest = json.loads((source / "run.json").read_text())
    if manifest["status"] != "complete" or manifest["holdout_read"]:
        raise ValueError("Require complete sealed archive")
    if sha256(source / "weekly.parquet") != manifest["panel_sha256"]:
        raise ValueError("Panel checksum mismatch")
    coverage = pd.read_csv(source / "coverage.csv")
    if set(coverage.item_id) != set(manifest["universe"]) or coverage.item_id.duplicated().any():
        raise ValueError("Coverage universe mismatch")
    panel = pd.read_parquet(source / "weekly.parquet")
    if not (panel.available_at < manifest["holdout_start"]).all():
        raise ValueError("Sealed observations in panel")
    spans, observed_years = [], []
    for kind, first, last, count in (
            ("raw_dates_only", "raw_first_timestamp", "raw_last_timestamp", "raw_rows"),
            ("development", "first_timestamp", "last_timestamp", "rows")):
        duration = (coverage[last] - coverage[first]) / YEAR
        equivalents = coverage[count] * WEEK / YEAR
        for years in range(10):
            observed_years.append(dict(scope=kind, observed_years_at_least=years,
                                       observed_years_below=years + 1,
                                       items=int((equivalents.ge(years) & equivalents.lt(years + 1) &
                                                  coverage[count].gt(0)).sum())))
            part = coverage[duration.ge(years) & duration.lt(years + 1)]
            spans.append(dict(scope=kind, span_years_at_least=years, span_years_below=years + 1,
                              items=len(part), median_observed_weeks=float(part[count].median())
                              if len(part) else None))
        spans.append(dict(scope=kind, span_years_at_least=None, span_years_below=None,
                          items=int(coverage[count].eq(0).sum()), median_observed_weeks=None))
    span_frame = pd.DataFrame(spans)
    span_frame.to_csv(output / "items-by-history-span.csv", index=False)
    pd.DataFrame(observed_years).to_csv(output / "items-by-observed-years.csv", index=False)
    starts = []
    for kind, column in (("raw_dates_only", "raw_first_timestamp"),
                         ("development", "first_timestamp")):
        counts = pd.to_datetime(coverage[column], unit="s", utc=True).dt.year.value_counts().sort_index()
        starts.extend(dict(scope=kind, first_year=int(y), items=int(n)) for y, n in counts.items())
    pd.DataFrame(starts).to_csv(output / "items-by-first-year.csv", index=False)
    grid = np.arange(panel.timestamp.min(), panel.timestamp.max() + WEEK, WEEK)
    valid = (panel[["overallPrice", "buyingPrice", "sellingPrice", "buyingCompleted",
                    "sellingCompleted"]] > 0).fillna(False).all(axis=1)
    annual = []
    grid_years = pd.to_datetime(grid, unit="s", utc=True).year
    years = pd.to_datetime(panel.timestamp, unit="s", utc=True).dt.year
    for year, group in panel.groupby(years):
        weeks = grid[grid_years == year]
        good = group[valid.loc[group.index]]
        raw_counts = group.groupby("timestamp").size().reindex(weeks, fill_value=0)
        good_counts = good.groupby("timestamp").size().reindex(weeks, fill_value=0)
        annual.append(dict(year=int(year), weeks=len(weeks), items=int(group.item_id.nunique()),
                           rows=len(group), eligible_items=int(good.item_id.nunique()),
                           eligible_rows=len(good), universe=len(coverage),
                           observed_cell_fraction=len(group) / (len(weeks) * len(coverage)),
                           eligible_cell_fraction=len(good) / (len(weeks) * len(coverage)),
                           weekly_items_min=int(raw_counts.min()),
                           weekly_items_median=float(raw_counts.median()),
                           weekly_eligible_min=int(good_counts.min()),
                           weekly_eligible_median=float(good_counts.median())))
    annual_frame = pd.DataFrame(annual)
    annual_frame.to_csv(output / "annual-breadth.csv", index=False)
    summary = dict(status="complete", holdout_read=False, universe=len(coverage),
                   statuses=coverage.status.value_counts().to_dict(),
                   raw_rows=int(coverage.raw_rows.sum()), development_rows=len(panel),
                   raw_earliest_date=str(pd.to_datetime(coverage.raw_first_timestamp.min(), unit="s", utc=True)),
                   development_latest_date=str(pd.to_datetime(panel.timestamp.max(), unit="s", utc=True)),
                   maximum_raw_span_years=float(((coverage.raw_last_timestamp -
                                                  coverage.raw_first_timestamp) / YEAR).max()),
                   source_manifest_sha256=sha256(source / "run.json"),
                   panel_sha256=manifest["panel_sha256"], code_sha256=sha256(Path(__file__)),
                   scope="Raw coverage uses dates/counts only; all market fields strictly development")
    atomic_json(output / "run.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    print(span_frame.to_string(index=False), flush=True)
    print(annual_frame.to_string(index=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-private-research", action="store_true")
    args = parser.parse_args()
    run(args.source, args.output, args.acknowledge_private_research)


if __name__ == "__main__":
    main()
