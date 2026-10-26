"""Narration first, then frames.

The voice decides how long a reel is. Each card is narrated on its own, the
audio is measured, and that measurement becomes the card's length — so the
visuals are in step with the narration by construction rather than by
stretching one to fit the other afterwards.

Doing it the other way round gives you a choice between a clipped last word
and a held frame at the end, and both read as a broken render.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.logging import get_logger
from app.models import Language
from app.tts.base import Speech, TTSProvider
from app.video.base import FPS, MAX_DURATION_SECONDS, Beat, VideoBrief
from app.video.script import ReelScript, Segment

log = get_logger("video.timing")

#: Held after the voice stops, before the cut. Without it the edit lands on
#: the last syllable, which sounds like the file was truncated.
PAD_SECONDS = 0.38
#: No card is shorter than this however short its line, or the reel flickers.
MIN_CARD_SECONDS = 1.5


@dataclass(slots=True)
class NarratedCard:
    segment: Segment
    speech: Speech
    frames: int
    start_frame: int

    @property
    def seconds(self) -> float:
        return self.frames / FPS

    @property
    def start_seconds(self) -> float:
        return self.start_frame / FPS

    @property
    def gap_seconds(self) -> float:
        """Silence between the end of this line and the cut."""
        return max(0.0, self.seconds - self.speech.duration_seconds)


@dataclass(slots=True)
class Narration:
    cards: list[NarratedCard]
    voice: str

    @property
    def total_frames(self) -> int:
        return sum(card.frames for card in self.cards)

    @property
    def duration_seconds(self) -> float:
        return self.total_frames / FPS

    def of_kind(self, kind: str) -> list[NarratedCard]:
        return [card for card in self.cards if card.segment.kind == kind]


def card_frames(seconds: float) -> int:
    """How long a card holds for a line of `seconds` of narration."""
    padded = max(MIN_CARD_SECONDS, seconds + PAD_SECONDS)
    return max(1, math.ceil(padded * FPS))


async def narrate(tts: TTSProvider, script: ReelScript, language: Language) -> Narration:
    """Narrate every card and lay them out on the timeline.

    Sequential rather than concurrent on purpose: this is an unofficial
    endpoint and five simultaneous connections is how a free service decides
    it does not like you.
    """
    cards: list[NarratedCard] = []
    cursor = 0

    for segment in script.segments:
        speech = await tts.speak(segment.say, language)
        frames = card_frames(speech.duration_seconds)
        cards.append(
            NarratedCard(segment=segment, speech=speech, frames=frames, start_frame=cursor)
        )
        cursor += frames

    narration = Narration(cards=cards, voice=cards[0].speech.voice if cards else "")
    log.info(
        "reel narrated",
        cards=len(cards),
        seconds=round(narration.duration_seconds, 2),
        voice=narration.voice,
    )
    return narration


def brief_from(
    script: ReelScript,
    narration: Narration,
    *,
    brand_name: str,
    primary_color: str,
    secondary_color: str,
    size: str = "reel",
    region_name: str = "",
    velocity: list[float] | None = None,
    script_name: str = "LATIN",
    logo_url: str | None = None,
) -> VideoBrief:
    """Build the render brief with every card's measured length on it."""
    total = narration.duration_seconds
    if total > MAX_DURATION_SECONDS:
        raise ValueError(
            f"The narration runs to {total:.0f}s, past the {MAX_DURATION_SECONDS:.0f}s a reel "
            "may be. Shorten the script."
        )

    beats = [
        Beat(text=card.segment.text, seconds=card.seconds, detail=card.segment.detail)
        for card in narration.of_kind("beat")
    ]
    title = narration.of_kind("title")
    outro = narration.of_kind("outro")

    return VideoBrief(
        headline=script.headline,
        beats=beats,
        brand_name=brand_name,
        primary_color=primary_color,
        secondary_color=secondary_color,
        size=size,
        logo_url=logo_url,
        region_name=region_name,
        hashtags=list(script.hashtags),
        velocity=list(velocity or []),
        script=script_name,
        alt_text=script.alt_text,
        # The opening and closing cards are narrated too, so their lengths are
        # measured the same way rather than left as constants the renderer
        # happens to agree with.
        title_seconds=title[0].seconds if title else None,
        outro_seconds=outro[0].seconds if outro else None,
    )
