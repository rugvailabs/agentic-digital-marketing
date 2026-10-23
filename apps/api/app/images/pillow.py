"""Three flat Pillow templates.

They obey the same design rules as the board: flat colour only, no gradients,
no drop shadows, no rounded corners, type and rules carrying the hierarchy.
A post that looks like the desk it came from is the point.

Every template is laid out from the canvas size rather than from constants, so
square and portrait are the same design at two aspect ratios instead of two
designs that drift apart.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from app.core.logging import get_logger
from app.images.base import ImageBrief, ImageProvider, RenderedImage
from app.images.fonts import load_font, shaping_available

log = get_logger("images.pillow")

TEMPLATES = ("bold-type", "split-panel", "flat-colour")

#: Paper and ink, matching the board's light palette.
PAPER = "#EEF1F6"
INK = "#1B2230"
WHITE = "#FFFFFF"


def _contrasting_ink(hex_color: str) -> str:
    """Black or white text, whichever is readable on `hex_color`.

    Relative luminance, not a brightness average: a saturated brand red and a
    mid grey can share an average and need opposite text colours.
    """
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return WHITE

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return INK if luminance > 0.45 else WHITE


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Greedy wrap by measured width.

    Measured, not character-counted: Devanagari and Tamil have wildly different
    advance widths from Latin at the same point size.
    """
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_headline(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    *,
    start: int,
    minimum: int,
    weight: str = "ExtraBold",
) -> tuple[list[str], object, int]:
    """Largest size at which the headline fits the box, stepping down.

    Autofitting rather than truncating: the headline is the whole design, and
    a six-word Tamil line at a fixed size would either overflow or look lost.
    """
    size = start
    while size > minimum:
        font = load_font(text, size, weight)
        lines = _wrap(draw, text, font, max_width)
        line_height = int(size * 1.12)
        # textbbox, not textlength: textlength is the advance width, and Tamil
        # and Telugu glyphs carry ink past it, so a line that "fits" by advance
        # still bleeds over the margin by a few pixels.
        widest = max((draw.textbbox((0, 0), line, font=font)[2] for line in lines), default=0)
        # Width as well as height: a single long word — common in Tamil and
        # Telugu, where one word carries what English needs three for — cannot
        # wrap, so it fits the height check and still runs off the edge.
        if len(lines) * line_height <= max_height and widest <= max_width:
            return lines, font, line_height
        size -= 4
    font = load_font(text, minimum, weight)
    return _wrap(draw, text, font, max_width), font, int(minimum * 1.12)


