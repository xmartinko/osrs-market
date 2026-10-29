"""Capacity-limited conversion accounts with separately purchased input legs."""

import math

import pandas as pd

from .backtest import BacktestResult, PreparedObservations
from .costs import integer_lots, price_target, sale_proceeds

DAY = 86400
CASH = 10_000_000


def simulate_mechanical(observations, mapping, rule, share):
    if rule not in ("alchemy", "processing"):
        raise ValueError("No observed shop execution model")
    prepared = observations if isinstance(observations, PreparedObservations) else PreparedObservations(
        observations)
    if not prepared.buckets or len(prepared.buckets) < 2:
        raise ValueError("Require multiple completed buckets")
    metadata = mapping.set_index("id")
    alch_values = metadata.high_alch.dropna().astype(int).to_dict()
    limits = metadata.buy_limit.dropna().astype(int).to_dict()
    production_rate = 1000 if rule == "alchemy" else 1800
    max_units = production_rate * 55 // 60
    cash = CASH - (1500 if rule == "alchemy" else 0)
    fixed_cost = CASH - cash
    stock, book, windows, latest = {}, {}, {}, {}
    active = None
    output_pending = None
    fills, orders, curve = [], [], []
    completed = produced = requested = realized = 0
    active_hours = 0.
    opportunity = 0
    peak, drawdown = CASH, 0.
    start, end = prepared.buckets[0][0], prepared.buckets[-1][0]

    def available(item, now):
        window = windows.get(item)
        used = window[1] if window and now < window[0] + 14400 else 0
        return max(0, limits.get(item, 0) - used)

    def unit_cost(row, buy):
        ref = int(row["avg_high_price" if buy else "avg_low_price"])
        return (price_target(ref, 10, buy=buy) + (9999 if buy else 0)) // 10000

    def valid(row):
        return (row is not None and not row.get("inverted_spread", False) and
                pd.notna(row["avg_high_price"]) and pd.notna(row["avg_low_price"]) and
                int(row["avg_high_price"]) >= int(row["avg_low_price"]) > 0 and
                int(row["high_price_volume"]) > 0 and int(row["low_price_volume"]) > 0)

    def consume(item, q):
        cost = book[item] * q // stock[item]
        stock[item] -= q
        book[item] -= cost
        return cost

    def exchange(item, q, row, now, submitted, buy):
        nonlocal cash, opportunity, realized
        reference = int(row["avg_high_price" if buy else "avg_low_price"])
        target = price_target(reference, 10, buy=buy)
        lots = integer_lots(target, int(q), buy=buy)
        opportunity += 1
        notional = sum(p * n for p, n in lots)
        if buy:
            cash -= notional
            stock[item] = stock.get(item, 0) + q
            book[item] = book.get(item, 0) + notional
            window = windows.get(item)
            if window is None or now >= window[0] + 14400:
                window = (now, 0)
            windows[item] = (window[0], window[1] + q)
        else:
            proceeds = sum(sale_proceeds(p, n, item_id=item) for p, n in lots)
            realized += proceeds - consume(item, q)
            cash += proceeds
        for p, n in lots:
            proceeds = sale_proceeds(p, n, item_id=item) if not buy else 0
            fills.append(dict(item_id=item, timestamp=now, submitted=submitted,
                              side="buy" if buy else "sell", quantity=int(n), price_gp=int(p),
                              cash_delta_gp=int(-p * n if buy else proceeds),
                              reference_price_gp=reference, reference_notional_gp=reference * n,
                              tax_gp=0 if buy else p * n - proceeds,
                              slippage_cost_gp=(p - reference) * n * (1 if buy else -1),
                              opportunity_id=opportunity,
                              bucket_volume=int(row["high_price_volume" if buy else "low_price_volume"]),
                              bucket_start=int(row["timestamp"]),
                              bucket_end=int(row["timestamp"]) + DAY))

    for now, rows in prepared.buckets:
        latest.update(rows)
        # Production runs before this timestamp's purchases: newly bought legs cannot be consumed.
        if active is not None and active["stage"] == "produce" and now > active["last_buy"]:
            ingredients = active["inputs"]
            q = min([stock.get(i, 0) for i in ingredients] + [max_units])
            if q:
                cost = sum(consume(i, q) for i in ingredients)
                active_hours += q / production_rate + 5 / 60
                produced += q
                if rule == "alchemy":
                    coins = alch_values[active["item"]] * q
                    cash += coins
                    realized += coins - cost
                    completed += 1
                else:
                    item = active["item"]
                    stock[item] = stock.get(item, 0) + q
                    book[item] = book.get(item, 0) + cost
                    output_pending = dict(item=item, submitted=now)
                orders.append(dict(timestamp=now, event="production", item_id=active["item"],
                                   quantity=q, input_cost_gp=cost,
                                   coins_gp=alch_values[active["item"]] * q if rule == "alchemy" else 0))
            active = None

        if output_pending is not None:
            item, submitted = output_pending["item"], output_pending["submitted"]
            row = rows.get(item)
            if valid(row) and int(row["timestamp"]) >= submitted + 300:
                q = min(stock[item], int(row["low_price_volume"]) * share // 10000)
                if q:
                    exchange(item, q, row, now, submitted, False)
                    if stock[item] == 0:
                        output_pending = None
                        completed += 1

        if active is not None and active["stage"] == "buy":
            submitted = active["submitted"]
            if now >= submitted + 3 * DAY + 300:
                active["stage"] = "produce"
                active["last_buy"] = now
                orders.append(dict(timestamp=now, event="buy_expired", item_id=active["item"]))
            else:
                for item in active["inputs"]:
                    row = rows.get(item)
                    if (not valid(row) or int(row["timestamp"]) < submitted + 300 or
                            int(row["timestamp"]) + DAY > submitted + 3 * DAY + 300):
                        continue
                    ceiling = active["ceilings"][item]
                    if unit_cost(row, True) > ceiling:
                        continue
                    q = min(active["remaining"][item], available(item, now),
                            int(row["high_price_volume"]) * share // 10000, cash // ceiling)
                    if q:
                        exchange(item, q, row, now, submitted, True)
                        active["remaining"][item] -= q
                        active["last_buy"] = now
                if all(q == 0 for q in active["remaining"].values()):
                    active["stage"] = "produce"

        if active is None and output_pending is None and now < end - 4 * DAY:
            candidates = []
            if rule == "alchemy" and valid(rows.get(561)):
                rune = unit_cost(rows[561], True)
                for item, row in rows.items():
                    if item == 561 or item not in alch_values or not valid(row):
                        continue
                    input_cost = unit_cost(row, True) + rune
                    margin = alch_values[item] - input_cost
                    if margin > 0:
                        candidates.append((margin / input_cost, item, (item, 561), input_cost))
            elif rule == "processing":
                for item, inputs in [(859, (70, 1777)), (855, (66, 1777))]:
                    if not valid(rows.get(item)) or not all(valid(rows.get(i)) for i in inputs):
                        continue
                    input_cost = sum(unit_cost(rows[i], True) for i in inputs)
                    output = unit_cost(rows[item], False)
                    margin = sale_proceeds(output, 1, item_id=item) - input_cost
                    if margin > 0:
                        candidates.append((margin / input_cost, item, inputs, input_cost))
            for _, item, inputs, cost in sorted(candidates, key=lambda x: (-x[0], x[1])):
                occupied = {i for i, q in stock.items() if q} | set(inputs) | {item}
                if len(occupied) > 8:
                    continue
                q = min([max_units, min(cash, 1_000_000) // cost] +
                        [available(i, now) for i in inputs])
                if q <= 0:
                    continue
                active = dict(item=item, inputs=inputs, submitted=now, last_buy=now, stage="buy",
                              remaining={i: q for i in inputs},
                              ceilings={i: unit_cost(rows[i], True) for i in inputs})
                requested += q * len(inputs)
                orders.append(dict(timestamp=now, event="batch_submitted", item_id=item,
                                   quantity=q, inputs=list(inputs)))
                break

        mark = raw_mark = 0
        for item, q in stock.items():
            if not q or item not in latest or pd.isna(latest[item]["avg_low_price"]):
                continue
            reference = int(latest[item]["avg_low_price"])
            raw_mark += q * reference
            target = price_target(reference, 10, buy=False) * 9900
            mark += sum(sale_proceeds(p, n, item_id=item) for p, n in
                        integer_lots(target, int(q), buy=False, denominator=100_000_000))
        reservation = (sum(active["remaining"][i] * active["ceilings"][i]
                           for i in active["inputs"]) if active and active["stage"] == "buy" else 0)
        # The batch reservation is funded before opening. Partial fills release their own ceiling.
        if cash < 0 or reservation > cash:
            raise AssertionError("Mechanical cash/reservation conservation")
        tied = sum(book.values()) + reservation
        equity = cash + mark
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
        curve.append(dict(timestamp=now, cash_gp=cash, equity_gp=equity, inventory_mark_gp=mark,
                          capital_tied_gp=tied,
                          active_slots=len({i for i, q in stock.items() if q} |
                                           (set(active["inputs"]) if active else set()))))
        if curve[-1]["active_slots"] > 8:
            raise AssertionError("Mechanical slot bound")
    hours = (end - start) / 3600
    capital_seconds = sum(a["capital_tied_gp"] * (b["timestamp"] - a["timestamp"])
                          for a, b in zip(curve[:-1], curve[1:], strict=True))
    net = curve[-1]["equity_gp"] - CASH
    metrics = dict(net_gp=net, net_gp_per_hour=net / hours, elapsed_hours=hours,
                   return_on_capital=net / CASH, max_drawdown=drawdown,
                   mean_capital_tied_gp=capital_seconds / (end - start),
                   peak_capital_tied_gp=max(r["capital_tied_gp"] for r in curve),
                   end_inventory_mark_gp=curve[-1]["inventory_mark_gp"],
                   end_inventory_gross_mark_gp=raw_mark, terminal_raw_gp=raw_mark,
                   end_inventory_units=sum(stock.values()), cash_pnl_gp=cash - CASH,
                   realized_gp=realized - fixed_cost,
                   turnover=sum(abs(f["cash_delta_gp"]) for f in fills) / CASH,
                   buy_units_filled=sum(f["quantity"] for f in fills if f["side"] == "buy"),
                   sell_units_filled=sum(f["quantity"] for f in fills if f["side"] == "sell"),
                   buy_units_requested=requested, active_hours=active_hours,
                   active_gp_per_hour=net / active_hours if active_hours else None,
                   produced_units=produced, fixed_cost_gp=fixed_cost,
                   execution=dict(price_model="integer_lots_v2", participation_bps=share,
                                  slippage_bps=10, latency_seconds=300,
                                  fill_model="crossed_bucket_proxy", historical_limits=False))
    if not math.isclose(CASH - fixed_cost + sum(f["cash_delta_gp"] for f in fills) +
                        sum(o.get("coins_gp", 0) for o in orders), cash):
        raise AssertionError("Mechanical ledger cash identity")
    return BacktestResult(metrics, fills, orders, curve), completed
