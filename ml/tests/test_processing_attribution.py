"""Deterministic accounting fixtures only; never training or profit evidence."""

from copy import deepcopy

import pandas as pd
import pytest
from test_battery import frame, mechanical_mapping

from osrs_ml.battery import DAY
from osrs_ml.mechanical import simulate_mechanical
from osrs_ml.processing_attribution import (
    attribute,
    read_development,
    verify_artifacts,
)


@pytest.fixture
def account():
    observations = frame(steps=36, items=(70, 1777, 859),
                         prices={(859, t): 400 for t in range(36)})
    observations["avg_low_price"] = observations.avg_high_price - 1
    # Force partial output sales across multiple buckets, and unmatched inputs.
    observations.loc[observations.item_id == 859, "low_price_volume"] = 10000
    observations.loc[(observations.item_id == 1777) &
                     (observations.timestamp < 3 * DAY), "high_price_volume"] = 0
    result, completed = simulate_mechanical(observations, mechanical_mapping(), "processing", 100)
    return dict(fills=pd.DataFrame(result.fills), orders=pd.DataFrame(result.orders),
                curve=pd.DataFrame(result.equity), observations=observations,
                metrics=result.metrics, share=100, cutoff=40 * DAY), completed


def test_attribution_reconciles_partial_lots_batches_and_every_equity_timestamp(account):
    inputs, completed = account
    summary, batches, submissions, inventory = attribute(**inputs)
    assert summary["fully_sold_batches"] == completed > 0
    assert summary["curve_rows_checked"] == len(inputs["curve"])
    assert summary["realized_gp"] == inputs["metrics"]["realized_gp"]
    assert summary["realized_gp"] - summary["remaining_book_gp"] == summary["cash_pnl_gp"]
    assert summary["realized_gp"] + summary["unrealized_gp"] == summary["net_gp"]
    assert sum(b["realized_gp"] for b in batches) == summary["realized_gp"]
    for b in batches:
        assert (b["decision_spread_gp"] + b["input_movement_gp"] + b["output_movement_gp"]
                == b["realized_gp"])
        assert b["first_sale_at"] > b["produced_at"]
    assert len(submissions) >= len(batches)
    assert sum(i["mark_gp"] for i in inventory) == summary["terminal_mark_gp"]
    assert summary["active_hours"] == pytest.approx(inputs["metrics"]["active_hours"])


def test_cash_change_is_not_realized_profit_when_inputs_remain(account):
    inputs, _ = account
    summary, _, _, inventory = attribute(**inputs)
    assert inventory and summary["remaining_book_gp"] > 0
    assert summary["realized_gp"] > summary["cash_pnl_gp"]
    assert summary["unrealized_gp"] == summary["terminal_mark_gp"] - summary["remaining_book_gp"]


@pytest.mark.parametrize("target,column,message", [
    ("curve", "cash_gp", "Cash path"),
    ("curve", "inventory_mark_gp", "Mark path"),
    ("curve", "equity_gp", "Equity path"),
    ("fills", "reference_price_gp", "Source reference"),
])
def test_rejects_interior_path_or_reference_corruption(account, target, column, message):
    inputs, _ = account
    inputs = deepcopy(inputs)
    inputs[target].loc[1, column] += 1
    with pytest.raises(AssertionError, match=message):
        attribute(**inputs)


def test_rejects_duplicate_lots_and_unowned_production(account):
    inputs, _ = account
    changed = deepcopy(inputs)
    changed["fills"] = pd.concat([inputs["fills"], inputs["fills"].iloc[[0]]], ignore_index=True)
    with pytest.raises(AssertionError, match="Duplicate fill"):
        attribute(**changed)
    changed = deepcopy(inputs)
    index = changed["orders"].index[changed["orders"].event.eq("production")][0]
    changed["orders"].loc[index, "quantity"] = 100000
    with pytest.raises(AssertionError, match="Production quantity|Unowned input"):
        attribute(**changed)


def test_rejects_sealed_observations_and_same_timestamp_production_inputs(account):
    inputs, _ = account
    changed = deepcopy(inputs)
    changed["cutoff"] = int(inputs["observations"].available_at.max())
    with pytest.raises(AssertionError, match="Sealed"):
        attribute(**changed)
    changed = deepcopy(inputs)
    index = changed["orders"].index[changed["orders"].event.eq("production")][0]
    changed["orders"].loc[index, "timestamp"] = int(inputs["fills"].timestamp.min())
    with pytest.raises(AssertionError, match="Unowned input|Input timing"):
        attribute(**changed)


def test_source_reader_projects_only_registered_items_and_development(tmp_path):
    observations = frame(steps=10, items=(70, 1777, 859, 999))
    path = tmp_path / "daily.parquet"
    observations.to_parquet(path)
    result = read_development(path, 2 * DAY, 8 * DAY)
    assert set(result.item_id) == {70, 1777, 859}
    assert (result.available_at >= 2 * DAY).all()
    assert (result.available_at < 8 * DAY).all()


def test_artifact_integrity_gate_detects_drift_before_loading(tmp_path):
    import json

    from osrs_ml.data import sha256

    names = ("fills.parquet", "orders.parquet", "equity.parquet", "metrics.json", "summary.json")
    directory = tmp_path / "processing_1d_p0100"
    directory.mkdir()
    known = {}
    for name in names:
        p = directory / name
        p.write_bytes(b"fixture bytes only")
        known[f"{directory.name}/{name}"] = sha256(p)
    (tmp_path / "audited-artifacts-sha256.json").write_text(json.dumps(known))
    verify_artifacts(tmp_path, [100])
    (directory / names[0]).write_bytes(b"changed")
    with pytest.raises(AssertionError, match="Artifact changed"):
        verify_artifacts(tmp_path, [100])
