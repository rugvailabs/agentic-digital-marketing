"""YouTube Data API v3, `videos?chart=mostPopular&regionCode=IN`.

Needs YOUTUBE_API_KEY. The chart is country-level only, so this adapter
supports the country region and nothing below it; state boards get their
YouTube signal indirectly, via the national rows the merge rolls in.

Six charts rather than one: the overall chart plus five categories. The
overall chart is dominated by music and film, which on any given day is most
of the top twenty — so a sports story or a news story that is genuinely
trending never appears on it. Asking per category is the only way the chart
reports anything but entertainment.

It also gets the category name for free. The old single call left
`category=None` because categoryId is numeric and naming it needs a second
request; querying by category means we already know which one answered.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.hashtags import literal_hashtags
from app.core.logging import get_logger
from app.models import Region, RegionKind, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.youtube")

API_URL = "https://www.googleapis.com/youtube/v3/videos"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
WATCH_URL = "https://www.youtube.com/watch?v="

#: Category name -> videoCategoryId, for the per-category charts. These five
#: because they are what an Indian marketing team posts against; the ids are
#: YouTube's fixed global ones.
#:
#: None is the overall chart and is listed first so that a video appearing in
#: both keeps the overall chart's view count, which is the complete figure.
CATEGORIES: dict[str, str | None] = {
    "Trending": None,
    "Music": "10",
    "Gaming": "20",
    "Sports": "17",
    "Entertainment": "24",
    "News & Politics": "25",
}

#: Per chart. Six charts at 50 would be 300 videos to rank 20 from, and
#: videos.list bills per call rather than per result, so the cost is the same
#: either way — but the merge only ever reads the top of the list.
PER_CHART = 25


class YouTubeAdapter(TrendSource):
    name = SourceName.youtube
    label = "YouTube"
    env_vars = ("YOUTUBE_API_KEY",)
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
        if not self.is_configured():
            log.info("not configured", region=region.code, reason="YOUTUBE_API_KEY is not set")
            return []

        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=TIMEOUT)
        try:
            # Keyed by video id: the overall chart and a category chart share
            # videos, and the same video twice is not two trends.
            seen: dict[str, tuple[str, dict[str, Any]]] = {}
            for label, category_id in CATEGORIES.items():
                for video in await self._chart(client, category_id, label):
                    video_id = str(video.get("id") or "")
                    if video_id and video_id not in seen:
                        # First writer wins, and "Trending" is iterated
                        # first, so a video on the overall chart keeps that
                        # label rather than being relabelled by a category.
                        seen[video_id] = (label, video)
        finally:
            if own_client:
                await client.aclose()

        ranked = sorted(seen.values(), key=lambda pair: _views(pair[1]), reverse=True)[:limit]
        items = [
            self._to_item(video, rank, label) for rank, (label, video) in enumerate(ranked, start=1)
        ]
        log.info("fetched", region=region.code, items=len(items), charts=len(CATEGORIES))
        return items

    async def _chart(
        self, client: httpx.AsyncClient, category_id: str | None, label: str
    ) -> list[dict[str, Any]]:
        """One chart, or nothing if YouTube will not serve that category.

        A category with no chart for a region answers 400 rather than an
        empty list, and that must not cost the other five: a 400 on Gaming
        is not a reason to report that nothing is trending in India.
        """
        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": "IN",
            "hl": "en_IN",
            "maxResults": str(PER_CHART),
            "key": self._api_key,
        }
        if category_id:
            params["videoCategoryId"] = category_id

        try:
            response = await client.get(API_URL, params=params)
        except httpx.HTTPError as exc:
            log.warning("chart failed", chart=label, error=str(exc)[:120])
            return []

        if response.status_code == 400:
            log.info("chart not served for this region, skipping", chart=label)
            return []
        response.raise_for_status()
        return list((response.json() or {}).get("items") or [])

    @staticmethod
    def _to_item(video: dict[str, Any], rank: int, chart: str) -> RawTrendItem:
        snippet = video.get("snippet") or {}
        stats = video.get("statistics") or {}
        video_id = str(video.get("id") or "")
        thumbnails = snippet.get("thumbnails") or {}
        thumb = (thumbnails.get("high") or thumbnails.get("default") or {}).get("url")
        title = str(snippet.get("title") or "").strip()
        description = str(snippet.get("description") or "")

        return RawTrendItem(
            title=title,
            rank=rank,
            volume=_as_int(stats.get("viewCount")),
            url=f"{WATCH_URL}{video_id}" if video_id else None,
            # The chart that answered, which is the category name without a
            # second request for videoCategories.list.
            category=chart,
            extra={
                "channel": snippet.get("channelTitle"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail": thumb,
                "likes": _as_int(stats.get("likeCount")),
                # `tags` are the uploader's keywords and carry no "#". The
                # hashtags creators actually publish are written into the
                # title and the top of the description, so those are read
                # separately and kept separately.
                "tags": list(snippet.get("tags") or [])[:8],
                "hashtags": literal_hashtags(title, description),
            },
        )


def _views(video: dict[str, Any]) -> int:
    """View count for ranking. Absent counts sort last rather than crashing:
    a video with statistics hidden is still a video that charted."""
    return _as_int((video.get("statistics") or {}).get("viewCount")) or 0


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
