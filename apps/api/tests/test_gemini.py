"""GeminiProvider against recorded responses. No network, no key needed."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.llm import GeminiProvider, LLMError, RateLimited
from app.llm.limiter import DailyBudget, TokenBucket
from tests.conftest import load_json

CURATE_RESPONSE = load_json("gemini_curate_response.json")
GENERATE = respx.patterns.M(url__regex=r".*:generateContent")
EMBED = respx.patterns.M(url__regex=r".*:embedContent")
KEY = "test-key"

SCHEMA = {"type": "ARRAY", "items": {"type": "OBJECT"}}


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


def provider(client: httpx.AsyncClient, **kw) -> GeminiProvider:
    return GeminiProvider(client=client, api_key=KEY, model="test-model", **kw)


def test_not_configured_without_a_key() -> None:
    assert GeminiProvider(api_key="").is_configured() is False
    assert GeminiProvider(api_key=KEY).is_configured() is True


async def test_unconfigured_provider_raises_rather_than_calling(client) -> None:
    with pytest.raises(LLMError, match="not configured"):
        await GeminiProvider(client=client, api_key="").generate_json(
            prompt_id="x", prompt="hi", schema=SCHEMA
        )


@respx.mock
async def test_generate_json_parses_the_recorded_curator_response(client) -> None:
    route = respx.route(GENERATE).mock(return_value=httpx.Response(200, json=CURATE_RESPONSE))

    result = await provider(client).generate_json(
        prompt_id="curate_v1", prompt="...", schema=SCHEMA
    )

    assert route.called
    assert isinstance(result.data, list)
    assert len(result.data) >= 4
    first = result.data[0]
    assert {"cluster_id", "title", "category", "hashtags", "summary", "safety_flag"} <= set(first)
    # Every call is logged with its token counts, so they must be parsed.
    assert result.call.total_tokens > 0
    assert result.call.prompt_id == "curate_v1"
    assert result.call.attempts == 1


@respx.mock
async def test_generate_json_sends_the_schema_and_json_mime_type(client) -> None:
    route = respx.route(GENERATE).mock(return_value=httpx.Response(200, json=CURATE_RESPONSE))

    await provider(client).generate_json(prompt_id="p", prompt="hello", schema=SCHEMA)

    body = json.loads(route.calls[0].request.read())
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"] == SCHEMA
    assert body["contents"][0]["parts"][0]["text"] == "hello"
    assert route.calls[0].request.url.params["key"] == KEY


@respx.mock
async def test_a_blocked_response_with_no_parts_is_an_error_not_a_crash(client) -> None:
    respx.route(GENERATE).mock(
        return_value=httpx.Response(200, json={"candidates": [{"finishReason": "SAFETY"}]})
    )

    with pytest.raises(LLMError, match="no content"):
        await provider(client).generate_json(prompt_id="p", prompt="x", schema=SCHEMA)


@respx.mock
async def test_non_json_text_is_reported_as_such(client) -> None:
    respx.route(GENERATE).mock(
        return_value=httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "sorry, I cannot"}]}}]}
        )
    )

    with pytest.raises(LLMError, match="not JSON"):
        await provider(client).generate_json(prompt_id="p", prompt="x", schema=SCHEMA)


@respx.mock
async def test_503_falls_through_to_the_next_model_in_the_chain(client) -> None:
    """This tier answers 503 "high demand" routinely, which is why the chain
    exists; a single model id is not dependable."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url.path))
        if "model-a" in str(request.url.path):
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(200, json=CURATE_RESPONSE)

    respx.route(GENERATE).mock(side_effect=handler)
    p = GeminiProvider(client=client, api_key=KEY)
    p._model_chain = ["model-a", "model-b"]

    result = await p.generate_json(prompt_id="p", prompt="x", schema=SCHEMA)

    assert isinstance(result.data, list)
    assert any("model-a" in c for c in calls)
    assert any("model-b" in c for c in calls)


