"""One causal, long-only executor for every model. All fills are hypothetical.

A lifecycle occupies one slot from buy submission through its last sale. Cash is
reserved at a fixed buy ceiling. Filled inventory is offered for sale only after
the buy expires/completes and the holding horizon has elapsed. Sell orders wait
indefinitely, including beyond the evaluation boundary (inventory is marked).
"""

import math
from dataclasses import asdict, dataclass
from itertools import pairwise

import pandas as pd

from .costs import DEFAULT_TAX, TaxPolicy, execution_price, sale_proceeds
from .execution import DEFAULT_PORTFOLIO, ExecutionAssumptions, PortfolioPolicy


@dataclass
class Order:
    item: int
    submitted: int
    requested: int
    buy_ceiling: int
    remaining_buy: int
    quantity: int = 0
    cost_gp: int = 0
    first_fill: int | None = None
    sell_submitted: int | None = None
    stage: str = "buy"


@dataclass
class BacktestResult:
    metrics: dict
    fills: list[dict]
    orders: list[dict]
    equity: list[dict]


def present(row: dict, name: str) -> bool:
    return name in row and not pd.isna(row[name])


def simulate(
    observations: pd.DataFrame,
    scores: dict[tuple[int, int], float],
    assumptions: ExecutionAssumptions,
    portfolio: PortfolioPolicy = DEFAULT_PORTFOLIO,
    tax: TaxPolicy = DEFAULT_TAX,
) -> BacktestResult:
    if observations.empty:
        raise ValueError("Backtest needs observations")
    if observations.duplicated(["item_id", "available_at"]).any():
        raise ValueError(
            "Duplicate item availability; qualify overlapping source resolutions first"
        )
    cash = portfolio.initial_cash_gp
    active: dict[int, Order] = {}
    # Per-account/item window starts on the FIRST BUY FILL, not on wall-clock boundaries.
    windows: dict[int, tuple[int, int]] = {}
    latest: dict[int, dict] = {}
    fills, order_log, curve = [], [], []
    requested = bought = sold = realized = 0
    wait_seconds_units = 0
    peak = portfolio.initial_cash_gp
    drawdown = 0.0

    def reserved() -> int:
        return sum(o.remaining_buy * o.buy_ceiling for o in active.values())

    def available_limit(item: int, now: int, row: dict) -> int:
        if not present(row, "buy_limit"):
            return 0
        window = windows.get(item)
        used = window[1] if window and now < window[0] + 14_400 else 0
        return max(0, int(row["buy_limit"]) - used)

    def fresh(row: dict, side: str, now: int) -> bool:
        if row.get("inverted_spread", False):
            return False
        age_key = f"{side}_freshness_seconds"
        uncertainty = 0
        if assumptions.freshness_basis == "upper_bound":
            uncertainty = (
                int(row["source_interval_seconds"])
                if present(row, "source_interval_seconds")
                else assumptions.unknown_interval_seconds
            )
        return (
            present(row, f"avg_{side}_price")
            and present(row, age_key)
            and int(row[age_key]) + uncertainty + now - int(row["available_at"])
            <= assumptions.max_freshness_seconds
            and (not row.get("interval_unknown", True) or assumptions.allow_unknown_metadata)
        )

    start = int(observations.available_at.min())
    end = int(observations.available_at.max())
    if end <= start:
        raise ValueError("Backtest requires positive elapsed time")

    for timestamp, group in observations.groupby("available_at", sort=True):
        now = int(timestamp)
        rows = {int(row["item_id"]): row for row in group.to_dict("records")}
        latest.update(rows)
        # Timeout uses elapsed wall time, even when an item has no new observations.
        for item, order in list(active.items()):
            if order.stage == "buy" and now >= order.submitted + assumptions.buy_timeout_seconds:
                order.remaining_buy = 0  # Releases reservation.
                order.stage = "hold"
                order_log.append(
                    {
                        "timestamp": now,
                        "item_id": item,
                        "event": "buy_expired",
                        "filled": order.quantity,
                    }
                )
            if order.stage == "hold" and order.quantity == 0:
                del active[item]
                continue
            if (
                order.stage == "hold"
                and order.first_fill is not None
                and now >= order.first_fill + portfolio.holding_seconds
            ):
                order.stage = "sell"
                order.sell_submitted = now
                order_log.append({"timestamp": now, "item_id": item, "event": "sell_submitted"})
                # A newly submitted sale cannot consume this same observation.
                continue
            row = rows.get(item)
            submitted = order.sell_submitted if order.stage == "sell" else order.submitted
            if (
                row is None
                or now <= submitted + assumptions.latency_seconds
                or int(row["timestamp"]) < submitted + assumptions.latency_seconds
            ):
                continue
            buy_side, sell_side = ("low", "high") if assumptions.passive_prices else ("high", "low")
            side = buy_side if order.stage == "buy" else sell_side
            if order.stage == "hold" or not fresh(row, side, now):
                continue
            capacity = (
                int(row[f"{side}_price_volume"])
                * assumptions.participation_bps * assumptions.queue_fill_bps // 100_000_000
            )
            price = execution_price(
                int(row[f"avg_{side}_price"]), assumptions.slippage_bps, buy=order.stage == "buy"
            )
            if order.stage == "buy":
                if price > order.buy_ceiling:
                    continue
                quantity = min(order.remaining_buy, capacity, available_limit(item, now, row))
                if quantity <= 0:
                    continue
                window = windows.get(item)
                if window is None or now >= window[0] + 14_400:
                    window = (now, 0)
                windows[item] = (window[0], window[1] + quantity)
                cash -= quantity * price
                order.cost_gp += quantity * price
                order.quantity += quantity
                order.remaining_buy -= quantity
                order.first_fill = order.first_fill if order.first_fill is not None else now
                bought += quantity
                wait_seconds_units += (now - order.submitted) * quantity
                if order.remaining_buy == 0:
                    order.stage = "hold"
                fills.append(
                    {
                        "timestamp": now,
                        "submitted": order.submitted,
                        "item_id": item,
                        "side": "buy",
                        "quantity": quantity,
                        "price_gp": price,
                        "cash_delta_gp": -quantity * price,
                        "tax_gp": 0,
                    }
                )
            else:
                quantity = min(order.quantity, capacity)
                if quantity <= 0:
                    continue
                proceeds = sale_proceeds(price, quantity, tax, item)
                # Allocate integer book cost; final sale consumes any rounding remainder.
                cost = order.cost_gp * quantity // order.quantity
                realized += proceeds - cost
                cash += proceeds
                sold += quantity
                order.quantity -= quantity
                order.cost_gp -= cost
                fills.append(
                    {
                        "timestamp": now,
                        "submitted": order.sell_submitted,
                        "item_id": item,
                        "side": "sell",
                        "quantity": quantity,
                        "price_gp": price,
                        "cash_delta_gp": proceeds,
                        "tax_gp": price * quantity - proceeds,
                    }
                )
                if order.quantity == 0:
                    del active[item]

        candidates = []
        for item, row in rows.items():
            score = scores.get((item, now), float("-inf"))
            if math.isfinite(score) and score > portfolio.minimum_score:
                candidates.append((score, item, row))
        for score, item, row in sorted(candidates, key=lambda c: (-c[0], c[1])):
            if (
                item in active
                or len(active) >= portfolio.offer_slots
                or not fresh(row, "low" if assumptions.passive_prices else "high", now)
            ):
                continue
            ceiling = execution_price(
                int(row["avg_low_price"] if assumptions.passive_prices else row["avg_high_price"]),
                assumptions.slippage_bps, buy=True
            )
            budget = min(
                cash - reserved(), portfolio.initial_cash_gp * portfolio.allocation_bps // 10_000
            )
            quantity = min(budget // ceiling, available_limit(item, now, row))
            if quantity <= 0:
                continue
            active[item] = Order(item, now, quantity, ceiling, quantity)
            requested += quantity
            order_log.append(
                {
                    "timestamp": now,
                    "item_id": item,
                    "event": "buy_submitted",
                    "quantity": quantity,
                    "score": score,
                    "buy_ceiling_gp": ceiling,
                }
            )

        inventory_value = 0
        for item, order in active.items():
            row = latest[item]
            low = int(row["avg_low_price"]) if present(row, "avg_low_price") else 0
            # Terminal marks include adverse slippage + a fixed illiquidity haircut,
            # regardless of whether there is enough volume to sell the position.
            mark = execution_price(low, assumptions.slippage_bps, buy=False)
            mark = execution_price(mark, assumptions.terminal_haircut_bps, buy=False)
            inventory_value += sale_proceeds(mark, order.quantity, tax, item)
        equity = cash + inventory_value
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
        tied = reserved() + sum(o.cost_gp for o in active.values())
        if cash < 0 or reserved() > cash:
            raise AssertionError("Cash conservation/reservation violated")
        curve.append(
            {
                "timestamp": now,
                "cash_gp": cash,
                "equity_gp": equity,
                "inventory_mark_gp": inventory_value,
                "capital_tied_gp": tied,
                "active_slots": len(active),
            }
        )

    hours = (end - start) / 3600
    # Time-weighted capital, including irregular gaps; last sample has zero duration.
    capital_seconds = sum(
        a["capital_tied_gp"] * (b["timestamp"] - a["timestamp"]) for a, b in pairwise(curve)
    )
    net = curve[-1]["equity_gp"] - portfolio.initial_cash_gp
    metrics = {
        "elapsed_hours": hours,
        "net_gp": net,
        "net_gp_per_hour": net / hours,
        "return_on_capital": net / portfolio.initial_cash_gp,
        "max_drawdown": drawdown,
        "fill_rate": bought / requested if requested else 0.0,
        "buy_units_requested": requested,
        "buy_units_filled": bought,
        "sell_units_filled": sold,
        "realized_gp": realized,
        "cash_pnl_gp": cash - portfolio.initial_cash_gp,
        "end_cash_gp": cash,
        "end_inventory_mark_gp": curve[-1]["inventory_mark_gp"],
        "end_inventory_units": sum(o.quantity for o in active.values()),
        "end_open_buy_units": sum(o.remaining_buy for o in active.values()),
        "mean_capital_tied_gp": capital_seconds / (end - start),
        "peak_capital_tied_gp": max(p["capital_tied_gp"] for p in curve),
        "end_capital_tied_gp": curve[-1]["capital_tied_gp"],
        "mean_buy_wait_seconds": wait_seconds_units / bought if bought else 0.0,
        "turnover": sum(abs(f["cash_delta_gp"]) for f in fills) / portfolio.initial_cash_gp,
        "execution": asdict(assumptions),
        "portfolio": asdict(portfolio),
        "tax": asdict(tax),
    }
    return BacktestResult(metrics, fills, order_log, curve)
