"""DuckDB connection management.

Provides a single place to create DuckDB connections configured from
:class:`src.core.config.Settings`. A context-managed helper is also exposed
so that callers don't have to remember to close the connection explicitly.

This module is deliberately minimal: no connection pooling, no per-dataset
routing, no write locks. Higher-level modules (``ingestion``,
``materialization``) decide where and how to open the database. The Silver
and Gold stages typically operate on an in-memory database and export to
Parquet for the sandbox, so long-lived file handles are uncommon.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from src.core.config import Settings, get_settings


def create_connection(
    database: Path | str | None = None,
    *,
    settings: Settings | None = None,
) -> duckdb.DuckDBPyConnection:
    """Create and configure a DuckDB connection.

    Configuration (``memory_limit``, ``threads``, ``temp_directory``) is
    applied via DuckDB's connect-time ``config`` dict so that values are
    never string-interpolated into SQL, sidestepping the injection concern
    flagged in AGENTS.md §SQL rules.

    Args:
        database: Path to a DuckDB file, ``":memory:"``, or ``None``. When
            ``None`` (the default) an in-memory database is created.
        settings: Optional override settings. Defaults to the cached
            application settings returned by :func:`get_settings`.

    Returns:
        A configured ``duckdb.DuckDBPyConnection``. The caller is
        responsible for closing it, or should use :func:`connection_scope`
        for automatic cleanup.
    """
    resolved = settings or get_settings()
    target = str(database) if database is not None else ":memory:"
    config: dict[str, str | int] = {
        "memory_limit": resolved.duckdb_memory_limit,
        "threads": resolved.duckdb_threads,
        "temp_directory": str(resolved.duckdb_temp_directory),
    }
    return duckdb.connect(target, config=config)


@contextmanager
def connection_scope(
    database: Path | str | None = None,
    *,
    settings: Settings | None = None,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield a DuckDB connection and close it when the ``with`` block exits.

    Example:
        >>> with connection_scope() as con:
        ...     con.execute("SELECT 42").fetchone()
        (42,)
    """
    connection = create_connection(database, settings=settings)
    try:
        yield connection
    finally:
        connection.close()
