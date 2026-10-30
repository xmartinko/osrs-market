"""Read adapters. Financial formulas stay in the existing research modules."""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pandas as pd

from ..assembly import data_dir
from ..costs import sale_proceeds
from ..mechanical_ceiling import Assumptions, capacity, catalogue, economics
from . import VERSION

ML = Path(__file__).resolve().parents[3]
BASE = "https://prices.runescape.wiki/api/v1/osrs"


def records(frame):
    return json.loads(frame.to_json(orient="records"))


class Service:
    def __init__(self, root=None, client=None, ttl=60):
        self.root = Path(root) if root else data_dir()
        self.started = time.time()
        self.ttl = ttl
        self.client = client or httpx.Client(timeout=12, headers={
            "User-Agent": os.getenv("OSRS_WIKI_USER_AGENT", "osrs-market/osrs-term research dashboard (local, read-only)"),
        })
        self.cache = {}
        self.lock = threading.RLock()
        self.last_success = None
        self.reachable = None

    def feed(self, endpoint, ttl=None):
        ttl = self.ttl if ttl is None else ttl
        with self.lock:
            old = self.cache.get(endpoint)
            now = time.time()
            if old and now - old["attempted_at"] < (ttl if not old["error"] else 10):
                return {**old, "age_seconds": now - old["fetched_at"] if old["fetched_at"] else None,
                        "stale": bool(old["error"] or now - old["fetched_at"] >= ttl)}
            try:
                response = self.client.get(f"{BASE}/{endpoint}")
                response.raise_for_status()
                payload = response.json()
                value = dict(data=payload, fetched_at=now, attempted_at=now, error=None)
                self.last_success, self.reachable = now, True
            except (httpx.HTTPError, ValueError) as exc:
                value = dict(data=old["data"] if old else None,
                             fetched_at=old["fetched_at"] if old else None,
                             attempted_at=now, error=str(exc))
                self.reachable = False
            self.cache[endpoint] = value
            return {**value, "age_seconds": now - value["fetched_at"] if value["fetched_at"] else None,
                    "stale": bool(value["error"])}

    def health(self):
        self.feed("latest")
        return dict(version=VERSION, uptime_seconds=round(time.time() - self.started, 2),
                    data_dir=str(self.root), market_feed_reachable=self.reachable,
                    last_successful_fetch=self.last_success)

    def items(self):
        path = self.root / "items.parquet"
        if path.exists():
            return dict(data=records(pd.read_parquet(path)), source=str(path), stale=False)
        result = self.feed("mapping", 86400)
        result["data"] = [{**r, "buy_limit": r.get("limit"), "high_alch": r.get("highalch"),
                           "low_alch": r.get("lowalch")} for r in result["data"] or []]
        return result

    def latest(self):
        value = self.feed("latest")
        meta = {int(r["id"]): r for r in self.items()["data"]}
        rows = []
        for item, price in (value["data"] or {}).get("data", {}).items():
            item = int(item)
            high, low = price.get("high"), price.get("low")
            margin = sale_proceeds(int(high), 1, item_id=item) - int(low) if high and low else None
            rows.append(dict(item_id=item, name=meta.get(item, {}).get("name", str(item)),
                             buy_price=high, sell_price=low, margin_gp=margin,
                             margin_basis="hypothetical low purchase / high sale after tax",
                             high_time=price.get("highTime"), low_time=price.get("lowTime")))
        return {**value, "data": sorted(rows, key=lambda r: r["item_id"])}

    def history(self, item_id, tf, limit):
        value = self.feed(f"timeseries?timestep={ {'5m': '5m', '1h': '1h', '1d': '24h'}[tf]}&id={item_id}", 300)
        rows, previous = [], None
        for row in (value["data"] or {}).get("data", []):
            high, low = row.get("avgHighPrice"), row.get("avgLowPrice")
            if high is None or low is None:
                continue
            close = (high + low) / 2
            opening = previous if previous is not None else close
            rows.append(dict(timestamp=row["timestamp"], open=opening,
                             high=max(high, low, opening), low=min(high, low, opening), close=close,
                             volume=(row.get("highPriceVolume") or 0) + (row.get("lowPriceVolume") or 0)))
            previous = close
        return {**value, "data": rows[-limit:], "item_id": item_id, "tf": tf,
                "candle_basis": "bucket mean envelope; open = previous midpoint, close = midpoint; not trade OHLC"}

    def alch(self):
        # Bulk completed volume buckets are needed for research capacity, not invented volumes.
        value = self.feed("5m", 300)
        bulk = (value["data"] or {}).get("data", {})
        meta = pd.DataFrame(self.items()["data"])
        if meta.empty or not bulk:
            return {**value, "data": [], "basis": "completed 5m bucket; conditional research capacity"}
        meta = meta.rename(columns={"limit": "buy_limit", "highalch": "high_alch"})
        indexed = meta.set_index("id")
        rows = []
        for recipe in catalogue()[:4]:
            item = recipe.inputs[0][0]
            raw, rune = bulk.get(str(item)), bulk.get("561")
            if not raw or not rune or item not in indexed.index or 561 not in indexed.index:
                continue
            if any(not r.get("avgHighPrice") or not r.get("avgLowPrice") for r in [raw, rune]):
                continue
            values = {}
            for i, r in [(item, raw), (561, rune)]:
                values.update({f"{i}_avg_high_price": r["avgHighPrice"], f"{i}_avg_low_price": r["avgLowPrice"],
                               f"{i}_high_price_volume": r["highPriceVolume"], f"{i}_low_price_volume": r["lowPriceVolume"]})
            frame = pd.DataFrame([values])
            try:
                _, gap = economics(frame, recipe)
                cap = capacity(frame, indexed, recipe, Assumptions())
            except (ValueError, TypeError, KeyError):
                continue
            rows.append(dict(item_id=item, name=indexed.loc[item, "name"], buy_price=raw["avgHighPrice"],
                             high_alch=recipe.coins, nature_rune_cost=rune["avgHighPrice"],
                             net_gap_gp=float(gap.iloc[0]), capacity=int(cap.target_units.iloc[0])))
        return {**value, "data": rows, "basis": "completed 5m mean prices; existing mechanical_ceiling economics/capacity, reference assumptions; conditional, not fills"}

    def research(self, kind):
        path = self.root / ({"battery": "strategy-battery-v1/results.csv",
                             "participation": "participation-bounds-v3-cached/break_even.csv"}[kind])
        if not path.exists():
            return dict(data=[], error=f"Missing artifact: {path}")
        rows = records(pd.read_csv(path))
        if kind == "battery":
            for row in rows:
                row["verdict"] = "survives" if row.get("survives") else row.get("status", "rejected")
        return dict(data=rows, source=str(path), basis="persisted existing research results")

    def collector(self):
        snapshots = sorted((self.root / "forward/wiki").glob("*s/*/observations.manifest.json"))
        buckets = {}
        for path in snapshots:
            m = json.loads(path.read_text())
            buckets.setdefault(m["resolution_seconds"], set()).add(m["timestamp"])
        series = []
        for resolution, times in buckets.items():
            times = sorted(times)
            series.append(dict(resolution_seconds=resolution, oldest=times[0], newest=times[-1],
                               gaps=sum(max(0, (b-a)//resolution-1) for a, b in zip(times, times[1:]))))
        ledgers = {}
        for path in sorted((self.root / "forward").glob("*.sqlite")):
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
                names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                ledgers[path.name] = {n: db.execute('SELECT count(*) FROM "' + n.replace('"', '""') + '"').fetchone()[0] for n in names}
        return dict(snapshot_count=len(snapshots), buckets=series, ledger_rows=ledgers)

    def runs(self):
        result = []
        for path in sorted((ML / "runs").glob("**/run.json")):
            if "holdout" in path.parts:
                continue
            metrics = []
            for p in path.parent.glob("**/metrics.json"):
                if "holdout" not in p.parts:
                    metrics.append(dict(path=str(p.relative_to(path.parent)), values=json.loads(p.read_text())))
            result.append(dict(path=str(path.parent), metadata=json.loads(path.read_text()), metrics=metrics))
        return dict(data=result)
