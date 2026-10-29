"""Independent ledger audit for integer_lots_v2 development replay artifacts.

Run: python -m osrs_ml.execution_audit OUTPUT PANEL
Reads explicit development folds only; never discovers holdout artifacts.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .data import sha256


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(output: Path, panel: Path) -> dict:
    run = json.loads((output / "run.json").read_text())
    require(run["status"] == "complete", "Incomplete replay")
    require(run["price_model"] == "integer_lots_v2", "Wrong price version")
    require(not run["holdout_read"], "Holdout was read")
    require(sha256(panel) == run["input_hashes"]["panel"], "Changed panel")
    totals = dict(scenarios=0, fill_lots=0, opportunities=0, no_buys=0, price_rejections=0)
    for fold_index, fold in enumerate(run["folds"]):
        require(fold["end"] <= run["holdout_start"], "Fold crosses holdout")
        observations = pq.read_table(
            panel,
            filters=[("available_at", ">=", fold["start"]), ("available_at", "<", fold["end"])],
        ).to_pandas(types_mapper=pd.ArrowDtype)
        lookup = observations.set_index(["item_id", "available_at"])
        latest = observations.sort_values("available_at").groupby("item_id").tail(1)
        last_prices = latest.set_index("item_id").avg_low_price.to_dict()
        for scenario, policy in run["scenarios"].items():
            for model in run["models"]:
                path = output / f"fold{fold_index}" / scenario / model
                metrics = json.loads((path / "metrics.json").read_text())
                fills = pd.read_parquet(path / "fills.parquet")
                orders = pd.read_parquet(path / "orders.parquet").to_dict("records")
                equity = pd.read_parquet(path / "equity.parquet")
                cash = run["portfolio"]["initial_cash_gp"]
                inventory, book = defaultdict(int), defaultdict(int)
                units, cost_gp, notionals, tick_gp = (defaultdict(int) for _ in range(4))
                residuals = defaultdict(int)
                windows = {}
                realized = 0
                buy_orders = {
                    (int(o["item_id"]), int(o["timestamp"])): o
                    for o in orders
                    if o["event"] == "buy_submitted"
                }
                requested_fills = defaultdict(int)
                if not fills.empty:
                    require(fills.price_gp.ge(1).all(), "Illegal nonpositive fill price")
                    require(fills.quantity.ge(1).all(), "Illegal fill quantity")
                    require(str(fills.price_gp.dtype).startswith("int"), "Noninteger fill price")
                    require(str(fills.quantity.dtype).startswith("int"), "Noninteger fill quantity")
                    for _, group in fills.groupby("opportunity_id", sort=False):
                        f = group.iloc[0]
                        item, now = int(f.item_id), int(f.timestamp)
                        side, submitted = f.side, int(f.submitted)
                        buying = side == "buy"
                        require(fold["start"] <= now < fold["end"], "Out-of-fold fill")
                        require(
                            group.item_id.eq(item).all()
                            and group.timestamp.eq(now).all()
                            and group.side.eq(side).all(),
                            "Mixed opportunity",
                        )
                        row = lookup.loc[(item, now)]
                        price_side = (
                            ("low" if buying else "high")
                            if policy["passive_prices"]
                            else ("high" if buying else "low")
                        )
                        reference = int(row[f"avg_{price_side}_price"])
                        q = int(group.quantity.sum())
                        require(group.reference_price_gp.eq(reference).all(), "Reference drift")
                        target = (
                            reference * (10_000 + (1 if buying else -1) * policy["slippage_bps"])
                            + (1 if buying else -1) * policy["adverse_ticks"] * 10_000
                        )
                        require(target >= 10_000, "Untradeable price generated a fill")
                        allowed = {target // 10_000, (target + 9999) // 10_000}
                        require(set(group.price_gp).issubset(allowed), "Wrong price lots")
                        gross = sum(int(r.price_gp) * int(r.quantity) for r in group.itertuples())
                        paid_bps = reference * q * policy["slippage_bps"] // 10_000
                        ticks = policy["adverse_ticks"] * q
                        require(
                            gross == reference * q + (1 if buying else -1) * (paid_bps + ticks),
                            "Bps notional cost mismatch",
                        )
                        residual = reference * q * policy["slippage_bps"] % 10_000
                        require(
                            int(group.cost_rounding_numerator.sum()) == residual,
                            "Unreported rounding residual",
                        )
                        require(int(group.slippage_cost_gp.sum()) == paid_bps, "Paid bps mismatch")
                        require(int(group.tick_cost_gp.sum()) == ticks, "Tick cost mismatch")
                        capacity = (
                            int(row[f"{price_side}_price_volume"])
                            * (policy["participation_bps"] * policy["queue_fill_bps"])
                            // 100_000_000
                        )
                        require(q <= capacity, "Capacity exceeded by price lots")
                        require(
                            now > submitted + policy["latency_seconds"]
                            and int(row.timestamp) >= submitted + policy["latency_seconds"],
                            "Noncausal fill",
                        )
                        uncertainty = 0
                        if policy["freshness_basis"] == "upper_bound":
                            interval = row.source_interval_seconds
                            uncertainty = int(
                                row.resolution_seconds if pd.isna(interval) else interval
                            )
                        require(
                            int(row[f"{price_side}_freshness_seconds"]) + uncertainty
                            <= policy["max_freshness_seconds"],
                            "Stale fill",
                        )
                        proceeds = 0
                        tax = metrics["tax"]
                        for lot in group.to_dict("records"):
                            p, n = lot["price_gp"], lot["quantity"]
                            unit_tax = (
                                0
                                if p <= tax["exempt_through_gp"] or item in (tax["exempt_item_ids"])
                                else min(p * tax["rate_bps"] // 10_000, tax["cap_gp"])
                            )
                            expected_tax = 0 if buying else unit_tax * n
                            expected_cash = -p * n if buying else p * n - expected_tax
                            require(lot["tax_gp"] == expected_tax, "Tax mismatch")
                            require(lot["cash_delta_gp"] == expected_cash, "Cash mismatch")
                            proceeds += expected_cash
                        if buying:
                            order = buy_orders[(item, submitted)]
                            require(
                                group.price_gp.le(order["buy_ceiling_gp"]).all(),
                                "Offer ceiling exceeded",
                            )
                            requested_fills[(item, submitted)] += q
                            require(
                                requested_fills[(item, submitted)] <= order["quantity"],
                                "Requested quantity exceeded",
                            )
                            start, used = windows.get(item, (now, 0))
                            if now >= start + 14_400:
                                start, used = now, 0
                            require(used + q <= int(row.buy_limit_current), "Buy limit exceeded")
                            windows[item] = start, used + q
                            inventory[item] += q
                            book[item] += gross
                        else:
                            require(q <= inventory[item], "Oversold inventory")
                            allocated = book[item] * q // inventory[item]
                            realized += proceeds - allocated
                            inventory[item] -= q
                            book[item] -= allocated
                        cash += proceeds
                        require(cash >= 0, "Negative cash")
                        units[side] += q
                        cost_gp[side] += paid_bps
                        tick_gp[side] += ticks
                        notionals[side] += reference * q
                        residuals[side] += residual
                        totals["opportunities"] += 1
                require(cash == metrics["end_cash_gp"], "Ending cash mismatch")
                require(
                    sum(inventory.values()) == metrics["end_inventory_units"],
                    "Ending inventory mismatch",
                )
                require(realized == metrics["realized_gp"], "Realized P&L mismatch")
                expected_mark = expected_unpriceable = 0
                for item, q in inventory.items():
                    if not q:
                        continue
                    low = last_prices[item]
                    target = (
                        0
                        if pd.isna(low)
                        else (
                            int(low) * (10_000 - policy["slippage_bps"])
                            - policy["adverse_ticks"] * 10_000
                        )
                        * (10_000 - policy["terminal_haircut_bps"])
                    )
                    if target < 100_000_000:
                        expected_unpriceable += q
                        continue
                    low_gp, fraction = divmod(target, 100_000_000)
                    high_q = (q * fraction + 99_999_999) // 100_000_000
                    for p, n in ((low_gp, q - high_q), (low_gp + 1, high_q)):
                        unit_tax = (
                            0
                            if p <= tax["exempt_through_gp"] or item in (tax["exempt_item_ids"])
                            else min(p * tax["rate_bps"] // 10_000, tax["cap_gp"])
                        )
                        expected_mark += (p - unit_tax) * n
                require(expected_mark == metrics["end_inventory_mark_gp"], "Terminal mark mismatch")
                require(
                    expected_unpriceable == metrics["end_unpriceable_inventory_units"],
                    "Unpriceable inventory mismatch",
                )
                require(
                    cash + metrics["end_inventory_mark_gp"] - run["portfolio"]["initial_cash_gp"]
                    == metrics["net_gp"],
                    "Net GP mismatch",
                )
                require(
                    equity.active_slots.le(run["portfolio"]["offer_slots"]).all(),
                    "Offer slots exceeded",
                )
                require(equity.cash_gp.ge(0).all(), "Negative equity-curve cash")
                require(
                    (
                        equity.inventory_gross_mark_gp - equity.inventory_mark_tax_gp
                        == equity.inventory_mark_gp
                    ).all(),
                    "Mark tax mismatch",
                )
                for side in ("buy", "sell"):
                    require(units[side] == metrics[f"{side}_units_filled"], "Unit metric mismatch")
                    require(
                        cost_gp[side] == metrics[f"{side}_slippage_cost_gp"], "Cost metric mismatch"
                    )
                    require(
                        tick_gp[side] == metrics[f"{side}_tick_cost_gp"], "Tick metric mismatch"
                    )
                    require(
                        notionals[side] == metrics[f"{side}_reference_notional_gp"],
                        "Notional metric mismatch",
                    )
                    require(
                        residuals[side] / 10_000 == metrics[f"{side}_cost_rounding_gp"],
                        "Residual metric mismatch",
                    )
                if model == "no_trade":
                    require(
                        fills.empty and not orders and metrics["net_gp"] == 0,
                        "No-trade control traded",
                    )
                totals["scenarios"] += 1
                totals["fill_lots"] += len(fills)
                totals["no_buys"] += units["buy"] == 0
                totals["price_rejections"] += sum(o["event"] == "price_rejected" for o in orders)
    require(totals["scenarios"] == run["completed_scenarios"], "Incomplete audited scenarios")
    return totals


if __name__ == "__main__":
    summary = audit(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(summary, sort_keys=True))
    print(
        "PASS: positive integer prices, quantity/cash/inventory/realized P&L, per-lot tax, "
        "bps cost and residual, tick separation, capacity, buy limits, offer ceilings/slots, "
        "temporal causality, freshness, no-trade. Holdout NOT read."
    )
