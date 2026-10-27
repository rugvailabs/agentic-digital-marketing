"""Workspaces, and the brand and job fields that hang off them.

Against real Postgres, because what is worth pinning here is a unique
constraint, a cascade and an enum default — none of which exist in Python.

There is one workspace and no way to make another, so most of this is about
the shape being right for when there is: a brand slug unique per workspace
rather than globally, a job carrying its own workspace rather than reaching
through its brand for one, and an editorial status that moves independently
of the pipeline status beside it.
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
    Brand,
    ContentJob,
    EditorialStatus,
    JobKind,
    JobStatus,
    Language,
    Region,
    RegionKind,
    Trend,
    Workspace,
)

TEST_DB = "trendforge_workspace_test"


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
    """Two workspaces, so "per workspace" means something."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()
    async with factory() as session:
        for table in (ContentJob, Brand, Trend, Region, Workspace):
            await session.execute(table.__table__.delete())

        default = Workspace(id=Workspace.DEFAULT_ID, slug="default", name="Default workspace")
        other = Workspace(id=2, slug="other", name="Another agency")
        region = Region(code="IN", name="India", kind=RegionKind.country, sort_order=0)
        session.add_all([default, other, region])
        await session.flush()

        trend = Trend(
            region_id=region.id,
            topic="India win the series",
            topic_key="india win series",
            rank=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(trend)
        await session.flush()
        await session.commit()
        return factory, default.id, other.id, trend.id


def brand(workspace_id: int, slug: str = "acme", **kw) -> Brand:
    kw.setdefault("name", "Acme")
    return Brand(workspace_id=workspace_id, slug=slug, **kw)


def job(workspace_id: int, brand_id: int, trend_id: int, **kw) -> ContentJob:
    kw.setdefault("language", Language.english)
    kw.setdefault("kind", JobKind.post)
    kw.setdefault("formats", ["square"])
    return ContentJob(workspace_id=workspace_id, brand_id=brand_id, trend_id=trend_id, **kw)


class TestWorkspaceOwnership:
    async def test_two_workspaces_may_each_have_the_same_brand_slug(self, seeded) -> None:
        """The slug is how a URL names a brand, and "acme" is not reserved by
        whichever agency signed up first."""
        factory, default_id, other_id, _ = seeded

        async with factory() as session:
            session.add_all([brand(default_id), brand(other_id)])
            await session.commit()

            assert await session.scalar(select(func.count()).select_from(Brand)) == 2

    async def test_one_workspace_may_not_reuse_a_slug(self, seeded) -> None:
        factory, default_id, _, _ = seeded

        async with factory() as session:
            session.add_all([brand(default_id), brand(default_id)])
            with pytest.raises(IntegrityError):
                await session.commit()

    async def test_deleting_a_workspace_takes_its_brands_and_jobs(self, seeded) -> None:
        factory, default_id, _, trend_id = seeded

        async with factory() as session:
            acme = brand(default_id)
            session.add(acme)
            await session.flush()
            session.add(job(default_id, acme.id, trend_id))
            await session.commit()

            await session.delete(await session.get(Workspace, default_id))
            await session.commit()

            assert await session.scalar(select(func.count()).select_from(Brand)) == 0
            assert await session.scalar(select(func.count()).select_from(ContentJob)) == 0

    async def test_a_job_carries_its_own_workspace(self, seeded) -> None:
        """Rather than reaching through its brand for one. The library and
        the calendar filter on it, and a join through brands on every query
        is a cost paid forever to avoid one column."""
        factory, default_id, _, trend_id = seeded

        async with factory() as session:
            acme = brand(default_id)
            session.add(acme)
            await session.flush()
            session.add(job(default_id, acme.id, trend_id))
            await session.commit()

            rows = (
                await session.scalars(
                    select(ContentJob).where(ContentJob.workspace_id == default_id)
                )
            ).all()

        assert len(rows) == 1


class TestEditorialStatus:
    async def test_a_new_job_is_a_draft(self, seeded) -> None:
        factory, default_id, _, trend_id = seeded

        async with factory() as session:
            acme = brand(default_id)
            session.add(acme)
            await session.flush()
            session.add(job(default_id, acme.id, trend_id))
            await session.commit()

            row = (await session.scalars(select(ContentJob))).one()

        assert row.editorial_status is EditorialStatus.draft
        assert row.scheduled_at is None

    async def test_it_moves_independently_of_the_pipeline_status(self, seeded) -> None:
        """A job can be `ready` and still `draft`, and a `posted` item is
        still `ready`. One column could not say both."""
        factory, default_id, _, trend_id = seeded

        async with factory() as session:
            acme = brand(default_id)
            session.add(acme)
            await session.flush()
            session.add(
                job(
                    default_id,
                    acme.id,
                    trend_id,
                    status=JobStatus.ready,
                    editorial_status=EditorialStatus.approved,
                )
            )
            await session.commit()

            row = (await session.scalars(select(ContentJob))).one()

        assert row.status is JobStatus.ready
        assert row.editorial_status is EditorialStatus.approved

    async def test_a_failed_job_can_still_be_a_draft(self, seeded) -> None:
        """The pipeline failing says nothing about where a human had got to."""
        factory, default_id, _, trend_id = seeded

        async with factory() as session:
            acme = brand(default_id)
            session.add(acme)
            await session.flush()
            session.add(job(default_id, acme.id, trend_id, status=JobStatus.failed, error="nope"))
            await session.commit()

            row = (await session.scalars(select(ContentJob))).one()

        assert row.status is JobStatus.failed
        assert row.editorial_status is EditorialStatus.draft


class TestBrandProfile:
    async def test_the_list_fields_default_to_empty_not_null(self, seeded) -> None:
        """Callers join and iterate these, so they are always lists."""
        factory, default_id, _, _ = seeded

        async with factory() as session:
            session.add(brand(default_id))
            await session.commit()

            row = (await session.scalars(select(Brand))).one()

        assert row.products == []
        assert row.do_not_mention == []
        assert row.languages == []

    async def test_a_brand_remembers_what_it_sells_and_will_not_say(self, seeded) -> None:
        factory, default_id, _, _ = seeded

        async with factory() as session:
            session.add(
                brand(
                    default_id,
                    products=["Filter coffee subscriptions", "Cold brew"],
                    do_not_mention=["Competitor Ltd", "pricing"],
                    default_region_code="IN-TN",
                )
            )
            await session.commit()

            row = (await session.scalars(select(Brand))).one()

        assert row.products[0] == "Filter coffee subscriptions"
        assert "pricing" in row.do_not_mention
        assert row.default_region_code == "IN-TN"

    async def test_the_default_region_is_a_code_not_a_foreign_key(self, seeded) -> None:
        """Regions are seeded reference data. A brand pointing at one must
        not be able to block reseeding them, so this is deliberately not a
        constraint — an unknown code falls back to the national board."""
        factory, default_id, _, _ = seeded

        async with factory() as session:
            session.add(brand(default_id, default_region_code="IN-XX"))
            await session.commit()

            assert (await session.scalars(select(Brand))).one().default_region_code == "IN-XX"
