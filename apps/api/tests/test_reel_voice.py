"""Voice resolution.

Microsoft retires voice ids without notice, and a retired id does not fail
loudly — it is simply not found. The failure that matters is a Tamil reel
narrated in English with nothing in the logs saying so, which is what these
exist to prevent.
"""

from __future__ import annotations

import pytest

import app.tts.edge as edge
from app.models import Language
from app.tts.base import DEFAULT_VOICE, VOICES, voice_for


@pytest.fixture(autouse=True)
def _clear_cache():
    """The voice list is module state; without this one test decides the
    answer for every later one."""
    edge._known = None
    yield
    edge._known = None


class TestResolveVoice:
    async def test_a_known_voice_is_used(self, monkeypatch) -> None:
        monkeypatch.setattr(edge, "known_voices", listing_set({"ta-IN-PallaviNeural"}))

        assert await edge.resolve_voice(Language.tamil) == "ta-IN-PallaviNeural"

    async def test_a_retired_voice_falls_back_to_english(self, monkeypatch) -> None:
        monkeypatch.setattr(edge, "known_voices", listing_set({"en-IN-NeerjaNeural"}))

        assert await edge.resolve_voice(Language.tamil) == DEFAULT_VOICE

    async def test_an_unavailable_list_changes_nothing(self, monkeypatch) -> None:
        """Could not ask is not the same as not there. Downgrading everyone to
        English because the listing endpoint was down would be worse than the
        problem it is guarding against."""
        monkeypatch.setattr(edge, "known_voices", listing_set(None))

        assert await edge.resolve_voice(Language.tamil) == VOICES[Language.tamil]

    async def test_hinglish_resolves_to_the_hindi_voice(self, monkeypatch) -> None:
        monkeypatch.setattr(edge, "known_voices", listing_set({"hi-IN-SwaraNeural"}))

        assert await edge.resolve_voice(Language.hinglish) == "hi-IN-SwaraNeural"


def listing_set(names: set[str] | None):
    async def _known() -> frozenset[str] | None:
        return None if names is None else frozenset(names)

    return _known


class TestKnownVoices:
    async def test_the_list_is_fetched_once(self, monkeypatch) -> None:
        calls = 0

        async def _list():
            nonlocal calls
            calls += 1
            return [{"ShortName": "en-IN-NeerjaNeural"}]

        monkeypatch.setattr(edge, "_fetch_voices", _list, raising=False)

        first = await edge.known_voices()
        second = await edge.known_voices()

        assert first == second == frozenset({"en-IN-NeerjaNeural"})
        assert calls == 1, "the voice list does not change inside one process"

    async def test_a_failure_is_reported_as_unknown_not_as_empty(self, monkeypatch) -> None:
        """An empty set would mean every voice is missing, which would send
        every language to the English fallback."""

        async def _boom():
            raise RuntimeError("offline")

        monkeypatch.setattr(edge, "_fetch_voices", _boom, raising=False)

        assert await edge.known_voices() is None


class TestVoiceTable:
    def test_every_language_maps_to_an_indian_locale(self) -> None:
        assert set(VOICES) == set(Language)
        assert all(voice.split("-")[1] == "IN" for voice in VOICES.values())

    def test_an_unknown_language_still_gets_a_voice(self) -> None:
        assert voice_for("klingon") == DEFAULT_VOICE
