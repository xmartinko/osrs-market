"""Audit integrity fixtures; these are never used as market/profit evidence."""

import json
from pathlib import Path

import pandas as pd
import pytest
from test_battery import frame, mechanical_mapping

from osrs_ml.battery import DAY
from osrs_ml.battery_audit import audit, verify_provenance
from osrs_ml.data import sha256
from osrs_ml.mechanical import simulate_mechanical


@pytest.fixture
def provenance(tmp_path):
    registration = Path(__file__).parents[1] / "strategy-battery-v1.json"
    config = json.loads(registration.read_text())
    protocol = tmp_path / "protocol.md"
    protocol.write_text("frozen protocol\n")
    development = tmp_path / "development.json"
    development.write_text(json.dumps(dict(holdout_evaluated=False, status="development_complete",
                                          holdout_start=1785024300)))
    code = tmp_path / "battery.py"
    code.write_text("# frozen implementation\n")
    rows = [dict(id=s["id"], participation_bps=p) for s in config["hypotheses"]
            for p in config["participation_bps"]]
    pd.DataFrame(rows).to_csv(tmp_path / "results.csv", index=False)
    manifest = dict(status="complete", holdout_read=False, holdout_start=1785024300,
                    registration_sha256=sha256(registration), protocol_sha256=sha256(protocol),
                    development_manifest_sha256=sha256(development),
                    code_sha256={code.name: sha256(code)}, family_size=213,
                    results_sha256=sha256(tmp_path / "results.csv"),
                    completed=[f"{r['id']}_p{r['participation_bps']:04d}" for r in rows])
    (tmp_path / "run.json").write_text(json.dumps(manifest))
    return tmp_path, registration, protocol, tmp_path, development


def test_audit_requires_complete_unchanged_registration_code_and_results(provenance):
    manifest, config, expected, results = verify_provenance(*provenance)
    assert not manifest["holdout_read"]
    assert len(results) == len(expected) == config["family_size"] == 213


@pytest.mark.parametrize("field,value,message", [
    ("status", "running", "Incomplete/unsealed"),
    ("holdout_read", True, "Incomplete/unsealed"),
    ("family_size", 212, "family size"),
    ("holdout_start", 1785024301, "boundary changed"),
    ("registration_sha256", "wrong", "Registration changed"),
])
def test_audit_refuses_manifest_tampering(provenance, field, value, message):
    path = provenance[0] / "run.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(AssertionError, match=message):
        verify_provenance(*provenance)


@pytest.mark.parametrize("name,message", [
    ("protocol.md", "Protocol changed"),
    ("development.json", "Development manifest changed"),
    ("battery.py", "Executed code changed"),
    ("results.csv", "Results changed"),
])
def test_audit_refuses_changed_input_bytes(provenance, name, message):
    with (provenance[0] / name).open("a") as stream:
        stream.write("\nchanged\n")
    with pytest.raises(AssertionError, match=message):
        verify_provenance(*provenance)


def test_audit_refuses_duplicated_completion_even_if_set_is_complete(provenance):
    path = provenance[0] / "run.json"
    manifest = json.loads(path.read_text())
    manifest["completed"].append(manifest["completed"][0])
    path.write_text(json.dumps(manifest))
    with pytest.raises(AssertionError, match="duplicated family"):
        verify_provenance(*provenance)


def test_audit_refuses_missing_csv_row_even_with_matching_hash(provenance):
    output = provenance[0]
    csv_path = output / "results.csv"
    pd.read_csv(csv_path).iloc[:-1].to_csv(csv_path, index=False)
    manifest = json.loads((output / "run.json").read_text())
    manifest["results_sha256"] = sha256(csv_path)
    (output / "run.json").write_text(json.dumps(manifest))
    with pytest.raises(AssertionError, match="Results family mismatch"):
        verify_provenance(*provenance)


