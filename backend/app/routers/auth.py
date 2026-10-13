"""Accounts and sessions."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..deps import current_user, get_db, get_settings
from ..models import AuthSession, LoginAttempt, User
from ..schemas import LoginIn, RegisterIn, UserOut
from ..security import DUMMY_HASH, hash_password, hash_token, new_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def start_session(session: Session, user: User, response: Response, settings: Settings) -> None:
    token, token_hash = new_session_token()
    lifetime = timedelta(days=settings.session_days)
    session.add(AuthSession(user_id=user.id, token_hash=token_hash,
                            expires_at=utcnow() + lifetime))
    response.set_cookie(
        settings.cookie_name, token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,  # JavaScript cannot read it, so a script injected in the page cannot steal it
        samesite="lax",  # not sent on cross-site POSTs, which blocks the usual CSRF attack
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(
    body: RegisterIn, response: Response,
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> User:
    if not settings.registration_open:
        raise HTTPException(403, "Registration is closed.")
    email = body.email.strip().lower()
    if session.execute(select(User.id).where(User.email == email)).first():
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    session.add(user)
    session.flush()
    start_session(session, user, response, settings)
    session.commit()
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginIn, response: Response,
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> User:
    email = body.email.strip().lower()
    window_start = utcnow() - timedelta(minutes=settings.login_window_minutes)
    failures = session.execute(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.email == email, LoginAttempt.created_at > window_start)
    ).scalar_one()
    if failures >= settings.login_max_failures:
        raise HTTPException(
            429, f"Too many failed sign-ins. Try again in {settings.login_window_minutes} minutes.")

    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        session.add(LoginAttempt(email=email))
        session.commit()
        # One message for every failure, so the form does not reveal which emails have an account.
        raise HTTPException(401, "Wrong email or password.")

    session.execute(delete(LoginAttempt).where(LoginAttempt.email == email))
    start_session(session, user, response, settings)
    session.commit()
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request, response: Response,
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> None:
    token = request.cookies.get(settings.cookie_name)
    if token:
        # Deleting the row is what signs the browser out: a copied cookie stops working too.
        session.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        session.commit()
    response.delete_cookie(settings.cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
