"""YouTubeAdapter against a recorded-shape videos.list response (respx).

The fixture is hand-authored to the documented response shape rather than
captured live — no YOUTUBE_API_KEY was available when these tests were written.
It therefore pins the adapter's field mapping and its missing-field handling,
not Google's live payload.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.models import SourceName
from app.sources.youtube import API_URL, YouTubeAdapter
from tests.conftest import load_json

PAYLOAD = load_json("youtube_most_popular_in.json")
KEY = "test-key"


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


def test_not_configured_without_a_key() -> None:
    assert YouTubeAdapter(api_key="").is_configured() is False
    assert YouTubeAdapter(api_key=KEY).is_configured() is True


def test_supports_country_only(india, maharashtra, mumbai) -> None:
    adapter = YouTubeAdapter(api_key=KEY)
    # mostPopular is a country-level chart; regionCode has no state granularity.
    assert adapter.supports(india)
    assert not adapter.supports(maharashtra)
    assert not adapter.supports(mumbai)


@respx.mock
async def test_fetch_sends_most_popular_india_query(client, india) -> None:
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=10)

    params = route.calls[0].request.url.params
    assert params["chart"] == "mostPopular"
    assert params["regionCode"] == "IN"
    assert params["part"] == "snippet,statistics"
    assert params["key"] == KEY


@respx.mock
async def test_fetch_maps_views_thumbnail_and_url(client, india) -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=10)

    assert len(items) == 4
    assert [i.rank for i in items] == [1, 2, 3, 4]

    first = items[0]
    assert first.title == "India vs Sri Lanka highlights | 3rd T20I"
    assert first.volume == 4820193
    assert first.url == "https://www.youtube.com/watch?v=aBcD1234efg"
    assert first.extra["channel"] == "Star Sports"
    assert first.extra["thumbnail"].endswith("hqdefault.jpg")
    assert first.extra["likes"] == 182044

    # Devanagari must survive untouched — the UI and Pillow renderer need it.
    assert items[1].title.startswith("नया गाना")


@respx.mock
async def test_fetch_tolerates_missing_statistics_and_thumbnails(client, india) -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=10)

    low_res, no_stats = items[2], items[3]
    assert low_res.extra["thumbnail"].endswith("default.jpg")  # fell back from `high`
    assert no_stats.volume is None
    assert no_stats.extra["thumbnail"] is None
    assert no_stats.extra["likes"] is None


@respx.mock
async def test_fetch_respects_limit(client, india) -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=2)
    assert len(items) == 2


@respx.mock
async def test_fetch_raises_on_quota_error(client, india) -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(403, json={"error": {"code": 403}}))

    with pytest.raises(httpx.HTTPStatusError):
        await YouTubeAdapter(client=client, api_key=KEY).fetch(india)


def test_source_identity() -> None:
    adapter = YouTubeAdapter(api_key=KEY)
    assert adapter.name is SourceName.youtube
    assert adapter.weight == 0.6
