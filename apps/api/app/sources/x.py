"""X (Twitter) trends — interface-complete stub for step 1.

It implements TrendSource so the orchestrator, the merge and the UI's source
chips need no special case when it goes live. It never returns rows: X's
trends endpoints sit behind a paid tier, and the WOEIDs in the region seed
still need verifying against `trends/available` before they can be trusted.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Region, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.x")


class XAdapter(TrendSource):
    name = SourceName.x
    label = "X"
    env_vars = ("X_BEARER_TOKEN",)
    # City-level and fast, so it will outrank news once implemented.
    weight = 0.8

    def __init__(self, bearer_token: str | None = None) -> None:
        self._bearer_token = bearer_token if bearer_token is not None else settings.x_bearer_token

    def is_configured(self) -> bool:
        return bool(self._bearer_token)

    def supports(self, region: Region) -> bool:
        return bool(region.woeids_for_rollup)

    async def fetch(self, region: Region, limit: int = 20) -> list[RawTrendItem]:
        if not self.is_configured():
            log.info("not configured", region=region.code, reason="X_BEARER_TOKEN is not set")
            return []

        log.warning(
            "stub returning no items",
            region=region.code,
            woeids=region.woeids_for_rollup,
            reason="X trends fetch is not implemented in step 1",
        )
        return []
