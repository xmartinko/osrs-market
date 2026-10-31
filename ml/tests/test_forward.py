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


@pytest.mark.parametrize("legacy", [False, True])
def test_daily_ledger_categorical_index_follows_frozen_frame(tmp_path, monkeypatch, legacy):
    import json

    import catboost
    import numpy as np
    import pandas as pd

    from osrs_ml.forward import daily_predictions
    from osrs_ml.research import FEATURES, matrix

    # The deployed model predates removal of the history_rows age proxy.
    features = list(FEATURES)
    if legacy:
        features.insert(features.index("high_missing"), "history_rows")
    frame = pd.DataFrame({name: np.arange(20, dtype=float) for name in features})
    frame["item"] = [str(i % 3) for i in range(len(frame))]
    x = matrix(frame, features)
    model = catboost.CatBoostRegressor(iterations=2, depth=2, verbose=False,
                                       allow_writing_files=False, thread_count=1)
    model.fit(x, np.arange(len(x)), cat_features=["item"])
    model.save_model(str(tmp_path / "net_return.cbm"))
    (tmp_path / "training.json").write_text(json.dumps({"features": features}))
    expected = model.predict(x)
    pool = catboost.Pool
    seen = []

    def checked_pool(data, *, cat_features):
        assert cat_features == [data.columns.get_loc("item")]
        assert data.columns[cat_features[0]] == "item"
        assert cat_features == model.get_cat_feature_indices()
        assert list(data.columns) == features
        seen.append(cat_features)
        return pool(data, cat_features=cat_features)

    monkeypatch.setattr(catboost, "Pool", checked_pool)
    np.testing.assert_allclose(daily_predictions(frame, tmp_path), expected)
    assert seen == [[features.index("item")]]


def replay_fixture(root):
    mapping = [{"id": 1, "limit": 100}]
    for t in range(0, 3601, 300):
        publish(root, bucket(t, high=100 if t != 3000 else None,
                             low=95 if t != 2100 else None), mapping, t + 400)
    # Later revisions cannot replace the first observed prices or duplicate volume.
    publish(root, bucket(0, high=999), mapping, 5000)


