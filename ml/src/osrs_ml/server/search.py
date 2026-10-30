"""Search intent is data: a closed JSON schema, pure filters, optional CPU embeddings."""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .search_intent import blend, evaluate, parse_dsl

MODEL = "BAAI/bge-small-en-v1.5"


def cosine_scores(matrix, query):
    matrix, query = np.asarray(matrix, dtype=np.float32), np.asarray(query, dtype=np.float32)
    return (
        matrix @ query / np.maximum(np.linalg.norm(matrix, axis=1) * np.linalg.norm(query), 1e-12)
    )


def search_items(service):
    """Current Wiki names plus local metadata, with a durable offline fallback."""
    local = service.items()
    current = service.feed("mapping", 86400)
    rows = {int(r["id"]): r for r in local["data"]}
    for row in current["data"] if isinstance(current.get("data"), list) else []:
        item = int(row["id"])
        rows[item] = {
            **rows.get(item, {}),
            **row,
            "buy_limit": row.get("limit"),
            "high_alch": row.get("highalch"),
        }
    return {**local, "data": list(rows.values()), "stale": current.get("stale", False)}


def catalogue_hash(rows):
    values = sorted(
        (int(r.get("id", r.get("item_id", 0))), r.get("name", ""), r.get("examine", ""))
        for r in rows
    )
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def documents():
    root = Path(__file__).resolve().parents[4] / "docs"
    return [
        dict(key=f"doc:{p.name}", name=p.stem.replace("-", " "), body=p.read_text(), kind="Docs")
        for p in sorted(root.glob("*.md"))
    ]


class Search:
    def __init__(self, service, terminal):
        self.service, self.terminal = service, terminal
        self.path = service.root / "search/item-embeddings.parquet"
        self.lock = threading.RLock()
        self.encoder = None
        self.matrix = None
        self.ids = []
        self.loaded = None
        self.docs = documents()

    def catalogue(self):
        metadata = search_items(self.service)
        market = self.terminal.market()
        prices = {r["item_id"]: r for r in market["data"]}
        movers = {r["item_id"]: r.get("change_pct") for r in self.service.movers().get("data", [])}
        # Existing research capacity is only defined for its registered recipes.
        caps = {r["item_id"]: r.get("capacity") for r in self.service.alch().get("data", [])}
        rows = []
        for m in metadata["data"]:
            item = int(m["id"])
            row = {
                **m,
                **prices.get(item, {}),
                "item_id": item,
                "name": m["name"],
                "members": m.get("members"),
                "buy_limit": m.get("buy_limit"),
                "capacity": caps.get(item),
                "change_pct": movers.get(item),
            }
            spread, price = row.get("spread"), row.get("price")
            row["spread_pct"] = 100 * spread / price if spread is not None and price else None
            rows.append(row)
        return dict(
            data=rows,
            docs=self.docs,
            stale=market.get("stale", False),
            error=market.get("error"),
            fingerprint=catalogue_hash(rows),
        )

    def semantic(self, text, rows):
        if not self.path.exists():
            return {}, "Semantic unavailable: embedding sidecar missing; fuzzy + DSL active"
        with self.lock:
            fingerprint = catalogue_hash(rows)
            stamp = self.path.stat().st_mtime_ns
            if self.loaded != (stamp, fingerprint):
                table = pq.read_table(self.path)
                meta = table.schema.metadata or {}
                if meta.get(b"catalogue_sha256", b"").decode() != fingerprint:
                    return {}, "Semantic unavailable: catalogue changed; rebuild embeddings"
                if meta.get(b"model", b"").decode() != MODEL or meta.get(b"dimension") != b"384":
                    return {}, "Semantic unavailable: model/dimension mismatch; rebuild embeddings"
                self.ids = table["item_id"].to_pylist()
                self.matrix = np.asarray(table["embedding"].to_pylist(), dtype=np.float32)
                if (
                    self.matrix.shape != (len(rows), 384)
                    or set(self.ids) != {int(r.get("id", r.get("item_id", 0))) for r in rows}
                    or not np.isfinite(self.matrix).all()
                ):
                    return {}, "Semantic unavailable: invalid embedding sidecar"
                self.loaded = (stamp, fingerprint)
            if not text:
                return {}, "Semantic ready (CPU, 384 dimensions)"
            if self.encoder is None:
                from fastembed import TextEmbedding

                self.encoder = TextEmbedding(
                    MODEL, threads=2, providers=["CPUExecutionProvider"], local_files_only=True
                )
            vector = next(iter(self.encoder.query_embed(text)))
            scores = cosine_scores(self.matrix, vector)
            return dict(
                zip(self.ids, map(float, scores), strict=True)
            ), "Semantic ready (CPU, 384 dimensions)"

    def results(self, request):
        data = self.catalogue()
        intent = request.intent or parse_dsl(request.query)
        try:
            semantic, note = self.semantic(intent.text, data["data"])
        except Exception as exc:
            semantic, note = {}, f"Semantic unavailable ({type(exc).__name__}); fuzzy + DSL active"
        rows = []
        for row in data["data"]:
            if not evaluate(row, intent):
                continue
            item = row["item_id"]
            fuzzy = request.fuzzy.get(item, 0.0)
            sem = semantic.get(item)
            if intent.text and fuzzy <= 0 and (sem is None or sem < 0.6):
                continue
            rows.append(
                dict(
                    item_id=item,
                    name=row["name"],
                    score=blend(fuzzy, sem),
                    cosine=sem,
                    semantic_only=fuzzy <= 0 and bool(intent.text),
                    reasons=[f"{c.field} {row[c.field]:+g}" for c in intent.comparisons],
                )
            )
        indexed = {r["item_id"]: r for r in data["data"]}
        if intent.sort:
            rows.sort(
                key=lambda r: (
                    indexed[r["item_id"]].get(intent.sort) is not None,
                    (indexed[r["item_id"]].get(intent.sort) or 0)
                    * (1 if intent.descending else -1),
                ),
                reverse=True,
            )
        else:
            rows.sort(key=lambda r: (-r["score"], r["name"]))
        return dict(data=rows[: intent.limit], filter=intent.model_dump(), semantic=note)


def build(service, force=False):
    rows = search_items(service)["data"]
    path = service.root / "search/item-embeddings.parquet"
    fingerprint = catalogue_hash(rows)
    if path.exists() and not force:
        meta = pq.read_schema(path).metadata or {}
        if (
            meta.get(b"catalogue_sha256") == fingerprint.encode()
            and meta.get(b"model") == MODEL.encode()
        ):
            print(f"Unchanged catalogue/model; kept {path}")
            return
    from fastembed import TextEmbedding

    encoder = TextEmbedding(MODEL, threads=2, providers=["CPUExecutionProvider"])
    vectors = list(
        encoder.passage_embed([f"{r['name']}. {r.get('examine', '')}" for r in rows], batch_size=64)
    )
    table = pa.table(
        {
            "item_id": [int(r["id"]) for r in rows],
            "embedding": pa.array([v.tolist() for v in vectors], type=pa.list_(pa.float32(), 384)),
        }
    )
    table = table.replace_schema_metadata(
        {b"model": MODEL.encode(), b"dimension": b"384", b"catalogue_sha256": fingerprint.encode()}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path.with_suffix(".tmp"))
    path.with_suffix(".tmp").replace(path)
    print(f"{len(rows)} items × 384 CPU embeddings -> {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    from .service import Service

    build(Service(), args.force)
