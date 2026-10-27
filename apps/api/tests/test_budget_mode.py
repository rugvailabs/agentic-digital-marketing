"""Dev budget mode: one curate a day, big batches, and calls kept for the Desk.

The free tier is 20 Gemini calls per model per day. Everything here exists
because that number is small enough that the scheduled work and the user
compete for it, and without arrangement the schedule wins by running first.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.budget import DailyBudget
from app.core.config import Settings, settings
from app.llm.priority import background, is_background
from app.models import SourceName
from app.tasks.celery_app import celery_app
from app.tasks.curate import RawRow, cluster_member_keys, split_by_evidence


class TestSchedule:
    def test_curate_runs_once_a_day_just_after_the_reset(self) -> None:
        """12:45 IST, because the tier resets at midnight Pacific — 12:30 —
        and running before that spends whatever yesterday left."""
        entry = celery_app.conf.beat_schedule["curate-daily"]

        assert entry["task"] == "app.tasks.curate.curate_daily"
        assert entry["schedule"].hour == {settings.curate_hour_ist}
        assert entry["schedule"].minute == {settings.curate_minute_ist}

    def test_the_schedule_is_read_in_ist(self) -> None:
        """A crontab is interpreted in the app's timezone, so 12:45 only
        means 12:45 IST because of this."""
        assert celery_app.conf.timezone == "Asia/Kolkata"

    def test_the_board_covers_a_state_as_well_as_the_country(self) -> None:
        """relevance_to_region only does anything on a state board, so IN
        alone would never exercise the one field that filters."""
        default = str(Settings.model_fields["curate_regions"].default)
        regions = [c.strip() for c in default.split(",") if c.strip()]

        assert regions[0] == "IN"
        assert any(code.startswith("IN-") for code in regions)

    def test_ingest_no_longer_dispatches_a_curate(self) -> None:
        """It used to run after every cycle: 48 attempts a day against an
        allowance of 20, so the budget was gone by mid-morning and every
        later run re-described the board from source titles."""
        import inspect

        from app.tasks import ingest

        source = inspect.getsource(ingest.ingest_all_regions)

        assert "curate_regions.delay" not in source


class TestDeskReserve:
    """Scheduled work stops short so a user clicking Generate is not
    starved by the 12:45 run."""

    async def test_background_work_stops_short_of_the_limit(self, fake_redis) -> None:
        budget = DailyBudget(10, name="gemini-rpd")

        spends = [await budget.spend("flash", reserve=3) for _ in range(10)]

        assert spends.count(True) == 7

    async def test_the_desk_may_spend_what_was_reserved(self, fake_redis) -> None:
        """The reserve is a floor for the scheduler, not a hole in the
        budget — the remaining calls are for someone, and this is who."""
        budget = DailyBudget(10, name="gemini-rpd")
        for _ in range(7):
            await budget.spend("flash", reserve=3)

        assert await budget.spend("flash") is True
        assert await budget.spend("flash") is True
        assert await budget.spend("flash") is True
        assert await budget.spend("flash") is False

    async def test_a_reserve_larger_than_the_limit_still_allows_one(self, fake_redis) -> None:
        """Misconfiguration should throttle, not deadlock."""
        budget = DailyBudget(2, name="gemini-rpd")

        assert await budget.spend("flash", reserve=99) is True

    async def test_no_reserve_is_the_default(self, fake_redis) -> None:
        budget = DailyBudget(3, name="gemini-rpd")

        assert [await budget.spend("flash") for _ in range(4)] == [True, True, True, False]


class TestPriority:
    """Which caller is background, carried by a context variable rather than
    an argument on generate_json — the task knows, the provider needs to
    know, and nothing between them should have to."""

    def test_the_desk_is_the_default(self) -> None:
        assert is_background() is False

    def test_inside_the_marker_is_background(self) -> None:
        with background():
            assert is_background() is True

    def test_it_is_restored_afterwards(self) -> None:
        with background():
            pass

        assert is_background() is False

    def test_it_is_restored_after_an_error(self) -> None:
        with pytest.raises(ValueError), background():
            raise ValueError("boom")

        assert is_background() is False

    async def test_it_survives_an_await(self) -> None:
        """Everything the task awaits is inside its context, which is the
        whole reason for contextvars rather than a thread local."""
        import asyncio

        async def inner() -> bool:
            await asyncio.sleep(0)
            return is_background()

        with background():
            assert await inner() is True


class TestBatchSizing:
    """Asserted on the class defaults, not on the loaded settings: a local
    .env may tune these, and a test that failed because someone lowered a
    batch size on their machine would be noise."""

    def test_the_batch_is_sized_to_the_output_ceiling(self) -> None:
        """Measured on the real board: ~126 output tokens per described
        cluster, so 40 is ~5,060 against Gemini flash's 8,192."""
        assert Settings.model_fields["curate_batch_size"].default == 40

    def test_there_is_a_floor_to_split_down_to(self) -> None:
        """Below it a retry costs about as much as it recovers."""
        floor = Settings.model_fields["curate_min_batch_size"].default
        assert 1 <= floor < Settings.model_fields["curate_batch_size"].default

    def test_calls_are_held_back_for_the_desk(self) -> None:
        assert Settings.model_fields["gemini_desk_reserve"].default == 5


class TestUnchangedTopics:
    """A cluster whose evidence has not moved does not need describing
    again — on a board where topics persist for days this is most of the
    daily cost."""

    def rows(self, titles: list[str]) -> list[RawRow]:
        return [
            RawRow(
                source=SourceName.google_news,
                snapshot_id=1,
                rank=i + 1,
                title=title,
                url=f"https://news/{i}",
                volume=None,
                extra={},
            )
            for i, title in enumerate(titles)
        ]

    def cluster(self, key: str, members: list[int]) -> SimpleNamespace:
        return SimpleNamespace(key=key, members=members)

    def test_everything_is_fresh_when_nothing_was_described(self) -> None:
        rows = self.rows(["A", "B"])
        clusters = [self.cluster("c0", [0]), self.cluster("c1", [1])]

        fresh, unchanged = split_by_evidence(clusters, rows, set())

        assert len(fresh) == 2
        assert unchanged == []

    def test_an_identical_cluster_is_skipped(self) -> None:
        rows = self.rows(["A", "B"])
        clusters = [self.cluster("c0", [0]), self.cluster("c1", [1])]
        seen = {frozenset(cluster_member_keys(clusters[0], rows))}

        fresh, unchanged = split_by_evidence(clusters, rows, seen)

        assert [c.key for c in unchanged] == ["c0"]
        assert [c.key for c in fresh] == ["c1"]

    def test_one_new_article_makes_it_fresh_again(self) -> None:
        """Exact match, not overlap. Overlap is how topic identity is
        matched further down — a story that gained an article is the same
        story — but it is a different question: the new article can change
        what the story is about, and the summary should follow it."""
        rows = self.rows(["A", "B"])
        before = {frozenset(cluster_member_keys(self.cluster("c0", [0]), rows))}
        grown = self.cluster("c0", [0, 1])

        fresh, unchanged = split_by_evidence([grown], rows, before)

        assert [c.key for c in fresh] == ["c0"]
        assert unchanged == []

    def test_order_within_a_cluster_does_not_matter(self) -> None:
        """Sources arrive in whatever order the ingest returned them."""
        rows = self.rows(["A", "B"])
        seen = {frozenset(cluster_member_keys(self.cluster("c0", [0, 1]), rows))}

        fresh, unchanged = split_by_evidence([self.cluster("c0", [1, 0])], rows, seen)

        assert [c.key for c in unchanged] == ["c0"]
        assert fresh == []
