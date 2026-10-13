from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.llm.base import ChatMessage, ProviderError, StreamChunk
from app.llm.mock import MockProvider, draft_answer
from app.main import create_app
from app.models import Message, UsageEvent

from .conftest import chat, make_settings, new_client, parse_sse, register


def test_stream_requires_sign_in(client: TestClient) -> None:
    assert chat(client, "hello").status_code == 401


def test_stream_sends_meta_deltas_done_and_saves_history(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    response = chat(client, "Write a product description for a ceramic mug")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done" and names.count("delta") > 10

    answer = "".join(data["text"] for name, data in events if name == "delta")
    assert answer == draft_answer("Write a product description for a ceramic mug")

    done = events[-1][1]
    assert done["status"] == "completed"
    assert done["usage"]["input_tokens"] > 0 and done["usage"]["output_tokens"] > 0
    assert done["quota"]["messages_used"] == 1

    conversation_id = events[0][1]["conversation_id"]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == answer
    assert detail["title"] == "Write a product description for a ceramic mug"
    assert detail["created_at"].endswith("Z")


def test_follow_up_goes_to_same_conversation_with_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    seen: list[list[ChatMessage]] = []

    class Recorder(MockProvider):
        async def stream(self, messages, max_tokens):  # type: ignore[no-untyped-def]
            seen.append(messages)
            async for chunk in super().stream(messages, max_tokens):
                yield chunk

    app = create_app(make_settings(tmp_path, context_messages=3), provider=Recorder(delay_ms=0))
    client = TestClient(app)
    register(client)
    first = parse_sse(chat(client, "Reply to a customer about a late parcel").text)
    conversation_id = first[0][1]["conversation_id"]
    second = parse_sse(chat(client, "Make it shorter", conversation_id).text)
    assert second[0][1]["conversation_id"] == conversation_id and not second[0][1]["is_new"]
    assert len(client.get("/api/conversations").json()) == 1

    # The model gets the system prompt, then the history, capped at `context_messages`.
    assert [m.role for m in seen[1]] == ["system", "user", "assistant", "user"]
    chat(client, "And friendlier", conversation_id)
    # Five messages exist now; only the last three are sent.
    assert [m.role for m in seen[2]] == ["system", "user", "assistant", "user"]
    assert seen[2][1].content == "Make it shorter"
    assert seen[2][-1].content == "And friendlier"


def test_input_validation(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    assert chat(client, "   ").status_code == 422
    assert chat(client, "x" * (app.state.settings.max_input_chars + 1)).status_code == 413
    assert chat(client, "hello", conversation_id=999).status_code == 404
    # Rejected input never reaches the quota.
    assert client.get("/api/account/usage").json()["quota"]["messages_used"] == 0


def test_conversations_are_private(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    conversation_id = parse_sse(chat(client, "Secret launch plan").text)[0][1]["conversation_id"]
    other = new_client(app, "omar@example.com")

    assert other.get("/api/conversations").json() == []
    assert other.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert other.patch(f"/api/conversations/{conversation_id}", json={"title": "mine"}).status_code == 404
    assert other.delete(f"/api/conversations/{conversation_id}").status_code == 404
    # Writing into someone else's conversation is refused and not charged.
    assert chat(other, "append this", conversation_id).status_code == 404
    assert other.get("/api/account/usage").json()["quota"]["messages_used"] == 0
    assert len(client.get(f"/api/conversations/{conversation_id}").json()["messages"]) == 2


def test_rename_and_delete(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    register(client)
    conversation_id = parse_sse(chat(client, "Shipping policy FAQ").text)[0][1]["conversation_id"]
    renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": "FAQ draft"})
    assert renamed.json()["title"] == "FAQ draft"
    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert client.get("/api/conversations").json() == []
    with app.state.db.session() as session:
        assert session.query(Message).count() == 0
        # The usage row survives: the request was served.
        assert session.query(UsageEvent).count() == 1


class FailingProvider:
    name, model = "broken", "broken-1"

    def __init__(self, pieces_before_failure: int) -> None:
        self.pieces = pieces_before_failure

    async def stream(self, messages: list[ChatMessage], max_tokens: int) -> AsyncIterator[StreamChunk]:
        for index in range(self.pieces):
            yield StreamChunk(text=f"piece{index} ")
        raise ProviderError("upstream exploded: secret-internal-detail")


def test_provider_failure_without_output_is_not_charged(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(tmp_path), provider=FailingProvider(0))
    client = TestClient(app)
    register(client)
    events = parse_sse(chat(client, "hello").text)
    assert [name for name, _ in events] == ["meta", "error"]
    assert "not counted" in events[-1][1]["detail"]
    # Internal error text stays in the server log.
    assert "secret-internal-detail" not in str(events)
    assert client.get("/api/account/usage").json()["quota"]["messages_used"] == 0
    with app.state.db.session() as session:
        assert session.query(UsageEvent).one().status == "failed"
        assert session.query(Message).filter_by(role="assistant").count() == 0


def test_provider_failure_after_partial_output_keeps_and_charges_it(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(tmp_path), provider=FailingProvider(3))
    client = TestClient(app)
    register(client)
    events = parse_sse(chat(client, "hello").text)
    assert [name for name, _ in events] == ["meta", "delta", "delta", "delta", "error"]
    assert client.get("/api/account/usage").json()["quota"]["messages_used"] == 1
    with app.state.db.session() as session:
        saved = session.query(Message).filter_by(role="assistant").one()
        assert saved.content == "piece0 piece1 piece2 " and saved.status == "error"
        event = session.query(UsageEvent).one()
        assert event.status == "stopped" and event.estimated and event.output_tokens > 0


def test_output_is_capped_by_the_plan(app, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app import plans
    monkeypatch.setitem(plans.PLANS, "free", plans.Plan("free", "Free", 0, 20, 20_000, 5, 10))
    register(client)
    done = parse_sse(chat(client, "Write a product description for a mug").text)[-1][1]
    assert 0 < done["usage"]["output_tokens"] <= 10
