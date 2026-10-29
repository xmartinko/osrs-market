"""Sealed mean-price diagnostics and offline, conditional high-alchemy cost caps.

No fill simulation, order placement, queue model or profit significance test.
"""

import argparse
import json
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import battery, costs
from .data import sha256
from .diagnostics import atomic_json
from .weekly_ingest import external_directory

REPO = Path(__file__).resolve().parents[3]
REGISTRATION = REPO / "ml/experiments/mechanical-edge-v1.json"


def registration():
    return json.loads(REGISTRATION.read_text())


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def cost_cap(*, item_id, item_cap_gp, rune_unit_cost_gp, owned_runes,
             buy_limit_remaining, cash_gp, casts_remaining, free_offer_slots,
             staff_already_paid):
    """A conditional contract, given truthful ownership/cost/limit inputs.

    rune_unit_cost_gp must bound the paid cost of EVERY rune used, including
    acquisition fees. Rune acquisition time is not free: recorded total active
    time must still be reconciled in the prospective battery. The planning time
    allowance is five minutes plus 3.6 seconds/cast. This is not an actual-fill
    certificate and cannot attest to skill, ownership, timing or evidence.
    """
    cfg = registration()
    values = locals().copy()
    for key in ("item_id", "item_cap_gp", "rune_unit_cost_gp", "owned_runes",
                "buy_limit_remaining", "cash_gp", "casts_remaining", "free_offer_slots"):
        integer(values[key], key, 1 if key in ("item_id", "item_cap_gp",
                                             "rune_unit_cost_gp") else 0)
    if type(staff_already_paid) is not bool:
        raise ValueError("staff_already_paid must be a boolean")
    if str(item_id) not in cfg["candidates"]:
        raise ValueError("Item is outside the fixed eligible candidate set")
    if cash_gp > cfg["cash_gp"] or free_offer_slots > 8:
        raise ValueError("Outside the registered single-account envelope")
    staff = 0 if staff_already_paid else cfg["staff_gp"]
    quantity = min(owned_runes, buy_limit_remaining, casts_remaining, cfg["daily_casts"],
                   max(0, cash_gp - staff) // item_cap_gp,
                   max(0, cfg["batch_budget_gp"] - staff) // (item_cap_gp + rune_unit_cost_gp))
    if not free_offer_slots:
        quantity = 0
    alch = cfg["candidates"][str(item_id)]
    # Rational seconds avoid floating point at strict break-even boundaries.
    seconds_numerator = quantity * 3600 + cfg["setup_seconds"] * cfg["casts_per_hour"]
    denominator = cfg["casts_per_hour"] * 3600
    time_charge = (seconds_numerator * cfg["active_value_gp_per_hour"] +
                   denominator - 1) // denominator if quantity else 0
    gross = quantity * (alch - item_cap_gp - rune_unit_cost_gp)
    surplus = gross - staff - time_charge if quantity else 0
    # For this quantity, the greatest integer price leaving STRICTLY positive surplus.
    maximum = (alch - rune_unit_cost_gp - (staff + time_charge) // quantity - 1
               if quantity else None)
    return dict(kind="conditional_cost_cap_only", item_id=item_id,
                high_alch_gp=alch, quantity=quantity, item_cap_gp=item_cap_gp,
                rune_unit_cost_gp=rune_unit_cost_gp, owned_runes_required=quantity,
                remaining_limit_required=quantity, staff_cost_gp=staff if quantity else 0,
                item_cash_required_gp=quantity * item_cap_gp + (staff if quantity else 0),
                total_input_and_staff_gp=quantity * (item_cap_gp + rune_unit_cost_gp) +
                (staff if quantity else 0),
                active_seconds_numerator=seconds_numerator if quantity else 0,
                active_seconds_denominator=cfg["casts_per_hour"],
                active_time_charge_gp=time_charge, cash_conversion_margin_gp=gross -
                (staff if quantity else 0), time_adjusted_surplus_gp=surplus,
                max_item_price_for_quantity_gp=max(0, maximum) if maximum is not None else None,
                clears_hurdle_if_filled=bool(quantity and surplus > 0),
                observed_profit_gp=None, own_fill_quantity=None,
                prerequisites=["eligible item and spell access verified by operator",
                               "owned rune costs bounded by supplied paid unit cost",
                               "item fills at or below cap within remaining allowance",
                               "actual total active time fits planning allowance",
                               "staff cost already paid or charged here exactly once"])


def load_development(root):
    """Check frozen provenance and date columns before reading market fields."""
    root = Path(root).resolve()
    cfg = registration()
    run_path = root / "strategy-battery-v1/run.json"
    run = json.loads(run_path.read_text())
    dev_path = REPO / "ml/runs/phase2-real-v1/run.json"
    dev = json.loads(dev_path.read_text())
    if (run["status"] != "complete" or run["holdout_read"] or
            run["holdout_start"] != cfg["holdout_start"] or dev["holdout_evaluated"] or
            dev["status"] != "development_complete" or
            dev["holdout_start"] != cfg["holdout_start"] or
            min(f["start"] for f in dev["folds"]) != cfg["start"] or
            max(f["end"] for f in dev["folds"]) != cfg["holdout_start"] or
            sha256(dev_path) != run["development_manifest_sha256"]):
        raise ValueError("Changed or unsealed development boundary")
    panel, mapping = root / "assembled-v3/daily.parquet", root / "items.parquet"
    if sha256(panel) != run["inputs"]["daily"] or sha256(mapping) != run["mapping_sha256"]:
        raise ValueError("Changed daily panel or item metadata")
    with duckdb.connect() as db:
        invalid = db.execute("""
            SELECT count(*) FROM read_parquet(?) WHERE available_at >= ? AND available_at < ?
            AND (timestamp IS NULL OR item_id IS NULL OR
                 available_at != timestamp + 86400 + 300)
        """, [str(panel), cfg["start"], cfg["holdout_start"]]).fetchone()[0]
    if invalid:
        raise ValueError("Invalid development availability")
    frame = battery.sealed_read(panel, cfg["holdout_start"], start=cfg["start"], columns=
                                "item_id,timestamp,available_at,avg_high_price,avg_low_price,"
                                "high_price_volume,low_price_volume")
    meta = pd.read_parquet(mapping, columns=["id", "name", "high_alch", "buy_limit"])
    return frame, meta, dict(source_run_sha256=sha256(run_path),
                            development_manifest_sha256=sha256(dev_path),
                            panel_sha256=sha256(panel), mapping_sha256=sha256(mapping))


def screen(frame, mapping):
    """Descriptive item-days only. Capacity is conditional on a chosen 1% share.

    No sum of capacities is an account allocation: rune volume, time and capital
    are shared. No row of means can become a cost_cap's owned-rune input.
    """
    cfg = registration()
    if (frame.empty or frame.available_at.isna().any() or
            not frame.available_at.between(cfg["start"], cfg["holdout_start"] - 1).all()):
        raise ValueError("Require nonempty development-only observations")
    if frame.duplicated(["item_id", "available_at"]).any() or mapping.id.duplicated().any():
        raise ValueError("Duplicate observation or item metadata")
    meta = mapping.set_index("id")
    for item, alch in cfg["candidates"].items():
        if int(item) not in meta.index or meta.loc[int(item), "high_alch"] != alch:
            raise ValueError("Fixed candidate alchemy metadata changed")
    if cfg["nature_rune_id"] not in meta.index:
        raise ValueError("Missing nature-rune metadata")
    fields = ["avg_high_price", "avg_low_price", "high_price_volume", "low_price_volume"]
    values = frame[fields].to_numpy(dtype=float, na_value=np.nan)
    valid = (np.isfinite(values).all(axis=1) & (values > 0).all(axis=1) &
             (values[:, 0] >= values[:, 1]))
    f = frame.loc[valid].copy()
    runes = f[f.item_id == cfg["nature_rune_id"]].set_index("available_at")
    f = f[f.item_id != cfg["nature_rune_id"]].merge(
        meta[["name", "high_alch", "buy_limit"]], left_on="item_id", right_index=True,
        validate="many_to_one")
    f = f[(f.high_alch > 0) & (f.buy_limit > 0)].copy()
    f = f.join(runes[fields].add_prefix("rune_"), on="available_at").dropna(
        subset=["rune_avg_high_price"])
    summaries, details = [], []
    for side in ("low", "high"):
        part = f.copy()
        item_price = part[f"avg_{side}_price"].astype("int64")
        rune_price = part.rune_avg_high_price.astype("int64")
        item_cost = (item_price * (10000 + cfg["adverse_bps"]) + 9999) // 10000
        rune_cost = (rune_price * (10000 + cfg["adverse_bps"]) + 9999) // 10000
        part["side"] = side
        part["raw_gap_gp"] = part.high_alch - item_price - rune_price
        part["item_ceiling_gp"], part["rune_ceiling_gp"] = item_cost, rune_cost
        part["gap_gp"] = part.high_alch - item_cost - rune_cost
        part["ge_tax_gp"] = 0  # Purchase and spell conversion incur no seller tax.
        limits = part.buy_limit.astype("int64")
        rune_limit = meta.loc[cfg["nature_rune_id"], "buy_limit"]
        if pd.isna(rune_limit) or rune_limit <= 0:
            raise ValueError("Unknown nature-rune buy limit")
        part["conditional_capacity"] = np.minimum.reduce([
            (part[f"{side}_price_volume"] * cfg["participation_bps"] // 10000)
            .to_numpy(dtype=np.int64),
            (part.rune_high_price_volume * cfg["participation_bps"] // 10000)
            .to_numpy(dtype=np.int64), limits.to_numpy(),
            np.full(len(part), int(rune_limit)),
            np.full(len(part), cfg["daily_casts"]),
            (cfg["batch_budget_gp"] // (item_cost + rune_cost)).to_numpy(dtype=np.int64),
        ])
        positive = part[part.gap_gp > 0]
        feasible = positive[positive.conditional_capacity > 0]
        summaries.append(dict(side=side, eligible_item_days=len(part),
                              raw_positive=int((part.raw_gap_gp > 0).sum()),
                              positive_item_days=len(positive),
                              days=int(positive.available_at.nunique()),
                              items=int(positive.item_id.nunique()),
                              median_gap_gp=float(positive.gap_gp.median()) if len(positive) else None,
                              reported_side_units=int(positive[f"{side}_price_volume"].sum()),
                              positive_capacity_rows=len(feasible),
                              median_conditional_capacity=float(feasible.conditional_capacity.median())
                              if len(feasible) else None))
        details.append(part)
    return pd.concat(details, ignore_index=True), pd.DataFrame(summaries)


def run_screen(root, output, acknowledged):
    # Reserve the attempt before any market observation is materialized.
    output = external_directory(output, acknowledged)
    run_path = output / "run.json"
    with run_path.open("x") as stream:
        json.dump(dict(status="reserved", holdout_read=False), stream)
    manifest = dict(status="running", holdout_read=False, kind=registration()["kind"],
                    holdout_start=registration()["holdout_start"],
                    registration_sha256=sha256(REGISTRATION),
                    code_sha256={p.name: sha256(p) for p in [Path(__file__),
                                 Path(battery.__file__), Path(costs.__file__)]},
                    observed_profit_gp=None, profit_tests_run=0)
    atomic_json(run_path, manifest)
    try:
        frame, meta, provenance = load_development(root)
        manifest.update(provenance, source_rows=len(frame))
        details, summary = screen(frame, meta)
        candidates = details[details.item_id.isin(map(int, registration()["candidates"]))]
        files = ["item-days.parquet", "summary.csv", "fixed-candidates.csv"]
        details.to_parquet(output / files[0], index=False)
        summary.to_csv(output / files[1], index=False)
        candidates.groupby(["item_id", "name", "side"]).agg(
            days=("available_at", "nunique"), positive_days=("gap_gp", lambda s: int((s > 0).sum())),
            median_gap_gp=("gap_gp", "median"),
            median_conditional_capacity=("conditional_capacity", "median"),
        ).to_csv(output / files[2])
        manifest.update(status="complete", outputs_sha256={f: sha256(output / f) for f in files})
        atomic_json(run_path, manifest)
    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        atomic_json(run_path, manifest)
        raise
    print(summary.to_string(index=False))
    print(f"PASS: {len(frame)} development rows; means only; profit tests=0; holdout_read=False")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="Offline JSON cost inputs; no market reads or orders")
    plan.add_argument("--inputs", type=Path, required=True)
    diagnostic = sub.add_parser("screen", help="Frozen development-only mean-price diagnostic")
    diagnostic.add_argument("--output", type=Path, required=True)
    diagnostic.add_argument("--acknowledge-private-research", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        print(json.dumps(cost_cap(**json.loads(args.inputs.read_text())), indent=2))
    else:
        run_screen(Path(os.environ["OSRS_DATA_DIR"]), args.output,
                   args.acknowledge_private_research)


if __name__ == "__main__":
    main()
