"""Shared types and helpers for the Bronze ingestion stage.

Defines the :class:`Loader` Protocol every concrete loader implements, the
:class:`LoadResult` schema every loader returns, and the
:func:`validate_identifier` guard used at every boundary where a table or
column name would otherwise be interpolated into SQL.

Loaders are intentionally decoupled from the :mod:`src.ingestion.gateway`
dispatcher — a loader only needs to answer "can I handle this path?" and
"load this path into this DuckDB connection as this table". The gateway
handles routing and the registry assigns dataset identifiers.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import duckdb
from pydantic import BaseModel, Field

from src.core.exceptions import SqlValidationError

SourceType = Literal[
    "csv",
    "excel",
    "json",
    "parquet",
    "postgres",
    "mysql",
    "sqlite",
]

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_IDENTIFIER_LENGTH = 128


def validate_identifier(name: str) -> str:
    """Validate and return a SQL identifier.

    DuckDB (and most SQL dialects) cannot parameterize table or column
    names, so anywhere an identifier reaches a SQL statement it must come
    from a validated allow-list. This helper is the single allow-list.

    Args:
        name: The candidate identifier (table or column name).

    Returns:
        The same string, unchanged, if it is a valid identifier.

    Raises:
        SqlValidationError: If ``name`` is empty, too long, or contains
            characters outside the pattern ``[A-Za-z_][A-Za-z0-9_]*``.
    """
    if not isinstance(name, str) or not name:
        raise SqlValidationError("Identifier must be a non-empty string")
    if len(name) > _MAX_IDENTIFIER_LENGTH:
        raise SqlValidationError(
            f"Identifier exceeds maximum length of {_MAX_IDENTIFIER_LENGTH}: {name!r}"
        )
    if not _IDENTIFIER_PATTERN.match(name):
        raise SqlValidationError(
            f"Invalid identifier {name!r}; must match {_IDENTIFIER_PATTERN.pattern}"
        )
    return name


def sanitize_for_identifier(name: str) -> str:
    """Convert an arbitrary column name into a safe SQL identifier token.

    Real-world column names routinely contain characters the SQL grammar
    won't accept as bare identifiers — dots (``MS.SubClass``), dashes
    (``user-id``), spaces (``Order Date``), or leading digits
    (``2024_revenue``). Most places in this codebase correctly wrap user
    column references in :func:`quote_identifier` double-quotes so they
    survive verbatim. But a few places — summary table names, enum type
    names, query aliases — compose synthetic SQL identifiers from the
    column name, and those fail :func:`validate_identifier`.

    This helper sanitizes the column name into a token that will pass
    the validator: any character outside ``[A-Za-z0-9_]`` becomes an
    underscore, consecutive underscores collapse to one, and a leading
    digit is prefixed with an underscore.

    Args:
        name: The column name to sanitize.

    Returns:
        A string that matches :data:`_IDENTIFIER_PATTERN`.

    Raises:
        SqlValidationError: If the input is empty.
    """
    if not isinstance(name, str) or not name:
        raise SqlValidationError("Cannot sanitize empty name")
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        raise SqlValidationError(f"Sanitizing {name!r} produced an empty identifier")
    if safe[0].isdigit():
        safe = f"_{safe}"
    return safe


def quote_identifier(name: str) -> str:
    """Return ``name`` wrapped as an injection-safe quoted SQL identifier.

    Where :func:`validate_identifier` enforces a strict allow-list for
    names generated inside Manthan, ``quote_identifier`` exists for names
    that come from external data (CSV headers, database column names)
    and may legitimately contain spaces, punctuation, or reserved words.
    The name is double-quoted and any internal double quotes are doubled,
    which is the standard SQL way to safely include any identifier.

    Args:
        name: The candidate identifier.

    Returns:
        The identifier wrapped in double quotes, with internal quotes
        escaped.

    Raises:
        SqlValidationError: If ``name`` is empty, too long, or contains
            a NUL byte or a newline (which DuckDB will reject regardless
            of quoting).
    """
    if not isinstance(name, str) or not name:
        raise SqlValidationError("Identifier must be a non-empty string")
    if len(name) > _MAX_IDENTIFIER_LENGTH:
        raise SqlValidationError(
            f"Identifier exceeds maximum length of {_MAX_IDENTIFIER_LENGTH}: {name!r}"
        )
    if "\x00" in name or "\n" in name or "\r" in name:
        raise SqlValidationError(
            f"Identifier contains disallowed control characters: {name!r}"
        )
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


class LoadResult(BaseModel):
    """Metadata produced by a Bronze-stage loader.

    ``LoadResult`` is deliberately minimal: it describes *what was loaded*,
    not *what the data means*. Semantic annotation is the Silver stage's
    responsibility.
    """

    table_name: str = Field(..., description="DuckDB table holding the raw data.")
    source_type: SourceType = Field(..., description="Normalized source type.")
    original_filename: str = Field(
        ...,
        description="Original filename or connection identifier for the source.",
    )
    ingested_at: datetime = Field(
        ...,
        description="UTC timestamp at which the load completed.",
    )
    row_count: int = Field(..., ge=0, description="Number of rows loaded.")
    column_count: int = Field(..., ge=0, description="Number of columns inferred.")
    raw_size_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Raw source size in bytes; None for database sources.",
    )


@runtime_checkable
class Loader(Protocol):
    """Protocol every Bronze-stage loader implements."""

    def detect(self, input_path: Path) -> bool:
        """Return ``True`` if this loader can handle ``input_path``."""

    def load(
        self,
        input_path: Path,
        connection: duckdb.DuckDBPyConnection,
        table_name: str,
    ) -> LoadResult:
        """Load ``input_path`` into ``connection`` as ``table_name``.

        Implementations must validate ``table_name`` via
        :func:`validate_identifier` before embedding it in any SQL.
        """


def count_rows(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Return the row count of ``table_name`` in ``connection``.

    Raises:
        SqlValidationError: If ``table_name`` is not a valid identifier.
    """
    validate_identifier(table_name)
    row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0]) if row is not None else 0


def count_columns(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Return the column count of ``table_name`` in ``connection``.

    Raises:
        SqlValidationError: If ``table_name`` is not a valid identifier.
    """
    validate_identifier(table_name)
    row = connection.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = ?",
        [table_name],
    ).fetchone()
    return int(row[0]) if row is not None else 0
