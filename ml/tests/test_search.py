import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from test_server import fixture_service

from osrs_ml.server.app import create_app
from osrs_ml.server.search import (
    MODEL,
    Search,
    catalogue_hash,
)
from osrs_ml.server.search_intent import Query
from osrs_ml.server.terminal import Terminal


def test_endpoints_and_offline_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("OSRS_SEARCH_LLM_MODEL", raising=False)
    service = fixture_service(tmp_path)
    with TestClient(create_app(service)) as client:
        catalogue = client.get("/api/search/catalogue").json()
        assert len(catalogue["data"]) == 5
        assert catalogue["docs"]
        parsed = client.post(
            "/api/search/parse", json={"query": "members alch>200 sort:alch_gap"}
        ).json()
        assert parsed["filter"]["comparisons"] == [dict(field="alch_gap", op=">", value=200)]
        result = client.post("/api/search", json={"query": "855", "fuzzy": {"855": 1}}).json()
        assert result["data"][0]["item_id"] == 855
        assert "sidecar missing" in result["semantic"]
        assert (
            client.post("/api/search", json={"intent": {"execute": "rm -rf /"}}).status_code == 422
        )
        assert (
            client.post(
                "/api/search",
                json={"intent": {"comparisons": [dict(field="shell", op=">", value=1)]}},
            ).status_code
            == 422
        )


def test_embeddings_metadata_and_catalogue_invalidation(tmp_path):
    service = fixture_service(tmp_path)
    search = Search(service, Terminal(service))
    rows = service.items()["data"]
    search.path.parent.mkdir(parents=True)
    table = pa.table(
        {"item_id": [r["id"] for r in rows], "embedding": [[1.0] + [0.0] * 383 for _ in rows]}
    )
    table = table.replace_schema_metadata(
        {
            b"model": MODEL.encode(),
            b"dimension": b"384",
            b"catalogue_sha256": catalogue_hash(rows).encode(),
        }
    )
    pq.write_table(table, search.path)
    scores, note = search.semantic("", rows)
    assert "ready" in note

    class Encoder:
        def query_embed(self, text):
            yield np.array([1.0] + [0.0] * 383)

    search.encoder = Encoder()
    scores, note = search.semantic("rune", rows)
    assert scores[855] == 1
    assert "catalogue changed" in search.semantic("rune", [*rows, dict(id=999, name="new")])[1]
    result = search.results(Query(query="rune", fuzzy={855: 1}))
    assert result["data"][0]["item_id"] == 855
    assert any(r["semantic_only"] for r in result["data"][1:])
