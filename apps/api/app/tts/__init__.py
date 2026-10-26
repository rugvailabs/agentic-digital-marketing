"""Text-to-speech registry."""

from app.tts.base import DEFAULT_VOICE, VOICES, Speech, TTSProvider, voice_for

__all__ = [
    "DEFAULT_VOICE",
    "VOICES",
    "Speech",
    "TTSProvider",
    "voice_for",
]
