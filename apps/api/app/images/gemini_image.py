"""Optional Gemini background generator.

Interface-complete and inert. GEMINI_IMAGE_MODEL is blank because this key's
tier answers 429 on every image model (probed 2026-10-23), so
`is_configured()` is False and the caller renders the flat template instead.
Set the model id once image quota exists and it activates with no other change.

Per the spec it fails *silently* to the flat template — the user gets a post
either way — but never quietly: each fallback is logged with the reason.
"""

from __future__ import annotations

import base64

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.images.base import ImageBrief, ImageProvider, RenderedImage

log = get_logger("images.gemini")

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiImageProvider(ImageProvider):
    name = "gemini_image"

    def __init__(
        self,
        client: httpx.Client | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key if api_key is not None else settings.gemini_api_key
        self._model = model if model is not None else settings.gemini_image_model

    def is_configured(self) -> bool:
        # Both are required: a key with no model id means image generation was
        # deliberately left off, which is the current state.
        return bool(self._api_key and self._model)

    def background_prompt(self, brief: ImageBrief) -> str:
        """Backgrounds only — never text.

        A generated image with model-rendered words in it is unusable: the
        letterforms are wrong, Indic scripts especially, and the headline is
        drawn by Pillow on top anyway.
        """
        return (
            "Abstract editorial background for a social media post about "
            f"'{brief.headline}'. Flat shapes, generous empty space in the upper "
            f"half for a headline, dominant colour {brief.primary_color}. "
            "No text, no letters, no words, no logos, no watermarks, no people's faces."
        )

    def render(self, brief: ImageBrief) -> RenderedImage:
        if not self.is_configured():
            raise RuntimeError("gemini image generation is not configured")

        width, height = brief.dimensions
        client = self._client or httpx.Client(timeout=settings.gemini_timeout_seconds)
        try:
            response = client.post(
                f"{BASE_URL}/models/{self._model}:generateContent",
                params={"key": self._api_key},
                json={
                    "contents": [{"parts": [{"text": self.background_prompt(brief)}]}],
                    "generationConfig": {"responseModalities": ["IMAGE"]},
                },
            )
        finally:
            if self._client is None:
                client.close()

        if response.status_code != 200:
            raise RuntimeError(f"{self._model}: {response.status_code} {response.text[:200]}")

        parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            inline = part.get("inlineData")
            if inline and inline.get("data"):
                png = base64.b64decode(inline["data"])
                return RenderedImage(
                    png=png,
                    width=width,
                    height=height,
                    template="gemini-background",
                    size=brief.size,
                    meta={"alt_text": brief.alt_text, "model": self._model},
                )

        raise RuntimeError(f"{self._model}: response contained no image")
