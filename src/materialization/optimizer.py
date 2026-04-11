"""Gold-stage table optimizer.

Rewrites a raw table into a Gold table sorted on the primary dimensions
(ascending cardinality) and the temporal column, attaches
``COMMENT ON`` descriptions from the DCD, and converts low-cardinality
dimension columns to DuckDB ``ENUM`` types for compression + enforced
valid-value sets (SPEC §3.1).
"""

from __future__ import annotations

import contextlib

import duckdb

from src.core.exceptions import SqlValidationError
from src.ingestion.base import quote_identifier, validate_identifier
from src.semantic.schema import DataContextDocument, DcdColumn

_ENUM_CARDINALITY_THRESHOLD = 100


def create_gold_table(
    connection: duckdb.DuckDBPyConnection,
    raw_table: str,
    gold_table: str,
    dcd: DataContextDocument,
) -> list[str]:
    """Build the Gold table, attach comments, and ENUM-convert dimensions.

    Args:
        connection: Active DuckDB connection.
        raw_table: Name of the Bronze table to transform.
        gold_table: Name to give the Gold table (created or replaced).
        dcd: The Data Context Document for ``raw_table``.

    Returns:
        The column names used in the ``ORDER BY`` clause, in order.
    """
    validate_identifier(raw_table)
    validate_identifier(gold_table)

    sort_columns = pick_sort_order(dcd)
    if sort_columns:
        sort_clause = ", ".join(quote_identifier(c) for c in sort_columns)
        sql = (
            f"CREATE OR REPLACE TABLE {gold_table} AS "
            f"SELECT * FROM {raw_table} ORDER BY {sort_clause}"
        )
    else:
        sql = f"CREATE OR REPLACE TABLE {gold_table} AS SELECT * FROM {raw_table}"
    connection.execute(sql)

    _attach_table_comment(connection, gold_table, dcd.dataset.description)
    for column in dcd.dataset.columns:
        _attach_column_comment(connection, gold_table, column)

    _convert_low_cardinality_dimensions_to_enums(
        connection, gold_table, dcd.dataset.columns
    )

    return sort_columns


def pick_sort_order(dcd: DataContextDocument) -> list[str]:
    """Return the Gold-table sort order for ``dcd``."""
    dimensions = [
        column for column in dcd.dataset.columns if column.role == "dimension"
    ]
    dimensions.sort(key=lambda c: (c.cardinality or 0, c.name))

    order: list[str] = [d.name for d in dimensions]
    temporal_column = dcd.dataset.temporal.column
    if temporal_column and temporal_column not in order:
        order.append(temporal_column)
    return order


def _attach_table_comment(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    description: str,
) -> None:
    escaped = description.replace("'", "''")
    connection.execute(f"COMMENT ON TABLE {table_name} IS '{escaped}'")


def _attach_column_comment(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    column: DcdColumn,
) -> None:
    quoted_column = quote_identifier(column.name)
    description = column.description.replace("'", "''")
    connection.execute(
        f"COMMENT ON COLUMN {table_name}.{quoted_column} IS '{description}'"
    )


def _convert_low_cardinality_dimensions_to_enums(
    connection: duckdb.DuckDBPyConnection,
    gold_table: str,
    columns: list[DcdColumn],
) -> None:
    """Convert each low-cardinality dimension to a DuckDB ENUM type.

    ENUM conversion is opportunistic: if DuckDB refuses (e.g. because
    the distinct set changed during the session) the column stays as
    its original type and materialization continues.
    """
    for column in columns:
        if column.role != "dimension":
            continue
        if column.cardinality is None or column.cardinality == 0:
            continue
        if column.cardinality >= _ENUM_CARDINALITY_THRESHOLD:
            continue
        try:
            validate_identifier(column.name)
        except SqlValidationError:
            continue
        enum_type = f"{gold_table}_{column.name}_enum"
        try:
            validate_identifier(enum_type)
        except SqlValidationError:
            continue
        quoted_col = quote_identifier(column.name)
        with contextlib.suppress(duckdb.Error):
            connection.execute(f"DROP TYPE IF EXISTS {enum_type}")
        try:
            connection.execute(
                f"CREATE TYPE {enum_type} AS ENUM "
                f"(SELECT DISTINCT {quoted_col} FROM {gold_table} "
                f"WHERE {quoted_col} IS NOT NULL)"
            )
            connection.execute(
                f"ALTER TABLE {gold_table} "
                f"ALTER COLUMN {quoted_col} TYPE {enum_type}"
            )
        except duckdb.Error:
            with contextlib.suppress(duckdb.Error):
                connection.execute(f"DROP TYPE IF EXISTS {enum_type}")
