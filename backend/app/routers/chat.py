"""The streaming chat endpoint.

A request has three parts, and the database is only touched in the first and the last:

1. prepare: sign-in check, quota reservation and saving the user's message, in one transaction;
2. stream: forward the provider's output to the browser, holding no database connection;
3. finalise: save the answer and fill in the usage row, also when the browser went away.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..config import Settings
from ..db import Database, utcnow
from ..deps import user_from_token
from ..llm import ChatMessage, Provider, ProviderError, Usage, estimate_tokens
from ..models import Conversation, Message, User
from ..plans import get_plan
from ..quota import QuotaExceeded, finish, reserve, snapshot
from ..schemas import ChatIn
from ..sse import sse

log = logging.getLogger("shopdesk.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are Shopdesk AI, a writing assistant for small online shops. You draft product "
    "descriptions, replies to customers and FAQ entries. Be concrete and brief. Never invent "
    "prices, stock levels or delivery dates: ask for them or leave a clearly marked placeholder."
)


@dataclass(frozen=True)
class Prepared:
    user_id: int
    conversation_id: int
    title: str
    is_new: bool
    event_id: int
    messages: list[ChatMessage]
    max_tokens: int


def _title_from(text: str) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= 60 else one_line[:57].rstrip() + "..."


def prepare(db: Database, settings: Settings, provider: Provider, token: str | None,
            body: ChatIn) -> Prepared:
    """Everything that must be true before the model is called, in one write transaction."""
    text = body.message.strip()
    if not text:
        raise HTTPException(422, "The message is empty.")
    if len(text) > settings.max_input_chars:
        raise HTTPException(
            413, f"The message is longer than {settings.max_input_chars} characters.")

    with db.session(write=True) as session:
        user = user_from_token(session, token)
        if user is None:
            raise HTTPException(401, "Please sign in.")

        if body.conversation_id is None:
            conversation = None
        else:
            conversation = session.execute(
                select(Conversation).where(
                    Conversation.id == body.conversation_id, Conversation.user_id == user.id)
            ).scalar_one_or_none()
            # 404 also for someone else's conversation, so ids cannot be probed.
            if conversation is None:
                raise HTTPException(404, "Conversation not found.")

        event = reserve(session, user, provider.name, provider.model)  # raises QuotaExceeded

        is_new = conversation is None
        if conversation is None:
            conversation = Conversation(user_id=user.id, title=_title_from(text))
            session.add(conversation)
            session.flush()
        conversation.updated_at = utcnow()
        event.conversation_id = conversation.id
        session.add(Message(conversation_id=conversation.id, role="user", content=text))
        session.flush()

        recent = session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.content != "")
            .order_by(Message.id.desc())
            .limit(settings.context_messages)
        ).scalars().all()
        history = [ChatMessage(m.role, m.content) for m in reversed(recent)]
        prepared = Prepared(
            user_id=user.id, conversation_id=conversation.id, title=conversation.title,
            is_new=is_new, event_id=event.id,
            messages=[ChatMessage("system", SYSTEM_PROMPT), *history],
            max_tokens=get_plan(user.plan).max_output_tokens,
        )
        session.commit()
        return prepared


def finalise(db: Database, prepared: Prepared, text: str, usage: Usage | None,
             outcome: str) -> dict[str, object]:
    """Save the answer and the token counts. `outcome` is completed, stopped or failed."""
    estimated = usage is None
    if usage is None:
        usage = Usage(
            input_tokens=sum(estimate_tokens(m.content) for m in prepared.messages),
            output_tokens=estimate_tokens(text) if text else 0,
        )
    # A provider failure before any output is not charged. With partial output it is, because
    # the tokens were really produced.
    status = "failed" if (outcome == "failed" and not text) else (
        "completed" if outcome == "completed" else "stopped")
    if status == "failed":
        usage = Usage(0, 0)

    with db.session(write=True) as session:
        message_id: int | None = None
        if text:
            message = Message(
                conversation_id=prepared.conversation_id, role="assistant", content=text,
                status={"completed": "complete", "stopped": "stopped"}.get(outcome, "error"),
            )
            session.add(message)
            session.flush()
            message_id = message.id
        event = finish(session, prepared.event_id, status, usage.input_tokens,
                       usage.output_tokens, estimated)
        user = session.get(User, prepared.user_id)
        quota = snapshot(session, user).public() if user else None
        session.commit()
        return {
            "message_id": message_id,
            "status": status,
            "usage": {"input_tokens": event.input_tokens, "output_tokens": event.output_tokens,
                      "estimated": event.estimated, "cost_usd": event.cost_usd},
            "quota": quota,
        }


@router.post("/stream")
async def chat_stream(body: ChatIn, request: Request):  # type: ignore[no-untyped-def]
    db: Database = request.app.state.db
    settings: Settings = request.app.state.settings
    provider: Provider = request.app.state.provider
    token = request.cookies.get(settings.cookie_name)

    try:
        prepared = await run_in_threadpool(prepare, db, settings, provider, token, body)
    except QuotaExceeded as exc:
        # A normal JSON error, not a stream: the browser can show it without parsing events.
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(exc.retry_after)},
            content={"detail": exc.message, "code": exc.code, "retry_after": exc.retry_after,
                     "quota": exc.snapshot.public()},
        )

    async def events() -> AsyncIterator[bytes]:
        yield sse("meta", {"conversation_id": prepared.conversation_id, "title": prepared.title,
                           "is_new": prepared.is_new, "model": provider.model})
        parts: list[str] = []
        usage: Usage | None = None
        outcome = "completed"
        try:
            async for chunk in provider.stream(prepared.messages, prepared.max_tokens):
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.text:
                    parts.append(chunk.text)
                    yield sse("delta", {"text": chunk.text})
        except ProviderError as exc:
            log.error("provider %s failed: %s", provider.name, exc)
            outcome = "failed"
        except BaseException:
            # The browser closed the connection (stop button, closed tab, lost network). The
            # request is being cancelled, so shield the write that keeps the partial answer.
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(finalise, db, prepared, "".join(parts), usage, "stopped")
            raise

        result = await run_in_threadpool(finalise, db, prepared, "".join(parts), usage, outcome)
        if outcome == "failed":
            charged = result["status"] != "failed"
            yield sse("error", {
                "detail": "The model provider failed. "
                          + ("The partial answer was kept." if charged
                             else "This message was not counted against your limit."),
                **result,
            })
        else:
            yield sse("done", result)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            # Stop proxies from caching, compressing or buffering the stream.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
