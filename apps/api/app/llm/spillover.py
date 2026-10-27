"""Gemini first, Groq when Gemini has nothing left.

One provider from the caller's side. The curator and the writers ask for
JSON and do not choose a vendor; this decides, and logs which one answered so
the choice is visible afterwards rather than inferred from token counts.

Spillover is narrow on purpose. It happens on `RateLimited` and nothing else:
that is the exception Gemini raises when every model in its chain has spent
its daily budget, which is a condition no retry fixes and the free tier
reaches most days. An ordinary error — a bad prompt, a 500, a malformed
response — is not a reason to go and ask someone else the same question.

Embeddings never spill over. Groq has no embedding model, and the curator's
clusters are cosine distances inside one vector space: mixing two models
would not weaken the grouping, it would make it meaningless.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.llm.base import EmbedResult, JSONResult, LLMError, LLMProvider, RateLimited

log = get_logger("llm.spillover")


class SpilloverProvider(LLMProvider):
    name = "spillover"

    def __init__(self, primary: LLMProvider, standby: LLMProvider) -> None:
        self.primary = primary
        self.standby = standby

    def is_configured(self) -> bool:
        return self.primary.is_configured() or self.standby.is_configured()

    async def generate_json(
        self,
        *,
        prompt_id: str,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.3,
    ) -> JSONResult:
        if self.primary.is_configured():
            try:
                return await self.primary.generate_json(
                    prompt_id=prompt_id, prompt=prompt, schema=schema, temperature=temperature
                )
            except RateLimited as exhausted:
                if not self.standby.is_configured():
                    raise
                log.warning(
                    "primary exhausted, spilling over",
                    prompt_id=prompt_id,
                    primary=self.primary.name,
                    standby=self.standby.name,
                    reason=str(exhausted)[:160],
                )
            # Any other LLMError propagates: a bad prompt does not become a
            # good one by being sent somewhere else.
        elif not self.standby.is_configured():
            raise LLMError("no LLM provider is configured")

        return await self.standby.generate_json(
            prompt_id=prompt_id, prompt=prompt, schema=schema, temperature=temperature
        )

    async def embed(self, *, prompt_id: str, texts: list[str]) -> EmbedResult:
        """Primary only. See the note at the top of this module."""
        return await self.primary.embed(prompt_id=prompt_id, texts=texts)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<SpilloverProvider {self.primary.name}"
            f"->{self.standby.name} configured={self.is_configured()}>"
        )
