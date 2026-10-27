"""OpenRouter, via its OpenAI-compatible API. Last in the spillover chain.

Third because it is the least proven, not the least useful: gemini -> groq ->
openrouter means two free tiers have to be spent before this one is asked,
and each has its own daily ceiling, so the chain survives an evening that any
one of them could not.

Like Gemini and unlike Groq it walks a model chain. OpenRouter's free ids are
withdrawn and renamed without notice, and a routed request can come back 429
from the upstream provider rather than from OpenRouter itself, so a single id
is a single point of failure in a way it is not on a first-party API.

The three defaults were measured rather than chosen. Asked for a two-cluster
curate-shaped array on 2026-10-28, of the seven free models declaring
response_format or structured_outputs:

  xingchen-agi/xing4.0-29b-a4b      2 items, platform_hashtags populated, 515 tokens
  nvidia/nemotron-3.5-super-vl      5 items for a request that asked for 2
  recursive/flint-v1.0              4 items, same problem
  dots-studio/dots-3-note-preview   HTTP 200 with an empty body
  google/gemma-4-31b-it             429 from the provider
  google/gemma-4-26b-a4b-it         429 from the provider
  liquid/lfm-2.5-2.6b               429 from the provider

Only the first honoured the count and filled the nested object, so it leads.
The two that miscount still return valid JSON and the curator drops a short
array per cluster rather than per batch, so they are useful behind it.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.base import (
    EmbedResult,
    JSONResult,
    LLMCall,
    LLMError,
    LLMProvider,
    ProviderBudget,
    RateLimited,
)
from app.llm.limiter import TokenBucket

log = get_logger("llm.openrouter")

BASE_URL = "https://openrouter.ai/api/v1"
MAX_ATTEMPTS = 3

#: /auth/key is a live HTTP call and /health is polled every ten seconds by
#: the compose healthcheck. Cached, or reporting the budget would cost
#: thousands of requests a day to read a number that moves slowly.
BUDGET_TTL_SECONDS = 300.0

#: And deliberately not the provider's 90s timeout. This call happens inside
#: /health, whose own healthcheck gives up after 5 seconds: a slow OpenRouter
#: would hang the endpoint, fail the healthcheck and get the api marked
#: unhealthy over a number that is only ever decoration. Three seconds, and
#: a miss reports null.
BUDGET_TIMEOUT_SECONDS = 3.0


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._key = api_key if api_key is not None else settings.openrouter_api_key
        self._chain = [model] if model else settings.openrouter_model_chain
        self._rpm = TokenBucket(settings.openrouter_rpm, 60.0, name="openrouter-rpm")
        self._budget: tuple[float, float | None] = (0.0, None)

    def is_configured(self) -> bool:
        # A key with no model chain cannot answer, and reporting it as
        # configured would put a dead provider in front of nothing.
        return bool(self._key and self._chain)

    async def budget(self) -> ProviderBudget:
        """What OpenRouter will say about the key.

        It meters money rather than calls, so `remaining_today` stays None —
        a request count would be an invented number — and the dollars go in
        `remaining_usd`. Null there means it could not be read, which is not
        the same as nothing left.
        """
        return ProviderBudget(
            name=self.name,
            configured=self.is_configured(),
            remaining_usd=await self._remaining_usd(),
            per_model=dict.fromkeys(self._chain, 0),
        )

    async def _remaining_usd(self) -> float | None:
        if not self.is_configured():
            return None
        cached_at, value = self._budget
        if value is not None and time.monotonic() - cached_at < BUDGET_TTL_SECONDS:
            return value

        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=BUDGET_TIMEOUT_SECONDS)
        try:
            response = await client.get(
                f"{BASE_URL}/auth/key",
                headers=self._headers(),
                timeout=BUDGET_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                return None
            data = (response.json() or {}).get("data") or {}
            budget = data.get("effective_budget") or {}
            remaining = budget.get("remaining_usd")
            if remaining is None:
                remaining = data.get("limit_remaining")
            value = float(remaining) if remaining is not None else None
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            log.info("budget unavailable", error=str(exc)[:120])
            return None
        finally:
            if own_client:
                await client.aclose()

        self._budget = (time.monotonic(), value)
        return value

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "content-type": "application/json",
            # Identification, not credentials: OpenRouter attributes the
            # request to these on the model's activity page.
            "HTTP-Referer": settings.openrouter_referer,
            "X-Title": settings.openrouter_title,
        }

    async def generate_json(
        self,
        *,
        prompt_id: str,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.3,
    ) -> JSONResult:
        if not self.is_configured():
            raise LLMError(
                "openrouter is not configured: OPENROUTER_API_KEY or OPENROUTER_MODEL is unset"
            )

        # json_object promises parseable JSON and nothing about its shape,
        # so the schema is restated in the system message — the same reason
        # as in the Groq provider.
        payload_messages = [
            {
                "role": "system",
                "content": (
                    "Return only JSON matching this schema. No prose, no code "
                    f"fences.\n{json.dumps(schema)}"
                ),
            },
            {"role": "user", "content": prompt},
        ]

        started = time.monotonic()
        last: Exception | None = None
        for model in self._chain:
            try:
                body, attempts = await self._post(model, payload_messages, temperature, prompt_id)
            except RateLimited as exc:
                last = exc
                log.warning("model rate limited, trying next", prompt_id=prompt_id, model=model)
                continue
            except LLMError as exc:
                # 404 means the id has been withdrawn, which is routine here.
                if "404" not in str(exc):
                    raise
                last = exc
                log.warning("model not served, trying next", prompt_id=prompt_id, model=model)
                continue

            text = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            try:
                data = json.loads(text)
            except ValueError as exc:
                # Not retried on the same model: a model that answers with
                # prose answers with prose again.
                last = LLMError(f"{prompt_id}: unparseable JSON from {model}")
                log.warning(
                    "unparseable answer, trying next",
                    prompt_id=prompt_id,
                    model=model,
                    error=str(exc)[:120],
                )
                continue

            usage = body.get("usage") or {}
            call = LLMCall(
                prompt_id=prompt_id,
                model=model,
                latency_ms=int((time.monotonic() - started) * 1000),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
                attempts=attempts,
                extra={"provider": self.name},
            )
            log.info(
                "llm call",
                provider=self.name,
                prompt_id=call.prompt_id,
                model=call.model,
                prompt_tokens=call.prompt_tokens,
                output_tokens=call.output_tokens,
                total_tokens=call.total_tokens,
                latency_ms=call.latency_ms,
                attempts=call.attempts,
            )
            return JSONResult(data=data, call=call)

        raise RateLimited(f"{prompt_id}: no model in {self._chain} answered ({last})") from last

    async def _post(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        prompt_id: str,
    ) -> tuple[dict[str, Any], int]:
        payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }

        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=settings.openrouter_timeout_seconds)
        try:
            last_error = ""
            for attempt in range(1, MAX_ATTEMPTS + 1):
                await self._rpm.acquire()
                try:
                    response = await client.post(
                        f"{BASE_URL}/chat/completions", headers=self._headers(), json=payload
                    )
                except httpx.HTTPError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt == MAX_ATTEMPTS:
                        raise LLMError(f"{prompt_id}: {last_error}") from exc
                    continue

                if response.status_code == 200:
                    return response.json(), attempt

                last_error = _message(response)
                if response.status_code == 429:
                    # Often the upstream provider rather than OpenRouter, and
                    # another model in the chain may route elsewhere.
                    raise RateLimited(f"{prompt_id}: {model} rate limited ({last_error})")
                if response.status_code >= 500 and attempt < MAX_ATTEMPTS:
                    continue
                raise LLMError(f"{prompt_id}: {response.status_code} {last_error}")
        finally:
            if own_client:
                await client.aclose()

        raise LLMError(f"{prompt_id}: exhausted {MAX_ATTEMPTS} attempts ({last_error})")

    async def embed(self, *, prompt_id: str, texts: list[str]) -> EmbedResult:
        """Refused, for the same reason Groq refuses.

        The curator's clusters are cosine distances inside one vector space.
        A second space in the same column does not weaken the grouping, it
        invalidates it.
        """
        raise LLMError("openrouter embeddings are not used; embeddings stay on Gemini")


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    error = (body or {}).get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)[:200]
    return str(error or body)[:200]
