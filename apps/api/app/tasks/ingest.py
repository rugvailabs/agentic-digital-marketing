"""The ingest cycle: fetch -> snapshot -> merge -> upsert.

Idempotency: every snapshot row is unique on (region, source, run_id) and
inserted with ON CONFLICT DO NOTHING, so a Celery redelivery re-runs the cycle
without duplicating history. The trends upsert is keyed on
(region, topic_key), so re-running only moves scores.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import SessionLocal, engine
from app.models import (
    PipelineStatus,
    Region,
    SnapshotStatus,
    Trend,
    TrendSnapshot,
)
from app.sources import all_sources
from app.sources.base import RawTrendItem, TrendSource
from app.tasks.merge import SourceItems, merge, next_velocity

log = get_logger("ingest")

#: Items to request per source per region. Enough for a long board, small
#: enough that one cycle over 53 regions stays polite to free endpoints.
FETCH_LIMIT = 25
#: Rows kept per region. The ladder is scannable, not exhaustive.
BOARD_LIMIT = 40


async def fetch_one(
    source: TrendSource, region: Region, run_id: str, captured_at: datetime
) -> dict[str, Any]:
    """Run one adapter against one region, never raising.

    Returns the row to insert into trend_snapshots. An unconfigured or
    unsupported source is recorded as `skipped` rather than silently omitted,
    so the board can explain a thin region.
    """
    started = utcnow()

    def row(status: SnapshotStatus, items: list[RawTrendItem], error: str | None = None) -> dict:
        return {
            "region_id": region.id,
            "source": source.name,
            "run_id": run_id,
            "captured_at": captured_at,
            "status": status,
            "error": error,
            "duration_ms": int((utcnow() - started).total_seconds() * 1000),
            "item_count": len(items),
            "items": [i.as_dict() for i in items],
        }

    if not source.is_configured():
        log.info(
            "source skipped", source=source.name.value, region=region.code, reason="not configured"
        )
        return row(SnapshotStatus.skipped, [], "not configured")

    if not source.supports(region):
        return row(SnapshotStatus.skipped, [], "region not supported by this source")

    try:
        items = await source.fetch(region, limit=FETCH_LIMIT)
    except Exception as exc:
        # One flaky endpoint must not cost us the other three sources.
        log.warning(
            "source failed",
            source=source.name.value,
            region=region.code,
            error=f"{type(exc).__name__}: {exc}",
        )
        return row(SnapshotStatus.error, [], f"{type(exc).__name__}: {exc}")

    status = SnapshotStatus.ok if items else SnapshotStatus.empty
    return row(status, items)


async def ingest_region(
    session: AsyncSession,
    region: Region,
    sources: list[TrendSource],
    run_id: str,
    captured_at: datetime,
    semaphore: asyncio.Semaphore,
) -> dict[str, int]:
    """Snapshot every source for one region, then rebuild that region's board."""

    async def guarded(source: TrendSource) -> dict[str, Any]:
        async with semaphore:
            return await fetch_one(source, region, run_id, captured_at)

    rows = await asyncio.gather(*(guarded(s) for s in sources))

    # ON CONFLICT DO NOTHING makes a retried task a no-op rather than a dupe.
    await session.execute(
        pg_insert(TrendSnapshot)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_trend_snapshots_run")
    )

    by_name = {s.name.value: s for s in sources}
    contributions = [
        SourceItems(
            source=str(row["source"].value),
            weight=by_name[str(row["source"].value)].weight,
            items=[RawTrendItem(**item) for item in row["items"]],
        )
        for row in rows
        if row["status"] is SnapshotStatus.ok
    ]

    merged = merge(contributions, limit=BOARD_LIMIT)
    await upsert_trends(session, region, merged, captured_at)
    await session.commit()

    counts = {
        "items": sum(int(r["item_count"]) for r in rows),
        "topics": len(merged),
        "sources_ok": len(contributions),
    }
    log.info("region ingested", region=region.code, **counts)
    return counts


async def upsert_trends(
    session: AsyncSession, region: Region, merged: list, captured_at: datetime
) -> None:
    """Rewrite one region's board, carrying velocity history forward."""
    existing = {
        t.topic_key: t
        for t in (await session.scalars(select(Trend).where(Trend.region_id == region.id))).all()
    }
    seen: set[str] = set()

    for position, topic in enumerate(merged, start=1):
        seen.add(topic.topic_key)
        row = existing.get(topic.topic_key)
        if row is None:
            row = Trend(
                region_id=region.id,
                topic_key=topic.topic_key,
                first_seen_at=captured_at,
                status=PipelineStatus.curated,
            )
            session.add(row)

        row.topic = topic.topic
        row.category = topic.category
        row.rank = position
        row.score = topic.score
        row.volume = topic.volume
        row.velocity = next_velocity(row.velocity, topic.score)
        row.hashtags = topic.hashtags
        row.sources = topic.sources
        row.evidence = topic.evidence
        row.last_seen_at = captured_at
        if row.status is PipelineStatus.ingested:
            row.status = PipelineStatus.curated

    # A topic that dropped off keeps its row and history but loses its rank, so
    # it can come back without resetting the sparkline to zeros.
    for key, row in existing.items():
        if key not in seen and row.rank != 0:
            row.rank = 0
            row.velocity = next_velocity(row.velocity, 0.0)


async def run_cycle(region_codes: list[str] | None = None) -> dict[str, Any]:
    """One full ingest cycle. Used by the Celery task and by `run_once`."""
    run_id = str(uuid.uuid4())
    captured_at = utcnow()
    sources = all_sources()
    semaphore = asyncio.Semaphore(max(1, settings.ingest_max_concurrency))

    log.info(
        "cycle started",
        run_id=run_id,
        sources=[s.name.value for s in sources if s.is_configured()],
        skipped=[s.name.value for s in sources if not s.is_configured()],
    )

    async with SessionLocal() as session:
        query = select(Region).where(Region.is_active.is_(True)).order_by(Region.sort_order)
        if region_codes:
            query = query.where(Region.code.in_(region_codes))
        regions = (await session.scalars(query)).all()

        totals = {"regions": 0, "items": 0, "topics": 0}
        for region in regions:
            counts = await ingest_region(session, region, sources, run_id, captured_at, semaphore)
            totals["regions"] += 1
            totals["items"] += counts["items"]
            totals["topics"] += counts["topics"]

    result = {"run_id": run_id, "captured_at": captured_at.isoformat(), **totals}
    log.info("cycle finished", **result)
    return result


async def _run_cycle_and_release(region_codes: list[str] | None) -> dict[str, Any]:
    """Run a cycle and drop the connection pool *inside the same loop*.

    The worker process is reused across tasks and each task gets a fresh
    asyncio.run() loop. Disposing the engine from a later loop leaves asyncpg
    trying to close sockets bound to the finished one, which surfaces as
    `RuntimeError: Event loop is closed` after an otherwise successful task.
    """
    try:
        return await run_cycle(region_codes)
    finally:
        await engine.dispose()


@shared_task(name="app.tasks.ingest.ingest_all_regions", bind=True, max_retries=2)
def ingest_all_regions(self, region_codes: list[str] | None = None) -> dict[str, Any]:
    """Beat entrypoint. Every 30 minutes by default."""
    try:
        return asyncio.run(_run_cycle_and_release(region_codes))
    except Exception as exc:
        log.error("cycle failed", error=f"{type(exc).__name__}: {exc}")
        raise self.retry(exc=exc, countdown=60) from exc
