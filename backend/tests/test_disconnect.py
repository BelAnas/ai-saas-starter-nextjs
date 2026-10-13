"""Stopping a stream, tested against a real server because an in-process client cannot hang up."""
from __future__ import annotations

import socket
import threading
import time

import httpx
import uvicorn

from app.llm.mock import MockProvider
from app.main import create_app
from app.models import Message, UsageEvent

from .conftest import make_settings


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_closing_the_connection_keeps_the_partial_answer(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(tmp_path), provider=MockProvider(delay_ms=30))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                httpx.get(f"{base}/api/health", timeout=1)
                break
            except httpx.TransportError:
                time.sleep(0.05)

        with httpx.Client(base_url=base, timeout=10) as client:
            client.post("/api/auth/register",
                        json={"email": "sara@example.com", "password": "correct-horse-1"})
            received = ""
            with client.stream("POST", "/api/chat/stream",
                               json={"message": "Write a product description for a mug"}) as response:
                for text in response.iter_text():
                    received += text
                    if received.count("event: delta") >= 5:
                        break  # leaving the block closes the connection mid-answer

            deadline = time.time() + 5
            saved = None
            while time.time() < deadline and saved is None:
                with app.state.db.session() as session:
                    saved = session.query(Message).filter_by(role="assistant").one_or_none()
                    event = session.query(UsageEvent).one()
                time.sleep(0.05)

            assert saved is not None, "the partial answer was not saved"
            assert saved.status == "stopped"
            assert saved.content.startswith("Here is a product description")
            # Far fewer words than the full answer (about 60 pieces at 30 ms each).
            assert len(saved.content.split()) < 30
            assert event.status == "stopped" and event.output_tokens > 0
            # A stopped answer still counts: its tokens were produced.
            assert client.get("/api/account/usage").json()["quota"]["messages_used"] == 1
    finally:
        server.should_exit = True
        thread.join(timeout=5)
