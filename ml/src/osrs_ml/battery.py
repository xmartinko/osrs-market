"""Frozen, finite strategy search. All inputs/ledgers stay outside Git."""

import argparse
import gc
import json
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .backtest import PreparedObservations, simulate
from .costs import DEFAULT_TAX, TaxPolicy
from .data import sha256
from .diagnostics import atomic_json
from .execution import ExecutionAssumptions, PortfolioPolicy
from .uncertainty import block_indices
from .weekly_ingest import WEEK, external_directory

DAY = 86400
CAPITAL = 10_000_000
PAIRS = {
    "herbs": [(257, 2434), (3000, 3024), (2998, 6685)],
    "ores": [(440, 2351), (453, 2353), (451, 2363)],
    "resources": [(383, 385), (1513, 859), (536, 22124)],
}
EXEMPT_NAMES = (
    "Bronze arrow", "Iron arrow", "Steel arrow", "Bronze dart", "Iron dart", "Steel dart",
    "Mind rune", "Bass", "Bread", "Cake", "Cooked chicken", "Cooked meat", "Herring",
    "Lobster", "Mackerel", "Meat pie", "Pike", "Salmon", "Shrimps", "Tuna", "Chisel",
    "Hammer", "Needle", "Pestle and mortar", "Rake", "Saw", "Secateurs", "Seed dibber",
    "Shears", "Spade",
)


def sealed_read(path, cutoff, *, start=None, columns="*"):
    """Predicate precedes materialization; never return sealed market observations."""
    if cutoff <= 0 or (start is not None and start >= cutoff):
        raise ValueError("Invalid development boundary")
    with duckdb.connect() as db:
        sql = f"SELECT {columns} FROM read_parquet(?) WHERE available_at < ?"
        args = [str(path), int(cutoff)]
        if start is not None:
            sql += " AND available_at >= ?"
            args.append(int(start))
        return db.execute(sql + " ORDER BY item_id, timestamp", args).fetchdf()


def exact(frame, values, delta):
    """Exact event-time lookup; missing buckets cannot become adjacent lags."""
    source = pd.Series(np.asarray(values), index=pd.MultiIndex.from_frame(
        frame[["item_id", "timestamp"]]))
    keys = pd.MultiIndex.from_arrays([frame.item_id, frame.timestamp - delta])
    return source.reindex(keys).to_numpy(dtype=float, na_value=np.nan)


def common_features(frame, horizon, tax=DEFAULT_TAX):
    f = frame.copy()
    valid = ((f.avg_high_price > 0) & (f.avg_low_price > 0) &
             (f.avg_high_price >= f.avg_low_price) &
             (f.high_price_volume > 0) & (f.low_price_volume > 0))
    f["price"] = f.get("overallPrice", (f.avg_high_price + f.avg_low_price) / 2).where(valid)
    f["volume"] = np.minimum(f.high_price_volume, f.low_price_volume).where(valid)
    high = f.avg_high_price.to_numpy(dtype=float, na_value=np.nan)
    taxes = np.where(high <= tax.exempt_through_gp, 0,
                     np.minimum(np.floor(high * tax.rate_bps / 10000), tax.cap_gp))
    taxes[np.isin(f.item_id, tax.exempt_item_ids)] = 0
    f["spread"] = ((high - taxes) / f.avg_low_price - 1).where(valid)
    prices = [f.price.to_numpy()] + [exact(f, f.price, horizon * k) for k in range(1, 5)]
    with np.errstate(divide="ignore", invalid="ignore"):
        f["ret"] = prices[0] / prices[1] - 1
        log_returns = np.array([np.log(prices[k] / prices[k + 1]) for k in range(4)])
    f["vol"] = np.std(log_returns, axis=0, ddof=1)
    f["range"] = np.mean(np.abs(np.expm1(log_returns)), axis=0)
    return f


def top_decile(f, score):
    score = pd.Series(np.asarray(score, dtype=float), index=f.index)
    score = score.where(np.isfinite(score) & (score > 0))
    cutoff = score.groupby(f.available_at).transform(lambda s: s.quantile(.9))
    return score.where(score >= cutoff)


