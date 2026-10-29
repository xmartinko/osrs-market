"""Prospective predictions and matured outcomes, with reproducible paper execution."""

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

from .backtest import simulate
from .collector import archive_observations
from .costs import sale_proceeds
from .data import sha256
from .execution import PRESETS, PortfolioPolicy

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
 id TEXT PRIMARY KEY, model TEXT NOT NULL, model_hash TEXT NOT NULL, item_id INTEGER NOT NULL,
 issued_at INTEGER NOT NULL, data_cutoff INTEGER NOT NULL, event_time INTEGER NOT NULL,
 resolution_seconds INTEGER NOT NULL, horizon_seconds INTEGER NOT NULL, score REAL NOT NULL,
 entry_gp INTEGER NOT NULL, context_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes (
 prediction_id TEXT PRIMARY KEY REFERENCES predictions(id), recorded_at INTEGER NOT NULL,
 observation_time INTEGER NOT NULL, status TEXT NOT NULL, net_gp_per_unit INTEGER,
 observation_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_runs (
 id TEXT PRIMARY KEY, recorded_at INTEGER NOT NULL, model TEXT NOT NULL, preset TEXT NOT NULL,
 archive_hash TEXT NOT NULL, policy_json TEXT NOT NULL, metrics_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_fills (
 id TEXT PRIMARY KEY, model TEXT NOT NULL, preset TEXT NOT NULL, fill_json TEXT NOT NULL);
"""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    for table in ["predictions", "outcomes", "paper_runs", "paper_fills"]:
        for action in ["UPDATE", "DELETE"]:
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{action}
                BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END""")
    db.commit()
    return db


def row_json(row):
    return {
        key: None if pd.isna(value) else value.item() if hasattr(value, "item") else value
        for key, value in row.items()
    }


def issue(db, observations, *, now=None, horizon=3600, model_scores=None, model_hash=None):
    now = int(time.time()) if now is None else now
    if observations.empty:
        return 0
    if horizon <= 0:
        raise ValueError("Positive horizon required")
    if observations.resolution_seconds.nunique() != 1 or not observations.source.eq("wiki").all():
        raise ValueError("One Wiki resolution per ledger")
    if (observations.fetched_at > now).any() or (observations.available_at > now).any():
        raise ValueError("Future context cannot issue a prediction")
    latest = observations.sort_values("available_at").drop_duplicates("item_id", keep="last")
    policy_hash = digest(
        {
            "code": sha256(Path(__file__)),
            "horizon": horizon,
            "tax": "2pct_floor_cap5m_exempt49_no_item_exemptions",
        }
    )
    added = 0
    for row in latest.to_dict("records"):
        if (
            now - int(row["available_at"]) > int(row["resolution_seconds"]) * 2
            or row["inverted_spread"]
            or pd.isna(row["avg_high_price"])
            or pd.isna(row["avg_low_price"])
        ):
            continue
        item, high, low = int(row["item_id"]), int(row["avg_high_price"]), int(row["avg_low_price"])
        spread = sale_proceeds(high, 1, item_id=item) - low
        scores = {
            "no_trade": -1.0,
            "no_change": float(sale_proceeds(low, 1, item_id=item) - high),
            "raw_spread": float(spread),
            "spread_volume": float(
                spread * min(int(row["high_price_volume"]), int(row["low_price_volume"]))
            ),
        }
        if model_scores is not None:
            candidate = model_scores.get((item, int(row["timestamp"])))
            if candidate is not None and math.isfinite(candidate):
                scores["catboost"] = candidate
        for model, score in scores.items():
            revision_hash = model_hash if model == "catboost" else policy_hash
            identity = [
                model,
                revision_hash,
                item,
                int(row["timestamp"]),
                int(row["resolution_seconds"]),
            ]
            context = row_json(row)
            values = [
                digest(identity),
                model,
                revision_hash,
                item,
                now,
                int(row["available_at"]),
                int(row["timestamp"]),
                int(row["resolution_seconds"]),
                horizon,
                score,
                high,
                canonical(context),
            ]
            result = db.execute(
                "INSERT OR IGNORE INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values
            )
            added += result.rowcount
    db.commit()  # Predictions are durable BEFORE outcomes can be examined.
    return added


def settle(db, observations, *, now=None):
    now = int(time.time()) if now is None else now
    if observations.empty:
        return 0
    added = 0
    pending = db.execute("""SELECT p.* FROM predictions p LEFT JOIN outcomes o
                            ON p.id=o.prediction_id WHERE o.prediction_id IS NULL""").fetchall()
    by_item = {int(i): g.sort_values("timestamp") for i, g in observations.groupby("item_id")}
    for p in pending:
        f = by_item.get(p["item_id"])
        if f is None:
            continue
        candidates = f[
            (f.timestamp >= p["issued_at"] + p["horizon_seconds"])
            & (f.fetched_at <= now)
            & (f.available_at <= now)
            & (f.resolution_seconds == p["resolution_seconds"])
        ]
        if candidates.empty:
            continue
        row = candidates.iloc[0].to_dict()
        missing = pd.isna(row["avg_low_price"]) or row["inverted_spread"]
        late = (
            int(row["timestamp"])
            > p["issued_at"] + p["horizon_seconds"] + p["resolution_seconds"] * 2
        )
        status = "missing_side" if missing else "late_observation" if late else "observed"
        net = (
            None
            if status != "observed"
            else sale_proceeds(int(row["avg_low_price"]), 1, item_id=p["item_id"]) - p["entry_gp"]
        )
        db.execute(
            "INSERT OR IGNORE INTO outcomes VALUES (?,?,?,?,?,?)",
            [p["id"], now, int(row["timestamp"]), status, net, canonical(row_json(row))],
        )
        added += 1
    db.commit()
    return added


def paper(db, observations, *, now=None, execution=None):
    now = int(time.time()) if now is None else now
    if observations.empty:
        return []
    archive_hash = digest(
        [row_json(r) for r in observations.sort_values(["item_id", "timestamp"]).to_dict("records")]
    )
    rows = []
    cohorts = db.execute("SELECT DISTINCT model,model_hash FROM predictions").fetchall()
    for cohort in cohorts:
        model = cohort["model"] + "@" + cohort["model_hash"][:12]
        predictions = db.execute(
            "SELECT * FROM predictions WHERE model=? AND model_hash=? ORDER BY issued_at,item_id",
            [cohort["model"], cohort["model_hash"]],
        ).fetchall()
        if not predictions:
            continue
        horizon = {p["horizon_seconds"] for p in predictions}
        if len(horizon) != 1:
            raise ValueError("One horizon per paper ledger")
        policy = PortfolioPolicy(holding_seconds=horizon.pop())
        start = min(p["issued_at"] for p in predictions)
        events = observations[
            (observations.available_at >= start) & (observations.available_at <= now)
        ].copy()
        keys = set(zip(events.item_id.astype(int), events.available_at.astype(int), strict=True))
        decisions = []
        for p in predictions:
            key = (p["item_id"], p["issued_at"])
            if key in keys:
                continue
            row = json.loads(p["context_json"])
            row["available_at"] = p["issued_at"]
            # Synthetic decision events NEVER contribute another copy of bucket volume.
            row["high_price_volume"] = row["low_price_volume"] = 0
            for side in ["high", "low"]:
                if row[f"{side}_freshness_seconds"] is not None:
                    row[f"{side}_freshness_seconds"] += p["issued_at"] - p["data_cutoff"]
            decisions.append(row)
            keys.add(key)
        if decisions:
            events = pd.concat([events, pd.DataFrame(decisions)], ignore_index=True)
        if events.available_at.nunique() < 2:
            continue
        scores = {(p["item_id"], p["issued_at"]): p["score"] for p in predictions}
        for name, preset in PRESETS.items():
            assumptions = replace(
                preset,
                passive_prices=name == "optimistic",
                queue_fill_bps={"optimistic": 10000, "moderate": 5000, "conservative": 2500}[name],
            )
            if execution is not None:
                assumptions = replace(preset, **execution[name])
            config = {"execution": asdict(assumptions), "portfolio": asdict(policy)}
            run_id = digest([archive_hash, model, config, [p["id"] for p in predictions]])
            result = simulate(events, scores, assumptions, policy)
            db.execute(
                "INSERT OR IGNORE INTO paper_runs VALUES (?,?,?,?,?,?,?)",
                [
                    run_id,
                    now,
                    model,
                    name,
                    archive_hash,
                    canonical(config),
                    canonical(result.metrics),
                ],
            )
            for fill in result.fills:
                db.execute(
                    "INSERT OR IGNORE INTO paper_fills VALUES (?,?,?,?)",
                    [digest([model, name, config, fill]), model, name, canonical(fill)],
                )
            rows.append({"model": model, "preset": name, **result.metrics})
    db.commit()
    return rows


def forward(
    archive: Path,
    ledger: Path,
    *,
    horizon: int = 3600,
    resolution: int = 300,
    model_dir: Path | None = None,
    history_panel: Path | None = None,
):
    f = archive_observations(archive, resolution=resolution)
    now = int(time.time())
    with connect(ledger) as db:
        old = db.execute("SELECT DISTINCT horizon_seconds FROM predictions").fetchall()
        if old and {row[0] for row in old} != {horizon}:
            raise ValueError("Horizon changed: use a separate ledger")
        model_scores, model_hash = None, None
        if model_dir is not None:
            if resolution != 86400 or horizon != 86400 or history_panel is None:
                raise ValueError(
                    "Daily CatBoost requires a daily ledger, 24h horizon and history panel"
                )
            from catboost import CatBoostRegressor

            from .data import load_snapshot
            from .research import daily_features, matrix

            history = load_snapshot(history_panel, allow_unknown_metadata=True)
            history = history[history.available_at <= now].groupby("item_id").tail(30)
            context = pd.concat([history, f[f.available_at <= now]], ignore_index=True)
            context = context.sort_values("available_at").drop_duplicates(
                ["item_id", "timestamp"], keep="first"
            )
            # Windows use event-time distances. Actual known-at times remain in the ledger.
            context["available_at"] = context.timestamp + 86400 + 300
            features = daily_features(context, labels=False)
            latest = features.sort_values("timestamp").drop_duplicates("item_id", keep="last")
            estimator = CatBoostRegressor()
            estimator.load_model(str(model_dir / "net_return.cbm"))
            values = estimator.predict(matrix(latest)) * latest.high.to_numpy(dtype=float) / 24
            model_scores = dict(
                zip(
                    zip(latest.item_id.astype(int), latest.timestamp.astype(int), strict=True),
                    values,
                    strict=True,
                )
            )
            model_hash = digest(
                {
                    "weights": sha256(model_dir / "net_return.cbm"),
                    "training": sha256(model_dir / "training.json"),
                    "code": sha256(Path(__file__)),
                    "history": sha256(history_panel),
                }
            )
        added = issue(
            db, f, now=now, horizon=horizon, model_scores=model_scores, model_hash=model_hash
        )
        matured = settle(db, f, now=now)
        execution = None
        if resolution == 86400:
            config_path = Path(__file__).resolve().parents[2] / "experiments" / "daily-v1.json"
            execution = json.loads(config_path.read_text())["execution"]
        results = paper(db, f, now=now, execution=execution)
        counts = {
            t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ["predictions", "outcomes", "paper_fills", "paper_runs"]
        }
    return {
        "issued_at": now,
        "new_predictions": added,
        "new_outcomes": matured,
        "counts": counts,
        "paper_metrics": results,
        "warning": "Prospective paper evidence; no actual trades. "
        "No matured outcomes means live profitability is unknown.",
    }
