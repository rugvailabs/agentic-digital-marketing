"""XAdapter against recorded responses, and the two guards around it.

X is the only source billed per request, so most of what matters here is
about not making requests: the per-region interval, the daily cap, and the
402 that the live account currently returns.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.budget import DailyBudget
from app.models import Region, RegionKind
from app.sources.x import API_BASE, CreditsDepleted, XAdapter
from tests.conftest import load_json

INDIA_WOEID = 23424848
MUMBAI_WOEID = 2295411
NATIONAL = load_json("x_trends_india.json")
CITY = load_json("x_trends_city.json")
TOKEN = "AAAA-test-bearer"


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


@pytest.fixture(autouse=True)
def _always_claimable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a fresh interval claim unless it says otherwise.

    Without this the first test to run claims the region and the rest see an
    empty list, which fails as "the adapter returned nothing" rather than as
    what it is.
    """
    monkeypatch.setattr("app.sources.x.claim_interval", _claimable(True))


def _claimable(result: bool):
    async def claim(key: str, seconds: int) -> bool:
        return result

    return claim


def india() -> Region:
    return Region(
        id=1,
        code="IN",
        name="India",
        kind=RegionKind.country,
        sort_order=0,
        x_woeid=INDIA_WOEID,
    )


def maharashtra(cities: list[int]) -> Region:
    region = Region(id=2, code="IN-MH", name="Maharashtra", kind=RegionKind.state, sort_order=1)
    region.children = [
        Region(
            id=10 + i,
            code=f"IN-MH-C{i}",
            name=f"City {i}",
            kind=RegionKind.city,
            sort_order=i,
            x_woeid=woeid,
        )
        for i, woeid in enumerate(cities)
    ]
    return region


def adapter(client: httpx.AsyncClient, **kw) -> XAdapter:
    kw.setdefault("bearer_token", TOKEN)
    kw.setdefault("daily_cap", 100)
    return XAdapter(client=client, **kw)


class TestConfiguration:
    def test_a_bearer_is_what_makes_it_configured(self) -> None:
        assert XAdapter(bearer_token=TOKEN).is_configured() is True
        assert XAdapter(bearer_token="").is_configured() is False

    async def test_an_unconfigured_adapter_spends_nothing(self) -> None:
        with respx.mock:
            route = respx.get(url__startswith=API_BASE)
            items = await XAdapter(bearer_token="").fetch(india())

        assert items == []
        assert not route.called

    def test_a_region_with_no_woeid_anywhere_is_unsupported(self) -> None:
        bare = Region(id=3, code="IN-XX", name="Nowhere", kind=RegionKind.state, sort_order=9)
        bare.children = []

        assert XAdapter(bearer_token=TOKEN).supports(bare) is False

    def test_a_state_is_supported_through_its_cities(self) -> None:
        assert XAdapter(bearer_token=TOKEN).supports(maharashtra([MUMBAI_WOEID])) is True


class TestFetch:
    @respx.mock
    async def test_trends_become_ranked_items(self, client) -> None:
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(return_value=httpx.Response(200, json=NATIONAL))

        items = await adapter(client).fetch(india(), limit=10)

        assert [i.rank for i in items] == [1, 2, 3, 4]
        assert items[0].title == "#INDvNZ"
        assert items[0].volume == 184000

    @respx.mock
    async def test_a_blank_trend_name_is_dropped(self, client) -> None:
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(return_value=httpx.Response(200, json=NATIONAL))

        items = await adapter(client).fetch(india(), limit=10)

        assert all(i.title.strip() for i in items)

    @respx.mock
    async def test_a_missing_count_is_none_not_zero(self, client) -> None:
        """X omits tweet_count on some trends. Zero would sort it below a
        trend with one post, which is a claim the response did not make."""
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(return_value=httpx.Response(200, json=NATIONAL))

        items = await adapter(client).fetch(india(), limit=10)
        rbi = next(i for i in items if i.title == "RBI policy")

        assert rbi.volume is None

    @respx.mock
    async def test_hashtags_are_whatever_was_literally_there(self, client) -> None:
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(return_value=httpx.Response(200, json=NATIONAL))

        items = await adapter(client).fetch(india(), limit=10)
        by_title = {i.title: i for i in items}

        assert by_title["#INDvNZ"].extra["hashtags"] == ["#INDvNZ"]
        # Not every X trend is a hashtag, and camel-casing one would invent a
        # tag nobody is using.
        assert by_title["Abhishek Sharma"].extra["hashtags"] == []

    @respx.mock
    async def test_a_state_rolls_up_its_cities(self, client) -> None:
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(return_value=httpx.Response(200, json=NATIONAL))
        respx.get(f"{API_BASE}/{MUMBAI_WOEID}").mock(return_value=httpx.Response(200, json=CITY))

        items = await adapter(client).fetch(maharashtra([INDIA_WOEID, MUMBAI_WOEID]), limit=10)

        assert any(i.title == "Mumbai Metro" for i in items)

    @respx.mock
    async def test_a_trend_in_two_cities_is_one_row(self, client) -> None:
        """#INDvNZ is 1st at 184,000 in one and 1st at 1,200 in the other.
        One topic, the better rank, the larger count."""
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(return_value=httpx.Response(200, json=NATIONAL))
        respx.get(f"{API_BASE}/{MUMBAI_WOEID}").mock(return_value=httpx.Response(200, json=CITY))

        items = await adapter(client).fetch(maharashtra([INDIA_WOEID, MUMBAI_WOEID]), limit=10)
        matching = [i for i in items if i.title == "#INDvNZ"]

        assert len(matching) == 1
        assert matching[0].volume == 184000


