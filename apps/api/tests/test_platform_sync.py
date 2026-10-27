"""`sync_platforms`: projecting per-platform rows, from either writer.

Two paths because the two board writers leave different traces. The curator
creates `trend_items` rows; the non-LLM merge does not, and it is what fills
52 of the 53 regions. Both have to end up with the same aggregation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.models import (
    Region,
    RegionKind,
    SourceName,
    Trend,
    TrendItem,
    TrendPlatform,
)
from app.tasks.merge import MergedTopic
from app.tasks.platforms import sync_platforms

TEST_DB = "trendforge_platform_sync_test"


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
async def board(engine):
    """One region, one live topic, one that has dropped off."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()
    async with factory() as session:
        for table in (TrendPlatform, TrendItem, Trend, Region):
            await session.execute(table.__table__.delete())

        region = Region(code="IN", name="India", kind=RegionKind.country, sort_order=0)
        session.add(region)
        await session.flush()

        live = Trend(
            region_id=region.id,
            topic="India win the series",
            topic_key="india win series",
            rank=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        dropped = Trend(
            region_id=region.id,
            topic="An older story",
            topic_key="older story",
            rank=0,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add_all([live, dropped])
        await session.commit()
        return factory, region.id, live.id, dropped.id


def item(region_id: int, trend_id: int | None, source: SourceName, **kw) -> TrendItem:
    kw.setdefault("rank", 1)
    kw.setdefault("title", "India win the series")
    kw.setdefault("run_id", "run-1")
    return TrendItem(region_id=region_id, trend_id=trend_id, source=source, **kw)


def merged_topic(**kw) -> MergedTopic:
    base = {
        "topic": "India win the series",
        "topic_key": "india win series",
        "score": 100.0,
        "volume": 1,
        "category": "Sports",
        "sources": ["google_trends"],
        "hashtags": ["#IndiaWin"],
    }
    base.update(kw)
    return MergedTopic(**base)


class TestFromItems:
    """The curated path."""

    async def test_one_row_per_platform_with_tags_and_url(self, board) -> None:
        factory, region_id, live_id, _ = board
        async with factory() as session:
            session.add_all(
                [
                    item(
                        region_id,
                        live_id,
                        SourceName.youtube,
                        rank=3,
                        volume=902_000,
                        url="https://youtu.be/a",
                        extra={"hashtags": ["#INDvAUS"], "tags": ["cricket"]},
                    ),
                    item(
                        region_id,
                        live_id,
                        SourceName.google_news,
                        rank=1,
                        url="https://news/a",
                        extra={},
                    ),
                ]
            )
            await session.commit()

            written = await sync_platforms(session, region_id, utcnow())
            await session.commit()

            rows = (await session.scalars(select(TrendPlatform))).all()

        assert written == 2
        by_platform = {r.platform: r for r in rows}
        yt = by_platform[SourceName.youtube]
        assert yt.rank == 3
        assert yt.volume == 902_000
        # `tags` is the uploader's keyword list and is not a hashtag.
        assert yt.hashtags == ["#INDvAUS"]
        assert yt.url == "https://youtu.be/a"

    async def test_the_best_rank_wins_and_brings_its_url(self, board) -> None:
        """A platform can carry one story twice. Its 2nd item is what that
        platform is saying about it, and the link must match the rank shown."""
        factory, region_id, live_id, _ = board
        async with factory() as session:
            session.add_all(
                [
                    item(region_id, live_id, SourceName.youtube, rank=14, url="https://low"),
                    item(region_id, live_id, SourceName.youtube, rank=2, url="https://high"),
                ]
            )
            await session.commit()
            await sync_platforms(session, region_id, utcnow())
            await session.commit()

            row = (await session.scalars(select(TrendPlatform))).one()

        assert row.rank == 2
        assert row.url == "https://high"

    async def test_volume_is_the_largest_not_the_sum(self, board) -> None:
        """Two YouTube videos about one story are not one video with their
        views added together."""
        factory, region_id, live_id, _ = board
        async with factory() as session:
            session.add_all(
                [
                    item(region_id, live_id, SourceName.youtube, rank=2, volume=900_000),
                    item(region_id, live_id, SourceName.youtube, rank=5, volume=100_000),
                ]
            )
            await session.commit()
            await sync_platforms(session, region_id, utcnow())
            await session.commit()

            row = (await session.scalars(select(TrendPlatform))).one()

        assert row.volume == 900_000

    async def test_a_dropped_topic_gets_no_row(self, board) -> None:
        """rank 0 means off the board but keep the history."""
        factory, region_id, _, dropped_id = board
        async with factory() as session:
            session.add(item(region_id, dropped_id, SourceName.youtube))
            await session.commit()

            written = await sync_platforms(session, region_id, utcnow())

        assert written == 0

    async def test_running_twice_updates_rather_than_duplicating(self, board) -> None:
        """The unique constraint is (trend_id, platform), so a cycle must
        update the row it has or the table grows with history."""
        factory, region_id, live_id, _ = board
        async with factory() as session:
            session.add(item(region_id, live_id, SourceName.youtube, rank=9, volume=5))
            await session.commit()
            await sync_platforms(session, region_id, utcnow())
            await session.commit()

            await session.execute(TrendItem.__table__.delete())
            session.add(item(region_id, live_id, SourceName.youtube, rank=4, volume=77))
            await session.commit()
            await sync_platforms(session, region_id, utcnow())
            await session.commit()

            rows = (await session.scalars(select(TrendPlatform))).all()

        assert len(rows) == 1
        assert rows[0].rank == 4
        assert rows[0].volume == 77


class TestFromMerge:
    """The uncurated path, which is 52 of the 53 regions."""

    async def test_merge_aggregates_are_used_when_there_are_no_items(self, board) -> None:
        """`trend_items` are written by the curator only, so without this
        fallback every uncurated region would report no platforms at all."""
        factory, region_id, _, _ = board
        merged = [
            merged_topic(
                platforms=[
                    {
                        "platform": SourceName.google_trends,
                        "rank": 1,
                        "volume": 200_000,
                        "hashtags": [],
                        "url": None,
                    }
                ]
            )
        ]

        async with factory() as session:
            written = await sync_platforms(session, region_id, utcnow(), merged=merged)
            await session.commit()

            row = (await session.scalars(select(TrendPlatform))).one()

        assert written == 1
        assert row.platform is SourceName.google_trends
        assert row.volume == 200_000

    async def test_items_win_over_the_merge_when_both_exist(self, board) -> None:
        """A curated region has items, and they are the better record: the
        curator has already decided which items belong to which topic."""
        factory, region_id, live_id, _ = board
        merged = [
            merged_topic(
                platforms=[
                    {
                        "platform": SourceName.google_trends,
                        "rank": 1,
                        "volume": 999,
                        "hashtags": [],
                        "url": None,
                    }
                ]
            )
        ]
        async with factory() as session:
            session.add(item(region_id, live_id, SourceName.youtube, rank=2, volume=50))
            await session.commit()

            await sync_platforms(session, region_id, utcnow(), merged=merged)
            await session.commit()

            rows = (await session.scalars(select(TrendPlatform))).all()

        assert [r.platform for r in rows] == [SourceName.youtube]

    async def test_a_merged_topic_with_no_row_is_skipped(self, board) -> None:
        """A topic the board does not carry has no id to attach to."""
        factory, region_id, _, _ = board
        merged = [
            merged_topic(
                topic="Not on the board",
                topic_key="not on board",
                platforms=[
                    {"platform": SourceName.google_news, "rank": 1, "volume": 0, "hashtags": []}
                ],
            )
        ]
        async with factory() as session:
            assert await sync_platforms(session, region_id, utcnow(), merged=merged) == 0

    async def test_a_platform_named_as_a_string_is_accepted(self, board) -> None:
        """The merge builds these dicts itself, but they round-trip through
        JSON in `trend_snapshots`, and a string comes back out."""
        factory, region_id, _, _ = board
        merged = [
            merged_topic(
                platforms=[{"platform": "google_trends", "rank": 2, "volume": 7, "hashtags": []}]
            )
        ]
        async with factory() as session:
            assert await sync_platforms(session, region_id, utcnow(), merged=merged) == 1

    async def test_nothing_at_all_writes_nothing(self, board) -> None:
        factory, region_id, _, _ = board
        async with factory() as session:
            assert await sync_platforms(session, region_id, utcnow()) == 0
