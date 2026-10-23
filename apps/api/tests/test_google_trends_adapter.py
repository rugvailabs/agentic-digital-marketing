"""GoogleTrendsAdapter against a recorded trendspy response.

The fixture holds the fields we actually read off TrendKeyword, recorded from a
live `trending_now` call for IN and IN-MH. The stand-in object below mirrors
trendspy's attribute access so the adapter code under test is unmodified.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.models import SourceName
from app.sources.google_trends import GoogleTrendsAdapter
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
