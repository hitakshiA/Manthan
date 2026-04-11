"""Shared fixtures for core module tests.

Provides an autouse fixture that sets the required ``OPENROUTER_API_KEY``
env var and clears the :func:`get_settings` cache so that each test sees a
fresh, isolated ``Settings`` instance.
"""

import pytest
from src.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test starts with a known API key and a cleared cache."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key-fixture")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
