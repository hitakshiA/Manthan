"""Tests for the database loader.

SQLite coverage is unit-level (checked-in synthetic `.db` built at test
time). Postgres integration is marked ``slow`` and spins up an ephemeral
container via testcontainers — skipped automatically when Docker is
unavailable so the test suite stays runnable on any machine.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from src.core.exceptions import IngestionError, SqlValidationError
from src.ingestion.loaders.db_loader import (
    DbLoadRequest,
    _escape_sql_string,
    _validate_source_table,
    load_from_database,
)


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "sample.db"
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "CREATE TABLE orders ("
            "order_id INTEGER PRIMARY KEY, region TEXT, revenue REAL)"
        )
        con.executemany(
            "INSERT INTO orders VALUES (?, ?, ?)",
            [
                (1, "North", 100.50),
                (2, "South", 89.00),
                (3, "East", 299.99),
            ],
        )
        con.commit()
    finally:
        con.close()
    return db_path


class TestValidateSourceTable:
    def test_plain_table(self) -> None:
        assert _validate_source_table("orders") == ["orders"]

    def test_schema_qualified(self) -> None:
        assert _validate_source_table("public.orders") == ["public", "orders"]

    def test_catalog_schema_table(self) -> None:
        assert _validate_source_table("cat.sch.tbl") == ["cat", "sch", "tbl"]

    def test_rejects_empty(self) -> None:
        with pytest.raises(SqlValidationError):
            _validate_source_table("")

    def test_rejects_injection(self) -> None:
        with pytest.raises(SqlValidationError):
            _validate_source_table("orders; DROP TABLE x")

    def test_rejects_too_many_dots(self) -> None:
        with pytest.raises(SqlValidationError):
            _validate_source_table("a.b.c.d")


class TestEscapeSqlString:
    def test_doubles_single_quotes(self) -> None:
        assert _escape_sql_string("foo'bar") == "foo''bar"

    def test_rejects_null_byte(self) -> None:
        with pytest.raises(SqlValidationError):
            _escape_sql_string("bad\x00")

    def test_rejects_newline(self) -> None:
        with pytest.raises(SqlValidationError):
            _escape_sql_string("bad\n")


class TestSqliteLoader:
    def test_loads_table(
        self,
        connection: duckdb.DuckDBPyConnection,
        sqlite_db: Path,
    ) -> None:
        result = load_from_database(
            connection,
            DbLoadRequest(
                source_type="sqlite",
                connection_string=str(sqlite_db),
                source_table="orders",
                destination_table="raw_orders",
            ),
        )
        assert result.source_type == "sqlite"
        assert result.row_count == 3
        assert result.column_count == 3
        total = connection.execute("SELECT SUM(revenue) FROM raw_orders").fetchone()
        assert total is not None
        assert round(total[0], 2) == 489.49

    def test_rejects_bad_destination(
        self,
        connection: duckdb.DuckDBPyConnection,
        sqlite_db: Path,
    ) -> None:
        with pytest.raises(SqlValidationError):
            load_from_database(
                connection,
                DbLoadRequest(
                    source_type="sqlite",
                    connection_string=str(sqlite_db),
                    source_table="orders",
                    destination_table="raw; DROP TABLE x",
                ),
            )

    def test_wraps_missing_table(
        self,
        connection: duckdb.DuckDBPyConnection,
        sqlite_db: Path,
    ) -> None:
        with pytest.raises(IngestionError):
            load_from_database(
                connection,
                DbLoadRequest(
                    source_type="sqlite",
                    connection_string=str(sqlite_db),
                    source_table="does_not_exist",
                    destination_table="raw_missing",
                ),
            )


def _docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.mark.slow
@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
class TestPostgresLoader:
    def test_loads_table_from_ephemeral_postgres(
        self,
        connection: duckdb.DuckDBPyConnection,
    ) -> None:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine") as pg:
            # Seed the container via DuckDB itself rather than psycopg so
            # we don't add an LGPL runtime dependency just for tests.
            seed_con = duckdb.connect(":memory:")
            try:
                seed_con.execute("INSTALL postgres")
                seed_con.execute("LOAD postgres")
                # Build libpq connection string from testcontainer metadata.
                conn_str = (
                    f"host={pg.get_container_host_ip()} "
                    f"port={pg.get_exposed_port(5432)} "
                    f"user={pg.username} password={pg.password} "
                    f"dbname={pg.dbname}"
                )
                seed_con.execute(f"ATTACH '{conn_str}' AS pg (TYPE POSTGRES)")
                seed_con.execute(
                    "CREATE OR REPLACE TABLE pg.orders "
                    "(order_id BIGINT, region VARCHAR, revenue DOUBLE)"
                )
                seed_con.execute(
                    "INSERT INTO pg.orders VALUES "
                    "(1, 'North', 100.50), "
                    "(2, 'South', 89.00), "
                    "(3, 'East', 299.99)"
                )
                seed_con.execute("DETACH pg")
            finally:
                seed_con.close()

            result = load_from_database(
                connection,
                DbLoadRequest(
                    source_type="postgres",
                    connection_string=conn_str,
                    source_table="orders",
                    destination_table="raw_pg_orders",
                ),
            )
            assert result.source_type == "postgres"
            assert result.row_count == 3
            total = connection.execute(
                "SELECT SUM(revenue) FROM raw_pg_orders"
            ).fetchone()
            assert total is not None
            assert round(total[0], 2) == 489.49
