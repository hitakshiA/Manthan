"""Top-level pytest fixtures.

Provides an autouse fixture that sets the required ``OPENROUTER_API_KEY``
env var and clears the :func:`get_settings` cache before every test.
This lets any test instantiate :class:`src.core.config.Settings` (and by
extension :class:`src.core.llm.LlmClient`) without needing a real key or
running inside a specific per-package fixture.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from src.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force every test to see a fresh, test-safe Settings singleton."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key-fixture")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
