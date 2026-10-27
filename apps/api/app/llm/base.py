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
    #: Calls spent today, where there is a count to spend. The counterpart
    #: of remaining_today: a board shows what is gone more usefully than
    #: what is left when the limit itself is the thing worth knowing.
    used_today: int | None = None
    #: Of the day's calls, how many are held back for the Desk. Scheduled
    #: work stops this far short, so remaining_today dropping to this number
    #: means curation has stopped and a user can still generate a post.
    reserved_for_desk: int | None = None
    #: Money left, where the vendor meters money rather than calls — which
    #: OpenRouter does. Separate from `remaining_today` rather than squeezed
    #: into it: dollars and requests are not the same quantity, and showing
    #: "100" under a column of request counts would read as 100 calls.
    remaining_usd: float | None = None


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
