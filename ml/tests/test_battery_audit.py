"""Audit integrity fixtures; these are never used as market/profit evidence."""

import json
from pathlib import Path

import pandas as pd
import pytest
from osrs_ml.battery_audit import verify_provenance
from osrs_ml.data import sha256


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
