"""Settings, read from the environment and from the `.env` file at the repository root."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}"

    # "mock" needs no key and gives the same answer for the same input, so tests are repeatable.
    llm_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    # Newer OpenAI reasoning models reject `max_tokens` and want `max_completion_tokens`.
    openai_max_tokens_param: str = "max_tokens"
    mock_delay_ms: int = 20

    session_days: int = 14
    cookie_name: str = "shopdesk_session"
    cookie_secure: bool = False
    registration_open: bool = True

    max_input_chars: int = 4000
    # Only the most recent messages are sent to the model, which bounds the cost of a long chat.
    context_messages: int = 12

    login_max_failures: int = 5
    login_window_minutes: int = 15

    @field_validator("*", mode="before")
    @classmethod
    def _empty_means_default(cls, value: object, info: ValidationInfo) -> object:
        # An empty value in `.env` (the state of `.env.example`) means "use the default".
        if value == "" and info.field_name:
            return cls.model_fields[info.field_name].default
        return value
