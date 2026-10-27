"""The reel script: what is on the card and what is said over it.

The spoken half goes straight to a text-to-speech voice that reads exactly
what it is given, so most of what matters here is what never reaches it — a
hashtag read aloud is "hash Goa A I", and a URL is a minute of letters.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.llm.base import JSONResult, LLMCall, LLMError, LLMProvider
from app.video.script import (
    UNAVAILABLE,
    ReelScript,
    ScriptError,
    Segment,
    _speakable,
    derive_script,
    unusable_lines,
    write_script,
)

BRIEF: dict[str, Any] = {
    "brand_name": "Demo",
    "brand_voice": "Plain, confident.",
    "topic": "Goa unveils AI policy 2026",
    "summary": "The state announced an AI policy this week. A hackathon opens in November.",
    "region_name": "Goa",
    "evidence": "- [google_news] Goa unveils AI policy",
    "language": "english",
    "hashtags": ["#GoaAI"],
}

GOOD = {
    "headline": "Goa unveils AI policy 2026",
    "intro_say": "Goa has just published its first artificial intelligence policy this week.",
    "beats": [
        {
            "text": "Goa has an AI policy",
            "detail": "Announced this week",
            "say": "The state government signed off its artificial intelligence policy on Tuesday.",
        },
        {
            "text": "Two crore in prizes",
            "detail": "For student teams",
            "say": "There is a prize pool of two crore rupees for student teams who enter.",
        },
        {
            "text": "Applications close soon",
            "detail": "",
            "say": "Entries close on the thirtieth of November, so there are three weeks left.",
        },
    ],
    "outro_say": "That is the Goa artificial intelligence policy in under a minute.",
    "hashtags": ["#GoaAI", "#AIPolicy"],
    "alt_text": "A reel about the Goa AI policy.",
}


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, data: Any, *, configured: bool = True, raises: Exception | None = None):
        self.data = data
        self.configured = configured
        self.raises = raises
        self.calls: list[str] = []

    def is_configured(self) -> bool:
        return self.configured

    async def generate_json(self, *, prompt_id, prompt, schema, temperature=0.3) -> JSONResult:
        self.calls.append(prompt)
        if self.raises:
            raise self.raises
        call = LLMCall(prompt_id=prompt_id, model="x", latency_ms=1)
        return JSONResult(data=self.data, call=call)

    async def embed(self, *, prompt_id, texts):  # pragma: no cover - unused here
        raise NotImplementedError


class TestSpeakable:
    def test_a_hashtag_never_reaches_the_voice(self) -> None:
        """Read aloud it is "hash Goa A I", which is not a sentence."""
        assert _speakable("Goa has a policy #GoaAI #AIPolicy") == "Goa has a policy"

    def test_a_url_never_reaches_the_voice(self) -> None:
        assert _speakable("Read it at https://goa.gov.in/ai today") == "Read it at today"

    def test_emoji_and_markup_are_dropped(self) -> None:
        assert _speakable("Goa **has** an AI policy 🎉") == "Goa has an AI policy"

    def test_sentence_punctuation_survives(self) -> None:
        """Commas and full stops are what the voice phrases against."""
        assert _speakable("Goa, finally, has a policy.") == "Goa, finally, has a policy."

    def test_indian_digits_and_words_survive(self) -> None:
        assert _speakable("two crore rupees, or 2,00,00,000") == "two crore rupees, or 2,00,00,000"

    def test_devanagari_keeps_its_matras(self) -> None:
        """`str.isalnum()` is False for every combining mark, so filtering on
        it alone turns "जानना चाहते" into "जनन चहत" — not a typo but a
        different set of words, spoken aloud and burned into the captions."""
        said = _speakable("लोग यह जानना चाहते हैं कि कल तापमान कितना रहेगा")

        assert said == "लोग यह जानना चाहते हैं कि कल तापमान कितना रहेगा"

    def test_tamil_keeps_its_vowel_signs(self) -> None:
        said = _speakable("கோவா செயற்கை நுண்ணறிவு கொள்கை அறிமுகம்")

        assert said == "கோவா செயற்கை நுண்ணறிவு கொள்கை அறிமுகம்"

    def test_an_indic_line_survives_the_hashtag_strip(self) -> None:
        """Both rules run over the same string; one must not undo the other."""
        said = _speakable("गोवा में बारिश #GoaWeather https://imd.gov.in")

        assert said == "गोवा में बारिश"

    def test_it_is_cut_to_a_length_a_card_can_hold(self) -> None:
        said = _speakable(" ".join(["word"] * 60))

        assert len(said.split()) <= 28


class TestWriteScript:
    async def test_a_good_answer_becomes_a_script(self) -> None:
        script = await write_script(FakeLLM(GOOD), BRIEF)

        assert script.headline == "Goa unveils AI policy 2026"
        assert [s.kind for s in script.segments] == ["title", "beat", "beat", "beat", "outro"]
        assert script.derived is False
        assert script.hashtags == ["#GoaAI", "#AIPolicy"]

    async def test_every_card_has_something_to_say(self) -> None:
        """A card with no narration is a silent gap in the middle of a reel."""
        script = await write_script(FakeLLM(GOOD), BRIEF)

        assert all(segment.say.strip() for segment in script.segments)

    async def test_the_spoken_half_is_not_the_card_read_aloud(self) -> None:
        script = await write_script(FakeLLM(GOOD), BRIEF)

        for beat in script.beats:
            assert beat.say.lower() != beat.text.lower()

    async def test_the_topic_reaches_the_prompt(self) -> None:
        """The narration has to be about this topic, not a template."""
        llm = FakeLLM(GOOD)

        await write_script(llm, BRIEF)

        assert "Goa unveils AI policy 2026" in llm.calls[0]
        assert "Goa" in llm.calls[0]

    async def test_a_dropped_topic_is_refused_rather_than_narrated(self) -> None:
        with pytest.raises(ScriptError, match="do not market against"):
            await write_script(FakeLLM({"drop": True}), BRIEF)

    async def test_no_model_falls_back_without_calling_one(self) -> None:
        llm = FakeLLM(GOOD, configured=False)

        script = await write_script(llm, BRIEF)

        assert llm.calls == []
        assert script.derived is True

    async def test_beats_missing_their_spoken_half_are_dropped(self) -> None:
        broken = {
            **GOOD,
            "beats": [
                {"text": "Goa has an AI policy", "detail": "", "say": ""},
                *GOOD["beats"],
            ],
        }

        script = await write_script(FakeLLM(broken), BRIEF)

        assert len(script.beats) == 3
        assert all(beat.say for beat in script.beats)

    async def test_a_hashtag_in_the_spoken_field_is_stripped_not_narrated(self) -> None:
        noisy = {
            **GOOD,
            "intro_say": "Goa has an AI policy #GoaAI https://goa.gov.in",
        }

        script = await write_script(FakeLLM(noisy), BRIEF)

        assert script.segments[0].say == "Goa has an AI policy"


class TestUnusableLines:
    """A reel is a published file with a voice on it. A placeholder on a card
    is worse than no reel, because it looks finished."""

    def script_with(
        self, say: str = "A real spoken line.", text: str = "Real line", detail: str = ""
    ) -> ReelScript:
        return ReelScript(
            headline="Goa unveils AI policy",
            segments=[
                Segment(kind="title", say="Here is what is trending."),
                Segment(kind="beat", say=say, text=text, detail=detail),
            ],
        )

    def test_the_no_summary_stand_in_is_caught(self) -> None:
        """The exact line that reached a card and a voiceover: an instruction
        to the writer that arrived looking like content."""
        bad = unusable_lines(
            self.script_with(say="No summary available; work from the headlines below.")
        )

        assert bad
        assert "No summary available" in bad[0]

    def test_it_is_caught_on_the_card_as_well_as_in_the_voice(self) -> None:
        assert unusable_lines(
            self.script_with(text="No summary available; work from the headlines below.")
        )

    @pytest.mark.parametrize(
        "line",
        [
            "No summary available; work from the headlines below.",
            "(none)",
            "Lorem ipsum dolor sit amet.",
            "PLACEHOLDER — replace this.",
            "N/A",
            "TBD",
        ],
    )
    def test_placeholders_are_refused(self, line: str) -> None:
        assert unusable_lines(self.script_with(say=line))

    @pytest.mark.parametrize(
        "line",
        [
            "Write one sentence about the topic.",
            "Generate a caption for this reel.",
            "As an AI language model, I cannot.",
            "Here is the JSON you asked for.",
        ],
    )
    def test_instructions_are_refused(self, line: str) -> None:
        assert unusable_lines(self.script_with(say=line))

    def test_an_empty_spoken_line_is_refused(self) -> None:
        """A card with nothing said over it is a silent gap mid-reel."""
        assert unusable_lines(self.script_with(say="   "))

    def test_an_empty_card_line_is_refused(self) -> None:
        assert unusable_lines(self.script_with(text=""))

    def test_an_empty_detail_is_allowed(self) -> None:
        """Not every beat has a second line, and most should not."""
        assert unusable_lines(self.script_with(detail="")) == []

    def test_a_clean_script_passes(self) -> None:
        assert unusable_lines(self.script_with()) == []

    def test_a_topic_that_mentions_a_summary_is_not_a_placeholder(self) -> None:
        """ "Summary" is an ordinary word; only the stand-in phrasing is not."""
        assert unusable_lines(self.script_with(say="The court summary runs to forty pages.")) == []


class TestWriterFailureFailsTheJob:
    async def test_an_outage_fails_rather_than_deriving(self) -> None:
        """A derived reel is not a lesser version of the same thing — it is a
        different, worse thing with the brand's name in the corner."""
        with pytest.raises(ScriptError, match=re.escape(UNAVAILABLE)):
            await write_script(FakeLLM(None, raises=LLMError("503")), BRIEF)

    async def test_a_thin_answer_fails(self) -> None:
        thin = {**GOOD, "beats": GOOD["beats"][:1]}

        with pytest.raises(ScriptError, match="Script unavailable"):
            await write_script(FakeLLM(thin), BRIEF)

    async def test_a_model_answer_carrying_a_placeholder_is_refused(self) -> None:
        leaked = {
            **GOOD,
            "intro_say": "No summary available; work from the headlines below.",
        }

        with pytest.raises(ScriptError, match="Script unavailable"):
            await write_script(FakeLLM(leaked), BRIEF)

    async def test_a_derived_script_with_no_summary_is_refused(self) -> None:
        """The case that produced the bug: no summary, so nothing real to
        derive from."""
        with pytest.raises(ScriptError, match="Script unavailable"):
            await write_script(FakeLLM(GOOD, configured=False), {**BRIEF, "summary": ""})

    async def test_a_derived_script_with_a_real_summary_still_renders(self) -> None:
        script = await write_script(FakeLLM(GOOD, configured=False), BRIEF)

        assert script.derived is True
        assert unusable_lines(script) == []


class TestDerivedScript:
    def test_the_summary_becomes_the_beats(self) -> None:
        script = derive_script(BRIEF)

        assert script.derived is True
        assert len(script.beats) == 2
        assert "announced an AI policy" in script.beats[0].say

    def test_it_says_where_the_topic_is_trending(self) -> None:
        assert "Goa" in derive_script(BRIEF).segments[0].say

    def test_a_topic_with_no_summary_derives_nothing_to_say(self) -> None:
        """There is no content to derive from, so it produces no beats rather
        than a card repeating the search term back at the viewer."""
        script = derive_script({**BRIEF, "summary": ""})

        assert script.beats == []

    def test_the_card_is_shorter_than_the_line_it_is_spoken_with(self) -> None:
        """The card is read in two seconds; the voice has longer."""
        script = derive_script(BRIEF)

        for beat in script.beats:
            assert len(beat.text.split()) <= 6
            assert len(beat.say.split()) >= len(beat.text.split())
