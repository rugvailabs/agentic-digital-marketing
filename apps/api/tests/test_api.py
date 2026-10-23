"""Endpoint tests against a real Postgres schema on an isolated database.

They exercise the SQL (outer joins, the rank > 0 filters, the freshness
aggregate) — the part most likely to break — so an in-memory fake would prove
nothing. Skipped automatically when no database is reachable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models import PipelineStatus, Region, RegionKind, Trend

TEST_DB = "trendforge_test"
DROPPED_TOPIC = "Yesterdays news"


def _test_url() -> str:
    base, _, _ = settings.database_url.rpartition("/")
    return f"{base}/{TEST_DB}"


@pytest.fixture(scope="module")
async def engine() -> AsyncIterator[object]:
    admin = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
            await conn.exec_driver_sql(f'CREATE DATABASE "{TEST_DB}"')
    except Exception as exc:  # pragma: no cover - CI without a database
        pytest.skip(f"no database available: {type(exc).__name__}")
    finally:
        await admin.dispose()

    test_engine = create_async_engine(_test_url())
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()

    admin = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
    await admin.dispose()


@pytest.fixture
async def seeded(engine) -> AsyncIterator[None]:
    """India + Maharashtra + Ladakh, with a small hand-built board."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()

    async with session_factory() as session:
        india = Region(
            code="IN",
            name="India",
            kind=RegionKind.country,
            sort_order=0,
            google_trends_geo="IN",
            x_woeid=23424848,
        )
        session.add(india)
        await session.flush()

        mh = Region(
            code="IN-MH",
            name="Maharashtra",
            kind=RegionKind.state,
            parent_id=india.id,
            sort_order=14,
            google_trends_geo="IN-MH",
        )
        # A region that has never been ingested: must still appear on the strip.
        ladakh = Region(
            code="IN-LA",
            name="Ladakh",
            kind=RegionKind.union_territory,
            parent_id=india.id,
            sort_order=20,
        )
        session.add_all([mh, ladakh])
        await session.flush()

        for i in range(1, 4):
            session.add(
                Trend(
                    region_id=mh.id,
                    topic=f"Topic {i}",
                    topic_key=f"topic {i}",
                    category="Sports",
                    rank=i,
                    score=100.0 - i,
                    volume=1000 * i,
                    velocity=[0.0, 0.0, 0.0, 0.0, 90.0, 100.0 - i],
                    hashtags=[f"#Topic{i}"],
                    sources=["google_trends"],
                    evidence=[{"source": "google_trends", "rank": i, "url": None}],
                    status=PipelineStatus.curated,
                    first_seen_at=now - timedelta(hours=1),
                    last_seen_at=now,
                )
            )
        # rank 0 = dropped off the board; keeps history, must never be served.
        session.add(
            Trend(
                region_id=mh.id,
                topic=DROPPED_TOPIC,
                topic_key="yesterdays news",
                rank=0,
                score=0.0,
                velocity=[90.0, 80.0, 50.0, 20.0, 10.0, 0.0],
                hashtags=[],
                sources=["google_news"],
                evidence=[],
                status=PipelineStatus.curated,
                first_seen_at=now - timedelta(days=1),
                last_seen_at=now - timedelta(hours=2),
            )
        )
        await session.commit()

    async def override() -> AsyncIterator[object]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield
    app.dependency_overrides.clear()

    async with session_factory() as session:
        await session.execute(Trend.__table__.delete())
        await session.execute(Region.__table__.delete())
        await session.commit()


@pytest.fixture
async def client(seeded) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_reports_counts_and_ist(client: httpx.AsyncClient) -> None:
    body = (await client.get("/health")).json()

    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["regions"] == 3
    assert body["now_ist"].endswith("+05:30")
    assert "google_trends" in body["sources_configured"]


async def test_regions_are_ordered_and_carry_parent_and_counts(client: httpx.AsyncClient) -> None:
    body = (await client.get("/regions")).json()

    assert [r["code"] for r in body] == ["IN", "IN-MH", "IN-LA"]
    assert body[0]["parent_code"] is None
    assert body[1]["parent_code"] == "IN"
    # Only rank > 0 rows count, so the dropped-off row is excluded.
    assert body[1]["trend_count"] == 3
    # Never ingested, but still listed — the strip shows all 36 states/UTs.
    assert body[2]["trend_count"] == 0


async def test_regions_filters(client: httpx.AsyncClient) -> None:
    states = (await client.get("/regions", params={"kind": "state"})).json()
    assert [r["code"] for r in states] == ["IN-MH"]

    populated = (await client.get("/regions", params={"with_trends_only": True})).json()
    assert [r["code"] for r in populated] == ["IN-MH"]


async def test_trends_returns_the_ladder_in_rank_order(client: httpx.AsyncClient) -> None:
    body = (await client.get("/trends", params={"region": "IN-MH"})).json()

    assert body["region"]["name"] == "Maharashtra"
    assert body["count"] == 3
    assert [t["rank"] for t in body["trends"]] == [1, 2, 3]

    first = body["trends"][0]
    assert first["topic"] == "Topic 1"
    assert first["category"] == "Sports"
    assert first["hashtags"] == ["#Topic1"]
    assert first["sources"] == ["google_trends"]
    assert len(first["velocity"]) == 6, "the sparkline always gets six points"
    assert first["volume"] == 1000
    assert first["evidence"][0]["source"] == "google_trends"
    assert body["updated_at"] is not None


async def test_trends_excludes_dropped_off_rows(client: httpx.AsyncClient) -> None:
    body = (await client.get("/trends", params={"region": "IN-MH", "limit": 100})).json()

    topics = [t["topic"] for t in body["trends"]]
    assert DROPPED_TOPIC not in topics
    assert len(topics) == 3


async def test_trends_respects_limit(client: httpx.AsyncClient) -> None:
    body = (await client.get("/trends", params={"region": "IN-MH", "limit": 2})).json()

    assert len(body["trends"]) == 2
    # count stays the full board size so the UI can say "2 of 3".
    assert body["count"] == 3


async def test_trends_for_a_never_ingested_region_is_empty_not_an_error(client) -> None:
    body = (await client.get("/trends", params={"region": "IN-LA"})).json()

    assert body["trends"] == []
    assert body["count"] == 0
    assert body["updated_at"] is None


async def test_trends_unknown_region_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/trends", params={"region": "XX-ZZ"})

    assert response.status_code == 404
    assert "unknown region" in response.json()["detail"]


@pytest.mark.parametrize("limit", [0, -1, 101])
async def test_trends_rejects_out_of_range_limits(client: httpx.AsyncClient, limit: int) -> None:
    response = await client.get("/trends", params={"region": "IN-MH", "limit": limit})
    assert response.status_code == 422


async def test_openapi_documents_the_board_contract(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()

    assert "/trends" in schema["paths"]
    assert "/regions" in schema["paths"]
    assert "/ingest/run" in schema["paths"]
    # @trendforge/types is generated from these; renaming them breaks the web app.
    assert {"TrendOut", "RegionOut", "TrendsResponse"} <= set(schema["components"]["schemas"])