@pytest.fixture
def account_audit(tmp_path, monkeypatch):
    """Exercise the ledger audit separately from the provenance gate tested above."""
    config = json.loads((Path(__file__).parents[1] / "strategy-battery-v1.json").read_text())
    output, root = tmp_path / "output", tmp_path / "source"
    output.mkdir()
    (root / "assembled-v3").mkdir(parents=True)
    mapping = mechanical_mapping()
    mapping.to_parquet(root / "items.parquet")
    observations = frame(steps=24, items=(1, 561))
    source = root / "assembled-v3/daily.parquet"
    observations.to_parquet(source)
    result, _ = simulate_mechanical(observations, mapping, "alchemy", 100)
    manifest = dict(mapping_sha256=sha256(root / "items.parquet"), holdout_start=30 * DAY,
                    inputs={"daily": sha256(source)})
    expected, rows = set(), []
    for spec in config["hypotheses"]:
        for share in config["participation_bps"]:
            key = f"{spec['id']}_p{share:04d}"
            expected.add(key)
            directory = output / key
            directory.mkdir()
            row = dict(id=spec["id"], participation_bps=share, p_raw=1., p_adjusted=1.,
                       survives=False, net_gp=None, trades=None, status="unidentified")
            if key == "alchemy_1d_p0100":
                row.update(net_gp=result.metrics["net_gp"], trades=0, status="inconclusive")
                for name, records in [("equity", result.equity), ("fills", result.fills),
                                      ("orders", result.orders)]:
                    pd.DataFrame(records).to_parquet(directory / f"{name}.parquet")
                (directory / "metrics.json").write_text(json.dumps(result.metrics))
                equity = pd.Series([r["equity_gp"] for r in result.equity])
                increments = equity.diff().fillna(equity.iloc[0] - 10_000_000)
                pd.DataFrame(dict(increment=increments)).to_parquet(directory / "increments.parquet")
            rows.append(row)
            (directory / "summary.json").write_text(json.dumps(dict(row=row, detail={})))
    results = pd.DataFrame(rows).set_index(["id", "participation_bps"])
    monkeypatch.setattr("osrs_ml.battery_audit.verify_provenance",
                        lambda *args: (manifest, config, expected, results))
    return output, root, output / "alchemy_1d_p0100"


def test_independent_ledger_reconstructs_conversion_cash_inventory_and_marks(account_audit):
    output, root, _ = account_audit
    counts = audit(output, root)
    assert counts["scenarios"] == 213 and counts["unavailable"] == 212
    assert counts["fills"] > 0 and counts["productions"] > 0


def test_ledger_audit_detects_changed_cash(account_audit):
    output, root, directory = account_audit
    path = directory / "equity.parquet"
    curve = pd.read_parquet(path)
    curve.loc[curve.index[-1], "cash_gp"] += 1
    curve.to_parquet(path)
    with pytest.raises(AssertionError, match="Final cash mismatch"):
        audit(output, root)


def test_ledger_audit_detects_consuming_unowned_input(account_audit):
    output, root, directory = account_audit
    path = directory / "orders.parquet"
    orders = pd.read_parquet(path)
    index = orders.index[orders.event.eq("production")][0]
    orders.loc[index, "quantity"] = 1000000
    orders.to_parquet(path)
    with pytest.raises(AssertionError, match="Consumed unowned input"):
        audit(output, root)


def test_ledger_audit_checks_fill_prices_against_observed_source(account_audit):
    output, root, directory = account_audit
    path = directory / "fills.parquet"
    fills = pd.read_parquet(path)
    fills.loc[0, "reference_price_gp"] += 1
    fills.to_parquet(path)
    with pytest.raises(AssertionError, match="Source reference mismatch"):
        audit(output, root)


def test_ledger_audit_checks_terminal_mark(account_audit):
    output, root, directory = account_audit
    path = directory / "equity.parquet"
    curve = pd.read_parquet(path)
    curve.loc[curve.index[-1], "inventory_mark_gp"] += 1
    curve.to_parquet(path)
    with pytest.raises(AssertionError, match="Final mark mismatch"):
        audit(output, root)
