from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import plans
from app.db import utcnow
from app.models import UsageEvent

from .conftest import chat, new_client, parse_sse, register, set_plan


def tiny_plan(monkeypatch, messages: int = 3, tokens: int = 20_000, burst: int = 100) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setitem(plans.PLANS, "free",
                        plans.Plan("free", "Free", 0, messages, tokens, burst, 400))


def test_daily_message_limit(app, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tiny_plan(monkeypatch, messages=3)
    register(client)
    for _ in range(3):
        assert chat(client, "hello").status_code == 200
    blocked = chat(client, "one more")
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "daily_messages"
    assert body["quota"]["messages_used"] == 3 and body["quota"]["messages_limit"] == 3
    assert 0 < int(blocked.headers["retry-after"]) <= 86_400
    # The refused message was not saved anywhere.
    assert sum(len(client.get(f"/api/conversations/{c['id']}").json()["messages"])
               for c in client.get("/api/conversations").json()) == 6


def test_limit_is_per_user(app, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tiny_plan(monkeypatch, messages=1)
    register(client)
    assert chat(client, "hello").status_code == 200
    assert chat(client, "hello").status_code == 429
    other = new_client(app, "omar@example.com")
    assert chat(other, "hello").status_code == 200


def test_upgrade_lifts_the_limit_at_once(app, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tiny_plan(monkeypatch, messages=1)
    register(client)
    chat(client, "hello")
    assert chat(client, "hello").status_code == 429
    set_plan(app, "sara@example.com", "pro")
    assert chat(client, "hello").status_code == 200
    assert client.get("/api/account/usage").json()["quota"]["messages_limit"] == 500


def test_daily_token_limit(app, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tiny_plan(monkeypatch, messages=50, tokens=30)
    register(client)
    assert chat(client, "Write a product description").status_code == 200  # uses more than 30
    blocked = chat(client, "again")
    assert blocked.status_code == 429 and blocked.json()["code"] == "daily_tokens"


def test_burst_limit(app, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tiny_plan(monkeypatch, messages=50, burst=2)
    register(client)
    assert chat(client, "a").status_code == 200
    assert chat(client, "b").status_code == 200
    blocked = chat(client, "c")
    assert blocked.status_code == 429 and blocked.json()["code"] == "burst"
    assert 1 <= blocked.json()["retry_after"] <= 60


def test_limit_resets_at_midnight_utc(app, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tiny_plan(monkeypatch, messages=1)
    register(client)
    chat(client, "hello")
    assert chat(client, "hello").status_code == 429
    # Move the recorded request to yesterday instead of waiting for midnight.
    with app.state.db.session(write=True) as session:
        session.query(UsageEvent).update({"created_at": utcnow() - timedelta(days=1)})
        session.commit()
    assert chat(client, "hello").status_code == 200


def test_usage_endpoint_matches_what_was_streamed(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    total = 0
    for text in ("Describe a mug", "Reply to a late parcel email"):
        usage = parse_sse(chat(client, text).text)[-1][1]["usage"]
        total += usage["input_tokens"] + usage["output_tokens"]
    report = client.get("/api/account/usage").json()
    assert report["quota"]["messages_used"] == 2
    assert report["quota"]["tokens_used"] == total
    assert report["last_7_days"][-1]["messages"] == 2 and len(report["last_7_days"]) == 7
    assert report["plan"]["daily_messages"] == 20


@pytest.mark.parametrize("limit,parallel", [(20, 50)])
async def test_parallel_requests_cannot_exceed_the_limit(app, monkeypatch, limit, parallel) -> None:  # type: ignore[no-untyped-def]
    """The race this design exists for: many requests arrive at once with few slots left."""
    tiny_plan(monkeypatch, messages=limit, burst=10_000)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/auth/register",
                                    json={"email": "race@example.com", "password": "correct-horse-1"})
        assert created.status_code == 201
        responses = await asyncio.gather(*[
            client.post("/api/chat/stream", json={"message": f"request {i}"})
            for i in range(parallel)
        ])
    codes = [r.status_code for r in responses]
    assert codes.count(200) == limit
    assert codes.count(429) == parallel - limit
    with app.state.db.session() as session:
        assert session.query(UsageEvent).filter_by(status="completed").count() == limit
