"""The music bed.

Beds are read from `app/assets/music`. The directory ships empty: licensed
music is not something this repository can carry, and a bed is optional by
design — a reel with a clear voice and no music is fine, a reel with music
over the voice is not.

Drop files in and they are picked up; see the README there.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("video.music")

MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
SUFFIXES = {".mp3", ".m4a", ".ogg", ".wav", ".flac"}


@lru_cache(maxsize=1)
def available() -> tuple[Path, ...]:
    """Every usable bed on disk, in a stable order."""
    if not MUSIC_DIR.is_dir():
        return ()
    return tuple(
        sorted(p for p in MUSIC_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)
    )


def is_configured() -> bool:
    return bool(settings.music_enabled) and bool(available())


def pick(seed: str = "") -> Path | None:
    """A bed for this reel, or None.

    Chosen by hashing the seed rather than at random, so re-rendering the same
    job twice produces the same reel. A render that changes its soundtrack
    every time it runs is impossible to review.
    """
    beds = available()
    if not settings.music_enabled:
        return None
    if not beds:
        log.info("no music beds installed, reel will carry voice only", directory=str(MUSIC_DIR))
        return None

    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).digest()
    return beds[digest[0] % len(beds)]
