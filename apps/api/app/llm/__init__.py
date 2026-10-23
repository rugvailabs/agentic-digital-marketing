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

__all__ = [
    "EmbedResult",
    "GeminiProvider",
    "JSONResult",
    "LLMCall",
    "LLMError",
    "LLMProvider",
    "RateLimited",
    "get_llm",
]

_provider: LLMProvider | None = None


def get_llm() -> LLMProvider:
    """The configured provider. Cached: the rate-limit buckets are per instance,
    so a fresh provider per call would hand every caller a full budget."""
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider
