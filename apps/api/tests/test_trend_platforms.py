"""`trend_sources`: one row per platform per topic, tags never pooled.

Against a real Postgres, because the two things worth pinning are a unique
constraint and a cascade, and neither exists in Python.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.models import (
    Region,
    RegionKind,
    SourceName,
    Trend,
    TrendPlatform,
)

TEST_DB = "trendforge_platforms_test"


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

    base, _, _ = settings.database_url.rpartition("/")
    test_engine = create_async_engine(f"{base}/{TEST_DB}")
    async with test_engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()

    admin = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
    await admin.dispose()


@pytest.fixture
async def topic(engine):
    """One topic trending on three platforms, each with its own tags."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()

    async with factory() as session:
        await session.execute(TrendPlatform.__table__.delete())
        await session.execute(Trend.__table__.delete())
        await session.execute(Region.__table__.delete())

        region = Region(code="IN", name="India", kind=RegionKind.country, sort_order=0)
        session.add(region)
        await session.flush()

        trend = Trend(
            region_id=region.id,
            topic="India win the series",
            topic_key="india win series",
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(trend)
        await session.flush()

        session.add_all(
            [
                TrendPlatform(
                    trend_id=trend.id,
                    platform=SourceName.reddit,
                    rank=2,
                    volume=18_400,
                    hashtags=["#AskIndia", "#Cricket"],
                    url="https://reddit.com/r/india/comments/abc",
                    seen_at=now,
                ),
                TrendPlatform(
                    trend_id=trend.id,
                    platform=SourceName.youtube,
                    rank=14,
                    volume=902_000,
                    hashtags=["#INDvAUS", "#Highlights"],
                    seen_at=now,
                ),
                TrendPlatform(
                    trend_id=trend.id,
                    # No chart of its own, so no rank — see the column note.
                    platform=SourceName.instagram,
                    rank=None,
                    volume=51_000,
                    hashtags=["#teamindia", "#cricketreels"],
                    seen_at=now,
                ),
            ]
        )
        await session.commit()
        return factory, trend.id


async def test_a_topic_carries_one_row_per_platform(topic) -> None:
    factory, trend_id = topic

    async with factory() as session:
        trend = (await session.scalars(select(Trend).where(Trend.id == trend_id))).one()

        assert {p.platform for p in trend.platforms} == {
            SourceName.reddit,
            SourceName.youtube,
            SourceName.instagram,
        }


async def test_each_platform_keeps_its_own_hashtags(topic) -> None:
    """The point of the table. #AskIndia means nothing on Instagram and
    #cricketreels means nothing on YouTube, so pooling them produces a list
    that is wrong everywhere it is used."""
    factory, trend_id = topic

    async with factory() as session:
        trend = (await session.scalars(select(Trend).where(Trend.id == trend_id))).one()
        tags = {p.platform.value: p.hashtags for p in trend.platforms}

        assert tags["reddit"] == ["#AskIndia", "#Cricket"]
        assert tags["youtube"] == ["#INDvAUS", "#Highlights"]
        assert tags["instagram"] == ["#teamindia", "#cricketreels"]


async def test_platforms_come_back_in_a_stable_order(topic) -> None:
    """The ladder's marks and the Desk's groups are rendered from this, so
    the order cannot be whatever the planner happened to return."""
    factory, trend_id = topic

    async with factory() as session:
        first = (await session.scalars(select(Trend).where(Trend.id == trend_id))).one()
        order = [p.platform for p in first.platforms]

    async with factory() as session:
        again = (await session.scalars(select(Trend).where(Trend.id == trend_id))).one()

        assert [p.platform for p in again.platforms] == order


async def test_the_same_platform_twice_is_refused(topic) -> None:
    """An ingest cycle updates the row it has rather than appending, so the
    table stays the size of the board. trend_snapshots is the history."""
    factory, trend_id = topic

    async with factory() as session:
        session.add(
            TrendPlatform(
                trend_id=trend_id,
                platform=SourceName.reddit,
                rank=5,
                volume=1,
                hashtags=["#Dupe"],
                seen_at=utcnow(),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_a_rank_may_be_absent(topic) -> None:
    """Instagram hashtag search returns counts, not a chart. A zero would be
    a rank and would sort as the best one."""
    factory, _ = topic

    async with factory() as session:
        rows = (
            await session.scalars(
                select(TrendPlatform).where(TrendPlatform.platform == SourceName.instagram)
            )
        ).all()

        assert rows[0].rank is None
        assert rows[0].volume == 51_000


async def test_deleting_the_topic_takes_its_platform_rows(topic) -> None:
    factory, trend_id = topic

    async with factory() as session:
        trend = await session.get(Trend, trend_id)
        await session.delete(trend)
        await session.commit()

        left = await session.scalar(select(func.count()).select_from(TrendPlatform))
        assert left == 0
