"""GoogleTrendsAdapter against a recorded trendspy response.

The fixture holds the fields we actually read off TrendKeyword, recorded from a
live `trending_now` call for IN and IN-MH. The stand-in object below mirrors
trendspy's attribute access so the adapter code under test is unmodified.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import settings
from app.models import SourceName
from app.sources.google_trends import ENRICH_TOP_N, GoogleTrendsAdapter
from tests.conftest import load_json


class FakeKeyword:
    """Attribute-access stand-in for trendspy.TrendKeyword."""

    def __init__(self, row: dict[str, Any]) -> None:
        for key, value in row.items():
            setattr(self, key, value)


class FakeTrendsClient:
    def __init__(self, rows_by_geo: dict[str, list[dict[str, Any]]]) -> None:
        self._rows = rows_by_geo
        self.calls: list[dict[str, Any]] = []

    def trending_now(self, geo: str = "US", language: str = "en", hours: int = 24) -> list[Any]:
        self.calls.append({"geo": geo, "language": language, "hours": hours})
        return [FakeKeyword(r) for r in self._rows[geo]]


@pytest.fixture
def client() -> FakeTrendsClient:
    return FakeTrendsClient(
        {
            "IN": load_json("google_trends_in.json"),
            "IN-MH": load_json("google_trends_in_mh.json"),
        }
    )


def test_is_configured_without_credentials(client: FakeTrendsClient) -> None:
    # Trends needs no key, so it must never report itself unconfigured.
    assert GoogleTrendsAdapter(client=client).is_configured() is True


def test_supports_only_regions_with_a_geo_code(client, india, maharashtra, ladakh, mumbai) -> None:
    adapter = GoogleTrendsAdapter(client=client)
    assert adapter.supports(india)
    assert adapter.supports(maharashtra)
    # No geo code => skipped rather than called with a guess.
    assert not adapter.supports(ladakh)
    assert not adapter.supports(mumbai)


async def test_fetch_maps_fields_and_ranks(client: FakeTrendsClient, india) -> None:
    items = await GoogleTrendsAdapter(client=client).fetch(india, limit=5)

    assert len(items) == 5
    assert [i.rank for i in items] == [1, 2, 3, 4, 5]
    assert client.calls == [{"geo": "IN", "language": "en", "hours": 24}]

    first = items[0]
    raw = load_json("google_trends_in.json")[0]
    assert first.title == raw["keyword"]
    assert first.volume == raw["volume"]
    # topics[] is a numeric id; the adapter resolves it to a readable name.
    assert first.category == "Sports"
    assert first.extra["volume_growth_pct"] == raw["volume_growth_pct"]
    assert first.extra["related"], "related queries feed step 2's captions"
    assert len(first.extra["related"]) <= 8


async def test_fetch_respects_limit_and_region_geo(client: FakeTrendsClient, maharashtra) -> None:
    items = await GoogleTrendsAdapter(client=client).fetch(maharashtra, limit=3)

    assert len(items) == 3
    assert client.calls[0]["geo"] == "IN-MH"
    assert all(i.title for i in items)


async def test_fetch_returns_empty_for_region_without_geo(client, ladakh) -> None:
    assert await GoogleTrendsAdapter(client=client).fetch(ladakh) == []


def test_source_identity(client: FakeTrendsClient) -> None:
    adapter = GoogleTrendsAdapter(client=client)
    assert adapter.name is SourceName.google_trends
    # Highest weight of the four: it is the only demand-side signal.
    assert adapter.weight == 1.0


class FakeFrame:
    """Stand-in for the pandas frame related_queries returns."""

    def __init__(self, rows: list[str] | None, column: str = "query") -> None:
        self._rows = rows or []
        self._column = column
        self.empty = not self._rows
        self.columns = [column] if rows is not None else []

    def __getitem__(self, column: str) -> Any:
        assert column == self._column
        return _Series(self._rows)


class _Series:
    def __init__(self, rows: list[str]) -> None:
        self._rows = rows

    def tolist(self) -> list[str]:
        return list(self._rows)


class EnrichingClient(FakeTrendsClient):
    """Adds related_queries, with whatever behaviour a test needs."""

    def __init__(self, rows_by_geo, *, result: Any = None, raises: Exception | None = None):
        super().__init__(rows_by_geo)
        self._result = result
        self._raises = raises
        self.related_calls: list[str] = []

    def related_queries(self, keyword: str, **kwargs: Any) -> Any:
        self.related_calls.append(keyword)
        if self._raises:
            raise self._raises
        return self._result


def rows() -> dict[str, list[dict[str, Any]]]:
    return {
        "IN": load_json("google_trends_in.json"),
        "IN-MH": load_json("google_trends_in_mh.json"),
    }


class TestRisingQueries:
    """`trending_now` already returns the queries rising alongside each trend,
    so the explicit endpoint is an optional improvement on a list that is
    never empty."""

    async def test_rising_comes_free_with_the_main_call(self, client, india) -> None:
        items = await GoogleTrendsAdapter(client=client).fetch(india, limit=5)

        assert items[0].extra["rising"]
        assert items[0].extra["rising_source"] == "trend_keywords"
        assert client.calls and not hasattr(client, "related_calls")

    async def test_the_endpoint_is_not_called_unless_enabled(self, india, monkeypatch) -> None:
        """Five sequential requests per region, for a list we already have."""
        monkeypatch.setattr(settings, "trends_rising_queries", False)
        c = EnrichingClient(rows(), result={"rising": FakeFrame(["a", "b"])})

        await GoogleTrendsAdapter(client=c).fetch(india, limit=5)

        assert c.related_calls == []

    async def test_when_enabled_it_replaces_rising_and_says_so(self, india, monkeypatch) -> None:
        monkeypatch.setattr(settings, "trends_rising_queries", True)
        c = EnrichingClient(
            rows(), result={"rising": FakeFrame(["cyclone tracker", "cyclone live"])}
        )

        items = await GoogleTrendsAdapter(client=c).fetch(india, limit=5)

        assert items[0].extra["rising"] == ["cyclone tracker", "cyclone live"]
        assert items[0].extra["rising_source"] == "related_queries"

    async def test_only_the_head_of_the_board_is_enriched(self, india, monkeypatch) -> None:
        monkeypatch.setattr(settings, "trends_rising_queries", True)
        c = EnrichingClient(rows(), result={"rising": FakeFrame(["x"])})

        await GoogleTrendsAdapter(client=c).fetch(india, limit=20)

        assert len(c.related_calls) <= ENRICH_TOP_N

    async def test_an_empty_frame_leaves_the_free_list_alone(self, india, monkeypatch) -> None:
        """The case this machine actually produces. The endpoint answers 200
        with empty frames, and overwriting with that would report "no rising
        queries" for a topic that has eight."""
        monkeypatch.setattr(settings, "trends_rising_queries", True)
        c = EnrichingClient(rows(), result={"top": FakeFrame([]), "rising": FakeFrame([])})

        items = await GoogleTrendsAdapter(client=c).fetch(india, limit=5)

        assert items[0].extra["rising"]
        assert items[0].extra["rising_source"] == "trend_keywords"

    async def test_a_quota_error_leaves_the_free_list_alone(self, india, monkeypatch) -> None:
        """Without the referer header this is what the endpoint does, and it
        is not an incident: the unmetered call already answered."""
        monkeypatch.setattr(settings, "trends_rising_queries", True)
        c = EnrichingClient(rows(), raises=RuntimeError("API quota exceeded"))

        items = await GoogleTrendsAdapter(client=c).fetch(india, limit=5)

        assert items[0].extra["rising"]
        assert items[0].extra["rising_source"] == "trend_keywords"

    async def test_a_nonsense_result_shape_is_survived(self, india, monkeypatch) -> None:
        monkeypatch.setattr(settings, "trends_rising_queries", True)
        c = EnrichingClient(rows(), result="not a dict at all")

        items = await GoogleTrendsAdapter(client=c).fetch(india, limit=5)

        assert items[0].extra["rising_source"] == "trend_keywords"
