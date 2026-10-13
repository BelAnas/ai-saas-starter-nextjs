"""Offline provider: no network, no key, the same answer for the same input.

It is not a language model. It fills a template chosen from keywords in the request, which is
enough to exercise streaming, quota, history and the interface without spending money.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

from .base import ChatMessage, StreamChunk, Usage, estimate_tokens

_NOTE = "(Offline demo answer from the mock provider. Set LLM_PROVIDER=openai for a real model.)"


def _subject(text: str) -> str:
    words = re.findall(r"[\w'-]+", text)
    return " ".join(words[:10]) or "your request"


def draft_answer(user_text: str) -> str:
    low = user_text.lower()
    subject = _subject(user_text)
    if any(k in low for k in ("description", "describe", "listing")):
        body = (
            f"Here is a product description draft based on: \"{subject}\".\n\n"
            "Made for everyday use, it is built from durable materials and finished by hand. "
            "It arrives ready to use, with clear care instructions in the box.\n\n"
            "- Built to last: quality materials, checked before shipping\n"
            "- Easy to care for: wipe clean, no special products needed\n"
            "- Ships in 2 working days, with 30-day returns"
        )
    elif any(k in low for k in ("reply", "email", "customer", "refund", "late", "complain")):
        body = (
            f"Here is a reply draft for: \"{subject}\".\n\n"
            "Hello,\n\nThank you for writing to us, and I am sorry for the trouble. "
            "I have checked your order and I am taking care of it today. "
            "You will receive a confirmation by email within one working day.\n\n"
            "If anything is still unclear, reply to this message and I will answer personally.\n\n"
            "Kind regards,\nThe shop team"
        )
    elif any(k in low for k in ("faq", "policy", "shipping", "return", "delivery")):
        body = (
            f"Here is an FAQ entry draft for: \"{subject}\".\n\n"
            "Q: How long does delivery take?\n"
            "A: Orders placed before 2 pm leave the same working day and arrive in 2 to 4 days.\n\n"
            "Q: Can I return an item?\n"
            "A: Yes, within 30 days, unused and in its original packaging."
        )
    else:
        body = (
            f"Here is a first draft for: \"{subject}\".\n\n"
            "1. State the main benefit for the shopper in one sentence.\n"
            "2. Add two concrete details: material, size, delivery time or guarantee.\n"
            "3. End with one clear next step, such as adding to the basket or replying to this email."
        )
    return f"{body}\n\n{_NOTE}"


class MockProvider:
    name = "mock"

    def __init__(self, delay_ms: int = 20, model: str = "mock-1") -> None:
        self.model = model
        self._delay = delay_ms / 1000

    async def stream(
        self, messages: list[ChatMessage], max_tokens: int
    ) -> AsyncIterator[StreamChunk]:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        answer = draft_answer(last_user)
        sent = ""
        # Split into words but keep the white space, so the pieces join back into the same text.
        for piece in re.findall(r"\S+\s*", answer):
            if estimate_tokens(sent + piece) > max_tokens:
                break
            if self._delay:
                await asyncio.sleep(self._delay)
            sent += piece
            yield StreamChunk(text=piece)
        yield StreamChunk(usage=Usage(
            input_tokens=sum(estimate_tokens(m.content) for m in messages),
            output_tokens=estimate_tokens(sent),
        ))
