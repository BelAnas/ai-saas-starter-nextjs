"""Demo data: `python -m app.seed`.

Creates an administrator, a demo user and a few synthetic customers with two weeks of usage, so
the admin page has something to show on a fresh install. All of it is generated here from a fixed
random seed; none of it is real customer data. Running it twice changes nothing.
"""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select

from .config import Settings
from .db import Database, utcnow
from .models import Conversation, Message, UsageEvent, User
from .plans import estimate_cost_usd
from .llm.mock import draft_answer
from .quota import day_start
from .security import hash_password

ADMIN = ("admin@example.com", "admin-demo-1", "Shop owner")
DEMO = ("demo@example.com", "demo-demo-1", "Demo user")

# (name, plan, average messages per day): a mix of light and heavy users.
CUSTOMERS = [
    ("Lina (candle shop)", "pro", 34), ("Youssef (bike parts)", "pro", 21),
    ("Marta (ceramics)", "free", 9), ("Tom (board games)", "free", 6),
    ("Aiko (stationery)", "free", 3), ("Noor (plants)", "pro", 12),
]
# Synthetic history is priced as if it had run on this model, so the cost column is not all zeros.
HISTORY_MODEL = "gpt-4o-mini"


def seed(db: Database, days: int = 14, rng_seed: int = 7) -> bool:
    """Returns False when the demo data already exists."""
    rng = random.Random(rng_seed)
    now = utcnow()
    with db.session(write=True) as session:
        if session.execute(select(User.id).where(User.email == ADMIN[0])).first():
            return False

        admin = User(email=ADMIN[0], name=ADMIN[2], role="admin", plan="pro",
                     password_hash=hash_password(ADMIN[1]))
        demo = User(email=DEMO[0], name=DEMO[2], plan="free",
                    password_hash=hash_password(DEMO[1]))
        session.add_all([admin, demo])

        # One throwaway password hash for all synthetic customers: nobody signs in as them.
        locked = hash_password(str(rng.random()))
        for index, (name, plan, per_day) in enumerate(CUSTOMERS, start=1):
            user = User(email=f"customer{index}@example.com", name=name, plan=plan,
                        password_hash=locked,
                        created_at=now - timedelta(days=days + rng.randint(1, 40)))
            session.add(user)
            session.flush()
            # Past days only, so today starts empty and the window is `days` long with today.
            for back in range(days - 1, 0, -1):
                start = day_start(now) - timedelta(days=back)
                weekday_factor = 0.5 if start.weekday() >= 5 else 1.0
                for _ in range(max(0, round(rng.gauss(per_day, per_day * 0.3) * weekday_factor))):
                    tokens_in, tokens_out = rng.randint(120, 900), rng.randint(80, 420)
                    created = start + timedelta(seconds=rng.randint(7 * 3600, 21 * 3600))
                    session.add(UsageEvent(
                        user_id=user.id, status="completed", provider="openai",
                        model=HISTORY_MODEL, input_tokens=tokens_in, output_tokens=tokens_out,
                        cost_usd=estimate_cost_usd(HISTORY_MODEL, tokens_in, tokens_out),
                        created_at=created, finished_at=created + timedelta(seconds=3),
                    ))

        session.flush()
        for offset, prompt in enumerate([
            "Write a product description for a hand-thrown ceramic mug",
            "Reply to a customer whose parcel is three days late",
        ]):
            when = now - timedelta(days=1, hours=offset)
            conversation = Conversation(user_id=demo.id, title=prompt, created_at=when,
                                        updated_at=when)
            session.add(conversation)
            session.flush()
            session.add_all([
                Message(conversation_id=conversation.id, role="user", content=prompt,
                        created_at=when),
                Message(conversation_id=conversation.id, role="assistant",
                        content=draft_answer(prompt), created_at=when),
            ])
        session.commit()
        return True


def main() -> None:
    db = Database(Settings().database_url)
    db.create_tables()
    if seed(db):
        print("Demo data created.")
    else:
        print("Demo data already present, nothing changed.")
    print(f"  admin: {ADMIN[0]} / {ADMIN[1]}")
    print(f"  user:  {DEMO[0]} / {DEMO[1]}")


if __name__ == "__main__":
    main()
