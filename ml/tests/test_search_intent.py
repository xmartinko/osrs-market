import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from osrs_ml.server.search_intent import Filter, blend, evaluate, parse_dsl, parse_intent


@pytest.mark.parametrize(
    "query,text,members",
    [
        ("dragon jav tips", "dragon jav tips", None),
        ("ags", "ags", None),
        ("members alch>200 sort:alch_gap", "", True),
        ("free rune price>=1k volume<2m limit:12", "rune", False),
        ("-members Épée café", "Épée café", False),
    ],
)
def test_dsl(query, text, members):
    f = parse_dsl(query)
    assert (f.text, f.members) == (text, members)


@pytest.mark.parametrize(
    "query", ["unknown>1", "price>NaN", "sort:shell", "limit:0", "limit:201", "price>>1"]
)
def test_bad_dsl(query):
    with pytest.raises((ValueError, ValidationError)):
        parse_dsl(query)


def test_filter_missing_unicode_and_blend():
    f = parse_dsl("members alch>200 price<1k")
    assert evaluate(dict(members=True, alch_gap=289, price=500), f)
    assert not evaluate(dict(members=True, alch_gap=None, price=500), f)
    assert not evaluate(dict(members=None, alch_gap=289, price=500), f)
    assert not evaluate(dict(members=True, alch_gap=float("nan"), price=500), f)
    assert blend(1, None) == 0.75
    assert blend(0, 1) == 0.25


def test_llm_json_only_and_dsl_authority(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OSRS_SEARCH_LLM_MODEL", "test-model")

    async def exercise(payload):
        def reply(request):
            return httpx.Response(200, json={"choices": [{"message": {"content": payload}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            return await parse_intent("show cheap member boots members price<5000", client)

    f = Filter(text="boots", members=False, sort="alch_gap").model_dump()
    parsed = asyncio.run(exercise(json.dumps(f)))
    assert parsed["source"] == "llm"
    assert parsed["filter"]["text"] == "boots"
    assert parsed["filter"]["members"] is True
    assert parsed["filter"]["comparisons"] == [dict(field="price", op="<", value=5000)]
    parsed = asyncio.run(exercise('{"execute":"print(1)"}'))
    assert parsed["source"] == "dsl"
    assert "unavailable" in parsed["note"]
    parsed = asyncio.run(exercise('import os; os.system("true")'))
    assert parsed["source"] == "dsl"
