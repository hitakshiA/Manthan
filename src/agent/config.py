"""Agent configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """Layer 2 agent settings - loaded from .env.

    Uses AGENT_ prefix for agent-specific settings. The Gemini key falls
    back to ``GEMINI_API_KEY`` (no prefix) if ``AGENT_GEMINI_API_KEY`` is
    not set, so the same .env works for both Layer 1 and Layer 2.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="AGENT_",
    )

    @classmethod
    def _resolve_api_key(cls) -> str:
        """Fall back to GEMINI_API_KEY if AGENT_ prefixed key not set."""
        import os

        return os.environ.get(
            "AGENT_GEMINI_API_KEY",
            os.environ.get("GEMINI_API_KEY", ""),
        )

    model: str = Field(
        default="gemini-3-flash-preview",
        description=(
            "Gemini model for agent reasoning. Default is Gemini 3 Flash - "
            "benchmarked 2.5x faster than Pro on Manthan's hard-question suite "
            "with comparable answer quality. Override via AGENT_MODEL env var."
        ),
    )
    gemini_api_key: str = Field(
        default="",
        description="Falls back to GEMINI_API_KEY if not set.",
    )
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    @property
    def resolved_model(self) -> str:
        """Model slug."""
        return self.model

    layer1_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Layer 1 API base URL",
    )
    max_turns: int = Field(default=25, ge=1, le=100)
    max_subagent_turns: int = Field(default=8, ge=1, le=20)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tool_result_tokens: int = Field(
        default=4000,
        description="Truncate tool results beyond this",
    )
    timeout_seconds: int = Field(default=180, ge=10)
