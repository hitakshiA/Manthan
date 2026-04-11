"""Tests for src.materialization.optimizer."""

from __future__ import annotations

import duckdb
from src.materialization.optimizer import create_gold_table, pick_sort_order
from src.semantic.schema import DataContextDocument


def test_pick_sort_order_puts_low_cardinality_first(
    sample_dcd: DataContextDocument,
) -> None:
    order = pick_sort_order(sample_dcd)
    # region (4) and customer_segment (2) are dimensions; order_date temporal.
    # customer_segment has lower cardinality than region.
    assert "customer_segment" in order
    assert "region" in order
    assert order.index("customer_segment") < order.index("region")
    assert order[-1] == "order_date"


def test_create_gold_table_sorts_and_comments(
    gold_connection: duckdb.DuckDBPyConnection,
    sample_dcd: DataContextDocument,
) -> None:
    sort_columns = create_gold_table(
        gold_connection, "raw_sales", "gold_sales", sample_dcd
    )
    assert sort_columns
    # Gold table exists and has the same row count as raw.
    row = gold_connection.execute("SELECT COUNT(*) FROM gold_sales").fetchone()
    assert row is not None
    assert row[0] == 10

    # Column comments were attached.
    comment_row = gold_connection.execute(
        "SELECT comment FROM duckdb_columns() "
        "WHERE table_name = 'gold_sales' AND column_name = 'revenue'"
    ).fetchone()
    assert comment_row is not None
    assert "revenue" in (comment_row[0] or "").lower() or comment_row[0]
