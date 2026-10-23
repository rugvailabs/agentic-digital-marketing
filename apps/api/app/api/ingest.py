"""POST /ingest/run — manual trigger, for development.

Runs the cycle inline by default so the endpoint works with `docker compose up
api` alone; pass `wait: false` to hand it to Celery instead. The response says
which path was taken.
"""

from fastapi import APIRouter, Body, HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.schemas.trend import IngestRunResponse
from app.tasks.ingest import ingest_all_regions, run_cycle

router = APIRouter(tags=["ingest"])
log = get_logger("api.ingest")


@router.post("/run", response_model=IngestRunResponse)
async def run_ingest(
    regions: list[str] | None = Body(
        default=None,
        description="Region codes to ingest; omit for every active region",
        examples=[["IN", "IN-MH"]],
    ),
    wait: bool = Body(default=True, description="Run inline and return the result"),
) -> IngestRunResponse:
    if not settings.is_dev:
        # An unauthenticated "go fetch everything" button is a DoS lever, and
        # these are third-party endpoints we do not own the quota for.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="manual ingest is only enabled when ENV=dev"
        )

    if wait:
        result = await run_cycle(regions)
        log.info("ingest ran inline", **result)
        return IngestRunResponse(**result, inline=True)

    try:
        task = ingest_all_regions.delay(regions)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"could not queue ingest: {type(exc).__name__}",
        ) from exc

    log.info("ingest queued", task_id=task.id, regions=regions)
    # Counts are unknown until the worker finishes; poll GET /trends instead.
    return IngestRunResponse(
        run_id=task.id, captured_at=utcnow(), regions=0, items=0, topics=0, inline=False
    )
