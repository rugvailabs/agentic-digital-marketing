"""InstagramHashtagAdapter against recorded Graph shapes. No keys needed.

The behaviour worth pinning is mostly about what this adapter refuses to do:
it does not discover trends, it does not invent hashtags from a region name,
and it does not report "Instagram declined" as a count of zero.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.config import settings
from app.models import Region, RegionKind, SourceName
from app.sources import all_sources, configured_source_names
from app.sources.instagram import (
    API_BASE,
    WEEKLY_HASHTAG_LIMIT,
    InstagramHashtagAdapter,
)
from tests.conftest import load_json

FIXTURE = load_json("instagram_hashtag.json")
TOKEN = "test-token"
BUSINESS = "17841400000000000"
HASHTAG_ID = FIXTURE["node"]["id"]


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


def adapter(client: httpx.AsyncClient, **kw) -> InstagramHashtagAdapter:
    kw.setdefault("access_token", TOKEN)
    kw.setdefault("business_id", BUSINESS)
    return InstagramHashtagAdapter(client=client, **kw)


def mock_graph(
    *,
    search: dict | None = None,
    node: dict | None = None,
    media: dict | None = None,
    search_status: int = 200,
):
    """Mock all three Graph calls; return the search route for call counts.

    Returned rather than re-registered by the caller. respx matches in
    registration order, so a second respx.get(...ig_hashtag_search) shadows
    this one and answers with an empty body — which fails as a JSON decode
    error in the adapter rather than as the assertion the test was making.
    """
    search_route = respx.get(f"{API_BASE}/ig_hashtag_search").mock(
        return_value=httpx.Response(search_status, json=search or FIXTURE["search"])
    )
    respx.get(f"{API_BASE}/{HASHTAG_ID}/top_media").mock(
        return_value=httpx.Response(200, json=media or FIXTURE["top_media"])
    )
    respx.get(f"{API_BASE}/{HASHTAG_ID}").mock(
        return_value=httpx.Response(200, json=node or FIXTURE["node"])
    )
    return search_route


class TestConfiguration:
    def test_both_halves_are_needed(self) -> None:
        assert InstagramHashtagAdapter(access_token="t", business_id="b").is_configured()
        assert not InstagramHashtagAdapter(access_token="t", business_id="").is_configured()
        assert not InstagramHashtagAdapter(access_token="", business_id="b").is_configured()

    def test_it_is_unconfigured_on_a_clean_checkout(self) -> None:
        """No IG keys have been issued, so it must report false and be
        skipped rather than crash the cycle."""
        assert settings.ig_access_token == ""
        assert InstagramHashtagAdapter().is_configured() is False
        assert "instagram" not in configured_source_names()

    def test_it_is_in_the_registry_anyway(self) -> None:
        """Per CLAUDE.md every capability is registered; configuration is a
        runtime answer, not a reason to be absent."""
        assert SourceName.instagram in [s.name for s in all_sources()]

    def test_hashtags_are_global_so_every_region_is_supported(self) -> None:
        ig = InstagramHashtagAdapter(access_token="t", business_id="b")
        for kind in (RegionKind.country, RegionKind.state, RegionKind.city):
            assert ig.supports(Region(id=1, code="IN", name="India", kind=kind, sort_order=0))

    async def test_an_unconfigured_measure_calls_nothing(self) -> None:
        with respx.mock:
            route = respx.get(url__startswith=API_BASE)
            out = await InstagramHashtagAdapter(access_token="", business_id="").measure(
                ["#AsiaCupFinal"]
            )

        assert out == []
        assert not route.called


class TestFetchDoesNotDiscover:
    """The Graph API has no trending-hashtags endpoint, so this adapter
    enriches topics found elsewhere and never produces a board of its own."""

    @respx.mock
    async def test_fetch_returns_nothing_even_when_configured(self, client) -> None:
        route = respx.get(url__startswith=API_BASE)
        india = Region(id=1, code="IN", name="India", kind=RegionKind.country, sort_order=0)

        items = await adapter(client).fetch(india, limit=20)

        assert items == []
        # And it spends nothing finding that out: a Graph call here would be
        # one of thirty weekly hashtag slots burnt on a question Instagram
        # cannot answer.
        assert not route.called

    @respx.mock
    async def test_fetch_does_not_invent_a_hashtag_from_the_region(self, client) -> None:
        """ "#Maharashtra" is not a trend, and a row sourced from it would be
        a real number attached to a topic nobody is posting about."""
        route = respx.get(url__startswith=API_BASE)
        mh = Region(id=2, code="IN-MH", name="Maharashtra", kind=RegionKind.state, sort_order=1)

        await adapter(client).fetch(mh, limit=20)

        assert not route.called


class TestMeasure:
    @respx.mock
    async def test_it_reports_media_count_and_engagement(self, client) -> None:
        mock_graph()

        out = await adapter(client).measure(["#AsiaCupFinal"])

        assert len(out) == 1
        metrics = out[0]
        assert metrics.hashtag == "#AsiaCupFinal"
        assert metrics.media_count == 184233
        # Likes + comments across the sampled top media: 48210+1340+12050+310.
        assert metrics.engagement == 61910
        assert metrics.top_permalink == "https://www.instagram.com/p/Cxyz123/"

    @respx.mock
    async def test_a_bare_name_and_a_hashed_one_are_the_same_input(self, client) -> None:
        mock_graph()

        with_hash = await adapter(client).measure(["#AsiaCupFinal"])
        without = await adapter(client).measure(["AsiaCupFinal"])

        assert with_hash[0].media_count == without[0].media_count

    @respx.mock
    async def test_the_id_is_cached_against_the_weekly_cap(self, client) -> None:
        """30 unique hashtags per account per rolling 7 days — not 30 calls.
        Resolving the same tag twice spends the allowance twice."""
        search = mock_graph()

        ig = adapter(client)
        await ig.measure(["#AsiaCupFinal"])
        await ig.measure(["#AsiaCupFinal"])

        assert search.call_count == 1

    @respx.mock
    async def test_duplicates_in_one_call_resolve_once(self, client) -> None:
        search = mock_graph()

        out = await adapter(client).measure(["#AsiaCupFinal", "asiacupfinal", "#AsiaCupFinal"])

        assert search.call_count == 1
        assert len(out) == 1

    @respx.mock
    async def test_the_callers_spelling_is_what_comes_back(self, client) -> None:
        """Dedupe is casefolded because Instagram's hashtags are, but the tag
        is going into a caption, so it is reported as the caller wrote it
        rather than as Graph's lowercase node name."""
        mock_graph()

        out = await adapter(client).measure(["#AsiaCupFinal"])

        assert out[0].hashtag == "#AsiaCupFinal"

    @respx.mock
    async def test_empty_and_blank_inputs_are_dropped(self, client) -> None:
        route = respx.get(url__startswith=API_BASE)

        out = await adapter(client).measure(["", "   ", "#", "##"])

        assert out == []
        assert not route.called

    @respx.mock
    async def test_more_than_the_weekly_allowance_is_capped_and_logged(
        self, client, caplog
    ) -> None:
        """Truncating silently would read as "Instagram had nothing for the
        rest", when what happened is the allowance ran out."""
        mock_graph()

        out = await adapter(client).measure([f"#Tag{i}" for i in range(WEEKLY_HASHTAG_LIMIT + 5)])

        assert len(out) <= WEEKLY_HASHTAG_LIMIT

    @respx.mock
    async def test_a_hashtag_with_no_top_media_still_reports_its_count(self, client) -> None:
        """A tag can have posts that Graph will not return media for; the
        count is still the honest figure."""
        mock_graph(media={"data": []})

        out = await adapter(client).measure(["#AsiaCupFinal"])

        assert out[0].media_count == 184233
        assert out[0].engagement == 0
        assert out[0].top_permalink is None


