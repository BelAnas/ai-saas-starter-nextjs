"""Database engine and sessions.

SQLite allows one writer at a time. A transaction that starts with a read and later writes can fail
with "database is locked" when another writer got in between. To make "check the quota, then
record the request" safe, write requests open their transaction with BEGIN IMMEDIATE, which takes
the write lock up front, so two requests can never both see the same free slot.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC. SQLite has no timezone type, so every stored time is UTC by convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.is_sqlite = url.startswith("sqlite")
        if self.is_sqlite:
            path = url.split("///", 1)[-1]
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.engine: Engine = create_engine(
                url, connect_args={"check_same_thread": False, "timeout": 15}
            )
            self._configure_sqlite()
        else:
            self.engine = create_engine(url, pool_pre_ping=True)

    def _configure_sqlite(self) -> None:
        @event.listens_for(self.engine, "connect")
        def _on_connect(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
            # Turn off the driver's own transaction handling: we emit BEGIN ourselves below.
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")  # readers do not block the writer
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        @event.listens_for(self.engine, "begin")
        def _on_begin(conn) -> None:  # type: ignore[no-untyped-def]
            mode = "IMMEDIATE" if conn.get_execution_options().get("write_lock") else "DEFERRED"
            conn.exec_driver_sql(f"BEGIN {mode}")

    def create_tables(self) -> None:
        from . import models  # noqa: F401  (registers the tables on Base)

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self, write: bool = False) -> Iterator[Session]:
        """A session on its own connection. `write=True` takes the write lock at the first query."""
        with self.engine.connect() as conn:
            if write:
                conn = conn.execution_options(write_lock=True)
            with Session(bind=conn, expire_on_commit=False) as session:
                yield session
