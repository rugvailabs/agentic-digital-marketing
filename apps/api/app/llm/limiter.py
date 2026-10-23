"""Token-bucket rate limiting for the free tier.

Two buckets per provider: requests per minute, which refills continuously, and
requests per day, which does not. The point is to wait locally rather than
spend the budget discovering a 429 — a rejected call still costs a round trip
and, on some tiers, still counts.

In-process only. A second worker would keep its own buckets; the shared-state
version belongs in Redis and is not worth it until there is a second worker.
"""

from __future__ import annotations

import asyncio
import time

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
    """A hard daily count. Does not refill within the day."""

    def __init__(self, limit: int, *, name: str) -> None:
        self._limit = max(1, limit)
        self._name = name
        self._used: dict[str, int] = {}
        self._day = time.gmtime().tm_yday

    def _roll(self) -> None:
        today = time.gmtime().tm_yday
        if today != self._day:
            self._day, self._used = today, {}

    def spend(self, key: str = "") -> bool:
        """True if there was budget left for `key`. False means stop, not retry.

        Counted per model, because Google's limit is per model too
        (GenerateRequestsPerDayPerProjectPerModel-FreeTier, 20/day on this
        tier). A single shared counter would block a model that still has
        budget, which is exactly what the fallback chain exists to use.
        """
        self._roll()
        used = self._used.get(key, 0)
        if used >= self._limit:
            return False
        self._used[key] = used + 1
        return True

    def remaining(self, key: str = "") -> int:
        self._roll()
        return max(0, self._limit - self._used.get(key, 0))
