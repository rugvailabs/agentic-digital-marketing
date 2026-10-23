"""Idempotent region seed.

    docker compose exec api python -m app.db.seed

Re-running updates names/codes/identifiers in place and never duplicates rows,
so it is safe to run on every `tf.ps1 up`.
"""

import asyncio

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.regions_data import CITY_COUNT, STATE_COUNT, UT_COUNT, all_regions
from app.db.session import SessionLocal, engine
from app.models import Region, RegionKind

log = get_logger("seed")


async def seed_regions() -> dict[str, int]:
    created = updated = 0

    async with SessionLocal() as session:
        existing = {r.code: r for r in (await session.scalars(select(Region))).all()}

        for row in all_regions():
            parent_code = row["parent"]
            parent = existing.get(parent_code) if parent_code else None
            if parent_code and parent is None:
                # all_regions() yields parents first, so this means bad data.
                raise RuntimeError(f"parent {parent_code} missing for {row['code']}")

            region = existing.get(row["code"])
            if region is None:
                region = Region(code=row["code"])
                session.add(region)
                created += 1
            else:
                updated += 1

            region.name = row["name"]
            region.kind = RegionKind(row["kind"])
            region.parent_id = parent.id if parent else None
            region.google_trends_geo = row["google_trends_geo"]
            region.x_woeid = row["x_woeid"]
            region.sort_order = row["sort_order"]
            region.is_active = True

            # Flush so this row's id is available as a parent in the same pass.
            await session.flush()
            existing[region.code] = region

        await session.commit()

    totals = {"created": created, "updated": updated, "total": created + updated}
    log.info(
        "regions seeded",
        **totals,
        states=STATE_COUNT,
        union_territories=UT_COUNT,
        cities=CITY_COUNT,
    )
    return totals


async def _main() -> None:
    await seed_regions()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
