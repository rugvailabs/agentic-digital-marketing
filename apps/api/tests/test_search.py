"""The global search box: topics, brands and generated work in one answer.

Against real Postgres, because the whole of it is SQL — an ILIKE with user
text in it, a workspace filter, and an ordering the fold depends on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models import (
    AssetKind,
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

TEST_DB = "trendforge_search_test"


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
        tn = Region(
            code="IN-TN", name="Tamil Nadu", kind=RegionKind.state, parent_id=india.id, sort_order=1
        )
        ga = Region(
            code="IN-GA", name="Goa", kind=RegionKind.state, parent_id=india.id, sort_order=2
        )
        session.add_all([tn, ga])
        await session.flush()

        def trend(region, topic: str, key: str, rank: int, flag: str | None = None) -> Trend:
            row = Trend(
                region_id=region.id,
                topic=topic,
                topic_key=key,
                rank=rank,
                safety_flag=flag,
                # Minted per board, which is exactly why the fold cannot use
                # it — a different value here for the same story.
                cluster_id=f"c-{region.code}-{key}",
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(row)
            return row

        # One national story carried on all three boards, best on IN-TN.
        national = trend(tn, "India seal the cricket series", "india seal cricket series", 1)
        trend(india, "India seal the cricket series", "india seal cricket series", 3)
        trend(ga, "India seal the cricket series", "india seal cricket series", 9)
        # And some rows that are their own stories.
        trend(ga, "Goa cuts jet fuel VAT", "goa cuts jet fuel vat", 4)
        trend(india, "Cricket board names the squad", "cricket board names squad", 6)
        # Flagged, and so never a destination.
        trend(
            india,
            "Cricket stadium crush kills two",
            "cricket stadium crush",
            2,
            SafetyFlag.skip.value,
        )
        # Off the board entirely.
        trend(india, "Cricket kit sales fall", "cricket kit sales fall", 0)
        # Literal wildcards, to prove the escaping.
        trend(india, "Jet fuel down 100% on paper", "jet fuel down 100 on paper", 12)
        await session.flush()

        coffee = Brand(
            workspace_id=Workspace.DEFAULT_ID,
            slug="madras-filter-coffee",
            name="Madras Filter Coffee",
            languages=["english"],
        )
        session.add(coffee)
        await session.flush()

        job = ContentJob(
            workspace_id=Workspace.DEFAULT_ID,
            brand_id=coffee.id,
            trend_id=national.id,
            kind=JobKind.post,
            language=Language.english,
            formats=["square"],
        )
        session.add(job)
        await session.flush()
        session.add_all(
            [
                ContentAsset(
                    job_id=job.id,
                    kind=AssetKind.caption,
                    variant="english",
                    meta_json={"hook": "A series worth closing the shop for"},
                ),
                ContentAsset(
                    job_id=job.id,
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
    yield {"factory": factory, "brand": coffee.id, "job": job.id, "trend": national.id}
    app.dependency_overrides.clear()


@pytest.fixture
async def client(seeded) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def find(client: httpx.AsyncClient, q: str) -> dict:
    response = await client.get(f"/search?q={quote(q)}")
    assert response.status_code == 200, response.text
    return response.json()


class TestTopics:
    async def test_it_finds_a_topic_by_substring(self, client) -> None:
        topics = (await find(client, "jet fuel"))["topics"]

        assert any("jet fuel" in t["topic"].lower() for t in topics)

    async def test_it_is_case_insensitive(self, client) -> None:
        assert (await find(client, "CRICKET"))["total"] == (await find(client, "cricket"))["total"]

    async def test_one_story_on_many_boards_is_one_result(self, client) -> None:
        """Searching a national story returned the same headline once per
        board, which on India's 36 boards fills the panel with one answer."""
        topics = (await find(client, "seal the cricket"))["topics"]

        assert len(topics) == 1

    async def test_the_kept_board_is_the_best_ranked_one(self, client) -> None:
        """A topic that is first in Tamil Nadu is a more useful destination
        than the same topic ninth in Goa."""
        hit = (await find(client, "seal the cricket"))["topics"][0]

        assert hit["region_code"] == "IN-TN"
        assert hit["rank"] == 1

    async def test_the_others_are_counted_rather_than_dropped_silently(self, client) -> None:
        hit = (await find(client, "seal the cricket"))["topics"][0]

        assert hit["also_on"] == 2

    async def test_a_story_on_one_board_says_so(self, client) -> None:
        hit = (await find(client, "jet fuel VAT"))["topics"][0]

        assert hit["also_on"] == 0

    async def test_the_fold_does_not_use_cluster_id(self, client) -> None:
        """Cluster ids are minted per board, so the same story carries a
        different one on each. Folding on them collapses nothing across
        boards, which is how the first version shipped looking broken."""
        folded = (await find(client, "seal the cricket"))["topics"]

        assert len(folded) == 1

    async def test_a_flagged_topic_is_never_offered(self, client) -> None:
        """The planner will not write about it, so a result is a dead end."""
        topics = (await find(client, "crush"))["topics"]

        assert topics == []

    async def test_a_topic_off_the_board_is_not_offered(self, client) -> None:
        topics = (await find(client, "kit sales"))["topics"]

        assert topics == []


