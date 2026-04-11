"""Tests for the fixed-width numeric PII heuristic (Layer 3 extension)."""

from __future__ import annotations

from typing import Any

from src.profiling.pii_detector import (
    _detect_fixed_width_numeric_pii,
    classify_column,
)
from src.profiling.statistical import ColumnProfile


def _profile(name: str, dtype: str, samples: list[Any]) -> ColumnProfile:
    return ColumnProfile(
        name=name,
        dtype=dtype,
        row_count=len(samples),
        null_count=0,
        completeness=1.0,
        distinct_count=len(set(samples)),
        cardinality_ratio=1.0,
        sample_values=samples,
    )


def test_detects_10_digit_as_phone_number() -> None:
    profile = _profile(
        "contact",
        "VARCHAR",
        [
            "9876543210",
            "9123456780",
            "9345612789",
            "9811223344",
            "9900112233",
            "9123456700",
        ],
    )
    flag = _detect_fixed_width_numeric_pii(profile)
    assert flag is not None
    assert flag.pii_type == "PHONE_NUMBER"
    assert flag.sensitivity == "pii"


def test_detects_12_digit_as_aadhaar() -> None:
    profile = _profile(
        "natl_id",
        "VARCHAR",
        [str(100000000000 + i) for i in range(6)],
    )
    flag = _detect_fixed_width_numeric_pii(profile)
    assert flag is not None
    assert flag.pii_type == "AADHAAR"


def test_detects_16_digit_as_credit_card() -> None:
    profile = _profile(
        "card_no",
        "VARCHAR",
        [str(4000000000000000 + i) for i in range(6)],
    )
    flag = _detect_fixed_width_numeric_pii(profile)
    assert flag is not None
    assert flag.pii_type == "CREDIT_CARD"


def test_ignores_numeric_column() -> None:
    # Integers shouldn't get flagged — only string columns hit the heuristic.
    profile = _profile("order_id", "BIGINT", [1, 2, 3, 4, 5, 6])
    assert _detect_fixed_width_numeric_pii(profile) is None


def test_ignores_mixed_length() -> None:
    profile = _profile(
        "code",
        "VARCHAR",
        ["12345", "123456", "1234567", "12345678"],
    )
    assert _detect_fixed_width_numeric_pii(profile) is None


def test_ignores_too_few_samples() -> None:
    profile = _profile(
        "tiny",
        "VARCHAR",
        ["9876543210", "9123456780"],
    )
    assert _detect_fixed_width_numeric_pii(profile) is None


def test_ignores_non_digit_content() -> None:
    profile = _profile(
        "free_text",
        "VARCHAR",
        ["hello", "world", "foo", "bar", "baz", "qux"],
    )
    assert _detect_fixed_width_numeric_pii(profile) is None


def test_classify_column_uses_numeric_heuristic() -> None:
    # "contact" doesn't match the Layer-1 PHONE regex (no "phone" / "tel"
    # etc.) but Layer 3 should still catch it via the digit-width test.
    profile = _profile(
        "contact",
        "VARCHAR",
        [
            "9876543210",
            "9123456780",
            "9345612789",
            "9811223344",
            "9900112233",
            "9123456700",
        ],
    )
    flag = classify_column(profile, enable_presidio=False)
    assert flag.sensitivity == "pii"
    assert flag.pii_type == "PHONE_NUMBER"
