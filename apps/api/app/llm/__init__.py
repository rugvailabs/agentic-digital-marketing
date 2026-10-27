"""LLM provider registry. Nothing outside this package constructs a provider."""

from app.llm.base import (
    EmbedResult,
    JSONResult,
    LLMCall,
    LLMError,
    LLMProvider,
    RateLimited,
)
from app.llm.gemini import GeminiProvider
from app.llm.groq import GroqProvider
from app.llm.spillover import SpilloverProvider

__all__ = [
    "EmbedResult",
    "GeminiProvider",
    "GroqProvider",
    "JSONResult",
    "LLMCall",
    "LLMError",
    "LLMProvider",
    "RateLimited",
    "SpilloverProvider",
    "get_llm",
]

_provider: LLMProvider | None = None


def get_llm() -> LLMProvider:
    """The configured provider. Cached: the rate-limit buckets are per
    instance, so a fresh provider per call would hand every caller a full
    budget.

    Gemini primary, Groq as spillover when Gemini's daily budget is gone.
    Callers never pick — they ask for JSON and the wrapper decides, logging
    which one answered.
    """
    global _provider
    if _provider is None:
        _provider = SpilloverProvider(GeminiProvider(), GroqProvider())
    return _provider
