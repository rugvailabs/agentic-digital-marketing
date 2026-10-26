"""The TTSProvider interface.

The voiceover decides the reel's length, so this runs before the video: TTS
first, measure, then render exactly that many frames. Doing it the other way
round means either a clipped sentence or silence at the end.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from app.models import Language

#: Microsoft Neural voices, one per language we write in. en-IN and hi-IN are
#: the two that matter most for this audience; the rest are the regional
#: voices for the scripts CLAUDE.md requires us to render.
VOICES: dict[Language, str] = {
    Language.english: "en-IN-NeerjaNeural",
    # Hinglish is Hindi written in Latin script, so it is read by the Hindi
    # voice: the vocabulary and the stress patterns are Hindi, and an English
    # voice reads "scenes hi alag hai" as English words.
    Language.hinglish: "hi-IN-SwaraNeural",
    Language.hindi: "hi-IN-SwaraNeural",
    Language.tamil: "ta-IN-PallaviNeural",
    Language.telugu: "te-IN-ShrutiNeural",
    Language.bengali: "bn-IN-TanishaaNeural",
    Language.marathi: "mr-IN-AarohiNeural",
}

DEFAULT_VOICE = VOICES[Language.english]


def voice_for(language: Language | str) -> str:
    try:
        return VOICES[Language(language)]
    except (ValueError, KeyError):
        return DEFAULT_VOICE


@dataclass(slots=True)
class Boundary:
    """One span of narration the provider timed, relative to its own audio."""

    start: float
    seconds: float
    text: str

    @property
    def end(self) -> float:
        return self.start + self.seconds


@dataclass(slots=True)
class Speech:
    """One rendered voiceover."""

    audio: bytes
    #: "mp3" | "wav". Whatever the provider actually produced.
    format: str
    duration_seconds: float
    voice: str
    #: One entry per boundary the provider reports, in order.
    #:
    #: The granularity is the provider's choice, not ours: edge-tts 7 reports
    #: one SentenceBoundary per sentence where older versions reported a
    #: WordBoundary per word. These are what the burned-in captions are cut
    #: from, so a provider that reports nothing means a reel with no captions
    #: rather than a broken one.
    boundaries: list[Boundary] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class TTSProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """False => the caller renders a silent video and says so."""

    @abc.abstractmethod
    async def speak(self, text: str, language: Language) -> Speech:
        """Narrate `text`. Raise on failure; the caller decides what to do."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} configured={self.is_configured()}>"
