"""Shared test fixtures. No test touches the network or the database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.models import Region, RegionKind

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def india() -> Region:
    return Region(
        id=1,
        code="IN",
        name="India",
        kind=RegionKind.country,
        google_trends_geo="IN",
        x_woeid=23424848,
        sort_order=0,
        is_active=True,
    )


@pytest.fixture
def maharashtra() -> Region:
    return Region(
        id=2,
        code="IN-MH",
        name="Maharashtra",
        kind=RegionKind.state,
        parent_id=1,
        google_trends_geo="IN-MH",
        x_woeid=None,
        sort_order=14,
        is_active=True,
    )


@pytest.fixture
def ladakh() -> Region:
    """A UT Google Trends does not serve: google_trends_geo is None."""
    return Region(
        id=3,
        code="IN-LA",
        name="Ladakh",
        kind=RegionKind.union_territory,
        parent_id=1,
        google_trends_geo=None,
        x_woeid=None,
        sort_order=20,
        is_active=True,
    )


@pytest.fixture
def mumbai() -> Region:
    return Region(
        id=4,
        code="IN-MH-BOM",
        name="Mumbai",
        kind=RegionKind.city,
        parent_id=2,
        google_trends_geo=None,
        x_woeid=2295411,
        sort_order=101,
        is_active=True,
    )


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches a Redis server, including by failing to.

    The daily budget keeps its count in Redis, and an unset url is what tells
    it to count in-process instead. Without this the suite would try to open a
    socket per budget check and rely on the refusal being fast, which is a
    network call either way. Tests that mean to exercise the Redis path
    install a fake client explicitly.
    """
    monkeypatch.setattr(settings, "redis_url", "", raising=False)
