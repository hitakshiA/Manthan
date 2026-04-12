"""Tests for src.core.config."""

import pytest
from pydantic import ValidationError
from src.core.config import Settings, get_settings


def test_get_settings_loads_api_key_from_env() -> None:
    settings = get_settings()
    assert settings.openrouter_api_key.get_secret_value() == "sk-test-key-fixture"


def test_get_settings_returns_cached_instance() -> None:
    first = get_settings()
    second = get_settings()
    assert first is second


def test_env_var_override_is_picked_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKDB_THREADS", "8")
    monkeypatch.setenv("PORT", "9999")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.duckdb_threads == 8
    assert settings.port == 9999


def test_default_values_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure we test hardcoded defaults, not whatever is currently in .env.
    for var in (
        "DUCKDB_MEMORY_LIMIT",
        "OPENROUTER_MODEL",
        "SANDBOX_NETWORK_DISABLED",
        "MAX_UPLOAD_SIZE_MB",
    ):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None, openrouter_api_key="sk-test")  # type: ignore[call-arg]
    assert settings.duckdb_memory_limit == "4GB"
    assert settings.openrouter_model == "openai/gpt-oss-120b"
    assert settings.openrouter_free_tier is True
    assert settings.resolved_model == "openai/gpt-oss-120b:free"
    assert "qwen/qwen3-next-80b-a3b-instruct" in settings.openrouter_fallback_models
    assert "nvidia/nemotron-3-nano-30b-a3b" in settings.openrouter_fallback_models
    assert settings.sandbox_network_disabled is True
    assert settings.max_upload_size_mb == 500


def test_missing_api_key_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_port_fails_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "99999")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
