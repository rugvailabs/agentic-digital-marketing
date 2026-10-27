"""GET /platforms — which trend sources this deployment can use.

Its own router rather than a route under /trends, because platforms are not a
sub-resource of a board: the answer has no region and touches no database. It
is deployment configuration, identical for every board, and the UI fetches it
once.
"""

from fastapi import APIRouter

from app.schemas.trend import PlatformOut
from app.sources import platform_catalog

router = APIRouter(tags=["platforms"])


@router.get("", response_model=list[PlatformOut])
async def list_platforms() -> list[PlatformOut]:
    """Every platform, configured or not, with what it needs if not.

    Unconfigured platforms are included rather than filtered out: the UI
    renders them as "Connect" chips, and an omitted chip would read as a
    platform that does not exist instead of one that needs a key.
    """
    return [PlatformOut.model_validate(entry) for entry in platform_catalog()]
