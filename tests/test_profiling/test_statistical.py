"""Tests for src.profiling.statistical."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError
from src.core.exceptions import SqlValidationError
from src.profiling.statistical import (
    ColumnProfile,
    is_numeric_type,
    is_string_type,
    is_temporal_type,
    profile_columns,
)


class TestTypePredicates:
    @pytest.mark.parametrize(
        "dtype",
        ["INTEGER", "BIGINT", "DOUBLE", "DECIMAL(10,2)", "FLOAT", "HUGEINT"],
    )
    def test_numeric_types(self, dtype: str) -> None:
        assert is_numeric_type(dtype)

    @pytest.mark.parametrize(
        "dtype", ["DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIME"]
    )
    def test_temporal_types(self, dtype: str) -> None:
        assert is_temporal_type(dtype)

    @pytest.mark.parametrize("dtype", ["VARCHAR", "CHAR(10)", "TEXT"])
    def test_string_types(self, dtype: str) -> None:
        assert is_string_type(dtype)

    def test_boolean_is_not_numeric(self) -> None:
        assert not is_numeric_type("BOOLEAN")


class TestProfileColumns:
    def test_profiles_every_column(
        self, raw_sales_connection: duckdb.DuckDBPyConnection
    ) -> None:
        profiles = profile_columns(raw_sales_connection, "raw_sales")
        assert [p.name for p in profiles] == [
            "order_id",
            "order_date",
            "region",
            "revenue",
            "quantity",
            "customer_segment",
        ]

    def test_revenue_numeric_stats_match_fixture(
        self, raw_sales_connection: duckdb.DuckDBPyConnection
    ) -> None:
        profiles = profile_columns(raw_sales_connection, "raw_sales")
        revenue = next(p for p in profiles if p.name == "revenue")

        assert revenue.row_count == 10
        assert revenue.null_count == 0
        assert revenue.completeness == pytest.approx(1.0)
        assert revenue.distinct_count == 10
        assert revenue.cardinality_ratio == pytest.approx(1.0)
        assert revenue.min_value == pytest.approx(45.25)
        assert revenue.max_value == pytest.approx(520.00)
        assert revenue.mean == pytest.approx(198.324, rel=1e-3)
        assert revenue.stddev is not None
        assert revenue.q25 is not None
        assert revenue.q75 is not None

    def test_region_dimension_profile(
        self, raw_sales_connection: duckdb.DuckDBPyConnection
    ) -> None:
        profiles = profile_columns(raw_sales_connection, "raw_sales")
        region = next(p for p in profiles if p.name == "region")

        assert region.distinct_count == 4
        assert set(region.sample_values) == {"North", "South", "East", "West"}
        # Dimensions are string-like so numeric stats should stay None.
        assert region.mean is None
        assert region.median is None

    def test_order_date_temporal_profile(
        self, raw_sales_connection: duckdb.DuckDBPyConnection
    ) -> None:
        profiles = profile_columns(raw_sales_connection, "raw_sales")
        order_date = next(p for p in profiles if p.name == "order_date")
        assert order_date.min_value == date(2024, 1, 15)
        assert order_date.max_value == date(2024, 1, 24)
        assert order_date.mean is None  # temporal columns have no mean

    def test_sample_size_is_honoured(
        self, raw_sales_connection: duckdb.DuckDBPyConnection
    ) -> None:
        profiles = profile_columns(raw_sales_connection, "raw_sales", sample_size=2)
        for profile in profiles:
            assert len(profile.sample_values) <= 2

    def test_rejects_invalid_table_name(
        self, raw_sales_connection: duckdb.DuckDBPyConnection
    ) -> None:
        with pytest.raises(SqlValidationError):
            profile_columns(raw_sales_connection, "raw_sales; DROP TABLE x")

    def test_handles_column_with_nulls(self, tmp_path: Path) -> None:
        del tmp_path  # not used; kept for potential future extensions
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                "CREATE TABLE t AS SELECT * FROM (VALUES "
                "(1, 'a'), (2, NULL), (3, 'a'), (4, NULL)) "
                "AS v(id, label)"
            )
            profiles = profile_columns(con, "t")
            label = next(p for p in profiles if p.name == "label")
            assert label.null_count == 2
            assert label.completeness == pytest.approx(0.5)
            assert label.distinct_count == 1
        finally:
            con.close()

    def test_column_profile_is_frozen(
        self, raw_sales_connection: duckdb.DuckDBPyConnection
    ) -> None:
        profiles = profile_columns(raw_sales_connection, "raw_sales")
        profile: ColumnProfile = profiles[0]
        with pytest.raises(ValidationError):
            profile.row_count = 999  # type: ignore[misc]
