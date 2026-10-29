"""Deterministic intake/accounting fixtures only; never execution or profit evidence."""

import json
import sqlite3
from copy import deepcopy

import pytest

from osrs_ml.data import sha256
from osrs_ml.processing_calibration import DAY, import_events, initialize, report


@pytest.fixture
def study(tmp_path):
    path = tmp_path / "study" / "ledger.sqlite"
    manifest = initialize(path, now=100 * DAY + 10)
    evidence = path.parent / "operator.txt"
    evidence.write_text("ACCOUNTING FIXTURE ONLY; not an actual order export\n")
    start = manifest["start"]

    def event(identity, kind, data, offset):
        return dict(id=identity, kind=kind, at=start + offset, source="operator_actual",
                    evidence=evidence.name, evidence_sha256=sha256(evidence), data=data)

    decision = event("d", "decision", dict(batch_id="b", output_id=859, quantity=10,
                                          input_ceilings={"70": 100, "1777": 20},
                                          buy_limits={"70": 10000, "1777": 10000},
                                          output_reference_gp=150), 10)
    events = [decision]
    for n, item, price in [(1, 70, 100), (2, 1777, 20)]:
        events.extend([
            event(f"s{n}", "submit", dict(order_id=f"o{n}", batch_id="b", item_id=item,
                                         side="buy", quantity=10, price_gp=price), n * 100),
            event(f"f{n}", "fill", dict(order_id=f"o{n}", quantity=10, price_gp=price,
                                       tax_gp=0), n * 100 + 10),
            event(f"c{n}", "close", dict(order_id=f"o{n}", reason="filled"), n * 100 + 20),
        ])
    events.extend([
        event("p", "produce", dict(batch_id="b", quantity=6), 300),
        event("so", "submit", dict(order_id="out", batch_id="b", item_id=859, side="sell",
                                   quantity=6, price_gp=150), 400),
        event("fo", "fill", dict(order_id="out", quantity=6, price_gp=150, tax_gp=18), 410),
        event("co", "close", dict(order_id="out", reason="filled"), 420),
        event("check", "session", dict(active_seconds=600, cash_gp=9999682,
                                       inventory={"70": 4, "1777": 4}), 500),
    ])
    return path, manifest, event, events


def test_empty_study_is_missing_data_and_has_no_profit_inference(study):
    path, manifest, _, _ = study
    result = report(path, now=manifest["start"] - 1)
    assert result["status"] == "awaiting_actual_records"
    assert result["event_count"] == result["completed_batches"] == 0
    assert result["expected_profit_gp"] is None
    assert result["p_adjusted"] is None
    assert result["historical_battery_p_adjusted"] == 1
    assert result["holdout_read"] is False
    assert "window_not_ended" in result["readiness_failures"]


def test_partial_production_reconciles_cash_book_cost_actual_tax_and_capital_time(study):
    path, m, _, events = study
    import_events(path, events[:1], now=m["start"] + 10)
    import_events(path, events[1:], now=m["start"] + 600)
    r = report(path, now=m["start"] + 600)
    assert r["cash_change_gp"] == -318
    assert r["realized_gp"] == 162  # actual tax is 18, not imputed by the ledger
    assert r["remaining_book_gp"] == 480
    assert r["cash_change_gp"] == r["realized_gp"] - r["remaining_book_gp"]
    assert r["inventory"] == {"70": 4, "1777": 4}
    assert r["completed_batches"] == 1
    assert r["tax_gp"] == 18
    assert r["peak_open_slots"] == 1
    assert r["peak_book_gp"] == 1200
    assert r["book_gp_seconds"] == 1000 * 100 + 1200 * 200 + 480 * 190
    assert r["orders"][0]["filled_units"] == 10
    assert r["orders"][0]["first_fill_wait_seconds"] == 10
    assert r["deviations"] == []
    assert not r["ready"]


def test_import_is_atomic_and_duplicate_ids_are_not_silently_ignored(study):
    path, m, _, events = study
    bad = deepcopy(events[:4])
    bad[-1]["id"] = bad[0]["id"]
    with pytest.raises(ValueError, match="Duplicate"):
        import_events(path, bad, now=m["start"] + 600)
    assert report(path, now=m["start"] + 600)["event_count"] == 0
    import_events(path, events[:1], now=m["start"] + 600)
    with pytest.raises(ValueError, match="Duplicate"):
        import_events(path, events[:1], now=m["start"] + 600)


