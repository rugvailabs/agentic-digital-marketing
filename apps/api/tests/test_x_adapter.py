"""XAdapter is a stub in step 1: interface-complete, zero rows, loud about why."""

from __future__ import annotations

from structlog.testing import capture_logs

from app.models import SourceName
from app.sources import all_sources, configured_source_names, source_weights
from app.sources.base import TrendSource
from app.sources.x import XAdapter


def test_not_configured_without_a_bearer_token() -> None:
    assert XAdapter(bearer_token="").is_configured() is False
    assert XAdapter(bearer_token="token").is_configured() is True


def test_supports_regions_that_have_woeids(india, maharashtra, mumbai, ladakh) -> None:
    adapter = XAdapter(bearer_token="token")
    assert adapter.supports(india)  # own WOEID
    assert adapter.supports(mumbai)  # own WOEID
    assert not adapter.supports(maharashtra)  # rolls up from cities, none loaded here
    assert not adapter.supports(ladakh)


async def test_fetch_logs_not_configured_and_returns_empty(india) -> None:
    # structlog renders to stdout, so capture through structlog, not caplog.
    with capture_logs() as logs:
        items = await XAdapter(bearer_token="").fetch(india)

    assert items == []
    assert [entry["event"] for entry in logs] == ["not configured"]
    assert logs[0]["reason"] == "X_BEARER_TOKEN is not set"


async def test_fetch_is_still_empty_with_a_token(india) -> None:
    # A token must not be mistaken for an implementation.
    with capture_logs() as logs:
        items = await XAdapter(bearer_token="token").fetch(india)

    assert items == []
    assert logs[0]["log_level"] == "warning"
    assert "not implemented" in logs[0]["reason"]


def test_registry_exposes_every_source_and_its_weight() -> None:
    sources = all_sources()

    assert [s.name for s in sources] == [
        SourceName.google_trends,
        SourceName.google_news,
        SourceName.youtube,
        SourceName.reddit,
        SourceName.x,
    ]
    assert all(isinstance(s, TrendSource) for s in sources)

    # Keyless sources work on a clean checkout; youtube, reddit and x all
    # need credentials, so a clean checkout has exactly the two.
    assert set(configured_source_names()) >= {"google_trends", "google_news"}
    assert source_weights()["google_trends"] > source_weights()["google_news"]
