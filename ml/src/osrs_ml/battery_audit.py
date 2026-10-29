"""Independent accounting/capacity audit of the frozen strategy battery."""

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import compatible_volume
from .battery import CAPITAL, DAY, WEEK, corrected, sealed_read
from .costs import TaxPolicy, integer_lots, price_target, sale_proceeds
from .data import sha256


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def verify_provenance(output, registration, protocol, code_dir, development):
    """Refuse drift or partial families before opening any market observations."""
    manifest = json.loads((output / "run.json").read_text())
    config = json.loads(registration.read_text())
    check(manifest["status"] == "complete" and not manifest["holdout_read"],
          "Incomplete/unsealed run")
    check(manifest["registration_sha256"] == sha256(registration), "Registration changed")
    check(manifest["protocol_sha256"] == sha256(protocol), "Protocol changed")
    check(manifest["development_manifest_sha256"] == sha256(development),
          "Development manifest changed")
    dev = json.loads(development.read_text())
    check(not dev["holdout_evaluated"] and dev["status"] == "development_complete" and
          dev["holdout_start"] == manifest["holdout_start"], "Development boundary changed")
    for name, digest in manifest["code_sha256"].items():
        check(sha256(code_dir / name) == digest, f"Executed code changed: {name}")
    check(manifest["results_sha256"] == sha256(output / "results.csv"), "Results changed")
    expected = {f"{s['id']}_p{p:04d}" for s in config["hypotheses"]
                for p in config["participation_bps"]}
    check(len(expected) == config["family_size"] == manifest["family_size"] == 213,
          "Changed family size")
    check(set(manifest["completed"]) == expected and len(manifest["completed"]) == len(expected),
          "Incomplete/duplicated family")
    results = pd.read_csv(output / "results.csv")
    keys = [f"{r.id}_p{r.participation_bps:04d}" for r in results.itertuples()]
    check(len(keys) == len(expected) and set(keys) == expected, "Results family mismatch")
    return manifest, config, expected, results.set_index(["id", "participation_bps"])


