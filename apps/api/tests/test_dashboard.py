"""The dashboard: one request, and every number in it measured.

The arithmetic is unit-tested directly and the shaping is checked against
real Postgres. What is worth pinning is mostly judgement rather than
mechanics — which rows count as hot, which mover wins, what happens when a
provider does not meter calls — because those are the decisions a later
change would quietly reverse.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import dashboard as dash
from app.api.dashboard import velocity_delta
from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.session import get_session
from app.llm.base import ProviderBudget
from app.main import app
from app.models import (
    AssetKind,
    Brand,
    ContentAsset,
    ContentJob,
    EditorialStatus,
    JobKind,
    JobStatus,
    Language,
    Region,
    RegionKind,
    SafetyFlag,
    Trend,
    Workspace,
)

TEST_DB = "trendforge_dashboard_test"

FLAT = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
RISING = [10.0, 10.0, 10.0, 10.0, 10.0, 40.0]
COOLING = [40.0, 40.0, 40.0, 40.0, 40.0, 5.0]


class TestVelocityDelta:
    """The one piece of arithmetic on the page, and the ladder's own."""

    def test_flat_is_zero(self) -> None:
        assert velocity_delta(FLAT) == pytest.approx(0.0)

    def test_a_rise_is_positive_and_proportional(self) -> None:
        # Last point four times the mean of the rest.
        assert velocity_delta(RISING) == pytest.approx(3.0)

    def test_a_fall_is_negative(self) -> None:
        assert velocity_delta(COOLING) < 0

    def test_a_new_topic_is_not_rising(self) -> None:
        """It is new. Calling a first data point a 100% rise would put
        every freshly ingested topic at the top of the movers."""
        assert velocity_delta([0.0, 0.0, 0.0, 0.0, 0.0, 90.0]) is None
        assert velocity_delta([90.0]) is None
        assert velocity_delta([]) is None

    def test_zeros_before_a_value_do_not_count_as_history(self) -> None:
        """The API left-pads a short series with zeros, and dividing by
        that mean is a division by zero dressed up as a huge number."""
        assert velocity_delta([0.0, 0.0, 10.0, 20.0]) == pytest.approx(1.0)


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
async def seeded(engine) -> AsyncIterator[dict]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()

    async with factory() as session:
        for table in (ContentAsset, ContentJob, Brand, Trend, Region, Workspace):
            await session.execute(table.__table__.delete())

        session.add(Workspace(id=Workspace.DEFAULT_ID, slug="default", name="Default workspace"))
        india = Region(code="IN", name="India", kind=RegionKind.country, sort_order=0)
        session.add(india)
        await session.flush()
        hot = Region(
            code="IN-GA", name="Goa", kind=RegionKind.state, parent_id=india.id, sort_order=1
        )
        cold = Region(
            code="IN-TN", name="Tamil Nadu", kind=RegionKind.state, parent_id=india.id, sort_order=2
        )
        session.add_all([hot, cold])
        await session.flush()

        def trend(region, topic, key, rank, velocity, volume=1000, flag=None) -> Trend:
            row = Trend(
                region_id=region.id,
                topic=topic,
                topic_key=key,
                rank=rank,
                volume=volume,
                velocity=velocity,
                safety_flag=flag,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(row)
            return row

        # Goa: two of three rising. Tamil Nadu: none of two.
        trend(hot, "Goa a", "goa a", 1, RISING)
        trend(hot, "Goa b", "goa b", 2, RISING)
        trend(hot, "Goa c", "goa c", 3, FLAT)
        trend(cold, "TN a", "tn a", 1, FLAT)
        trend(cold, "TN b", "tn b", 2, COOLING)
        # Flagged and off-board rows, which must not reach the map.
        trend(hot, "Goa crash", "goa crash", 4, RISING, flag=SafetyFlag.skip.value)
        trend(hot, "Goa old", "goa old", 0, RISING)
        # A national duplicate of a state story, to prove the movers fold.
        biggest = trend(india, "Shared surge", "shared surge", 5, [1.0, 1.0, 1.0, 1.0, 1.0, 99.0])
        trend(hot, "Shared surge", "shared surge", 6, [1.0, 1.0, 1.0, 1.0, 1.0, 99.0])
        # Rising but with nobody searching for it. On the national board,
        # which the state map does not draw, so it tests the movers'
        # volume filter without warming Tamil Nadu.
        trend(india, "Silent riser", "silent riser", 3, RISING, volume=0)
        await session.flush()

        brand = Brand(
            workspace_id=Workspace.DEFAULT_ID, slug="demo", name="Demo", languages=["english"]
        )
        session.add(brand)
        await session.flush()

        def job(trend_row, kind, *, age_days=0, status=JobStatus.ready, scheduled=None):
            row = ContentJob(
                workspace_id=Workspace.DEFAULT_ID,
                brand_id=brand.id,
                trend_id=trend_row.id,
                kind=kind,
                language=Language.english,
                formats=["square"],
                status=status,
                editorial_status=(
                    EditorialStatus.scheduled if scheduled else EditorialStatus.draft
                ),
                scheduled_at=scheduled,
                created_at=now - timedelta(days=age_days),
            )
            session.add(row)
            return row

        recent = job(biggest, JobKind.post)
        job(biggest, JobKind.post, age_days=2)
        job(biggest, JobKind.reel, age_days=3)
        # Outside the week, so it must not be counted.
        job(biggest, JobKind.post, age_days=9)
        # Failed today, which the pipeline panel has to surface.
        job(biggest, JobKind.post, status=JobStatus.failed)
        # Scheduled: one behind, three ahead. Only the ahead ones are next.
        job(biggest, JobKind.post, scheduled=now - timedelta(hours=3))
        job(biggest, JobKind.post, scheduled=now + timedelta(hours=5))
        job(biggest, JobKind.post, scheduled=now + timedelta(hours=2))
        job(biggest, JobKind.reel, scheduled=now + timedelta(days=2))
        await session.flush()

        session.add_all(
            [
                ContentAsset(
                    job_id=recent.id,
                    kind=AssetKind.caption,
                    variant="english",
                    meta_json={"hook": "The hook, not the topic"},
                ),
                ContentAsset(
                    job_id=recent.id,
                    kind=AssetKind.image,
                    variant="square:poster",
                    url="http://minio/poster.png",
                ),
            ]
        )
        await session.commit()

    async def override() -> AsyncIterator[object]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield {"factory": factory, "captioned": recent.id}
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def budget(monkeypatch: pytest.MonkeyPatch):
    """A metered provider and an unmetered one, which is the real shape."""

    class Fake:
        async def statuses(self):
            return [
                ProviderBudget(
                    name="gemini",
                    configured=True,
                    remaining_today=130,
                    used_today=30,
                    reserved_for_desk=40,
                ),
                ProviderBudget(name="openrouter", configured=True, remaining_usd=100.0),
            ]

    monkeypatch.setattr(dash, "get_llm", lambda: Fake())


@pytest.fixture
async def client(seeded) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def board(client: httpx.AsyncClient) -> dict:
    response = await client.get("/dashboard")
    assert response.status_code == 200, response.text
    return response.json()


class TestHeat:
    async def test_one_entry_per_state(self, client) -> None:
        heat = (await board(client))["heat"]

        assert sorted(s["region_code"] for s in heat) == ["IN-GA", "IN-TN"]

    async def test_the_country_is_not_a_state(self, client) -> None:
        """India has its own board, and a national row on a choropleth of
        states is a row with nowhere to be drawn."""
        heat = (await board(client))["heat"]

        assert all(s["region_code"] != "IN" for s in heat)

    async def test_share_is_rising_over_topics(self, client) -> None:
        heat = {s["region_code"]: s for s in (await board(client))["heat"]}

        assert heat["IN-GA"]["rising"] == 3
        assert heat["IN-GA"]["topics"] == 4
        assert heat["IN-GA"]["share"] == pytest.approx(0.75)

    async def test_a_board_with_nothing_moving_is_cold_not_absent(self, client) -> None:
        """A state with no risers still has to be drawn, or it reads as
        missing data rather than as a quiet day."""
        heat = {s["region_code"]: s for s in (await board(client))["heat"]}

        assert heat["IN-TN"]["rising"] == 0
        assert heat["IN-TN"]["share"] == 0

    async def test_flagged_and_off_board_topics_are_not_counted(self, client) -> None:
        """Goa has six rows; two are a flagged topic and a dropped one."""
        heat = {s["region_code"]: s for s in (await board(client))["heat"]}

        assert heat["IN-GA"]["topics"] == 4


class TestMovers:
    async def test_ordered_by_how_hard_they_are_climbing(self, client) -> None:
        """Not by rank. A topic that is twelfth and accelerating is the
        news; one that has been first all day is not."""
        movers = (await board(client))["movers"]

        assert movers[0]["topic"] == "Shared surge"
        assert [m["delta"] for m in movers] == sorted((m["delta"] for m in movers), reverse=True)

    async def test_one_story_fills_one_slot(self, client) -> None:
        """A national surge sits on every board, and five copies of one
        headline is not five movers."""
        movers = (await board(client))["movers"]
        topics = [m["topic"] for m in movers]

        assert topics.count("Shared surge") == 1

    async def test_a_riser_nobody_is_searching_for_is_not_a_mover(self, client) -> None:
        """A percentage climb on zero volume is a rounding error on a
        small board."""
        movers = (await board(client))["movers"]

        assert all(m["topic"] != "Silent riser" for m in movers)

    async def test_flat_and_falling_topics_are_not_movers(self, client) -> None:
        movers = (await board(client))["movers"]

        assert all(m["delta"] > 0 for m in movers)
        assert all(m["topic"] not in {"Goa c", "TN a", "TN b"} for m in movers)

    async def test_it_carries_the_series_for_the_sparkline(self, client) -> None:
        movers = (await board(client))["movers"]

        assert len(movers[0]["velocity"]) == 6


class TestWeek:
    async def test_it_counts_the_last_seven_days_only(self, client) -> None:
        week = (await board(client))["week"]

        # Nine jobs exist; the nine-day-old post is the one left out.
        assert week["posts"] == 6
        assert week["reels"] == 2

    async def test_the_title_is_the_hook_where_there_is_one(self, client, seeded) -> None:
        # By id, not by position: six of these jobs were created inside the
        # same microsecond, so which one is "first" is the id tiebreak.
        items = {i["job_id"]: i for i in (await board(client))["week"]["items"]}

        assert items[seeded["captioned"]]["title"] == "The hook, not the topic"

    async def test_it_carries_a_poster(self, client, seeded) -> None:
        items = {i["job_id"]: i for i in (await board(client))["week"]["items"]}

        assert items[seeded["captioned"]]["preview_url"] == "http://minio/poster.png"

    async def test_an_item_with_no_caption_falls_back_to_its_topic(self, client) -> None:
        items = (await board(client))["week"]["items"]
        bare = [i for i in items if i["preview_url"] is None]

        assert bare and all(i["title"] == "Shared surge" for i in bare)


class TestScheduled:
    async def test_only_what_is_still_ahead(self, client) -> None:
        """A dashboard is about what happens next. The calendar is where
        the past is."""
        items = (await board(client))["scheduled"]

        assert len(items) == 3

    async def test_soonest_first(self, client) -> None:
        items = (await board(client))["scheduled"]
        times = [i["scheduled_at"] for i in items]

        assert times == sorted(times)

    async def test_drafts_are_not_scheduled_items(self, client) -> None:
        items = (await board(client))["scheduled"]

        assert len(items) < 9


class TestBudget:
    async def test_a_metered_provider_gets_a_denominator(self, client) -> None:
        """A bar needs one, and the client should not have to invent it."""
        bars = {b["name"]: b for b in (await board(client))["budget"]}

        assert bars["gemini"]["limit"] == 160
        assert bars["gemini"]["used_today"] == 30

    async def test_the_desk_reserve_is_reported(self, client) -> None:
        bars = {b["name"]: b for b in (await board(client))["budget"]}

        assert bars["gemini"]["reserved_for_desk"] == 40

    async def test_a_provider_that_bills_money_has_no_call_limit(self, client) -> None:
        """None is not zero. Drawing a bar at 0% for a paid key would say
        the opposite of what is true."""
        bars = {b["name"]: b for b in (await board(client))["budget"]}

        assert bars["openrouter"]["limit"] is None
        assert bars["openrouter"]["remaining_usd"] == 100.0

    async def test_an_unreadable_budget_does_not_fail_the_page(self, client, monkeypatch) -> None:
        """Redis being down must cost the bars, not the dashboard."""

        class Broken:
            async def statuses(self):
                raise RuntimeError("redis is gone")

        monkeypatch.setattr(dash, "get_llm", lambda: Broken())

        body = await board(client)

        assert body["budget"] == []
        assert body["heat"]


class TestPipeline:
    async def test_it_reports_the_board_size(self, client) -> None:
        pipeline = (await board(client))["pipeline"]

        assert pipeline["database"] is True
        assert pipeline["trends"] > 0

    async def test_it_surfaces_today_s_failures(self, client) -> None:
        """A dashboard that hides these hides the only thing on the page
        that needs doing something about."""
        pipeline = (await board(client))["pipeline"]

        assert pipeline["failed_today"] == 1

    async def test_last_ingest_is_the_freshest_row(self, client) -> None:
        pipeline = (await board(client))["pipeline"]

        assert pipeline["last_ingest_at"] is not None
