"""OpenRouterProvider, and where it sits in the chain.

Mostly about the model chain and the budget, because those are what differ
from the Groq provider it otherwise resembles: OpenRouter's free ids are
withdrawn without notice and a routed 429 often comes from the upstream
provider rather than OpenRouter, so walking to the next id is the normal
path rather than an edge case.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from app.core.config import settings
from app.llm import GeminiProvider, GroqProvider, OpenRouterProvider, SpilloverProvider, get_llm
from app.llm.base import LLMError, RateLimited
from app.llm.openrouter import BASE_URL

SCHEMA: dict[str, Any] = {"type": "OBJECT", "properties": {"headline": {"type": "STRING"}}}
CHAIN = ["model-a", "model-b", "model-c"]


def answer(content: str = '{"headline": "Goa cuts jet fuel tax"}') -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
        },
    )


def provider(**kw) -> OpenRouterProvider:
    kw.setdefault("api_key", "sk-or-test")
    return OpenRouterProvider(**kw)


@pytest.fixture(autouse=True)
def _chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_model", CHAIN[0])
    monkeypatch.setattr(settings, "openrouter_model_fallbacks", ",".join(CHAIN[1:]))


class TestConfiguration:
    def test_a_key_and_a_model_are_both_needed(self, monkeypatch) -> None:
        assert provider().is_configured() is True

        # A key with nothing to call would put a dead provider in front of
        # nothing, which is worse than reporting itself unavailable.
        monkeypatch.setattr(settings, "openrouter_model", "")
        monkeypatch.setattr(settings, "openrouter_model_fallbacks", "")
        assert OpenRouterProvider(api_key="sk-or-test").is_configured() is False

    def test_no_key_is_not_configured(self) -> None:
        assert OpenRouterProvider(api_key="").is_configured() is False

    async def test_it_refuses_rather_than_calling_without_a_key(self) -> None:
        with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
            await OpenRouterProvider(api_key="").generate_json(
                prompt_id="p", prompt="x", schema=SCHEMA
            )

    async def test_embeddings_are_refused(self) -> None:
        """Two vector spaces in one column invalidates the curator's
        clusters rather than merely weakening them."""
        with pytest.raises(LLMError, match="embeddings"):
            await provider().embed(prompt_id="p", texts=["a"])


class TestChain:
    @respx.mock
    async def test_the_first_model_answers_when_it_can(self, client) -> None:
        route = respx.post(f"{BASE_URL}/chat/completions").mock(return_value=answer())

        result = await provider(client=client).generate_json(
            prompt_id="p", prompt="go", schema=SCHEMA
        )

        assert result.data == {"headline": "Goa cuts jet fuel tax"}
        assert result.call.model == CHAIN[0]
        assert route.call_count == 1

    @respx.mock
    async def test_a_rate_limited_model_hands_on_to_the_next(self, client) -> None:
        """Usually the upstream provider rather than OpenRouter, and another
        id may route somewhere else entirely."""
        respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[
                httpx.Response(429, json={"error": {"message": "Provider returned error"}}),
                answer(),
            ]
        )

        result = await provider(client=client).generate_json(
            prompt_id="p", prompt="go", schema=SCHEMA
        )

        assert result.call.model == CHAIN[1]

    @respx.mock
    async def test_a_withdrawn_model_hands_on_to_the_next(self, client) -> None:
        """Free ids disappear without notice, so a 404 is routine here."""
        respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[
                httpx.Response(404, json={"error": {"message": "No such model"}}),
                answer(),
            ]
        )

        result = await provider(client=client).generate_json(
            prompt_id="p", prompt="go", schema=SCHEMA
        )

        assert result.call.model == CHAIN[1]

    @respx.mock
    async def test_prose_hands_on_rather_than_retrying_the_same_model(self, client) -> None:
        """A model that answers with prose answers with prose again. One of
        the free models returned HTTP 200 with an empty body when probed."""
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[answer("here is your json:"), answer(""), answer()]
        )

        result = await provider(client=client).generate_json(
            prompt_id="p", prompt="go", schema=SCHEMA
        )

        assert result.call.model == CHAIN[2]
        assert route.call_count == 3

    @respx.mock
    async def test_the_whole_chain_failing_is_a_rate_limit(self, client) -> None:
        """So SpilloverProvider treats it as exhaustion rather than a bug."""
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(429, json={"error": {"message": "busy"}})
        )

        with pytest.raises(RateLimited, match="no model in"):
            await provider(client=client).generate_json(prompt_id="p", prompt="go", schema=SCHEMA)

    @respx.mock
    async def test_a_bad_request_raises_rather_than_walking_the_chain(self, client) -> None:
        """A malformed prompt is malformed for every model, and asking three
        of them is three times the cost for the same answer."""
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(400, json={"error": {"message": "bad input"}})
        )

        with pytest.raises(LLMError, match="bad input"):
            await provider(client=client).generate_json(prompt_id="p", prompt="go", schema=SCHEMA)

    @respx.mock
    async def test_the_schema_is_restated_in_the_prompt(self, client) -> None:
        """json_object promises parseable JSON and nothing about its shape."""
        route = respx.post(f"{BASE_URL}/chat/completions").mock(return_value=answer())

        await provider(client=client).generate_json(prompt_id="p", prompt="go", schema=SCHEMA)

        sent = json.loads(route.calls.last.request.content)
        assert sent["response_format"] == {"type": "json_object"}
        assert "headline" in sent["messages"][0]["content"]

    @respx.mock
    async def test_it_identifies_itself(self, client) -> None:
        """OpenRouter attributes the request to these on the activity page.
        They are identification, not credentials."""
        route = respx.post(f"{BASE_URL}/chat/completions").mock(return_value=answer())

        await provider(client=client).generate_json(prompt_id="p", prompt="go", schema=SCHEMA)

        headers = route.calls.last.request.headers
        assert headers["x-title"] == settings.openrouter_title
        assert headers["http-referer"] == settings.openrouter_referer

    @respx.mock
    async def test_the_call_records_which_provider_served_it(self, client) -> None:
        respx.post(f"{BASE_URL}/chat/completions").mock(return_value=answer())

        result = await provider(client=client).generate_json(
            prompt_id="p", prompt="go", schema=SCHEMA
        )

        assert result.call.extra["provider"] == "openrouter"


class TestBudget:
    @respx.mock
    async def test_it_reports_dollars_not_a_request_count(self, client) -> None:
        """OpenRouter meters money. A request count here would be invented."""
        respx.get(f"{BASE_URL}/auth/key").mock(
            return_value=httpx.Response(
                200, json={"data": {"effective_budget": {"remaining_usd": 7.5}}}
            )
        )

        status = await provider(client=client).budget()

        assert status.remaining_usd == 7.5
        assert status.remaining_today is None

    @respx.mock
    async def test_it_falls_back_to_the_top_level_figure(self, client) -> None:
        respx.get(f"{BASE_URL}/auth/key").mock(
            return_value=httpx.Response(200, json={"data": {"limit_remaining": 42}})
        )

        assert (await provider(client=client).budget()).remaining_usd == 42.0

    @respx.mock
    async def test_an_unreadable_budget_is_null_not_zero(self, client) -> None:
        """Null says "could not be read"; zero says "nothing left"."""
        respx.get(f"{BASE_URL}/auth/key").mock(return_value=httpx.Response(500, text="oops"))

        assert (await provider(client=client).budget()).remaining_usd is None

    @respx.mock
    async def test_the_figure_is_cached(self, client) -> None:
        """/health is polled every ten seconds by the compose healthcheck,
        and this is a live HTTP call."""
        route = respx.get(f"{BASE_URL}/auth/key").mock(
            return_value=httpx.Response(200, json={"data": {"limit_remaining": 5}})
        )

        openrouter = provider(client=client)
        await openrouter.budget()
        await openrouter.budget()

        assert route.call_count == 1

    async def test_an_unconfigured_provider_asks_nothing(self) -> None:
        with respx.mock:
            route = respx.get(f"{BASE_URL}/auth/key")
            status = await OpenRouterProvider(api_key="").budget()

        assert status.configured is False
        assert status.remaining_usd is None
        assert not route.called


class TestChainOrder:
    async def test_the_registry_chains_all_three_in_order(self, monkeypatch) -> None:
        import app.llm as registry

        monkeypatch.setattr(registry, "_provider", None)
        statuses = await get_llm().statuses()

        assert [s.name for s in statuses] == ["gemini", "groq", "openrouter"]

    async def test_openrouter_is_only_asked_after_both_others(self) -> None:
        """Nested so each standby is itself a chain. Three free tiers in a
        row is the point: each has its own daily ceiling."""
        chain = SpilloverProvider(
            GeminiProvider(api_key=""),
            SpilloverProvider(GroqProvider(api_key=""), OpenRouterProvider(api_key="k")),
        )

        assert [s.name for s in await chain.statuses()] == ["gemini", "groq", "openrouter"]
        assert chain.is_configured() is True


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c
