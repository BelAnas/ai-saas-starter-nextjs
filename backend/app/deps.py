"""FastAPI dependencies: a database session and the signed-in user."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import Database, utcnow
from .models import AuthSession, User
from .security import hash_token


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.db
    # Requests that change data take the write lock from their first query (see db.py).
    with database.session(write=request.method not in ("GET", "HEAD")) as session:
        yield session


def user_from_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = session.execute(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.expires_at > utcnow())
    ).scalar_one_or_none()
    return row if row is not None and row.is_active else None


def current_user(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    user = user_from_token(session, request.cookies.get(settings.cookie_name))
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="This page is for administrators.")
    return user
