"""The daily budget, and what /health is told about it.

The behaviour worth pinning is that the count is *shared*. Two processes hold
their own DailyBudget objects — the worker spends, the api reports — and the
number has to be the same one. While it was not, /health answered with the
api's untouched allowance and reported a full day at midnight and a full day
at dusk.
"""

from __future__ import annotations

import pytest

from app.core.budget import DailyBudget
from app.core.config import settings
from app.llm import GeminiProvider, GroqProvider, SpilloverProvider
from tests.conftest import FakeRedis


@pytest.fixture
def redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(settings, "redis_url", "redis://fake:6379/0")
    monkeypatch.setattr("app.core.budget._client", lambda: fake.client())
    return fake


class TestDailyBudget:
    async def test_it_spends_down_to_zero_and_stops(self, redis: FakeRedis) -> None:
        budget = DailyBudget(2, name="gemini-rpd")

        assert await budget.spend("flash") is True
        assert await budget.spend("flash") is True
        assert await budget.spend("flash") is False
        assert await budget.remaining("flash") == 0

    async def test_two_processes_share_one_count(self, redis: FakeRedis) -> None:
        """The whole point. `worker` spends, `api` reports, and the api was
        never going to learn the number any other way."""
        worker = DailyBudget(5, name="gemini-rpd")
        api = DailyBudget(5, name="gemini-rpd")

        for _ in range(3):
            await worker.spend("flash")

        assert await api.remaining("flash") == 2

    async def test_a_refused_call_is_not_counted_as_spent(self, redis: FakeRedis) -> None:
        """A blocked call costs nothing, so the stored count must come back
        down. Otherwise the number /health renders drifts past the limit and
        reads as a bookkeeping bug."""
        budget = DailyBudget(1, name="gemini-rpd")

        await budget.spend("flash")
        for _ in range(4):
            assert await budget.spend("flash") is False

        key = next(iter(redis.store))
        assert redis.store[key] == 1
        assert await budget.remaining("flash") == 0

    async def test_each_model_carries_its_own_day(self, redis: FakeRedis) -> None:
        """Google counts the free tier per model id, which is why the chain is
        long: an exhausted model is not an exhausted key."""
        budget = DailyBudget(1, name="gemini-rpd")

        assert await budget.spend("flash") is True
        assert await budget.spend("flash") is False
        assert await budget.spend("flash-lite") is True

    async def test_the_key_is_scoped_by_provider_model_and_day(self, redis: FakeRedis) -> None:
        await DailyBudget(3, name="gemini-rpd").spend("flash")

        key = next(iter(redis.store))
        assert key.startswith("llm:rpd:gemini-rpd:flash:")
        assert redis.expires[key] == DailyBudget.TTL_SECONDS

    async def test_a_dead_redis_counts_locally_rather_than_refusing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Losing the bookkeeper risks spending a budget twice. Refusing to
        generate guarantees spending none of it, which is worse."""
        fake = FakeRedis(fail=True)
        monkeypatch.setattr(settings, "redis_url", "redis://fake:6379/0")
        monkeypatch.setattr("app.core.budget._client", lambda: fake.client())
        budget = DailyBudget(2, name="gemini-rpd")

        assert await budget.spend("flash") is True
        assert await budget.spend("flash") is True
        assert await budget.spend("flash") is False

    async def test_no_url_configured_counts_locally(self) -> None:
        """The autouse fixture blanks the url, so this is the suite's default."""
        budget = DailyBudget(1, name="gemini-rpd")

        assert await budget.spend() is True
        assert await budget.spend() is False
        assert await budget.remaining() == 0


class TestProviderStatuses:
    async def test_gemini_reports_every_model_and_the_sum(self, redis: FakeRedis) -> None:
        """A call walks the chain, so the budget that matters is the ladder's
        total — eight models at twenty a day is not twenty."""
        provider = GeminiProvider(api_key="k")
        chain = settings.gemini_model_chain

        status = await provider.budget()

        assert status.name == "gemini"
        assert status.configured is True
        assert set(status.per_model) == set(chain)
        assert status.remaining_today == settings.gemini_rpd * len(chain)

    async def test_gemini_spends_show_up_in_its_budget(self, redis: FakeRedis) -> None:
        provider = GeminiProvider(api_key="k")
        primary = settings.gemini_model_chain[0]
        full = await provider.budget()

        await provider._daily.spend(primary)
        after = await provider.budget()

        assert after.per_model[primary] == full.per_model[primary] - 1
        assert after.remaining_today == full.remaining_today - 1

    async def test_an_unconfigured_provider_says_so_without_a_key(self) -> None:
        status = await GeminiProvider(api_key="").budget()

        assert status.configured is False

    async def test_groq_reports_no_daily_figure_rather_than_a_wrong_one(self) -> None:
        """Groq meters tokens per day as well as requests and nothing here
        counts tokens. Null says "not counted"; zero would say "spent"."""
        status = await GroqProvider(api_key="k").budget()

        assert status.name == "groq"
        assert status.configured is True
        assert status.remaining_today is None

    async def test_the_chain_reports_both_vendors_primary_first(self) -> None:
        chain = SpilloverProvider(GeminiProvider(api_key="k"), GroqProvider(api_key="k"))

        statuses = await chain.statuses()

        assert [s.name for s in statuses] == ["gemini", "groq"]

    async def test_the_chain_reports_a_standby_that_is_not_wired_up(self) -> None:
        chain = SpilloverProvider(GeminiProvider(api_key="k"), GroqProvider(api_key=""))

        statuses = await chain.statuses()

        assert [(s.name, s.configured) for s in statuses] == [("gemini", True), ("groq", False)]
