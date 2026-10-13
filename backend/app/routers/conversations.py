"""Saved history. Every query filters on the owner."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..deps import current_user, get_db
from ..models import Conversation, Message, User
from ..schemas import ConversationDetail, ConversationOut, MessageOut, RenameIn

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _owned(session: Session, user: User, conversation_id: int) -> Conversation:
    conversation = session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id)
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(404, "Conversation not found.")
    return conversation


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    session: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[Conversation]:
    return list(session.execute(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(100)
    ).scalars())


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int, session: Session = Depends(get_db), user: User = Depends(current_user)
) -> ConversationDetail:
    conversation = _owned(session, user, conversation_id)
    messages = session.execute(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id)
    ).scalars().all()
    return ConversationDetail(
        id=conversation.id, title=conversation.title, created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: int, body: RenameIn,
    session: Session = Depends(get_db), user: User = Depends(current_user),
) -> Conversation:
    conversation = _owned(session, user, conversation_id)
    conversation.title = body.title.strip() or conversation.title
    session.commit()
    return conversation


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: int, session: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    conversation = _owned(session, user, conversation_id)
    # Usage rows stay: the request was served and paid for, whatever happens to the text.
    session.execute(delete(Message).where(Message.conversation_id == conversation.id))
    session.delete(conversation)
    session.commit()
