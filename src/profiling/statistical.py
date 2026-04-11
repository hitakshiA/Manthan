"""Statistical profiling of raw DuckDB tables.

Produces a :class:`ColumnProfile` for every column in a raw table: row
counts, null counts, cardinality, numeric/temporal min-max-mean-median-
stddev-quantiles, and a handful of distinct non-null sample values. These
profiles feed the column classifier, the enricher, the PII detector, and
ultimately the Data Context Document.

This module is the *statistical* surface of the Silver stage. It does no
LLM calls and no semantic interpretation — every function here is
deterministic and testable against a fixed dataset.
"""

from __future__ import annotations

from typing import Any

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from src.ingestion.base import quote_identifier, validate_identifier

_NUMERIC_TYPE_TOKENS = (
    "INT",
    "BIGINT",
    "SMALLINT",
    "TINYINT",
    "HUGEINT",
    "UBIGINT",
    "USMALLINT",
    "UTINYINT",
    "UHUGEINT",
    "UINTEGER",
    "DECIMAL",
    "NUMERIC",
    "DOUBLE",
    "FLOAT",
    "REAL",
)

_TEMPORAL_TYPE_TOKENS = ("DATE", "TIME", "TIMESTAMP", "INTERVAL")
_STRING_TYPE_TOKENS = ("VARCHAR", "CHAR", "TEXT", "STRING")

# Default number of distinct non-null sample values retained per column.
# Matches SPEC §6 "sample 100 values" scaled down: we keep enough to show
# the user what the column looks like without blowing up memory on very
# wide tables.
DEFAULT_SAMPLE_SIZE = 20


class ColumnProfile(BaseModel):
    """Per-column statistical profile produced by :func:`profile_columns`."""

    model_config = ConfigDict(frozen=True)

    name: str
    dtype: str
    row_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    completeness: float = Field(ge=0.0, le=1.0)
    distinct_count: int = Field(ge=0)
    cardinality_ratio: float = Field(ge=0.0, le=1.0)
    min_value: Any = None
    max_value: Any = None
    mean: float | None = None
    median: float | None = None
    stddev: float | None = None
    q25: float | None = None
    q75: float | None = None
    sample_values: list[Any] = Field(default_factory=list)


def is_numeric_type(dtype: str) -> bool:
    """Return ``True`` if ``dtype`` is a DuckDB numeric type."""
    upper = dtype.upper()
    return any(token in upper for token in _NUMERIC_TYPE_TOKENS)


def is_temporal_type(dtype: str) -> bool:
    """Return ``True`` if ``dtype`` is a DuckDB date/time type."""
    upper = dtype.upper()
    return any(token in upper for token in _TEMPORAL_TYPE_TOKENS)


def is_string_type(dtype: str) -> bool:
    """Return ``True`` if ``dtype`` is a DuckDB string type."""
    upper = dtype.upper()
    return any(token in upper for token in _STRING_TYPE_TOKENS)


def profile_columns(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> list[ColumnProfile]:
    """Profile every column in ``table_name``.

    Args:
        connection: Live DuckDB connection with ``table_name`` present.
        table_name: Target raw table. Must pass
            :func:`~src.ingestion.base.validate_identifier`.
        sample_size: Maximum number of distinct non-null sample values to
            retain per column. Defaults to :data:`DEFAULT_SAMPLE_SIZE`.

    Returns:
        One :class:`ColumnProfile` per column, in schema order.

    Raises:
        SqlValidationError: If ``table_name`` is not a valid identifier.
    """
    validate_identifier(table_name)

    columns = connection.execute(
        "SELECT column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_name = ? "
        "ORDER BY ordinal_position",
        [table_name],
    ).fetchall()

    row_count_row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    row_count = int(row_count_row[0]) if row_count_row is not None else 0

    profiles: list[ColumnProfile] = []
    for column_name, dtype in columns:
        profiles.append(
            _profile_single_column(
                connection=connection,
                table_name=table_name,
                column_name=column_name,
                dtype=dtype,
                row_count=row_count,
                sample_size=sample_size,
            )
        )
    return profiles


def _profile_single_column(
    *,
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    column_name: str,
    dtype: str,
    row_count: int,
    sample_size: int,
) -> ColumnProfile:
    quoted = quote_identifier(column_name)

    counts_row = connection.execute(
        f"SELECT COUNT({quoted}) AS non_null, "
        f"       COUNT(DISTINCT {quoted}) AS distinct_count "
        f"FROM {table_name}"
    ).fetchone()
    non_null_count = int(counts_row[0]) if counts_row else 0
    distinct_count = int(counts_row[1]) if counts_row else 0
    null_count = max(row_count - non_null_count, 0)
    completeness = non_null_count / row_count if row_count > 0 else 1.0
    cardinality_ratio = distinct_count / row_count if row_count > 0 else 0.0

    min_value: Any = None
    max_value: Any = None
    mean: float | None = None
    median: float | None = None
    stddev: float | None = None
    q25: float | None = None
    q75: float | None = None

    if is_numeric_type(dtype):
        numeric_row = connection.execute(
            f"SELECT MIN({quoted}), MAX({quoted}), "
            f"       AVG({quoted}::DOUBLE), "
            f"       MEDIAN({quoted}::DOUBLE), "
            f"       STDDEV({quoted}::DOUBLE), "
            f"       QUANTILE_CONT({quoted}::DOUBLE, 0.25), "
            f"       QUANTILE_CONT({quoted}::DOUBLE, 0.75) "
            f"FROM {table_name}"
        ).fetchone()
        if numeric_row is not None:
            min_value = numeric_row[0]
            max_value = numeric_row[1]
            mean = _maybe_float(numeric_row[2])
            median = _maybe_float(numeric_row[3])
            stddev = _maybe_float(numeric_row[4])
            q25 = _maybe_float(numeric_row[5])
            q75 = _maybe_float(numeric_row[6])
    elif is_temporal_type(dtype) or is_string_type(dtype):
        range_row = connection.execute(
            f"SELECT MIN({quoted}), MAX({quoted}) FROM {table_name}"
        ).fetchone()
        if range_row is not None:
            min_value = range_row[0]
            max_value = range_row[1]

    sample_rows = connection.execute(
        f"SELECT DISTINCT {quoted} FROM {table_name} "
        f"WHERE {quoted} IS NOT NULL "
        f"LIMIT {int(sample_size)}"
    ).fetchall()
    sample_values: list[Any] = [row[0] for row in sample_rows]

    return ColumnProfile(
        name=column_name,
        dtype=dtype,
        row_count=row_count,
        null_count=null_count,
        completeness=completeness,
        distinct_count=distinct_count,
        cardinality_ratio=cardinality_ratio,
        min_value=min_value,
        max_value=max_value,
        mean=mean,
        median=median,
        stddev=stddev,
        q25=q25,
        q75=q75,
        sample_values=sample_values,
    )


def _maybe_float(value: object) -> float | None:
    """Coerce ``value`` to ``float`` if it is not ``None``."""
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]
