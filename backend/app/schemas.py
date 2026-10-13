"""Request and response shapes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer

# Stored times are naive UTC; send them with a "Z" so the browser does not read them as local time.
UtcDatetime = Annotated[
    datetime,
    PlainSerializer(
        lambda d: d.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        return_type=str,
    ),
]


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=80)


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    role: str
    plan: str
    is_active: bool
    created_at: UtcDatetime


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: int | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    status: str
    created_at: UtcDatetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=128)


class AdminUserPatch(BaseModel):
    plan: Literal["free", "pro"] | None = None
    is_active: bool | None = None