def strategy_scores(frame, spec, start, end, tax=DEFAULT_TAX):
    f = common_features(frame, spec["horizon"], tax)
    rule = spec["rule"]
    score = pd.Series(np.nan, index=f.index)
    allocations = None
    if rule in ("xs_reversal", "abs_reversal", "vol_size", "patient"):
        score = -f.ret
    elif rule in ("xs_momentum", "abs_momentum"):
        score = f.ret
    elif rule == "range":
        score = np.minimum(f.spread, f["range"])
    elif rule == "persistent_spread":
        parts = np.array([f.spread] + [exact(f, f.spread, k * spec["resolution"])
                                      for k in range(1, 4)])
        score = pd.Series(np.where((parts > 0).all(axis=0), parts.mean(axis=0), np.nan))
    elif rule == "volume_shock":
        past = np.array([exact(f, f.volume, k * spec["resolution"]) for k in range(1, 5)])
        ratio = f.volume / past.mean(axis=0)
        score = (f.ret * ratio).where((ratio >= 2) & (f.ret > 0))
    elif rule in ("limit_spread", "low_tax"):
        score = f.spread.copy()
        if rule == "limit_spread":
            q = np.minimum(np.minimum(f.buy_limit, .01 * f.volume), 1_000_000 / f.avg_low_price)
            score = score * f.avg_low_price * np.floor(q)
        else:
            score = score.where((f.avg_high_price < 50) | f.item_id.isin(tax.exempt_item_ids))
    elif rule in ("lead", "convergence"):
        for a, b in PAIRS[spec["family"]]:
            left, right = f[f.item_id == a], f[f.item_id == b]
            if left.empty or right.empty:
                continue
            joined = left[["timestamp", "price", "ret", "available_at"]].merge(
                right[["timestamp", "price", "ret", "available_at"]], on="timestamp",
                suffixes=("_a", "_b"))
            joined = joined[joined.available_at_a == joined.available_at_b]
            if rule == "lead":
                delta = joined.ret_a - joined.ret_b
                for ts, s in zip(joined.timestamp, delta, strict=True):
                    if np.isfinite(s) and s >= .05:
                        score.loc[(f.item_id == b) & (f.timestamp == ts)] = s
            else:
                ratio = np.log(joined.price_b / joined.price_a)
                series = pd.Series(ratio.to_numpy(), index=joined.timestamp)
                past = np.array([series.reindex(joined.timestamp - k * spec["resolution"])
                                 .to_numpy() for k in range(8)])
                deviation = ratio.to_numpy() - past.mean(axis=0)
                for ts, s in zip(joined.timestamp, deviation, strict=True):
                    if np.isfinite(s) and abs(s) >= .1:
                        item = b if s < 0 else a
                        score.loc[(f.item_id == item) & (f.timestamp == ts)] = abs(s)
    else:
        raise ValueError(f"Unregistered rule {rule}")
    score = pd.Series(np.asarray(score), index=f.index)
    if rule.startswith("abs_"):
        score = score.where(score >= spec["threshold"])
    elif rule == "patient":
        score = score.where((score >= spec["threshold"]) &
                            ((1 / (1 - score) - 1 - .022) >= .08))
        if spec["resolution"] == DAY:
            score = score.where((f.timestamp // DAY) % 2 == 0)
        chosen = f.assign(score=score).dropna(subset=["score"])
        chosen = chosen.sort_values(["available_at", "score", "item_id"],
                                    ascending=[True, False, True]).drop_duplicates("available_at")
        score = score.where(f.index.isin(chosen.index))
    else:
        score = top_decile(f, score)
    eligible = ((f.available_at >= start) &
                (f.available_at < end - spec["holding"] - 3 * spec["resolution"]) &
                f.price.notna() & score.gt(0) & np.isfinite(score))
    keys = list(zip(f.loc[eligible, "item_id"].astype(int),
                    f.loc[eligible, "available_at"].astype(int), strict=True))
    scores = dict(zip(keys, score[eligible].astype(float), strict=True))
    if rule == "vol_size":
        eligible &= f.vol.notna()
        keys = list(zip(f.loc[eligible, "item_id"].astype(int),
                        f.loc[eligible, "available_at"].astype(int), strict=True))
        scores = dict(zip(keys, score[eligible].astype(float), strict=True))
        bps = np.floor(1000 * np.minimum(1, .05 / np.maximum(f.loc[eligible, "vol"], .01)))
        allocations = dict(zip(keys, np.maximum(1, bps).astype(int).tolist(), strict=True))
    diagnostic = None
    if rule in ("vol_size", "range"):
        future = exact(f, f.price, -spec["horizon"])
        target = np.abs(future / f.price - 1)
        valid = ((f.available_at >= start) &
                 (f.available_at + spec["horizon"] < end) & np.isfinite(target))
        metric = f.vol if rule == "vol_size" else f["range"]
        diagnostic = metric[valid].corr(pd.Series(target, index=f.index)[valid], method="spearman")
        diagnostic = float(diagnostic) if np.isfinite(diagnostic) else None
    return scores, allocations, diagnostic


def bootstrap_test(increments, blocks, *, completed, draws=20000, seed=42):
    x = np.asarray(increments, dtype=float)
    adequate = len(x) >= 4 * max(blocks) and completed >= 10
    detail = []
    for block in blocks:
        if not len(x):
            detail.append(dict(block=block, p=1., lower=None, upper=None))
            continue
        indices = block_indices(len(x), block, draws=draws, seed=seed)
        totals = x[indices].sum(axis=1)
        observed = float(x.sum())
        centered = totals - observed
        p = float((1 + np.count_nonzero(centered >= observed)) / (draws + 1))
        if not adequate or observed <= 0 or np.ptp(x) == 0:
            p = 1.
        lo, hi = np.quantile(totals, [.025, .975], method="inverted_cdf")
        detail.append(dict(block=int(block), p=p, lower=float(lo), upper=float(hi)))
    return dict(adequate=adequate, p=max(t["p"] for t in detail),
                lower=min((t["lower"] for t in detail if t["lower"] is not None), default=None),
                upper=max((t["upper"] for t in detail if t["upper"] is not None), default=None),
                blocks=detail)


def corrected(p, family_size=213):
    if not np.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("Invalid bootstrap p")
    return min(1., family_size * p)


def completed_positions(fills):
    inventory, count = {}, 0
    for f in fills:
        item, q = f["item_id"], f["quantity"]
        inventory[item] = inventory.get(item, 0) + (q if f["side"] == "buy" else -q)
        if f["side"] == "sell" and inventory[item] == 0:
            count += 1
    return count


def summarize(result, spec, share, observations, *, completed=None):
    m = result.metrics
    curve = pd.DataFrame(result.equity)
    fills = pd.DataFrame(result.fills)
    timestamps = curve.timestamp.to_numpy(dtype=np.int64)
    resolution = spec["resolution"]
    grid = np.arange(timestamps.min(), timestamps.max() + resolution, resolution)
    if not np.isin(timestamps, grid).all():
        raise ValueError("Off-grid equity dates")
    # Carry the account state across missing observation timestamps; never create market rows.
    equity = curve.set_index("timestamp").equity_gp.reindex(grid).ffill().to_numpy()
    increments = np.diff(equity, prepend=CAPITAL)
    block = max(4 if resolution == WEEK else DAY // resolution if resolution < DAY else 7,
                int(np.ceil(spec["holding"] / resolution)))
    completed = completed_positions(result.fills) if completed is None else completed
    inference = bootstrap_test(increments, [block, 2 * block], completed=completed)
    costs = sum(f.get("slippage_cost_gp", 0) + f.get("tick_cost_gp", 0) + f["tax_gp"]
                for f in result.fills)
    terminal_adjustment = m["end_inventory_gross_mark_gp"] - m["end_inventory_mark_gp"]
    # Restore tax/slippage/haircut on final owned units at latest unadjusted low price.
    terminal_raw = m.get("terminal_raw_gp")
    if terminal_raw is None:
        remaining = {}
        for f in result.fills:
            i = f["item_id"]
            remaining[i] = remaining.get(i, 0) + (1 if f["side"] == "buy" else -1) * f["quantity"]
        latest = observations.sort_values("available_at").drop_duplicates("item_id", keep="last")
        prices = latest.set_index("item_id").avg_low_price.to_dict()
        terminal_raw = sum(q * int(prices[i]) for i, q in remaining.items()
                           if q and i in prices and pd.notna(prices[i]))
        terminal_adjustment = terminal_raw - m["end_inventory_mark_gp"]
    else:
        terminal_adjustment = terminal_raw - m["end_inventory_mark_gp"]
    peak_share = 0.
    used_capacity = 0
    if not fills.empty:
        source = observations.set_index(["item_id", "available_at"])
        for (i, ts, side), part in fills.groupby(["item_id", "timestamp", "side"]):
            side_name = ("high" if side == "sell" else "low")
            if spec["rule"] in ("alchemy", "processing"):
                side_name = "high" if side == "buy" else "low"
            volume = int(source.loc[(i, ts), f"{side_name}_price_volume"])
            q = int(part.quantity.sum())
            if volume:
                peak_share = max(peak_share, q / volume)
            used_capacity += q
    years = pd.to_datetime(grid, unit="s", utc=True).year
    annual = pd.DataFrame(dict(year=years, increment=increments)).groupby("year").increment.sum()
    row = dict(id=spec["id"], rule=spec["rule"], horizon_seconds=spec["horizon"],
               holding_seconds=spec["holding"], resolution_seconds=resolution,
               participation_bps=share, universe_items=int(observations.item_id.nunique()),
               status="tested" if inference["adequate"] else "inconclusive",
               reason="conditional_aggregate_fills" if inference["adequate"] else
               "fewer_than_10_completions_or_4_larger_blocks",
               trades=completed, gross_gp=m["net_gp"] + costs + terminal_adjustment,
               tax_gp=sum(f["tax_gp"] for f in result.fills), capacity_units=used_capacity,
               peak_observed_share=peak_share, p_raw=inference["p"],
               p_adjusted=corrected(inference["p"]), lower_gp=inference["lower"],
               upper_gp=inference["upper"], profitable_years=int((annual > 0).sum()),
               observed_years=len(annual), **{k: m[k] for k in (
                   "net_gp", "net_gp_per_hour", "elapsed_hours", "return_on_capital", "max_drawdown",
                   "mean_capital_tied_gp", "peak_capital_tied_gp", "end_inventory_mark_gp",
                   "end_inventory_units", "cash_pnl_gp", "realized_gp", "turnover",
                   "buy_units_filled", "sell_units_filled")})
    row["survives"] = bool(row["p_adjusted"] < .05 and (inference["lower"] or 0) > 0)
    if "active_hours" in m:
        row.update(active_hours=m["active_hours"], active_gp_per_hour=m["active_gp_per_hour"],
                   produced_units=m["produced_units"])
    return row, increments, dict(inference=inference, annual_gp=annual.to_dict(),
                                 equity_grid_start=int(grid[0]), equity_grid_rows=len(grid))


def run(root, output, registration, acknowledged):
    from .mechanical import simulate_mechanical

    output = external_directory(output, acknowledged)
    config = json.loads(registration.read_text())
    repo = Path(__file__).resolve().parents[3]
    dev_path = repo / "ml/runs/phase2-real-v1/run.json"
    dev = json.loads(dev_path.read_text())
    cutoff = dev["holdout_start"]
    if dev["holdout_evaluated"] or dev["status"] != "development_complete":
        raise ValueError("Development boundary must remain sealed")
    start = min(f["start"] for f in dev["folds"])
    if max(f["end"] for f in dev["folds"]) != cutoff:
        raise ValueError("Unexpected evaluation interval")
    provenance = dict(status="running", holdout_read=False, holdout_start=cutoff,
                      registration_sha256=sha256(registration),
                      protocol_sha256=sha256(repo / "docs/strategy-battery-protocol.md"),
                      code_sha256={p.name: sha256(p) for p in [Path(__file__),
                                   Path(__file__).with_name("mechanical.py"),
                                   Path(__file__).with_name("backtest.py")]},
                      development_manifest_sha256=sha256(dev_path), family_size=213,
                      draws=config["draws"], seed=config["seed"], inputs={}, completed=[])
    run_path = output / "run.json"
    saved = json.loads(run_path.read_text()) if run_path.exists() else None
    if saved:
        for key in ("registration_sha256", "protocol_sha256", "code_sha256",
                    "development_manifest_sha256"):
            if saved[key] != provenance[key]:
                raise ValueError(f"Resume provenance changed: {key}")
        provenance = saved
    else:
        atomic_json(run_path, provenance)
    mapping_path = root / "items.parquet"
    mapping = pd.read_parquet(mapping_path, columns=["id", "name", "buy_limit", "high_alch"])
    mapping_hash = sha256(mapping_path)
    if saved and saved.get("mapping_sha256", mapping_hash) != mapping_hash:
        raise ValueError("Metadata changed")
    provenance["mapping_sha256"] = mapping_hash
    exempt_ids = tuple(mapping.loc[mapping.name.isin(EXEMPT_NAMES), "id"].astype(int))
    all_rows = []
    for resolution in (300, 3600, DAY, WEEK):
        name = {300: "intraday_5m", 3600: "intraday_1h", DAY: "daily", WEEK: "weekly"}[resolution]
        directory = root / ("ge-tracker-weekly-v1" if resolution == WEEK else "assembled-v3")
        path = directory / f"{name}.parquet"
        metadata_path = directory / ("run.json" if resolution == WEEK else f"{name}.manifest.json")
        metadata = json.loads(metadata_path.read_text())
        digest = sha256(path)
        if digest != metadata["panel_sha256" if resolution == WEEK else "sha256"]:
            raise ValueError(f"Input checksum mismatch: {name}")
        if saved and saved["inputs"].get(name, digest) != digest:
            raise ValueError("Input changed during resume")
        provenance["inputs"][name] = digest
        if resolution == WEEK:
            if metadata["holdout_read"] or metadata["holdout_start"] != cutoff:
                raise ValueError("Weekly source not sealed")
            frame = sealed_read(path, cutoff, columns="item_id,timestamp,available_at,overallPrice,"
                                "buyingPrice AS avg_high_price,sellingPrice AS avg_low_price,"
                                "buyingCompleted AS high_price_volume,"
                                "sellingCompleted AS low_price_volume")
            frame["buy_limit"] = frame.item_id.map(mapping.set_index("id").buy_limit)
            frame["source_interval_seconds"] = WEEK
            frame["resolution_seconds"] = WEEK
            frame["interval_unknown"] = False
            frame["high_freshness_seconds"] = 300
            frame["low_freshness_seconds"] = 300
            frame["inverted_spread"] = frame.avg_low_price > frame.avg_high_price
            eval_start = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp())
        else:
            frame = sealed_read(path, cutoff, columns="item_id,timestamp,available_at,avg_high_price,"
                                "avg_low_price,high_price_volume,low_price_volume,buy_limit_current "
                                "AS buy_limit,source_interval_seconds,resolution_seconds,"
                                "interval_unknown,high_freshness_seconds,low_freshness_seconds,"
                                "inverted_spread")
            eval_start = start
        eval_frame = frame[frame.available_at >= eval_start].copy()
        print(f"Sealed {name}: context={len(frame)} evaluation={len(eval_frame)} "
              f"items={eval_frame.item_id.nunique()}; holdout NOT read", flush=True)
        ready = len(eval_frame.available_at.unique()) >= 2
        prepared = PreparedObservations(eval_frame) if ready else None
        for spec in (s for s in config["hypotheses"] if s["resolution"] == resolution):
            tax = TaxPolicy(exempt_item_ids=exempt_ids) if spec["rule"] == "low_tax" else DEFAULT_TAX
            mechanical = spec["rule"] in ("alchemy", "processing", "shop")
            if ready and not mechanical:
                scores, allocations, diagnostic = strategy_scores(frame, spec, eval_start, cutoff, tax)
            else:
                scores, allocations, diagnostic = {}, None, None
            for share in config["participation_bps"]:
                key = f"{spec['id']}_p{share:04d}"
                destination = output / key
                summary_path = destination / "summary.json"
                if key in provenance["completed"]:
                    row = json.loads(summary_path.read_text())["row"]
                    all_rows.append(row)
                    continue
                destination.mkdir(exist_ok=True)
                if not ready or spec["rule"] == "shop":
                    reason = "no_pre_holdout_evaluation_buckets" if not ready else "no_shop_stock_or_cost_observations"
                    row = dict(id=spec["id"], rule=spec["rule"], participation_bps=share,
                               horizon_seconds=spec["horizon"], holding_seconds=spec["holding"],
                               resolution_seconds=resolution, universe_items=0, status="unidentified",
                               reason=reason, trades=None, net_gp=None, gross_gp=None, p_raw=1.,
                               p_adjusted=1., survives=False)
                    detail = {}
                else:
                    policy = PortfolioPolicy(holding_seconds=spec["holding"],
                                             allocation_bps=2500 if spec["rule"] == "patient" else 1000,
                                             offer_slots=4 if spec["rule"] == "patient" else 8)
                    assumptions = ExecutionAssumptions(
                        "battery_v1", share, 10, 300, 2 * resolution + 300,
                        buy_timeout_seconds=3 * resolution + 300, allow_unknown_metadata=True,
                        passive_prices=True, fill_model="volume_bounded_v3")
                    if mechanical:
                        result, count = simulate_mechanical(prepared, mapping, spec["rule"], share)
                    else:
                        result = simulate(prepared, scores, assumptions, policy, tax,
                                          allocation_bps=allocations)
                        count = None
                    row, increments, detail = summarize(result, spec, share, eval_frame, completed=count)
                    row["forecast_rank_correlation"] = diagnostic
                    row["signal_count"] = len(scores) if not mechanical else None
                    if spec["rule"] == "vol_size":
                        label = spec["id"].removeprefix("vol_size_")
                        baseline = pd.read_parquet(output / f"xs_reversal_{label}_p{share:04d}" /
                                                   "increments.parquet").increment.to_numpy()
                        if len(baseline) != len(increments):
                            raise ValueError("Unpaired sizing comparison")
                        blocks = [d["block"] for d in detail["inference"]["blocks"]]
                        paired = bootstrap_test(increments - baseline, blocks, completed=row["trades"])
                        row["paired_improvement_gp"] = float((increments - baseline).sum())
                        row["p_raw"] = max(row["p_raw"], paired["p"])
                        row["p_adjusted"] = corrected(row["p_raw"])
                        row["survives"] = bool(row["p_adjusted"] < .05 and
                                               (row["lower_gp"] or 0) > 0 and (paired["lower"] or 0) > 0)
                        detail["paired_improvement"] = paired
                    pd.DataFrame(dict(increment=increments)).to_parquet(destination / "increments.parquet")
                    for name, records in [("fills", result.fills), ("orders", result.orders),
                                          ("equity", result.equity)]:
                        pd.DataFrame(records).to_parquet(destination / f"{name}.parquet", index=False)
                    atomic_json(destination / "metrics.json", result.metrics)
                atomic_json(summary_path, dict(row=row, detail=detail))
                provenance["completed"].append(key)
                atomic_json(run_path, provenance)
                all_rows.append(row)
                pd.DataFrame(all_rows).to_csv(output / "results.csv", index=False)
                print(f"{key}: {row['status']} trades={row['trades']} net={row['net_gp']} "
                      f"p={row['p_raw']:.6g} adj={row['p_adjusted']:.6g}", flush=True)
        del frame, eval_frame, prepared
        gc.collect()
    results = pd.DataFrame(all_rows)
    results.to_csv(output / "results.csv", index=False)
    if len(results) != config["family_size"] or len(provenance["completed"]) != config["family_size"]:
        raise AssertionError("Incomplete hypothesis family")
    provenance.update(status="complete", results_sha256=sha256(output / "results.csv"))
    atomic_json(run_path, provenance)
    print(f"COMPLETE {len(results)} tests; corrected survivors={int(results.survives.sum())}; "
          "holdout NOT read", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registration", type=Path,
                        default=Path(__file__).resolve().parents[2] / "strategy-battery-v1.json")
    parser.add_argument("--acknowledge-private-research", action="store_true")
    args = parser.parse_args()
    run(Path(os.environ["OSRS_DATA_DIR"]), args.output, args.registration,
        args.acknowledge_private_research)


if __name__ == "__main__":
    main()
