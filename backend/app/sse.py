"""Server-Sent Events formatting."""
from __future__ import annotations

import json


def sse(event: str, data: dict[str, object]) -> bytes:
    """One event. JSON keeps the payload on a single `data:` line, even when the text has newlines."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()
