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

from .costs import (
    DEFAULT_TAX,
    TaxPolicy,
    UntradeablePrice,
    execution_price,
    integer_lots,
    price_target,
    sale_proceeds,
)
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
    buy_reference: int | None = None
    buy_target: int | None = None
    sell_reference: int | None = None
    sell_target: int | None = None


@dataclass
class BacktestResult:
    metrics: dict
    fills: list[dict]
    orders: list[dict]
    equity: list[dict]


class PreparedObservations:
    """Snapshot and convert a development frame once for repeated policy replays.

    Internal records are read-only by convention. The source frame can subsequently
    change without changing this snapshot. This cache contains no scores or outcomes
    beyond the explicitly provided observations.
    """

    def __init__(self, observations: pd.DataFrame):
        self.frame = observations.copy(deep=True)
        self.buckets = [
            (int(now), {int(row["item_id"]): row for row in group.to_dict("records")})
            for now, group in self.frame.groupby("available_at", sort=True)
        ]


class StreamingObservations:
    """Validated, unique availability buckets replayed from a bounded disk cursor."""

    def __init__(self, start, end, buckets):
        self.start, self.end, self.buckets = start, end, buckets


def present(row: dict, name: str) -> bool:
    return name in row and not pd.isna(row[name])


def compatible_volume(volume: int, mean: int, threshold: int, *, buy: bool, rule: str) -> int:
    """Conditional proxy or loose moment upper bound; never an own-fill guarantee."""
    if volume < 0 or min(mean, threshold) < 1:
        raise ValueError("Positive prices and nonnegative volume required")
    if rule == "mean_proxy":
        return volume if (mean <= threshold if buy else mean >= threshold) else 0
    if rule != "moment_upper":
        raise ValueError("Unknown volume qualification")
    if buy:
        return volume if max(1, mean - 1) <= threshold else max(0, volume - 1)
    return volume if threshold == 1 else min(volume, volume * mean // (threshold - 1))


def simulate(
    observations: pd.DataFrame | PreparedObservations | StreamingObservations,
    scores: dict[tuple[int, int], float],
    assumptions: ExecutionAssumptions,
    portfolio: PortfolioPolicy = DEFAULT_PORTFOLIO,
    tax: TaxPolicy = DEFAULT_TAX,
    *,
    allocation_bps: dict[tuple[int, int], int] | None = None,
) -> BacktestResult:
    steps = simulation_steps(observations, scores, assumptions, portfolio, tax,
                             allocation_bps=allocation_bps)
    while True:
        try:
            next(steps)
        except StopIteration as completed:
            return completed.value


def simulation_steps(
    observations,
    scores,
    assumptions,
    portfolio=DEFAULT_PORTFOLIO,
    tax=DEFAULT_TAX,
    *,
    allocation_bps=None,
):
    """Advance one bucket at a time, allowing replays to share an archive stream."""
    streaming = observations if isinstance(observations, StreamingObservations) else None
    prepared = observations if isinstance(observations, PreparedObservations) else None
    if prepared is not None:
        observations = prepared.frame
    if streaming is None and observations.empty:
        raise ValueError("Backtest needs observations")
    if streaming is None and observations.duplicated(["item_id", "available_at"]).any():
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
    legacy = assumptions.price_model == "legacy_v1"
    bounded = assumptions.fill_model == "volume_bounded_v3"
    opportunity_id = 0

    def target_price(reference, *, buy, now, item, phase):
        if legacy:
            return execution_price(int(reference), assumptions.slippage_bps, buy=buy) * 10_000
        try:
            return price_target(
                reference, assumptions.slippage_bps, buy=buy, ticks=assumptions.adverse_ticks
            )
        except UntradeablePrice as error:
            order_log.append(
                dict(
                    timestamp=now,
                    item_id=item,
                    event="price_rejected",
                    phase=phase,
                    reason=str(error),
                    side="buy" if buy else "sell",
                )
            )
            return None

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
                else int(row.get("resolution_seconds", assumptions.unknown_interval_seconds))
            )
        return (
            present(row, f"avg_{side}_price")
            and present(row, age_key)
            and int(row[age_key]) + uncertainty + now - int(row["available_at"])
            <= assumptions.max_freshness_seconds
            and (not row.get("interval_unknown", True) or assumptions.allow_unknown_metadata)
        )

    start = int(streaming.start if streaming else observations.available_at.min())
    end = int(streaming.end if streaming else observations.available_at.max())
    if end <= start:
        raise ValueError("Backtest requires positive elapsed time")

    if streaming:
        buckets = streaming.buckets
    elif prepared:
        buckets = prepared.buckets
    else:
        buckets = observations.groupby("available_at", sort=True)
    for timestamp, group in buckets:
        now = int(timestamp)
        rows = (
            {int(row["item_id"]): row for row in group.to_dict("records")}
            if prepared is None and streaming is None
            else group
        )
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
                if bounded:
                    row = latest.get(item)
                    if row is None or not fresh(row, "high", now):
                        continue
                    target = target_price(
                        row["avg_high_price"], buy=False, now=now, item=item, phase="submission"
                    )
                    if target is None:
                        continue
                    order.sell_reference = int(row["avg_high_price"])
                    order.sell_target = target
                order.stage = "sell"
                order.sell_submitted = now
                order_log.append(
                    {
                        "timestamp": now,
                        "item_id": item,
                        "event": "sell_submitted",
                        **(
                            {
                                "reference_price_gp": order.sell_reference,
                                "target_numerator": order.sell_target,
                            }
                            if bounded
                            else {}
                        ),
                    }
                )
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
                * assumptions.participation_bps
                * assumptions.queue_fill_bps
                // 100_000_000
            )
            buying = order.stage == "buy"
            reference = row[f"avg_{side}_price"]
            bucket_volume = int(row[f"{side}_price_volume"])
            qualifying = bucket_volume
            threshold = None
            if bounded:
                # Validate aggregate prices too; never truncate malformed means.
                try:
                    price_target(reference, 0, buy=buying)
                except UntradeablePrice as error:
                    order_log.append(
                        dict(
                            timestamp=now,
                            item_id=item,
                            event="price_rejected",
                            phase="qualification",
                            reason=str(error),
                        )
                    )
                    continue
                interval = (
                    int(row["source_interval_seconds"])
                    if present(row, "source_interval_seconds")
                    else int(row["resolution_seconds"])
                )
                # Whole buckets only; no invented intrabucket survival or limit resets.
                if buying and int(row["timestamp"]) + interval > (
                    order.submitted + assumptions.buy_timeout_seconds
                ):
                    continue
                reference = order.buy_reference if buying else order.sell_reference
                target = order.buy_target if buying else order.sell_target
                threshold = target // 10_000 if buying else (target + 9999) // 10_000
                qualifying = compatible_volume(
                    bucket_volume,
                    int(row[f"avg_{side}_price"]),
                    threshold,
                    buy=buying,
                    rule=assumptions.volume_qualification,
                )
                capacity = qualifying * assumptions.participation_bps // 10_000
            else:
                target = target_price(reference, buy=buying, now=now, item=item, phase="fill")
            if target is None:
                continue
            if buying and (target + 9999) // 10_000 > order.buy_ceiling:
                continue
            quantity = (
                min(order.remaining_buy, capacity, available_limit(item, now, row))
                if buying
                else min(order.quantity, capacity)
            )
            if quantity <= 0:
                continue
            lots = (
                [(target // 10_000, quantity)]
                if legacy
                else integer_lots(target, quantity, buy=buying)
            )
            opportunity_id += 1
            gross = sum(price * units for price, units in lots)
            price_cost = (gross - int(reference) * quantity) * (1 if buying else -1)
            tick_cost = assumptions.adverse_ticks * quantity
            residual = (
                int(reference) * quantity * assumptions.slippage_bps
                - (price_cost - tick_cost) * 10_000
            )
            submitted = order.submitted if buying else order.sell_submitted
            if buying:
                window = windows.get(item)
                if window is None or now >= window[0] + 14_400:
                    window = (now, 0)
                windows[item] = (window[0], window[1] + quantity)
                cash -= gross
                order.cost_gp += gross
                order.quantity += quantity
                order.remaining_buy -= quantity
                order.first_fill = order.first_fill if order.first_fill is not None else now
                bought += quantity
                wait_seconds_units += (now - order.submitted) * quantity
                if order.remaining_buy == 0:
                    order.stage = "hold"
            else:
                proceeds = sum(sale_proceeds(p, q, tax, item) for p, q in lots)
                # Allocate integer book cost; final sale consumes any remainder.
                cost = order.cost_gp * quantity // order.quantity
                realized += proceeds - cost
                cash += proceeds
                sold += quantity
                order.quantity -= quantity
                order.cost_gp -= cost
                if order.quantity == 0:
                    del active[item]
            for lot_index, (price, units) in enumerate(lots):
                proceeds = sale_proceeds(price, units, tax, item) if not buying else 0
                fills.append(
                    {
                        "timestamp": now,
                        "submitted": submitted,
                        "item_id": item,
                        "side": "buy" if buying else "sell",
                        "quantity": units,
                        "price_gp": price,
                        "cash_delta_gp": -price * units if buying else proceeds,
                        "tax_gp": 0 if buying else price * units - proceeds,
                        "opportunity_id": opportunity_id,
                        "reference_price_gp": int(reference),
                        "reference_notional_gp": int(reference) * units,
                        "slippage_bps": assumptions.slippage_bps,
                        "slippage_cost_gp": (price - int(reference)) * units * (1 if buying else -1)
                        - assumptions.adverse_ticks * units,
                        "tick_cost_gp": assumptions.adverse_ticks * units,
                        # One residual per opportunity, not once per price lot.
                        "cost_rounding_numerator": residual if lot_index == 0 else 0,
                        **(
                            {
                                "bucket_volume": bucket_volume,
                                "compatible_volume_upper_or_proxy": qualifying,
                                "participation_capacity": capacity,
                                "qualification_price_gp": threshold,
                                "bucket_mean_gp": int(row[f"avg_{side}_price"]),
                                "bucket_start": int(row["timestamp"]),
                                "bucket_end": int(row["timestamp"]) + interval,
                            }
                            if bounded
                            else {}
                        ),
                    }
                )

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
            target = target_price(
                row["avg_low_price"] if assumptions.passive_prices else row["avg_high_price"],
                buy=True,
                now=now,
                item=item,
                phase="submission",
            )
            if target is None:
                continue
            ceiling = (target + 9999) // 10_000
            allocation = (
                portfolio.allocation_bps
                if allocation_bps is None
                else allocation_bps.get((item, now), portfolio.allocation_bps)
            )
            if type(allocation) is not int or not 0 < allocation <= 10_000:
                raise ValueError("Per-decision allocation must be integer bps in (0, 10000]")
            budget = min(
                cash - reserved(), portfolio.initial_cash_gp * allocation // 10_000
            )
            quantity = min(budget // ceiling, available_limit(item, now, row))
            if quantity <= 0:
                continue
            active[item] = Order(
                item,
                now,
                quantity,
                ceiling,
                quantity,
                buy_reference=int(row["avg_low_price"]) if bounded else None,
                buy_target=target if bounded else None,
            )
            requested += quantity
            order_log.append(
                {
                    "timestamp": now,
                    "item_id": item,
                    "event": "buy_submitted",
                    "quantity": quantity,
                    "score": score,
                    "buy_ceiling_gp": ceiling,
                    **(
                        {
                            "reference_price_gp": int(row["avg_low_price"]),
                            "target_numerator": target,
                        }
                        if bounded
                        else {}
                    ),
                }
            )

        inventory_value = 0
        unpriceable_units = 0
        mark_gross = mark_tax = mark_rounding_numerator = 0
        for item, order in active.items():
            if not order.quantity:
                continue
            row = latest[item]
            low = row["avg_low_price"] if present(row, "avg_low_price") else 0
            if legacy:
                mark = execution_price(int(low), assumptions.slippage_bps, buy=False)
                mark = execution_price(mark, assumptions.terminal_haircut_bps, buy=False)
                proceeds = sale_proceeds(mark, order.quantity, tax, item)
                inventory_value += proceeds
                mark_gross += mark * order.quantity
                mark_tax += mark * order.quantity - proceeds
            else:
                try:
                    target = price_target(
                        low, assumptions.slippage_bps, buy=False, ticks=assumptions.adverse_ticks
                    ) * (10_000 - assumptions.terminal_haircut_bps)
                    lots = integer_lots(target, order.quantity, buy=False, denominator=100_000_000)
                    gross = sum(p * q for p, q in lots)
                    proceeds = sum(sale_proceeds(p, q, tax, item) for p, q in lots)
                    inventory_value += proceeds
                    mark_gross += gross
                    mark_tax += gross - proceeds
                    mark_rounding_numerator += gross * 100_000_000 - target * order.quantity
                except UntradeablePrice:
                    # A zero valuation bound is not a fill, liquidation or slot release.
                    unpriceable_units += order.quantity
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
                "unpriceable_inventory_units": unpriceable_units,
                "inventory_gross_mark_gp": mark_gross,
                "inventory_mark_tax_gp": mark_tax,
                "inventory_mark_rounding_gp": (
                    None if legacy else mark_rounding_numerator / 100_000_000
                ),
                "capital_tied_gp": tied,
                "active_slots": len(active),
            }
        )
        yield now

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
        "end_unpriceable_inventory_units": curve[-1]["unpriceable_inventory_units"],
        "end_inventory_gross_mark_gp": curve[-1]["inventory_gross_mark_gp"],
        "end_inventory_mark_tax_gp": curve[-1]["inventory_mark_tax_gp"],
        "end_inventory_mark_rounding_gp": curve[-1]["inventory_mark_rounding_gp"],
        "price_rejections": sum(o["event"] == "price_rejected" for o in order_log),
        "untradeable_at_granularity": sum(
            o.get("reason") == "untradeable_at_granularity" for o in order_log
        ),
        "invalid_reference_price": sum(
            o.get("reason") == "invalid_reference_price" for o in order_log
        ),
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
    for side in ("buy", "sell"):
        events = [f for f in fills if f["side"] == side]
        notional = sum(f["reference_notional_gp"] for f in events)
        cost = sum(f["slippage_cost_gp"] for f in events)
        metrics.update(
            {
                f"{side}_reference_notional_gp": notional,
                f"{side}_slippage_cost_gp": cost,
                f"{side}_effective_slippage_bps": cost * 10_000 / notional if notional else None,
                f"{side}_tick_cost_gp": sum(f["tick_cost_gp"] for f in events),
                f"{side}_effective_tick_bps": (
                    sum(f["tick_cost_gp"] for f in events) * 10_000 / notional if notional else None
                ),
                f"{side}_cost_rounding_gp": sum(f["cost_rounding_numerator"] for f in events)
                / 10_000,
                f"{side}_fill_opportunities": len({f["opportunity_id"] for f in events}),
            }
        )
    return BacktestResult(metrics, fills, order_log, curve)
