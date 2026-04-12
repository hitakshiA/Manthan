"""SQL execution tool with read-only guardrails and scratchpad support.

Exposes :func:`run_sql` — the agent-facing tool for querying a dataset.
Allows ``SELECT``, ``WITH``, and a narrow set of DDL for scratchpad
work: ``CREATE TEMP TABLE/VIEW`` and ``DROP TABLE/VIEW`` *only* when
the target is a temporary object (exists in DuckDB's ``temp`` schema).
Persistent Gold tables cannot be created or dropped from this surface.

Agents use the temp table feature to build up intermediate results
across many tool calls — e.g. materialise a subquery as a named
scratch table in one turn and JOIN against it in the next. Temp tables
are per-connection in DuckDB and vanish when the connection closes.
"""

from __future__ import annotations

import contextlib
import re
import threading
from time import perf_counter
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from src.core.exceptions import SqlValidationError, ToolError

_DEFAULT_MAX_ROWS = 1000
_DEFAULT_TIMEOUT_SECONDS = 30

# Anchored regex for the statement shapes we allow. Order matters —
# the CREATE/DROP variants must be checked before a generic prefix match.
_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_WITH_RE = re.compile(r"^\s*WITH\b", re.IGNORECASE)
_DESCRIBE_RE = re.compile(
    r"^\s*DESCRIBE\b",
    re.IGNORECASE,
)
_SHOW_RE = re.compile(
    r"^\s*SHOW\s+(TABLES|ALL\s+TABLES)\b",
    re.IGNORECASE,
)
_CREATE_TEMP_RE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP|TEMPORARY)\s+(TABLE|VIEW)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_DROP_RE = re.compile(
    r"^\s*DROP\s+(TABLE|VIEW)(?:\s+IF\s+EXISTS)?\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


class SqlResult(BaseModel):
    """Structured result of a ``run_sql`` call.

    For queries that return rows (``SELECT``, ``WITH``, or the body of
    a ``CREATE ... AS SELECT``) the ``columns`` and ``rows`` fields are
    populated. For pure DDL statements (``CREATE TEMP TABLE ... (col
    INT)``, ``DROP TABLE``) ``rows`` is empty and ``affected`` reports
    what changed.
    """

    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    truncated: bool = False
    execution_time_ms: float = Field(ge=0.0)
    statement_kind: str = Field(
        default="query",
        description="query | create_temp | drop",
    )
    affected: str | None = Field(
        default=None,
        description="For DDL: the temp object that was created or dropped.",
    )


def run_sql(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    *,
    max_rows: int = _DEFAULT_MAX_ROWS,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> SqlResult:
    """Execute ``sql`` with read-only + scratchpad guardrails.

    Accepted statement shapes:

    - ``SELECT ...``
    - ``WITH ... SELECT ...``
    - ``CREATE [OR REPLACE] TEMP[ORARY] TABLE|VIEW name AS SELECT ...``
    - ``CREATE [OR REPLACE] TEMP[ORARY] TABLE name (col ...)``
    - ``DROP TABLE|VIEW [IF EXISTS] temp_name`` — only when ``temp_name``
      exists in DuckDB's ``temp`` schema.

    Raises:
        SqlValidationError: On any disallowed statement shape, or on a
            DROP that targets a non-temp object.
        ToolError: On DuckDB parse/execution errors or timeout.
    """
    kind, create_target, drop_target = _validate_sql(sql, connection)

    interrupt_fired = threading.Event()

    def _interrupt() -> None:
        interrupt_fired.set()
        with contextlib.suppress(Exception):
            connection.interrupt()

    timer = threading.Timer(float(timeout_seconds), _interrupt)
    timer.daemon = True
    timer.start()

    start = perf_counter()
    try:
        if kind == "query":
            relation = connection.sql(sql)
            column_names = list(relation.columns)
            fetched = relation.fetchmany(max_rows + 1)
        elif kind == "create_temp" or kind == "drop":
            connection.execute(sql)
            column_names = []
            fetched = []
        else:  # pragma: no cover — defensive, validator rejects anything else
            raise SqlValidationError(f"Unsupported statement kind: {kind}")
    except duckdb.InterruptException as exc:
        raise ToolError(f"SQL execution exceeded {timeout_seconds}s timeout") from exc
    except duckdb.Error as exc:
        if interrupt_fired.is_set():
            raise ToolError(
                f"SQL execution exceeded {timeout_seconds}s timeout"
            ) from exc
        raise ToolError(f"SQL execution failed: {exc}") from exc
    finally:
        timer.cancel()

    truncated = len(fetched) > max_rows
    if truncated:
        fetched = fetched[:max_rows]

    elapsed_ms = (perf_counter() - start) * 1000.0

    return SqlResult(
        columns=column_names,
        rows=[list(row) for row in fetched],
        row_count=len(fetched),
        truncated=truncated,
        execution_time_ms=round(elapsed_ms, 3),
        statement_kind=kind,
        affected=create_target or drop_target,
    )


def _validate_sql(
    sql: str, connection: duckdb.DuckDBPyConnection
) -> tuple[str, str | None, str | None]:
    """Classify ``sql`` as query / create_temp / drop, or reject it.

    Returns a ``(kind, create_target, drop_target)`` tuple.
    """
    stripped = _strip_comments(sql).strip()
    if not stripped:
        raise SqlValidationError("SQL statement is empty")

    if _SELECT_RE.match(stripped) or _WITH_RE.match(stripped):
        return "query", None, None

    if _DESCRIBE_RE.match(stripped) or _SHOW_RE.match(stripped):
        return "query", None, None

    create_match = _CREATE_TEMP_RE.match(stripped)
    if create_match:
        return "create_temp", create_match.group("name"), None

    drop_match = _DROP_RE.match(stripped)
    if drop_match:
        target = drop_match.group("name")
        _require_temp_object(connection, target)
        return "drop", None, target

    # Anything else — rejected with an actionable hint.
    first_word = stripped.split(None, 1)[0].upper()
    raise SqlValidationError(
        f"Statement type {first_word!r} is not allowed. "
        "Supported: SELECT, WITH, DESCRIBE, SHOW TABLES, "
        "CREATE TEMP TABLE/VIEW, "
        "and DROP TABLE/VIEW on temp objects only."
    )


def _require_temp_object(connection: duckdb.DuckDBPyConnection, name: str) -> None:
    """Raise unless ``name`` exists in DuckDB's ``temp`` database.

    DuckDB stores temporary tables and views in a catalog called
    ``temp`` (not a schema called ``temp`` — the catalog contains a
    ``main`` schema). The check below matches by ``database_name``.
    """
    row = connection.execute(
        "SELECT 1 FROM duckdb_tables() "
        "WHERE database_name = 'temp' AND table_name = ? "
        "UNION ALL "
        "SELECT 1 FROM duckdb_views() "
        "WHERE database_name = 'temp' AND view_name = ? "
        "LIMIT 1",
        [name, name],
    ).fetchone()
    if row is None:
        raise SqlValidationError(
            f"DROP is only allowed for temp objects; {name!r} is not a "
            "temp table or temp view. Persistent Gold tables are read-only "
            "from this tool."
        )


def _strip_comments(sql: str) -> str:
    """Remove ``--`` line comments and ``/* */`` block comments from ``sql``."""
    no_block = _BLOCK_COMMENT_RE.sub(" ", sql)
    no_line = _LINE_COMMENT_RE.sub(" ", no_block)
    return no_line
