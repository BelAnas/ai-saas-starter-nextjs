"""Measure streaming: time to the first word, total time, and behaviour under parallel streams.

    backend/.venv/bin/python scripts/bench_stream.py                      # API only
    backend/.venv/bin/python scripts/bench_stream.py --web http://localhost:3000   # and through Next.js

The script starts its own API on a free port with a temporary database and the offline provider
(20 ms per word), so the numbers measure this code and not a model. With --web it also sends the
same requests through an already running web app (./dev.sh) to show that the proxy does not hold
the answer back. If a proxy buffered, "first word" would be as late as "whole answer".
"""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1] / "backend"
PROMPT = "Write a product description for a hand-thrown ceramic mug"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def one_stream(client: httpx.AsyncClient) -> tuple[float, float, int]:
    """Returns (seconds to first word, seconds to end, number of pieces)."""
    start = time.perf_counter()
    first, pieces, buffer = 0.0, 0, ""
    async with client.stream("POST", "/api/chat/stream", json={"message": PROMPT}) as response:
        assert response.status_code == 200, (response.status_code, await response.aread())
        async for text in response.aiter_text():
            buffer += text
            seen = buffer.count("event: delta")
            if seen and not first:
                first = time.perf_counter() - start
            pieces = seen
    return first, time.perf_counter() - start, pieces


def ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms"


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


async def sequential(label: str, base: str, login: dict | None, runs: int) -> None:
    results = []
    for index in range(runs + 1):
        async with httpx.AsyncClient(base_url=base, timeout=60) as client:
            if login:
                (await client.post("/api/auth/login", json=login)).raise_for_status()
            else:
                # A new free account per answer, so the per-user burst limit is not what we measure.
                (await client.post("/api/auth/register", json={
                    "email": f"bench{index}@example.com", "password": "correct-horse-1"})).raise_for_status()
            results.append(await one_stream(client))
    results = results[1:]  # the first answer is a warm-up
    firsts, totals = [r[0] for r in results], [r[1] for r in results]
    print(f"{label}: {runs} answers of {results[0][2]} pieces | first word median "
          f"{ms(statistics.median(firsts))} (max {ms(max(firsts))}) | whole answer median "
          f"{ms(statistics.median(totals))}")


async def parallel(base: str, users: int) -> None:
    limits = httpx.Limits(max_connections=users + 10)
    clients = [httpx.AsyncClient(base_url=base, timeout=120, limits=limits) for _ in range(users)]
    try:
        # One account per stream: the per-user burst limit would refuse them otherwise.
        for index, client in enumerate(clients):
            (await client.post("/api/auth/register", json={
                "email": f"load{index}@example.com", "password": "correct-horse-1"})).raise_for_status()
        start = time.perf_counter()
        results = await asyncio.gather(*[one_stream(c) for c in clients])
        wall = time.perf_counter() - start
    finally:
        await asyncio.gather(*[c.aclose() for c in clients])
    firsts, totals = [r[0] for r in results], [r[1] for r in results]
    print(f"parallel: {users} streams at once on one API process | all completed in {wall:.2f} s | "
          f"first word p50 {ms(pct(firsts, 0.5))}, p95 {ms(pct(firsts, 0.95))} | "
          f"whole answer p50 {ms(pct(totals, 0.5))}, p95 {ms(pct(totals, 0.95))}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", help="URL of a running web app, to measure through its proxy")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--users", type=int, default=100)
    args = parser.parse_args()

    port = free_port()
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp}/bench.db", "LLM_PROVIDER": "mock",
               "MOCK_DELAY_MS": "20"}
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
             "--port", str(port), "--log-level", "warning"], cwd=BACKEND, env=env)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    httpx.get(f"{base}/api/health", timeout=1)
                    break
                except httpx.TransportError:
                    time.sleep(0.1)
            await sequential("direct to the API", base, None, args.runs)
            await parallel(base, args.users)
        finally:
            server.terminate()
            server.wait(timeout=10)

    if args.web:
        # The seeded admin is on the Pro plan (30 messages a minute), enough for the runs.
        await sequential("through the Next.js proxy", args.web.rstrip("/"),
                         {"email": "admin@example.com", "password": "admin-demo-1"}, args.runs)


if __name__ == "__main__":
    asyncio.run(main())
