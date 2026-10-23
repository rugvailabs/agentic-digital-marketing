"""Async engine + session factory, shared by the API and the Celery tasks."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def task_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory owned by one Celery task.

    Celery runs tasks on a thread pool and each gets its own asyncio.run loop,
    so a shared engine is wrong twice over: asyncpg connections belong to the
    loop that opened them, and disposing the global pool at the end of one
    task tears it out from under a sibling still running. Both showed up as
    "attached to a different loop" on a job that had otherwise succeeded.
    """
    task_engine = create_async_engine(
        settings.database_url, pool_pre_ping=True, pool_size=2, max_overflow=4
    )
    try:
        yield async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await task_engine.dispose()
