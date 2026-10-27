"""Projecting `trend_items` onto `trend_sources`.

One row per topic per platform, derived rather than written alongside the
board. That choice is the point of this module.

`trends` has two writers that disagree about almost everything: the non-LLM
merge keys topics on the source headline, the curator keys them on its own
rewritten title, and `upsert_trends` steps aside entirely once a region has
been curated. Teaching both of them to also maintain per-platform rows would
mean two implementations of the same aggregation, drifting apart, with the
one that matters — the curated path — being the one less often exercised.

`trend_items` already carries everything a platform row needs: source, rank
within that source, volume, url, and whatever the adapter put in `extra`.
Both writers attach items to a trend. So this reads the items and aggregates,
and is correct for whichever writer produced the board.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import SourceName, Trend, TrendItem, TrendPlatform

log = get_logger("tasks.platforms")

#: Per platform per topic. A platform contributing more than this to one
#: topic is a platform repeating itself.
MAX_HASHTAGS_PER_PLATFORM = 8


def _hashtags_of(item: TrendItem) -> list[str]:
    """The adapter's per-platform hashtags, if it reported any.

    Only `extra["hashtags"]` counts. YouTube also has `extra["tags"]`, which
    is the uploader's keyword list with no "#" — publishing those as hashtags
    would put "cricket" in a caption as "#cricket" on a brand's behalf, which
    nobody asked for.
    """
    raw = (item.extra or {}).get("hashtags")
    if not isinstance(raw, list):
        return []
    return [str(tag) for tag in raw if str(tag).strip()]


async def sync_platforms(
    session: AsyncSession,
    region_id: int,
    seen_at: datetime,
    merged: Sequence[Any] | None = None,
) -> int:
    """Rebuild `trend_sources` for one region's live board. Returns rows written.

    Aggregated per (topic, platform):
      rank    the best that platform gave it. A story can be its 2nd item and
              its 14th; the 2nd is what that platform is saying about it.
      volume  the largest it reported. Not summed — two YouTube videos about
              one story are not one video with their views added.
      url     from the best-ranked item, so the link matches the rank shown.
    """
    rows = (
        await session.execute(
            select(TrendItem, Trend.id)
            .join(Trend, TrendItem.trend_id == Trend.id)
            .where(Trend.region_id == region_id, Trend.rank > 0)
            .order_by(TrendItem.rank)
        )
    ).all()

    # (trend_id, platform) -> aggregate. Insertion order follows the rank
    # ordering above, so the first item seen for a platform is its best.
    buckets: dict[tuple[int, SourceName], dict[str, Any]] = {}
    for item, trend_id in rows:
        key = (trend_id, item.source)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "trend_id": trend_id,
                "platform": item.source,
                "rank": item.rank or None,
                "volume": int(item.volume or 0),
                "hashtags": [],
                "seen": set(),
                "url": item.url,
                "seen_at": seen_at,
            }
            buckets[key] = bucket
        else:
            if item.rank and (bucket["rank"] is None or item.rank < bucket["rank"]):
                bucket["rank"] = item.rank
                bucket["url"] = item.url
            bucket["volume"] = max(bucket["volume"], int(item.volume or 0))

        for tag in _hashtags_of(item):
            lowered = tag.lower()
            if (
                lowered not in bucket["seen"]
                and len(bucket["hashtags"]) < MAX_HASHTAGS_PER_PLATFORM
            ):
                bucket["seen"].add(lowered)
                bucket["hashtags"].append(tag)

    if not buckets and merged:
        # No trend_items, which is the normal state for 52 of the 53 regions:
        # items are written by the curator, and the merge does not write
        # them. The merge carries the same aggregates on MergedTopic.platforms
        # instead, so fall back to those.
        buckets = await _from_merged(session, region_id, seen_at, merged)

    if not buckets:
        # Nothing to write and nothing to clear: a region with neither items
        # nor a fresh merge has not been ingested, which is not the same as a
        # region whose platforms have gone away.
        return 0

    values = [
        {
            "trend_id": b["trend_id"],
            "platform": b["platform"],
            "rank": b["rank"],
            "volume": b["volume"],
            "hashtags": b["hashtags"],
            "url": b["url"],
            "seen_at": b["seen_at"],
        }
        for b in buckets.values()
    ]

    # Upsert rather than delete-then-insert: the unique constraint is
    # (trend_id, platform), so a cycle updates the row it already has and the
    # table stays the size of the board. A delete pass would also take the
    # Instagram rows, which are measured on demand from the Desk and would
    # not come back until a user opened the topic again.
    statement = insert(TrendPlatform).values(values)
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_trend_sources_trend_platform",
            set_={
                "rank": statement.excluded.rank,
                "volume": statement.excluded.volume,
                "hashtags": statement.excluded.hashtags,
                "url": statement.excluded.url,
                "seen_at": statement.excluded.seen_at,
            },
        )
    )
    log.info("platform rows synced", region_id=region_id, rows=len(values))
    return len(values)


async def _from_merged(
    session: AsyncSession,
    region_id: int,
    seen_at: datetime,
    merged: Sequence[Any],
) -> dict[tuple[int, SourceName], dict[str, Any]]:
    """The merge's own per-platform aggregates, keyed to trend ids.

    `MergedTopic` knows its `topic_key` but not the row id it was written to,
    so the ids are looked up in one query rather than per topic.
    """
    ids = dict(
        (
            await session.execute(
                select(Trend.topic_key, Trend.id).where(
                    Trend.region_id == region_id, Trend.rank > 0
                )
            )
        ).all()
    )

    buckets: dict[tuple[int, SourceName], dict[str, Any]] = {}
    for topic in merged:
        topic_key = str(getattr(topic, "topic_key", "") or "")
        trend_id = ids.get(topic_key) if topic_key else None
        if trend_id is None:
            continue
        for entry in getattr(topic, "platforms", None) or []:
            platform = entry["platform"]
            name = platform if isinstance(platform, SourceName) else SourceName(str(platform))
            buckets[(trend_id, name)] = {
                "trend_id": trend_id,
                "platform": name,
                "rank": entry.get("rank"),
                "volume": int(entry.get("volume") or 0),
                "hashtags": list(entry.get("hashtags") or [])[:MAX_HASHTAGS_PER_PLATFORM],
                "url": entry.get("url"),
                "seen_at": seen_at,
            }
    return buckets