class TestSpendGuards:
    @respx.mock
    async def test_a_region_pulled_recently_costs_nothing(self, client, monkeypatch) -> None:
        """The beat runs every 30 minutes and the default interval is 120, so
        without this a region costs 48 requests a day instead of 12."""
        monkeypatch.setattr("app.sources.x.claim_interval", _claimable(False))
        route = respx.get(url__startswith=API_BASE)

        items = await adapter(client).fetch(india())

        assert items == []
        assert not route.called

    @respx.mock
    async def test_the_daily_cap_stops_further_requests(self, client) -> None:
        """Stops rather than queues: a budget that waited would hold the
        whole ingest cycle open until midnight."""
        route = respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(
            return_value=httpx.Response(200, json=NATIONAL)
        )
        x = adapter(client, daily_cap=2)

        for _ in range(4):
            await x.fetch(india(), limit=5)

        assert route.call_count == 2

    @respx.mock
    async def test_each_woeid_is_a_separate_billed_request(self, client) -> None:
        """A state rolling up three cities costs three, which is why the cap
        counts requests and not regions."""
        for woeid in (1, 2, 3):
            respx.get(f"{API_BASE}/{woeid}").mock(return_value=httpx.Response(200, json=CITY))
        x = adapter(client, daily_cap=100)

        await x.fetch(maharashtra([1, 2, 3]), limit=5)

        assert await x.requests_used_today() == 3

    async def test_requests_used_is_zero_before_anything_is_spent(self) -> None:
        x = XAdapter(bearer_token=TOKEN, daily_cap=50)

        assert await x.requests_used_today() == 0

    async def test_the_counter_is_shared_across_adapter_instances(self, fake_redis) -> None:
        """The worker spends and the api reports, so a process-local count
        would make /health useless — the same lesson as the LLM budget. Needs
        the fake Redis: the suite's default is the in-process fallback, where
        two objects genuinely do not share a count."""
        spender = DailyBudget(50, name="x-requests")
        await spender.spend()

        assert await XAdapter(bearer_token=TOKEN, daily_cap=50).requests_used_today() == 1


class TestFailures:
    @respx.mock
    async def test_credits_depleted_is_its_own_error(self, client) -> None:
        """What the live account returns today. Authentication is fine — the
        response is accounted — so this must not read as a broken adapter."""
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(
            return_value=httpx.Response(
                402,
                json={
                    "detail": "credits depleted",
                    "status": 402,
                    "title": "Payment Required",
                },
            )
        )

        with pytest.raises(CreditsDepleted, match="credits depleted"):
            await adapter(client).fetch(india())

    @respx.mock
    async def test_the_402_says_the_credentials_are_not_the_problem(self, client) -> None:
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(
            return_value=httpx.Response(402, json={"detail": "credits depleted"})
        )

        with pytest.raises(CreditsDepleted, match="needs credits"):
            await adapter(client).fetch(india())

    @respx.mock
    async def test_an_unauthorised_call_raises(self, client) -> None:
        """401 is a wrong credential, which is a different fix from a 402 and
        must not be swallowed into an empty board."""
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(
            return_value=httpx.Response(401, json={"title": "Unauthorized"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await adapter(client).fetch(india())

    @respx.mock
    async def test_a_rate_limit_raises(self, client) -> None:
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(return_value=httpx.Response(429))

        with pytest.raises(httpx.HTTPStatusError):
            await adapter(client).fetch(india())

    @respx.mock
    async def test_an_unexpected_body_is_survived(self, client) -> None:
        respx.get(f"{API_BASE}/{INDIA_WOEID}").mock(
            return_value=httpx.Response(200, json=["not", "an", "object"])
        )

        assert await adapter(client).fetch(india()) == []
