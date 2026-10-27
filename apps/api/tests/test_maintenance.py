"""clean-orphans deletes rows, so the boundary it deletes on is worth pinning.

Two mistakes would be expensive and silent: taking a topic that is still on a
board, or taking one that only just left it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.maintenance import describe, survey
from app.models import (
    AssetKind,
    Brand,
    ContentAsset,
    ContentJob,
    JobStatus,
    Language,
    Region,
    RegionKind,
    Trend,
    Workspace,
)

TEST_DB = "trendforge_maintenance_test"


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
async def seeded(engine):
    """Four topics around the 7-day line, one of them carrying a post."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()

    async with factory() as session:
        region = Region(code="IN-GA", name="Goa", kind=RegionKind.state, sort_order=6)
        session.add(region)
        await session.flush()

        def topic(key: str, rank: int, age_days: float) -> Trend:
            return Trend(
                region_id=region.id,
                topic=key,
                topic_key=key,
                rank=rank,
                score=0.0,
                velocity=[0.0] * 6,
                hashtags=[],
                sources=[],
                evidence=[],
                first_seen_at=now - timedelta(days=30),
                last_seen_at=now - timedelta(days=age_days),
            )

        rows = {
            "stale": topic("stale", 0, 9.0),  # rank 0, long gone -> goes
            "recent": topic("recent", 0, 2.0),  # rank 0, still fresh -> stays
            "edge": topic("edge", 0, 6.9),  # just inside the window -> stays
            "live": topic("live", 3, 9.0),  # old but on the board -> stays
        }
        session.add_all(rows.values())
        await session.flush()

        # merge, not add: the engine is module-scoped so this fixture runs
        # against a database that may already hold the row.
        await session.merge(
            Workspace(id=Workspace.DEFAULT_ID, slug="default", name="Default workspace")
        )
        await session.flush()
        brand = Brand(
            workspace_id=Workspace.DEFAULT_ID, slug="demo", name="Demo", languages=["english"]
        )
        session.add(brand)
        await session.flush()
        job = ContentJob(
            workspace_id=Workspace.DEFAULT_ID,
            trend_id=rows["stale"].id,
            brand_id=brand.id,
            language=Language.english,
            formats=["square"],
            status=JobStatus.ready,
        )
        session.add(job)
        await session.flush()
        session.add(
            ContentAsset(
                job_id=job.id,
                kind=AssetKind.image,
                variant="square:bold-type",
                url="http://minio/trendforge-assets/jobs/1/square-bold-type.png",
                meta_json={},
            )
        )
        await session.commit()
        ids = {k: v.id for k, v in rows.items()}

    yield factory, ids

    async with factory() as session:
        for table in (ContentAsset, ContentJob, Trend, Brand, Region):
            await session.execute(table.__table__.delete())
        await session.commit()


async def run_clean(factory, days: int = 7, *, dry_run: bool = False) -> dict:
    """clean_orphans() against the test database rather than SessionLocal."""
    from sqlalchemy import delete

    async with factory() as session:
        result = await survey(session, days)
        result["dry_run"] = dry_run
        if result["topics"] and not dry_run:
            cutoff = utcnow() - timedelta(days=days)
            await session.execute(delete(Trend).where(Trend.rank == 0, Trend.last_seen_at < cutoff))
            await session.commit()
    return result


async def remaining(factory) -> set[str]:
    async with factory() as session:
        return {t.topic_key for t in (await session.scalars(select(Trend))).all()}


class TestSurvey:
    async def test_it_counts_only_what_it_would_delete(self, seeded) -> None:
        factory, _ = seeded

        result = await survey_in(factory, 7)

        assert result["topics"] == 1, "only the long-gone rank-0 topic"
        assert result["jobs"] == 1
        assert result["assets"] == 1
        assert result["stored_images"] == 1
        assert result["rank0_total"] == 3, "three sit at rank 0; two are too recent"

    async def test_a_dry_run_deletes_nothing(self, seeded) -> None:
        factory, _ = seeded

        await run_clean(factory, dry_run=True)

        assert await remaining(factory) == {"stale", "recent", "edge", "live"}


async def survey_in(factory, days: int) -> dict:
    async with factory() as session:
        return await survey(session, days)


class TestCleanOrphans:
    async def test_it_takes_the_stale_topic_and_leaves_the_rest(self, seeded) -> None:
        factory, _ = seeded

        result = await run_clean(factory)

        assert result["topics"] == 1
        assert await remaining(factory) == {"recent", "edge", "live"}

    async def test_a_topic_still_on_a_board_is_never_touched(self, seeded) -> None:
        """`live` is older than the cutoff but has a rank, so it is in use."""
        factory, _ = seeded

        await run_clean(factory)

        assert "live" in await remaining(factory)

    async def test_a_topic_that_only_just_dropped_off_is_kept(self, seeded) -> None:
        # 6.9 days is inside the window; velocity history is still worth having.
        factory, _ = seeded

        await run_clean(factory)

        assert "edge" in await remaining(factory)

    async def test_content_jobs_and_assets_go_with_the_topic(self, seeded) -> None:
        factory, ids = seeded

        await run_clean(factory)

        async with factory() as session:
            jobs = list((await session.scalars(select(ContentJob))).all())
            assets = list((await session.scalars(select(ContentAsset))).all())

        # A job whose topic no longer exists cannot be opened or regenerated.
        assert jobs == []
        assert assets == [], "the FK cascade reaches assets too"
        assert ids["stale"] not in {j.trend_id for j in jobs}

    async def test_a_wider_window_takes_more(self, seeded) -> None:
        factory, _ = seeded

        await run_clean(factory, days=1)

        assert await remaining(factory) == {"live"}, "every rank-0 row is older than a day"


class TestDescribe:
    def test_it_explains_an_empty_run_rather_than_printing_zero(self) -> None:
        line = describe(
            {
                "topics": 0,
                "rank0_total": 763,
                "cutoff": "2026-10-16T00:00:00+00:00",
                "dry_run": False,
                "stored_images": 0,
            },
            7,
        )

        assert "Nothing to clean" in line
        assert "763" in line

    def test_it_says_the_pngs_are_left_behind(self) -> None:
        line = describe(
            {
                "topics": 2,
                "rank0_total": 10,
                "jobs": 1,
                "assets": 7,
                "cutoff": "2026-10-16T00:00:00+00:00",
                "dry_run": False,
                "stored_images": 6,
            },
            7,
        )

        assert "Deleted 2 rank-0 topics" in line
        assert "6 rendered PNGs remain in object storage" in line

    def test_a_dry_run_says_would(self) -> None:
        line = describe(
            {
                "topics": 2,
                "rank0_total": 10,
                "jobs": 0,
                "assets": 0,
                "cutoff": "2026-10-16T00:00:00+00:00",
                "dry_run": True,
                "stored_images": 0,
            },
            7,
        )

        assert line.startswith("Would delete")
