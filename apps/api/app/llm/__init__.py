"""LLM provider registry. Nothing outside this package constructs a provider."""

from app.llm.base import (
    EmbedResult,
    JSONResult,
    LLMCall,
    LLMError,
    LLMProvider,
    ProviderBudget,
    RateLimited,
)
from app.llm.gemini import GeminiProvider
from app.llm.groq import GroqProvider
from app.llm.openrouter import OpenRouterProvider
from app.llm.spillover import SpilloverProvider

__all__ = [
    "EmbedResult",
    "GeminiProvider",
    "GroqProvider",
    "JSONResult",
    "LLMCall",
    "LLMError",
    "LLMProvider",
    "OpenRouterProvider",
    "ProviderBudget",
    "RateLimited",
    "SpilloverProvider",
    "get_llm",
]

_provider: LLMProvider | None = None


def get_llm() -> LLMProvider:
    """The configured provider. Cached: the rate-limit buckets are per
    instance, so a fresh provider per call would hand every caller a full
    budget.

    Gemini primary, then Groq, then OpenRouter. Callers never pick — they
    ask for JSON and the wrapper decides, logging which one answered.
    """
    global _provider
    if _provider is None:
        # gemini -> groq -> openrouter, nested so each standby is itself a
        # chain. SpilloverProvider takes two, and three free tiers in a row
        # is the point: each has its own daily ceiling, so an evening that
        # exhausts one need not stop the desk.
        _provider = SpilloverProvider(
            GeminiProvider(),
            SpilloverProvider(GroqProvider(), OpenRouterProvider()),
        )
    return _provider
