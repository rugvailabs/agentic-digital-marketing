"""The reel script: what is on the card and what is said over it.

The spoken half goes straight to a text-to-speech voice that reads exactly
what it is given, so most of what matters here is what never reaches it — a
hashtag read aloud is "hash Goa A I", and a URL is a minute of letters.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.llm.base import JSONResult, LLMCall, LLMError, LLMProvider
from app.video.script import ScriptError, _speakable, derive_script, write_script

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

    async def test_an_outage_falls_back_to_the_topic(self) -> None:
        script = await write_script(FakeLLM(None, raises=LLMError("503")), BRIEF)

        assert script.derived is True
        assert script.headline == BRIEF["topic"]
        assert script.segments

    async def test_no_model_falls_back_without_calling_one(self) -> None:
        llm = FakeLLM(GOOD, configured=False)

        script = await write_script(llm, BRIEF)

        assert llm.calls == []
        assert script.derived is True

    async def test_a_thin_answer_falls_back(self) -> None:
        """One beat is not a reel, and half a script is worse than none."""
        thin = {**GOOD, "beats": GOOD["beats"][:1]}

        script = await write_script(FakeLLM(thin), BRIEF)

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


class TestDerivedScript:
    def test_the_summary_becomes_the_beats(self) -> None:
        script = derive_script(BRIEF)

        assert script.derived is True
        assert len(script.beats) == 2
        assert "announced an AI policy" in script.beats[0].say

    def test_it_says_where_the_topic_is_trending(self) -> None:
        assert "Goa" in derive_script(BRIEF).segments[0].say

    def test_a_topic_with_no_summary_still_produces_a_reel(self) -> None:
        script = derive_script({**BRIEF, "summary": ""})

        assert script.beats
        assert all(segment.say for segment in script.segments)

    def test_the_card_is_shorter_than_the_line_it_is_spoken_with(self) -> None:
        """The card is read in two seconds; the voice has longer."""
        script = derive_script(BRIEF)

        for beat in script.beats:
            assert len(beat.text.split()) <= 6
            assert len(beat.say.split()) >= len(beat.text.split())
