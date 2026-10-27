"""Google Trends via trendspy. No credentials required.

`trending_now` serves both the country (`IN`) and state geos (`IN-MH`), which
is why states carry a `google_trends_geo` and cities don't — metro granularity
needs numeric DMA ids we don't have.

Rising related queries come from the same call. `trending_now` returns
`trend_keywords` per topic — eight of them, which are the queries Google
itself shows as rising alongside that trend ("cyclone arnab tracker",
"cyclone update in odisha") — and they cost nothing extra.

The explicit `related_queries` endpoint is not used by default, and that is
measured rather than assumed. Probed on 2026-10-27 from this machine it
raised TrendsQuotaExceededError; with the google.com referer the library
itself recommends, it stopped raising and returned `{"top": empty,
"rising": empty}` instead. An endpoint that answers successfully with nothing
is worse than one that fails, because the result reads as "this topic has no
rising queries". So it is opt-in behind TRENDS_RISING_QUERIES, and even when
enabled an empty answer falls back to `trend_keywords` rather than replacing
them with nothing.
"""

from __future__ import annotations

import asyncio
from typing import Any

from trendspy import Trends
from trendspy.constants import TREND_TOPICS

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Region, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.google_trends")

# How far back a topic still counts as "trending now".
LOOKBACK_HOURS = 24

#: Topics enriched with an explicit related_queries call when that is enabled.
#: One sequential request each, so only the head of the board is worth it.
ENRICH_TOP_N = 5

#: Window for the enrichment call. Short, because a 12-month default would
#: return queries that rose last spring.
ENRICH_TIMEFRAME = "now 7-d"

#: The library's own first suggestion for the quota error, and it does change
#: the outcome: without it the call raises, with it the call succeeds empty.
ENRICH_HEADERS = {"referer": "https://www.google.com/"}


class GoogleTrendsAdapter(TrendSource):
    name = SourceName.google_trends
    # The strongest signal we have: it is the only source that reports search
    # volume and is explicitly about trending rather than merely recent.
    weight = 1.0

    def __init__(self, client: Trends | None = None) -> None:
        self._client = client or Trends()

    def is_configured(self) -> bool:
        return True

    def supports(self, region: Region) -> bool:
        return bool(region.google_trends_geo)

    async def fetch(self, region: Region, limit: int = 20) -> list[RawTrendItem]:
        geo = region.google_trends_geo
        if not geo:
            return []

        # trendspy is synchronous; keep the event loop free.
        raw = await asyncio.to_thread(
            self._client.trending_now, geo=geo, language="en", hours=LOOKBACK_HOURS
        )
        items = [self._to_item(kw, rank) for rank, kw in enumerate(raw[:limit], start=1)]

        if settings.trends_rising_queries:
            await self._enrich(items, geo)

        log.info(
            "fetched",
            region=region.code,
            geo=geo,
            items=len(items),
            with_rising=sum(1 for i in items if i.extra.get("rising")),
        )
        return items

    async def _enrich(self, items: list[RawTrendItem], geo: str) -> None:
        """Replace `rising` with the explicit endpoint's answer where it has one.

        Only ever additive: a quota error, an exception or an empty frame all
        leave the `trend_keywords` already in place. The endpoint returning
        nothing must not be mistaken for the topic having no rising queries.
        """
        for item in items[:ENRICH_TOP_N]:
            try:
                result = await asyncio.to_thread(
                    self._client.related_queries,
                    item.title,
                    geo=geo,
                    timeframe=ENRICH_TIMEFRAME,
                    headers=ENRICH_HEADERS,
                )
            except Exception as exc:
                # Quota is the common case and is not an incident; the free
                # endpoint is unmetered and we already have its answer.
                log.info(
                    "rising queries unavailable",
                    topic=item.title[:48],
                    error=f"{type(exc).__name__}: {exc}"[:120],
                )
                continue

            queries = _rising_queries(result)
            if queries:
                item.extra["rising"] = queries
                item.extra["rising_source"] = "related_queries"

    @staticmethod
    def _to_item(kw: Any, rank: int) -> RawTrendItem:
        topics = list(getattr(kw, "topics", None) or [])
        category = TREND_TOPICS.get(topics[0]) if topics else None
        growth = getattr(kw, "volume_growth_pct", None)

        return RawTrendItem(
            title=str(getattr(kw, "keyword", "")).strip(),
            rank=rank,
            volume=getattr(kw, "volume", None),
            url=None,
            category=category,
            extra={
                "volume_growth_pct": growth,
                "normalized_keyword": getattr(kw, "normalized_keyword", None),
                # Related queries are the raw material for step 2's captions.
                "related": list(getattr(kw, "trend_keywords", None) or [])[:8],
                # The same list, named for what the curator is told it is:
                # the queries rising alongside this trend. Google surfaces
                # these on its own trending page, and they arrive free with
                # the call above rather than costing one request per topic.
                "rising": list(getattr(kw, "trend_keywords", None) or [])[:8],
                "rising_source": "trend_keywords",
                "started_timestamp": _first_timestamp(kw),
            },
        )


def _first_timestamp(kw: Any) -> int | None:
    ts = getattr(kw, "started_timestamp", None)
    if isinstance(ts, (list, tuple)) and ts:
        first = ts[0]
        return int(first) if isinstance(first, (int, float)) else None
    return int(ts) if isinstance(ts, (int, float)) else None


def _rising_queries(result: Any, limit: int = 8) -> list[str]:
    """The `rising` frame as a list of query strings, or nothing.

    `result` is a dict of pandas frames when the call succeeds, and the
    frames are routinely empty — so "no exception" is not the same as "has
    data", and every absence here has to land on the same empty list.
    """
    if not isinstance(result, dict):
        return []
    frame = result.get("rising")
    if frame is None or getattr(frame, "empty", True):
        return []
    for column in ("query", "Top query", "value"):
        if column in getattr(frame, "columns", []):
            return [str(v) for v in frame[column].tolist()[:limit] if str(v).strip()]
    return []
