"""Font selection per script.

CLAUDE.md requires Devanagari, Tamil, Telugu, Bengali, Gujarati, Kannada and
Malayalam to render, so the Noto face for each is bundled in
`app/assets/fonts` rather than fetched at render time.

Shaping matters as much as coverage: without libraqm (installed in the image)
Pillow draws Devanagari with detached vowel signs and no conjuncts, which looks
broken to anyone who reads the script. `shaping_available()` makes that
visible instead of letting it ship silently.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from app.core.logging import get_logger

log = get_logger("images.fonts")

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

#: Unicode script name prefix -> bundled face. Latin falls through to NotoSans.
SCRIPT_FONTS: dict[str, str] = {
    "DEVANAGARI": "NotoSansDevanagari.ttf",
    "TAMIL": "NotoSansTamil.ttf",
    "TELUGU": "NotoSansTelugu.ttf",
    "BENGALI": "NotoSansBengali.ttf",
    "GUJARATI": "NotoSansGujarati.ttf",
    "KANNADA": "NotoSansKannada.ttf",
    "MALAYALAM": "NotoSansMalayalam.ttf",
}
DEFAULT_FONT = "NotoSans.ttf"


def shaping_available() -> bool:
    """True when Pillow can shape complex scripts (libraqm present)."""
    return bool(getattr(ImageFont.core, "HAVE_RAQM", False))


def script_of(text: str) -> str:
    """The dominant Indic script in `text`, or "LATIN".

    Decided by the first strong character rather than by counting: a Devanagari
    headline with an English brand name in it is still Devanagari.
    """
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        head = name.split(" ")[0]
        if head in SCRIPT_FONTS:
            return head
    return "LATIN"


def font_file(text: str) -> Path:
    return FONT_DIR / SCRIPT_FONTS.get(script_of(text), DEFAULT_FONT)


@lru_cache(maxsize=256)
def _load(path: str, size: int, weight: str) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(path, size)
    try:
        font.set_variation_by_name(weight.encode())
    except Exception:  # pragma: no cover - static face, or weight not present
        # These are variable fonts; a static fallback simply keeps its weight.
        log.debug("weight unavailable", font=Path(path).name, weight=weight)
    return font


def load_font(text: str, size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    """A face that covers `text`, at `size`, in `weight`.

    Cached by (file, size, weight): a template draws the same sizes repeatedly
    and truetype() re-parses the file every call.
    """
    return _load(str(font_file(text)), size, weight)


def missing_fonts() -> list[str]:
    """Bundled faces that are not actually on disk."""
    wanted = [DEFAULT_FONT, *SCRIPT_FONTS.values()]
    return [name for name in wanted if not (FONT_DIR / name).is_file()]
