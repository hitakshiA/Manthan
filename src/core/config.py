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
    openrouter_model: str = Field(
        default="openai/gpt-oss-120b:free",
        description="Free-tier OpenRouter model slug used for profiling.",
    )
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

    # --- PII Detection -----------------------------------------------------
    presidio_nlp_model: str = Field(default="en_core_web_lg")
    pii_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    pii_sample_size: int = Field(default=100, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton for this process."""
    return Settings()
