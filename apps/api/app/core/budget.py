"""Shared spend counters: a hard daily cap, and a "not again yet" claim.

In `app.core` rather than beside the LLM limiter that first needed it,
because `app.sources.x` needs the same two things and an adapter importing
from `app.llm` is the layering mistake that already produced one circular
import in this codebase.

Both are backed by Redis for the same reason: the process that spends is not
the process asked about it. The worker calls the APIs; /health is served by
the api.
"""

from __future__ import annotations

import time

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("core.budget")


class DailyBudget:
    """A hard daily count, shared across processes. Does not refill in-day.

    One Redis key per provider, model and day, INCR'd on spend. A refused call
    decrements again, so the stored count is what was actually spent rather
    than what was attempted — the api renders this number, and a budget that
    reads as overspent because something was *blocked* would be read as a bug.

    If Redis cannot be reached the count falls back to a process-local one.
    Degrading to local counting risks spending a budget twice over; refusing
    to generate because the bookkeeper is down guarantees spending none of it.
    """

    #: Long enough that a key outlives its own day in any timezone, short
    #: enough that yesterday's counts do not accumulate.
    TTL_SECONDS = 48 * 3600

    def __init__(self, limit: int, *, name: str) -> None:
        self._limit = max(1, limit)
        self._name = name
        self._local = _LocalDay()
        self._warned = False

    @property
    def limit(self) -> int:
        return self._limit

    def _key(self, model: str) -> str:
        return f"llm:rpd:{self._name}:{model or '-'}:{_utc_day()}"

    async def spend(self, key: str = "") -> bool:
        """True if there was budget left for `key`. False means stop, not retry.

        Counted per model, because Google's limit is per model too
        (GenerateRequestsPerDayPerProjectPerModel-FreeTier, 20/day on this
        tier). A single shared counter would block a model that still has
        budget, which is exactly what the fallback chain exists to use.
        """
        client = _client()
        if client is None:
            return self._local.spend(key, self._limit)

        redis_key = self._key(key)
        try:
            async with client:
                used = await client.incr(redis_key)
                await client.expire(redis_key, self.TTL_SECONDS)
                if used > self._limit:
                    # Put it back: this call is not happening, so it did not
                    # cost anything and must not read as though it had.
                    await client.decr(redis_key)
                    return False
                return True
        except RedisError as exc:
            self._degrade(exc)
            return self._local.spend(key, self._limit)

    async def remaining(self, key: str = "") -> int:
        client = _client()
        if client is None:
            return max(0, self._limit - self._local.used(key))
        try:
            async with client:
                used = await client.get(self._key(key))
        except RedisError as exc:
            self._degrade(exc)
            return max(0, self._limit - self._local.used(key))
        return max(0, self._limit - int(used or 0))

    def _degrade(self, exc: Exception) -> None:
        # Once per process. This fires on every model in the chain otherwise,
        # and the second line tells you nothing the first did not.
        if not self._warned:
            self._warned = True
            log.warning(
                "daily budget is counting locally: redis is unreachable",
                bucket=self._name,
                error=str(exc)[:120],
            )


def _utc_day() -> str:
    """The day the budget belongs to.

    UTC, which is what the process-local version counted and so keeps the
    rollover where it was. It is not where Google resets a free-tier day, so
    the count can disagree with theirs for a few hours — the local budget is
    deliberately the stricter of the two, and a 429 is still handled.
    """
    return time.strftime("%Y%m%d", time.gmtime())


def _client() -> aioredis.Redis | None:
    """A Redis client for one piece of work, or None if there is no url.

    Built per call and closed by the caller's `async with`, rather than
    cached. Every Celery task runs in its own `asyncio.run()` loop, and a
    cached asyncio client holds connections bound to the loop that made them:
    reuse across tasks fails with "Event loop is closed" on the second task.
    A connection setup is nothing next to the ten-second model call it is
    accounting for.
    """
    if not settings.redis_url:
        return None
    try:
        return aioredis.from_url(settings.redis_url, decode_responses=True)
    except (RedisError, ValueError):
        return None


class _LocalDay:
    """Process-local counts. Only reached when Redis is unavailable."""

    def __init__(self) -> None:
        self._day = _utc_day()
        self._used: dict[str, int] = {}

    def _roll(self) -> None:
        today = _utc_day()
        if today != self._day:
            self._day, self._used = today, {}

    def spend(self, key: str, limit: int) -> bool:
        self._roll()
        used = self._used.get(key, 0)
        if used >= limit:
            return False
        self._used[key] = used + 1
        return True

    def used(self, key: str) -> int:
        self._roll()
        return self._used.get(key, 0)


async def claim_interval(key: str, seconds: int) -> bool:
    """True if `key` has not been claimed within the last `seconds`.

    A SET NX EX, so the claim and its expiry are one atomic operation — two
    workers starting a cycle together cannot both decide they are first.

    Used to stop a pay-per-request source being pulled on every beat: the
    ingest schedule is 30 minutes and X is billed per call, so without this a
    region would cost 48 requests a day instead of 12.

    With no Redis this returns True, which is the right way round: the cap in
    DailyBudget is the hard limit, and this is an optimisation on top of it.
    A failure here costs extra requests; a failure that returned False would
    stop ingesting entirely.
    """
    client = _client()
    if client is None:
        return True
    try:
        async with client:
            claimed = await client.set(key, "1", ex=max(1, seconds), nx=True)
    except RedisError as exc:
        log.warning("interval claim unavailable", key=key, error=str(exc)[:120])
        return True
    return bool(claimed)
