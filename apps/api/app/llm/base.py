"""The LLMProvider interface.

Same contract as TrendSource: `is_configured()` is checked before a provider
is called, and a provider raises rather than returning junk. Callers decide
whether a failure is fatal — the curator degrades to the non-LLM merge, the
writer marks the job failed.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    """Any provider failure the caller is expected to handle."""


class RateLimited(LLMError):
    """Budget exhausted — retrying sooner will not help."""


@dataclass(slots=True)
class LLMCall:
    """What one call cost. Logged for every request, per CLAUDE.md."""

    prompt_id: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    attempts: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JSONResult:
    data: Any
    call: LLMCall


@dataclass(slots=True)
class EmbedResult:
    #: One vector per input, in input order.
    vectors: list[list[float]]
    call: LLMCall


class LLMProvider(abc.ABC):
    """Text generation and embeddings behind one interface."""

    name: str

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """False => callers skip this provider, logging why."""

    @abc.abstractmethod
    async def generate_json(
        self,
        *,
        prompt_id: str,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.3,
    ) -> JSONResult:
        """Return parsed JSON conforming to `schema`. Raise LLMError on failure."""

    @abc.abstractmethod
    async def embed(self, *, prompt_id: str, texts: list[str]) -> EmbedResult:
        """Return one vector per text, in order."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} configured={self.is_configured()}>"
