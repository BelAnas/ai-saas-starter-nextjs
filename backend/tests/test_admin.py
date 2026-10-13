from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import AuthSession, Conversation, Message, UsageEvent, User
from app.seed import ADMIN, CUSTOMERS, DEMO, seed

from .conftest import chat, make_admin, new_client, register


def test_admin_routes_are_closed_to_everyone_else(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    for path in ("/api/admin/overview", "/api/admin/users"):
        assert client.get(path).status_code == 401
    register(client)
    for path in ("/api/admin/overview", "/api/admin/users"):
        assert client.get(path).status_code == 403
    assert client.patch("/api/admin/users/1", json={"plan": "pro"}).status_code == 403
    assert client.get("/api/auth/me").json()["plan"] == "free"


def test_overview_and_user_table_add_up(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client, "owner@example.com")
    make_admin(app, "owner@example.com")
    sara = new_client(app, "sara@example.com")
    for text in ("Describe a mug", "Describe a bowl", "Describe a plate"):
        chat(sara, text)
    chat(client, "Reply to a late parcel email")

    overview = client.get("/api/admin/overview?days=7").json()
    assert len(overview["series"]) == 7
    assert overview["today"]["messages"] == 4 and overview["today"]["active_users"] == 2
    assert overview["totals"]["users"] == 2 and overview["totals"]["messages"] == 4
    assert overview["plans"] == [{"plan": "free", "users": 2}, {"plan": "pro", "users": 0}]

    users = {u["email"]: u for u in client.get("/api/admin/users").json()}
    assert users["sara@example.com"]["messages_today"] == 3
    assert users["owner@example.com"]["messages_today"] == 1
    # The admin totals are the sum of the per-user rows: one source for both.
    assert sum(u["tokens_today"] for u in users.values()) == overview["today"]["tokens"]
    # The user's own meter shows the same number as the admin table.
    assert sara.get("/api/account/usage").json()["quota"]["tokens_used"] == \
        users["sara@example.com"]["tokens_today"]


def test_admin_changes_plan_and_deactivates(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client, "owner@example.com")
    make_admin(app, "owner@example.com")
    sara = new_client(app, "sara@example.com")
    sara_id = sara.get("/api/auth/me").json()["id"]
    owner_id = client.get("/api/auth/me").json()["id"]

    assert client.patch(f"/api/admin/users/{sara_id}", json={"plan": "pro"}).json()["plan"] == "pro"
    assert sara.get("/api/account/usage").json()["quota"]["messages_limit"] == 500
    assert client.patch(f"/api/admin/users/{sara_id}", json={"plan": "gold"}).status_code == 422

    assert client.patch(f"/api/admin/users/{sara_id}", json={"is_active": False}).status_code == 200
    # Signed out at once, and cannot sign in again.
    assert sara.get("/api/auth/me").status_code == 401
    assert sara.post("/api/auth/login", json={"email": "sara@example.com",
                                              "password": "correct-horse-1"}).status_code == 401

    assert client.patch(f"/api/admin/users/{owner_id}", json={"is_active": False}).status_code == 409
    assert client.patch("/api/admin/users/9999", json={"plan": "pro"}).status_code == 404


def test_delete_account_removes_content_but_keeps_cost_history(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    chat(client, "Describe a mug")
    assert client.post("/api/account/delete", json={"password": "wrong"}).status_code == 403
    assert client.post("/api/account/delete", json={"password": "correct-horse-1"}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    with app.state.db.session() as session:
        assert session.query(User).count() == 0
        assert session.query(Conversation).count() == 0
        assert session.query(Message).count() == 0
        assert session.query(AuthSession).count() == 0
        kept = session.query(UsageEvent).one()
        assert kept.user_id is None and kept.output_tokens > 0


def test_last_admin_cannot_delete_their_account(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client, "owner@example.com")
    make_admin(app, "owner@example.com")
    assert client.post("/api/account/delete", json={"password": "correct-horse-1"}).status_code == 409


def test_plans_endpoint_is_public(client: TestClient) -> None:
    plans = client.get("/api/plans").json()
    assert [p["name"] for p in plans] == ["free", "pro"]
    assert plans[0]["daily_messages"] == 20 and plans[1]["price_usd_month"] == 19


def test_seed_is_repeatable_and_usable(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    assert seed(app.state.db) is True
    assert seed(app.state.db) is False
    with app.state.db.session() as session:
        assert session.query(User).count() == 2 + len(CUSTOMERS)
        events = session.query(UsageEvent).count()
    assert events > 500

    assert client.post("/api/auth/login",
                       json={"email": DEMO[0], "password": DEMO[1]}).status_code == 200
    assert len(client.get("/api/conversations").json()) == 2
    # History is in the past: the demo user starts the day with a full allowance.
    assert client.get("/api/account/usage").json()["quota"]["messages_used"] == 0

    admin = TestClient(app)
    assert admin.post("/api/auth/login",
                      json={"email": ADMIN[0], "password": ADMIN[1]}).status_code == 200
    overview = admin.get("/api/admin/overview").json()
    assert overview["totals"]["messages"] == events and overview["totals"]["cost_usd"] > 0
    assert overview["totals"]["monthly_revenue_usd"] == 19 * 4  # three pro customers and the admin
