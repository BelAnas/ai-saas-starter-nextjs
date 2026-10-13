"""The contract every model provider follows."""
from __future__ import annotations

import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class StreamChunk:
    """A piece of the answer, or (usually last) the token counts reported by the provider."""

    text: str = ""
    usage: Usage | None = None


class ProviderError(Exception):
    """The provider could not answer. The message is for the server log, not for the user."""


class Provider(Protocol):
    name: str
    model: str

    def stream(self, messages: list[ChatMessage], max_tokens: int) -> AsyncIterator[StreamChunk]:
        ...


def estimate_tokens(text: str) -> int:
    """Rough count (about four characters per token in English), used when a provider reports none."""
    return max(1, math.ceil(len(text) / 4))
