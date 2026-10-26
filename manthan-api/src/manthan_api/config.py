"""Runtime configuration. Loads from .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Core ──
    database_url: str = Field(..., alias="DATABASE_URL")
    event_signing_key: str = Field("dev-event-key-change-me", alias="EVENT_SIGNING_KEY")
    source_config_key: str = Field("dev-source-key-change-me", alias="SOURCE_CONFIG_KEY")

    # ── Auth ──
    clerk_secret_key: str | None = Field(None, alias="CLERK_SECRET_KEY")
    clerk_publishable_key: str | None = Field(None, alias="CLERK_PUBLISHABLE_KEY")
    clerk_jwt_verification_key: str | None = Field(None, alias="CLERK_JWT_VERIFICATION_KEY")

    # ── LLM + Coral ──
    openrouter_api_key: str | None = Field(None, alias="OPENROUTER_API_KEY")
    coral_binary: str = Field(
        "coral",
        alias="CORAL_BINARY",
    )

    # ── Email ──
    resend_api_key: str | None = Field(None, alias="RESEND_API_KEY")
    resend_from_address: str = Field("manthan@miny-labs.com", alias="RESEND_FROM_ADDRESS")

    # ── Webhook secrets ──
    stripe_webhook_secret: str | None = Field(None, alias="STRIPE_WEBHOOK_SECRET")
    slack_signing_secret: str | None = Field(None, alias="SLACK_SIGNING_SECRET")
    resend_inbound_webhook_secret: str | None = Field(None, alias="RESEND_INBOUND_WEBHOOK_SECRET")

    # ── Web ──
    web_app_origin: str = Field("http://localhost:5173", alias="WEB_APP_ORIGIN")

    @property
    def is_dev(self) -> bool:
        return "dev-" in self.event_signing_key or "localhost" in self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
