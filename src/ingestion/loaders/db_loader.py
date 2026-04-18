"""Database source loaders via DuckDB scanner extensions.

Handles PostgreSQL, MySQL, and SQLite sources. DuckDB's scanner
extensions (``postgres``, ``mysql``, ``sqlite``) talk to the upstream
database directly from C++; no Python driver is required.

The loader accepts a connection string and a fully-qualified source
table identifier (``table`` or ``schema.table``) and copies the rows
into a destination DuckDB table. The connection string is never
persisted — it lives only for the duration of the ``ATTACH`` call.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import duckdb
from pydantic import BaseModel, Field, SecretStr

from src.core.exceptions import IngestionError, SqlValidationError
from src.ingestion.base import (
    LoadResult,
    count_columns,
    count_rows,
    validate_identifier,
)

DbSourceType = Literal["postgres", "mysql", "sqlite"]


class DbLoadRequest(BaseModel):
    """Structured request for a database source load."""

    source_type: DbSourceType
    connection_string: SecretStr = Field(
        ...,
        description="libpq / mysql / sqlite connection string.",
    )
    source_table: str = Field(
        ...,
        description="Source table name, optionally schema-qualified.",
    )
    destination_table: str = Field(
        ...,
        description="DuckDB table to create (must be a valid identifier).",
    )


def load_from_database(
    connection: duckdb.DuckDBPyConnection,
    request: DbLoadRequest,
) -> LoadResult:
    """Copy ``request.source_table`` into DuckDB as ``request.destination_table``.

    Raises:
        SqlValidationError: If ``destination_table`` or ``source_table`` is
            not a valid identifier (schema-qualified names are allowed with
            each part validated independently).
        IngestionError: If DuckDB fails to attach, read, or copy the source.
    """
    validate_identifier(request.destination_table)
    source_table_parts = _validate_source_table(request.source_table)

    extension = _extension_for(request.source_type)
    alias = f"src_{uuid4().hex[:8]}"
    validate_identifier(alias)

    try:
        connection.execute(f"INSTALL {extension}")
        connection.execute(f"LOAD {extension}")
        # DuckDB's ATTACH does not accept parameter binding for the path;
        # we validate the string contains no control characters then embed
        # it directly with escaped single quotes.
        raw_conn = request.connection_string.get_secret_value()
        # Normalize libpq-style parameter names to the style DuckDB's
        # mysql_scanner expects. Users frequently paste
        # ``password=…`` / ``dbname=…`` (Postgres convention) into the
        # MySQL form, which used to die deep inside ATTACH with a
        # cryptic "Unrecognized configuration parameter" error.
        if request.source_type == "mysql":
            raw_conn = _normalize_mysql_conn_string(raw_conn)
        escaped_conn = _escape_sql_string(raw_conn)
        connection.execute(
            f"ATTACH '{escaped_conn}' AS {alias} (TYPE {extension.upper()}, READ_ONLY)"
        )
    except duckdb.Error as exc:
        raise IngestionError(
            f"Failed to attach {request.source_type} source: {exc}"
        ) from exc

    try:
        qualified = ".".join(source_table_parts)
        connection.execute(
            f"CREATE OR REPLACE TABLE {request.destination_table} AS "
            f"SELECT * FROM {alias}.{qualified}"
        )
    except duckdb.Error as exc:
        raise IngestionError(
            f"Failed to load {request.source_table} from {request.source_type}: {exc}"
        ) from exc
    finally:
        with contextlib.suppress(duckdb.Error):
            connection.execute(f"DETACH {alias}")

    source_identifier = f"{request.source_type}:{request.source_table}"
    return LoadResult(
        table_name=request.destination_table,
        source_type=request.source_type,
        original_filename=source_identifier,
        ingested_at=datetime.now(UTC),
        row_count=count_rows(connection, request.destination_table),
        column_count=count_columns(connection, request.destination_table),
        raw_size_bytes=None,
    )


def _extension_for(source_type: DbSourceType) -> str:
    return {
        "postgres": "postgres",
        "mysql": "mysql",
        "sqlite": "sqlite",
    }[source_type]


def _validate_source_table(name: str) -> list[str]:
    """Split and validate a ``[schema.]table`` name."""
    if not isinstance(name, str) or not name:
        raise SqlValidationError("source_table must be a non-empty string")
    parts = name.split(".")
    if len(parts) > 3:
        raise SqlValidationError(
            "source_table may have at most two dots (catalog.schema.table)"
        )
    for part in parts:
        validate_identifier(part)
    return parts


def _escape_sql_string(text: str) -> str:
    """Escape ``text`` for safe embedding in a single-quoted SQL string."""
    if "\x00" in text or "\n" in text or "\r" in text:
        raise SqlValidationError(
            "Connection string contains disallowed control characters"
        )
    return text.replace("'", "''")


# DuckDB's mysql_scanner extension accepts a very specific set of
# parameter names. Users often paste libpq-style names because the
# Postgres form is what they see elsewhere — we translate so either
# flavor works.
_MYSQL_PARAM_ALIASES = {
    "password": "passwd",
    "pwd": "passwd",
    "database": "db",
    "dbname": "db",
}


def _normalize_mysql_conn_string(conn: str) -> str:
    """Rewrite libpq-style param names (``password=``, ``dbname=``) to
    the mysql_scanner equivalents (``passwd=``, ``db=``). Leaves
    unknown keys alone so a user-supplied ``socket=`` / ``ssl_mode=``
    passes through untouched. Whitespace-separated ``key=value``
    tokens, like the rest of DuckDB's scanner syntax.

    Also drops empty-value parameters — DuckDB's mysql extension
    rejects ``passwd=`` (empty), which is a common gotcha when the
    MySQL role has no password (like the Rfam public reader).
    """
    parts = conn.split()
    out: list[str] = []
    for part in parts:
        if "=" not in part:
            out.append(part)
            continue
        key, _, value = part.partition("=")
        key_low = key.strip().lower()
        # Empty value → skip entirely. DuckDB's parser treats
        # ``passwd=`` as a malformed token rather than "no password".
        if value.strip() == "":
            continue
        if key_low in _MYSQL_PARAM_ALIASES:
            out.append(f"{_MYSQL_PARAM_ALIASES[key_low]}={value}")
        else:
            out.append(part)
    return " ".join(out)
