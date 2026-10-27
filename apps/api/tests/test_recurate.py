"""Re-curation must update a topic, not fork it.

The curator writes the display title fresh every run, so the same story comes
back worded differently — "Rafale Marine trials underway in Goa" one cycle,
"Rafale Marine fighter begins flight trials in Goa" the next. Keying a topic on
that title spawned a second row, dropped the first to rank 0, and stranded the
content jobs hanging off it. These tests pin the matching that prevents it.
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
    Workspace,
)
from app.tasks.cluster import Cluster
from app.tasks.curate import (
    RawRow,
    _write,
    blend_centroid,
    cluster_member_keys,
    evidence_member_keys,
    find_matches,
    member_key,
)
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


def raw_row(
    title: str,
    rank: int = 1,
    url: str | None = "https://example.test/a",
    source: SourceName = SourceName.google_news,
) -> RawRow:
    return RawRow(
        source=source,
        # Nullable on purpose: these rows exist without a snapshot behind them.
        snapshot_id=None,
        rank=rank,
        title=title,
        url=url,
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


async def curate_once(
    session_factory,
    region: Region,
    title: str,
    centroid: list[float],
    rows: list[RawRow] | None = None,
) -> None:
    """One curate pass over a single cluster of source items."""
    rows = rows if rows is not None else [raw_row(SOURCE_HEADLINE)]
    clusters = [cluster_of(list(range(len(rows))), centroid)]
    async with session_factory() as session:
        await _write(
            session,
            region,
            run_id=f"run-{title[:8]}",
            rows=rows,
            clusters=clusters,
            keys=["c000"],
            described={"c000": fields_for(title)},
            vectors=[centroid] * len(rows),
        )
        await session.commit()


class TestRecurateKeepsContent:
    async def test_a_generated_post_survives_a_rename(self, session_factory, goa) -> None:
        """The regression this whole change exists for."""
        await curate_once(session_factory, goa, FIRST_TITLE, vector(0.25))

        async with session_factory() as session:
            trend = await session.scalar(select(Trend).where(Trend.region_id == goa.id))
            assert trend is not None
            trend_id, identity = trend.id, trend.cluster_id

            # merge, not add: the engine is module-scoped so this fixture
            # runs against a database that may already hold the row.
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

        # Its own URL: a different article is a different source item, and
        # sharing one would make these the same topic by rule 1.
        rows = [raw_row("Gold rate today", url="https://ex.test/gold")]
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
                rows=[raw_row("Gold rate today", url="https://ex.test/gold")],
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


def existing_row(
    topic_key: str,
    member_keys: list[str] | None = None,
    embedding: list[float] | None = None,
) -> Trend:
    """An unsaved Trend standing in for a row from an earlier run."""
    return Trend(
        region_id=1,
        topic=topic_key,
        topic_key=topic_key,
        member_keys=member_keys or [],
        embedding=embedding,
    )


class TestMemberKeys:
    """Identity is matched on source items, not on anything a model writes."""

    def test_a_url_names_the_item(self) -> None:
        key = member_key(raw_row("Rafale trials begin", url="https://wion.test/rafale"))

        assert key == "google_news:https://wion.test/rafale"

    def test_the_same_article_survives_a_reworded_headline(self) -> None:
        url = "https://wion.test/rafale"

        assert member_key(raw_row("Rafale trials begin", url=url)) == member_key(
            raw_row("Rafale Marine fighter begins flight trials", url=url)
        )

    def test_an_item_without_a_url_falls_back_to_its_normalised_title(self) -> None:
        trends = SourceName.google_trends
        first = member_key(raw_row("gold rate today", url=None, source=trends))
        second = member_key(raw_row("Gold Rate Today!", url=None, source=trends))

        assert first == second
        assert first.startswith("google_trends:h")

    def test_the_same_text_from_two_sources_is_two_items(self) -> None:
        trends = member_key(raw_row("gold rate", url=None, source=SourceName.google_trends))
        youtube = member_key(raw_row("gold rate", url=None, source=SourceName.youtube))

        assert trends != youtube

    def test_a_cluster_contributes_the_keys_of_its_members_only(self) -> None:
        rows = [
            raw_row("one", url="https://a.test/1"),
            raw_row("two", url="https://a.test/2"),
            raw_row("three", url="https://a.test/3"),
        ]

        keys = cluster_member_keys(cluster_of([0, 2], vector(0.1)), rows)

        assert keys == {"google_news:https://a.test/1", "google_news:https://a.test/3"}


class TestBlendCentroid:
    def test_the_first_observation_is_taken_whole(self) -> None:
        assert blend_centroid(None, [1.0, 0.0]) == [1.0, 0.0]

    def test_a_later_run_only_moves_it_part_way(self) -> None:
        blended = blend_centroid([0.0, 0.0], [1.0, 1.0], alpha=0.3)

        assert blended == [pytest.approx(0.3), pytest.approx(0.3)]

    def test_drift_accumulates_across_runs(self) -> None:
        vec: list[float] | None = [0.0]
        for _ in range(5):
            vec = blend_centroid(vec, [1.0], alpha=0.3)

        # Moving toward the story without ever snapping to one headline.
        assert vec is not None
        assert 0.5 < vec[0] < 1.0

    def test_a_missing_observation_leaves_it_alone(self) -> None:
        assert blend_centroid([0.5], None) == [0.5]


class TestFindMatches:
    THRESHOLD = settings.topic_match_similarity

    def find(self, rows: list[Trend], **kwargs: object) -> list:
        defaults: dict = {
            "keys": set(),
            "centroid": None,
            "topic_key": "a title nothing holds",
            "claimed": set(),
            "threshold": self.THRESHOLD,
            "has_content": set(),
        }
        defaults.update(kwargs)
        return find_matches(rows=rows, **defaults)

    def test_one_shared_article_is_enough(self) -> None:
        row = existing_row("old wording", ["google_news:https://a.test/1"])

        matches = self.find(
            [row],
            keys={"google_news:https://a.test/1", "google_news:https://a.test/2"},
        )

        assert [m.row for m in matches] == [row]
        assert matches[0].reason == "member_keys"
        assert matches[0].overlap == 1

    def test_the_largest_overlap_wins_and_the_rest_come_back_to_be_merged(self) -> None:
        weak = existing_row("fork one", ["google_news:https://a.test/1"])
        strong = existing_row(
            "fork two",
            ["google_news:https://a.test/1", "google_news:https://a.test/2"],
        )

        matches = self.find(
            [weak, strong],
            keys={"google_news:https://a.test/1", "google_news:https://a.test/2"},
        )

        assert matches[0].row is strong
        assert [m.row for m in matches[1:]] == [weak]

    def test_a_row_carrying_a_post_wins_an_otherwise_equal_match(self) -> None:
        plain = existing_row("plain", ["google_news:https://a.test/1"])
        posted = existing_row("posted", ["google_news:https://a.test/1"])

        matches = self.find(
            [plain, posted],
            keys={"google_news:https://a.test/1"},
            has_content={id(posted)},
        )

        assert matches[0].row is posted

    def test_the_centroid_carries_a_run_where_every_item_changed(self) -> None:
        row = existing_row("new wording", ["google_news:https://old.test/1"], vector(0.5))

        matches = self.find(
            [row],
            keys={"google_news:https://new.test/9"},
            centroid=vector(0.5),
        )

        assert matches[0].row is row
        assert matches[0].reason == "centroid"

    def test_only_one_row_comes_back_from_a_centroid_match(self) -> None:
        """Similarity is not proof, so it must never trigger a merge."""
        rows = [existing_row("a", None, vector(0.5)), existing_row("b", None, vector(0.5))]

        assert len(self.find(rows, centroid=vector(0.5))) == 1

    def test_a_centroid_from_the_no_llm_path_is_ignored(self) -> None:
        """One-hot title vectors are not comparable across runs."""
        row = existing_row("a", None, vector(0.5))

        assert self.find([row], centroid=[1.0, 0.0]) == []

    def test_title_is_the_last_resort(self) -> None:
        row = existing_row("same wording")

        matches = self.find(
            [row],
            keys={"google_news:https://a.test/1"},
            topic_key="same wording",
        )

        assert matches[0].reason == "title"

    def test_a_claimed_row_is_never_offered_twice(self) -> None:
        taken = existing_row("taken", ["google_news:https://a.test/1"])

        matches = self.find(
            [taken],
            keys={"google_news:https://a.test/1"},
            claimed={id(taken)},
        )

        assert matches == []

    def test_an_unrelated_topic_matches_nothing(self) -> None:
        other = existing_row("other", ["google_news:https://b.test/9"], axis(3))

        matches = self.find(
            [other],
            keys={"google_news:https://a.test/1"},
            centroid=axis(9),
        )

        assert matches == []


#: Six articles about one story, so a run can carry only part of it.
ARTICLES = [f"https://wion.test/rafale-{i}" for i in range(6)]


class TestChurnedMembership:
    """Three ingests where the source items turn over almost completely.

    This is the real failure mode. A story's coverage changes every cycle, so
    an identity pinned to one headline — or to one run's centroid — lets go of
    the topic and strands the post hanging off it.
    """

    def rows_for(self, urls: list[str], titles: list[str]) -> list[RawRow]:
        return [
            raw_row(title, rank=i + 1, url=url)
            for i, (url, title) in enumerate(zip(urls, titles, strict=True))
        ]

    async def attach_post(self, session_factory, trend_id: int, slug: str) -> int:
        """Give a topic a generated post, which is what identity protects."""
        async with session_factory() as session:
            # merge, not add: the engine is module-scoped so this fixture
            # runs against a database that may already hold the row.
            await session.merge(
                Workspace(id=Workspace.DEFAULT_ID, slug="default", name="Default workspace")
            )
            await session.flush()
            brand = Brand(
                workspace_id=Workspace.DEFAULT_ID, slug=slug, name="Demo", languages=["english"]
            )
            session.add(brand)
            await session.flush()
            job = ContentJob(
                workspace_id=Workspace.DEFAULT_ID,
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
            return job.id

    async def test_a_post_survives_three_runs_of_churn(self, session_factory, goa) -> None:
        # Run 1: two articles.
        await curate_once(
            session_factory,
            goa,
            "Rafale Marine trials under way in Goa",
            vector(0.25),
            rows=self.rows_for(ARTICLES[:2], ["Rafale trials begin", "Rafale in Goa"]),
        )

        async with session_factory() as session:
            trend = await session.scalar(select(Trend).where(Trend.region_id == goa.id))
            assert trend is not None
            trend_id, identity = trend.id, trend.cluster_id

        job_id = await self.attach_post(session_factory, trend_id, "churn")

        # Run 2: one article carries over, two are new, and the curator
        # rewords the title.
        await curate_once(
            session_factory,
            goa,
            "Rafale Marine fighter begins flight trials in Goa",
            vector(0.4),
            rows=self.rows_for(
                ARTICLES[1:4],
                ["Rafale in Goa", "Navy weighs carrier fit", "Trials ahead of induction"],
            ),
        )

        # Run 3: nothing from run 1 remains, and the title moves again.
        await curate_once(
            session_factory,
            goa,
            "Navy weighs carrier modifications for Rafale Marine",
            vector(0.55),
            rows=self.rows_for(
                ARTICLES[3:6],
                ["Trials ahead of induction", "Carrier fit under review", "Vikrant readiness"],
            ),
        )

        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )
            job = await session.get(ContentJob, job_id)

        # One row through three runs of churn, and the post still on it.
        assert len(trends) == 1, [t.topic_key for t in trends]
        assert trends[0].id == trend_id
        assert trends[0].cluster_id == identity
        assert trends[0].rank == 1
        assert trends[0].topic == "Navy weighs carrier modifications for Rafale Marine"

        assert job is not None
        assert job.trend_id == trend_id
        assert job.assets[0].meta_json["caption"] == "Trials have begun."

        # Every article the topic has ever carried, not just this run's three.
        assert set(trends[0].member_keys) == {f"google_news:{u}" for u in ARTICLES}

    async def test_the_centroid_follows_the_story(self, session_factory, goa) -> None:
        """Three runs of drift, none of which may snap identity to one run."""
        for title, seed in (("One", 0.2), ("Two", 0.5), ("Three", 0.8)):
            await curate_once(
                session_factory,
                goa,
                f"Rafale Marine trials {title}",
                vector(seed),
                rows=self.rows_for(ARTICLES[:1], ["Rafale trials begin"]),
            )

        async with session_factory() as session:
            trend = await session.scalar(select(Trend).where(Trend.region_id == goa.id))

        # 0.2 -> 0.29 -> 0.443 at alpha 0.3: moved toward the latest run
        # without arriving at it, and well clear of where it started.
        assert trend is not None
        assert trend.embedding is not None
        assert 0.2 < trend.embedding[0] < 0.8
        assert trend.embedding[0] == pytest.approx(0.443, abs=0.01)

    async def test_forks_from_earlier_runs_are_merged(self, session_factory, goa) -> None:
        """Rows that forked before member keys existed must be folded back in,
        taking their content with them rather than being deleted under it."""
        now = utcnow()
        async with session_factory() as session:
            keeper = Trend(
                region_id=goa.id,
                topic="Rafale Marine trials",
                topic_key="rafale marine trials",
                rank=1,
                score=80.0,
                velocity=[0.0, 0.0, 10.0, 20.0, 30.0, 40.0],
                member_keys=[f"google_news:{ARTICLES[0]}"],
                first_seen_at=now - timedelta(days=2),
                last_seen_at=now,
                curated_at=now,
            )
            fork = Trend(
                region_id=goa.id,
                topic="Rafale Marine fighter trials",
                topic_key="rafale marine fighter trials",
                rank=2,
                score=70.0,
                velocity=[0.0, 0.0, 0.0, 0.0, 0.0, 70.0],
                member_keys=[f"google_news:{u}" for u in ARTICLES[:2]],
                first_seen_at=now - timedelta(days=5),
                last_seen_at=now,
                curated_at=now,
            )
            session.add_all([keeper, fork])
            await session.commit()
            keeper_id, fork_id, born = keeper.id, fork.id, fork.first_seen_at

        # The post sits on the fork, which is the row with the larger overlap
        # and therefore the one that wins the match.
        job_id = await self.attach_post(session_factory, fork_id, "forked")

        await curate_once(
            session_factory,
            goa,
            "Rafale Marine fighter begins flight trials in Goa",
            vector(0.3),
            rows=self.rows_for(ARTICLES[:2], ["Rafale trials begin", "Rafale in Goa"]),
        )

        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )
            job = await session.get(ContentJob, job_id)
            absorbed = await session.get(Trend, keeper_id)

        assert len(trends) == 1, "the fork is folded into the winner, not left beside it"
        survivor = trends[0]
        assert survivor.id == fork_id
        assert absorbed is None
        assert job is not None
        assert job.trend_id == survivor.id

        # The union of both key sets, the earlier birthday, and whichever
        # velocity history is longer — here the one the absorbed row carried.
        assert len(survivor.member_keys) == 2
        assert survivor.first_seen_at == born
        assert len([v for v in survivor.velocity if v > 0]) >= 4

    async def test_a_merge_moves_the_post_off_the_row_it_deletes(
        self, session_factory, goa
    ) -> None:
        """The same merge with the post on the losing row: it has to move."""
        now = utcnow()
        async with session_factory() as session:
            winner = Trend(
                region_id=goa.id,
                topic="Rafale Marine trials",
                topic_key="rafale marine trials",
                rank=1,
                score=80.0,
                member_keys=[f"google_news:{u}" for u in ARTICLES[:2]],
                first_seen_at=now,
                last_seen_at=now,
                curated_at=now,
            )
            loser = Trend(
                region_id=goa.id,
                topic="Rafale trials in Goa",
                topic_key="rafale trials in goa",
                rank=2,
                score=70.0,
                member_keys=[f"google_news:{ARTICLES[1]}"],
                first_seen_at=now,
                last_seen_at=now,
                curated_at=now,
            )
            session.add_all([winner, loser])
            await session.commit()
            winner_id, loser_id = winner.id, loser.id

        job_id = await self.attach_post(session_factory, loser_id, "loser")

        await curate_once(
            session_factory,
            goa,
            "Rafale Marine fighter begins flight trials in Goa",
            vector(0.3),
            rows=self.rows_for(ARTICLES[:2], ["Rafale trials begin", "Rafale in Goa"]),
        )

        async with session_factory() as session:
            job = await session.get(ContentJob, job_id)
            gone = await session.get(Trend, loser_id)

        assert gone is None
        assert job is not None, "the post was deleted along with its row"
        assert job.trend_id == winner_id

    async def test_a_post_whose_story_vanishes_keeps_its_row(self, session_factory, goa) -> None:
        """No match for a row carrying a post is rank 0 and a warning, never a
        second row for the same topic."""
        await curate_once(
            session_factory,
            goa,
            "Rafale Marine trials",
            vector(0.25),
            rows=self.rows_for(ARTICLES[:1], ["Rafale trials begin"]),
        )

        async with session_factory() as session:
            trend = await session.scalar(select(Trend).where(Trend.region_id == goa.id))
            assert trend is not None
            trend_id = trend.id

        job_id = await self.attach_post(session_factory, trend_id, "vanished")

        # An entirely unrelated story, sharing no items and no direction.
        await curate_once(
            session_factory,
            goa,
            "Gold rate rises in Goa",
            axis(11),
            rows=self.rows_for(["https://ex.test/gold"], ["Gold rate today"]),
        )

        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )
            kept = await session.get(Trend, trend_id)
            job = await session.get(ContentJob, job_id)

        assert len(trends) == 2
        assert kept is not None
        assert kept.rank == 0, "off the board, but still there and still addressable"
        assert kept.topic_key == "rafale marine trials", "and not renamed to the new story"
        assert job is not None
        assert job.trend_id == trend_id

    async def test_a_winner_may_take_the_title_of_the_row_it_absorbs(
        self, session_factory, goa
    ) -> None:
        """A merge frees a title in the same breath as the winner claims it.

        This is the common case, not an edge one: two rows get merged exactly
        because they describe one story under near-identical titles, so the
        title the curator settles on is usually the one the absorbed row was
        already holding. (region, topic_key) is unique and deletes are ordered
        after updates within a flush, so the delete has to reach the database
        before the rename does.
        """
        title = "Zimbabwe vs Afghanistan second test"
        now = utcnow()
        async with session_factory() as session:
            winner = Trend(
                region_id=goa.id,
                topic="Zimbabwe tour of Afghanistan",
                topic_key="zimbabwe tour of afghanistan",
                rank=1,
                score=80.0,
                member_keys=[f"google_news:{u}" for u in ARTICLES[:2]],
                first_seen_at=now,
                last_seen_at=now,
                curated_at=now,
            )
            loser = Trend(
                region_id=goa.id,
                # Already holding the title this run settles on.
                topic=title,
                topic_key=normalise(title),
                rank=2,
                score=70.0,
                member_keys=[f"google_news:{ARTICLES[1]}"],
                first_seen_at=now,
                last_seen_at=now,
                curated_at=now,
            )
            session.add_all([winner, loser])
            await session.commit()
            winner_id, loser_id = winner.id, loser.id

        await curate_once(
            session_factory,
            goa,
            title,
            vector(0.3),
            rows=self.rows_for(ARTICLES[:2], ["Zimbabwe collapse", "Afghanistan seal series"]),
        )

        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )

        assert len(trends) == 1
        assert trends[0].id == winner_id
        assert trends[0].topic_key == normalise(title)
        assert trends[0].rank == 1
        assert loser_id not in {t.id for t in trends}


class TestEvidenceSeeding:
    """Rows written before the column existed still have to match.

    Every curated row records the items it was built from, so its keys can be
    derived from the row itself rather than backfilled by a migration. Without
    this the first run after the change matches on exact titles alone, which is
    long enough to fork every topic on the board.
    """

    def test_keys_are_derived_from_a_row_that_has_none(self) -> None:
        row = Trend(
            region_id=1,
            topic="Rafale Marine trials",
            topic_key="rafale marine trials",
            member_keys=[],
            evidence=[
                {"source": "google_news", "rank": 1, "title": "Trials begin", "url": "u1"},
                {"source": "google_trends", "rank": 2, "title": "Rafale Marine", "url": None},
            ],
        )

        keys = evidence_member_keys(row)

        assert "google_news:u1" in keys
        assert any(k.startswith("google_trends:h") for k in keys)

    def test_a_derived_key_equals_the_key_of_the_live_item(self) -> None:
        """Both sides of the match have to agree, or the seeding is noise."""
        live = raw_row("Rafale trials begin", url="https://wion.test/rafale")
        row = Trend(
            region_id=1,
            topic="x",
            topic_key="x",
            evidence=[
                {
                    "source": "google_news",
                    "rank": 1,
                    "title": "Rafale trials begin",
                    "url": "https://wion.test/rafale",
                }
            ],
        )

        assert evidence_member_keys(row) == {member_key(live)}

    def test_a_keyword_without_a_url_agrees_too(self) -> None:
        live = raw_row("Gold Rate Today", url=None, source=SourceName.google_trends)
        row = Trend(
            region_id=1,
            topic="x",
            topic_key="x",
            evidence=[{"source": "google_trends", "rank": 1, "title": "gold rate today"}],
        )

        assert evidence_member_keys(row) == {member_key(live)}

    def test_unusable_evidence_yields_nothing(self) -> None:
        row = Trend(
            region_id=1,
            topic="x",
            topic_key="x",
            evidence=[{"rank": 1, "title": "no source"}, {"source": "google_news", "title": " "}],
        )

        assert evidence_member_keys(row) == set()

    def test_an_empty_evidence_list_yields_nothing(self) -> None:
        assert evidence_member_keys(Trend(region_id=1, topic="x", topic_key="x")) == set()

    async def test_a_pre_existing_row_is_matched_on_its_evidence(
        self, session_factory, goa
    ) -> None:
        """The case this exists for: a row from before the change, carrying a
        post, reworded by the curator this run."""
        now = utcnow()
        url = f"https://wion.test/rafale-{0}"
        async with session_factory() as session:
            legacy = Trend(
                region_id=goa.id,
                topic="Rafale Marine trials",
                topic_key="rafale marine trials",
                rank=1,
                score=80.0,
                # No member_keys and no embedding, which is what every row on
                # the board looked like before this change.
                member_keys=[],
                evidence=[
                    {"source": "google_news", "rank": 1, "title": "Rafale trials begin", "url": url}
                ],
                first_seen_at=now,
                last_seen_at=now,
                curated_at=now,
            )
            session.add(legacy)
            await session.commit()
            legacy_id = legacy.id

        await curate_once(
            session_factory,
            goa,
            "Rafale Marine fighter begins flight trials in Goa",
            vector(0.3),
            rows=[raw_row("Rafale trials begin", url=url)],
        )

        async with session_factory() as session:
            trends = list(
                (await session.scalars(select(Trend).where(Trend.region_id == goa.id))).all()
            )

        assert len(trends) == 1, "matched on its own evidence rather than forked"
        assert trends[0].id == legacy_id
        assert trends[0].rank == 1
        assert trends[0].member_keys == [f"google_news:{url}"]
