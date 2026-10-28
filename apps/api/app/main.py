"""FastAPI entrypoint.

Step 1 serves the trend board: regions, merged trends, a manual ingest trigger
and health. No content generation yet.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    batch,
    brands,
    content,
    health,
    ingest,
    library,
    platforms,
    regions,
    trends,
)
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import engine

log = get_logger("api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info("api starting", env=settings.env, tz=settings.tz)
    yield
    await engine.dispose()
    log.info("api stopped")


app = FastAPI(
    title="TrendForge API",
    version="0.1.0",
    description="Trend ingest and board for India. Step 1: no AI generation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(platforms.router, prefix="/platforms")
app.include_router(regions.router, prefix="/regions")
app.include_router(trends.router, prefix="/trends")
app.include_router(ingest.router, prefix="/ingest")
app.include_router(brands.router, prefix="/brands")
app.include_router(library.router, prefix="/library")
app.include_router(batch.router, prefix="/content/batch")
# content routes carry their own full paths (/content/...).
app.include_router(content.router)
