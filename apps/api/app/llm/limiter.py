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

`DailyBudget` itself now lives in `app.core.budget`, since the X adapter
needs the same counter and an adapter must not import from `app.llm`. It is
re-exported here because that is where callers and tests import it from.
"""

from __future__ import annotations

import asyncio
import time

from app.core.budget import DailyBudget
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

    async def acquire(self, cost: float = 1.0) -> float:
        """Take `cost` tokens, waiting if necessary. Returns seconds waited.

        `cost` is what lets one bucket meter requests per minute and another
        meter *tokens* per minute: Groq's free tier caps both, and a single
        curate call is most of a minute's token allowance on its own.

        A cost above the bucket's whole capacity would wait forever, so it is
        clamped. One oversized call then gets through after a full window
        rather than deadlocking the cycle — the provider's own 429 is the
        backstop for a request that is genuinely too large.
        """
        cost = max(0.0, min(float(cost), float(self._capacity)))
        waited = 0.0
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= cost:
                    self._tokens -= cost
                    return waited
                deficit = (cost - self._tokens) / self.rate
            waited += deficit
            log.debug("throttling", bucket=self._name, sleep_s=round(deficit, 2), cost=cost)
            await asyncio.sleep(deficit)

    def tokens_left(self) -> float:
        self._refill()
        return self._tokens


__all__ = ["DailyBudget", "TokenBucket"]
