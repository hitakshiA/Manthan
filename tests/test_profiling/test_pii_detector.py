"""Tests for src.profiling.pii_detector (Layers 1 and 3)."""

from __future__ import annotations

from typing import Any

import pytest
from src.profiling.pii_detector import (
    classify_by_column_name,
    classify_column,
    detect_statistical_pii,
)
from src.profiling.statistical import ColumnProfile


def _build_profile(
    *,
    name: str = "col",
    dtype: str = "VARCHAR",
    row_count: int = 1000,
    distinct_count: int = 10,
    sample_values: list[Any] | None = None,
) -> ColumnProfile:
    return ColumnProfile(
        name=name,
        dtype=dtype,
        row_count=row_count,
        null_count=0,
        completeness=1.0,
        distinct_count=distinct_count,
        cardinality_ratio=distinct_count / row_count if row_count else 0.0,
        sample_values=sample_values or [],
    )


class TestLayer1ColumnName:
    @pytest.mark.parametrize(
        ("column_name", "expected_type"),
        [
            ("customer_name", "PERSON"),
            ("first_name", "PERSON"),
            ("last_name", "PERSON"),
            ("full_name", "PERSON"),
            ("email", "EMAIL_ADDRESS"),
            ("customer_email", "EMAIL_ADDRESS"),
            ("phone", "PHONE_NUMBER"),
            ("mobile_number", "PHONE_NUMBER"),
            ("ssn", "US_SSN"),
            ("social_security", "US_SSN"),
            ("credit_card", "CREDIT_CARD"),
            ("card_number", "CREDIT_CARD"),
            ("aadhaar", "AADHAAR"),
            ("pan_card", "PAN_CARD"),
            ("passport_number", "PASSPORT"),
            ("iban", "BANK_ACCOUNT"),
            ("street_address", "LOCATION_ADDRESS"),
            ("zip_code", "LOCATION_ADDRESS"),
        ],
    )
    def test_positive_matches(self, column_name: str, expected_type: str) -> None:
        flag = classify_by_column_name(column_name)
        assert flag is not None
        assert flag.sensitivity == "pii"
        assert flag.pii_type == expected_type
        assert flag.handling == "never_expose_in_outputs"
        assert flag.confidence > 0.8

    @pytest.mark.parametrize(
        "column_name",
        [
            "revenue",
            "order_date",
            "region",
            "quantity",
            "product_id",
            "customer_segment",
        ],
    )
    def test_negative_matches(self, column_name: str) -> None:
        assert classify_by_column_name(column_name) is None


class TestLayer3Statistical:
    def test_uuid_sample_values_flagged(self) -> None:
        profile = _build_profile(
            name="internal_id",
            sample_values=[
                "550e8400-e29b-41d4-a716-446655440000",
                "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
            ],
        )
        flag = detect_statistical_pii(profile)
        assert flag is not None
        assert flag.pii_type == "UUID"
        assert flag.sensitivity == "quasi_identifier"
        assert flag.handling == "aggregate_only"

    def test_high_cardinality_string_flagged(self) -> None:
        profile = _build_profile(
            name="natural_key",
            dtype="VARCHAR",
            row_count=1000,
            distinct_count=980,  # ratio 0.98, well above threshold
        )
        flag = detect_statistical_pii(profile)
        assert flag is not None
        assert flag.sensitivity == "quasi_identifier"
        assert flag.handling == "aggregate_only"

    def test_low_cardinality_string_not_flagged(self) -> None:
        profile = _build_profile(
            name="region",
            dtype="VARCHAR",
            row_count=1000,
            distinct_count=4,
        )
        assert detect_statistical_pii(profile) is None

    def test_high_cardinality_numeric_not_flagged(self) -> None:
        # Only string-like columns should be caught by this heuristic.
        profile = _build_profile(
            name="order_id",
            dtype="BIGINT",
            row_count=1000,
            distinct_count=1000,
        )
        assert detect_statistical_pii(profile) is None

    def test_few_distinct_string_not_flagged(self) -> None:
        # 20 distinct is below _HIGH_CARDINALITY_MIN_DISTINCT.
        profile = _build_profile(
            name="sku",
            dtype="VARCHAR",
            row_count=20,
            distinct_count=20,
        )
        assert detect_statistical_pii(profile) is None


class TestClassifyColumn:
    def test_layer1_takes_precedence(self) -> None:
        profile = _build_profile(
            name="customer_email",
            dtype="VARCHAR",
            row_count=1000,
            distinct_count=999,  # would also trip Layer 3
        )
        flag = classify_column(profile)
        assert flag.sensitivity == "pii"
        assert flag.pii_type == "EMAIL_ADDRESS"

    def test_falls_back_to_layer3(self) -> None:
        profile = _build_profile(
            name="internal_hash",
            dtype="VARCHAR",
            row_count=1000,
            distinct_count=999,
        )
        flag = classify_column(profile)
        assert flag.sensitivity == "quasi_identifier"

    def test_defaults_to_public(self) -> None:
        profile = _build_profile(
            name="region", dtype="VARCHAR", row_count=1000, distinct_count=4
        )
        flag = classify_column(profile)
        assert flag.sensitivity == "public"
        assert flag.handling == "expose"
