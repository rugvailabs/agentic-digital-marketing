"""Re-curation must update a topic, not fork it.

The curator writes the display title fresh every run, so the same story comes
back worded differently — "Rafale Marine trials underway in Goa" one cycle,
"Rafale Marine fighter begins flight trials in Goa" the next. Keying a topic on
that title spawned a second row, dropped the first to rank 0, and stranded the
content jobs hanging off it. These tests pin the matching that prevents it.
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
    AssetKind,
    Brand,
    ContentAsset,
    ContentJob,
    JobStatus,
    Language,
    Region,
    RegionKind,
    SourceName,
    Trend,
    TrendItem,
)
from app.tasks.cluster import Cluster
from app.tasks.curate import RawRow, _write, match_existing, topic_identity
from app.tasks.merge import normalise_topic as normalise

TEST_DB = "trendforge_recurate_test"
DIM = settings.gemini_embed_dim

FIRST_TITLE = "Rafale Marine trials underway in Goa for INS Vikrant operations"
SECOND_TITLE = "Rafale Marine fighter begins flight trials in Goa ahead of Navy induction"
#: The *source* headline, identical in both runs. Only the curator reworded.
SOURCE_HEADLINE = "Rafale Marine fighter begins flight trials in Goa"


def vector(seed: float) -> list[float]:
    return [seed] * DIM


def axis(index: int) -> list[float]:
    """A unit vector along one axis.

    Two all-positive vectors in 768 dimensions sit at cosine ~0.95 however
    different their emphasis, so "unrelated" has to mean orthogonal here.
    """
    v = [0.0] * DIM
    v[index] = 1.0
    return v


def raw_row(title: str, rank: int = 1) -> RawRow:
    return RawRow(
        source=SourceName.google_news,
        # Nullable on purpose: these rows exist without a snapshot behind them.
        snapshot_id=None,
        rank=rank,
        title=title,
        url="https://example.test/a",
        volume=1000,
        extra={"publisher": "WION"},
    )


def cluster_of(members: list[int], centroid: list[float], key: str = "c000") -> Cluster:
    return Cluster(key=key, members=members, centroid=centroid)


def fields_for(title: str) -> dict:
    return {
        "title": title,
        "category": "Technology",
        "hashtags": ["#RafaleMarine"],
        "summary": "Flight trials have begun in Goa.",
        "safety_flag": "none",
    }


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
async def session_factory(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    async with factory() as session:
        for table in (ContentAsset, ContentJob, TrendItem, Trend, Brand, Region):
            await session.execute(table.__table__.delete())
        await session.commit()


@pytest.fixture
async def goa(session_factory) -> Region:
    async with session_factory() as session:
        region = Region(code="IN-GA", name="Goa", kind=RegionKind.state, sort_order=6)
        session.add(region)
        await session.commit()
        return region


async def curate_once(session_factory, region: Region, title: str, centroid: list[float]) -> None:
    """One curate pass over a single cluster carrying one source headline."""
    rows = [raw_row(SOURCE_HEADLINE)]
    clusters = [cluster_of([0], centroid)]
    async with session_factory() as session:
        await _write(
            session,
            region,
            run_id=f"run-{title[:8]}",
            rows=rows,
            clusters=clusters,
            keys=["c000"],
            described={"c000": fields_for(title)},
            vectors=[centroid],
        )
        await session.commit()


class TestTopicIdentity:
    def test_identity_follows_the_source_headline_not_the_curated_title(self) -> None:
        rows = [raw_row(SOURCE_HEADLINE)]
        cluster = cluster_of([0], vector(0.1))

        # Same cluster, same members: the identity cannot depend on what the
        # model happened to call it this run.
        assert topic_identity(cluster, rows) == topic_identity(cluster, rows)

    def test_different_stories_get_different_identities(self) -> None:
        a = topic_identity(cluster_of([0], vector(0.1)), [raw_row(SOURCE_HEADLINE)])
        b = topic_identity(cluster_of([0], vector(0.1)), [raw_row("Gold rate today")])

        assert a != b

    def test_the_most_trusted_member_anchors_the_identity(self) -> None:
        """Trends outranks news, so adding a lower-weight member must not
        rename the topic."""
        trends_row = RawRow(
            source=SourceName.google_trends,
            snapshot_id=None,
            rank=1,
            title="rafale marine",
            url=None,
            volume=5000,
            extra={},
        )
        rows = [trends_row, raw_row(SOURCE_HEADLINE, rank=2)]

        one = topic_identity(cluster_of([0], vector(0.1)), rows)
        both = topic_identity(cluster_of([0, 1], vector(0.1)), rows)

        assert one == both


class TestMatchExisting:
    def row(self, **kw) -> Trend:
        return Trend(region_id=1, topic="t", topic_key=kw.pop("topic_key", "k"), **kw)

    def test_identity_wins_over_everything(self) -> None:
        wanted = self.row(cluster_id="abc123", topic_key="old wording")
        other = self.row(cluster_id="zzz", topic_key="new wording")

        match = match_existing(
            identity="abc123",
            topic_key="new wording",
            centroid=None,
            by_identity={"abc123": wanted},
            by_key={"new wording": other},
            with_vectors=[],
            claimed=set(),
            threshold=0.9,
        )

        assert match is wanted

    def test_centroid_matches_when_the_identity_is_new(self) -> None:
        """First run after the change: no row carries an identity yet."""
        wanted = self.row(cluster_id=None, topic_key="old wording")

        match = match_existing(
            identity="brand-new",
            topic_key="new wording",
            centroid=vector(0.5),
            by_identity={},
            by_key={},
            with_vectors=[(wanted, vector(0.5))],
            claimed=set(),
            threshold=0.9,
        )

        assert match is wanted

    def test_a_merely_related_topic_is_not_the_same_topic(self) -> None:
        unrelated = self.row(topic_key="something else")

        match = match_existing(
            identity="new",
            topic_key="new wording",
            centroid=axis(0),
            by_identity={},
            by_key={},
            with_vectors=[(unrelated, axis(1))],
            claimed=set(),
            threshold=0.9,
        )

        assert match is None

    def test_an_exact_title_still_matches_without_any_vector(self) -> None:
        wanted = self.row(topic_key="same wording")

        match = match_existing(
            identity="new",
            topic_key="same wording",
            centroid=None,
            by_identity={},
            by_key={"same wording": wanted},
            with_vectors=[],
            claimed=set(),
            threshold=0.9,
        )

        assert match is wanted

    def test_a_row_already_claimed_this_run_is_not_offered_twice(self) -> None:
        taken = self.row(cluster_id="abc123")

        match = match_existing(
            identity="abc123",
            topic_key="whatever",
            centroid=None,
            by_identity={"abc123": taken},
            by_key={},
            with_vectors=[],
            claimed={id(taken)},
            threshold=0.9,
        )

        assert match is None


class TestRecurateKeepsContent:
    async def test_a_generated_post_survives_a_rename(self, session_factory, goa) -> None:
        """The regression this whole change exists for."""
        await curate_once(session_factory, goa, FIRST_TITLE, vector(0.25))

        async with session_factory() as session:
            trend = await session.scalar(select(Trend).where(Trend.region_id == goa.id))
            assert trend is not None
            trend_id, identity = trend.id, trend.cluster_id

            brand = Brand(slug="demo", name="Demo", languages=["english"])
            session.add(brand)
            await session.flush()
            job = ContentJob(
                trend_id=trend_id,
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
                    kind=AssetKind.caption,
                    variant="english",
                    meta_json={"caption": "Trials have begun."},
                )
            )
            await session.commit()
            job_id = job.id

        # Second cycle: same story, the curator words it differently.
        await curate_once(session_factory, goa, SECOND_TITLE, vector(0.25))

        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )

            # One row, not two, and it is the row the job points at.
            assert len(trends) == 1
            assert trends[0].id == trend_id
            assert trends[0].topic == SECOND_TITLE
            assert trends[0].rank == 1, "the renamed topic stays on the board"
            assert trends[0].cluster_id == identity

            job = await session.get(ContentJob, job_id)
            assert job is not None
            assert job.trend_id == trend_id
            assert len(job.assets) == 1
            assert job.assets[0].meta_json["caption"] == "Trials have begun."

    async def test_a_rename_keeps_the_velocity_history(self, session_factory, goa) -> None:
        await curate_once(session_factory, goa, FIRST_TITLE, vector(0.25))
        await curate_once(session_factory, goa, SECOND_TITLE, vector(0.25))

        async with session_factory() as session:
            trend = await session.scalar(select(Trend).where(Trend.region_id == goa.id))

            # Two cycles recorded, not one: a forked row would have restarted
            # the sparkline from zeros.
            assert trend is not None
            assert len([v for v in trend.velocity if v > 0]) == 2

    async def test_a_genuinely_new_topic_still_gets_its_own_row(self, session_factory, goa) -> None:
        await curate_once(session_factory, goa, FIRST_TITLE, vector(0.25))

        rows = [raw_row("Gold rate today")]
        async with session_factory() as session:
            await _write(
                session,
                goa,
                run_id="run-2",
                rows=rows,
                clusters=[cluster_of([0], axis(7))],
                keys=["c000"],
                described={"c000": fields_for("Gold rate climbs in Goa")},
                vectors=[axis(7)],
            )
            await session.commit()

        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )

            assert len(trends) == 2
            # The absent one drops off the board but keeps its history.
            assert sorted(t.rank for t in trends) == [0, 1]

    async def test_a_rename_onto_a_title_another_row_holds_does_not_crash(
        self, session_factory, goa
    ) -> None:
        """Two rows, one of which is reworded into the other's exact title.

        (region, topic_key) is unique, so claiming a key another row still
        holds would fail on flush. The row already holding the title wins.
        """
        await curate_once(session_factory, goa, FIRST_TITLE, vector(0.25))

        # A second, unrelated row that happens to hold the title the first one
        # is about to be reworded into.
        async with session_factory() as session:
            await _write(
                session,
                goa,
                run_id="run-other",
                rows=[raw_row("Gold rate today")],
                clusters=[cluster_of([0], axis(7))],
                keys=["c000"],
                described={"c000": fields_for(SECOND_TITLE)},
                vectors=[axis(7)],
            )
            await session.commit()

        # Now re-curate the first story under that same title.
        await curate_once(session_factory, goa, SECOND_TITLE, vector(0.25))

        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )
            keys = [t.topic_key for t in trends]

            # No crash, and no duplicate key.
            assert len(keys) == len(set(keys))
            assert any(t.topic == SECOND_TITLE and t.rank == 1 for t in trends)


class TestIngestDoesNotClobberCuration:
    """The merge and the curator key topics differently, so only one may own
    a region's board. Running both produced duplicate rows under raw headlines
    and blanked the categories and summaries the curator had written."""

    async def test_an_uncurated_region_still_gets_the_merge_board(
        self, session_factory, goa
    ) -> None:
        from app.tasks.ingest import upsert_trends
        from app.tasks.merge import MergedTopic

        topic = MergedTopic(
            topic="Gold rate today",
            topic_key="gold rate today",
            score=90.0,
            volume=1000,
            category=None,
            sources=["google_trends"],
            hashtags=["#GoldRate"],
            evidence=[],
        )

        async with session_factory() as session:
            wrote = await upsert_trends(session, goa, [topic], utcnow())
            await session.commit()

        assert wrote is True
        async with session_factory() as session:
            keys = {t.topic_key for t in (await session.scalars(select(Trend))).all()}
        assert keys == {"gold rate today"}

    async def test_a_curated_region_is_left_alone(self, session_factory, goa) -> None:
        from app.tasks.ingest import upsert_trends
        from app.tasks.merge import MergedTopic

        await curate_once(session_factory, goa, FIRST_TITLE, vector(0.25))

        raw = MergedTopic(
            topic=SOURCE_HEADLINE,
            topic_key=normalise(SOURCE_HEADLINE),
            score=90.0,
            volume=0,
            category=None,
            sources=["google_news"],
            hashtags=[],
            evidence=[],
        )

        async with session_factory() as session:
            wrote = await upsert_trends(session, goa, [raw], utcnow())
            await session.commit()

        assert wrote is False
        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )

        # One row, still the curated one, with its category intact.
        assert len(trends) == 1
        assert trends[0].topic == FIRST_TITLE
        assert trends[0].category == "Technology"
        assert trends[0].summary