@pytest.mark.parametrize("change,message", [
    (lambda e, m: e[0].update(source="paper"), "operator_actual"),
    (lambda e, m: e[0].update(at=m["start"] - 1), "window"),
    (lambda e, m: e[0].update(at=m["start"] + 9000), "Future"),
    (lambda e, m: e[0]["data"].update(quantity=True), "integer"),
    (lambda e, m: e[0].update(evidence="../escape.txt"), "Evidence"),
    (lambda e, m: e[0].update(evidence="ledger.sqlite"), "Evidence"),
    (lambda e, m: e[2]["data"].update(quantity=11), "overfill"),
    (lambda e, m: e[2]["data"].update(price_gp=101), "limit"),
    (lambda e, m: e[2]["data"].update(tax_gp=1), "tax"),
    (lambda e, m: e[7]["data"].update(quantity=11), "Unowned"),
    (lambda e, m: e[-1]["data"].update(cash_gp=1), "Cash checkpoint"),
    (lambda e, m: e[-1]["data"].update(inventory={}), "Inventory checkpoint"),
])
def test_invalid_evidence_timing_prices_inventory_and_checkpoints_rejected(study, change, message):
    path, m, _, events = study
    change(events, m)
    with pytest.raises(ValueError, match=message):
        import_events(path, events, now=m["start"] + 600)
    assert report(path, now=m["start"] + 600)["event_count"] == 0


def test_reject_and_cancel_keep_failed_attempts_and_unmatched_inputs(study):
    path, m, ev, events = study
    records = events[:2] + [ev("rejected", "reject", dict(order_id="o1", reason="failed"), 105)]
    records += [ev("s2", "submit", dict(order_id="o2", batch_id="b", item_id=1777,
                                        side="buy", quantity=10, price_gp=20), 200)]
    records += [ev("f2", "fill", dict(order_id="o2", quantity=2, price_gp=20, tax_gp=0), 210),
                ev("x2", "cancel", dict(order_id="o2", reason="timeout"), 220)]
    import_events(path, records, now=m["start"] + 600)
    r = report(path, now=m["start"] + 600)
    assert r["rejections"] == r["cancellations"] == 1
    assert r["inventory"] == {"1777": 2}
    assert r["remaining_book_gp"] == 40 and r["completed_batches"] == 0
    assert r["orders"][0]["filled_units"] == 0


def test_envelope_breaches_are_retained_and_block_readiness(study):
    path, m, _, events = study
    events[0]["data"]["buy_limits"]["70"] = 5
    events[-1]["data"]["active_seconds"] = 3601
    import_events(path, events, now=m["start"] + 600)
    r = report(path, now=m["end"])
    assert r["event_count"] == len(events)
    assert {d["reason"] for d in r["deviations"]} >= {"buy_limit", "active_time"}
    assert "protocol_deviations" in r["readiness_failures"]
    assert r["realized_gp"] == 162


def test_evidence_revalidated_and_sqlite_records_are_immutable(study):
    path, m, _, events = study
    import_events(path, events, now=m["start"] + 600)
    with sqlite3.connect(path) as db:
        for statement in ["DELETE FROM events", "UPDATE events SET at=0",
                          "DELETE FROM manifest", "UPDATE manifest SET payload='{}'"]:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute(statement)
    (path.parent / "operator.txt").write_text("Changed evidence")
    with pytest.raises(ValueError, match="Evidence hash"):
        report(path, now=m["start"] + 600)


def test_manifest_drift_existing_init_and_nonexistent_report_are_rejected(study, tmp_path):
    path, m, _, _ = study
    with pytest.raises(FileExistsError):
        initialize(path, now=m["start"])
    with pytest.raises(FileNotFoundError):
        report(tmp_path / "absent.sqlite", now=m["start"])
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER manifest_no_update")
        content = json.loads(db.execute("SELECT payload FROM manifest").fetchone()[0])
        content["code_sha256"] = "changed"
        db.execute("UPDATE manifest SET payload=?", [json.dumps(content)])
    with pytest.raises(ValueError, match="implementation"):
        report(path, now=m["start"])


def test_events_cannot_follow_a_daily_session_or_reuse_closed_order(study):
    path, m, ev, events = study
    for tail in [ev("late", "fill", dict(order_id="out", quantity=1, price_gp=150,
                                        tax_gp=3), 600),
                 ev("late", "produce", dict(batch_id="b", quantity=1), 600)]:
        with pytest.raises(ValueError, match="session|closed"):
            import_events(path, events + [tail], now=m["start"] + 700)


