"""Google Trends via trendspy. No credentials required.

`trending_now` serves both the country (`IN`) and state geos (`IN-MH`), which
is why states carry a `google_trends_geo` and cities don't — metro granularity
needs numeric DMA ids we don't have.
"""

from __future__ import annotations

import asyncio
from typing import Any

from trendspy import Trends
from trendspy.constants import TREND_TOPICS

from app.core.logging import get_logger
from app.models import Region, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.google_trends")

# How far back a topic still counts as "trending now".
LOOKBACK_HOURS = 24


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
        log.info("fetched", region=region.code, geo=geo, items=len(items))
        return items

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
                "started_timestamp": _first_timestamp(kw),
            },
        )


def _first_timestamp(kw: Any) -> int | None:
    ts = getattr(kw, "started_timestamp", None)
    if isinstance(ts, (list, tuple)) and ts:
        first = ts[0]
        return int(first) if isinstance(first, (int, float)) else None
    return int(ts) if isinstance(ts, (int, float)) else None
