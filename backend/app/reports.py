"""Usage reporting queries, shared by the account page and the admin page."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import UsageEvent
from .quota import COUNTED, day_start


def daily_series(session: Session, now: datetime, days: int,
                 user_id: int | None = None) -> list[dict[str, object]]:
    """One entry per day, oldest first, with zeros for days without usage."""
    first = day_start(now) - timedelta(days=days - 1)
    day = func.date(UsageEvent.created_at)
    query = (
        select(
            day,
            func.count(UsageEvent.id),
            func.coalesce(func.sum(UsageEvent.input_tokens + UsageEvent.output_tokens), 0),
            func.coalesce(func.sum(UsageEvent.cost_usd), 0.0),
            func.count(func.distinct(UsageEvent.user_id)),
        )
        .where(UsageEvent.created_at >= first, UsageEvent.status.in_(COUNTED))
        .group_by(day)
    )
    if user_id is not None:
        query = query.where(UsageEvent.user_id == user_id)
    found = {str(row[0]): row for row in session.execute(query)}
    series: list[dict[str, object]] = []
    for offset in range(days):
        key = (first + timedelta(days=offset)).date().isoformat()
        row = found.get(key)
        series.append({
            "date": key,
            "messages": int(row[1]) if row else 0,
            "tokens": int(row[2]) if row else 0,
            "cost_usd": round(float(row[3]), 6) if row else 0.0,
            "active_users": int(row[4]) if row else 0,
        })
    return series
