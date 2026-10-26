"""Three post templates, rendered with Pillow.

They obey the same rules as the board — flat colour, no gradient, no shadow,
type and rules carrying the hierarchy — so a post looks like the desk it came
from. Each one is a genuinely different idea rather than the same layout in
three palettes:

* **Poster** — full-bleed brand colour, the headline at poster scale. For a
  statement.
* **Split** — a secondary-colour block holding one short token (a score, a
  price, a year) over a white half carrying the headline. For a number.
* **Wire** — the app itself as a post: paper, a dotted rule, the velocity
  sparkline drawn large. For "this is moving".

Everything is laid out from the canvas size, so square and portrait are one
design at two aspect ratios rather than two designs that drift apart. The
canvas is rendered at SUPERSAMPLE and downscaled, which is what keeps small
text and Indic conjuncts crisp.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw
from PIL.Image import Resampling

from app.core.logging import get_logger
from app.images.base import ImageBrief, ImageProvider, RenderedImage
from app.images.fonts import load_font, shaping_available

log = get_logger("images.pillow")

TEMPLATES = ("poster", "split", "wire")

#: Shown in the Desk and in asset variants. Full words, not truncated slugs.
TEMPLATE_LABELS = {
    "poster": "Poster",
    "split": "Split panel",
    "wire": "Wire",
}

#: Board palette. Chilli is the accent the Wire sparkline uses, exactly as the
#: ladder does — it means rising, and nothing else on either surface.
PAPER = "#EEF1F6"
INK = "#1B2230"
SLATE = "#5B6578"
RULE = "#D5DAE3"
CHILLI = "#D8322B"
WHITE = "#FFFFFF"

#: Draw at 2x and downscale. Pillow has no hinting at display size, so a 1x
#: render leaves 14px hashtags and Tamil conjuncts visibly soft.
SUPERSAMPLE = 2

ELLIPSIS = "…"


def contrasting_ink(hex_color: str) -> str:
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


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    """Ink width, not advance width.

    textlength is the advance; Tamil and Telugu glyphs carry ink past it, so a
    line that "fits" by advance still bleeds over the margin.
    """
    if not text:
        return 0
    return int(draw.textbbox((0, 0), text, font=font)[2])


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Greedy wrap by measured width, not character count — Devanagari and
    Tamil have nothing like Latin advance widths at the same point size."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    *,
    start: int,
    minimum: int,
    weight: str = "ExtraBold",
    leading: float = 1.1,
    role: str = "display",
) -> tuple[list[str], object, int]:
    """Largest size at which `text` fits the box, stepping down.

    Both dimensions are checked: a single long word — common in Tamil and
    Telugu, where one word carries what English needs three for — cannot wrap,
    so it passes a height-only check and still runs off the edge.
    """
    size = max(start, minimum)
    while size > minimum:
        font = load_font(text, size, weight, role)
        lines = wrap(draw, text, font, max_width)
        line_height = int(size * leading)
        widest = max((text_width(draw, line, font) for line in lines), default=0)
        if len(lines) * line_height <= max_height and widest <= max_width:
            return lines, font, line_height
        size -= max(2, size // 24)

    font = load_font(text, minimum, weight, role)
    return wrap(draw, text, font, max_width), font, int(minimum * leading)


def fit_single_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    *,
    start: int,
    minimum: int,
    weight: str,
    role: str = "display",
) -> object:
    """Largest size at which `text` fits on one line without wrapping."""
    size = max(start, minimum)
    while size > minimum:
        font = load_font(text, size, weight, role)
        if text_width(draw, text, font) <= max_width:
            return font
        size -= max(2, size // 20)
    return load_font(text, minimum, weight, role)


def hashtag_line(
    draw: ImageDraw.ImageDraw, hashtags: list[str], font, max_width: int, limit: int = 3
) -> str:
    """At most `limit` tags, ellipsised to fit `max_width` exactly.

    Measured rather than counted, and ellipsised rather than clipped: a
    hashtag cut mid-word by an overflowing container reads as a typo, and one
    running under the logo reads as a bug.
    """
    chosen: list[str] = []
    for tag in hashtags[:limit]:
        candidate = " ".join([*chosen, tag])
        if text_width(draw, candidate, font) > max_width:
            break
        chosen.append(tag)

    if chosen:
        return " ".join(chosen)
    if not hashtags:
        return ""

    # Not even one fits whole: shorten the first until it does, with an
    # ellipsis so the truncation is visible rather than silent.
    tag = hashtags[0]
    while len(tag) > 2:
        tag = tag[:-1]
        if text_width(draw, tag + ELLIPSIS, font) <= max_width:
            return tag + ELLIPSIS
    return ""


class PillowTemplateProvider(ImageProvider):
    """Always available: no credentials, no network, no model."""

    name = "pillow"

    def is_configured(self) -> bool:
        return True

    def render(self, brief: ImageBrief) -> RenderedImage:
        width, height = brief.dimensions
        template = brief.template if brief.template in TEMPLATES else TEMPLATES[0]

        if not shaping_available():
            # Worth saying out loud: the image still renders, but Indic text in
            # it is wrong, and that is not obvious from the bytes.
            log.warning("libraqm missing; complex scripts will not shape correctly")

        scale = SUPERSAMPLE
        canvas = Image.new("RGB", (width * scale, height * scale), PAPER)
        draw = ImageDraw.Draw(canvas)
        w, h = width * scale, height * scale

        if template == "poster":
            self._poster(draw, brief, w, h)
        elif template == "split":
            self._split(draw, brief, w, h)
        else:
            self._wire(draw, brief, w, h)

        canvas = canvas.resize((width, height), Resampling.LANCZOS)
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=True)

        return RenderedImage(
            png=buffer.getvalue(),
            width=width,
            height=height,
            template=template,
            size=brief.size,
            meta={
                "alt_text": brief.alt_text,
                "shaped": shaping_available(),
                "label": TEMPLATE_LABELS[template],
            },
        )

    # ── templates ─────────────────────────────────────────────────────────

    def _poster(self, draw, brief: ImageBrief, w: int, h: int) -> None:
        """Full-bleed brand colour; the headline is the whole design."""
        draw.rectangle([0, 0, w, h], fill=brief.primary_color)
        ink = contrasting_ink(brief.primary_color)

        margin = int(w * 0.08)
        box = w - margin * 2

        # 96-120px at 1080 wide, which is 0.089-0.111 of the canvas.
        lines, font, line_height = fit_text(
            draw,
            brief.headline,
            box,
            int(h * 0.46),
            start=int(w * 0.111),
            minimum=int(w * 0.050),
            role=brief.font_role,
        )

        sub_font = load_font(brief.subline or " ", int(w * 0.038), "Medium", "ui")
        sub_lines = wrap(draw, brief.subline, sub_font, box)[:3] if brief.subline else []
        sub_height = int(w * 0.052)

        block = len(lines) * line_height + (int(h * 0.03) + len(sub_lines) * sub_height)
        top, bottom = int(h * 0.12), int(h * 0.80)
        y = max(top, top + ((bottom - top) - block) // 2)

        for line in lines:
            draw.text((margin, y), line, font=font, fill=ink)
            y += line_height

        # Thin secondary rule between headline and subline.
        y += int(h * 0.014)
        draw.rectangle(
            [margin, y, margin + int(w * 0.16), y + max(2, int(h * 0.004))],
            fill=brief.secondary_color,
        )
        y += int(h * 0.034)

        for line in sub_lines:
            draw.text((margin, y), line, font=sub_font, fill=ink)
            y += sub_height

        self._footer(draw, brief, w, h, margin, ink=ink, rule=False)

    def _split(self, draw, brief: ImageBrief, w: int, h: int) -> None:
        """A secondary-colour block carrying one token, over a white half."""
        block_h = int(h * 0.60)
        draw.rectangle([0, 0, w, block_h], fill=brief.secondary_color)
        draw.rectangle([0, block_h, w, h], fill=WHITE)
        block_ink = contrasting_ink(brief.secondary_color)

        margin = int(w * 0.08)
        box = w - margin * 2

        token = brief.display_token or (brief.headline.split() or [""])[0]
        token_font = fit_single_line(
            draw,
            token,
            box,
            start=int(w * 0.34),
            minimum=int(w * 0.09),
            weight="ExtraBold",
            role=brief.font_role,
        )
        bbox = draw.textbbox((0, 0), token, font=token_font)
        draw.text(
            (margin, block_h // 2 - (bbox[3] - bbox[1]) // 2 - bbox[1]),
            token,
            font=token_font,
            fill=block_ink,
        )

        y = block_h + int(h * 0.06)

        # Headline and subline share one band, which ends above the footer
        # rule. The subline is measured and its rows reserved *before* the
        # headline is fitted: sized against the whole band, a headline that
        # takes one line more than expected pushes the subline straight
        # through the hashtags. Which is not hypothetical — it is what
        # happened when the Latin face changed to a narrower one.
        sub_height = int(w * 0.044)
        sub_font = load_font(brief.subline or " ", int(w * 0.032), "Medium", "ui")
        sub_lines = wrap(draw, brief.subline, sub_font, box)[:2] if brief.subline else []
        gap = int(h * 0.012) if sub_lines else 0
        band_bottom = self._footer_top(h) - int(h * 0.02)
        headline_box = max(int(h * 0.10), band_bottom - y - gap - len(sub_lines) * sub_height)

        lines, font, line_height = fit_text(
            draw,
            brief.headline,
            box,
            headline_box,
            start=int(w * 0.058),
            minimum=int(w * 0.030),
            weight="Bold",
            role=brief.font_role,
        )
        for line in lines:
            draw.text((margin, y), line, font=font, fill=INK)
            y += line_height

        if sub_lines:
            y += gap
            for line in sub_lines:
                draw.text((margin, y), line, font=sub_font, fill=SLATE)
                y += sub_height

        self._footer(draw, brief, w, h, margin, ink=INK, rule=True)

    def _wire(self, draw, brief: ImageBrief, w: int, h: int) -> None:
        """The board as a post: paper, a dotted rule, the sparkline enlarged."""
        draw.rectangle([0, 0, w, h], fill=PAPER)
        margin = int(w * 0.08)
        box = w - margin * 2

        label = f"Trending in {brief.region_name}" if brief.region_name else "Trending now"
        label_font = load_font(label, int(w * 0.029), "SemiBold", "ui")
        draw.text((margin, int(h * 0.10)), label, font=label_font, fill=SLATE)

        y = int(h * 0.145)
        self._dotted_rule(draw, margin, y, w - margin, w)

        y += int(h * 0.045)
        lines, font, line_height = fit_text(
            draw,
            brief.headline,
            box,
            int(h * 0.34),
            start=int(w * 0.085),
            minimum=int(w * 0.040),
            role=brief.font_role,
        )
        for line in lines:
            draw.text((margin, y), line, font=font, fill=INK)
            y += line_height

        if brief.subline:
            sub_font = load_font(brief.subline, int(w * 0.032), "Medium", "ui")
            y += int(h * 0.014)
            for line in wrap(draw, brief.subline, sub_font, box)[:2]:
                draw.text((margin, y), line, font=sub_font, fill=SLATE)
                y += int(w * 0.044)

        # The sparkline is the point of this template, so it gets real space.
        self._sparkline(
            draw,
            brief.velocity,
            left=margin,
            top=int(h * 0.60),
            width=box,
            height=int(h * 0.20),
        )

        self._footer(draw, brief, w, h, margin, ink=INK, rule=True, dotted=True)

    # ── shared furniture ──────────────────────────────────────────────────

    def _dotted_rule(self, draw, x0: int, y: int, x1: int, w: int) -> None:
        """The ladder's wire-feed cue, scaled to the canvas."""
        dot = max(2, int(w * 0.003))
        gap = dot * 2
        x = x0
        while x < x1:
            draw.rectangle([x, y, min(x + dot, x1), y + max(1, dot // 2)], fill=RULE)
            x += dot + gap

    def _sparkline(self, draw, series: list[float], *, left, top, width, height) -> None:
        """Velocity, drawn large and in chilli. Nothing when there is no series."""
        points = [float(v) for v in series or []]
        if len(points) < 2 or max(points) <= 0:
            return

        high = max(points)
        step = width / (len(points) - 1)
        coords = [
            (left + i * step, top + height - (v / high) * height) for i, v in enumerate(points)
        ]
        draw.line(coords, fill=CHILLI, width=max(4, int(width * 0.012)), joint="curve")

        # Mark "now", the same as the ladder does.
        x, y = coords[-1]
        r = max(6, int(width * 0.016))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=CHILLI)

    @staticmethod
    def _baseline(h: int) -> int:
        """Footer text baseline.

        Far enough up that a 29px line plus descenders still clears the 4%
        safe margin every platform crops into.
        """
        return h - int(h * 0.095)

    @staticmethod
    def _footer_top(h: int) -> int:
        """Where the footer begins. Nothing above it may be drawn past this."""
        return h - int(h * 0.095) - int(h * 0.030)

    def _footer(
        self,
        draw,
        brief: ImageBrief,
        w: int,
        h: int,
        margin: int,
        *,
        ink: str,
        rule: bool,
        dotted: bool = False,
    ) -> None:
        """Hashtags left, brand right.

        The brand is measured and drawn first so the hashtag line knows exactly
        how much room it has; drawing tags first let a long one run underneath
        the brand name. The brand block is the logo slot — an image is fetched
        here once logo_url is wired up.
        """
        baseline = self._baseline(h)

        brand_font = load_font(brief.brand_name, int(w * 0.028), "Bold", "ui")
        brand_width = text_width(draw, brief.brand_name, brand_font)
        draw.text((w - margin - brand_width, baseline), brief.brand_name, font=brand_font, fill=ink)

        available = w - margin * 2 - brand_width - int(w * 0.05)
        tag_font = load_font(" ".join(brief.hashtags) or "#", int(w * 0.029), "SemiBold", "ui")
        line = hashtag_line(draw, brief.hashtags, tag_font, available)
        if line:
            draw.text((margin, baseline), line, font=tag_font, fill=ink)

        if rule:
            rule_y = self._footer_top(h)
            if dotted:
                self._dotted_rule(draw, margin, rule_y, w - margin, w)
            else:
                draw.rectangle([margin, rule_y, w - margin, rule_y + 1], fill=ink)
