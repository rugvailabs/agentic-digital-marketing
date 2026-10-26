"""The voice decides the length.

These are the tests that the picture and the narration stay in step. The
failure they exist to catch is silent in every other sense: a reel whose
cards are a little shorter than the lines spoken over them plays fine, sounds
fine for the first card, and has the voice a beat behind the picture by the
end.
"""

from __future__ import annotations

import pytest

from app.models import Language
from app.tts.base import Speech, TTSProvider
from app.video.base import FPS, MAX_DURATION_SECONDS
from app.video.script import ReelScript, Segment
from app.video.timing import (
    MIN_CARD_SECONDS,
    PAD_SECONDS,
    brief_from,
    card_frames,
    narrate,
)


class FakeTTS(TTSProvider):
    """Returns a fixed duration per line, so timing is arithmetic not luck."""

    name = "fake"

    def __init__(self, seconds: list[float] | float = 2.0, *, configured: bool = True):
        self.seconds = seconds
        self.configured = configured
        self.said: list[str] = []

    def is_configured(self) -> bool:
        return self.configured

    async def speak(self, text: str, language: Language) -> Speech:
        self.said.append(text)
        if isinstance(self.seconds, list):
            seconds = self.seconds[min(len(self.said) - 1, len(self.seconds) - 1)]
        else:
            seconds = self.seconds
        return Speech(
            audio=b"\xff\xfb" + bytes(64),
            format="mp3",
            duration_seconds=seconds,
            voice="en-IN-NeerjaNeural",
        )


def script(beats: int = 3, *, outro: bool = True) -> ReelScript:
    segments = [Segment(kind="title", say="Here is what is trending in Goa today.")]
    for i in range(beats):
        segments.append(
            Segment(kind="beat", text=f"Beat {i + 1}", detail="Detail", say=f"Line {i + 1} spoken.")
        )
    if outro:
        segments.append(Segment(kind="outro", say="That is the story."))
    return ReelScript(headline="Goa unveils AI policy 2026", segments=segments)


class TestCardFrames:
    def test_a_card_outlasts_its_line(self) -> None:
        """The cut must not land on the last syllable."""
        assert card_frames(2.0) > round(2.0 * FPS)

    def test_the_pad_is_what_makes_the_difference(self) -> None:
        import math

        assert card_frames(3.0) == math.ceil((3.0 + PAD_SECONDS) * FPS)

    def test_a_very_short_line_still_holds_long_enough_to_read(self) -> None:
        assert card_frames(0.2) == round(MIN_CARD_SECONDS * FPS)

    def test_frames_are_whole(self) -> None:
        assert card_frames(2.345) == int(card_frames(2.345))


class TestNarrate:
    async def test_every_segment_is_narrated_once(self) -> None:
        tts = FakeTTS()

        narration = await narrate(tts, script(), Language.english)

        assert len(tts.said) == 5
        assert len(narration.cards) == 5

    async def test_the_spoken_line_is_what_is_sent_to_the_voice(self) -> None:
        tts = FakeTTS()

        await narrate(tts, script(), Language.english)

        assert tts.said[1] == "Line 1 spoken."

    async def test_cards_are_laid_end_to_end_with_no_gap(self) -> None:
        """A gap between cards is a gap in the narration."""
        narration = await narrate(FakeTTS([1.0, 2.0, 3.0, 4.0, 5.0]), script(), Language.english)

        cursor = 0
        for card in narration.cards:
            assert card.start_frame == cursor
            cursor += card.frames
        assert cursor == narration.total_frames

    async def test_each_card_is_long_enough_for_its_own_line(self) -> None:
        narration = await narrate(FakeTTS([1.0, 4.0, 2.5, 0.4, 3.0]), script(), Language.english)

        for card in narration.cards:
            assert card.seconds >= card.speech.duration_seconds

    async def test_the_leftover_silence_is_reported_per_card(self) -> None:
        """The mix pads each line out by exactly this much."""
        narration = await narrate(FakeTTS(2.0), script(), Language.english)

        for card in narration.cards:
            assert card.gap_seconds == pytest.approx(card.seconds - 2.0, abs=0.001)
            assert card.gap_seconds >= 0

    async def test_a_longer_line_makes_a_longer_reel(self) -> None:
        short = await narrate(FakeTTS(1.5), script(), Language.english)
        long = await narrate(FakeTTS(4.0), script(), Language.english)

        assert long.duration_seconds > short.duration_seconds

    async def test_the_voice_is_recorded(self) -> None:
        narration = await narrate(FakeTTS(), script(), Language.english)

        assert narration.voice == "en-IN-NeerjaNeural"


class TestBriefFromNarration:
    def brief(self, narration):
        return brief_from(
            ReelScript(headline="Goa unveils AI policy 2026", segments=[]),
            narration,
            brand_name="Demo",
            primary_color="#1B2230",
            secondary_color="#D8322B",
            region_name="Goa",
        )

    async def test_the_render_is_exactly_as_long_as_the_narration(self) -> None:
        """This is the whole point: no stretching either way."""
        narration = await narrate(FakeTTS([1.2, 3.4, 2.1, 2.8, 1.6]), script(), Language.english)

        brief = self.brief(narration)

        assert brief.duration_in_frames == narration.total_frames

    async def test_every_card_keeps_its_own_measured_length(self) -> None:
        narration = await narrate(FakeTTS([1.2, 3.4, 2.1, 2.8, 1.6]), script(), Language.english)

        brief = self.brief(narration)

        assert brief.title_frames == narration.of_kind("title")[0].frames
        assert brief.outro_frames == narration.of_kind("outro")[0].frames
        assert [b.frames for b in brief.beats] == [c.frames for c in narration.of_kind("beat")]

    async def test_the_props_the_renderer_gets_agree_with_the_audio(self) -> None:
        """The renderer is a separate process; this is the number it uses."""
        narration = await narrate(FakeTTS([1.2, 3.4, 2.1, 2.8, 1.6]), script(), Language.english)

        props = self.brief(narration).as_props()

        assert props["durationInFrames"] == narration.total_frames
        assert (
            props["titleFrames"] + sum(b["frames"] for b in props["beats"]) + props["outroFrames"]
            == narration.total_frames
        )

    async def test_a_reel_with_no_closing_card_still_adds_up(self) -> None:
        narration = await narrate(FakeTTS(2.0), script(outro=False), Language.english)

        brief = self.brief(narration)

        # No outro narrated, so the composition falls back to its default
        # closing length and the total has to include it.
        assert brief.duration_in_frames == narration.total_frames + brief.outro_frames

    async def test_a_script_too_long_for_a_reel_is_refused(self) -> None:
        """Clipping it would strand the last sentence mid-word."""
        narration = await narrate(FakeTTS(19.0), script(), Language.english)

        with pytest.raises(ValueError, match="past the"):
            self.brief(narration)

        assert narration.duration_seconds > MAX_DURATION_SECONDS
