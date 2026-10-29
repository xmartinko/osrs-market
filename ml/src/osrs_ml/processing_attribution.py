"""Descriptive batch attribution of the frozen processing accounts; no new tests of profit."""

import argparse
import json
import math
import os
from pathlib import Path

import duckdb
import pandas as pd

from .battery import CAPITAL, DAY
from .battery_audit import check, verify_provenance
from .costs import integer_lots, price_target, sale_proceeds
from .data import sha256
from .diagnostics import atomic_json
from .weekly_ingest import external_directory

RECIPES = {859: (70, 1777), 855: (66, 1777)}
ITEMS = (66, 70, 855, 859, 1777)
ARTIFACTS = ("fills.parquet", "orders.parquet", "equity.parquet", "metrics.json", "summary.json")


def read_development(path, start, cutoff):
    """Filter items and availability inside DuckDB, before market materialization."""
    check(0 <= start < cutoff, "Invalid development boundary")
    with duckdb.connect() as db:
        return db.execute(
            "SELECT item_id,timestamp,available_at,avg_high_price,avg_low_price,"
            "high_price_volume,low_price_volume FROM read_parquet(?) "
            "WHERE available_at >= ? AND available_at < ? "
            "AND item_id IN (66,70,855,859,1777) ORDER BY available_at,item_id",
            [str(path), int(start), int(cutoff)],
        ).fetchdf()


def verify_artifacts(source, shares):
    known = json.loads((source / "audited-artifacts-sha256.json").read_text())
    hashes = {}
    for share in shares:
        for name in ARTIFACTS:
            key = f"processing_1d_p{share:04d}/{name}"
            hashes[key] = sha256(source / key)
            check(hashes[key] == known.get(key), f"Artifact changed: {key}")
    return hashes


def terminal_mark(reference, quantity, item):
    target = price_target(reference, 10, buy=False) * 9900
    return sum(sale_proceeds(p, n, item_id=item) for p, n in
               integer_lots(target, quantity, buy=False, denominator=100_000_000))


