"""Tests for src.core.database."""

import duckdb
import pytest
from src.core.database import connection_scope, create_connection


def test_create_connection_returns_duckdb_connection() -> None:
    connection = create_connection(":memory:")
    try:
        assert isinstance(connection, duckdb.DuckDBPyConnection)
        result = connection.execute("SELECT 42 AS answer").fetchone()
        assert result is not None
        assert result[0] == 42
    finally:
        connection.close()


def test_create_connection_defaults_to_in_memory() -> None:
    connection = create_connection()
    try:
        result = connection.execute("SELECT 'manthan' AS name").fetchone()
        assert result is not None
        assert result[0] == "manthan"
    finally:
        connection.close()


def test_connection_scope_closes_on_exit() -> None:
    with connection_scope(":memory:") as connection:
        result = connection.execute("SELECT 1").fetchone()
        assert result is not None
        assert result[0] == 1
    # After the ``with`` block the connection should be closed.
    with pytest.raises(duckdb.ConnectionException):
        connection.execute("SELECT 1")


def test_connection_applies_configured_threads() -> None:
    with connection_scope(":memory:") as connection:
        result = connection.execute("SELECT current_setting('threads')").fetchone()
        assert result is not None
        # The default fixture does not override DUCKDB_THREADS so the
        # hard-coded Settings default (4) applies.
        assert int(result[0]) == 4
