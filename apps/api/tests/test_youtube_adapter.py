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
from app.sources.youtube import API_URL, CATEGORIES, YouTubeAdapter
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


SPORTS = load_json("youtube_category_sports.json")


def charts(overall: dict, **by_category: dict) -> None:
    """Mock all six charts at once, specific routes first.

    One function rather than a per-chart helper because respx matches in
    registration order and the overall chart can only be expressed as a
    catch-all — there is no "parameter is absent" matcher. Registered by hand
    in the wrong order it silently answers the category requests too, which
    reads as the category chart returning nothing.
    """
    for category_id, payload in by_category.items():
        respx.get(API_URL, params__contains={"videoCategoryId": category_id}).mock(
            return_value=httpx.Response(200, json=payload)
        )
    for category_id in (v for v in CATEGORIES.values() if v and v not in by_category):
        respx.get(API_URL, params__contains={"videoCategoryId": category_id}).mock(
            return_value=httpx.Response(200, json={"items": []})
        )
    # Last: anything not matched above is the overall chart.
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=overall))


class TestCategoryCharts:
    """Six charts, not one. The overall chart is mostly music and film on any
    given day, so a sports or news story that is genuinely trending never
    reaches it."""

    @respx.mock
    async def test_every_category_is_requested(self, client, india) -> None:
        respx.get(API_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

        await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=50)

        requested = [dict(call.request.url.params).get("videoCategoryId") for call in respx.calls]
        assert len(requested) == len(CATEGORIES)
        # The overall chart sends no videoCategoryId; the five others do.
        assert sorted(x for x in requested if x) == sorted(v for v in CATEGORIES.values() if v)

    @respx.mock
    async def test_a_category_only_video_reaches_the_board(self, client, india) -> None:
        """The whole reason for the extra five calls."""
        charts(PAYLOAD, **{"17": SPORTS})

        items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=50)

        assert any("fastest T20 century" in i.title for i in items)

    @respx.mock
    async def test_a_video_on_two_charts_appears_once_with_the_fuller_count(
        self, client, india
    ) -> None:
        """aBcD1234efg is on the overall chart at 4,820,193 views and on the
        sports chart at 1. One video, and the overall chart's figure is the
        complete one."""
        charts(PAYLOAD, **{"17": SPORTS})

        items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=50)
        matching = [i for i in items if i.url and i.url.endswith("aBcD1234efg")]

        assert len(matching) == 1
        assert matching[0].volume == 4820193

    @respx.mock
    async def test_the_chart_that_answered_names_the_category(self, client, india) -> None:
        """categoryId is numeric and naming it used to need a second request,
        so this field was always None."""
        charts(PAYLOAD, **{"17": SPORTS})

        items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=50)
        sports = next(i for i in items if "fastest T20" in i.title)

        assert sports.category == "Sports"

    @respx.mock
    async def test_a_refused_category_costs_only_itself(self, client, india) -> None:
        """A category with no chart for a region answers 400, not an empty
        list. A 400 on Gaming is not a reason to report that nothing is
        trending in India."""
        respx.get(API_URL, params__contains={"videoCategoryId": "17"}).mock(
            return_value=httpx.Response(200, json=SPORTS)
        )
        for cid in (v for v in CATEGORIES.values() if v and v != "17"):
            respx.get(API_URL, params__contains={"videoCategoryId": cid}).mock(
                return_value=httpx.Response(400, json={"error": {"message": "invalid"}})
            )
        respx.get(API_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

        items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=50)

        assert any("fastest T20" in i.title for i in items)
        assert len(items) > 1

    @respx.mock
    async def test_a_server_error_still_raises(self, client, india) -> None:
        respx.get(API_URL).mock(return_value=httpx.Response(500, text="oops"))

        with pytest.raises(httpx.HTTPStatusError):
            await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=10)

    @respx.mock
    async def test_an_unconfigured_adapter_makes_no_call(self, client, india) -> None:
        route = respx.get(API_URL)

        items = await YouTubeAdapter(client=client, api_key="").fetch(india)

        assert items == []
        assert not route.called


class TestYouTubeHashtags:
    @respx.mock
    async def test_hashtags_come_from_the_title_and_description(self, client, india) -> None:
        """Where creators actually put them. `tags` is the uploader's keyword
        list and carries no "#", so it stays a separate field."""
        charts({"items": []}, **{"17": SPORTS})

        items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=50)
        sports = next(i for i in items if "fastest T20" in i.title)

        assert "#INDvNZ" in sports.extra["hashtags"]
        assert "#AbhishekSharma" in sports.extra["hashtags"]
        assert "#Cricket" in sports.extra["hashtags"]
        # Keywords are not hashtags and are kept apart.
        assert sports.extra["tags"] == ["cricket", "india", "t20"]

    @respx.mock
    async def test_a_video_with_no_hashtags_gets_an_empty_list(self, client, india) -> None:
        charts(PAYLOAD)

        items = await YouTubeAdapter(client=client, api_key=KEY).fetch(india, limit=50)

        assert all(isinstance(i.extra["hashtags"], list) for i in items)
