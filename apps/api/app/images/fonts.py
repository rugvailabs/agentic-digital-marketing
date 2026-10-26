"""Font selection per script and per role.

CLAUDE.md names two Latin faces — Bricolage Grotesque for display type and
numerals, Schibsted Grotesk for body and UI — and requires Devanagari, Tamil,
Telugu, Bengali, Gujarati, Kannada and Malayalam to render. All of them are
bundled in `app/assets/fonts` rather than fetched at render time; see the
README there for why, and for which face covers what.

Neither Latin face has an Indic script, so a Devanagari headline sets in Noto
Sans Devanagari while the English brand line next to it sets in Schibsted.
That is the right outcome: matching the Latin face is not worth setting
Devanagari in a font with no Devanagari in it.

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

#: Unicode script name prefix -> bundled face. Latin is handled by ROLE_FONTS.
SCRIPT_FONTS: dict[str, str] = {
    "DEVANAGARI": "NotoSansDevanagari.ttf",
    "TAMIL": "NotoSansTamil.ttf",
    "TELUGU": "NotoSansTelugu.ttf",
    "BENGALI": "NotoSansBengali.ttf",
    "GUJARATI": "NotoSansGujarati.ttf",
    "KANNADA": "NotoSansKannada.ttf",
    "MALAYALAM": "NotoSansMalayalam.ttf",
}

#: Latin faces by role. `Brand.font_choice` holds one of these keys.
ROLE_FONTS: dict[str, str] = {
    "display": "BricolageGrotesque.ttf",
    "ui": "SchibstedGrotesk.ttf",
}
DEFAULT_ROLE = "display"
#: Last resort, and the fallback for any script with no bundled face.
DEFAULT_FONT = "NotoSans.ttf"

#: Optical size axis on Bricolage, in points. Set to the drawn size so a 200px
#: display token gets the tight, tall cut and 14px body gets the open one —
#: which is the whole reason CLAUDE.md asks for optical size.
OPSZ_MIN = 12.0
OPSZ_MAX = 96.0


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


def font_file(text: str, role: str = DEFAULT_ROLE) -> Path:
    """The face that covers `text`, preferring the Latin face for `role`."""
    script = script_of(text)
    if script in SCRIPT_FONTS:
        return FONT_DIR / SCRIPT_FONTS[script]
    name = ROLE_FONTS.get(role, ROLE_FONTS[DEFAULT_ROLE])
    path = FONT_DIR / name
    # A missing display face must not take the whole render down; Noto covers
    # Latin perfectly well, it just is not the brand.
    if not path.is_file():
        log.warning("latin face missing, falling back", wanted=name)
        return FONT_DIR / DEFAULT_FONT
    return path


@lru_cache(maxsize=512)
def _load(path: str, size: int, weight: str, opsz: bool) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(path, size)
    try:
        font.set_variation_by_name(weight.encode())
    except Exception:  # pragma: no cover - static face, or weight not present
        # These are variable fonts; a static fallback simply keeps its weight.
        log.debug("weight unavailable", font=Path(path).name, weight=weight)
    if opsz:
        _apply_opsz(font, size)
    return font


def _apply_opsz(font: ImageFont.FreeTypeFont, size: int) -> None:
    """Set the optical size axis to the drawn size, where there is one.

    set_variation_by_name above resets every axis to that instance's defaults,
    so this has to come after it. Axis order is read from the font rather than
    assumed: Bricolage is opsz,wdth,wght and getting the order wrong silently
    sets the wrong axis.
    """
    try:
        axes = font.get_variation_axes()
    except Exception:  # pragma: no cover - static face
        return

    values: list[float] = []
    found = False
    for axis in axes:
        name = axis.get("name")
        label = name.decode() if isinstance(name, bytes) else str(name or "")
        default = float(axis.get("default") or 0)
        if label.lower().startswith("optical"):
            values.append(max(OPSZ_MIN, min(OPSZ_MAX, float(size))))
            found = True
        else:
            values.append(default)

    if not found:
        return
    try:
        font.set_variation_by_axes(values)
    except Exception:  # pragma: no cover - defensive
        log.debug("optical size unavailable", size=size)


def load_font(
    text: str, size: int, weight: str = "Bold", role: str = DEFAULT_ROLE
) -> ImageFont.FreeTypeFont:
    """A face that covers `text`, at `size`, in `weight`, for `role`.

    Cached by (file, size, weight, opsz): a template draws the same sizes
    repeatedly and truetype() re-parses the file every call.
    """
    path = font_file(text, role)
    return _load(str(path), size, weight, path.name == ROLE_FONTS["display"])


def missing_fonts() -> list[str]:
    """Bundled faces that are not actually on disk."""
    wanted = [DEFAULT_FONT, *ROLE_FONTS.values(), *SCRIPT_FONTS.values()]
    return [name for name in wanted if not (FONT_DIR / name).is_file()]
