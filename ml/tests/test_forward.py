import sqlite3

import pytest
from osrs_ml.collector import archive_observations, publish
from osrs_ml.forward import connect, issue, paper, settle


def bucket(t, high=100, low=95):
    return {
        "timestamp": t,
        "data": {
            "1": {
                "avgHighPrice": high,
                "avgLowPrice": low,
                "highPriceVolume": 1000,
                "lowPriceVolume": 1000,
            }
        },
    }


def test_archive_idempotence_resolution_nulls_and_first_fetch(tmp_path):
    mapping = [{"id": 1, "limit": 100}]
    a = publish(tmp_path, bucket(0), mapping, 400)
    assert a["status"] == "archived"
    assert publish(tmp_path, bucket(0), mapping, 450)["status"] == "already_archived"
    publish(tmp_path, bucket(0, high=101), mapping, 460)  # immutable API revision
    publish(tmp_path, bucket(300, high=None), mapping, 700)
    f = archive_observations(tmp_path)
    assert len(f) == 2
    assert f.iloc[0].avg_high_price == 100
    assert f.avg_high_price.isna().sum() == 1
    assert f.iloc[0].available_at == 400
    with pytest.raises(ValueError, match="completed"):
        publish(tmp_path, bucket(900), mapping, 1000)


def test_ledger_prospective_append_only_idempotent_and_paper(tmp_path):
    root = tmp_path / "archive"
    mapping = [{"id": 1, "limit": 100}]
    publish(root, bucket(0), mapping, 400)
    f = archive_observations(root)
    with connect(tmp_path / "ledger.sqlite") as db:
        assert issue(db, f, now=400, horizon=300) == 4
        assert issue(db, f, now=450, horizon=300) == 0
        assert settle(db, f, now=450) == 0
        assert paper(db, f, now=450) == []
        with pytest.raises(ValueError, match="Future context"):
            issue(db, f, now=399, horizon=300)
        for t in range(300, 3301, 300):
            publish(root, bucket(t), mapping, t + 400)
        f = archive_observations(root)
        assert settle(db, f, now=4000) == 4
        assert settle(db, f, now=4000) == 0
        results = paper(db, f, now=4000)
        assert len(results) == 12
        assert next(r for r in results if r["model"].startswith("no_trade@"))["net_gp"] == 0
        for r in results:
            assert r["net_gp"] == r["end_cash_gp"] + r["end_inventory_mark_gp"] - 10000000
        count = db.execute("select count(*) from paper_runs").fetchone()[0]
        paper(db, f, now=4000)
        assert db.execute("select count(*) from paper_runs").fetchone()[0] == count
        outcome = db.execute("select * from outcomes limit 1").fetchone()
        assert outcome["observation_time"] >= 700
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("delete from predictions")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute('update outcomes set status="changed"')
