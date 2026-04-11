"""Gold-stage table optimizer.

Rewrites a raw table into a Gold table sorted on the primary dimensions
(ascending cardinality) and the temporal column, then attaches
``COMMENT ON`` descriptions from the DCD so the schema is
self-documenting at the database level. Per SPEC §3.1.

ENUM type conversion (also described in SPEC §3.1) is intentionally
skipped for this pass: creating and attaching ENUM types in DuckDB
requires either rewriting the column or recreating the table, both of
which add complexity without affecting correctness. We can revisit once
the end-to-end flow is demonstrably working.
"""

from __future__ import annotations

import duckdb

from src.ingestion.base import quote_identifier, validate_identifier
from src.semantic.schema import DataContextDocument, DcdColumn


def create_gold_table(
    connection: duckdb.DuckDBPyConnection,
    raw_table: str,
    gold_table: str,
    dcd: DataContextDocument,
) -> list[str]:
    """Build the Gold table and attach documentation comments.

    Args:
        connection: Active DuckDB connection.
        raw_table: Name of the Bronze table to transform.
        gold_table: Name to give the Gold table (created or replaced).
        dcd: The Data Context Document for ``raw_table``.

    Returns:
        The column names used in the ``ORDER BY`` clause, in order. May
        be empty when the DCD has no dimensions or temporal column.
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

    return sort_columns


def pick_sort_order(dcd: DataContextDocument) -> list[str]:
    """Return the Gold-table sort order for ``dcd``.

    Dimensions are sorted ascending by cardinality (lowest first) so
    that zone maps on DuckDB row groups prune as aggressively as
    possible for typical ``WHERE dim = X AND date BETWEEN Y AND Z``
    queries. The temporal column is appended last.
    """
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
