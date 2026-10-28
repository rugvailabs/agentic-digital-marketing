"""GET /search — one box across topics, brands and generated work.

Three things a user might be looking for with a name in their head, and
historically three places to go and look. A topic is on a board they have
to pick first; a post is in a library behind four filters; a brand is on a
settings page. The box exists so that knowing the name is enough.

Deliberately not fuzzy. Postgres has trigram similarity and pgvector is
already installed, and both were considered and left: a marketer searching
"Diwali" wants the Diwali topics, and a ranked-by-distance list that puts
"Diwali sale" below "Dhanteras" because the vectors say so is a worse
answer than nothing. Substring, case-insensitive, ordered by how the user
would expect each kind to be ordered.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.brands import workspace_id
from app.db.session import get_session
from app.models import (
    AssetKind,
    Brand,
    ContentJob,
    SafetyFlag,
    Trend,
)

router = APIRouter(tags=["search"])

#: Per group. Enough that the right answer is almost always visible, few
#: enough that the panel does not become a page.
PER_GROUP = 5

#: Below this a search matches most of the board and tells you nothing.
MIN_QUERY = 2

#: How many rows to pull per group before folding duplicate stories. India
#: has 36 boards, so a national story can occupy 36 rows; six times the
#: group size finds five distinct stories in every case seen so far without
#: reading the whole table.
OVERSAMPLE = 8


class TopicHit(BaseModel):
    trend_id: int
    topic: str
    region_code: str
    region_name: str
    rank: int
    #: How many other boards carry the same story. One row per board was the
    #: first version, and searching "cricket" returned the same headline
    #: five times because a national story is on every state board.
    also_on: int


class BrandHit(BaseModel):
    id: int
    name: str
    slug: str
    primary_color: str
    secondary_color: str


class WorkHit(BaseModel):
    job_id: int
    kind: str
    #: The caption's hook where there is one, else the topic — the same
    #: thing the library shows as a row title.
    title: str
    topic: str
    brand_name: str
    region_code: str
    editorial_status: str
    preview_url: str | None


class SearchResults(BaseModel):
    query: str
    topics: list[TopicHit]
    brands: list[BrandHit]
    work: list[WorkHit]
    #: So the panel can say "nothing for that" once rather than three times.
    total: int


@router.get("", response_model=SearchResults)
async def search(
    q: str = Query(
        default="", description="What to look for. Under two characters returns nothing."
    ),
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> SearchResults:
    query = q.strip()
    if len(query) < MIN_QUERY:
        return SearchResults(query=query, topics=[], brands=[], work=[], total=0)

    # ILIKE with both wildcards escaped: a user typing "100%" should search
    # for "100%" rather than for everything.
    pattern = f"%{_escape(query)}%"

    # Over-fetched and then folded, because one story sits on many boards
    # and the fold has to see them all to pick the best one.
    matched = (
        await session.scalars(
            select(Trend)
            .options(selectinload(Trend.region))
            .where(
                Trend.topic.ilike(pattern, escape="\\"),
                Trend.rank > 0,
                # The planner will not write about these, so offering one as
                # a destination is offering a dead end.
                Trend.safety_flag.is_distinct_from(SafetyFlag.skip.value),
            )
            # Best rank first: a topic that is second in India is a more
            # useful hit than one that is fortieth in Goa. The fold below
            # relies on this order to keep the first of each story.
            .order_by(Trend.rank, Trend.score.desc())
            .limit(PER_GROUP * OVERSAMPLE)
        )
    ).all()
    topics = _fold(matched)

    brands = (
        await session.scalars(
            select(Brand)
            .where(
                Brand.workspace_id == ws,
                or_(
                    Brand.name.ilike(pattern, escape="\\"),
                    Brand.slug.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(Brand.name)
            .limit(PER_GROUP)
        )
    ).all()

    # Generated work, matched on the topic it was written about. Matching
    # caption text as well was tried and dropped: a caption contains the
    # topic almost by construction, so it doubled the query cost to return
    # the same rows.
    work = (
        await session.scalars(
            select(ContentJob)
            .options(selectinload(ContentJob.brand), selectinload(ContentJob.assets))
            .join(Trend, Trend.id == ContentJob.trend_id)
            .where(
                ContentJob.workspace_id == ws,
                Trend.topic.ilike(pattern, escape="\\"),
            )
            .order_by(ContentJob.created_at.desc(), ContentJob.id.desc())
            .limit(PER_GROUP)
        )
    ).all()

    work_trends = (
        {
            trend.id: trend
            for trend in (
                await session.scalars(
                    select(Trend)
                    .options(selectinload(Trend.region))
                    .where(Trend.id.in_([job.trend_id for job in work]))
                )
            ).all()
        }
        if work
        else {}
    )

    topic_hits = [
        TopicHit(
            trend_id=trend.id,
            topic=trend.topic,
            region_code=trend.region.code if trend.region else "",
            region_name=trend.region.name if trend.region else "",
            rank=trend.rank,
            also_on=others,
        )
        for trend, others in topics
    ]
    brand_hits = [
        BrandHit(
            id=brand.id,
            name=brand.name,
            slug=brand.slug,
            primary_color=brand.primary_color,
            secondary_color=brand.secondary_color,
        )
        for brand in brands
    ]
    work_hits = [_work_hit(job, work_trends.get(job.trend_id)) for job in work]

    return SearchResults(
        query=query,
        topics=topic_hits,
        brands=brand_hits,
        work=work_hits,
        total=len(topic_hits) + len(brand_hits) + len(work_hits),
    )


def _fold(rows: Sequence[Trend]) -> list[tuple[Trend, int]]:
    """One row per story, best board first, with the others counted.

    Identity is the topic key, and deliberately not the cluster id. A
    cluster id is minted per board, so the same story carries a different
    one on IN and on IN-TN — folding on it left four copies of the same
    headline and only collapsed the duplicates within a single board, which
    was the first version of this and looked like the fold was broken.
    """
    best: dict[str, Trend] = {}
    seen: dict[str, int] = {}
    for trend in rows:
        key = trend.topic_key
        seen[key] = seen.get(key, 0) + 1
        # The query is ordered by rank, so the first of a key is its best.
        best.setdefault(key, trend)

    return [(trend, seen[key] - 1) for key, trend in list(best.items())[:PER_GROUP]]


def _work_hit(job: ContentJob, trend: Trend | None) -> WorkHit:
    caption = next((a for a in job.assets if a.kind is AssetKind.caption), None)
    hook = (caption.meta_json or {}).get("hook") if caption else None
    topic = trend.topic if trend else "Topic no longer on the board"
    preview = next(
        (a.url for a in job.assets if a.kind is AssetKind.image and a.url),
        None,
    ) or next(
        ((a.meta_json or {}).get("poster_url") for a in job.assets if a.kind is AssetKind.video),
        None,
    )
    return WorkHit(
        job_id=job.id,
        kind=job.kind.value,
        title=hook if isinstance(hook, str) and hook else topic,
        topic=topic,
        brand_name=job.brand.name,
        region_code=trend.region.code if trend and trend.region else "",
        editorial_status=job.editorial_status.value,
        preview_url=preview if isinstance(preview, str) else None,
    )


def _escape(value: str) -> str:
    """Make a user's literal text safe for ILIKE.

    `%` and `_` are wildcards there, so "100%" and "a_b" would otherwise
    match far more than was asked for. The backslash is escaped first or it
    would escape the escapes.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
