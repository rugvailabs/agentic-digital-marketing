"""GoogleNewsRSSAdapter against recorded en-IN RSS bodies (respx, no network)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.models import SourceName
from app.sources.google_news import GoogleNewsRSSAdapter, _strip_publisher
from tests.conftest import load_bytes

NATIONAL = load_bytes("google_news_national.xml")
STATE_MH = load_bytes("google_news_state_mh.xml")


@pytest.fixture
async def client():
    async with httpx.AsyncClient(follow_redirects=True) as c:
        yield c


def test_is_configured_without_credentials() -> None:
    assert GoogleNewsRSSAdapter().is_configured() is True


def test_supports_every_region(india, maharashtra, ladakh, mumbai) -> None:
    adapter = GoogleNewsRSSAdapter()
    # The search feed only needs a name, so even Trends-less regions work.
    assert all(adapter.supports(r) for r in (india, maharashtra, ladakh, mumbai))


def test_country_uses_top_stories_and_others_use_search(india, maharashtra, mumbai) -> None:
    adapter = GoogleNewsRSSAdapter()

    url, params = adapter.feed_url(india)
    assert url.endswith("/rss")
    assert "q" not in params
    assert params["hl"] == "en-IN" and params["ceid"] == "IN:en"

    url, params = adapter.feed_url(maharashtra)
    assert url.endswith("/rss/search")
    assert params["q"] == "Maharashtra"

    _, params = adapter.feed_url(mumbai)
    assert params["q"] == "Mumbai"


@respx.mock
async def test_fetch_national_feed(client, india) -> None:
    route = respx.get("https://news.google.com/rss").mock(
        return_value=httpx.Response(200, content=NATIONAL)
    )
    items = await GoogleNewsRSSAdapter(client=client).fetch(india, limit=5)

    assert route.called
    assert len(items) == 5
    assert [i.rank for i in items] == [1, 2, 3, 4, 5]
    assert all(i.url and i.url.startswith("http") for i in items)
    assert all(i.extra["publisher"] for i in items)
    # The " - Publisher" suffix must be gone, or dedupe splits syndicated copies.
    for item in items:
        assert not item.title.endswith(f" - {item.extra['publisher']}")


@respx.mock
async def test_fetch_state_feed_passes_region_name_as_query(client, maharashtra) -> None:
    route = respx.get("https://news.google.com/rss/search").mock(
        return_value=httpx.Response(200, content=STATE_MH)
    )
    items = await GoogleNewsRSSAdapter(client=client).fetch(maharashtra, limit=8)

    assert route.called
    assert route.calls[0].request.url.params["q"] == "Maharashtra"
    assert route.calls[0].request.url.params["hl"] == "en-IN"
    assert len(items) == 8
    assert all(i.volume is None for i in items), "RSS has no volume signal"


@respx.mock
async def test_fetch_raises_on_http_error(client, india) -> None:
    respx.get("https://news.google.com/rss").mock(return_value=httpx.Response(503))

    # Adapters raise; the orchestrator records it on the snapshot row.
    with pytest.raises(httpx.HTTPStatusError):
        await GoogleNewsRSSAdapter(client=client).fetch(india)


@pytest.mark.parametrize(
    ("title", "publisher", "expected"),
    [
        (
            "Mumbai flyovers open today - ET Government",
            "ET Government",
            "Mumbai flyovers open today",
        ),
        ("Mumbai flyovers open today - ET Government", None, "Mumbai flyovers open today"),
        # Short head: the dash is part of the headline, not a publisher suffix.
        ("Sensex up - live", None, "Sensex up - live"),
        ("No suffix here at all", "Reuters", "No suffix here at all"),
    ],
)
def test_strip_publisher(title: str, publisher: str | None, expected: str) -> None:
    assert _strip_publisher(title, publisher) == expected


def test_source_identity() -> None:
    adapter = GoogleNewsRSSAdapter()
    assert adapter.name is SourceName.google_news
    assert adapter.weight == 0.7
