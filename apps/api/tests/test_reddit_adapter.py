"""RedditAdapter against recorded listings. No network, no credentials.

The fixtures carry the cases that cost something if mishandled: a stickied
megathread with the highest score on the page, an NSFW post, a post present
in both hot and rising with different scores, a Devanagari title, and a
procedural flair.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.models import Region, RegionKind
from app.sources.reddit import (
    API_BASE,
    NATIONAL,
    SUBREDDITS,
    TOKEN_URL,
    RedditAdapter,
    hashtags_from,
    subreddits_for,
)
from tests.conftest import load_json

HOT = load_json("reddit_hot_india.json")
RISING = load_json("reddit_rising_india.json")
TOKEN = {"access_token": "test-token", "expires_in": 7200, "token_type": "bearer"}


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


def adapter(client: httpx.AsyncClient, **kw) -> RedditAdapter:
    kw.setdefault("client_id", "id")
    kw.setdefault("client_secret", "secret")
    return RedditAdapter(client=client, **kw)


def india() -> Region:
    return Region(id=1, code="IN", name="India", kind=RegionKind.country, sort_order=0)


def mock_listings(hot=HOT, rising=RISING):
    """Register the token and every national listing; return the token route.

    Returned rather than re-registered by the caller: a second
    respx.post(TOKEN_URL) shadows this one and answers with an empty body,
    which is a confusing way to fail a test about call counts.
    """
    token_route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN))
    for sub in NATIONAL:
        respx.get(f"{API_BASE}/r/{sub}/hot").mock(return_value=httpx.Response(200, json=hot))
        respx.get(f"{API_BASE}/r/{sub}/rising").mock(return_value=httpx.Response(200, json=rising))
    return token_route


class TestConfiguration:
    def test_both_halves_of_the_credential_are_needed(self) -> None:
        assert RedditAdapter(client_id="a", client_secret="b").is_configured() is True
        assert RedditAdapter(client_id="a", client_secret="").is_configured() is False
        assert RedditAdapter(client_id="", client_secret="b").is_configured() is False

    async def test_an_unconfigured_adapter_returns_nothing_and_does_not_call(self) -> None:
        """Per CLAUDE.md an unconfigured adapter is skipped, never fatal."""
        with respx.mock:
            route = respx.post(TOKEN_URL)
            items = await RedditAdapter(client_id="", client_secret="").fetch(india())

        assert items == []
        assert not route.called

    def test_it_supports_the_country_and_every_mapped_region(self) -> None:
        assert subreddits_for(india()) == NATIONAL
        mh = Region(id=2, code="IN-MH", name="Maharashtra", kind=RegionKind.state, sort_order=1)
        assert "mumbai" in subreddits_for(mh)

    def test_an_unmapped_region_is_not_supported(self) -> None:
        """Rather than fetching r/india for a place it does not cover and
        calling the result local."""
        nowhere = Region(id=3, code="IN-XX", name="Nowhere", kind=RegionKind.state, sort_order=9)

        assert subreddits_for(nowhere) == ()
        assert RedditAdapter(client_id="a", client_secret="b").supports(nowhere) is False

    def test_every_mapped_city_belongs_to_its_state(self) -> None:
        """A city code is IN-<state>-<city>, so a typo in the map would
        otherwise sit there as a region nothing ever matches."""
        for code in SUBREDDITS:
            parts = code.split("-")
            if len(parts) == 3:
                assert "-".join(parts[:2]) in SUBREDDITS, code


class TestFetch:
    @respx.mock
    async def test_posts_become_items_ranked_by_upvotes(self, client) -> None:
        mock_listings()

        items = await adapter(client).fetch(india(), limit=10)

        assert items
        assert [i.rank for i in items] == list(range(1, len(items) + 1))
        volumes = [i.volume for i in items]
        assert volumes == sorted(volumes, reverse=True)

    @respx.mock
    async def test_a_stickied_megathread_is_dropped(self, client) -> None:
        """It has the highest score on the page by a wide margin and is not a
        trend — it is the subreddit's furniture. Ranking on score alone would
        make it the top topic in India every single cycle."""
        mock_listings()

        items = await adapter(client).fetch(india(), limit=10)

        assert not any("discussion thread" in i.title.lower() for i in items)
        assert items[0].volume < 52000

    @respx.mock
    async def test_nsfw_is_dropped(self, client) -> None:
        mock_listings()

        items = await adapter(client).fetch(india(), limit=10)

        assert not any("NSFW" in i.title for i in items)

    @respx.mock
    async def test_a_post_in_both_listings_appears_once(self, client) -> None:
        """The RBI post is in hot at 9,120 and rising at 11,890. One post, and
        the better score decides its rank."""
        mock_listings()

        items = await adapter(client).fetch(india(), limit=20)
        rbi = [i for i in items if "RBI holds" in i.title]

        assert len(rbi) == 1
        assert rbi[0].volume == 11890

    @respx.mock
    async def test_rising_contributes_posts_hot_does_not_have(self, client) -> None:
        """Ranking on hot alone makes this a slow duplicate of Google News."""
        mock_listings()

        items = await adapter(client).fetch(india(), limit=20)

        assert any("Chandrayaan-4" in i.title for i in items)

    @respx.mock
    async def test_an_indic_title_survives_intact(self, client) -> None:
        mock_listings()

        items = await adapter(client).fetch(india(), limit=20)
        hindi = [i for i in items if "दिल्ली" in i.title]

        assert len(hindi) == 1
        # Matras intact: the combining marks are what get eaten by \w and
        # isalnum, and "गुणवत्ता" without them is a different word.
        assert "गुणवत्ता" in hindi[0].title

    @respx.mock
    async def test_items_carry_url_subreddit_and_comments(self, client) -> None:
        mock_listings()

        items = await adapter(client).fetch(india(), limit=20)
        metro = next(i for i in items if "Metro" in i.title)

        assert (
            metro.url == "https://www.reddit.com/r/india/comments/1a0001/mumbai_metro_line_3_opens/"
        )
        assert metro.extra["subreddit"] in NATIONAL
        assert metro.extra["comments"] == 1204

    @respx.mock
    async def test_the_limit_is_honoured(self, client) -> None:
        mock_listings()

        items = await adapter(client).fetch(india(), limit=3)

        assert len(items) == 3


class TestResilience:
    @respx.mock
    async def test_a_missing_subreddit_costs_only_itself(self, client) -> None:
        """SUBREDDITS could not be verified against live Reddit — every
        anonymous request answers 403 from a datacenter IP — so a name that
        is gone must not take the region's other subreddits with it."""
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN))
        respx.get(f"{API_BASE}/r/{NATIONAL[0]}/hot").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        respx.get(f"{API_BASE}/r/{NATIONAL[0]}/rising").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        for sub in NATIONAL[1:]:
            respx.get(f"{API_BASE}/r/{sub}/hot").mock(return_value=httpx.Response(200, json=HOT))
            respx.get(f"{API_BASE}/r/{sub}/rising").mock(
                return_value=httpx.Response(200, json=RISING)
            )

        items = await adapter(client).fetch(india(), limit=10)

        assert items

    @respx.mock
    async def test_a_private_subreddit_is_skipped_not_fatal(self, client) -> None:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN))
        for sub in NATIONAL:
            respx.get(f"{API_BASE}/r/{sub}/hot").mock(
                return_value=httpx.Response(403, json={"reason": "private"})
            )
            respx.get(f"{API_BASE}/r/{sub}/rising").mock(
                return_value=httpx.Response(200, json=RISING)
            )

        items = await adapter(client).fetch(india(), limit=10)

        assert any("Chandrayaan-4" in i.title for i in items)

    @respx.mock
    async def test_a_server_error_is_raised_not_swallowed(self, client) -> None:
        """A 500 is Reddit being broken, not a bad subreddit name. The caller
        records it on the snapshot row; silently returning [] would read as
        "nothing is trending in India"."""
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=TOKEN))
        respx.get(url__startswith=f"{API_BASE}/r/").mock(
            return_value=httpx.Response(500, text="oops")
        )

        with pytest.raises(httpx.HTTPStatusError):
            await adapter(client).fetch(india(), limit=10)

    @respx.mock
    async def test_a_refused_token_is_raised(self, client) -> None:
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(401, json={"error": "invalid"}))

        with pytest.raises(httpx.HTTPStatusError):
            await adapter(client).fetch(india(), limit=10)

    @respx.mock
    async def test_the_token_is_reused_across_fetches(self, client) -> None:
        """Six listings per region for the national board, and a cycle visits
        many regions; minting a token for each would be dozens of pointless
        round trips. Reddit's last about two hours."""
        route = mock_listings()

        reddit = adapter(client)
        await reddit.fetch(india(), limit=5)
        await reddit.fetch(india(), limit=5)

        assert route.call_count == 1

    @respx.mock
    async def test_the_user_agent_is_sent_on_every_call(self, client) -> None:
        """Reddit answers 429 to a generic user agent even with good keys."""
        mock_listings()

        await adapter(client, user_agent="trendforge/0.1 (by /u/someone)").fetch(india(), limit=5)

        for call in respx.calls:
            assert call.request.headers["user-agent"] == "trendforge/0.1 (by /u/someone)"


class TestHashtags:
    def test_a_literal_hashtag_in_the_title_is_kept(self) -> None:
        assert "#BengaluruTraffic" in hashtags_from(
            "What is the #BengaluruTraffic situation like?", None
        )

    def test_a_subject_flair_becomes_a_tag(self) -> None:
        assert hashtags_from("RBI holds the repo rate", "Business/Finance") == ["#BusinessFinance"]

    def test_a_procedural_flair_does_not(self) -> None:
        """#Image and #Discussion describe the post's format, so they would be
        published beside a caption about something else entirely."""
        assert hashtags_from("What is the traffic like?", "AskIndia") == []
        assert hashtags_from("Look at this", "Image") == []
        assert hashtags_from("Weekly thread", "Megathread") == []

    def test_a_devanagari_flair_keeps_its_matras(self) -> None:
        tags = hashtags_from("दिल्ली में हवा", "मौसम")

        assert tags == ["#मौसम"]

    def test_duplicates_are_dropped_case_insensitively(self) -> None:
        tags = hashtags_from("#Cricket and #cricket again", "Cricket")

        assert len(tags) == 1

    def test_no_title_and_no_flair_is_no_tags(self) -> None:
        assert hashtags_from("", None) == []
