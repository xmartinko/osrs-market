"""Offline actual-event processing calibration. No market reader, trading or profit inference."""

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .data import sha256
from .weekly_ingest import external_directory

DAY = 86400
CAPITAL = 10_000_000
RECIPES = {859: (70, 1777), 855: (66, 1777)}
PROTOCOL = Path(__file__).resolve().parents[3] / "docs/processing-own-fill-protocol.md"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, f"{name}: integer >= {minimum} required")
    return value


def identity(value):
    require(isinstance(value, str) and bool(value.strip()), "Nonempty identifier required")
    return value


def shape(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value) <= set(required) | set(optional),
            f"Unexpected/missing fields: expected {required}")


def mapping(value, keys=None, minimum=0):
    require(isinstance(value, dict), "Item mapping required")
    require(all(isinstance(k, str) and k.isdecimal() and str(int(k)) == k for k in value),
            "Canonical string item IDs required")
    require(keys is None or set(value) == {str(i) for i in keys}, "Recipe item mapping mismatch")
    for q in value.values():
        integer(q, "Item amount", minimum)
    return {int(i): q for i, q in value.items()}


def initialize(path, *, now=None):
    now = int(time.time()) if now is None else integer(now, "now")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the filename exclusively before SQLite can open it.
    with path.open("xb"):
        pass
    start = (now // DAY + 1) * DAY
    manifest = dict(version=1, enrolled_at=now, start=start, end=start + 56 * DAY,
                    capital_gp=CAPITAL, recipes={str(i): list(v) for i, v in RECIPES.items()},
                    protocol_sha256=sha256(PROTOCOL), code_sha256=sha256(Path(__file__)),
                    study_kind="actual_fill_calibration_descriptive_only", holdout_read=False)
    with sqlite3.connect(path) as db:
        db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE manifest (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
            CREATE TABLE events (seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
                at INTEGER NOT NULL, ingested_at INTEGER NOT NULL, payload TEXT NOT NULL,
                chain_sha256 TEXT NOT NULL);
        """)
        db.execute("INSERT INTO manifest VALUES (1,?)", [canonical(manifest)])
        for table in ("manifest", "events"):
            for action in ("update", "delete"):
                db.execute(f"CREATE TRIGGER {table}_no_{action} BEFORE {action} ON {table} "
                           "BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END")
    return manifest


def connect(path, *, write=False):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    db = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True)
    db.row_factory = sqlite3.Row
    if write:
        db.execute("PRAGMA synchronous=FULL")
    return db


def evidence_check(event, path):
    relative = Path(event["evidence"])
    evidence = (path.parent / relative).resolve()
    require(not relative.is_absolute() and evidence.is_relative_to(path.parent.resolve()) and
            evidence.is_file() and evidence != path.resolve() and
            evidence.name not in {path.name + suffix for suffix in ("-wal", "-shm", "-journal")},
            "Evidence must be an existing file inside study, separate from ledger")
    expected = event["evidence_sha256"]
    require(isinstance(expected, str) and sha256(evidence) == expected, "Evidence hash mismatch")


def load(db):
    manifest = json.loads(db.execute("SELECT payload FROM manifest WHERE id=1").fetchone()[0])
    require(manifest["code_sha256"] == sha256(Path(__file__)), "Changed implementation hash")
    require(manifest["protocol_sha256"] == sha256(PROTOCOL), "Changed protocol hash")
    require(manifest["version"] == 1 and manifest["capital_gp"] == CAPITAL and
            manifest["recipes"] == {str(i): list(v) for i, v in RECIPES.items()} and
            manifest["start"] == (manifest["enrolled_at"] // DAY + 1) * DAY and
            manifest["end"] == manifest["start"] + 56 * DAY, "Changed study envelope")
    chain = hashlib.sha256(canonical(manifest).encode()).hexdigest()
    events, ingestion = [], {}
    last_ingested = manifest["enrolled_at"]
    for seq, row in enumerate(db.execute("SELECT * FROM events ORDER BY seq"), start=1):
        event = json.loads(row["payload"])
        chain = hashlib.sha256((chain + canonical(event) + str(row["ingested_at"])).encode()).hexdigest()
        require(row["seq"] == seq and row["chain_sha256"] == chain and
                row["id"] == event["id"] and row["at"] == event["at"], "Event chain mismatch")
        require(last_ingested <= row["ingested_at"] and event["at"] <= row["ingested_at"],
                "Invalid ingestion timestamp")
        last_ingested = row["ingested_at"]
        events.append(event)
        ingestion[event["id"]] = row["ingested_at"]
    return manifest, events, chain, last_ingested, ingestion


def replay(manifest, events, path, now, ingestion):
    cash, realized, tax, capital_time, peak_book, peak_slots = CAPITAL, 0, 0, 0, 0, 0
    stock, book, last_buy, windows = {}, {}, {}, {}
    batches, orders, decisions, sessions, production_days = {}, {}, {}, {}, {}
    deviations, ids, interaction_days = [], set(), set()
    counts = {k: 0 for k in ("submissions", "rejections", "cancellations", "buy_fills",
                             "sell_fills", "buy_units", "sell_units", "produced_units")}
    previous = manifest["start"]
    until = min(now, manifest["end"])

    def deviation(event, reason):
        deviations.append(dict(event_id=event["id"], reason=reason))

    def consume(item, q):
        require(stock.get(item, 0) >= q, "Unowned inventory")
        cost = book[item] * q // stock[item]
        stock[item] -= q
        book[item] -= cost
        return cost

    def live():
        return [o for o in orders.values() if o["status"] == "open"]

    for event in events:
        shape(event, ("id", "kind", "at", "source", "evidence", "evidence_sha256", "data"))
        identity(event["id"])
        require(event["id"] not in ids, "Duplicate event ID")
        ids.add(event["id"])
        require(event["source"] == "operator_actual", "Only operator_actual records accepted")
        at = integer(event["at"], "at")
        require(manifest["start"] <= at < manifest["end"], "Event outside enrolled window")
        require(at <= now, "Future event")
        require(at >= previous, "Events must be chronological")
        evidence_check(event, path)
        capital_time += sum(book.values()) * (at - previous)
        previous = at
        day, data, kind = at // DAY, event["data"], event["kind"]
        require(day not in sessions, "Event after daily session checkpoint")
        if kind not in ("decision", "session"):
            interaction_days.add(day)
        if kind == "decision":
            shape(data, ("batch_id", "output_id", "quantity", "input_ceilings", "buy_limits",
                         "output_reference_gp"), ("reason",))
            batch_id = identity(data["batch_id"])
            require(batch_id not in batches and day not in decisions, "Duplicate batch/daily decision")
            output = integer(data["output_id"], "output_id", 1)
            require(output in RECIPES, "Unregistered recipe")
            q = integer(data["quantity"], "quantity")
            if q:
                ceilings = mapping(data["input_ceilings"], RECIPES[output], 1)
                limits = mapping(data["buy_limits"], RECIPES[output])
                integer(data["output_reference_gp"], "output_reference_gp", 1)
                if q * sum(ceilings.values()) > 1_000_000:
                    deviation(event, "batch_budget")
                if q > 1650:
                    deviation(event, "production_rate")
                if live() or any(b["produced"] > b["sold"] for b in batches.values()):
                    deviation(event, "overlapping_batches")
            else:
                identity(data.get("reason"))
                ceilings = mapping(data["input_ceilings"])
                limits = mapping(data["buy_limits"])
                integer(data["output_reference_gp"], "output_reference_gp")
            batches[batch_id] = dict(output=output, planned=q, ceilings=ceilings, limits=limits,
                                     produced=0, sold=0, bought_gp=0, at=at,
                                     decision_id=event["id"])
            decisions[day] = batch_id
        elif kind == "submit":
            shape(data, ("order_id", "batch_id", "item_id", "side", "quantity", "price_gp"))
            order_id = identity(data["order_id"])
            require(order_id not in orders, "Duplicate order ID")
            require(data["batch_id"] in batches, "Missing decision")
            batch = batches[data["batch_id"]]
            require(batch["planned"] > 0, "Order after no-attempt decision")
            if ingestion[batch["decision_id"]] > at:
                deviation(event, "decision_recorded_after_submission")
            item = integer(data["item_id"], "item_id", 1)
            q = integer(data["quantity"], "quantity", 1)
            price = integer(data["price_gp"], "price_gp", 1)
            buy = data["side"] == "buy"
            require(data["side"] in ("buy", "sell"), "Unknown side")
            require(item in (RECIPES[batch["output"]] if buy else (batch["output"],)),
                    "Wrong recipe/order side")
            if buy and price > batch["ceilings"][item]:
                deviation(event, "input_ceiling")
            if any(o["batch_id"] != data["batch_id"] for o in live()):
                deviation(event, "overlapping_batches")
            if any(bid != data["batch_id"] and b["produced"] > b["sold"]
                   for bid, b in batches.items()):
                deviation(event, "overlapping_batches")
            if not buy:
                reserved = sum(o["quantity"] - o["filled_units"] for o in live()
                               if o["item_id"] == item and o["side"] == "sell")
                require(q + reserved <= stock.get(item, 0), "Unowned sale submission")
            orders[order_id] = dict(**data, submitted_at=at, filled_units=0, status="open",
                                    first_fill_at=None, last_fill_at=None, closed_at=None)
            counts["submissions"] += 1
            peak_slots = max(peak_slots, len(live()))
            if len(live()) > 8:
                deviation(event, "slots")
            reserved_cash = sum((o["quantity"] - o["filled_units"]) * o["price_gp"]
                                for o in live() if o["side"] == "buy")
            if reserved_cash > cash:
                deviation(event, "cash_reservation")
        elif kind in ("reject", "cancel", "close"):
            shape(data, ("order_id", "reason"))
            identity(data["reason"])
            require(data["order_id"] in orders, "Unknown order")
            order = orders[data["order_id"]]
            require(order["status"] == "open", "Order already closed")
            if kind == "close":
                require(order["filled_units"] == order["quantity"], "Close of unfilled order")
            if kind == "reject":
                require(order["filled_units"] == 0, "Rejected order has fills")
            if order["side"] == "buy" and at > order["submitted_at"] + 3 * DAY:
                deviation(event, "buy_expiry")
            order.update(status=kind, closed_at=at, reason=data["reason"])
            if kind in ("reject", "cancel"):
                counts["rejections" if kind == "reject" else "cancellations"] += 1
        elif kind == "fill":
            shape(data, ("order_id", "quantity", "price_gp", "tax_gp"))
            require(data["order_id"] in orders, "Unknown order")
            order = orders[data["order_id"]]
            require(order["status"] == "open", "Fill of closed order")
            q = integer(data["quantity"], "quantity", 1)
            price = integer(data["price_gp"], "price_gp", 1)
            paid_tax = integer(data["tax_gp"], "tax_gp")
            buy, item = order["side"] == "buy", order["item_id"]
            batch = batches[order["batch_id"]]
            require(order["filled_units"] + q <= order["quantity"], "Order overfill")
            require(price <= order["price_gp"] if buy else price >= order["price_gp"],
                    "Fill violates order price limit")
            require(paid_tax == 0 if buy else paid_tax <= price * q, "Invalid actual tax")
            order["filled_units"] += q
            order["first_fill_at"] = order["first_fill_at"] or at
            order["last_fill_at"] = at
            if buy:
                cash -= price * q
                require(cash >= 0, "Negative cash")
                stock[item] = stock.get(item, 0) + q
                book[item] = book.get(item, 0) + price * q
                last_buy[item] = at
                batch["bought_gp"] += price * q
                if batch["bought_gp"] > 1_000_000:
                    deviation(event, "batch_budget")
                window = windows.get(item, (at, 0))
                if at >= window[0] + 14400:
                    window = (at, 0)
                windows[item] = (window[0], window[1] + q)
                if windows[item][1] > batch["limits"][item]:
                    deviation(event, "buy_limit")
                if at > order["submitted_at"] + 3 * DAY:
                    deviation(event, "buy_expiry")
            else:
                require(batch["sold"] + q <= batch["produced"], "Unowned batch output")
                cost = consume(item, q)
                proceeds = price * q - paid_tax
                cash += proceeds
                realized += proceeds - cost
                tax += paid_tax
                batch["sold"] += q
            counts["buy_fills" if buy else "sell_fills"] += 1
            counts["buy_units" if buy else "sell_units"] += q
        elif kind == "produce":
            shape(data, ("batch_id", "quantity"))
            require(data["batch_id"] in batches, "Missing production decision")
            batch = batches[data["batch_id"]]
            require(batch["planned"] > 0, "Production after no-attempt decision")
            q = integer(data["quantity"], "quantity", 1)
            output = batch["output"]
            require(all(stock.get(i, 0) >= q for i in RECIPES[output]), "Unowned production inputs")
            require(all(last_buy[i] < at for i in RECIPES[output]), "Input timing before production")
            cost = sum(consume(i, q) for i in RECIPES[output])
            stock[output] = stock.get(output, 0) + q
            book[output] = book.get(output, 0) + cost
            batch["produced"] += q
            counts["produced_units"] += q
            production_days[day] = production_days.get(day, 0) + q
            if production_days[day] > 1650 or batch["produced"] > batch["planned"]:
                deviation(event, "production_rate")
        elif kind == "session":
            shape(data, ("active_seconds", "cash_gp", "inventory"))
            active = integer(data["active_seconds"], "active_seconds")
            require(integer(data["cash_gp"], "cash_gp") == cash, "Cash checkpoint mismatch")
            reported = {i: q for i, q in mapping(data["inventory"]).items() if q}
            require(reported == {i: q for i, q in stock.items() if q}, "Inventory checkpoint mismatch")
            if active > 3600:
                deviation(event, "active_time")
            if active == 0 and day in interaction_days:
                deviation(event, "missing_active_time")
            sessions[day] = active
        else:
            raise ValueError(f"Unknown event kind: {kind}")
        peak_book = max(peak_book, sum(book.values()))
        require(cash - CAPITAL == realized - sum(book.values()), "Cash/book accounting mismatch")

    capital_time += sum(book.values()) * max(0, until - previous)
    for order in live():
        if order["side"] == "buy" and until > order["submitted_at"] + 3 * DAY:
            deviations.append(dict(event_id=order["order_id"], reason="buy_expiry"))
    failures = []
    if now < manifest["end"]:
        failures.append("window_not_ended")
    if len(decisions) < 56:
        failures.append("missing_daily_decisions")
    if len(sessions) < 56:
        failures.append("missing_daily_sessions")
    completed = sum(b["produced"] > 0 and b["produced"] == b["sold"] and
                    not any(o["batch_id"] == bid for o in live()) for bid, b in batches.items())
    if completed < 10:
        failures.append("fewer_than_ten_completed_batches")
    if not counts["buy_fills"] or not counts["sell_fills"]:
        failures.append("missing_buy_or_sale_activity")
    if live():
        failures.append("open_orders")
    if any(stock.values()):
        failures.append("residual_inventory")
    if deviations:
        failures.append("protocol_deviations")
    active = sum(sessions.values())
    return dict(status="awaiting_actual_records" if not events else
                "calibration_complete" if not failures else "inconclusive",
                ready=not failures, readiness_failures=failures, enrolled_at=manifest["enrolled_at"],
                start=manifest["start"], end=manifest["end"], as_of=now, event_count=len(events),
                decisions=len(decisions), sessions=len(sessions),
                attempted_batches=sum(b["planned"] > 0 for b in batches.values()),
                completed_batches=completed, open_orders=len(live()), cash_gp=cash,
                cash_change_gp=cash - CAPITAL, realized_gp=realized, remaining_book_gp=sum(book.values()),
                inventory={str(i): q for i, q in sorted(stock.items()) if q},
                inventory_book_gp={str(i): book[i] for i in sorted(stock) if stock[i]},
                tax_gp=tax, active_seconds=active,
                realized_gp_per_recorded_active_hour=realized * 3600 / active if active else None,
                active_time_complete=(len(sessions) == 56), peak_open_slots=peak_slots,
                peak_book_gp=peak_book, book_gp_seconds=capital_time, deviations=deviations,
                orders=[dict(o, first_fill_wait_seconds=(o["first_fill_at"] - o["submitted_at"]
                              if o["first_fill_at"] is not None else None)) for o in orders.values()],
                **counts, expected_profit_gp=None, marked_profit_gp=None, participation=None,
                p_adjusted=None, historical_battery_p_adjusted=1.0, holdout_read=False,
                interpretation="Descriptive operator-supplied records; no executable-edge inference")


def import_events(path, events, *, now=None):
    now = int(time.time()) if now is None else integer(now, "now")
    path = Path(path).resolve()
    with connect(path, write=True) as db:
        db.execute("BEGIN IMMEDIATE")
        manifest, previous, chain, last_ingested, ingestion = load(db)
        require(now >= last_ingested, "Import time before previous ingestion")
        events = list(events)
        ingestion.update({e["id"]: now for e in events})
        result = replay(manifest, previous + events, path, now, ingestion)
        for seq, event in enumerate(events, start=len(previous) + 1):
            chain = hashlib.sha256((chain + canonical(event) + str(now)).encode()).hexdigest()
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                       [seq, event["id"], event["at"], now, canonical(event), chain])
    return result


def report(path, *, now=None):
    now = int(time.time()) if now is None else integer(now, "now")
    path = Path(path).resolve()
    with connect(path) as db:
        db.execute("BEGIN")
        manifest, events, _, last_ingested, ingestion = load(db)
        require(now >= last_ingested, "Report time before previous ingestion")
        return replay(manifest, events, path, now, ingestion)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "import", "report"))
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--acknowledge-private-research", action="store_true")
    args = parser.parse_args()
    root = external_directory(args.study, args.acknowledge_private_research)
    path = root / "ledger.sqlite"
    if args.action == "init":
        result = initialize(path)
    elif args.action == "import":
        require(args.events is not None and args.events.resolve().is_relative_to(root),
                "Events must be supplied inside study directory")
        events = [json.loads(line) for line in args.events.read_text().splitlines() if line.strip()]
        result = import_events(path, events)
    else:
        require(args.events is None, "Report does not accept events")
        result = report(path)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
