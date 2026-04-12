"""Agent configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """Layer 2 agent settings — loaded from .env.

    Uses AGENT_ prefix for agent-specific settings. The API key
    falls back to OPENROUTER_API_KEY (no prefix) if AGENT_OPENROUTER_API_KEY
    is not set, so the same .env works for both Layer 1 and Layer 2.
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
        """Fall back to OPENROUTER_API_KEY if AGENT_ prefixed key not set."""
        import os

        return os.environ.get(
            "AGENT_OPENROUTER_API_KEY",
            os.environ.get("OPENROUTER_API_KEY", ""),
        )

    model: str = Field(
        default="openai/gpt-oss-120b",
        description="LLM for agent reasoning (fast + good tool calling)",
    )
    free_tier: bool = Field(
        default=True,
        description="Append ':free' to model slug for free tier",
    )
    openrouter_api_key: str = Field(
        default="",
        description="Falls back to OPENROUTER_API_KEY if not set",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
    )

    @property
    def resolved_model(self) -> str:
        """Model slug with free-tier suffix if enabled."""
        slug = self.model
        if self.free_tier and not slug.endswith(":free"):
            slug = f"{slug}:free"
        return slug

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
