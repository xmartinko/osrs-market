"""Append-only Wiki bulk snapshots. No changes to the C++ collector or database."""

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import pyarrow.parquet as pq

from .assembly import data_dir
from .data import manifest

BASE = "https://prices.runescape.wiki/api/v1/osrs"


def fetch_json(url: str, user_agent: str):
    if not user_agent or len(user_agent) < 10:
        raise ValueError("Set a descriptive OSRS_WIKI_USER_AGENT with project/contact information")
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def publish(
    root: Path,
    payload: dict,
    mapping: list,
    fetched: int,
    resolution: int = 300,
    *,
    mapping_fetched_at: int | None = None,
):
    timestamp = int(payload["timestamp"])
    if timestamp % resolution or timestamp + resolution > fetched or not payload["data"]:
        raise ValueError("Require a nonempty completed, aligned bucket")
    content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(content).hexdigest()
    destination = root / f"{resolution}s" / f"{timestamp}-{digest[:16]}"
    if destination.exists():
        return {"status": "already_archived", "path": str(destination), "timestamp": timestamp}
    destination.parent.mkdir(parents=True, exist_ok=True)
    mapping_by_id = {int(row["id"]): row for row in mapping}
    rows = []
    for item, raw in payload["data"].items():
        high, low = raw.get("avgHighPrice"), raw.get("avgLowPrice")
        for p in [high, low]:
            if p is not None and (not isinstance(p, int) or p <= 0):
                raise ValueError(
                    "v1 collector requires positive integer prices; preserve raw response on API changes"
                )
        hv, lv = raw["highPriceVolume"], raw["lowPriceVolume"]
        if not isinstance(hv, int) or not isinstance(lv, int) or min(hv, lv) < 0:
            raise ValueError("Invalid volumes")
        item_mapping = mapping_by_id.get(int(item), {})
        rows.append(
            {
                "item_id": int(item),
                "timestamp": timestamp,
                "avg_high_price": high,
                "avg_low_price": low,
                "high_price_volume": hv,
                "low_price_volume": lv,
                # Mapping fetched now is usable only from this fetch onward.
                "buy_limit": item_mapping.get("limit"),
                "metadata_status": "mapping_at_fetch",
                "metadata_available_at": mapping_fetched_at or fetched,
                "source_interval_seconds": resolution,
                "resolution_seconds": resolution,
                "resolution_basis": "api_endpoint",
                "interval_unknown": False,
                "inverted_spread": high is not None and low is not None and low > high,
                "source": "wiki",
                "source_dataset": "forward_bulk",
                "fetched_at": fetched,
                "ingested_at": fetched,
                "available_at": fetched,
                # Freshness lower bound is publication lag; exact side times are unknown.
                "high_freshness_seconds": fetched - timestamp - resolution
                if hv and high is not None
                else None,
                "low_freshness_seconds": fetched - timestamp - resolution
                if lv and low is not None
                else None,
                "payload_sha256": digest,
            }
        )
    numeric = [
        "item_id",
        "timestamp",
        "avg_high_price",
        "avg_low_price",
        "high_price_volume",
        "low_price_volume",
        "buy_limit",
        "metadata_available_at",
        "source_interval_seconds",
        "resolution_seconds",
        "fetched_at",
        "ingested_at",
        "available_at",
        "high_freshness_seconds",
        "low_freshness_seconds",
    ]
    frame = pd.DataFrame(rows)
    for col in numeric:
        frame[col] = pd.array([r[col] for r in rows], dtype="int64[pyarrow]")
    temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=destination.parent))
    try:
        (temporary / "response.json").write_bytes(content)
        (temporary / "mapping.json").write_text(json.dumps(mapping, sort_keys=True))
        frame.to_parquet(temporary / "observations.parquet", index=False)
        manifest(
            temporary / "observations.parquet",
            source="wiki",
            rows=len(frame),
            endpoint=f"{BASE}/" + {300: "5m", 3600: "1h", 86400: "24h"}[resolution],
            fetched_at=fetched,
            resolution_seconds=resolution,
            timestamp=timestamp,
            payload_sha256=digest,
        )
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "status": "archived",
        "path": str(destination),
        "rows": len(frame),
        "timestamp": timestamp,
        "fetched_at": fetched,
        "lag_seconds": fetched - timestamp - resolution,
    }


def collect(root: Path | None = None, *, user_agent: str | None = None, resolution: int = 300):
    root = root or data_dir() / "forward" / "wiki"
    root.mkdir(parents=True, exist_ok=True)
    user_agent = user_agent or os.environ.get("OSRS_WIKI_USER_AGENT", "")
    with (root / ".collector.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Persist mapping revisions daily; a cached mapping is never fetched from the future.
        day = int(time.time()) // 86400
        cache = root / "mappings" / f"{day}.json"
        cache.parent.mkdir(exist_ok=True)
        if not cache.exists():
            mapping = fetch_json(f"{BASE}/mapping", user_agent)
            pending = cache.with_suffix(".partial")
            pending.write_text(json.dumps({"fetched_at": int(time.time()), "data": mapping}))
            pending.rename(cache)
        revision = json.loads(cache.read_text())
        endpoint = {300: "5m", 3600: "1h", 86400: "24h"}[resolution]
        payload = fetch_json(f"{BASE}/{endpoint}", user_agent)
        result = publish(
            root,
            payload,
            revision["data"],
            int(time.time()),
            resolution,
            mapping_fetched_at=revision["fetched_at"],
        )
        return result


def archive_observations(root: Path, *, resolution: int | None = None) -> pd.DataFrame:
    pattern = "*s" if resolution is None else f"{resolution}s"
    paths = sorted(root.glob(f"{pattern}/*/observations.parquet"))
    if not paths:
        return pd.DataFrame()
    frames = []
    for path in paths:
        metadata = json.loads(path.with_suffix(".manifest.json").read_text())
        from .data import sha256

        if sha256(path) != metadata["sha256"]:
            raise ValueError("Archive checksum mismatch")
        frames.append(pq.read_table(path).to_pandas(types_mapper=pd.ArrowDtype))
    frame = pd.concat(frames, ignore_index=True)
    # API revisions/re-fetches cannot duplicate volume or change prior paper inputs.
    return frame.sort_values("fetched_at").drop_duplicates(
        ["source", "resolution_seconds", "item_id", "timestamp"], keep="first"
    )
