"""Test fixtures: every test gets a fresh SQLite file and the offline mock provider."""
from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.mock import MockProvider
from app.main import create_app
from app.models import User


def make_settings(tmp_path, **overrides) -> Settings:  # type: ignore[no-untyped-def]
    values = {
        "database_url": f"sqlite:///{tmp_path / 'test.db'}",
        "llm_provider": "mock",
        "mock_delay_ms": 0,
        **overrides,
    }
    # _env_file=None: a developer's own .env must not change test results.
    return Settings(_env_file=None, **values)


@pytest.fixture()
def app(tmp_path):  # type: ignore[no-untyped-def]
    return create_app(make_settings(tmp_path), provider=MockProvider(delay_ms=0))


@pytest.fixture()
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, email: str = "sara@example.com",
             password: str = "correct-horse-1") -> dict:
    response = client.post("/api/auth/register",
                           json={"email": email, "password": password, "name": "Sara"})
    assert response.status_code == 201, response.text
    return response.json()


def new_client(app, email: str) -> TestClient:  # type: ignore[no-untyped-def]
    """A second browser with its own cookie jar, signed in as another user."""
    other = TestClient(app)
    register(other, email)
    return other


def make_admin(app, email: str) -> None:  # type: ignore[no-untyped-def]
    with app.state.db.session(write=True) as session:
        user = session.query(User).filter_by(email=email).one()
        user.role = "admin"
        session.commit()


def set_plan(app, email: str, plan: str) -> None:  # type: ignore[no-untyped-def]
    with app.state.db.session(write=True) as session:
        session.query(User).filter_by(email=email).one().plan = plan
        session.commit()


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        name, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if data:
            events.append((name, json.loads(data)))
    return events


def chat(client: TestClient, message: str, conversation_id: int | None = None):  # type: ignore[no-untyped-def]
    return client.post("/api/chat/stream",
                       json={"message": message, "conversation_id": conversation_id})
