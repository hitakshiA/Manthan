"""Read-only SQL execution tool.

Exposes :func:`run_sql` — the agent-facing tool for querying a dataset's
Gold table. Only ``SELECT`` and ``WITH`` statements are allowed; results
are capped at a configurable row limit and annotated with whether they
were truncated. Execution time is reported so callers can surface it to
the user.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from src.core.exceptions import SqlValidationError, ToolError

_ALLOWED_PREFIXES = frozenset({"SELECT", "WITH"})
_DEFAULT_MAX_ROWS = 1000


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
) -> SqlResult:
    """Execute ``sql`` against ``connection`` with read-only guardrails.

    Raises:
        SqlValidationError: If ``sql`` starts with anything other than
            ``SELECT`` or ``WITH``.
        ToolError: If DuckDB fails to parse or execute the statement.
    """
    _validate_read_only(sql)

    start = perf_counter()
    try:
        relation = connection.sql(sql)
    except duckdb.Error as exc:
        raise ToolError(f"SQL execution failed: {exc}") from exc

    column_names = list(relation.columns)
    # fetchmany(max_rows + 1) lets us detect truncation cheaply.
    fetched = relation.fetchmany(max_rows + 1)
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
    stripped = sql.strip()
    if not stripped:
        raise SqlValidationError("SQL statement is empty")
    first_word = stripped.split(None, 1)[0].upper()
    if first_word not in _ALLOWED_PREFIXES:
        raise SqlValidationError(
            f"Only SELECT and WITH statements are allowed, got: {first_word}"
        )
