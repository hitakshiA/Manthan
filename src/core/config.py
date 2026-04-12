"""Application configuration loaded from environment variables.

All configuration flows through this module. Other ``src/`` modules import
:func:`get_settings` rather than reading ``os.environ`` directly (see
AGENTS.md §Configuration Rules). Secrets have **no defaults** so the
application fails fast at startup when they are missing; non-secret values
have sensible defaults defined below.

The settings object is cached via :func:`functools.lru_cache` so that it is
constructed at most once per process. Tests can reset the cache with
``get_settings.cache_clear()``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration for the Manthan data layer."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM ---------------------------------------------------------------
    openrouter_api_key: SecretStr = Field(
        ...,
        description="OpenRouter API key. No default — must be provided via env.",
    )
    openrouter_free_tier: bool = Field(
        default=True,
        description=(
            "When True, appends ':free' to all model slugs so "
            "requests use OpenRouter's free endpoints (rate-limited "
            "but $0). Set to False with a funded OpenRouter account "
            "for full-speed paid inference."
        ),
    )
    openrouter_model: str = Field(
        default="qwen/qwen3-next-80b-a3b-instruct",
        description=(
            "Primary OpenRouter model for profiling. Qwen3 Next "
            "80B benchmarked at 3.5s/19-col with 5/5 quality."
        ),
    )
    openrouter_fallback_models: list[str] = Field(
        default=[
            "openai/gpt-oss-120b",
            "nvidia/nemotron-3-nano-30b-a3b",
        ],
        description=(
            "Ordered fallback model slugs. Tried when the primary "
            "is unavailable. If all fail, heuristic classifier "
            "kicks in."
        ),
    )

    @property
    def resolved_model(self) -> str:
        """Primary model slug with free-tier suffix if enabled."""
        slug = self.openrouter_model
        if self.openrouter_free_tier and not slug.endswith(":free"):
            slug = f"{slug}:free"
        return slug

    @property
    def resolved_fallback_models(self) -> list[str]:
        """Fallback slugs with free-tier suffix if enabled."""
        out: list[str] = []
        for slug in self.openrouter_fallback_models:
            if self.openrouter_free_tier and not slug.endswith(":free"):
                slug = f"{slug}:free"
            out.append(slug)
        return out

    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL.",
    )

    # --- DuckDB ------------------------------------------------------------
    duckdb_memory_limit: str = Field(
        default="4GB",
        description="DuckDB memory_limit config value.",
    )
    duckdb_threads: int = Field(
        default=4,
        ge=1,
        description="Number of DuckDB worker threads.",
    )
    duckdb_temp_directory: Path = Field(
        default=Path("/tmp/duckdb"),
        description="DuckDB spill-to-disk scratch directory.",
    )

    # --- Sandbox -----------------------------------------------------------
    sandbox_image: str = Field(default="manthan-sandbox:latest")
    sandbox_memory_limit: str = Field(default="2g")
    sandbox_cpu_limit: int = Field(default=2, ge=1)
    sandbox_timeout_seconds: int = Field(default=60, ge=1)
    sandbox_network_disabled: bool = Field(default=True)

    # --- Rate Limiting -----------------------------------------------------
    rate_limit_whitelist: list[str] = Field(
        default_factory=list,
        description=(
            "Additional IPs to whitelist from rate limits. "
            "127.0.0.1 and ::1 are always whitelisted. "
            "Add your Layer 2/3 server IPs here."
        ),
    )

    # --- Storage -----------------------------------------------------------
    data_directory: Path = Field(
        default=Path("./data"),
        description="Root directory for per-dataset artifacts.",
    )
    max_upload_size_mb: int = Field(default=500, ge=1)

    # --- Server ------------------------------------------------------------
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = Field(default="info")
    log_format: str = Field(default="json", description="Either 'json' or 'console'.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton for this process."""
    return Settings()
