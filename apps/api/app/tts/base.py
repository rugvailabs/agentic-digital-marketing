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
    # Hinglish is written in Latin script with Hindi words, which the Indian
    # English voice reads far better than the Hindi one does.
    Language.hinglish: "en-IN-NeerjaNeural",
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
class Speech:
    """One rendered voiceover."""

    audio: bytes
    #: "mp3" | "wav". Whatever the provider actually produced.
    format: str
    duration_seconds: float
    voice: str
    #: Per-word timings where the provider reports them, so beats can be cut
    #: to the narration instead of to a guess.
    word_boundaries: list[tuple[float, str]] = field(default_factory=list)
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
