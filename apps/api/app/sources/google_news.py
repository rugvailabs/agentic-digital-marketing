"""Google News RSS, en-IN. No credentials required.

The country uses the top-stories feed; every other region uses a search feed
keyed on the region name, which is the only identifier Google News exposes for
Indian states and cities.
"""

from __future__ import annotations

import feedparser
import httpx

from app.core.logging import get_logger
from app.models import Region, RegionKind, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.google_news")

NATIONAL_FEED = "https://news.google.com/rss"
SEARCH_FEED = "https://news.google.com/rss/search"
# en-IN everywhere: Hinglish headlines come through, and ceid pins the edition.
LOCALE = {"hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
USER_AGENT = "TrendForge/0.1 (+https://github.com/trendforge)"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class GoogleNewsRSSAdapter(TrendSource):
    name = SourceName.google_news
    label = "Google News"
    env_vars = ()
    # Recency, not search demand: a headline being published says less about
    # audience interest than a Trends spike does.
    weight = 0.7

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def is_configured(self) -> bool:
        return True

    def supports(self, region: Region) -> bool:
        # Every region has a name, which is all the search feed needs.
        return True

    def feed_url(self, region: Region) -> tuple[str, dict[str, str]]:
        if region.kind is RegionKind.country:
            return NATIONAL_FEED, dict(LOCALE)
        return SEARCH_FEED, {"q": region.name, **LOCALE}

    async def fetch(self, region: Region, limit: int = 20) -> list[RawTrendItem]:
        url, params = self.feed_url(region)
        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            )
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            body = response.content
        finally:
            if own_client:
                await client.aclose()

        feed = feedparser.parse(body)
        items: list[RawTrendItem] = []
        for rank, entry in enumerate(feed.entries[:limit], start=1):
            publisher = _publisher(entry)
            title = _strip_publisher(str(entry.get("title", "")), publisher)
            if not title:
                continue
            items.append(
                RawTrendItem(
                    title=title,
                    rank=rank,
                    volume=None,
                    url=str(entry.get("link") or "") or None,
                    category=None,  # RSS carries no category for this edition
                    extra={"publisher": publisher, "published": entry.get("published")},
                )
            )

        log.info(
            "fetched", region=region.code, query=params.get("q", "top-stories"), items=len(items)
        )
        return items


def _publisher(entry: object) -> str | None:
    source = getattr(entry, "source", None) or (
        entry.get("source") if isinstance(entry, dict) else None
    )
    title = getattr(source, "title", None)
    if title is None and isinstance(source, dict):
        title = source.get("title")
    return str(title) if title else None


def _strip_publisher(title: str, publisher: str | None) -> str:
    """Google News appends " - Publisher" to every headline; the publisher is
    already available separately, and leaving it in wrecks dedupe (the same
    story syndicated by three outlets would read as three topics)."""
    title = title.strip()
    if publisher and title.endswith(f" - {publisher}"):
        return title[: -len(f" - {publisher}")].strip()
    # Fall back to the last " - " segment when <source> is missing.
    head, sep, _tail = title.rpartition(" - ")
    return (head if sep and len(head) > 20 else title).strip()
