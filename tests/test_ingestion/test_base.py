"""Tests for ingestion.base (LoadResult schema, identifier validation)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from src.core.exceptions import SqlValidationError
from src.ingestion.base import LoadResult, validate_identifier


class TestValidateIdentifier:
    def test_accepts_simple_name(self) -> None:
        assert validate_identifier("orders") == "orders"

    def test_accepts_underscore_prefix(self) -> None:
        assert validate_identifier("_raw_orders") == "_raw_orders"

    def test_accepts_digits_after_first_character(self) -> None:
        assert validate_identifier("orders_2024") == "orders_2024"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(SqlValidationError):
            validate_identifier("")

    def test_rejects_leading_digit(self) -> None:
        with pytest.raises(SqlValidationError):
            validate_identifier("2024_orders")

    def test_rejects_sql_injection_attempt(self) -> None:
        with pytest.raises(SqlValidationError):
            validate_identifier("orders; DROP TABLE users")

    def test_rejects_spaces(self) -> None:
        with pytest.raises(SqlValidationError):
            validate_identifier("my orders")

    def test_rejects_hyphens(self) -> None:
        with pytest.raises(SqlValidationError):
            validate_identifier("my-orders")

    def test_rejects_quotes(self) -> None:
        with pytest.raises(SqlValidationError):
            validate_identifier('"orders"')

    def test_rejects_overlong_identifier(self) -> None:
        with pytest.raises(SqlValidationError):
            validate_identifier("a" * 129)


class TestLoadResult:
    def _sample(self, **overrides: object) -> LoadResult:
        base: dict[str, object] = {
            "table_name": "raw_orders",
            "source_type": "csv",
            "original_filename": "orders.csv",
            "ingested_at": datetime.now(UTC),
            "row_count": 100,
            "column_count": 5,
            "raw_size_bytes": 4096,
        }
        base.update(overrides)
        return LoadResult(**base)  # type: ignore[arg-type]

    def test_builds_from_valid_data(self) -> None:
        result = self._sample()
        assert result.row_count == 100
        assert result.source_type == "csv"

    def test_rejects_negative_row_count(self) -> None:
        with pytest.raises(ValidationError):
            self._sample(row_count=-1)

    def test_raw_size_bytes_is_optional_for_db_sources(self) -> None:
        result = self._sample(source_type="postgres", raw_size_bytes=None)
        assert result.raw_size_bytes is None
