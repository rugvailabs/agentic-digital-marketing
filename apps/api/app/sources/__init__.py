"""Trend source registry.

Nothing outside this package constructs an adapter: callers ask for the
registry and respect `is_configured()`/`supports()`. Adding a source means
adding one line here.
"""

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
