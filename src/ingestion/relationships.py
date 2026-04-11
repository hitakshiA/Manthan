"""Foreign-key detection across multiple tables in one dataset.

When an agent uploads several related files (orders.csv, customers.csv,
products.csv), Layer 1 needs to tell the downstream agent how to join
them. This module implements a simple but effective heuristic:

1. Find columns that appear in more than one table by name equality.
2. For each such pair, verify value containment: are the distinct
   non-null values of one column a subset of the other?
3. If yes, emit a :class:`DcdRelationship` pointing from the subset
   side to the superset side. That's the foreign-key direction.

The algorithm is intentionally conservative — it won't invent joins.
It only reports relationships the data itself confirms.
"""

from __future__ import annotations

import duckdb

from src.ingestion.base import quote_identifier, validate_identifier
from src.semantic.schema import DcdRelationship

_CONFIDENCE = 0.9


def detect_relationships(
    connection: duckdb.DuckDBPyConnection,
    table_names: list[str],
) -> list[DcdRelationship]:
    """Return every detected foreign key across ``table_names``.

    Args:
        connection: Live DuckDB connection containing every named table.
        table_names: The tables to scan for cross-table relationships.

    Returns:
        A list of :class:`DcdRelationship` entries pointing from the
        subset-value side to the superset-value side. May be empty.
    """
    if len(table_names) < 2:
        return []

    table_columns: dict[str, set[str]] = {}
    for table in table_names:
        validate_identifier(table)
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        table_columns[table] = {row[0] for row in rows}

    relationships: list[DcdRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()

    for i, t1 in enumerate(table_names):
        for t2 in table_names[i + 1 :]:
            shared = table_columns[t1] & table_columns[t2]
            for column in shared:
                if _is_value_subset(connection, t1, column, t2, column):
                    key = (t1, column, t2, column)
                    if key not in seen:
                        seen.add(key)
                        relationships.append(
                            DcdRelationship(
                                from_table=t1,
                                from_column=column,
                                to_table=t2,
                                to_column=column,
                                kind="foreign_key",
                                confidence=_CONFIDENCE,
                            )
                        )
                elif _is_value_subset(connection, t2, column, t1, column):
                    key = (t2, column, t1, column)
                    if key not in seen:
                        seen.add(key)
                        relationships.append(
                            DcdRelationship(
                                from_table=t2,
                                from_column=column,
                                to_table=t1,
                                to_column=column,
                                kind="foreign_key",
                                confidence=_CONFIDENCE,
                            )
                        )
    return relationships


def _is_value_subset(
    connection: duckdb.DuckDBPyConnection,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> bool:
    """Return ``True`` when every non-null value in child appears in parent."""
    validate_identifier(child_table)
    validate_identifier(parent_table)
    qc = quote_identifier(child_column)
    qp = quote_identifier(parent_column)

    # Non-empty child check first — a totally empty child column would
    # trivially be a "subset" but carries no join information.
    child_count = connection.execute(
        f"SELECT COUNT(*) FROM {child_table} WHERE {qc} IS NOT NULL"
    ).fetchone()
    if child_count is None or int(child_count[0]) == 0:
        return False

    orphan_count = connection.execute(
        f"SELECT COUNT(*) FROM ("
        f"  SELECT DISTINCT {qc} AS v FROM {child_table} WHERE {qc} IS NOT NULL"
        f") child WHERE child.v NOT IN ("
        f"  SELECT {qp} FROM {parent_table} WHERE {qp} IS NOT NULL"
        f")"
    ).fetchone()
    return orphan_count is not None and int(orphan_count[0]) == 0
