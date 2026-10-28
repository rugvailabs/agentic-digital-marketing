"""The content library and the editorial status that moves through it.

Against real Postgres, because almost everything worth pinning is SQL: a
region filter that rolls a country up over its states, a JSONB containment
on formats, a count that has to agree with the page beside it, and an order
that has to be stable across a page boundary.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy import select
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
    EditorialStatus,
    JobKind,
    JobStatus,
    Language,
    Region,
    RegionKind,
    Trend,
    Workspace,
)

TEST_DB = "trendforge_library_test"


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
    """Two brands, three regions and eight items, varied along every axis a
    filter can ask about."""
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
            code="IN-TN",
            name="Tamil Nadu",
            kind=RegionKind.state,
            parent_id=india.id,
            sort_order=1,
        )
        goa = Region(
            code="IN-GA", name="Goa", kind=RegionKind.state, parent_id=india.id, sort_order=2
        )
        session.add_all([tn, goa])
        await session.flush()

        trends = {}
        for key, region, topic in [
            ("national", india, "India seal the series"),
            ("tn", tn, "Chennai metro phase two"),
            ("goa", goa, "Goa unveils AI policy"),
        ]:
            trend = Trend(
                region_id=region.id,
                topic=topic,
                topic_key=topic.lower(),
                rank=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(trend)
            trends[key] = trend
        await session.flush()

        coffee = Brand(
            workspace_id=Workspace.DEFAULT_ID,
            slug="coffee",
            name="Madras Filter Coffee",
            languages=["english", "tamil"],
        )
        tea = Brand(
            workspace_id=Workspace.DEFAULT_ID,
            slug="tea",
            name="Anna Tea",
            languages=["english"],
        )
        session.add_all([coffee, tea])
        await session.flush()

        # id, brand, trend, kind, language, formats, editorial, age in hours
        plan = [
            (coffee, "national", JobKind.post, Language.english, ["square", "portrait"], 0),
            (coffee, "tn", JobKind.post, Language.tamil, ["square"], 2),
            (coffee, "tn", JobKind.reel, Language.tamil, ["reel"], 4),
            (coffee, "goa", JobKind.post, Language.hindi, ["portrait"], 26),
            (tea, "national", JobKind.post, Language.english, ["square"], 28),
            (tea, "goa", JobKind.reel, Language.english, ["reel"], 50),
            (tea, "goa", JobKind.post, Language.english, ["square"], 52),
            (tea, "tn", JobKind.post, Language.english, ["square"], 54),
        ]
        jobs = []
        for brand, trend_key, kind, language, formats, hours in plan:
            job = ContentJob(
                workspace_id=Workspace.DEFAULT_ID,
                brand_id=brand.id,
                trend_id=trends[trend_key].id,
                kind=kind,
                language=language,
                formats=formats,
                status=JobStatus.ready,
                created_at=now - timedelta(hours=hours),
            )
            session.add(job)
            jobs.append(job)
        await session.flush()

        # One item with real assets, so the row's hook, preview and count
        # are read off something rather than always being null.
        session.add_all(
            [
                ContentAsset(
                    job_id=jobs[0].id,
                    kind=AssetKind.caption,
                    variant="english",
                    meta_json={"hook": "India seal it in Chennai", "caption": "..."},
                ),
                ContentAsset(
                    job_id=jobs[0].id,
                    kind=AssetKind.image,
                    variant="square:poster",
                    url="http://minio/square-poster.png",
                ),
                ContentAsset(
                    job_id=jobs[0].id,
                    kind=AssetKind.image,
                    variant="square:wire",
                    url="http://minio/square-wire.png",
                ),
            ]
        )
        await session.commit()

    async def override() -> AsyncIterator[object]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield {
        "factory": factory,
        "jobs": [job.id for job in jobs],
        "brands": {
            "coffee": coffee.id,
            "tea": tea.id,
        },
    }
    app.dependency_overrides.clear()


@pytest.fixture
async def client(seeded) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def ids(client: httpx.AsyncClient, query: str = "") -> list[int]:
    response = await client.get(f"/library{query}")
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def total(client: httpx.AsyncClient, query: str = "") -> int:
    return (await client.get(f"/library{query}")).json()["total"]


class TestListing:
    async def test_everything_this_workspace_made(self, client: httpx.AsyncClient) -> None:
        assert len(await ids(client)) == 8

    async def test_newest_first(self, client: httpx.AsyncClient) -> None:
        """The library opens on what was just generated, not on the oldest
        thing anyone ever made."""
        body = (await client.get("/library")).json()["items"]
        times = [item["created_at"] for item in body]

        assert times == sorted(times, reverse=True)

    async def test_a_row_carries_what_a_row_shows(self, client: httpx.AsyncClient) -> None:
        newest = (await client.get("/library?limit=1")).json()["items"][0]

        assert newest["brand_name"] == "Madras Filter Coffee"
        assert newest["topic"] == "India seal the series"
        assert newest["region_name"] == "India"
        assert newest["hook"] == "India seal it in Chennai"
        assert newest["preview_url"] == "http://minio/square-poster.png"
        assert newest["asset_count"] == 3

    async def test_an_item_with_no_assets_yet_says_so_rather_than_breaking(
        self, client: httpx.AsyncClient
    ) -> None:
        """Every row but the first has none, which is what a queued or
        failed job looks like."""
        rows = (await client.get("/library")).json()["items"]
        bare = [row for row in rows if row["asset_count"] == 0]

        assert len(bare) == 7
        assert all(row["preview_url"] is None and row["hook"] is None for row in bare)

    async def test_a_caption_is_not_offered_as_a_thumbnail(self, client: httpx.AsyncClient) -> None:
        """A caption has no url, and a scan over a list that has one first
        would otherwise return it."""
        newest = (await client.get("/library?limit=1")).json()["items"][0]

        assert newest["preview_url"].endswith(".png")

    async def test_a_reel_previews_with_its_poster_not_its_mp4(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        """A <video> draws nothing until it has fetched a frame, so a list
        of reels renders as a column of empty boxes. The renderer already
        saves a poster beside the video."""
        reel_id = seeded["jobs"][2]
        async with seeded["factory"]() as session:
            session.add(
                ContentAsset(
                    job_id=reel_id,
                    kind=AssetKind.video,
                    variant="reel:wire",
                    url="http://minio/reel.mp4",
                    meta_json={"poster_url": "http://minio/reel-poster.jpg"},
                )
            )
            await session.commit()

        rows = (await client.get("/library?kind=reel")).json()["items"]
        row = next(item for item in rows if item["id"] == reel_id)

        assert row["preview_url"] == "http://minio/reel-poster.jpg"

    async def test_a_reel_with_no_poster_previews_with_nothing(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        """Rather than with an mp4 the thumbnail cannot draw."""
        reel_id = seeded["jobs"][5]
        async with seeded["factory"]() as session:
            session.add(
                ContentAsset(
                    job_id=reel_id,
                    kind=AssetKind.video,
                    variant="reel:wire",
                    url="http://minio/reel.mp4",
                    meta_json={},
                )
            )
            await session.commit()

        rows = (await client.get("/library?kind=reel")).json()["items"]
        row = next(item for item in rows if item["id"] == reel_id)

        assert row["preview_url"] is None


class TestFilters:
    async def test_by_brand(self, client: httpx.AsyncClient, seeded) -> None:
        assert await total(client, f"?brand_id={seeded['brands']['tea']}") == 4

    async def test_by_kind(self, client: httpx.AsyncClient) -> None:
        assert await total(client, "?kind=reel") == 2
        assert await total(client, "?kind=post") == 6

    async def test_by_language(self, client: httpx.AsyncClient) -> None:
        assert await total(client, "?language=tamil") == 2
        assert await total(client, "?language=bengali") == 0

    async def test_a_state_shows_only_its_own(self, client: httpx.AsyncClient) -> None:
        assert await total(client, "?region=IN-TN") == 3

    async def test_the_country_rolls_up_its_states(self, client: httpx.AsyncClient) -> None:
        """Picking India on the region strip and seeing only the five
        national items would read as data loss."""
        assert await total(client, "?region=IN") == 8

    async def test_a_prefix_match_does_not_leak_across_countries(
        self, client: httpx.AsyncClient
    ) -> None:
        """ "IN" must not match "IND-..." if such a code ever exists. The
        roll-up is on "IN-", with the hyphen."""
        assert await total(client, "?region=I") == 0

    async def test_by_format(self, client: httpx.AsyncClient) -> None:
        """Formats are a JSONB array, so this is containment rather than
        equality — an item rendered square and portrait matches both."""
        assert await total(client, "?format=square") == 5
        assert await total(client, "?format=portrait") == 2
        assert await total(client, "?format=reel") == 2

    async def test_by_editorial_status(self, client: httpx.AsyncClient) -> None:
        assert await total(client, "?status=draft") == 8
        assert await total(client, "?status=posted") == 0

    async def test_by_date(self, client: httpx.AsyncClient) -> None:
        # quote, because an ISO offset ends in "+00:00" and a raw "+" in a
        # query string is a space. The web client builds these with
        # URLSearchParams, which encodes; anything hand-rolling a URL has to
        # remember, and the symptom is a 422 about "extra characters".
        cutoff = quote((utcnow() - timedelta(hours=24)).isoformat())

        assert await total(client, f"?created_from={cutoff}") == 3

    async def test_an_unencoded_offset_is_a_422_rather_than_a_wrong_answer(
        self, client: httpx.AsyncClient
    ) -> None:
        """Which is the right failure: a silently mis-parsed cutoff would
        quietly list the wrong fortnight."""
        raw = (utcnow() - timedelta(hours=24)).isoformat()

        assert (await client.get(f"/library?created_from={raw}")).status_code == 422

    async def test_by_topic_text(self, client: httpx.AsyncClient) -> None:
        assert await total(client, "?q=chennai") == 3
        assert await total(client, "?q=CHENNAI") == 3

    async def test_filters_combine(self, client: httpx.AsyncClient, seeded) -> None:
        query = f"?brand_id={seeded['brands']['coffee']}&region=IN-TN&kind=post"

        assert await total(client, query) == 1

    async def test_an_unknown_language_is_a_422_not_an_empty_page(
        self, client: httpx.AsyncClient
    ) -> None:
        """An empty page would read as "you have written nothing in
        Klingon", which is true and not what was asked."""
        assert (await client.get("/library?language=klingon")).status_code == 422