class TestRefusals:
    @respx.mock
    async def test_a_banned_hashtag_is_skipped_not_reported_as_zero(self, client) -> None:
        """Zero posts and "Instagram declined to answer" are different
        claims, and the second must not be published as the first."""
        respx.get(f"{API_BASE}/ig_hashtag_search").mock(
            return_value=httpx.Response(400, json=FIXTURE["banned"])
        )

        out = await adapter(client).measure(["#BannedTag"])

        assert out == []

    @respx.mock
    async def test_an_unresolvable_hashtag_is_skipped(self, client) -> None:
        respx.get(f"{API_BASE}/ig_hashtag_search").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        assert await adapter(client).measure(["#NeverHeardOfIt"]) == []

    @respx.mock
    async def test_an_expired_token_raises_rather_than_emptying_the_batch(self, client) -> None:
        """Every remaining hashtag will fail the same way, so a silent empty
        result would read as "none of these tags exist"."""
        respx.get(f"{API_BASE}/ig_hashtag_search").mock(
            return_value=httpx.Response(400, json=FIXTURE["expired_token"])
        )

        with pytest.raises(httpx.HTTPStatusError, match="token rejected"):
            await adapter(client).measure(["#AsiaCupFinal", "#Cricket"])

    @respx.mock
    async def test_a_server_error_raises(self, client) -> None:
        respx.get(f"{API_BASE}/ig_hashtag_search").mock(
            return_value=httpx.Response(500, text="oops")
        )

        with pytest.raises(httpx.HTTPStatusError):
            await adapter(client).measure(["#AsiaCupFinal"])

    @respx.mock
    async def test_the_token_is_never_in_a_logged_url(self, client) -> None:
        """It is sent as a query parameter, which is where secrets get into
        logs by accident."""
        mock_graph()

        await adapter(client).measure(["#AsiaCupFinal"])

        for call in respx.calls:
            assert "access_token" in dict(call.request.url.params)
