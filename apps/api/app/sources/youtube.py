"""YouTube Data API v3, `videos?chart=mostPopular&regionCode=IN`.

Needs YOUTUBE_API_KEY. The chart is country-level only, so this adapter
supports the country region and nothing below it; state boards get their
YouTube signal indirectly, via the national rows the merge rolls in.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Region, RegionKind, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.youtube")

API_URL = "https://www.googleapis.com/youtube/v3/videos"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
WATCH_URL = "https://www.youtube.com/watch?v="


class YouTubeAdapter(TrendSource):
    name = SourceName.youtube
    # View counts are real audience signal but lag a trend by hours.
    weight = 0.6

    def __init__(self, client: httpx.AsyncClient | None = None, api_key: str | None = None) -> None:
        self._client = client
        self._api_key = api_key if api_key is not None else settings.youtube_api_key

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def supports(self, region: Region) -> bool:
        return region.kind is RegionKind.country

    async def fetch(self, region: Region, limit: int = 20) -> list[RawTrendItem]:
        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": "IN",
            "hl": "en_IN",
            "maxResults": str(min(limit, 50)),
            "key": self._api_key,
        }

        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=TIMEOUT)
        try:
            response = await client.get(API_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        finally:
            if own_client:
                await client.aclose()

        items = [
            self._to_item(video, rank)
            for rank, video in enumerate(payload.get("items", [])[:limit], start=1)
        ]
        log.info("fetched", region=region.code, items=len(items))
        return items

    @staticmethod
    def _to_item(video: dict[str, Any], rank: int) -> RawTrendItem:
        snippet = video.get("snippet") or {}
        stats = video.get("statistics") or {}
        video_id = str(video.get("id") or "")
        thumbnails = snippet.get("thumbnails") or {}
        thumb = (thumbnails.get("high") or thumbnails.get("default") or {}).get("url")

        return RawTrendItem(
            title=str(snippet.get("title") or "").strip(),
            rank=rank,
            volume=_as_int(stats.get("viewCount")),
            url=f"{WATCH_URL}{video_id}" if video_id else None,
            category=None,  # categoryId is numeric; names need a second call
            extra={
                "channel": snippet.get("channelTitle"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail": thumb,
                "likes": _as_int(stats.get("likeCount")),
                "tags": list(snippet.get("tags") or [])[:8],
            },
        )


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
