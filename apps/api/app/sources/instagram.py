"""Instagram hashtag metrics via the Graph API.

This adapter cannot discover trends, and that is a property of the API rather
than of the implementation. There is no trending-hashtags endpoint: the Graph
API offers `ig_hashtag_search`, which resolves one hashtag you already know
to an id, and `{id}/top_media`, which returns that hashtag's top posts. So
Instagram answers "how big is #AsiaCupFinal" and never "what is trending".

That makes it an enricher, not a discoverer, and the interface reflects it:

  - `measure()` is the real entry point. Given hashtags from somewhere that
    does discover — the curator's output, the other adapters — it returns
    what Instagram knows about each.
  - `fetch()` exists because TrendSource requires it, and returns nothing
    without candidate hashtags. It does not invent them from the region name:
    "#Maharashtra" is not a trend, and a board row sourced from it would be
    a number attached to a topic nobody is posting about.

Two limits worth knowing before relying on it. `ig_hashtag_search` allows 30
unique hashtags per Business account per rolling 7 days — not 30 calls, 30
distinct hashtags — so ids are worth caching and a board of 20 topics would
spend two thirds of a week's allowance in one cycle. And `top_media` returns
no media count on the media edge itself; the count comes from the hashtag
node, so both calls are needed per hashtag.

Unconfigured until IG_ACCESS_TOKEN and IG_BUSINESS_ID exist, at which point
`is_configured()` turns true and nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Region, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.instagram")

#: Pinned, because Graph deprecates versions on a schedule and an unpinned
#: base URL changes behaviour without a deploy.
API_VERSION = "v21.0"
API_BASE = f"https://graph.facebook.com/{API_VERSION}"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

#: Unique hashtags per Business account per rolling 7 days. Not per call.
WEEKLY_HASHTAG_LIMIT = 30

#: Fields on the media edge. `like_count` and `comments_count` are the only
#: engagement numbers Instagram exposes for a hashtag's top media.
MEDIA_FIELDS = "id,caption,like_count,comments_count,permalink"


@dataclass(slots=True)
class HashtagMetrics:
    """What Instagram knows about one hashtag."""

    hashtag: str
    #: Graph's node id for the hashtag, worth caching against the weekly cap.
    hashtag_id: str
    #: Posts carrying the tag. This is the figure that goes to
    #: trend_sources.volume, and it is a lifetime total rather than a
    #: velocity — #Cricket is enormous and always has been.
    media_count: int
    #: Likes and comments summed across the top media sampled. A rough
    #: current-activity signal, which media_count is not.
    engagement: int
    #: Permalink of the top post, so a marketer can look before posting.
    top_permalink: str | None = None


class InstagramHashtagAdapter(TrendSource):
    name = SourceName.instagram
    label = "Instagram"
    env_vars = ("IG_ACCESS_TOKEN", "IG_BUSINESS_ID")
    #: Lowest of all sources. media_count is lifetime, so on its own it ranks
    #: evergreen tags above today's story; it is useful as a per-platform
    #: number on a topic found elsewhere, not as a ranking signal.
    weight = 0.3

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        access_token: str | None = None,
        business_id: str | None = None,
    ) -> None:
        self._client = client
        self._access_token = access_token if access_token is not None else settings.ig_access_token
        self._business_id = business_id if business_id is not None else settings.ig_business_id
        #: hashtag -> node id, for the weekly unique-hashtag cap.
        self._ids: dict[str, str] = {}

    def is_configured(self) -> bool:
        return bool(self._access_token and self._business_id)

    def supports(self, region: Region) -> bool:
        """Hashtags are global on Instagram; there is no region parameter.

        True everywhere rather than country-only, because the hashtags being
        measured are a region's topics even though the counts are worldwide.
        """
        return True

    async def fetch(self, region: Region, limit: int = 20) -> list[RawTrendItem]:
        """Nothing, by design. See the module docstring.

        Returning [] rather than raising: an adapter that cannot contribute to
        discovery is not a failure, and the orchestrator records an empty
        snapshot the same way it does for an unconfigured source.
        """
        if not self.is_configured():
            log.info(
                "not configured",
                region=region.code,
                reason="IG_ACCESS_TOKEN/IG_BUSINESS_ID are not set",
            )
            return []

        log.info(
            "no discovery endpoint; use measure() with candidate hashtags",
            region=region.code,
        )
        return []

    async def measure(self, hashtags: list[str]) -> list[HashtagMetrics]:
        """What Instagram knows about each of `hashtags`, in input order.

        A hashtag Instagram will not resolve is skipped rather than recorded
        as zero: zero posts and "Instagram declined to answer" are different
        claims, and the second must not be published as the first.
        """
        if not self.is_configured():
            log.info("not configured", reason="IG_ACCESS_TOKEN/IG_BUSINESS_ID are not set")
            return []

        # Keyed by lowercase, because Instagram's hashtags are
        # case-insensitive — the node for #AsiaCupFinal is named
        # "asiacupfinal". Deduping on the spelling as given would resolve
        # #AsiaCupFinal and #asiacupfinal separately and spend two of only
        # thirty weekly slots on one tag. The first spelling seen is kept for
        # display, since that is what the caller wrote.
        canonical: dict[str, str] = {}
        for raw in hashtags:
            name = (raw or "").lstrip("#").strip()
            if name:
                canonical.setdefault(name.casefold(), name)
        if not canonical:
            return []

        unresolved = [key for key in canonical if key not in self._ids]
        if len(unresolved) > WEEKLY_HASHTAG_LIMIT:
            # Said out loud rather than silently truncated: the caller is
            # spending a weekly allowance it cannot see, and a short result
            # would otherwise read as "Instagram had nothing for the rest".
            log.warning(
                "more unique hashtags than the weekly allowance",
                asked=len(unresolved),
                limit=WEEKLY_HASHTAG_LIMIT,
                skipped=len(unresolved) - WEEKLY_HASHTAG_LIMIT,
            )
            allowed = set(unresolved[:WEEKLY_HASHTAG_LIMIT])
        else:
            allowed = set(unresolved)

        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=TIMEOUT)
        try:
            out: list[HashtagMetrics] = []
            for key, display in canonical.items():
                if key not in self._ids and key not in allowed:
                    continue
                metrics = await self._measure_one(client, key, display)
                if metrics is not None:
                    out.append(metrics)
        finally:
            if own_client:
                await client.aclose()
        return out

    async def _measure_one(
        self, client: httpx.AsyncClient, key: str, display: str
    ) -> HashtagMetrics | None:
        """`key` is the casefolded name used for the cache and the API;
        `display` is the spelling the caller wrote."""
        hashtag = key
        hashtag_id = self._ids.get(key)
        if hashtag_id is None:
            hashtag_id = await self._resolve(client, key)
            if hashtag_id is None:
                return None
            self._ids[key] = hashtag_id

        node = await self._get(
            client,
            f"{API_BASE}/{hashtag_id}",
            {"fields": "id,name,media_count"},
            hashtag,
        )
        if node is None:
            return None

        media = await self._get(
            client,
            f"{API_BASE}/{hashtag_id}/top_media",
            {"user_id": self._business_id, "fields": MEDIA_FIELDS, "limit": "10"},
            hashtag,
        )
        posts = list((media or {}).get("data") or [])

        return HashtagMetrics(
            hashtag=f"#{display}",
            hashtag_id=hashtag_id,
            media_count=int(node.get("media_count") or 0),
            engagement=sum(
                int(p.get("like_count") or 0) + int(p.get("comments_count") or 0) for p in posts
            ),
            top_permalink=str(posts[0].get("permalink")) if posts else None,
        )

    async def _resolve(self, client: httpx.AsyncClient, hashtag: str) -> str | None:
        body = await self._get(
            client,
            f"{API_BASE}/ig_hashtag_search",
            {"user_id": self._business_id, "q": hashtag},
            hashtag,
        )
        data = list((body or {}).get("data") or [])
        return str(data[0].get("id")) if data and data[0].get("id") else None

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, str],
        hashtag: str,
    ) -> dict[str, Any] | None:
        """One Graph call. None where Instagram declined, which is not zero.

        Graph answers 400 for a hashtag it will not serve — banned, or simply
        unknown — and that is per hashtag rather than a reason to abandon the
        batch. An expired token is a 190 inside a 400, and that *is* worth
        raising, because every remaining hashtag will fail the same way and a
        silent empty result would read as "none of these tags exist".
        """
        try:
            response = await client.get(url, params={**params, "access_token": self._access_token})
        except httpx.HTTPError as exc:
            log.warning("graph call failed", hashtag=hashtag, error=str(exc)[:120])
            return None

        if response.status_code == 400:
            error = ((response.json() or {}).get("error") or {}) if response.content else {}
            if int(error.get("code") or 0) in (102, 190):
                raise httpx.HTTPStatusError(
                    f"instagram token rejected: {error.get('message')}",
                    request=response.request,
                    response=response,
                )
            log.info(
                "hashtag not served, skipping",
                hashtag=hashtag,
                message=str(error.get("message") or "")[:120],
            )
            return None

        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else None
