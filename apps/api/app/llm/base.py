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


@dataclass(slots=True)
class ProviderBudget:
    """What one provider is, and how much of today it has left.

    `/health` renders a list of these so the state of the writing half of the
    app is answerable without reading logs: which vendor is wired up, and
    whether there is anything left to spend on it.
    """

    name: str
    configured: bool
    #: Calls left today. None where this provider's day is not metered here —
    #: an absent number and a zero mean opposite things and must not share a
    #: representation.
    remaining_today: int | None = None
    #: Per model id, because a free-tier day can be counted per model rather
    #: than per key, and then one exhausted model is not an exhausted vendor.
    per_model: dict[str, int] = field(default_factory=dict)


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

    async def budget(self) -> ProviderBudget:
        """This provider's own name, wiring and remaining day.

        The default reports no daily figure, which is the honest answer for a
        provider that does not meter one. Override where there is a real
        number to give.
        """
        return ProviderBudget(name=self.name, configured=self.is_configured())

    async def statuses(self) -> list[ProviderBudget]:
        """Every provider reachable through this one, in the order tried.

        A list rather than a single entry so that a wrapper standing in front
        of two vendors reports both, and /health does not have to know which
        kind of provider it is holding.
        """
        return [await self.budget()]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} configured={self.is_configured()}>"