class TestBrands:
    async def test_by_name(self, client) -> None:
        assert (await find(client, "Madras"))["brands"][0]["name"] == "Madras Filter Coffee"

    async def test_by_slug(self, client) -> None:
        assert len((await find(client, "madras-filter"))["brands"]) == 1

    async def test_it_carries_the_colours_for_the_swatch(self, client) -> None:
        brand = (await find(client, "Madras"))["brands"][0]

        assert brand["primary_color"].startswith("#")
        assert brand["secondary_color"].startswith("#")


class TestWork:
    async def test_generated_work_is_found_by_its_topic(self, client) -> None:
        work = (await find(client, "seal the cricket"))["work"]

        assert len(work) == 1
        assert work[0]["brand_name"] == "Madras Filter Coffee"

    async def test_the_title_is_the_hook_where_there_is_one(self, client) -> None:
        """The same thing the library shows as a row title: the topic says
        what it is about, the hook says what this post said."""
        hit = (await find(client, "seal the cricket"))["work"][0]

        assert hit["title"] == "A series worth closing the shop for"
        assert hit["topic"] == "India seal the cricket series"

    async def test_it_carries_a_preview(self, client) -> None:
        assert (await find(client, "seal the cricket"))["work"][0]["preview_url"] is not None

    async def test_it_carries_where_the_item_has_got_to(self, client) -> None:
        assert (await find(client, "seal the cricket"))["work"][0]["editorial_status"] == "draft"


class TestRefusals:
    @pytest.mark.parametrize("q", ["", " ", "a", " x "])
    async def test_a_query_too_short_to_mean_anything_returns_nothing(self, client, q) -> None:
        """One character matches most of the board, which is a slow way of
        saying nothing."""
        assert (await find(client, q))["total"] == 0

    async def test_a_percent_sign_is_a_percent_sign(self, client) -> None:
        """Unescaped it is an ILIKE wildcard, so "%" would match the whole
        table and "100%" would match everything containing "100"."""
        assert (await find(client, "100%"))["total"] == 1
        assert (await find(client, "%%"))["total"] == 0

    async def test_an_underscore_is_an_underscore(self, client) -> None:
        # "_" matches any single character unescaped, so this would hit
        # "jet fuel" via "l fu".
        assert (await find(client, "l_fu"))["total"] == 0

    async def test_nothing_found_is_an_empty_answer_not_an_error(self, client) -> None:
        body = await find(client, "zzzzz")

        assert body["total"] == 0
        assert body["topics"] == [] and body["brands"] == [] and body["work"] == []

    async def test_the_query_comes_back_so_the_panel_can_echo_it(self, client) -> None:
        assert (await find(client, "  cricket  "))["query"] == "cricket"
