"""Closed, validated search intent. LLM output is JSON data, never executable code."""

import math
import os
import re
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .usage import load_key

FieldName = Literal["price", "alch_gap", "spread", "spread_pct", "volume", "buy_limit", "capacity"]
FIELDS = set(FieldName.__args__)


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: FieldName
    op: Literal[">", ">=", "<", "<=", "="]
    value: float = Field(allow_inf_nan=False)


class Filter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(
        "",
        max_length=2000,
        description="Only item names or descriptive search words. Exclude filter, membership, comparison, sort and limit prose.",
    )
    members: bool | None = None
    comparisons: list[Comparison] = Field(default_factory=list, max_length=30)
    sort: FieldName | None = None
    descending: bool = True
    limit: int = Field(50, ge=1, le=200)


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field("", max_length=2000)
    intent: Filter | None = None
    fuzzy: dict[int, float] = Field(default_factory=dict, max_length=10000)


def parse_dsl(query: str) -> Filter:
    result = Filter()
    words = []
    for token in query.split():
        low = token.lower()
        if low in ("members", "-members", "free"):
            result.members = low == "members"
        elif low.startswith("sort:"):
            field = low[5:]
            result.descending = not field.startswith("+")
            result.sort = (
                field.lstrip("+-").replace("alch", "alch_gap")
                if field.lstrip("+-") == "alch"
                else field.lstrip("+-")
            )
            if result.sort not in FIELDS:
                raise ValueError("Unknown sort field")
        elif low.startswith("limit:"):
            result.limit = int(low[6:])
            if not 1 <= result.limit <= 200:
                raise ValueError("limit must be 1..200")
        else:
            match = re.fullmatch(r"([a-z_]+)(>=|<=|>|<|=)([-+]?\d+(?:\.\d+)?)([km]?)", low)
            if match:
                field, op, value, suffix = match.groups()
                field = "alch_gap" if field == "alch" else field
                result.comparisons.append(
                    Comparison(
                        field=field,
                        op=op,
                        value=float(value) * {"": 1, "k": 1000, "m": 1000000}[suffix],
                    )
                )
            elif re.search(r"[<>]|^(?:price|alch|spread|volume|buy_limit|capacity).*=", low):
                raise ValueError(f"Invalid comparison: {token}")
            else:
                words.append(token)
    result.text = " ".join(words)
    return Filter.model_validate(result.model_dump())


def evaluate(row: dict, intent: Filter) -> bool:
    if intent.members is not None and row.get("members") is not intent.members:
        return False
    for c in intent.comparisons:
        value = row.get(c.field)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
        if not {
            ">": value > c.value,
            ">=": value >= c.value,
            "<": value < c.value,
            "<=": value <= c.value,
            "=": value == c.value,
        }[c.op]:
            return False
    return True


def blend(fuzzy: float, cosine: float | None) -> float:
    return 0.75 * max(0.0, min(1.0, fuzzy)) + 0.25 * max(0.0, min(1.0, cosine or 0.0))


async def parse_intent(query: str, client=None):
    try:
        dsl = parse_dsl(query)
    except ValueError as exc:
        return dict(filter=Filter(text=query).model_dump(), source="dsl", error=str(exc))
    # Deterministic tokens remain authoritative. An LLM parses only remaining prose.
    key = load_key(Path.home() / ".hermes/.env")
    model = os.getenv("OSRS_SEARCH_LLM_MODEL")
    if not model or not key or not dsl.text:
        return dict(
            filter=dsl.model_dump(), source="dsl", note="LLM unavailable/unconfigured; DSL only"
        )
    owned = client is None
    client = client or httpx.AsyncClient(timeout=12)
    try:
        schema = Filter.model_json_schema()
        schema["required"] = list(schema["properties"])
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=dict(
                model=model,
                temperature=0,
                max_tokens=700,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "search_filter", "strict": True, "schema": schema},
                },
                messages=[
                    {
                        "role": "system",
                        "content": "Convert item search intent to the supplied JSON schema. Only parse intent, never generate items. text MUST contain ONLY remaining item-name or descriptive words, NEVER membership, price, alchemy, limit or sort instructions. Strip filter prose completely. Examples: 'member boots under 500000 coins sorted by highest alchemy profit' becomes text='boots', members=true, comparisons=[{field:'price',op:'<',value:500000}], sort='alch_gap'. 'cheap free swords over 100 volume' becomes text='swords', members=false, comparisons=[{field:'volume',op:'>',value:100}], sort='price', descending=false. alch means alch_gap. Default limit=50. Default descending=true unless cheapest/ascending. Return JSON only.",
                    },
                    {"role": "user", "content": dsl.text},
                ],
            ),
        )
        response.raise_for_status()
        intent = Filter.model_validate_json(response.json()["choices"][0]["message"]["content"])
        intent.comparisons += dsl.comparisons
        if dsl.members is not None:
            intent.members = dsl.members
        if dsl.sort is not None:
            intent.sort, intent.descending = dsl.sort, dsl.descending
        if re.search(r"\blimit:", query):
            intent.limit = dsl.limit
        intent = Filter.model_validate(intent.model_dump())
        return dict(
            filter=intent.model_dump(),
            source="llm",
            note="Validated intent; edit query or press Ctrl+E to edit DSL",
        )
    except Exception as exc:
        return dict(
            filter=dsl.model_dump(),
            source="dsl",
            note=f"LLM unavailable ({type(exc).__name__}); DSL only",
        )
    finally:
        if owned:
            await client.aclose()
