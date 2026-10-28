"""Generate for the top N: what it queues, what it refuses, what it says.

The budget is faked. Exercising the real cap would mean spending a free
tier to prove a subtraction, and the interesting cases — nothing left, one
left, fewer left than asked for — are precisely the ones that are hard to
arrange on a live key and easy to arrange here.

Celery is faked too, for the same reason every other task test does it: a
broker in a test is a broker to keep running.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import batch as batch_api
from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.session import get_session
from app.llm.base import ProviderBudget
from app.main import app
from app.models import (
    Brand,
    ContentAsset,
    ContentJob,
    JobKind,
    Language,
    Region,
    RegionKind,
    SafetyFlag,
    Trend,
    Workspace,
)

TEST_DB = "trendforge_batch_test"


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
    """One brand and a board of ten topics, rank 1 to 10. Rank 3 is flagged
    as one we do not market against."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()

    async with factory() as session:
        for table in (ContentAsset, ContentJob, Brand, Trend, Region, Workspace):
            await session.execute(table.__table__.delete())

        session.add(Workspace(id=Workspace.DEFAULT_ID, slug="default", name="Default workspace"))
        india = Region(code="IN", name="India", kind=RegionKind.country, sort_order=0)
        empty = Region(code="IN-LA", name="Ladakh", kind=RegionKind.union_territory, sort_order=1)
        session.add_all([india, empty])
        await session.flush()

        trends = []
        for rank in range(1, 11):
            trend = Trend(
                region_id=india.id,
                topic=f"Topic {rank}",
                topic_key=f"topic {rank}",
                rank=rank,
                safety_flag=SafetyFlag.skip.value if rank == 3 else None,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(trend)
            trends.append(trend)

        brand = Brand(
            workspace_id=Workspace.DEFAULT_ID,
            slug="coffee",
            name="Madras Filter Coffee",
            languages=["english"],
        )
        session.add(brand)
        await session.commit()

    async def override() -> AsyncIterator[object]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield {"factory": factory, "brand": brand.id, "trends": [t.id for t in trends]}
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_broker(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Records what would have been dispatched."""
    sent: list[int] = []

    class Task:
        def delay(self, job_id: int) -> None:
            sent.append(job_id)

    import app.tasks.ingest as ingest

    monkeypatch.setattr(ingest, "generate_content", Task(), raising=False)
    monkeypatch.setattr(ingest, "render_video", Task(), raising=False)
    return sent


@pytest.fixture
def budget(monkeypatch: pytest.MonkeyPatch):
    """Set today's remaining model calls to whatever a test needs."""

    def make(remaining: int | None):
        class Fake:
            async def budget(self) -> ProviderBudget:
                return ProviderBudget(name="fake", configured=True, remaining_today=remaining)

        monkeypatch.setattr(batch_api, "get_llm", lambda: Fake())

    return make


@pytest.fixture
async def client(seeded) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def body(seeded, **kw) -> dict:
    return {"brand_id": seeded["brand"], "region": "IN", **kw}


class TestQueueing:
    async def test_it_queues_the_top_n(self, client, seeded, budget, no_broker) -> None:
        budget(100)

        result = (await client.post("/content/batch", json=body(seeded, n=5))).json()

        assert len(result["queued"]) == 5
        assert no_broker == result["queued"]

    async def test_in_board_order(self, client, seeded, budget) -> None:
        """A batch of three on a board is the top three, not three of the
        ten."""
        budget(100)
        await client.post("/content/batch", json=body(seeded, n=3))

        async with seeded["factory"]() as session:
            rows = (
                await session.scalars(
                    select(Trend).join(ContentJob, ContentJob.trend_id == Trend.id)
                )
            ).all()

        assert sorted(t.rank for t in rows) == [1, 2, 4]

    async def test_a_flagged_topic_is_skipped_with_a_reason(self, client, seeded, budget) -> None:
        """The planner's rule, applied here too: a batch must not be a way
        around it."""
        budget(100)

        result = (await client.post("/content/batch", json=body(seeded, n=5))).json()
        reasons = {s["topic"]: s["reason"] for s in result["skipped"]}

        assert "Topic 3" in reasons
        assert "do not market against" in reasons["Topic 3"]

    async def test_it_reaches_past_a_skip_to_fill_the_number(self, client, seeded, budget) -> None:
        """Asking for five and getting four because the third was flagged
        would be a worse answer than taking the sixth."""
        budget(100)

        result = (await client.post("/content/batch", json=body(seeded, n=5))).json()

        assert len(result["queued"]) == 5

    async def test_a_topic_this_brand_already_has_is_skipped(self, client, seeded, budget) -> None:
        budget(100)
        await client.post("/content/batch", json=body(seeded, n=2))

        again = (await client.post("/content/batch", json=body(seeded, n=2))).json()
        reasons = [s["reason"] for s in again["skipped"]]

        assert any("already has one" in reason for reason in reasons)

    async def test_another_brand_is_not_blocked_by_the_first(self, client, seeded, budget) -> None:
        """ "Already done" is per brand. Two brands posting about the same
        trend is the normal case, not a mistake."""
        budget(100)
        await client.post("/content/batch", json=body(seeded, n=2))

        async with seeded["factory"]() as session:
            other = Brand(
                workspace_id=Workspace.DEFAULT_ID, slug="tea", name="Anna Tea", languages=[]
            )
            session.add(other)
            await session.commit()
            other_id = other.id

        result = (
            await client.post("/content/batch", json={"brand_id": other_id, "region": "IN", "n": 2})
        ).json()

        assert len(result["queued"]) == 2

    async def test_a_reel_batch_queues_reels(self, client, seeded, budget) -> None:
        budget(100)

        result = (await client.post("/content/batch", json=body(seeded, n=2, kind="reel"))).json()

        async with seeded["factory"]() as session:
            kinds = (await session.scalars(select(ContentJob.kind))).all()

        assert len(result["queued"]) == 2
        assert all(kind is JobKind.reel for kind in kinds)

    async def test_the_language_is_carried(self, client, seeded, budget) -> None:
        budget(100)
        await client.post("/content/batch", json=body(seeded, n=1, language="tamil"))

        async with seeded["factory"]() as session:
            job = (await session.scalars(select(ContentJob))).one()

        assert job.language is Language.tamil

    async def test_jobs_belong_to_the_brands_workspace(self, client, seeded, budget) -> None:
        budget(100)
        await client.post("/content/batch", json=body(seeded, n=1))

        async with seeded["factory"]() as session:
            job = (await session.scalars(select(ContentJob))).one()

        assert job.workspace_id == Workspace.DEFAULT_ID


class TestBudget:
    async def test_it_queues_only_what_the_day_can_pay_for(self, client, seeded, budget) -> None:
        """Capped before anything is written. Queueing twelve and failing at
        nine leaves three rows that look like bugs and three assets nobody
        asked for."""
        budget(3)

        result = (await client.post("/content/batch", json=body(seeded, n=8))).json()

        assert len(result["queued"]) == 3

    async def test_nothing_is_written_past_the_cap(self, client, seeded, budget) -> None:
        budget(2)
        await client.post("/content/batch", json=body(seeded, n=8))

        async with seeded["factory"]() as session:
            assert await session.scalar(select(func.count()).select_from(ContentJob)) == 2

    async def test_the_message_says_why_it_is_short(self, client, seeded, budget) -> None:
        """ "Queued 3 posts" when ten were asked for is true and useless."""
        budget(3)

        result = (await client.post("/content/batch", json=body(seeded, n=8))).json()

        assert "8 were asked for" in result["message"]
        assert "3 model calls are left today" in result["message"]

    async def test_one_call_left_reads_as_one_call(self, client, seeded, budget) -> None:
        budget(1)

        result = (await client.post("/content/batch", json=body(seeded, n=5))).json()

        assert "1 model call is left today" in result["message"]
        assert "calls are" not in result["message"]

    async def test_an_exhausted_day_queues_nothing_and_says_when_it_resets(
        self, client, seeded, budget
    ) -> None:
        budget(0)

        result = (await client.post("/content/batch", json=body(seeded, n=5))).json()

        assert result["queued"] == []
        assert "used up" in result["message"]
        assert "12:30 IST" in result["message"]

    async def test_the_skipped_list_says_the_budget_was_the_reason(
        self, client, seeded, budget
    ) -> None:
        budget(2)

        result = (await client.post("/content/batch", json=body(seeded, n=5))).json()
        reasons = [s["reason"] for s in result["skipped"]]

        assert reasons.count("no model calls left today") == 3

    async def test_an_unmetered_provider_does_not_cap(self, client, seeded, budget) -> None:
        """None is not zero. A key that bills in dollars has no call count,
        and reading "unknown" as "none left" would refuse every batch on a
        paid plan."""
        budget(None)

        result = (await client.post("/content/batch", json=body(seeded, n=5))).json()

        assert len(result["queued"]) == 5
        assert result["remaining_before"] is None

    async def test_a_budget_that_cannot_be_read_does_not_fail_the_request(
        self, client, seeded, monkeypatch
    ) -> None:
        """Redis being down must not stop a user generating."""

        class Broken:
            async def budget(self):
                raise RuntimeError("redis is gone")

        monkeypatch.setattr(batch_api, "get_llm", lambda: Broken())

        result = (await client.post("/content/batch", json=body(seeded, n=3))).json()

        assert len(result["queued"]) == 3


class TestPlan:
    async def test_it_writes_nothing(self, client, seeded, budget) -> None:
        budget(100)

        await client.post("/content/batch/plan", json=body(seeded, n=5))

        async with seeded["factory"]() as session:
            assert await session.scalar(select(func.count()).select_from(ContentJob)) == 0

    async def test_it_says_the_number_the_button_should_show(self, client, seeded, budget) -> None:
        """The board's button says "Generate 3 posts" rather than "Generate
        for top 8": telling someone the real number after the fact is a
        worse moment than telling them before."""
        budget(3)

        plan = (await client.post("/content/batch/plan", json=body(seeded, n=8))).json()

        assert plan["would_queue"] == 3
        assert plan["available"] == 8
        assert plan["remaining_today"] == 3

    async def test_it_speaks_in_the_future_tense(self, client, seeded, budget) -> None:
        budget(100)

        plan = (await client.post("/content/batch/plan", json=body(seeded, n=4))).json()

        assert plan["message"] == "Ready to generate 4 posts."

    async def test_a_reel_plan_says_reels(self, client, seeded, budget) -> None:
        budget(100)

        plan = (
            await client.post("/content/batch/plan", json=body(seeded, n=2, kind="reel"))
        ).json()

        assert "reels" in plan["message"]

    async def test_an_exhausted_day_says_so_before_the_click(self, client, seeded, budget) -> None:
        budget(0)

        plan = (await client.post("/content/batch/plan", json=body(seeded, n=5))).json()

        assert plan["would_queue"] == 0
        assert plan["message"].startswith("Nothing to queue")


class TestRefusals:
    async def test_an_unknown_brand_is_a_404(self, client, budget) -> None:
        budget(100)

        response = await client.post(
            "/content/batch", json={"brand_id": 9999, "region": "IN", "n": 2}
        )

        assert response.status_code == 404

    async def test_an_unknown_region_is_a_404_naming_it(self, client, seeded, budget) -> None:
        budget(100)

        response = await client.post("/content/batch", json=body(seeded, n=2, region="XX"))

        assert response.status_code == 404
        assert "XX" in response.json()["detail"]

    async def test_an_empty_board_queues_nothing_and_says_so(self, client, seeded, budget) -> None:
        budget(100)

        result = (
            await client.post("/content/batch", json=body(seeded, n=5, region="IN-LA"))
        ).json()

        assert result["queued"] == []
        assert "no topics in range" in result["message"]

    async def test_n_is_bounded(self, client, seeded, budget) -> None:
        """A thousand would be a thousand rows and a very surprised free
        tier."""
        budget(10_000)

        assert (await client.post("/content/batch", json=body(seeded, n=0))).status_code == 422
        assert (await client.post("/content/batch", json=body(seeded, n=1000))).status_code == 422

    async def test_a_board_shorter_than_n_queues_what_there_is(
        self, client, seeded, budget
    ) -> None:
        budget(100)

        result = (await client.post("/content/batch", json=body(seeded, n=25))).json()

        # Ten topics, one of them flagged.
        assert len(result["queued"]) == 9
