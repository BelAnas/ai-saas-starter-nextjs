"""What a user can see and do about their own account."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..deps import current_user, get_db, get_settings
from ..models import AuthSession, Conversation, Message, UsageEvent, User
from ..plans import PLANS, get_plan
from ..quota import snapshot
from ..reports import daily_series
from ..schemas import DeleteAccountIn
from ..security import verify_password

router = APIRouter(prefix="/api", tags=["account"])


@router.get("/plans")
def plans() -> list[dict[str, object]]:
    """Public: the landing page shows the same limits the server enforces."""
    return [plan.public() for plan in PLANS.values()]


@router.get("/account/usage")
def usage(
    session: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[str, object]:
    now = utcnow()
    return {
        "quota": snapshot(session, user, now).public(),
        "plan": get_plan(user.plan).public(),
        "last_7_days": daily_series(session, now, 7, user_id=user.id),
    }


def delete_user_data(session: Session, user: User) -> None:
    """Remove a user and their content. Usage rows are kept without the user id, so the cost
    history stays correct while nothing in it points to a person any more."""
    conversation_ids = select(Conversation.id).where(Conversation.user_id == user.id)
    session.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    session.execute(delete(Conversation).where(Conversation.user_id == user.id))
    session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    session.execute(
        update(UsageEvent).where(UsageEvent.user_id == user.id)
        .values(user_id=None, conversation_id=None)
    )
    session.delete(user)


@router.post("/account/delete", status_code=204)
def delete_account(
    body: DeleteAccountIn, response: Response,
    session: Session = Depends(get_db), user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> None:
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(403, "Wrong password.")
    if user.role == "admin":
        others = session.execute(
            select(User.id).where(User.role == "admin", User.id != user.id, User.is_active)
        ).first()
        if others is None:
            raise HTTPException(409, "The last administrator cannot delete their account.")
    delete_user_data(session, user)
    session.commit()
    response.delete_cookie(settings.cookie_name, path="/")
