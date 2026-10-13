"""Model providers. The rest of the app only knows the `Provider` contract."""
from __future__ import annotations

from ..config import Settings
from .base import ChatMessage, Provider, ProviderError, StreamChunk, Usage, estimate_tokens
from .mock import MockProvider
from .openai_compat import OpenAICompatProvider

__all__ = ["ChatMessage", "Provider", "ProviderError", "StreamChunk", "Usage",
           "estimate_tokens", "build_provider"]


def build_provider(settings: Settings) -> Provider:
    if settings.llm_provider == "openai":
        return OpenAICompatProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            max_tokens_param=settings.openai_max_tokens_param,
        )
    return MockProvider(delay_ms=settings.mock_delay_ms)
