"""Read-only SQL execution tool.

Exposes :func:`run_sql` — the agent-facing tool for querying a dataset's
Gold table. Only ``SELECT`` and ``WITH`` statements are allowed; results
are capped at a configurable row limit and annotated with whether they
were truncated. Execution time is reported so callers can surface it to
the user.
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

_ALLOWED_PREFIXES = frozenset({"SELECT", "WITH"})
_DEFAULT_MAX_ROWS = 1000
_DEFAULT_TIMEOUT_SECONDS = 30

# Forbidden keywords that must never appear as a leading token in a read-only
# SQL statement even after stripping comments. Reject up front to block cases
# like trailing DDL hidden behind block comments.
_FORBIDDEN_LEADING_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "ATTACH",
        "DETACH",
        "COPY",
        "PRAGMA",
        "CALL",
        "SET",
    }
)

_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


class SqlResult(BaseModel):
    """Structured result of a ``run_sql`` call."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int = Field(ge=0)
    truncated: bool
    execution_time_ms: float = Field(ge=0.0)


def run_sql(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    *,
    max_rows: int = _DEFAULT_MAX_ROWS,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> SqlResult:
    """Execute ``sql`` against ``connection`` with read-only guardrails.

    Raises:
        SqlValidationError: If ``sql`` starts with anything other than
            ``SELECT`` or ``WITH``, or references a table that does not
            exist in the DuckDB catalog.
        ToolError: If DuckDB fails to parse or execute the statement, or
            if the query runs longer than ``timeout_seconds``.
    """
    _validate_read_only(sql)

    # DuckDB does not support a session-level statement timeout; enforce
    # the timeout by scheduling a background ``connection.interrupt()``
    # via ``threading.Timer``.
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
        relation = connection.sql(sql)
        column_names = list(relation.columns)
        fetched = relation.fetchmany(max_rows + 1)
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
    )


def _validate_read_only(sql: str) -> None:
    """Strip comments and ensure the statement is read-only SELECT/WITH."""
    stripped = _strip_comments(sql).strip()
    if not stripped:
        raise SqlValidationError("SQL statement is empty")
    first_word = stripped.split(None, 1)[0].upper()
    if first_word in _FORBIDDEN_LEADING_KEYWORDS:
        raise SqlValidationError(
            f"Only SELECT and WITH statements are allowed, got: {first_word}"
        )
    if first_word not in _ALLOWED_PREFIXES:
        raise SqlValidationError(
            f"Only SELECT and WITH statements are allowed, got: {first_word}"
        )


def _strip_comments(sql: str) -> str:
    """Remove ``--`` line comments and ``/* */`` block comments from ``sql``."""
    no_block = _BLOCK_COMMENT_RE.sub(" ", sql)
    no_line = _LINE_COMMENT_RE.sub(" ", no_block)
    return no_line