def attribute(fills, orders, curve, observations, metrics, share, cutoff):
    """Rebuild weighted books by whole opportunities, preserving rounded-lot accounting."""
    check(not curve.empty and not observations.empty, "Missing account/source")
    for table, field in [(fills, "timestamp"), (orders, "timestamp"),
                         (curve, "timestamp"), (observations, "available_at")]:
        check((table[field] < cutoff).all(), "Sealed event/observation")
    check(not observations.duplicated(["item_id", "available_at"]).any(), "Duplicate source")
    check(not fills.duplicated(["opportunity_id", "price_gp"]).any(), "Duplicate fill lot")
    check(not orders.duplicated(["timestamp", "event", "item_id"]).any(), "Duplicate order")
    check(not curve.timestamp.duplicated().any() and curve.timestamp.is_monotonic_increasing,
          "Duplicate/unordered equity")
    lookup = {(int(r.item_id), int(r.available_at)): r for r in observations.itertuples()}
    source_by_time = {int(t): part for t, part in observations.groupby("available_at")}
    submitted = orders[orders.event.eq("batch_submitted")].sort_values("timestamp")
    submissions, submission_by_time = [], {}
    for r in submitted.itertuples():
        now, item = int(r.timestamp), int(r.item_id)
        check(item in RECIPES and tuple(r.inputs) == RECIPES[item], "Recipe changed")
        ceilings = []
        for ingredient in RECIPES[item]:
            check((ingredient, now) in lookup, "Missing causal input price")
            price = int(lookup[ingredient, now].avg_high_price)
            ceilings.append((price_target(price, 10, buy=True) + 9999) // 10000)
        check((item, now) in lookup, "Missing causal output price")
        output = price_target(int(lookup[item, now].avg_low_price), 10, buy=False) // 10000
        entry = dict(submitted_at=now, item_id=item, requested_units=int(r.quantity),
                     decision_input_ceiling_gp=sum(ceilings),
                     decision_net_output_gp=sale_proceeds(output, 1, item_id=item),
                     bought_units=0, spent_gp=0, produced_units=0, expired=False)
        check(now not in submission_by_time, "Multiple same-time submissions")
        submissions.append(entry)
        submission_by_time[now] = entry

    # Events share the account's production-before-fills order. All lot rows of one
    # exchange consume cost once, exactly as mechanical.exchange does.
    events = {}
    for r in orders[orders.event.eq("production")].to_dict("records"):
        events.setdefault(int(r["timestamp"]), []).append((0, r))
    for _, part in fills.groupby("opportunity_id", sort=False):
        check(part.reference_price_gp.nunique() == 1, "Source reference mismatch")
        check(all(part[c].nunique() == 1 for c in
                  ("timestamp", "submitted", "item_id", "side")),
              "Mixed opportunity")
        events.setdefault(int(part.timestamp.iloc[0]), []).append((1, part))
    for r in orders[orders.event.eq("buy_expired")].to_dict("records"):
        prior = [s for s in submissions if s["submitted_at"] < int(r["timestamp"])]
        check(bool(prior), "Expiry without submission")
        check(prior[-1]["item_id"] == int(r["item_id"]), "Expiry item mismatch")
        prior[-1]["expired"] = True
    check(set(events).issubset(set(curve.timestamp)), "Off-grid event")

    cash, stock, book, last_buy, latest = CAPITAL, {}, {}, {}, {}
    batches, batch_by_output_time = [], {}

    def consume(item, q):
        check(stock.get(item, 0) >= q > 0, "Unowned input/output")
        cost = book[item] * q // stock[item]
        stock[item] -= q
        book[item] -= cost
        return cost

    for point in curve.itertuples():
        now = int(point.timestamp)
        for r in source_by_time.get(now, pd.DataFrame()).itertuples():
            latest[int(r.item_id)] = r
        for kind, event in sorted(events.get(now, []), key=lambda e: e[0]):
            if kind == 0:
                item, q = int(event["item_id"]), int(event["quantity"])
                check(0 < q <= 1650, "Production quantity")
                prior = [s for s in submissions if s["submitted_at"] < now]
                check(bool(prior), "Production without submission")
                submission = prior[-1]
                check(submission["item_id"] == item and not submission["produced_units"],
                      "Production/submission mismatch")
                check(all(stock.get(i, 0) >= q for i in RECIPES[item]), "Unowned input")
                check(all(last_buy.get(i, now) < now for i in RECIPES[item]), "Input timing")
                check(stock.get(item, 0) == 0, "Overlapping output batches")
                cost = sum(consume(i, q) for i in RECIPES[item])
                check(cost == int(event["input_cost_gp"]), "Production input cost")
                check(int(event["coins_gp"]) == 0, "Unexpected production coins")
                stock[item], book[item] = q, cost
                submission["produced_units"] = q
                batch = dict(batch=len(batches) + 1, item_id=item, produced_at=now,
                             submitted_at=submission["submitted_at"], produced_units=q,
                             input_cost_gp=cost, sold_units=0, sold_cost_gp=0,
                             net_proceeds_gp=0, tax_gp=0, first_sale_at=None, last_sale_at=None,
                             active_hours=q / 1800 + 5 / 60,
                             decision_input_ceiling_gp=submission["decision_input_ceiling_gp"],
                             decision_net_output_gp=submission["decision_net_output_gp"])
                batches.append(batch)
                batch_by_output_time[item, now] = batch
            else:
                part = event
                r = part.iloc[0]
                item, q, submitted_at = int(r.item_id), int(part.quantity.sum()), int(r.submitted)
                buy = r.side == "buy"
                check(r.side in ("buy", "sell"), "Unknown fill side")
                src = lookup.get((item, now))
                check(src is not None, "Missing fill source")
                reference = int(src.avg_high_price if buy else src.avg_low_price)
                check((part.reference_price_gp == reference).all(), "Source reference mismatch")
                lots = integer_lots(price_target(reference, 10, buy=buy), q, buy=buy)
                check(list(zip(part.price_gp, part.quantity, strict=True)) == lots, "Fill lots")
                check(int(src.timestamp) >= submitted_at + 300, "Fill bucket timing")
                check((part.bucket_start == int(src.timestamp)).all() and
                      (part.bucket_end == int(src.timestamp) + DAY).all(), "Fill bucket provenance")
                volume = int(src.high_price_volume if buy else src.low_price_volume)
                used = fills[(fills.item_id == item) & (fills.timestamp == now) &
                             (fills.side == r.side)].quantity.sum()
                check(used <= volume * share // 10000, "Participation exceeded")
                for lot in part.itertuples():
                    price, n = int(lot.price_gp), int(lot.quantity)
                    delta = -price*n if buy else sale_proceeds(price, n, item_id=item)
                    check(delta == int(lot.cash_delta_gp), "Fill cash")
                    check(int(lot.tax_gp) == (0 if buy else price*n - delta), "Fill tax")
                delta = int(part.cash_delta_gp.sum())
                cash += delta
                if buy:
                    check(submitted_at in submission_by_time, "Purchase without submission")
                    submission = submission_by_time[submitted_at]
                    check(item in RECIPES[submission["item_id"]], "Wrong input leg")
                    stock[item] = stock.get(item, 0) + q
                    book[item] = book.get(item, 0) - delta
                    last_buy[item] = now
                    submission["bought_units"] += q
                    submission["spent_gp"] -= delta
                else:
                    batch = batch_by_output_time.get((item, submitted_at))
                    check(batch is not None and now > submitted_at, "Sale without earlier production")
                    cost = consume(item, q)
                    batch["sold_units"] += q
                    batch["sold_cost_gp"] += cost
                    batch["net_proceeds_gp"] += delta
                    batch["tax_gp"] += int(part.tax_gp.sum())
                    batch["first_sale_at"] = batch["first_sale_at"] or now
                    batch["last_sale_at"] = now
        mark = sum(terminal_mark(int(latest[i].avg_low_price), int(q), i)
                   for i, q in stock.items()
                   if q and i in latest and pd.notna(latest[i].avg_low_price))
        check(cash == int(point.cash_gp), f"Cash path mismatch at {now}")
        check(mark == int(point.inventory_mark_gp), f"Mark path mismatch at {now}")
        check(cash + mark == int(point.equity_gp), f"Equity path mismatch at {now}")

    for b in batches:
        q = b["sold_units"]
        b["realized_gp"] = b["net_proceeds_gp"] - b["sold_cost_gp"]
        b["decision_spread_gp"] = q * (b["decision_net_output_gp"] - b["decision_input_ceiling_gp"])
        b["input_movement_gp"] = q * b["decision_input_ceiling_gp"] - b["sold_cost_gp"]
        b["output_movement_gp"] = b["net_proceeds_gp"] - q * b["decision_net_output_gp"]
        check(b["realized_gp"] == b["decision_spread_gp"] + b["input_movement_gp"] +
              b["output_movement_gp"], "Attribution identity")
        b["fully_sold"] = b["sold_units"] == b["produced_units"]
        b["production_wait_hours"] = (b["produced_at"] - b["submitted_at"]) / 3600
        b["sale_wait_hours"] = ((b["last_sale_at"] - b["produced_at"]) / 3600
                                if b["last_sale_at"] is not None else None)
    inventory = []
    for item, q in sorted(stock.items()):
        if not q:
            continue
        r = latest.get(item)
        mark = (terminal_mark(int(r.avg_low_price), int(q), item)
                if r is not None and pd.notna(r.avg_low_price) else 0)
        inventory.append(dict(item_id=item, kind="output" if item in RECIPES else "input",
                              units=q, book_gp=book[item], mark_gp=mark,
                              unrealized_gp=mark - book[item],
                              source_age_seconds=(now - int(r.available_at)) if r else None))
    active_hours = sum(b["active_hours"] for b in batches)
    realized = sum(b["realized_gp"] for b in batches)
    remaining_book = sum(book.values())
    mark = sum(i["mark_gp"] for i in inventory)
    summary = dict(participation_bps=share, submitted_batches=len(submissions),
                   unproduced_submissions=sum(not s["produced_units"] for s in submissions),
                   expired_submissions=sum(s["expired"] for s in submissions),
                   produced_batches=len(batches), fully_sold_batches=sum(b["fully_sold"] for b in batches),
                   produced_units=sum(b["produced_units"] for b in batches),
                   sold_units=sum(b["sold_units"] for b in batches),
                   profitable_batches=sum(b["realized_gp"] > 0 for b in batches),
                   losing_batches=sum(b["realized_gp"] < 0 for b in batches),
                   net_proceeds_gp=sum(b["net_proceeds_gp"] for b in batches),
                   tax_gp=sum(b["tax_gp"] for b in batches),
                   realized_gp=realized, remaining_book_gp=remaining_book, terminal_mark_gp=mark,
                   unrealized_gp=mark - remaining_book, cash_pnl_gp=cash - CAPITAL,
                   net_gp=cash + mark - CAPITAL, active_hours=active_hours,
                   elapsed_hours=(int(curve.timestamp.iloc[-1])-int(curve.timestamp.iloc[0])) / 3600,
                   realized_gp_per_active_hour=realized / active_hours if active_hours else None,
                   largest_batch_realized_gp=max((b["realized_gp"] for b in batches), default=0),
                   curve_rows_checked=len(curve))
    for field in ("decision_spread_gp", "input_movement_gp", "output_movement_gp"):
        summary[field] = sum(b[field] for b in batches)
    check(summary["cash_pnl_gp"] == realized - remaining_book, "Cash/book identity")
    check(summary["net_gp"] == realized + summary["unrealized_gp"], "Net/book identity")
    for field in ("realized_gp", "cash_pnl_gp", "net_gp", "produced_units", "elapsed_hours"):
        check(summary[field] == metrics[field], f"Saved metric mismatch: {field}")
    check(mark == metrics["end_inventory_mark_gp"], "Saved terminal mark")
    check(sum(stock.values()) == metrics["end_inventory_units"], "Saved inventory units")
    check(math.isclose(active_hours, metrics["active_hours"]), "Saved active hours")
    return summary, batches, submissions, inventory


def run(root, source, output, acknowledged):
    repo = Path(__file__).resolve().parents[3]
    output = Path(output).resolve()
    check(not output.exists(), "Refuse output overwrite")
    manifest, config, _, _ = verify_provenance(
        source, repo / "ml/strategy-battery-v1.json", repo / "docs/strategy-battery-protocol.md",
        Path(__file__).parent, repo / "ml/runs/phase2-real-v1/run.json")
    shares = config["participation_bps"]
    hashes = verify_artifacts(source, shares)
    daily = root / "assembled-v3/daily.parquet"
    check(sha256(daily) == manifest["inputs"]["daily"], "Daily source changed")
    cutoff = manifest["holdout_start"]
    development = json.loads((repo / "ml/runs/phase2-real-v1/run.json").read_text())
    start = min(f["start"] for f in development["folds"])
    check(start == 1777766700 and cutoff == 1785024300, "Development boundary changed")
    output = external_directory(output, acknowledged)
    provenance = dict(status="running", holdout_read=False, holdout_start=cutoff, start=start,
                      source_run_sha256=sha256(source / "run.json"), input_artifacts_sha256=hashes,
                      source_daily_sha256=sha256(daily), code_sha256=sha256(Path(__file__)),
                      attribution_protocol_sha256=sha256(repo / "docs/processing-attribution-protocol.md"),
                      completed=[])
    atomic_json(output / "run.json", provenance)
    observations = read_development(daily, start, cutoff)
    summaries = []
    for share in shares:
        directory = source / f"processing_1d_p{share:04d}"
        summary, batches, submissions, inventory = attribute(
            pd.read_parquet(directory / "fills.parquet"),
            pd.read_parquet(directory / "orders.parquet"),
            pd.read_parquet(directory / "equity.parquet"), observations,
            json.loads((directory / "metrics.json").read_text()), share, cutoff)
        original = json.loads((directory / "summary.json").read_text())["row"]
        check(summary["fully_sold_batches"] == original["trades"], "Completed batch mismatch")
        summary.update(p_raw=original["p_raw"], p_adjusted=original["p_adjusted"],
                       status=original["status"], survives=original["survives"])
        for name, records in [("batches", batches), ("submissions", submissions),
                              ("inventory", inventory)]:
            pd.DataFrame(records).to_csv(output / f"{name}-p{share:04d}.csv", index=False)
        summaries.append(summary)
        pd.DataFrame(summaries).to_csv(output / "summary.csv", index=False)
        provenance["completed"].append(share)
        atomic_json(output / "run.json", provenance)
        print(json.dumps(summary), flush=True)
    provenance.update(status="complete", source_rows=len(observations),
                      artifacts_sha256={p.name: sha256(p) for p in sorted(output.glob("*.csv"))})
    atomic_json(output / "run.json", provenance)
    print("PASS: 3 unchanged processing accounts attributed; original inference retained; "
          "holdout NOT read", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-private-research", action="store_true")
    args = parser.parse_args()
    run(Path(os.environ["OSRS_DATA_DIR"]), args.source, args.output, args.acknowledge_private_research)


if __name__ == "__main__":
    main()
