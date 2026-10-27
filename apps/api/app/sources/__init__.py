"""Trend source registry.

Nothing outside this package constructs an adapter: callers ask for the
registry and respect `is_configured()`/`supports()`. Adding a source means
adding one line here.
"""

from app.models import Region
from app.sources.base import RawTrendItem, TrendSource
from app.sources.google_news import GoogleNewsRSSAdapter
from app.sources.google_trends import GoogleTrendsAdapter
from app.sources.instagram import InstagramHashtagAdapter
from app.sources.reddit import RedditAdapter
from app.sources.x import XAdapter
from app.sources.youtube import YouTubeAdapter

__all__ = [
    "GoogleNewsRSSAdapter",
    "GoogleTrendsAdapter",
    "InstagramHashtagAdapter",
    "RawTrendItem",
    "RedditAdapter",
    "TrendSource",
    "XAdapter",
    "YouTubeAdapter",
    "all_sources",
    "configured_source_names",
    "platform_catalog",
    "platforms_for_region",
    "source_weights",
]


def all_sources() -> list[TrendSource]:
    """Every known source, configured or not."""
    return [
        GoogleTrendsAdapter(),
        GoogleNewsRSSAdapter(),
        YouTubeAdapter(),
        RedditAdapter(),
        XAdapter(),
        InstagramHashtagAdapter(),
    ]


def configured_source_names() -> list[str]:
    return [s.name.value for s in all_sources() if s.is_configured()]


def source_weights() -> dict[str, float]:
    return {s.name.value: s.weight for s in all_sources()}


def platform_catalog() -> list[dict[str, object]]:
    """Every platform, whether it is wired up, and what it needs if not.

    Drives the filter chips and the settings page. Unconfigured platforms are
    in the list rather than omitted, because the UI renders them as "Connect"
    chips — a missing chip would read as a platform that does not exist, and
    `env_vars` is what lets the settings page name the variable to set rather
    than saying something is unavailable.
    """
    return [
        {
            "name": source.name.value,
            "label": source.label,
            "configured": source.is_configured(),
            "env_vars": list(source.env_vars),
            "weight": source.weight,
        }
        for source in all_sources()
    ]


def platforms_for_region(region: Region) -> list[str]:
    """Platforms that are configured *and* cover this region.

    Both halves matter and they fail differently. YouTube's chart is
    country-level, so it is configured everywhere and covers only India;
    Reddit covers a region only if it has subreddits mapped. A chip offering
    a filter that can never match anything is worse than no chip.
    """
    return [
        source.name.value
        for source in all_sources()
        if source.is_configured() and source.supports(region)
    ]
