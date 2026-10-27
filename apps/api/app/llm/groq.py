"""Groq, as spillover when Gemini has nothing left.

Gemini stays primary: it is what the prompts were written against and what
the curator's embeddings come from. This exists for the one failure the free
tier guarantees — every model in the chain having spent its twenty calls for
the day — where the alternative is a studio that stops working until
midnight UTC.

Groq serves an OpenAI-shaped API, so this is a different request body and the
same contract. It has no embedding model, which is why `embed()` refuses
rather than pretending: the curator's vectors have to come from one model or
the clusters are meaningless.
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

log = get_logger("llm.groq")

BASE_URL = "https://api.groq.com/openai/v1"
#: Retried on; anything else is reported as-is.
RETRY_STATUS = {429, 500, 502, 503, 529}
MAX_ATTEMPTS = 3


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._key = settings.groq_api_key if api_key is None else api_key
        self._model = settings.groq_model if model is None else model
        self._rpm = TokenBucket(settings.groq_rpm, 60.0, name="groq-rpm")
        #: The limit that actually bites — see settings.groq_tpm.
        self._tpm = TokenBucket(settings.groq_tpm, 60.0, name="groq-tpm")

    def is_configured(self) -> bool:
        return bool(self._key)

    async def budget(self) -> ProviderBudget:
        """Configured or not, and no daily figure.

        Groq's free tier meters tokens per day as well as requests, and
        nothing here counts tokens. Reporting a request count as "the budget"
        would be a number that runs out at the wrong time, so the field stays
        null and the only honest claim — whether there is a key — is made.
        """
        return ProviderBudget(name=self.name, configured=self.is_configured())

    async def generate_json(
        self,
        *,
        prompt_id: str,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.3,
    ) -> JSONResult:
        if not self.is_configured():
            raise LLMError("GROQ_API_KEY is not set")

        started = time.monotonic()
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    # The schema goes in the prompt, not in the request: Groq's
                    # json_object mode guarantees parseable JSON and nothing
                    # about its shape, where Gemini is given the schema
                    # directly. Saying it twice is cheaper than a retry.
                    "content": (
                        _shape_instruction(schema)
                        + " It must match this schema: "
                        + json.dumps(schema)
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            # Explicit, because Groq's default for this model truncates a
            # batch mid-array and reports it as a JSON validation failure.
            "max_completion_tokens": settings.groq_max_output_tokens,
        }

        # Reserve the whole call — prompt plus room for the answer — before
        # making it. Groq counts both halves against TPM, and a reservation
        # taken afterwards would already be too late.
        body, attempts = await self._post(
            "/chat/completions",
            payload,
            prompt_id=prompt_id,
            tokens=_estimate_tokens(payload) + settings.groq_output_reserve,
        )

        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"{prompt_id}: groq response had no content") from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"{prompt_id}: groq returned unparseable JSON: {exc}") from exc

        usage = body.get("usage") or {}
        call = LLMCall(
            prompt_id=prompt_id,
            model=self._model,
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
            prompt_id=prompt_id,
            model=self._model,
            latency_ms=call.latency_ms,
            prompt_tokens=call.prompt_tokens,
            output_tokens=call.output_tokens,
            total_tokens=call.total_tokens,
            attempts=attempts,
        )
        return JSONResult(data=data, call=call)

    async def embed(self, *, prompt_id: str, texts: list[str]) -> EmbedResult:
        """Refused, deliberately.

        Groq serves no embedding model. Falling back to a different one would
        put two incompatible vector spaces in the same column, and the
        curator's clusters are cosine distances within one space — mixing
        them does not degrade the grouping, it invalidates it.
        """
        raise LLMError("groq has no embedding model; embeddings stay on Gemini")

    async def _post(
        self, path: str, payload: dict[str, Any], *, prompt_id: str, tokens: int = 0
    ) -> tuple[dict[str, Any], int]:
        headers = {
            "Authorization": f"Bearer {self._key}",
            "content-type": "application/json",
        }
        last_error = ""

        async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                await self._rpm.acquire()
                if tokens:
                    await self._tpm.acquire(tokens)
                try:
                    response = await client.post(f"{BASE_URL}{path}", json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt == MAX_ATTEMPTS:
                        raise LLMError(f"{prompt_id}: groq unreachable ({last_error})") from exc
                    continue

                if response.status_code == 200:
                    data = response.json()
                    return (data if isinstance(data, dict) else {}), attempt

                last_error = _detail(response)
                if response.status_code == 429:
                    # Groq's own rate limit. The caller has already spilled
                    # over to get here, so there is nowhere further to go.
                    raise RateLimited(f"{prompt_id}: groq rate limited ({last_error})")
                if response.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                    log.warning(
                        "retrying",
                        provider=self.name,
                        prompt_id=prompt_id,
                        status=response.status_code,
                        attempt=attempt,
                    )
                    continue
                raise LLMError(f"{prompt_id}: groq {response.status_code} {last_error}")

        raise LLMError(f"{prompt_id}: groq gave up after {MAX_ATTEMPTS} attempts ({last_error})")


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        message = (payload.get("error") or {}).get("message")
        if message:
            return str(message)[:300]
    except Exception:
        pass
    return response.text[:200]


def _estimate_tokens(payload: dict[str, Any]) -> int:
    """Rough token count for a request, before it is sent.

    Four characters to a token is the usual approximation and is close enough
    for a limiter: the cost of being wrong is waiting slightly too long or
    taking one 429, not a wrong answer. Deliberately a slight over-estimate —
    under-reserving is what produces the 429 this exists to avoid.
    """
    characters = sum(
        len(str(message.get("content") or "")) for message in payload.get("messages") or []
    )
    return characters // 4 + 64


def _shape_instruction(schema: dict[str, Any]) -> str:
    """How to carry the answer inside the object json_object mode requires.

    A schema asking for an array cannot be honoured literally — the mode
    forbids a top-level array — so the array needs a named home. Without
    this a model handed a five-cluster batch returns one cluster as a bare
    object, which parses cleanly and contains none of what was asked for.
    """
    if str(schema.get("type", "")).upper() == "ARRAY":
        return (
            'You return a single JSON object of the form {"items": [ ... ]} and '
            "nothing else, where items is the array described below."
        )
    return "You return a single JSON object and nothing else."
