from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import AuthSession, User
from app.security import hash_password, verify_password

from .conftest import register


def test_password_hash_roundtrip() -> None:
    stored = hash_password("correct-horse-1")
    assert "correct-horse-1" not in stored
    assert verify_password("correct-horse-1", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("x", "not-a-hash")
    # A fresh salt every time: equal passwords do not give equal hashes.
    assert stored != hash_password("correct-horse-1")


def test_register_signs_in_and_sets_httponly_cookie(client: TestClient) -> None:
    response = client.post("/api/auth/register",
                           json={"email": "Sara@Example.com", "password": "correct-horse-1"})
    assert response.status_code == 201
    assert response.json()["email"] == "sara@example.com"
    assert response.json()["plan"] == "free" and response.json()["role"] == "user"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["email"] == "sara@example.com"


def test_register_rejects_duplicate_weak_password_and_bad_email(client: TestClient) -> None:
    register(client)
    again = client.post("/api/auth/register",
                        json={"email": "sara@example.com", "password": "correct-horse-1"})
    assert again.status_code == 409
    assert client.post("/api/auth/register",
                       json={"email": "b@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/auth/register",
                       json={"email": "not-an-email", "password": "long-enough-1"}).status_code == 422


def test_password_and_cookie_are_not_stored_in_clear(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    token = client.cookies.get(app.state.settings.cookie_name)
    with app.state.db.session() as session:
        user = session.query(User).one()
        stored_session = session.query(AuthSession).one()
    assert user.password_hash.startswith("scrypt$")
    assert stored_session.token_hash != token and len(stored_session.token_hash) == 64


def test_me_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("shopdesk_session", "forged-value")
    assert client.get("/api/auth/me").status_code == 401


def test_login_logout(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    bad = client.post("/api/auth/login", json={"email": "sara@example.com", "password": "nope"})
    unknown = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    # Same answer for a wrong password and an unknown email.
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()

    ok = client.post("/api/auth/login",
                     json={"email": "sara@example.com", "password": "correct-horse-1"})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_logout_revokes_a_copied_cookie(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    name = app.state.settings.cookie_name
    stolen = client.cookies.get(name)
    client.post("/api/auth/logout")
    thief = TestClient(app)
    thief.cookies.set(name, stolen)
    assert thief.get("/api/auth/me").status_code == 401


def test_login_locks_after_repeated_failures(client: TestClient) -> None:
    register(client)
    client.post("/api/auth/logout")
    for _ in range(5):
        assert client.post("/api/auth/login",
                           json={"email": "sara@example.com", "password": "nope"}).status_code == 401
    locked = client.post("/api/auth/login",
                         json={"email": "sara@example.com", "password": "correct-horse-1"})
    assert locked.status_code == 429
