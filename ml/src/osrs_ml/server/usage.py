"""Private OpenRouter credentials, cached public balance readings."""

import asyncio
import math
import os
import time
from pathlib import Path

import httpx


def load_key(env_path):
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        for line in Path(env_path).read_text().splitlines():
            name, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and name.strip() == "OPENROUTER_API_KEY":
                return value.strip().strip("\"'")
    except OSError:
        pass
    return None


class Usage:
    def __init__(self, client=None, env_path=None):
        self.client = client or httpx.AsyncClient(timeout=10)
        self.env_path = env_path or Path.home() / ".hermes/.env"
        self.reading = None
        self.checked_at = 0
        self.lock = asyncio.Lock()

    def invalidate(self):
        self.checked_at = 0

    async def get(self):
        async with self.lock:
            if time.time() - self.checked_at < 60:
                return self.reading
            now = time.time()
            try:
                key = load_key(self.env_path)
                if not key:
                    raise ValueError("OPENROUTER_API_KEY is unavailable")
                headers = {"Authorization": f"Bearer {key}"}
                responses = await asyncio.gather(
                    *[
                        self.client.get(f"https://openrouter.ai/api/v1/{route}", headers=headers)
                        for route in ("credits", "key")
                    ]
                )
                credits, info = [r.raise_for_status().json()["data"] for r in responses]
                total, used = float(credits["total_credits"]), float(credits["total_usage"])
                for number in [
                    total,
                    used,
                    *(
                        info.get(k)
                        for k in ("usage_daily", "usage_weekly", "usage_monthly", "limit")
                    ),
                ]:
                    if number is not None and (
                        not isinstance(number, (int, float))
                        or not math.isfinite(number)
                        or number < 0
                    ):
                        raise ValueError("Invalid upstream balance")
                self.reading = dict(
                    total_credits=total,
                    total_usage=used,
                    remaining=total - used,
                    percent_remaining=100 * (total - used) / total if total else 0,
                    usage_daily=info.get("usage_daily"),
                    usage_weekly=info.get("usage_weekly"),
                    usage_monthly=info.get("usage_monthly"),
                    hard_key_limit=info.get("limit"),
                    hard_key_limit_set=info.get("limit") is not None,
                    timestamp=now,
                    stale=False,
                    error=None,
                )
            except Exception as exc:
                # Do not expose upstream bodies/headers or exception strings containing secrets.
                error = (
                    "OPENROUTER_API_KEY is unavailable"
                    if isinstance(exc, ValueError) and not load_key(self.env_path)
                    else f"OpenRouter reading failed ({type(exc).__name__})"
                )
                self.reading = {
                    **(
                        self.reading
                        or dict(
                            total_credits=None,
                            total_usage=None,
                            remaining=None,
                            percent_remaining=None,
                            usage_daily=None,
                            usage_weekly=None,
                            usage_monthly=None,
                            hard_key_limit=None,
                            hard_key_limit_set=None,
                            timestamp=None,
                        )
                    ),
                    "stale": True,
                    "error": error,
                }
            self.checked_at = now
            return self.reading

    async def close(self):
        await self.client.aclose()
