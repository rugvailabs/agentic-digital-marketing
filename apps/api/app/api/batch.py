"""Generate for the top N topics on a board, in one action.

The Desk generates one post at a time, which is right when a person is
reading a topic and deciding. It is wrong at the start of a week, when the
answer is "the top ten, for this brand, in English" and clicking ten times
is just clicking ten times.

The whole of the difficulty is that each post costs one model call out of a
free tier of a few dozen a day. So this endpoint's real job is to say what
it will do before it does it, and to refuse the part it cannot afford
rather than queueing twelve jobs that fail at nine.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.brands import workspace_id
from app.core.logging import get_logger
from app.db.session import get_session
from app.images.base import SIZES
from app.llm import get_llm
from app.models import (
    Brand,
    ContentJob,
    JobKind,
    JobStatus,
    Language,
    Region,
    SafetyFlag,
    Trend,
)
from app.video.base import SIZES as VIDEO_SIZES

router = APIRouter(tags=["batch"])
log = get_logger("api.batch")

#: Ten is a week of daily posts, and more than that in one click is a lot of
#: work to review. The budget usually bites first anyway.
MAX_N = 25


class BatchRequest(BaseModel):
    brand_id: int
    #: The board to take the top N from.
    region: str
    n: int = Field(default=5, ge=1, le=MAX_N)
    language: Language = Language.english
    #: Posts, or reels. A reel costs the same one writer call.
    kind: JobKind = JobKind.post
    formats: list[str] = Field(default_factory=list)


class Skipped(BaseModel):
    """A topic that was not queued, and the reason in words a user can act
    on."""

    trend_id: int
    topic: str
    reason: str


class BatchResult(BaseModel):
    #: Job ids, in board order.
    queued: list[int]
    skipped: list[Skipped]
    #: What the day had left when this ran, for the message and for the UI
    #: to show without a second request.
    remaining_before: int | None
    requested: int
    #: One line, already written. The caller should not have to assemble
    #: this from the numbers — every client would word it differently and
    #: most would word it badly.
    message: str


class BatchPlan(BaseModel):
    """What a batch would do, without doing it."""

    available: int
    remaining_today: int | None
    would_queue: int
    skipped: list[Skipped]
    message: str


async def _candidates(
    session: AsyncSession, *, region: str, brand_id: int, kind: JobKind, n: int
) -> tuple[list[Trend], list[Skipped]]:
    """The top topics worth generating for, and what was passed over.

    Takes more than `n` from the board, because the reasons below remove
    rows: asking for exactly n and filtering afterwards returns four when
    five were wanted and the fifth was two rows down.
    """
    region_row = await session.scalar(select(Region).where(Region.code == region))
    if region_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"unknown region {region!r}")

    rows = (
        await session.scalars(
            select(Trend)
            .where(Trend.region_id == region_row.id, Trend.rank > 0)
            .order_by(Trend.rank)
            .limit(n * 4)
        )
    ).all()

    # One query for everything this brand already has on these topics,
    # rather than one per topic.
    existing = set(
        (
            await session.scalars(
                select(ContentJob.trend_id).where(
                    ContentJob.brand_id == brand_id,
                    ContentJob.kind == kind,
                    ContentJob.trend_id.in_([t.id for t in rows]),
                )
            )
        ).all()
    )

    chosen: list[Trend] = []
    skipped: list[Skipped] = []
    for trend in rows:
        if len(chosen) >= n:
            break
        if trend.safety_flag == SafetyFlag.skip.value:
            # The planner's rule, applied here too: a batch must not be a
            # way around it.
            skipped.append(
                Skipped(
                    trend_id=trend.id,
                    topic=trend.topic,
                    reason="flagged as a topic we do not market against",
                )
            )
            continue
        if trend.id in existing:
            skipped.append(
                Skipped(
                    trend_id=trend.id,
                    topic=trend.topic,
                    reason="this brand already has one for this topic",
                )
            )
            continue
        chosen.append(trend)

    return chosen, skipped


async def _remaining() -> int | None:
    """Model calls left today, or None when nothing meters a day.

    None is not zero: a key that bills in dollars has no call count, and
    treating "unknown" as "none left" would refuse every batch on a paid
    plan.
    """
    try:
        return (await get_llm().budget()).remaining_today
    except Exception as exc:  # pragma: no cover - a budget read must not fail a request
        log.warning("budget unreadable", error=f"{type(exc).__name__}: {exc}"[:200])
        return None


def _message(
    *,
    requested: int,
    queued: int,
    remaining: int | None,
    skipped: int,
    kind: JobKind = JobKind.post,
    planning: bool = False,
) -> str:
    """One sentence saying what happened, or what would.

    Written here rather than in the client because every client would word
    it differently and most would word it badly — and because the
    interesting case, "you asked for ten and today has four", is exactly the
    one a generic "queued 4 jobs" fails to explain.

    `planning` flips the tense. The plan endpoint exists so the button can
    say "Generate 8 posts" before the click rather than "queued 8" after
    it, and a plan that reports in the past tense gives that away.
    """
    noun = "reel" if kind is JobKind.reel else "post"
    nothing = "Nothing to queue" if planning else "Nothing queued"

    if queued == 0 and remaining == 0:
        return f"{nothing}: today's model calls are used up. The free tier resets at 12:30 IST."
    if queued == 0 and skipped:
        return f"{nothing}: every topic in that range is already done or flagged."
    if queued == 0:
        return f"{nothing}: that board has no topics in range."

    verb = "Ready to generate" if planning else "Queued"
    parts = [f"{verb} {queued} {noun if queued == 1 else noun + 's'}"]
    if queued < requested and remaining is not None and queued >= remaining:
        were = "are" if planning else "were"
        parts.append(
            f"— {requested} {were} asked for, and only {remaining} model "
            f"{'call is' if remaining == 1 else 'calls are'} left today"
        )
    elif queued < requested and skipped:
        is_was = "is" if planning else "was"
        are_were = "are" if planning else "were"
        parts.append(
            f"— {skipped} {'topic ' + is_was if skipped == 1 else 'topics ' + are_were} skipped"
        )
    return f"{' '.join(parts)}."


@router.post("/plan", response_model=BatchPlan)
async def plan_batch(
    payload: BatchRequest,
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> BatchPlan:
    """What would happen, without spending anything.

    The board's button says "Generate 8 posts" rather than "Generate for top
    10" because of this: telling someone the number after the fact, when it
    is lower than the one they chose, is a worse moment than telling them
    before.
    """
    brand = await session.get(Brand, payload.brand_id)
    if brand is None or brand.workspace_id != ws:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown brand")

    chosen, skipped = await _candidates(
        session, region=payload.region, brand_id=brand.id, kind=payload.kind, n=payload.n
    )
    remaining = await _remaining()
    available = len(chosen) if remaining is None else min(len(chosen), remaining)

    return BatchPlan(
        available=len(chosen),
        remaining_today=remaining,
        would_queue=available,
        skipped=skipped,
        message=_message(
            requested=payload.n,
            queued=available,
            remaining=remaining,
            skipped=len(skipped),
            kind=payload.kind,
            planning=True,
        ),
    )


@router.post("", response_model=BatchResult, status_code=status.HTTP_201_CREATED)
async def run_batch(
    payload: BatchRequest,
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> BatchResult:
    """Queue up to N posts for the top of a board.

    Capped at what the day can pay for. The cap is applied before anything
    is written, so the rows that exist are the rows that will run — queueing
    twelve and failing at nine leaves three rows that look like bugs and
    three assets nobody asked for.
    """
    brand = await session.get(Brand, payload.brand_id)
    if brand is None or brand.workspace_id != ws:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown brand")

    chosen, skipped = await _candidates(
        session, region=payload.region, brand_id=brand.id, kind=payload.kind, n=payload.n
    )
    remaining = await _remaining()

    if remaining is not None and len(chosen) > remaining:
        for trend in chosen[remaining:]:
            skipped.append(
                Skipped(
                    trend_id=trend.id,
                    topic=trend.topic,
                    reason="no model calls left today",
                )
            )
        chosen = chosen[:remaining]

    reel = payload.kind is JobKind.reel
    allowed = VIDEO_SIZES if reel else SIZES
    formats = [f for f in payload.formats if f in allowed] or (
        ["reel"] if reel else ["square", "portrait"]
    )

    jobs = [
        ContentJob(
            workspace_id=brand.workspace_id,
            trend_id=trend.id,
            brand_id=brand.id,
            kind=payload.kind,
            language=payload.language,
            formats=formats,
            status=JobStatus.queued,
        )
        for trend in chosen
    ]
    session.add_all(jobs)
    await session.commit()
    for job in jobs:
        await session.refresh(job)

    queued: list[int] = []
    if jobs:
        from app.tasks.ingest import generate_content, render_video

        task = render_video if reel else generate_content
        for job in jobs:
            try:
                task.delay(job.id)
                queued.append(job.id)
            except Exception as exc:
                # Same as the single-job path: say so on the row rather than
                # leaving it queued forever.
                job.status = JobStatus.failed
                job.error = f"could not queue the job: {type(exc).__name__}. Is the worker running?"
                skipped.append(
                    Skipped(
                        trend_id=job.trend_id,
                        topic="",
                        reason="the worker could not be reached",
                    )
                )
        await session.commit()

    log.info(
        "batch queued",
        brand_id=brand.id,
        region=payload.region,
        requested=payload.n,
        queued=len(queued),
        skipped=len(skipped),
        remaining_before=remaining,
    )

    return BatchResult(
        queued=queued,
        skipped=skipped,
        remaining_before=remaining,
        requested=payload.n,
        message=_message(
            requested=payload.n,
            queued=len(queued),
            remaining=remaining,
            skipped=len(skipped),
            kind=payload.kind,
        ),
    )


@router.get("/jobs", response_model=list[int])
async def recent_batch_jobs(
    brand_id: int,
    limit: int = 25,
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> list[int]:
    """The newest jobs for a brand, so a client can watch a batch finish."""
    rows = await session.scalars(
        select(ContentJob.id)
        .where(ContentJob.workspace_id == ws, ContentJob.brand_id == brand_id)
        .order_by(ContentJob.id.desc())
        .limit(max(1, min(100, limit)))
    )
    return list(rows.all())
