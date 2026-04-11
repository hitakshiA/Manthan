"""Tests for Presidio-backed value-pattern PII detection (Layer 2).

Marked slow because Presidio engine construction loads the spaCy
en_core_web_lg model which takes ~2s even on warm disk.
"""

from __future__ import annotations

from typing import Any

import pytest
from src.profiling.presidio_layer import (
    _engine,
    detect_value_pii,
    scan_samples,
)
from src.profiling.statistical import ColumnProfile


def _profile(name: str, samples: list[Any]) -> ColumnProfile:
    return ColumnProfile(
        name=name,
        dtype="VARCHAR",
        row_count=len(samples),
        null_count=0,
        completeness=1.0,
        distinct_count=len(set(samples)),
        cardinality_ratio=1.0,
        sample_values=samples,
    )


@pytest.fixture(scope="module")
def presidio_available() -> bool:
    return _engine() is not None


pytestmark = pytest.mark.slow


def test_detects_email_in_free_text(presidio_available: bool) -> None:
    if not presidio_available:
        pytest.skip("Presidio engine unavailable")
    profile = _profile(
        "notes",
        [
            "contact customer alex@example.com for delivery update",
            "please reach bailey@example.com on Monday",
            "escalated, see casey@example.com",
            "standard delivery",
            "returned — refund issued",
            "contact dana@example.com for replacement",
        ],
    )
    flag = detect_value_pii(profile)
    assert flag is not None
    assert flag.pii_type == "EMAIL_ADDRESS"
    assert flag.sensitivity == "pii"


def test_skips_non_string_columns(presidio_available: bool) -> None:
    if not presidio_available:
        pytest.skip("Presidio engine unavailable")
    profile = ColumnProfile(
        name="quantity",
        dtype="INTEGER",
        row_count=10,
        null_count=0,
        completeness=1.0,
        distinct_count=5,
        cardinality_ratio=0.5,
        sample_values=[1, 2, 3, 4, 5],
    )
    assert scan_samples(profile) is None


def test_does_not_flag_generic_text(presidio_available: bool) -> None:
    if not presidio_available:
        pytest.skip("Presidio engine unavailable")
    profile = _profile(
        "status",
        ["ok", "pending", "ok", "cancelled", "shipped", "delivered"],
    )
    assert detect_value_pii(profile) is None
