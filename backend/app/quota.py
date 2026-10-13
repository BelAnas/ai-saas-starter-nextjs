"""Usage limits.

Everything is computed from the `usage_events` table, so what is enforced, what the user sees in
the meter and what the admin page reports can never disagree.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import UsageEvent, User
from .plans import Plan, estimate_cost_usd, get_plan

# A request that produced no output at all is not charged to the user.
COUNTED = ("started", "completed", "stopped")


@dataclass(frozen=True)
class UsageSnapshot:
    plan: str
    messages_used: int
    messages_limit: int
    tokens_used: int
    tokens_limit: int
    resets_at: datetime

    def public(self) -> dict[str, object]:
        return {
            "plan": self.plan,
            "messages_used": self.messages_used,
            "messages_limit": self.messages_limit,
            "tokens_used": self.tokens_used,
            "tokens_limit": self.tokens_limit,
            "resets_at": self.resets_at.isoformat() + "Z",
        }


class QuotaExceeded(Exception):
    def __init__(self, code: str, message: str, retry_after: int, snapshot: UsageSnapshot) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self.snapshot = snapshot


def day_start(now: datetime) -> datetime:
    """Limits reset at midnight UTC: one rule for every user, whatever their time zone."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def snapshot(session: Session, user: User, now: datetime | None = None) -> UsageSnapshot:
    now = now or utcnow()
    plan = get_plan(user.plan)
    start = day_start(now)
    messages, tokens = session.execute(
        select(
            func.count(UsageEvent.id),
            func.coalesce(func.sum(UsageEvent.input_tokens + UsageEvent.output_tokens), 0),
        ).where(
            UsageEvent.user_id == user.id,
            UsageEvent.created_at >= start,
            UsageEvent.status.in_(COUNTED),
        )
    ).one()
    return UsageSnapshot(plan.name, int(messages), plan.daily_messages, int(tokens),
                         plan.daily_tokens, start + timedelta(days=1))


def reserve(
    session: Session, user: User, provider: str, model: str, now: datetime | None = None
) -> UsageEvent:
    """Check the limits and record the request as `started`.

    Must be called in a session opened with `write=True`: the check and the insert then happen
    under the database write lock, so concurrent requests cannot both take the last slot.
    The caller commits.
    """
    now = now or utcnow()
    plan: Plan = get_plan(user.plan)
    snap = snapshot(session, user, now)
    seconds_to_reset = max(1, int((snap.resets_at - now).total_seconds()))

    if snap.messages_used >= plan.daily_messages:
        raise QuotaExceeded(
            "daily_messages",
            f"You have used all {plan.daily_messages} messages of the {plan.label} plan for today.",
            seconds_to_reset, snap,
        )
    if snap.tokens_used >= plan.daily_tokens:
        raise QuotaExceeded(
            "daily_tokens",
            f"You have used the daily token allowance of the {plan.label} plan.",
            seconds_to_reset, snap,
        )

    window_start = now - timedelta(seconds=60)
    recent, oldest = session.execute(
        select(func.count(UsageEvent.id), func.min(UsageEvent.created_at)).where(
            UsageEvent.user_id == user.id,
            UsageEvent.created_at > window_start,
            UsageEvent.status.in_(COUNTED),
        )
    ).one()
    if recent >= plan.burst_per_minute:
        wait = max(1, 60 - int((now - oldest).total_seconds()))
        raise QuotaExceeded(
            "burst",
            f"Too many messages in a short time. Try again in {wait} seconds.",
            wait, snap,
        )

    event = UsageEvent(user_id=user.id, status="started", provider=provider, model=model,
                       created_at=now)
    session.add(event)
    session.flush()
    return event


def finish(
    session: Session, event_id: int, status: str, input_tokens: int, output_tokens: int,
    estimated: bool,
) -> UsageEvent:
    """Fill in the usage row once the stream has ended. The caller commits."""
    event = session.get(UsageEvent, event_id)
    assert event is not None
    event.status = status
    event.input_tokens = input_tokens
    event.output_tokens = output_tokens
    event.estimated = estimated
    event.cost_usd = estimate_cost_usd(event.model, input_tokens, output_tokens)
    event.finished_at = utcnow()
    return event
