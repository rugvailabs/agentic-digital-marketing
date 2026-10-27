"""Gemini via the Generative Language REST API.

Deliberately httpx rather than the google-genai SDK: every other adapter in
this codebase is a thin httpx client, the two calls we make are one endpoint
each, and respx then mocks Gemini in tests exactly the way it mocks YouTube.
The SDK would add a second HTTP stack and its own retry policy fighting ours.
"""

from __future__ import annotations

import asyncio
import json
import random
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
from app.llm.limiter import DailyBudget, TokenBucket
from app.llm.priority import is_background

log = get_logger("llm.gemini")

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_ATTEMPTS = 4
#: Gemini embeds one text per call on this endpoint, so batches are serialised.
EMBED_CHUNK = 1


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        model: str | None = None,
        embed_model: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key if api_key is not None else settings.gemini_api_key
        self._model = model or settings.gemini_model
        self._model_chain = [self._model] if model else settings.gemini_model_chain
        self._embed_model = embed_model or settings.gemini_embed_model
        self._rpm = TokenBucket(settings.gemini_rpm, 60.0, name="gemini-rpm")
        self._embed_rpm = TokenBucket(settings.gemini_embed_rpm, 60.0, name="gemini-embed-rpm")
        self._daily = DailyBudget(settings.gemini_rpd, name="gemini-rpd")

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def budget(self) -> ProviderBudget:
        """Today's allowance, per model and in total.

        The total is a sum across the chain rather than one model's figure,
        because a call walks the chain until something answers: the budget
        that matters is the whole ladder's, and eight models at twenty a day
        is a different story from twenty.
        """
        per_model = {model: await self._daily.remaining(model) for model in self._model_chain}
        limit = self._daily.limit * len(self._model_chain)
        remaining = sum(per_model.values())
        return ProviderBudget(
            name=self.name,
            configured=self.is_configured(),
            remaining_today=remaining,
            per_model=per_model,
            used_today=limit - remaining,
            # Per model, like the limit itself: the reserve stops a
            # scheduled curate on each model id, so the Desk keeps this many
            # on each of them rather than this many in total.
            reserved_for_desk=settings.gemini_desk_reserve * len(self._model_chain),
        )

    # ── public API ────────────────────────────────────────────────────────

    async def generate_json(
        self,
        *,
        prompt_id: str,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.3,
    ) -> JSONResult:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
                "temperature": temperature,
            },
        }

        # Walk the model chain. This tier answers 503 "high demand" often
        # enough that exhausting retries against one model id is a routine
        # outcome rather than an incident, and a sibling model usually answers.
        last: Exception | None = None
        body = call = None
        for model in self._model_chain:
            try:
                body, call = await self._post(
                    f"models/{model}:generateContent",
                    payload,
                    prompt_id=prompt_id,
                    model=model,
                    bucket=self._rpm,
                    count_daily=True,
                )
                break
            except RateLimited as exc:
                last = exc
                log.warning("model unavailable, trying next", prompt_id=prompt_id, model=model)
            except LLMError as exc:
                # 404 means this id is not served to this key; try the next.
                if "404" not in str(exc):
                    raise
                last = exc
                log.warning("model not served, trying next", prompt_id=prompt_id, model=model)

        if body is None or call is None:
            raise RateLimited(
                f"{prompt_id}: no model in {self._model_chain} answered ({last})"
            ) from last

        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            # A blocked or truncated response has no parts at all.
            finish = (body.get("candidates") or [{}])[0].get("finishReason")
            raise LLMError(f"{prompt_id}: no content in response (finishReason={finish})") from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"{prompt_id}: response was not JSON ({len(text)} chars)") from exc

        return JSONResult(data=data, call=call)

    async def embed(self, *, prompt_id: str, texts: list[str]) -> EmbedResult:
        if not texts:
            return EmbedResult(vectors=[], call=LLMCall(prompt_id, self._embed_model, 0))

        started = time.monotonic()
        vectors: list[list[float]] = []
        attempts = 0

        for text in texts:
            payload = {
                "model": f"models/{self._embed_model}",
                "content": {"parts": [{"text": text[:8000]}]},
                "outputDimensionality": settings.gemini_embed_dim,
            }
            body, call = await self._post(
                f"models/{self._embed_model}:embedContent",
                payload,
                prompt_id=prompt_id,
                model=self._embed_model,
                bucket=self._embed_rpm,
                count_daily=False,
                quiet=True,
            )
            attempts += call.attempts
            values = (body.get("embedding") or {}).get("values")
            if not values:
                raise LLMError(f"{prompt_id}: embedding response had no values")
            vectors.append([float(v) for v in values])

        latency_ms = int((time.monotonic() - started) * 1000)
        call = LLMCall(
            prompt_id=prompt_id,
            model=self._embed_model,
            latency_ms=latency_ms,
            attempts=attempts,
            extra={"texts": len(texts), "dim": len(vectors[0]) if vectors else 0},
        )
        log.info(
            "llm call",
            prompt_id=prompt_id,
            model=self._embed_model,
            texts=len(texts),
            dim=call.extra["dim"],
            latency_ms=latency_ms,
            attempts=attempts,
        )
        return EmbedResult(vectors=vectors, call=call)

    # ── transport ─────────────────────────────────────────────────────────

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        prompt_id: str,
        model: str,
        bucket: TokenBucket,
        count_daily: bool,
        quiet: bool = False,
    ) -> tuple[dict[str, Any], LLMCall]:
        if not self.is_configured():
            raise LLMError("gemini is not configured: GEMINI_API_KEY is not set")

        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=settings.gemini_timeout_seconds)

        started = time.monotonic()
        last_error: str = ""
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                # Scheduled work stops short of the limit so a user at the
                # Desk still has calls left. See app.llm.priority.
                reserve = settings.gemini_desk_reserve if is_background() else 0
                if count_daily and not await self._daily.spend(model, reserve=reserve):
                    held = f", holding {reserve} back for the Desk" if reserve else ""
                    raise RateLimited(
                        f"{prompt_id}: {model} has spent its daily budget of "
                        f"{settings.gemini_rpd} calls{held}"
                    )
                await bucket.acquire()

                try:
                    response = await client.post(
                        f"{BASE_URL}/{path}", params={"key": self._api_key}, json=payload
                    )
                except httpx.HTTPError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt == MAX_ATTEMPTS:
                        raise LLMError(f"{prompt_id}: {last_error}") from exc
                    await self._backoff(attempt, prompt_id, last_error)
                    continue

                if response.status_code == 200:
                    body = response.json()
                    call = await self._record(body, prompt_id, model, started, attempt, quiet=quiet)
                    return body, call

                last_error = _error_message(response)
                # 429 and 5xx are worth another attempt; 4xx is our mistake.
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == MAX_ATTEMPTS:
                        raise RateLimited(f"{prompt_id}: {response.status_code} {last_error}")
                    await self._backoff(attempt, prompt_id, last_error)
                    continue

                raise LLMError(f"{prompt_id}: {response.status_code} {last_error}")
        finally:
            if own_client:
                await client.aclose()

        raise LLMError(f"{prompt_id}: exhausted {MAX_ATTEMPTS} attempts ({last_error})")

    @staticmethod
    async def _backoff(attempt: int, prompt_id: str, reason: str) -> None:
        # Full jitter: several workers retrying in lockstep is how a transient
        # 429 becomes a sustained one.
        delay = random.uniform(0, min(32.0, 2.0**attempt))
        log.warning(
            "retrying",
            prompt_id=prompt_id,
            attempt=attempt,
            sleep_s=round(delay, 2),
            reason=reason[:160],
        )
        await asyncio.sleep(delay)

    async def _record(
        self,
        body: dict[str, Any],
        prompt_id: str,
        model: str,
        started: float,
        attempts: int,
        *,
        quiet: bool,
    ) -> LLMCall:
        usage = body.get("usageMetadata") or {}
        call = LLMCall(
            prompt_id=prompt_id,
            model=model,
            latency_ms=int((time.monotonic() - started) * 1000),
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            output_tokens=int(usage.get("candidatesTokenCount") or 0),
            total_tokens=int(usage.get("totalTokenCount") or 0),
            attempts=attempts,
            # Which vendor served this call. Gemini answering is the ordinary
            # case and so the easiest one to leave unlabelled, which is
            # exactly what makes a spillover hard to see afterwards: a line
            # with a model id and no vendor reads as "the usual one".
            extra={"provider": self.name},
        )
        if not quiet:
            # Every LLM call is logged with prompt id, model, tokens, latency.
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
                daily_remaining=await self._daily.remaining(model),
            )
        return call


def _error_message(response: httpx.Response) -> str:
    try:
        return str((response.json().get("error") or {}).get("message") or response.text)[:300]
    except ValueError:
        return response.text[:300]