class TestPaging:
    async def test_total_counts_matches_not_the_page(self, client: httpx.AsyncClient) -> None:
        body = (await client.get("/library?limit=2")).json()

        assert len(body["items"]) == 2
        assert body["total"] == 8

    async def test_the_total_respects_the_filters(self, client: httpx.AsyncClient) -> None:
        """The count and the page share one WHERE, so "2 of 40" cannot be
        2 filtered items out of 40 unfiltered ones."""
        body = (await client.get("/library?kind=reel&limit=1")).json()

        assert body["total"] == 2

    async def test_paging_covers_everything_exactly_once(self, client: httpx.AsyncClient) -> None:
        """Four pages of three over eight rows, several of which were
        created inside the same microsecond. Ordering by created_at alone
        would repeat or drop one at a boundary."""
        seen: list[int] = []
        for offset in range(0, 9, 3):
            seen.extend(await ids(client, f"?limit=3&offset={offset}"))

        assert len(seen) == 8
        assert len(set(seen)) == 8

    async def test_a_limit_past_the_cap_is_refused(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/library?limit=5000")).status_code == 422


class TestFacets:
    async def test_brands_carry_their_counts(self, client: httpx.AsyncClient) -> None:
        facets = (await client.get("/library/facets")).json()

        assert [b["name"] for b in facets["brands"]] == ["Anna Tea", "Madras Filter Coffee"]
        assert [b["count"] for b in facets["brands"]] == [4, 4]

    async def test_only_regions_that_have_content(self, client: httpx.AsyncClient) -> None:
        facets = (await client.get("/library/facets")).json()

        assert sorted(r["code"] for r in facets["regions"]) == ["IN", "IN-GA", "IN-TN"]

    async def test_only_languages_that_were_used(self, client: httpx.AsyncClient) -> None:
        """Offering Bengali when nothing has been written in it is a dead
        end dressed as a choice."""
        facets = (await client.get("/library/facets")).json()

        assert facets["languages"] == ["english", "hindi", "tamil"]

    async def test_formats_are_flattened_out_of_the_arrays(self, client: httpx.AsyncClient) -> None:
        facets = (await client.get("/library/facets")).json()

        assert facets["formats"] == ["portrait", "reel", "square"]


class TestEditorialStatus:
    async def test_approving_leaves_the_pipeline_status_alone(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        job_id = seeded["jobs"][0]

        body = (
            await client.patch(f"/content/jobs/{job_id}", json={"editorial_status": "approved"})
        ).json()

        assert body["editorial_status"] == "approved"
        assert body["status"] == "ready"

    async def test_scheduling_without_a_time_is_refused(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        """A scheduled row with no time is invisible on the calendar, which
        looks exactly like work that was lost."""
        response = await client.patch(
            f"/content/jobs/{seeded['jobs'][0]}", json={"editorial_status": "scheduled"}
        )

        assert response.status_code == 422
        assert "needs a time" in response.json()["detail"]

    async def test_scheduling_with_a_time(self, client: httpx.AsyncClient, seeded) -> None:
        when = (utcnow() + timedelta(days=3)).isoformat()

        body = (
            await client.patch(
                f"/content/jobs/{seeded['jobs'][0]}",
                json={"editorial_status": "scheduled", "scheduled_at": when},
            )
        ).json()

        assert body["editorial_status"] == "scheduled"
        assert body["scheduled_at"] is not None

    async def test_a_drag_on_the_calendar_moves_the_time_alone(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        """Which is the whole of what dropping an item on another day
        means: still scheduled, different day."""
        job_id = seeded["jobs"][0]
        first = (utcnow() + timedelta(days=1)).isoformat()
        second = (utcnow() + timedelta(days=5)).isoformat()

        await client.patch(
            f"/content/jobs/{job_id}",
            json={"editorial_status": "scheduled", "scheduled_at": first},
        )
        body = (await client.patch(f"/content/jobs/{job_id}", json={"scheduled_at": second})).json()

        assert body["editorial_status"] == "scheduled"
        assert body["scheduled_at"][:10] == second[:10]

    async def test_going_back_to_draft_takes_it_off_the_calendar(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        """Keeping the time would leave the item on the calendar after the
        user took it off, which is the opposite of what they asked for."""
        job_id = seeded["jobs"][0]
        await client.patch(
            f"/content/jobs/{job_id}",
            json={
                "editorial_status": "scheduled",
                "scheduled_at": (utcnow() + timedelta(days=1)).isoformat(),
            },
        )

        body = (
            await client.patch(f"/content/jobs/{job_id}", json={"editorial_status": "draft"})
        ).json()

        assert body["editorial_status"] == "draft"
        assert body["scheduled_at"] is None

    async def test_an_empty_patch_is_refused(self, client: httpx.AsyncClient, seeded) -> None:
        response = await client.patch(f"/content/jobs/{seeded['jobs'][0]}", json={})

        assert response.status_code == 422

    async def test_an_unknown_job_is_a_404(self, client: httpx.AsyncClient) -> None:
        response = await client.patch("/content/jobs/99999", json={"editorial_status": "approved"})

        assert response.status_code == 404

    async def test_the_change_is_what_the_library_then_lists(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        await client.patch(
            f"/content/jobs/{seeded['jobs'][1]}", json={"editorial_status": "approved"}
        )

        assert await total(client, "?status=approved") == 1
        assert await total(client, "?status=draft") == 7

    async def test_it_is_persisted_rather_than_just_echoed(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        job_id = seeded["jobs"][2]
        await client.patch(f"/content/jobs/{job_id}", json={"editorial_status": "posted"})

        async with seeded["factory"]() as session:
            row = await session.scalar(select(ContentJob).where(ContentJob.id == job_id))

        assert row is not None
        assert row.editorial_status is EditorialStatus.posted


class TestCalendarWindow:
    """The same endpoint, asked a different question: what is scheduled, and
    when. The calendar needs a window and an order, not a page of newest
    work."""

    async def schedule(self, client: httpx.AsyncClient, job_id: int, when: str) -> None:
        response = await client.patch(
            f"/content/jobs/{job_id}",
            json={"editorial_status": "scheduled", "scheduled_at": when},
        )
        assert response.status_code == 200, response.text

    async def test_a_window_holds_only_what_falls_in_it(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        monday = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
        await self.schedule(client, seeded["jobs"][0], monday.isoformat())
        await self.schedule(client, seeded["jobs"][1], (monday + timedelta(days=9)).isoformat())

        window = (
            f"?scheduled_from={quote(monday.isoformat())}"
            f"&scheduled_to={quote((monday + timedelta(days=7)).isoformat())}"
        )

        assert await total(client, window) == 1

    async def test_the_window_is_half_open(self, client: httpx.AsyncClient, seeded) -> None:
        """Or a week and the week after it would both claim an item
        scheduled for exactly midnight on the boundary, and it would appear
        twice as you paged across."""
        boundary = datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
        await self.schedule(client, seeded["jobs"][0], boundary.isoformat())

        first = (
            f"?scheduled_from={quote((boundary - timedelta(days=7)).isoformat())}"
            f"&scheduled_to={quote(boundary.isoformat())}"
        )
        second = (
            f"?scheduled_from={quote(boundary.isoformat())}"
            f"&scheduled_to={quote((boundary + timedelta(days=7)).isoformat())}"
        )

        assert await total(client, first) == 0
        assert await total(client, second) == 1

    async def test_unscheduled_items_are_never_in_a_window(self, client: httpx.AsyncClient) -> None:
        """scheduled_at is null on a draft, and null compares false against
        every bound — which is the behaviour wanted, pinned because it is
        load-bearing rather than obvious."""
        window = (
            f"?scheduled_from={quote(datetime(2000, 1, 1, tzinfo=UTC).isoformat())}"
            f"&scheduled_to={quote(datetime(2099, 1, 1, tzinfo=UTC).isoformat())}"
        )

        assert await total(client, window) == 0

    async def test_scheduled_order_is_earliest_first(
        self, client: httpx.AsyncClient, seeded
    ) -> None:
        """A day column reads top to bottom in time. The library's newest
        first would run it backwards."""
        base = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
        await self.schedule(client, seeded["jobs"][0], (base + timedelta(days=2)).isoformat())
        await self.schedule(client, seeded["jobs"][1], base.isoformat())
        await self.schedule(client, seeded["jobs"][2], (base + timedelta(days=1)).isoformat())

        rows = (await client.get("/library?status=scheduled&order=scheduled")).json()["items"]

        assert [row["id"] for row in rows] == [
            seeded["jobs"][1],
            seeded["jobs"][2],
            seeded["jobs"][0],
        ]

    async def test_an_unknown_order_is_refused(self, client: httpx.AsyncClient) -> None:
        """Rather than silently falling back, which would sort a calendar
        by age and look like the drag did nothing."""
        assert (await client.get("/library?order=sideways")).status_code == 422
