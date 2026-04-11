"""Tests for ``run_sql`` temp-table scratchpad support."""

from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pytest
from src.core.exceptions import SqlValidationError, ToolError
from src.tools.sql_tool import run_sql


@pytest.fixture
def con() -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE TABLE gold_sales (region VARCHAR, revenue DOUBLE)")
        connection.execute(
            "INSERT INTO gold_sales VALUES "
            "('North', 100.0), ('South', 200.0), ('East', 150.0)"
        )
        yield connection
    finally:
        connection.close()


class TestScratchpadCreation:
    def test_create_temp_table_as_select(self, con: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(
            con,
            "CREATE TEMP TABLE scratch_totals AS "
            "SELECT region, SUM(revenue) AS total FROM gold_sales GROUP BY region",
        )
        assert result.statement_kind == "create_temp"
        assert result.affected == "scratch_totals"
        assert result.row_count == 0

        # Subsequent SELECT sees the scratch table.
        followup = run_sql(
            con,
            "SELECT region, total FROM scratch_totals ORDER BY total DESC",
        )
        assert followup.statement_kind == "query"
        assert followup.row_count == 3
        assert followup.rows[0] == ["South", 200.0]

    def test_create_temp_view(self, con: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(
            con,
            "CREATE TEMP VIEW scratch_view AS "
            "SELECT * FROM gold_sales WHERE revenue > 100",
        )
        assert result.statement_kind == "create_temp"
        assert result.affected == "scratch_view"

        followup = run_sql(con, "SELECT COUNT(*) FROM scratch_view")
        assert followup.rows[0][0] == 2

    def test_create_temp_table_with_replace(
        self, con: duckdb.DuckDBPyConnection
    ) -> None:
        run_sql(con, "CREATE TEMP TABLE scratch AS SELECT 1 AS x")
        result = run_sql(
            con,
            "CREATE OR REPLACE TEMP TABLE scratch AS SELECT 2 AS x, 3 AS y",
        )
        assert result.statement_kind == "create_temp"


class TestScratchpadDrop:
    def test_drop_temp_table(self, con: duckdb.DuckDBPyConnection) -> None:
        run_sql(con, "CREATE TEMP TABLE scratch AS SELECT 42 AS x")
        result = run_sql(con, "DROP TABLE scratch")
        assert result.statement_kind == "drop"
        assert result.affected == "scratch"

        with pytest.raises(ToolError):
            run_sql(con, "SELECT * FROM scratch")

    def test_drop_temp_view(self, con: duckdb.DuckDBPyConnection) -> None:
        run_sql(con, "CREATE TEMP VIEW scratch_v AS SELECT * FROM gold_sales")
        result = run_sql(con, "DROP VIEW scratch_v")
        assert result.statement_kind == "drop"

    def test_drop_if_exists_on_temp(self, con: duckdb.DuckDBPyConnection) -> None:
        run_sql(con, "CREATE TEMP TABLE scratch AS SELECT 1 AS x")
        result = run_sql(con, "DROP TABLE IF EXISTS scratch")
        assert result.statement_kind == "drop"


class TestSafetyRails:
    def test_drop_gold_table_rejected(self, con: duckdb.DuckDBPyConnection) -> None:
        with pytest.raises(SqlValidationError, match="temp"):
            run_sql(con, "DROP TABLE gold_sales")

    def test_drop_nonexistent_object_rejected(
        self, con: duckdb.DuckDBPyConnection
    ) -> None:
        with pytest.raises(SqlValidationError, match="temp"):
            run_sql(con, "DROP TABLE does_not_exist")

    def test_create_persistent_table_rejected(
        self, con: duckdb.DuckDBPyConnection
    ) -> None:
        with pytest.raises(SqlValidationError):
            run_sql(con, "CREATE TABLE persistent AS SELECT 1 AS x")

    def test_insert_rejected(self, con: duckdb.DuckDBPyConnection) -> None:
        with pytest.raises(SqlValidationError):
            run_sql(con, "INSERT INTO gold_sales VALUES ('West', 999.0)")

    def test_delete_rejected(self, con: duckdb.DuckDBPyConnection) -> None:
        with pytest.raises(SqlValidationError):
            run_sql(con, "DELETE FROM gold_sales")

    def test_pragma_rejected(self, con: duckdb.DuckDBPyConnection) -> None:
        with pytest.raises(SqlValidationError):
            run_sql(con, "PRAGMA table_info('gold_sales')")

    def test_comment_hidden_drop_still_parses_as_query(
        self, con: duckdb.DuckDBPyConnection
    ) -> None:
        # Hiding a DROP behind a line comment should be a SELECT
        # (because the comment is stripped and the leading token is
        # SELECT), never a drop.
        result = run_sql(
            con,
            "SELECT 1 -- DROP TABLE gold_sales\n",
        )
        assert result.statement_kind == "query"

    def test_empty_statement_rejected(self, con: duckdb.DuckDBPyConnection) -> None:
        with pytest.raises(SqlValidationError):
            run_sql(con, "   ")


class TestSelectStillWorks:
    def test_select_returns_rows(self, con: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(con, "SELECT region, revenue FROM gold_sales ORDER BY revenue")
        assert result.statement_kind == "query"
        assert result.row_count == 3
        assert result.columns == ["region", "revenue"]

    def test_with_clause_accepted(self, con: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(
            con,
            "WITH totals AS (SELECT SUM(revenue) AS t FROM gold_sales) "
            "SELECT t FROM totals",
        )
        assert result.rows[0][0] == 450.0
