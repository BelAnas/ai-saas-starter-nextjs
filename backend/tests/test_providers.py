from __future__ import annotations

import json

import httpx
import pytest

from app.llm.base import ChatMessage, ProviderError, estimate_tokens
from app.llm.mock import MockProvider
from app.llm.openai_compat import OpenAICompatProvider
from app.plans import estimate_cost_usd

MESSAGES = [ChatMessage("system", "Be brief."), ChatMessage("user", "Describe a mug")]


def _line(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


async def test_mock_is_deterministic_and_reports_usage() -> None:
    async def run() -> tuple[str, object]:
        text, usage = "", None
        async for chunk in MockProvider(delay_ms=0).stream(MESSAGES, 400):
            text += chunk.text
            usage = chunk.usage or usage
        return text, usage

    first, second = await run(), await run()
    assert first == second
    assert first[1].output_tokens == estimate_tokens(first[0])  # type: ignore[union-attr]


async def test_openai_provider_parses_stream_and_usage() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        body = (
            _line({"choices": [{"delta": {"role": "assistant", "content": ""}}]})
            + _line({"choices": [{"delta": {"content": "A sturdy "}}]})
            + ": keep-alive comment\n\n"
            + _line({"choices": [{"delta": {"content": "mug."}}]})
            + _line({"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 4}})
            + "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    provider = OpenAICompatProvider("test-key", "http://llm.test/v1/", "gpt-4o-mini",
                                    transport=httpx.MockTransport(handler))
    chunks = [c async for c in provider.stream(MESSAGES, 50)]
    assert "".join(c.text for c in chunks) == "A sturdy mug."
    assert chunks[-1].usage.input_tokens == 12 and chunks[-1].usage.output_tokens == 4  # type: ignore[union-attr]
    assert captured["url"] == "http://llm.test/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["max_tokens"] == 50 and captured["body"]["stream"] is True
    assert captured["body"]["messages"][0] == {"role": "system", "content": "Be brief."}


async def test_openai_provider_turns_http_errors_into_provider_errors() -> None:
    provider = OpenAICompatProvider(
        "bad", "http://llm.test/v1", "gpt-4o-mini",
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "bad key"})))
    with pytest.raises(ProviderError, match="401"):
        [c async for c in provider.stream(MESSAGES, 50)]

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    offline = OpenAICompatProvider("k", "http://llm.test/v1", "m",
                                   transport=httpx.MockTransport(refuse))
    with pytest.raises(ProviderError, match="ConnectError"):
        [c async for c in offline.stream(MESSAGES, 50)]


def test_cost_estimate() -> None:
    # 1M input at $0.15 plus 1M output at $0.60.
    assert estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(0.75)
    assert estimate_cost_usd("some-local-model", 5000, 5000) == 0.0
