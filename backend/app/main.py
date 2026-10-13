"""Application factory. Run with: uvicorn app.main:create_app --factory"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from .config import Settings
from .db import Database
from .llm import Provider, build_provider
from .routers import account, admin, auth, chat, conversations


def create_app(settings: Settings | None = None, provider: Provider | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    app = FastAPI(title="Shopdesk AI API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    # State lives on the app, not in module globals, so each test gets its own database and
    # provider.
    app.state.settings = settings
    app.state.db = Database(settings.database_url)
    app.state.db.create_tables()
    app.state.provider = provider or build_provider(settings)

    for module in (auth, chat, conversations, account, admin):
        app.include_router(module.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        active: Provider = app.state.provider
        return {"status": "ok", "provider": active.name, "model": active.model}

    return app
