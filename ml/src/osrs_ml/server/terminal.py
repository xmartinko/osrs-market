"""Terminal adapters: real historical observations, screeners and persistent local alerts."""

import json
import math
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from . import charting as c


class ChartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: int = Field(855, gt=0)
    tf: Literal["5m", "15m", "30m", "1h", "1d", "1w"] = "1d"
    style: str = "Line"
    scale: Literal["linear", "percent", "indexed", "logarithmic"] = "linear"
    range: Literal["5y", "1y", "6m", "3m", "1m", "5d", "1d"] = "3m"
    date: str = ""
    bars: int = Field(0, ge=0, le=10000)
    offset: int = Field(0, ge=0, le=1000000)
    indicators: list[Literal["SMA", "EMA", "BOLL", "RSI", "MACD", "VWAP"]] = []
    invert: bool = False
    axis_left: bool = False
    auto_fit: bool = True
    lock: bool = False
    price_only: bool = True
    ratio: float | None = Field(None, gt=0, allow_inf_nan=False)
    bounds: tuple[float, float] | None = None
    box: float | None = Field(None, gt=0, allow_inf_nan=False)
    width: int = Field(100, ge=1, le=1000)
    height: int = Field(24, ge=1, le=500)


class PanelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["TAS", "QM", "HCP", "HMAP", "MOST", "EQS", "COMP", "AL"]
    item: int = Field(855, gt=0)
    linked: bool = False
    ids: list[int] = Field(default_factory=lambda: [855, 561, 4151], max_length=100)
    filter: str = ""
    sort: int = 0
    min_spread: float | None = Field(None, allow_inf_nan=False)
    min_volume: float | None = Field(None, ge=0, allow_inf_nan=False)
    min_alch: float | None = Field(None, allow_inf_nan=False)
    members: bool | None = None
    limit_min: int | None = Field(None, ge=0)
    limit_max: int | None = Field(None, ge=0)
    width: int = Field(100, ge=1, le=1000)
    height: int = Field(24, ge=1, le=500)
    range: Literal["5y", "1y", "6m", "3m", "1m", "5d", "1d"] = "3m"
    tf: Literal["5m", "15m", "30m", "1h", "1d", "1w"] = "1d"


class AlertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: int = Field(gt=0)
    field: Literal["price", "spread", "alch_gap"]
    direction: Literal["above", "below"]
    threshold: float = Field(allow_inf_nan=False)


