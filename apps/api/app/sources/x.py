"""X trends, via `GET /2/trends/by/woeid/:woeid`.

The only source here that is billed per request, which shapes everything
below. Two independent guards, and they fail in opposite directions on
purpose:

  - a per-region interval claim, so a region is pulled at most once per
    X_PULL_INTERVAL_MINUTES however often the beat runs. The ingest schedule
    is 30 minutes and the default interval is 120, so this is the difference
    between 12 requests a day per region and 48. If Redis is down the claim
    succeeds and we spend more than intended.
  - a hard daily cap, X_DAILY_CAP, counted in Redis so the api can report it
    and the worker cannot exceed it. If Redis is down this falls back to an
    in-process count, which is a weaker ceiling but still a ceiling.

A region is pulled by WOEID. India has its own; a state has none, so it rolls
up the WOEIDs of its seeded cities — `Region.woeids_for_rollup` — and each one
is a separate billed request, which is why the cap counts requests rather
than regions.

Status as of 2026-10-27: the account's credits are exhausted, so every call
returns

    HTTP 402 {"detail":"credits depleted", ...}

Authentication is fine — the response carries x-rate-limit-remaining, so the
request was accounted. That means this adapter is correct against the
documented response shape and the recorded fixtures, and unverified against a
live 200. The shape below is from the API reference, not from a capture.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.budget import DailyBudget, claim_interval
from app.core.config import settings
from app.core.hashtags import literal_hashtags
from app.core.logging import get_logger
from app.models import Region, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.x")

API_BASE = "https://api.x.com/2/trends/by/woeid"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

#: Named so the daily counter is readable in Redis and in /health.
BUDGET_NAME = "x-requests"


class CreditsDepleted(RuntimeError):
    """HTTP 402. Not a rate limit and not a bug — the account needs topping up.

    Its own type because the handling differs: a 429 is worth waiting out, a
    402 is worth telling someone about, and neither should look like the
    adapter being broken.
    """


class XAdapter(TrendSource):
    name = SourceName.x
    label = "X"
    env_vars = ("X_BEARER_TOKEN",)
    # City-level and fast, so it outranks news but not Trends' own volume.
    weight = 0.8

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        bearer_token: str | None = None,
        daily_cap: int | None = None,
        pull_interval_minutes: int | None = None,
    ) -> None:
        self._client = client
        self._bearer_token = bearer_token if bearer_token is not None else settings.x_bearer_token
        self._interval = (
            pull_interval_minutes
            if pull_interval_minutes is not None
            else settings.x_pull_interval_minutes
        )
        self._budget = DailyBudget(
            daily_cap if daily_cap is not None else settings.x_daily_cap,
            name=BUDGET_NAME,
        )

    def is_configured(self) -> bool:
        return bool(self._bearer_token)

    def supports(self, region: Region) -> bool:
        # Reads `children` for anything without its own WOEID, so callers
        # must eager-load them — see the note on woeids_for_rollup.
        return bool(region.woeids_for_rollup)

    async def requests_used_today(self) -> int:
        """What /health reports. Counted across every WOEID, not per region."""
        return self._budget.limit - await self._budget.remaining()

    async def fetch(self, region: Region, limit: int = 20) -> list[RawTrendItem]:
        if not self.is_configured():
            log.info("not configured", region=region.code, reason="X_BEARER_TOKEN is not set")
            return []

        woeids = region.woeids_for_rollup
        if not woeids:
            return []

        if not await claim_interval(f"x:pulled:{region.code}", self._interval * 60):
            # Not an error, and not worth a warning every half hour: this is
            # the guard doing its job.
            log.info(
                "pulled recently, skipping",
                region=region.code,
                interval_minutes=self._interval,
            )
            return []

        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=TIMEOUT)
        try:
            # Keyed by the trend name so a topic trending in two of a state's
            # cities is one row, carrying the better rank and the larger count.
            merged: dict[str, dict[str, Any]] = {}
            for woeid in woeids:
                for rank, trend in enumerate(await self._woeid(client, woeid), start=1):
                    name = str(trend.get("trend_name") or "").strip()
                    if not name:
                        continue
                    count = _as_int(trend.get("tweet_count"))
                    existing = merged.get(name.casefold())
                    if existing is None:
                        merged[name.casefold()] = {
                            "name": name,
                            "rank": rank,
                            "count": count or 0,
                            "woeid": woeid,
                        }
                    else:
                        existing["rank"] = min(existing["rank"], rank)
                        existing["count"] = max(existing["count"], count or 0)
        finally:
            if own_client:
                await client.aclose()

        ranked = sorted(merged.values(), key=lambda t: (t["rank"], -t["count"]))[:limit]
        items = [
            RawTrendItem(
                title=entry["name"],
                rank=position,
                volume=entry["count"] or None,
                url=f"https://x.com/search?q={httpx.QueryParams({'q': entry['name']})['q']}",
                category=None,
                extra={
                    "woeid": entry["woeid"],
                    # X trends are frequently hashtags already, so the tag is
                    # whatever was literally there rather than camel-cased
                    # from a headline.
                    "hashtags": literal_hashtags(entry["name"]),
                },
            )
            for position, entry in enumerate(ranked, start=1)
        ]
        log.info("fetched", region=region.code, woeids=len(woeids), items=len(items))
        return items

    async def _woeid(self, client: httpx.AsyncClient, woeid: int) -> list[dict[str, Any]]:
        """One billed request. Spends the daily budget before making it."""
        if not await self._budget.spend():
            # Stops rather than queues: a budget that waits would hold the
            # whole ingest cycle open until midnight.
            log.warning(
                "daily request cap reached, skipping",
                woeid=woeid,
                cap=self._budget.limit,
            )
            return []

        response = await client.get(
            f"{API_BASE}/{woeid}",
            headers={"Authorization": f"Bearer {self._bearer_token}"},
        )

        if response.status_code == 402:
            raise CreditsDepleted(
                f"x returned 402 for woeid {woeid}: {_detail(response)}. "
                "The credentials are valid; the account needs credits."
            )
        response.raise_for_status()

        body = response.json()
        return list((body or {}).get("data") or []) if isinstance(body, dict) else []


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:160]
    if isinstance(body, dict):
        return str(body.get("detail") or body.get("title") or body)[:160]
    return str(body)[:160]


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
