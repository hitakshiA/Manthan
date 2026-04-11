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


def test_default_values_are_applied() -> None:
    settings = get_settings()
    assert settings.duckdb_memory_limit == "4GB"
    assert settings.openrouter_model == "google/gemma-4-27b-it:free"
    assert settings.sandbox_network_disabled is True
    assert settings.pii_confidence_threshold == 0.7


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
