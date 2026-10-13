"""Owner reporting and user controls. Every route requires the admin role."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..deps import admin_user, get_db
from ..models import AuthSession, UsageEvent, User
from ..plans import PLANS, get_plan
from ..quota import COUNTED, day_start
from ..reports import daily_series
from ..schemas import AdminUserPatch

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/overview")
def overview(
    days: int = Query(14, ge=1, le=90), session: Session = Depends(get_db)
) -> dict[str, object]:
    now = utcnow()
    series = daily_series(session, now, days)
    today = series[-1]
    plan_counts = dict(session.execute(select(User.plan, func.count(User.id)).group_by(User.plan)).all())
    failed = session.execute(
        select(func.count(UsageEvent.id)).where(
            UsageEvent.created_at >= day_start(now) - timedelta(days=days - 1),
            UsageEvent.status == "failed")
    ).scalar_one()
    return {
        "days": days,
        "today": today,
        "totals": {
            "users": sum(plan_counts.values()),
            "messages": sum(int(d["messages"]) for d in series),
            "tokens": sum(int(d["tokens"]) for d in series),
            "cost_usd": round(sum(float(d["cost_usd"]) for d in series), 4),
            "failed_requests": failed,
            # What the paying plans bring in per month at list price, to set against the cost.
            "monthly_revenue_usd": sum(
                PLANS[name].price_usd_month * count
                for name, count in plan_counts.items() if name in PLANS),
        },
        "plans": [{"plan": name, "users": plan_counts.get(name, 0)} for name in PLANS],
        "series": series,
    }


@router.get("/users")
def users(session: Session = Depends(get_db)) -> list[dict[str, object]]:
    now = utcnow()
    today, month = day_start(now), day_start(now) - timedelta(days=29)
    is_today = UsageEvent.created_at >= today
    tokens = UsageEvent.input_tokens + UsageEvent.output_tokens
    rows = session.execute(
        select(
            User,
            func.coalesce(func.sum(case((is_today, 1), else_=0)), 0),
            func.coalesce(func.sum(case((is_today, tokens), else_=0)), 0),
            func.count(UsageEvent.id),
            func.coalesce(func.sum(tokens), 0),
            func.coalesce(func.sum(UsageEvent.cost_usd), 0.0),
            func.max(UsageEvent.created_at),
        )
        .outerjoin(UsageEvent, (UsageEvent.user_id == User.id)
                   & (UsageEvent.created_at >= month) & UsageEvent.status.in_(COUNTED))
        .group_by(User.id)
        .order_by(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0).desc(),
                  func.count(UsageEvent.id).desc(), User.id)
    ).all()
    out: list[dict[str, object]] = []
    for user, messages_today, tokens_today, messages_30d, tokens_30d, cost_30d, last_used in rows:
        plan = get_plan(user.plan)
        out.append({
            "id": user.id, "email": user.email, "name": user.name, "role": user.role,
            "plan": user.plan, "is_active": user.is_active,
            "created_at": user.created_at.isoformat() + "Z",
            "messages_today": int(messages_today), "messages_limit": plan.daily_messages,
            "tokens_today": int(tokens_today),
            "messages_30d": int(messages_30d), "tokens_30d": int(tokens_30d),
            "cost_30d_usd": round(float(cost_30d), 4),
            "last_used_at": last_used.isoformat() + "Z" if last_used else None,
        })
    return out


@router.patch("/users/{user_id}")
def update_user(
    user_id: int, body: AdminUserPatch,
    session: Session = Depends(get_db), admin: User = Depends(admin_user),
) -> dict[str, object]:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found.")
    if body.plan is not None:
        user.plan = body.plan
    if body.is_active is not None:
        if user.id == admin.id and not body.is_active:
            raise HTTPException(409, "You cannot deactivate your own account.")
        user.is_active = body.is_active
        if not body.is_active:
            # Sign the user out everywhere at once.
            session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    session.commit()
    return {"id": user.id, "plan": user.plan, "is_active": user.is_active}
