"""One real request through the whole API, against a real model.

OpenAI (the key is read from the environment, never stored in the project):
    OPENAI_API_KEY=... backend/.venv/bin/python scripts/live_check.py

A local model served by Ollama, which speaks the same protocol and needs no key:
    OPENAI_BASE_URL=http://127.0.0.1:11434/v1 OPENAI_MODEL=llama3.2 \\
        backend/.venv/bin/python scripts/live_check.py

It starts the API on a free port with a temporary database, registers a user, sends one short
request and prints what was streamed and what was recorded for billing.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1] / "backend"
PROMPT = "Write a two-sentence product description for a hand-thrown ceramic mug."


def main() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp}/live.db", "LLM_PROVIDER": "openai"}
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
             "--port", str(port), "--log-level", "warning"], cwd=BACKEND, env=env)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    health = httpx.get(f"{base}/api/health", timeout=1).json()
                    break
                except httpx.TransportError:
                    time.sleep(0.1)
            print(f"provider: {health['provider']}  model: {health['model']}")

            with httpx.Client(base_url=base, timeout=300) as client:
                client.post("/api/auth/register", json={
                    "email": "live@example.com", "password": "correct-horse-1"}).raise_for_status()
                start = time.perf_counter()
                first, text, end, name = None, "", None, ""
                with client.stream("POST", "/api/chat/stream", json={"message": PROMPT}) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line.startswith("event:"):
                            name = line[6:].strip()
                        elif line.startswith("data:"):
                            data = json.loads(line[5:])
                            if name == "delta":
                                first = first or time.perf_counter() - start
                                text += data["text"]
                            elif name in ("done", "error"):
                                end = (name, data)
                total = time.perf_counter() - start
                usage = client.get("/api/account/usage").json()["quota"]

            print(f"answer: {text.strip()}")
            if end is None or end[0] != "done" or not text.strip():
                print(f"LIVE CHECK FAILED: {end}")
                return 1
            recorded = end[1]["usage"]
            source = "estimated by the app" if recorded["estimated"] else "reported by the provider"
            print(f"first word after {first:.2f} s, whole answer after {total:.2f} s")
            print(f"tokens: {recorded['input_tokens']} in, {recorded['output_tokens']} out ({source})")
            print(f"estimated cost: ${recorded['cost_usd']:.6f}")
            print(f"quota after the request: {usage['messages_used']} message, {usage['tokens_used']} tokens")
            print("LIVE CHECK PASSED")
            return 0
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