def test_closed_orders_unowned_output_and_nonchronological_import_rejected(study):
    path, m, ev, events = study
    with pytest.raises(ValueError, match="chronological"):
        import_events(path, events[:4] + [ev("back", "produce",
                      dict(batch_id="b", quantity=1), 105)], now=m["start"] + 600)
    bad = events[:4] + [ev("again", "fill", dict(order_id="o1", quantity=1,
                                               price_gp=100, tax_gp=0), 190)]
    with pytest.raises(ValueError, match="closed"):
        import_events(path, bad, now=m["start"] + 600)
    bad = events[:7] + events[8:11]
    with pytest.raises(ValueError, match="Unowned"):
        import_events(path, bad, now=m["start"] + 600)


def test_late_decision_is_preserved_but_cannot_be_used_as_preregistered_execution(study):
    path, m, _, events = study
    r = import_events(path, events, now=m["start"] + 600)
    assert "decision_recorded_after_submission" in {d["reason"] for d in r["deviations"]}
    assert r["event_count"] == len(events) and r["realized_gp"] == 162


def test_no_activity_is_inconclusive_even_with_all_daily_checks(study):
    path, m, ev, _ = study
    records = []
    for day in range(56):
        records.extend([
            ev(f"d{day}", "decision", dict(batch_id=f"b{day}", output_id=859, quantity=0,
                                          input_ceilings={}, buy_limits={}, output_reference_gp=0,
                                          reason="no candidate"), day * DAY + 10),
            ev(f"c{day}", "session", dict(active_seconds=60, cash_gp=10000000,
                                         inventory={}), day * DAY + 100),
        ])
    r = import_events(path, records, now=m["end"])
    assert r["decisions"] == r["sessions"] == 56
    assert r["status"] == "inconclusive"
    assert r["readiness_failures"] == ["fewer_than_ten_completed_batches",
                                       "missing_buy_or_sale_activity"]


def test_complete_sample_can_qualify_without_claiming_expected_profit(study):
    path, m, ev, template = study
    cash = 10000000
    for day in range(56):
        offset = day * DAY
        if day < 10:
            records = deepcopy(template[:-1])
            for e in records:
                e["at"] += offset
                e["id"] += str(day)
                for key in ("order_id", "batch_id"):
                    if key in e["data"]:
                        e["data"][key] += str(day)
            records[7]["data"]["quantity"] = 10
            records[8]["data"]["quantity"] = 10
            records[9]["data"].update(quantity=10, tax_gp=30)
            cash += 270
            import_events(path, records[:1], now=m["start"] + offset + 10)
            import_events(path, records[1:], now=m["start"] + offset + 500)
        else:
            import_events(path, [ev(f"d{day}", "decision", dict(batch_id=f"b{day}", output_id=859,
                          quantity=0, input_ceilings={}, buy_limits={}, output_reference_gp=0,
                          reason="no candidate"), offset + 10)], now=m["start"] + offset + 10)
        import_events(path, [ev(f"check{day}", "session", dict(active_seconds=600,
                      cash_gp=cash, inventory={}), offset + 600)], now=m["start"] + offset + 600)
    r = report(path, now=m["end"])
    assert r["ready"] and r["completed_batches"] == 10
    assert r["status"] == "calibration_complete"
    assert r["realized_gp"] == 2700 and r["remaining_book_gp"] == 0
    assert r["p_adjusted"] is None and r["expected_profit_gp"] is None


def test_zero_active_time_with_production_is_a_retained_deviation(study):
    path, m, _, records = study
    records[-1]["data"]["active_seconds"] = 0
    r = import_events(path, records, now=m["start"] + 600)
    assert "missing_active_time" in {d["reason"] for d in r["deviations"]}
    assert r["realized_gp_per_recorded_active_hour"] is None


def test_evidence_symlink_escape_and_tampered_event_chain_rejected(study, tmp_path):
    path, m, _, events = study
    outside = tmp_path / "outside.txt"
    outside.write_text("fixture only")
    (path.parent / "escape.txt").symlink_to(outside)
    changed = deepcopy(events[:1])
    changed[0].update(evidence="escape.txt", evidence_sha256=sha256(outside))
    with pytest.raises(ValueError, match="Evidence"):
        import_events(path, changed, now=m["start"] + 600)
    import_events(path, events[:1], now=m["start"] + 600)
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET at=at+1")
    with pytest.raises(ValueError, match="chain"):
        report(path, now=m["start"] + 600)


def test_no_implicit_ledger_creation_and_clock_cannot_move_backwards(study):
    path, m, _, events = study
    import_events(path, events[:1], now=m["start"] + 600)
    with pytest.raises(ValueError, match="before previous ingestion"):
        report(path, now=m["start"] + 500)
    with pytest.raises(ValueError, match="before previous ingestion"):
        import_events(path, [], now=m["start"] + 500)
    with pytest.raises(FileNotFoundError):
        import_events(path.parent / "missing.sqlite", [], now=m["end"])
