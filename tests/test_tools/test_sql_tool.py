"""Tests for src.tools.sql_tool."""

from __future__ import annotations

import duckdb
import pytest
from src.core.exceptions import SqlValidationError, ToolError
from src.tools.sql_tool import run_sql


def test_run_sql_returns_columns_and_rows(
    gold_connection: duckdb.DuckDBPyConnection,
) -> None:
    result = run_sql(
        gold_connection,
        "SELECT region, SUM(revenue) AS total FROM raw_sales GROUP BY region",
    )
    assert "region" in result.columns
    assert "total" in result.columns
    assert result.row_count == 4
    assert not result.truncated
    assert result.execution_time_ms >= 0


def test_run_sql_truncates_when_over_max_rows(
    gold_connection: duckdb.DuckDBPyConnection,
) -> None:
    result = run_sql(gold_connection, "SELECT * FROM raw_sales", max_rows=3)
    assert result.row_count == 3
    assert result.truncated


def test_run_sql_rejects_ddl(
    gold_connection: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(SqlValidationError):
        run_sql(gold_connection, "DROP TABLE raw_sales")


def test_run_sql_rejects_insert(
    gold_connection: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(SqlValidationError):
        run_sql(gold_connection, "INSERT INTO raw_sales VALUES (1)")


def test_run_sql_rejects_empty(
    gold_connection: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(SqlValidationError):
        run_sql(gold_connection, "   ")


def test_run_sql_accepts_with(
    gold_connection: duckdb.DuckDBPyConnection,
) -> None:
    result = run_sql(
        gold_connection,
        "WITH t AS (SELECT SUM(revenue) AS r FROM raw_sales) SELECT r FROM t",
    )
    assert result.row_count == 1


def test_run_sql_wraps_syntax_errors(
    gold_connection: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(ToolError):
        run_sql(gold_connection, "SELECT * FROM nonexistent_table")