def audit(output, root):
    repo = Path(__file__).resolve().parents[3]
    manifest, config, expected, results = verify_provenance(
        output, repo / "ml/strategy-battery-v1.json", repo / "docs/strategy-battery-protocol.md",
        Path(__file__).parent, repo / "ml/runs/phase2-real-v1/run.json")
    specs = {s["id"]: s for s in config["hypotheses"]}
    check(sha256(root / "items.parquet") == manifest["mapping_sha256"], "Metadata changed")
    mapping = pd.read_parquet(root / "items.parquet", columns=["id", "buy_limit", "high_alch"])
    limits = mapping.set_index("id").buy_limit.to_dict()
    alch = mapping.set_index("id").high_alch.to_dict()
    cutoff = manifest["holdout_start"]
    source = {}
    counts = dict(scenarios=0, unavailable=0, fills=0, productions=0, negative_cash=0,
                  capacity_violations=0, holdout_rows=0)
    for key in sorted(expected):
        directory = output / key
        saved = json.loads((directory / "summary.json").read_text())
        row, spec = saved["row"], specs[saved["row"]["id"]]
        csv_row = results.loc[(row["id"], row["participation_bps"])]
        for field in ("net_gp", "p_raw", "p_adjusted", "trades", "survives", "status"):
            a, b = row[field], csv_row[field]
            check((a is None and pd.isna(b)) or a == b or
                  (isinstance(a, float) and np.isclose(a, b, rtol=1e-14, atol=0)),
                  f"Summary/CSV mismatch {key}: {field}")
        counts["scenarios"] += 1
        check(row["p_adjusted"] == corrected(row["p_raw"]), f"Correction mismatch {key}")
        check(row["survives"] == (row["p_adjusted"] < .05 and (row.get("lower_gp") or 0) > 0 and
                                 (spec["rule"] != "vol_size" or
                                  (saved["detail"]["paired_improvement"]["lower"] or 0) > 0)),
              f"Survival mismatch {key}")
        if row["status"] == "unidentified":
            check(row["p_raw"] == 1 and row["net_gp"] is None, "Unavailable profit claim")
            counts["unavailable"] += 1
            continue
        resolution = spec["resolution"]
        if resolution not in source:
            if resolution == WEEK:
                path = root / "ge-tracker-weekly-v1/weekly.parquet"
                columns = ("item_id,timestamp,available_at,buyingPrice AS avg_high_price,"
                           "sellingPrice AS avg_low_price,buyingCompleted AS high_price_volume,"
                           "sellingCompleted AS low_price_volume")
                name = "weekly"
            else:
                name = {300: "intraday_5m", 3600: "intraday_1h", DAY: "daily"}[resolution]
                path = root / f"assembled-v3/{name}.parquet"
                columns = ("item_id,timestamp,available_at,avg_high_price,avg_low_price,"
                           "high_price_volume,low_price_volume")
            check(sha256(path) == manifest["inputs"][name], "Source changed")
            source[resolution] = sealed_read(path, cutoff, columns=columns).set_index(
                ["item_id", "available_at"])
        lookup = source[resolution]
        m = json.loads((directory / "metrics.json").read_text())
        curve = pd.read_parquet(directory / "equity.parquet")
        fills = pd.read_parquet(directory / "fills.parquet")
        orders = pd.read_parquet(directory / "orders.parquet")
        check((curve.timestamp < cutoff).all(), f"Sealed equity {key}")
        check((curve.cash_gp >= 0).all(), f"Negative cash {key}")
        check((curve.active_slots <= (4 if spec["rule"] == "patient" else 8)).all(), "Slot excess")
        check(curve.equity_gp.iloc[-1] - CAPITAL == m["net_gp"] == row["net_gp"], "Equity mismatch")
        increments = pd.read_parquet(directory / "increments.parquet").increment
        check(increments.sum() == row["net_gp"], "Increment mismatch")
        mech = spec["rule"] in ("alchemy", "processing")
        tax = TaxPolicy(**m["tax"]) if not mech else TaxPolicy()
        if not fills.empty:
            for _, part in fills.groupby("opportunity_id", sort=False):
                first = part.iloc[0]
                item, now, submitted = int(first.item_id), int(first.timestamp), int(first.submitted)
                buy = first.side == "buy"
                side = ("high" if buy else "low") if mech else ("low" if buy else "high")
                if mech:
                    reference = int(lookup.loc[(item, now), f"avg_{side}_price"])
                else:
                    history = lookup.loc[item]
                    prior = history[history.index <= submitted]
                    check(not prior.empty, "Missing causal submission price")
                    reference = int(prior.iloc[-1][f"avg_{side}_price"])
                check((part.reference_price_gp == reference).all(), "Source reference mismatch")
                target = price_target(reference, 10, buy=buy)
                lots = integer_lots(target, int(part.quantity.sum()), buy=buy)
                check(list(zip(part.price_gp, part.quantity, strict=True)) == lots,
                      "Slippage/lot allocation mismatch")
                if not mech:
                    threshold = target // 10000 if buy else (target + 9999) // 10000
                    check((part.qualification_price_gp == threshold).all(),
                          "Frozen qualification price mismatch")
                if buy:
                    src = lookup.loc[(item, now)]
                    check(int(src.timestamp) + resolution <= submitted + 3 * resolution + 300,
                          "Buy bucket exceeds timeout")
                    if mech:
                        history = lookup.loc[item]
                        decision = history[history.index <= submitted].iloc[-1]
                        ceiling_target = price_target(int(decision.avg_high_price), 10, buy=True)
                        check(part.price_gp.max() <= (ceiling_target + 9999) // 10000,
                              "Mechanical frozen ceiling exceeded")
        productions = [] if orders.empty else orders[orders.event == "production"].to_dict("records")
        counts["productions"] += len(productions)
        fixed = m.get("fixed_cost_gp", 0)
        cash = CAPITAL - fixed
        stock, book, windows = {}, {}, {}
        events = [(int(f["timestamp"]), 1, f) for f in fills.to_dict("records")]
        events += [(int(p["timestamp"]), 0, p) for p in productions]
        for now, kind, event in sorted(events, key=lambda e: (e[0], e[1])):
            item, q = int(event["item_id"]), int(event["quantity"])
            check(q > 0 and now < cutoff, "Nonpositive/sealed event")
            if kind == 0:
                inputs = (item, 561) if spec["rule"] == "alchemy" else {
                    859: (70, 1777), 855: (66, 1777)}[item]
                cost = 0
                for ingredient in inputs:
                    check(stock.get(ingredient, 0) >= q, "Consumed unowned input")
                    allocated = book[ingredient] * q // stock[ingredient]
                    cost += allocated
                    book[ingredient] -= allocated
                    stock[ingredient] -= q
                check(cost == event["input_cost_gp"], "Conversion cost mismatch")
                if spec["rule"] == "alchemy":
                    check(event["coins_gp"] == alch[item] * q, "Alchemy coins mismatch")
                    check(q <= 916, "Alchemy active time exceeded")
                    cash += int(event["coins_gp"])
                else:
                    stock[item] = stock.get(item, 0) + q
                    book[item] = book.get(item, 0) + cost
                    check(q <= 1650, "Processing active time exceeded")
                continue
            counts["fills"] += 1
            check(int(event["price_gp"]) >= 1, "Illegal fill price")
            check(now > int(event["submitted"]) + 300, "Fill latency")
            src = lookup.loc[(item, now)]
            check(int(src.timestamp) >= int(event["submitted"]) + 300, "Incompatible bucket start")
            buy = event["side"] == "buy"
            side = ("high" if buy else "low") if mech else ("low" if buy else "high")
            volume = int(src[f"{side}_price_volume"])
            mean = int(src[f"avg_{side}_price"])
            check(volume == int(event["bucket_volume"]), "Source volume mismatch")
            if not mech:
                threshold = int(event["qualification_price_gp"])
                qualifying = compatible_volume(volume, mean, threshold, buy=buy, rule="mean_proxy")
                check(qualifying == event["compatible_volume_upper_or_proxy"], "Qualification mismatch")
            price, delta = int(event["price_gp"]), int(event["cash_delta_gp"])
            check(delta == (-price*q if buy else sale_proceeds(price, q, tax, item)), "Fill cash/tax")
            cash += delta
            if buy:
                window = windows.get(item)
                if window is None or now >= window[0] + 14400:
                    window = (now, 0)
                windows[item] = (window[0], window[1] + q)
                check(windows[item][1] <= limits.get(item, 0), "Buy limit exceeded")
                stock[item] = stock.get(item, 0) + q
                book[item] = book.get(item, 0) + price*q
            else:
                check(stock.get(item, 0) >= q, "Unowned sale")
                cost = book[item] * q // stock[item]
                stock[item] -= q
                book[item] -= cost
        check(cash == curve.cash_gp.iloc[-1], f"Final cash mismatch {key}")
        check(sum(stock.values()) == m["end_inventory_units"], f"Inventory mismatch {key}")
        if not fills.empty:
            for (item, now, side), part in fills.groupby(["item_id", "timestamp", "side"]):
                src = lookup.loc[(item, now)]
                volume_side = ("high" if side == "buy" else "low") if mech else (
                    "low" if side == "buy" else "high")
                volume = int(src[f"{volume_side}_price_volume"])
                check(part.quantity.sum() <= volume * row["participation_bps"] // 10000,
                      "Bucket participation exceeded")
        # Rebuild the final conservative mark from original sealed observations.
        mark = 0
        for item, q in stock.items():
            if not q:
                continue
            item_rows = lookup.loc[item]
            latest = item_rows[item_rows.index <= curve.timestamp.iloc[-1]].iloc[-1]
            low = latest.avg_low_price
            if pd.isna(low):
                continue
            target = price_target(int(low), 10, buy=False) * 9900
            lots = integer_lots(target, int(q), buy=False, denominator=100_000_000)
            mark += sum(sale_proceeds(p, n, tax, int(item)) for p, n in lots)
        check(mark == curve.inventory_mark_gp.iloc[-1], f"Final mark mismatch {key}")
        if mech and productions:
            dates = [int(p["timestamp"]) // DAY for p in productions]
            check(len(dates) == len(set(dates)), "Multiple active sessions per day")
            check(m["active_hours"] <= len(dates) + 1e-9, "Active hour budget")
    check(counts["scenarios"] == 213, "Missing tests")
    check(np.isfinite(counts["fills"]), "Bad audit count")
    print(json.dumps(dict(status="passed", **counts, holdout_read=False), indent=2))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    audit(args.output, Path(os.environ["OSRS_DATA_DIR"]))


if __name__ == "__main__":
    main()
