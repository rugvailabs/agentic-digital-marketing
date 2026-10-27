"""Groq, and when it is allowed to answer.

The rule that matters is the narrow one: spillover happens when Gemini has
spent its daily budget and for no other reason. A bad prompt does not become
a good one by being sent somewhere else, and embeddings never move at all.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.llm.base import EmbedResult, JSONResult, LLMCall, LLMError, LLMProvider, RateLimited
from app.llm.groq import BASE_URL, GroqProvider
from app.llm.spillover import SpilloverProvider

SCHEMA: dict[str, Any] = {"type": "OBJECT", "properties": {"headline": {"type": "STRING"}}}


def answer(content: str = '{"headline": "Goa cuts jet fuel tax"}') -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160},
        },
    )


class Fake(LLMProvider):
    """A provider that does exactly what the test needs and records calls."""

    def __init__(self, name: str, *, configured: bool = True, raises: Exception | None = None):
        self.name = name
        self.configured = configured
        self.raises = raises
        self.json_calls = 0
        self.embed_calls = 0

    def is_configured(self) -> bool:
        return self.configured

    async def generate_json(self, *, prompt_id, prompt, schema, temperature=0.3) -> JSONResult:
        self.json_calls += 1
        if self.raises:
            raise self.raises
        return JSONResult(
            data={"served_by": self.name},
            call=LLMCall(prompt_id=prompt_id, model=self.name, latency_ms=1),
        )

    async def embed(self, *, prompt_id, texts) -> EmbedResult:
        self.embed_calls += 1
        if self.raises:
            raise self.raises
        return EmbedResult(
            vectors=[[0.0]] * len(texts),
            call=LLMCall(prompt_id=prompt_id, model=self.name, latency_ms=1),
        )


class TestGroqProvider:
    def test_a_key_is_what_makes_it_configured(self) -> None:
        assert GroqProvider(api_key="k").is_configured() is True
        assert GroqProvider(api_key="").is_configured() is False

    async def test_it_refuses_rather_than_calling_without_a_key(self) -> None:
        with pytest.raises(LLMError, match="GROQ_API_KEY"):
            await GroqProvider(api_key="").generate_json(prompt_id="p", prompt="x", schema=SCHEMA)

    @respx.mock
    async def test_a_good_answer_is_parsed(self) -> None:
        respx.post(f"{BASE_URL}/chat/completions").mock(return_value=answer())

        result = await GroqProvider(api_key="k").generate_json(
            prompt_id="write_reel_v1", prompt="go", schema=SCHEMA
        )

        assert result.data == {"headline": "Goa cuts jet fuel tax"}
        assert result.call.total_tokens == 160

    @respx.mock
    async def test_the_call_records_which_provider_served_it(self) -> None:
        """Every call is logged with its provider, so a spillover is visible
        afterwards rather than inferred from token counts."""
        respx.post(f"{BASE_URL}/chat/completions").mock(return_value=answer())

        result = await GroqProvider(api_key="k", model="openai/gpt-oss-120b").generate_json(
            prompt_id="p", prompt="go", schema=SCHEMA
        )

        assert result.call.extra["provider"] == "groq"
        assert result.call.model == "openai/gpt-oss-120b"

    @respx.mock
    async def test_the_schema_is_restated_in_the_prompt(self) -> None:
        """Groq's json_object mode promises parseable JSON and nothing about
        its shape, where Gemini is handed the schema directly."""
        import json

        route = respx.post(f"{BASE_URL}/chat/completions").mock(return_value=answer())

        await GroqProvider(api_key="k").generate_json(prompt_id="p", prompt="go", schema=SCHEMA)

        sent = json.loads(route.calls.last.request.content)
        assert sent["response_format"] == {"type": "json_object"}
        assert "headline" in sent["messages"][0]["content"]

    @respx.mock
    async def test_unparseable_json_is_an_error_not_a_guess(self) -> None:
        respx.post(f"{BASE_URL}/chat/completions").mock(return_value=answer("not json at all"))

        with pytest.raises(LLMError, match="unparseable JSON"):
            await GroqProvider(api_key="k").generate_json(prompt_id="p", prompt="go", schema=SCHEMA)

    @respx.mock
    async def test_a_rate_limit_is_terminal(self) -> None:
        """By the time Groq is answering, the caller has already spilled over
        once. There is nowhere further to go."""
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(429, json={"error": {"message": "slow down"}})
        )

        with pytest.raises(RateLimited, match="slow down"):
            await GroqProvider(api_key="k").generate_json(prompt_id="p", prompt="go", schema=SCHEMA)

    @respx.mock
    async def test_a_server_error_is_retried(self) -> None:
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[httpx.Response(503, text="busy"), answer()]
        )

        result = await GroqProvider(api_key="k").generate_json(
            prompt_id="p", prompt="go", schema=SCHEMA
        )

        assert route.call_count == 2
        assert result.call.attempts == 2

    @respx.mock
    async def test_a_bad_model_name_says_so(self) -> None:
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(
                404, json={"error": {"message": "The model `x` does not exist"}}
            )
        )

        with pytest.raises(LLMError, match="does not exist"):
            await GroqProvider(api_key="k", model="x").generate_json(
                prompt_id="p", prompt="go", schema=SCHEMA
            )

    async def test_embeddings_are_refused(self) -> None:
        """Two vector spaces in one column does not weaken the curator's
        clusters, it invalidates them."""
        with pytest.raises(LLMError, match="no embedding model"):
            await GroqProvider(api_key="k").embed(prompt_id="p", texts=["a"])


class TestSpillover:
    def chain(self, primary: Fake, standby: Fake) -> SpilloverProvider:
        return SpilloverProvider(primary, standby)

    async def call(self, provider: LLMProvider) -> Any:
        result = await provider.generate_json(prompt_id="p", prompt="go", schema=SCHEMA)
        return result.data.get("served_by")

    async def test_the_primary_serves_when_it_can(self) -> None:
        primary, standby = Fake("gemini"), Fake("groq")

        assert await self.call(self.chain(primary, standby)) == "gemini"
        assert standby.json_calls == 0

    async def test_an_exhausted_budget_spills_over(self) -> None:
        primary = Fake("gemini", raises=RateLimited("all models spent their daily budget"))
        standby = Fake("groq")

        assert await self.call(self.chain(primary, standby)) == "groq"

    async def test_an_ordinary_error_does_not_spill_over(self) -> None:
        """A bad prompt does not become a good one by being sent somewhere
        else, and a second vendor billing for the same failure is waste."""
        primary = Fake("gemini", raises=LLMError("malformed response"))
        standby = Fake("groq")

        with pytest.raises(LLMError, match="malformed response"):
            await self.call(self.chain(primary, standby))
        assert standby.json_calls == 0

    async def test_exhaustion_with_no_standby_raises_the_original(self) -> None:
        primary = Fake("gemini", raises=RateLimited("budget spent"))
        standby = Fake("groq", configured=False)

        with pytest.raises(RateLimited, match="budget spent"):
            await self.call(self.chain(primary, standby))

    async def test_an_unconfigured_primary_goes_straight_to_the_standby(self) -> None:
        primary, standby = Fake("gemini", configured=False), Fake("groq")

        assert await self.call(self.chain(primary, standby)) == "groq"
        assert primary.json_calls == 0

    async def test_neither_configured_is_a_clear_error(self) -> None:
        chain = self.chain(Fake("gemini", configured=False), Fake("groq", configured=False))

        with pytest.raises(LLMError, match="no LLM provider is configured"):
            await self.call(chain)

    async def test_it_is_configured_if_either_is(self) -> None:
        assert self.chain(Fake("g"), Fake("q", configured=False)).is_configured() is True
        assert self.chain(Fake("g", configured=False), Fake("q")).is_configured() is True
        assert (
            self.chain(Fake("g", configured=False), Fake("q", configured=False)).is_configured()
            is False
        )

    async def test_embeddings_never_spill_over(self) -> None:
        """Groq has no embedding model, and the curator's clusters are cosine
        distances inside one vector space."""
        primary = Fake("gemini", raises=RateLimited("budget spent"))
        standby = Fake("groq")

        with pytest.raises(RateLimited):
            await self.chain(primary, standby).embed(prompt_id="p", texts=["a"])
        assert standby.embed_calls == 0

    async def test_embeddings_go_to_the_primary_when_it_works(self) -> None:
        primary, standby = Fake("gemini"), Fake("groq")

        result = await self.chain(primary, standby).embed(prompt_id="p", texts=["a", "b"])

        assert len(result.vectors) == 2
        assert standby.embed_calls == 0
