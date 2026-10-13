"""Provider for OpenAI and for any server that speaks the same chat-completions protocol
(Ollama, vLLM, LM Studio, Azure-style gateways). It talks to the HTTP API directly, so the
project does not depend on a vendor SDK."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .base import ChatMessage, ProviderError, StreamChunk, Usage


class OpenAICompatProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens_param: str = "max_tokens",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._max_tokens_param = max_tokens_param
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # A long read timeout: a local model on CPU can take a while before the first token.
        self._client = httpx.AsyncClient(
            headers=headers, transport=transport, timeout=httpx.Timeout(120.0, connect=10.0)
        )

    async def stream(
        self, messages: list[ChatMessage], max_tokens: int
    ) -> AsyncIterator[StreamChunk]:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            # Ask for the real token counts at the end of the stream.
            "stream_options": {"include_usage": True},
            self._max_tokens_param: max_tokens,
        }
        usage: Usage | None = None
        try:
            async with self._client.stream("POST", self._url, json=payload) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode(errors="replace")
                    raise ProviderError(f"HTTP {response.status_code}: {body[:300]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event.get("usage"):
                        usage = Usage(
                            input_tokens=int(event["usage"].get("prompt_tokens", 0)),
                            output_tokens=int(event["usage"].get("completion_tokens", 0)),
                        )
                    for choice in event.get("choices") or []:
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            yield StreamChunk(text=text)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{type(exc).__name__}: {exc}") from exc
        if usage is not None:
            yield StreamChunk(usage=usage)
