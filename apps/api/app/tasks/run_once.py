"""Run one ingest cycle synchronously, with no worker or broker involved.

    docker compose exec api python -m app.tasks.run_once          # all regions
    docker compose exec api python -m app.tasks.run_once IN IN-MH # just these

This is the dev path behind `tf.ps1 ingest`; the scheduled path is Celery Beat.
"""

import asyncio
import json
import sys

from app.db.session import engine
from app.tasks.ingest import run_cycle


async def _main(codes: list[str]) -> None:
    result = await run_cycle(codes or None)
    print(json.dumps(result, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