def ledger_contents(db):
    return {table: [tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY 1')]
            for table in ['predictions', 'outcomes', 'paper_runs', 'paper_fills']}


def seed_predictions(db, root):
    f = archive_observations(root)
    for t in [0, 300, 600]:
        # Exercise synthetic decisions, with zero volume and adjusted freshness.
        issue(db, f[f.fetched_at <= t + 410], now=t + 410, horizon=300)
    issue(db, f[f.fetched_at <= 1610], now=1610, horizon=300,
          model_scores={(1, 1200): 5.0}, model_hash='second-frozen-model')
    return f


@pytest.mark.parametrize('custom_execution', [False, True])
def test_disk_replay_exactly_matches_full_frame_without_skipping_rows(tmp_path, custom_execution):
    from osrs_ml.execution import PRESETS
    from osrs_ml.forward import canonical, digest, paper_streamed, row_json
    from osrs_ml.forward_store import ArchiveStore

    root = tmp_path / 'archive'
    replay_fixture(root)
    execution = ({name: {'participation_bps': 500, 'queue_fill_bps': 3000,
                        'passive_prices': False} for name in PRESETS} if custom_execution else None)
    with connect(tmp_path / 'reference.sqlite') as reference:
        f = seed_predictions(reference, root)
        settle(reference, f, now=5000)
        expected = paper(reference, f, now=5000, execution=execution)
        contents = ledger_contents(reference)
    with connect(tmp_path / 'streamed.sqlite') as db:
        seed_predictions(db, root)
        store = ArchiveStore(db, tmp_path / 'cache.sqlite')
        store.refresh(root, 300)
        assert store.archive_hash() == digest([
            row_json(r) for r in f.sort_values(['item_id', 'timestamp']).to_dict('records')])
        assert db.execute('SELECT count(*) FROM archive_cache.observations').fetchone()[0] == len(f)
        store.settle(5000)
        actual = paper_streamed(db, store, now=5000, execution=execution)
        def ordered(rows):
            return sorted(rows, key=lambda r: (r["model"], r["preset"]))
        assert canonical(ordered(actual)) == canonical(ordered(expected))
        assert ledger_contents(db) == contents
        store.refresh(root, 300)
        assert store.settle(5000) == 0
        assert canonical(ordered(paper_streamed(db, store, now=5000, execution=execution))) == canonical(ordered(expected))
        assert ledger_contents(db) == contents
        # The bounded issue window preserves exact nullable integer contexts.
        assert store.latest(4000, 300).iloc[0].avg_high_price == 100


def test_killed_paper_replay_rolls_back_run_and_fills_and_resumes(tmp_path):
    import signal
    import subprocess
    import sys

    from osrs_ml.forward import canonical, paper_streamed
    from osrs_ml.forward_store import ArchiveStore

    root, ledger, cache = tmp_path / 'archive', tmp_path / 'ledger.sqlite', tmp_path / 'cache.sqlite'
    replay_fixture(root)
    with connect(ledger) as db:
        seed_predictions(db, root)
        store = ArchiveStore(db, cache)
        store.refresh(root, 300)
        original_hash = store.archive_hash()

    child = subprocess.run([sys.executable, '-c', """
import os
import signal
import sys
from pathlib import Path
from osrs_ml.forward import connect, paper_streamed
from osrs_ml.forward_store import ArchiveStore
with connect(Path(sys.argv[1])) as db:
    store = ArchiveStore(db, Path(sys.argv[2]))
    db.create_function('kill_run', 0, lambda: os.kill(os.getpid(), signal.SIGKILL))
    db.execute('CREATE TEMP TRIGGER interrupt_fill BEFORE INSERT ON paper_fills '
               'BEGIN SELECT kill_run(); END')
    paper_streamed(db, store, now=5000)
""", str(ledger), str(cache)], capture_output=True, timeout=20)
    assert child.returncode == -signal.SIGKILL, child.stderr.decode()
    with connect(ledger) as db:
        # Any completed no-fill runs may survive. The interrupted fill's run cannot.
        assert db.execute('SELECT count(*) FROM paper_fills').fetchone()[0] == 0
        partial = db.execute('SELECT model FROM paper_runs').fetchall()
        assert all(not r[0].startswith('raw_spread@') for r in partial)
        store = ArchiveStore(db, cache)
        store.refresh(root, 300)
        assert store.archive_hash() == original_hash
        resumed = paper_streamed(db, store, now=5000)
        assert db.execute('SELECT count(*) FROM paper_fills').fetchone()[0] > 0
        contents = ledger_contents(db)
        assert canonical(paper_streamed(db, store, now=5000)) == canonical(resumed)
        assert ledger_contents(db) == contents


def test_archive_import_checkpoint_is_atomic_and_checksums_are_rechecked(tmp_path, monkeypatch):
    import osrs_ml.forward_store as module

    root = tmp_path / 'archive'
    publish(root, bucket(0), [{"id": 1, "limit": 100}], 400)
    parquet = module.pq.ParquetFile

    class InterruptedParquet:
        def __init__(self, path):
            self.file = parquet(path)

        def iter_batches(self, *, batch_size):
            assert batch_size == 4096
            yield from self.file.iter_batches(batch_size=batch_size)
            raise RuntimeError('interrupted before checkpoint')

    with connect(tmp_path / 'ledger.sqlite') as db:
        store = module.ArchiveStore(db, tmp_path / 'cache.sqlite')
        monkeypatch.setattr(module.pq, 'ParquetFile', InterruptedParquet)
        with pytest.raises(RuntimeError, match='interrupted'):
            store.refresh(root, 300)
        for table in ['snapshots', 'observations']:
            assert db.execute(f'SELECT count(*) FROM archive_cache.{table}').fetchone()[0] == 0
        monkeypatch.setattr(module.pq, 'ParquetFile', parquet)
        store.refresh(root, 300)
        assert len(store.latest(410, 300)) == 1
        path = next(root.glob('300s/*/observations.parquet'))
        path.write_bytes(path.read_bytes() + b'corrupt')
        with pytest.raises(ValueError, match='checksum'):
            store.refresh(root, 300)


def test_forward_issues_after_index_build_with_exact_integer_context(tmp_path, monkeypatch):
    import json

    import osrs_ml.forward as module
    from osrs_ml.forward_store import ArchiveStore

    root, ledger = tmp_path / 'archive', tmp_path / 'ledger.sqlite'
    publish(root, bucket(0), [{"id": 1, "limit": 100}], 400)
    clock = [410]
    monkeypatch.setattr(module.time, 'time', lambda: clock[0])
    refresh = ArchiveStore.refresh

    def delayed_refresh(store, archive, resolution):
        refresh(store, archive, resolution)
        clock[0] = 650

    monkeypatch.setattr(ArchiveStore, 'refresh', delayed_refresh)

    def full_frame_forbidden(*args, **kwargs):
        raise AssertionError('Forward replay must not materialize the full archive')

    monkeypatch.setattr(module, 'archive_observations', full_frame_forbidden)
    result = module.forward(root, ledger, horizon=300)
    assert result['issued_at'] == 650
    assert result['new_predictions'] == 4
    expected = module.row_json(archive_observations(root).iloc[0].to_dict())
    with connect(ledger) as db:
        rows = db.execute('SELECT issued_at,context_json FROM predictions').fetchall()
        assert all(row[0] == 650 and json.loads(row[1]) == expected for row in rows)
        assert all('100.0' not in row[1] for row in rows)
    assert module.forward(root, ledger, horizon=300)['new_predictions'] == 0