class PillowTemplateProvider(ImageProvider):
    """Always available: no credentials, no network, no model."""

    name = "pillow"

    def is_configured(self) -> bool:
        return True

    def render(self, brief: ImageBrief) -> RenderedImage:
        width, height = brief.dimensions
        template = brief.template if brief.template in TEMPLATES else TEMPLATES[0]

        if not shaping_available():
            # Worth saying out loud: the image still renders, but Indic text
            # in it is wrong, and that is not obvious from the bytes.
            log.warning("libraqm missing; complex scripts will not shape correctly")

        canvas = Image.new("RGB", (width, height), PAPER)
        draw = ImageDraw.Draw(canvas)

        if template == "bold-type":
            self._bold_type(draw, brief, width, height)
        elif template == "split-panel":
            self._split_panel(canvas, draw, brief, width, height)
        else:
            self._flat_colour(canvas, draw, brief, width, height)

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=True)
        return RenderedImage(
            png=buffer.getvalue(),
            width=width,
            height=height,
            template=template,
            size=brief.size,
            meta={"alt_text": brief.alt_text, "shaped": shaping_available()},
        )

    # ── templates ─────────────────────────────────────────────────────────

    def _bold_type(self, draw, brief: ImageBrief, w: int, h: int) -> None:
        """Type on paper. The headline is the entire design."""
        margin = int(w * 0.08)
        box = w - margin * 2

        draw.rectangle(
            [margin, int(h * 0.10), margin + int(w * 0.14), int(h * 0.105)],
            fill=brief.secondary_color,
        )

        lines, font, line_height = _fit_headline(
            draw, brief.headline, box, int(h * 0.50), start=int(w * 0.15), minimum=36
        )

        sub_lines: list[str] = []
        sub_font = None
        sub_height = int(w * 0.055)
        if brief.subline:
            sub_font = load_font(brief.subline, int(w * 0.042), "Medium")
            sub_lines = _wrap(draw, brief.subline, sub_font, box)[:3]

        # Centre the whole text block in the space between the accent rule and
        # the footer rule. Top-anchoring left a short headline floating above a
        # third of empty canvas.
        top, bottom = int(h * 0.16), int(h * 0.86)
        block = len(lines) * line_height + (
            int(h * 0.02) + len(sub_lines) * sub_height if sub_lines else 0
        )
        y = max(top, top + ((bottom - top) - block) // 2)

        for line in lines:
            draw.text((margin, y), line, font=font, fill=INK)
            y += line_height

        if sub_lines and sub_font is not None:
            y += int(h * 0.02)
            for line in sub_lines:
                draw.text((margin, y), line, font=sub_font, fill=brief.primary_color)
                y += sub_height

        self._footer(draw, brief, w, h, margin, ink=INK)

    def _split_panel(self, canvas, draw, brief: ImageBrief, w: int, h: int) -> None:
        """A solid brand panel over paper; headline sits in the panel."""
        panel_h = int(h * 0.58)
        draw.rectangle([0, 0, w, panel_h], fill=brief.primary_color)
        ink = _contrasting_ink(brief.primary_color)

        margin = int(w * 0.08)
        box = w - margin * 2

        lines, font, line_height = _fit_headline(
            draw, brief.headline, box, panel_h - int(h * 0.20), start=int(w * 0.12), minimum=34
        )
        y = int(h * 0.11)
        for line in lines:
            draw.text((margin, y), line, font=font, fill=ink)
            y += line_height

        # Accent rule sits on the seam, tying the two halves together.
        draw.rectangle(
            [margin, panel_h - 6, margin + int(w * 0.18), panel_h], fill=brief.secondary_color
        )

        if brief.subline:
            sub_font = load_font(brief.subline, int(w * 0.044), "Medium")
            y = panel_h + int(h * 0.06)
            for line in _wrap(draw, brief.subline, sub_font, box)[:3]:
                draw.text((margin, y), line, font=sub_font, fill=INK)
                y += int(w * 0.058)

        self._footer(draw, brief, w, h, margin, ink=INK)

    def _flat_colour(self, canvas, draw, brief: ImageBrief, w: int, h: int) -> None:
        """Full-bleed brand colour. No gradient, by design."""
        draw.rectangle([0, 0, w, h], fill=brief.primary_color)
        ink = _contrasting_ink(brief.primary_color)

        margin = int(w * 0.09)
        box = w - margin * 2

        lines, font, line_height = _fit_headline(
            draw, brief.headline, box, int(h * 0.46), start=int(w * 0.14), minimum=36
        )
        y = int(h * 0.20)
        for line in lines:
            draw.text((margin, y), line, font=font, fill=ink)
            y += line_height

        draw.rectangle(
            [margin, y + int(h * 0.02), margin + int(w * 0.20), y + int(h * 0.025)],
            fill=brief.secondary_color,
        )

        if brief.subline:
            sub_font = load_font(brief.subline, int(w * 0.042), "Medium")
            y += int(h * 0.07)
            for line in _wrap(draw, brief.subline, sub_font, box)[:3]:
                draw.text((margin, y), line, font=sub_font, fill=ink)
                y += int(w * 0.055)

        self._footer(draw, brief, w, h, margin, ink=ink)

    # ── shared furniture ──────────────────────────────────────────────────

    def _footer(self, draw, brief: ImageBrief, w: int, h: int, margin: int, *, ink: str) -> None:
        """Hashtags on one line, brand name opposite. The logo slot is the
        brand block: an image is fetched only once logo_url is wired up."""
        baseline = h - int(h * 0.07)

        # Brand first: it is fixed, so it decides how much room the tags get.
        # Drawing tags first let a long one run under the brand name.
        brand_font = load_font(brief.brand_name, int(w * 0.030), "Bold")
        brand_width = draw.textbbox((0, 0), brief.brand_name, font=brand_font)[2]
        draw.text((w - margin - brand_width, baseline), brief.brand_name, font=brand_font, fill=ink)

        available = w - margin * 2 - brand_width - int(w * 0.04)
        tag_font = load_font(" ".join(brief.hashtags) or "#", int(w * 0.032), "SemiBold")
        shown: list[str] = []
        for tag in brief.hashtags[:3]:
            candidate = " ".join([*shown, tag])
            if draw.textbbox((0, 0), candidate, font=tag_font)[2] > available:
                break
            shown.append(tag)

        if shown:
            draw.text((margin, baseline), " ".join(shown), font=tag_font, fill=ink)

        rule_y = baseline - int(h * 0.025)
        draw.rectangle([margin, rule_y, w - margin, rule_y + 1], fill=ink)
