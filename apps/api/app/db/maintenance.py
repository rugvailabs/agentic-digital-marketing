"""Housekeeping for the trends table.

    docker compose exec api python -m app.db.maintenance --dry-run
    docker compose exec api python -m app.db.maintenance

A topic drops to rank 0 when it leaves a board but keeps its row, so velocity
history survives if it comes back. Most never do, and the curator's own
matching means a reworded topic now updates its row rather than leaving a
fork behind — so the rank-0 tail only grows. This prunes the part of it that
has sat untouched long enough to be dead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import SessionLocal, engine
from app.models import ContentAsset, ContentJob, Trend

log = get_logger("maintenance")

DEFAULT_DAYS = 7


async def survey(session: AsyncSession, days: int) -> dict[str, Any]:
    """What a run would touch. Separated so --dry-run and the real run agree."""
    cutoff = utcnow() - timedelta(days=days)

    stale = select(Trend.id).where(Trend.rank == 0, Trend.last_seen_at < cutoff).subquery()
    jobs = select(ContentJob.id).where(ContentJob.trend_id.in_(select(stale.c.id))).subquery()

    return {
        "cutoff": cutoff.isoformat(),
        "rank0_total": await session.scalar(
            select(func.count()).select_from(Trend).where(Trend.rank == 0)
        )
        or 0,
        "topics": await session.scalar(select(func.count()).select_from(stale)) or 0,
        "jobs": await session.scalar(select(func.count()).select_from(jobs)) or 0,
        "assets": await session.scalar(
            select(func.count())
            .select_from(ContentAsset)
            .where(ContentAsset.job_id.in_(select(jobs.c.id)))
        )
        or 0,
        "stored_images": await session.scalar(
            select(func.count())
            .select_from(ContentAsset)
            .where(
                ContentAsset.job_id.in_(select(jobs.c.id)),
                ContentAsset.url.is_not(None),
            )
        )
        or 0,
    }


async def clean_orphans(days: int = DEFAULT_DAYS, *, dry_run: bool = False) -> dict[str, Any]:
    """Delete rank-0 topics last seen before the cutoff, and their content.

    Content jobs and assets go with them through the FK cascade — a job whose
    topic no longer exists cannot be regenerated or opened, so keeping it is
    only clutter.
    """
    async with SessionLocal() as session:
        result = await survey(session, days)
        result["dry_run"] = dry_run

        if result["topics"] and not dry_run:
            # One statement; ON DELETE CASCADE on content_jobs.trend_id and
            # content_assets.job_id takes the rest.
            cutoff = utcnow() - timedelta(days=days)
            await session.execute(delete(Trend).where(Trend.rank == 0, Trend.last_seen_at < cutoff))
            await session.commit()

    log.info("clean-orphans", **result)
    return result


def describe(result: dict[str, Any], days: int) -> str:
    if result["topics"] == 0:
        return (
            f"Nothing to clean: {result['rank0_total']} topics sit at rank 0, "
            f"none last seen before {result['cutoff'][:10]} ({days} days ago)."
        )
    verb = "Would delete" if result["dry_run"] else "Deleted"
    line = (
        f"{verb} {result['topics']} rank-0 topics last seen before "
        f"{result['cutoff'][:10]}, with {result['jobs']} content jobs and "
        f"{result['assets']} assets."
    )
    if result["stored_images"]:
        # Said out loud because this command does not touch object storage.
        line += (
            f"\n{result['stored_images']} rendered PNGs remain in object storage; "
            "this command only prunes the database."
        )
    return line


async def _main(days: int, dry_run: bool) -> None:
    result = await clean_orphans(days, dry_run=dry_run)
    print(describe(result, days))
    print(json.dumps(result, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prune long-dead rank-0 topics.")
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS, help=f"age cutoff (default {DEFAULT_DAYS})"
    )
    parser.add_argument("--dry-run", action="store_true", help="report without deleting")
    args = parser.parse_args()
    asyncio.run(_main(args.days, args.dry_run))
