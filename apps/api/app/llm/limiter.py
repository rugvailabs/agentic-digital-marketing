"""Token-bucket rate limiting for the free tier.

Two buckets per provider: requests per minute, which refills continuously, and
requests per day, which does not. The point is to wait locally rather than
spend the budget discovering a 429 — a rejected call still costs a round trip
and, on some tiers, still counts.

The per-minute bucket is in-process, which is the right scope for it: it
smooths one process's own bursts, and there is one worker.

The daily budget is in Redis, which it has to be, because the process that
spends it is not the process asked about it. Only the worker calls a model;
/health is served by the api. While this count was process-local the api
could only report what the api had not spent, which was the whole allowance,
every time — a number that looked like reassurance and carried no information.
"""

from __future__ import annotations

import asyncio
import time

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("llm.limiter")


class TokenBucket:
    """Continuously refilling bucket. `capacity` tokens per `period` seconds."""

    def __init__(self, capacity: int, period: float, *, name: str) -> None:
        self._capacity = max(1, capacity)
        self._period = period
        self._name = name
        self._tokens = float(self._capacity)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def rate(self) -> float:
        return self._capacity / self._period

    def _refill(self) -> None:
        now = time.monotonic()
        self._tokens = min(self._capacity, self._tokens + (now - self._updated) * self.rate)
        self._updated = now

    async def acquire(self) -> float:
        """Take one token, waiting if necessary. Returns seconds waited."""
        waited = 0.0
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return waited
                deficit = (1 - self._tokens) / self.rate
            waited += deficit
            log.debug("throttling", bucket=self._name, sleep_s=round(deficit, 2))
            await asyncio.sleep(deficit)

    def tokens_left(self) -> float:
        self._refill()
        return self._tokens


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