class Terminal:
    def __init__(self, service):
        self.service = service
        self.cache = {}
        self.lock = threading.RLock()
        self.path = service.root / "server/terminal.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY, item INTEGER, field TEXT, direction TEXT,
                threshold REAL, created REAL, triggered REAL, value REAL)""")
        self.tape = {}

    def db(self):
        return sqlite3.connect(self.path, timeout=15)

    def cached(self, key, load, ttl=300):
        with self.lock:
            old = self.cache.get(key)
            if old and time.time() - old[0] < ttl:
                return old[1]
            result = load()
            self.cache[key] = (time.time(), result)
            return result

    def local(self, item, tf):
        def load():
            root = self.service.root
            if tf == "1w":
                path = root / "ge-tracker-weekly-v1/weekly.parquet"
                query = """SELECT timestamp, overallPrice AS close, overallCompleted AS volume
                    FROM read_parquet(?) WHERE item_id=? AND overallPrice > 0 ORDER BY timestamp"""
                source = "GE Tracker weekly mean; completed counts are volume proxy"
            elif tf == "1d":
                path = root / "assembled-v3/daily.parquet"
                query = """SELECT timestamp, (avg_high_price+avg_low_price)/2.0 AS close,
                    coalesce(high_price_volume,0)+coalesce(low_price_volume,0) AS volume
                    FROM read_parquet(?) WHERE item_id=? AND avg_high_price > 0
                    AND avg_low_price > 0 ORDER BY timestamp"""
                source = "local daily means; source interval unknown (timestamp-phase inference)"
            else:
                path = root / "forward/wiki/300s/*/observations.parquet"
                query = """SELECT timestamp, (avg_high_price+avg_low_price)/2.0 AS close,
                    coalesce(high_price_volume,0)+coalesce(low_price_volume,0) AS volume
                    FROM read_parquet(?) WHERE item_id=? AND avg_high_price > 0
                    AND avg_low_price > 0 ORDER BY timestamp"""
                source = "archived genuine 5m bucket means"
            if not (
                list((root / "forward/wiki/300s").glob("*/observations.parquet"))
                if "*" in str(path)
                else path.exists()
            ):
                return [], ""
            with duckdb.connect() as db:
                frame = db.execute(query, [str(path), item]).fetchdf()
            rows = json.loads(frame.drop_duplicates("timestamp").to_json(orient="records"))
            return rows, source

        return self.cached((item, tf), load)

    def series(self, item, tf):
        rows, source = self.local(item, tf)
        feed_tf = "24h" if tf in ("1d", "1w") else "5m"
        value = self.service.feed(f"timeseries?timestep={feed_tf}&id={item}", 300)
        recent = []
        for r in (value.get("data") or {}).get("data", []):
            high, low = r.get("avgHighPrice"), r.get("avgLowPrice")
            if high and low:
                recent.append(
                    dict(
                        timestamp=r["timestamp"],
                        close=(high + low) / 2,
                        volume=(r.get("highPriceVolume") or 0) + (r.get("lowPriceVolume") or 0),
                    )
                )
        if tf != "1w":
            merged = {r["timestamp"]: r for r in rows}
            merged.update({r["timestamp"]: r for r in recent})
            rows = sorted(merged.values(), key=lambda r: r["timestamp"])
            source = (source + "; " if source else "") + "Wiki bucket means"
        elif not rows and recent:
            rows = c.aggregate(recent, c.RESOLUTIONS[tf])
            source = "weekly aggregates of Wiki daily bucket means; incomplete weeks possible"
        if tf in ("15m", "30m", "1h"):
            rows = c.aggregate(rows, c.RESOLUTIONS[tf])
            source += f"; OHLC of 5m means aggregated to {tf} (not trade OHLC)"
        return rows, source, value

    def chart(self, req):
        if req.style not in c.STYLES:
            raise ValueError("Unknown chart style")
        rows, source, status = self.series(req.item, req.tf)
        end = rows[-1]["timestamp"] if rows else int(time.time())
        if req.date:
            try:
                end = (
                    int(
                        datetime.strptime(req.date, "%Y-%m-%d")
                        .replace(tzinfo=timezone.utc)
                        .timestamp()
                    )
                    + 86399
                )
            except ValueError:
                raise ValueError("Go to date requires YYYY-MM-DD (UTC)") from None
        start = end - c.RANGES[req.range] * 86400
        visible = [r for r in rows if start <= r["timestamp"] <= end]
        stop = max(0, len(visible) - req.offset)
        visible = visible[max(0, stop - (req.bars or len(visible))) : stop]
        envelopes = c.mean_envelopes(visible)
        if req.tf in ("15m", "30m", "1h"):
            envelopes = visible  # first/last/min/max of observed 5m bucket means
        if req.bounds is not None and (
            not all(math.isfinite(b) for b in req.bounds) or req.bounds[0] >= req.bounds[1]
        ):
            raise ValueError("Scale bounds must be finite and increasing")
        geometry = c.chart(
            envelopes,
            req.style,
            req.scale,
            req.indicators,
            req.invert,
            req.height,
            req.width,
            req.lock,
            None if req.auto_fit else req.bounds,
            req.box,
            req.price_only,
            rows,
            next(
                (
                    i
                    for i, r in enumerate(rows)
                    if visible and r["timestamp"] == visible[0]["timestamp"]
                ),
                0,
            ),
            req.ratio,
        )
        last = visible[-1] if visible else None
        first = visible[0] if visible else None
        delta = last["close"] - first["close"] if last else 0
        close_at = (int(time.time()) // c.RESOLUTIONS[req.tf] + 1) * c.RESOLUTIONS[req.tf]
        bucket_end = last["timestamp"] + c.RESOLUTIONS[req.tf] if last else 0
        label = (
            "mean-envelope; NOT trade OHLC"
            if req.style in ("Candles", "Hollow Candles", "Heikin Ashi")
            else "close/mean series"
        )
        if req.tf in ("15m", "30m", "1h"):
            label += "; OHLC of 5m means"
        return dict(
            **geometry,
            item=req.item,
            tf=req.tf,
            style=req.style,
            scale=req.scale,
            provenance=label,
            source=source,
            stale=status.get("stale", False),
            error=status.get("error"),
            first=first,
            last=last,
            delta=delta,
            change_pct=delta / first["close"] * 100 if first else None,
            cursor=[
                dict(timestamp=r["timestamp"], close=r["close"], volume=r.get("volume"))
                for r in visible
            ],
            visible_volume=sum(r.get("volume", 0) or 0 for r in visible),
            close_at=close_at,
            bucket_historical=bucket_end < time.time() - c.RESOLUTIONS[req.tf],
            available_bars=len(rows),
            visible_bars=len(visible),
            note="Ranges end at latest available observation; no prices filled across gaps",
        )

    def market(self):
        def load():
            latest = self.service.latest()
            bulk = self.service.feed("5m", 300)
            payload = bulk.get("data") or {}
            metadata = {int(r["id"]): r for r in self.service.items()["data"]}
            nature = next((r["buy_price"] for r in latest["data"] if r["item_id"] == 561), None)
            rows = []
            for r in latest["data"]:
                meta = metadata.get(r["item_id"], {})
                bucket = payload.get("data", {}).get(str(r["item_id"]), {})
                high, low = r["buy_price"], r["sell_price"]
                alch = meta.get("high_alch", meta.get("highalch"))
                gap = alch - high - nature if alch is not None and high and nature else None
                stamp = max(r.get("high_time") or 0, r.get("low_time") or 0)
                rows.append(
                    dict(
                        **r,
                        price=(high + low) / 2 if high and low else None,
                        bid=low,
                        ask=high,
                        spread=r["margin_gp"],
                        alch_gap=gap,
                        volume=(bucket.get("highPriceVolume") or 0)
                        + (bucket.get("lowPriceVolume") or 0),
                        high_volume=bucket.get("highPriceVolume"),
                        low_volume=bucket.get("lowPriceVolume"),
                        high_mean=bucket.get("avgHighPrice"),
                        low_mean=bucket.get("avgLowPrice"),
                        bucket_time=payload.get("timestamp"),
                        quote_time=stamp,
                        bid_time=r.get("low_time"),
                        ask_time=r.get("high_time"),
                        members=meta.get("members"),
                        buy_limit=meta.get("buy_limit", meta.get("limit")),
                        trade_count=None,
                    )
                )
            stale = latest.get("stale", False) or bulk.get("stale", False)
            return dict(
                data=rows,
                stale=stale,
                error=latest.get("error") or bulk.get("error"),
                basis="Wiki latest side prices (not order-book quotes); 5m item volume, no trade counts",
            )

        return self.cached("market", load, 5)

    def changes(self, rows):
        def load():
            path = self.service.root / "assembled-v3/daily.parquet"
            now = int(time.time())
            data = []
            if path.exists():
                with duckdb.connect() as db:
                    data = db.execute(
                        """WITH horizons AS (
                            SELECT unnest([1,7,31]) AS days), candidates AS (
                            SELECT item_id, days, timestamp, (avg_high_price+avg_low_price)/2.0 AS price,
                                row_number() OVER (PARTITION BY item_id, days ORDER BY timestamp DESC) AS rn
                            FROM read_parquet(?) CROSS JOIN horizons
                            WHERE timestamp <= ? - days*86400 AND timestamp >= ? - (days+2)*86400
                            AND avg_high_price > 0 AND avg_low_price > 0)
                        SELECT item_id, days, price FROM candidates WHERE rn=1""",
                        [str(path), now, now],
                    ).fetchall()
            historic = {(item, days): price for item, days, price in data}
            for days in (1, 7, 31):
                target = (now - days * 86400) // 86400 * 86400
                value = self.service.feed(f"24h?timestamp={target}", 300)
                payload = value.get("data") or {}
                stamp = payload.get("timestamp")
                if value.get("stale") or stamp is None or not target - 2 * 86400 <= stamp <= target:
                    continue
                for item, raw in payload.get("data", {}).items():
                    high, low = raw.get("avgHighPrice"), raw.get("avgLowPrice")
                    if high and low:
                        historic.setdefault((int(item), days), (high + low) / 2)
            return historic

        historic = self.cached("changes", load)
        return [
            {
                **r,
                **{
                    f"change_{n}": (r["price"] / historic[r["item_id"], days] - 1) * 100
                    if (r["item_id"], days) in historic and r["price"]
                    else None
                    for n, days in [("1d", 1), ("1w", 7), ("1m", 31)]
                },
            }
            for r in rows
        ]

    def panel(self, req):
        if req.kind == "AL":
            return self.alerts()
        if req.kind == "COMP":
            if not 1 <= len(req.ids) <= 5:
                raise ValueError("COMP requires one to five item IDs")
            series, provenance, stale = {}, [], False
            ids = ([req.item] + req.ids[1:]) if req.linked else req.ids
            for item in dict.fromkeys(ids):
                rows, source, status = self.series(item, req.tf)
                provenance.append(source)
                stale |= status.get("stale", False)
                series[str(item)] = rows
            common = c.comparison(series)
            if common:
                end = common[0]["points"][-1][0]
                times = [
                    p[0] for p in common[0]["points"] if p[0] >= end - c.RANGES[req.range] * 86400
                ]
                series = {
                    name: [r for r in rows if r["timestamp"] in set(times)]
                    for name, rows in series.items()
                }
                common = c.comparison(series)
            return dict(
                series=common,
                **c.comparison_geometry(common),
                tf=req.tf,
                source="; ".join(dict.fromkeys(provenance)),
                stale=stale,
                basis="Close/mean return indexed to 100 at exact common start; no dividends or filling",
            )
        market = self.market()
        rows = market["data"]
        basis = market["basis"]
        if req.kind == "TAS":
            with self.lock:
                for r in rows:
                    for side in ("high", "low"):
                        if r[f"{side}_volume"] and r[f"{side}_mean"]:
                            key = (r["bucket_time"], r["item_id"], side)
                            self.tape[key] = dict(
                                timestamp=r["bucket_time"],
                                item_id=r["item_id"],
                                name=r["name"],
                                side="buy" if side == "high" else "sell",
                                price=r[f"{side}_mean"],
                                volume=r[f"{side}_volume"],
                            )
                cutoff = max((r["timestamp"] or 0 for r in self.tape.values()), default=0) - 86400
                self.tape = {k: v for k, v in self.tape.items() if (v["timestamp"] or 0) >= cutoff}
                rows = sorted(
                    self.tape.values(),
                    key=lambda r: (r["timestamp"] or 0, r["volume"]),
                    reverse=True,
                )
            basis = "5m side bucket events; aggregate means and item volume, NOT individual trades"
        elif req.kind == "QM":
            ids = set(req.ids) | ({req.item} if req.linked else set())
            rows = [r for r in rows if r["item_id"] in ids]
        elif req.kind in ("HCP", "HMAP"):
            rows = self.changes(rows)
            key = ["change_1d", "change_1w", "change_1m"][req.sort % 3]
            if req.kind == "HMAP" and req.sort % 2 == 0:
                key = "spread"
            rows = sorted(
                rows,
                key=lambda r: r.get(key) if r.get(key) is not None else -math.inf,
                reverse=True,
            )
            basis += "; returns vs daily means within 2d of lookback (local / Wiki 24h); missing stays absent"
        elif req.kind == "MOST":
            rows = sorted(rows, key=lambda r: r["volume"], reverse=True)
            basis += "; trade-count ranking unavailable: source reports item quantity only"
        elif req.kind == "EQS":
            # Composable comparisons exclude unknown values when a constraint is active.
            for field, bound in [
                ("spread", req.min_spread),
                ("volume", req.min_volume),
                ("alch_gap", req.min_alch),
                ("buy_limit", req.limit_min),
            ]:
                if bound is not None:
                    rows = [r for r in rows if r.get(field) is not None and r[field] >= bound]
            if req.limit_max is not None:
                rows = [
                    r
                    for r in rows
                    if r.get("buy_limit") is not None and r["buy_limit"] <= req.limit_max
                ]
            if req.members is not None:
                rows = [r for r in rows if r["members"] == req.members]
            key = ["spread", "volume", "alch_gap"][req.sort % 3]
            rows = sorted(
                rows,
                key=lambda r: r.get(key) if r.get(key) is not None else -math.inf,
                reverse=True,
            )
            basis += "; alch gap = high alch minus instant buy minus nature rune (fire staff assumed, no time charge)"
        if req.linked and req.kind == "TAS":
            rows = [r for r in rows if r["item_id"] == req.item]
        rows = [
            r
            for r in rows
            if req.filter.lower() in r["name"].lower() or req.filter == str(r["item_id"])
        ]
        result = dict(data=rows, stale=market["stale"], error=market.get("error"), basis=basis)
        if req.kind == "EQS":
            constraints = []
            for name, value in [
                ("spread", req.min_spread),
                ("volume", req.min_volume),
                ("alch gap", req.min_alch),
                ("buy limit", req.limit_min),
            ]:
                if value is not None:
                    constraints.append(f"{name} ≥ {value:g}")
            if req.limit_max is not None:
                constraints.append(f"buy limit ≤ {req.limit_max}")
            if req.members is not None:
                constraints.append("members" if req.members else "free")
            result["filters_label"] = " · ".join(constraints) or "none"
        if req.kind == "HMAP":
            top = sorted(
                [r for r in rows if r["volume"] > 0], key=lambda r: r["volume"], reverse=True
            )[:32]
            result["cells"] = c.treemap(top, req.width, req.height)
            result["color_field"] = "spread" if req.sort % 2 == 0 else "change_1d"
        return result

    def add_alert(self, req):
        with self.db() as db:
            cur = db.execute(
                """INSERT INTO alerts(item,field,direction,threshold,created)
                VALUES(?,?,?,?,?)""",
                (req.item, req.field, req.direction, req.threshold, time.time()),
            )
            return dict(id=cur.lastrowid)

    def delete_alert(self, alert_id):
        with self.db() as db:
            db.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
        return dict(deleted=alert_id)

    def alerts(self):
        with self.db() as db:
            db.row_factory = sqlite3.Row
            return dict(
                data=[dict(r) for r in db.execute("SELECT * FROM alerts ORDER BY id DESC")],
                basis="Server-persisted one-shot thresholds; fresh live data only; no external delivery",
            )

    def evaluate_alerts(self):
        with self.db() as db:
            pending = db.execute(
                "SELECT id,item,field,direction,threshold FROM alerts WHERE triggered IS NULL"
            ).fetchall()
            if not pending:
                return
            market = self.market()
            if market["stale"]:
                return
            indexed = {r["item_id"]: r for r in market["data"]}
            for alert_id, item, field, direction, threshold in pending:
                r = indexed.get(item, {})
                # Do not fire on an old side quote carried in a fresh HTTP response.
                stamp = min(r.get("bid_time") or 0, r.get("ask_time") or 0)
                value = r.get(field)
                if value is None or time.time() - stamp > 900:
                    continue
                if value >= threshold if direction == "above" else value <= threshold:
                    db.execute(
                        "UPDATE alerts SET triggered=?,value=? WHERE id=? AND triggered IS NULL",
                        (time.time(), value, alert_id),
                    )