@respx.mock
async def test_every_model_failing_raises_rate_limited(client) -> None:
    respx.route(GENERATE).mock(return_value=httpx.Response(429, json={"error": {"message": "q"}}))
    p = GeminiProvider(client=client, api_key=KEY)
    p._model_chain = ["model-a"]

    with pytest.raises(RateLimited):
        await p.generate_json(prompt_id="p", prompt="x", schema=SCHEMA)


@respx.mock
async def test_a_4xx_that_is_not_429_is_not_retried(client) -> None:
    route = respx.route(GENERATE).mock(
        return_value=httpx.Response(400, json={"error": {"message": "bad request"}})
    )
    p = GeminiProvider(client=client, api_key=KEY)
    p._model_chain = ["model-a"]

    with pytest.raises(LLMError, match="400"):
        await p.generate_json(prompt_id="p", prompt="x", schema=SCHEMA)
    assert route.call_count == 1, "our own bad request must not be retried"


@respx.mock
async def test_embed_returns_one_vector_per_text_in_order(client) -> None:
    vectors = [[0.1] * 768, [0.2] * 768, [0.3] * 768]
    seq = iter(vectors)
    respx.route(EMBED).mock(
        side_effect=lambda _r: httpx.Response(200, json={"embedding": {"values": next(seq)}})
    )

    result = await provider(client).embed(prompt_id="curate_embed", texts=["a", "b", "c"])

    assert len(result.vectors) == 3
    assert [v[0] for v in result.vectors] == [
        pytest.approx(0.1),
        pytest.approx(0.2),
        pytest.approx(0.3),
    ]
    assert len(result.vectors[0]) == 768
    assert result.call.extra["dim"] == 768


@respx.mock
async def test_embed_requests_the_configured_dimensionality(client) -> None:
    route = respx.route(EMBED).mock(
        return_value=httpx.Response(200, json={"embedding": {"values": [0.0] * 768}})
    )

    await provider(client).embed(prompt_id="p", texts=["one"])

    body = json.loads(route.calls[0].request.read())
    assert body["outputDimensionality"] == 768
    assert body["content"]["parts"][0]["text"] == "one"


async def test_embedding_nothing_costs_no_calls(client) -> None:
    result = await provider(client).embed(prompt_id="p", texts=[])

    assert result.vectors == []


@respx.mock
async def test_an_embedding_without_values_is_an_error(client) -> None:
    respx.route(EMBED).mock(return_value=httpx.Response(200, json={"embedding": {}}))

    with pytest.raises(LLMError, match="no values"):
        await provider(client).embed(prompt_id="p", texts=["x"])


@respx.mock
async def test_a_call_records_which_provider_served_it(client) -> None:
    """Matches what Groq records, so a spillover is visible in the logs
    afterwards rather than inferred from which model id turned up."""
    respx.route(GENERATE).mock(return_value=httpx.Response(200, json=CURATE_RESPONSE))

    result = await provider(client).generate_json(
        prompt_id="curate_v1", prompt="...", schema=SCHEMA
    )

    assert result.call.extra["provider"] == "gemini"


class TestLimiter:
    async def test_bucket_allows_up_to_capacity_without_waiting(self) -> None:
        bucket = TokenBucket(3, 60.0, name="t")

        waits = [await bucket.acquire() for _ in range(3)]

        assert waits == [0.0, 0.0, 0.0]
        assert bucket.tokens_left() < 1

    async def test_bucket_makes_the_caller_wait_once_empty(self) -> None:
        # 60 per minute refills one per second, so the fourth call waits.
        bucket = TokenBucket(60, 60.0, name="t")
        for _ in range(60):
            await bucket.acquire()

        assert await bucket.acquire() > 0

    async def test_daily_budget_stops_rather_than_throttling(self) -> None:
        """Async since the count moved to Redis. With no url configured — the
        suite default — it falls back to counting in-process, which is what
        this asserts. The shared path is in test_llm_budget.py."""
        budget = DailyBudget(2, name="d")

        assert await budget.spend() is True
        assert await budget.spend() is True
        assert await budget.spend() is False
        assert await budget.remaining() == 0
