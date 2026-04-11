"""Tests for src.materialization.summarizer."""

from __future__ import annotations

import duckdb
from src.materialization.optimizer import create_gold_table
from src.materialization.summarizer import create_summary_tables
from src.semantic.schema import DataContextDocument


def test_creates_rollup_and_breakdowns(
    gold_connection: duckdb.DuckDBPyConnection,
    sample_dcd: DataContextDocument,
) -> None:
    create_gold_table(gold_connection, "raw_sales", "gold_sales", sample_dcd)
    summaries = create_summary_tables(gold_connection, "gold_sales", sample_dcd)

    # Should include one daily rollup and one breakdown per dimension.
    assert "gold_sales_daily" in summaries
    assert "gold_sales_by_region" in summaries
    assert "gold_sales_by_customer_segment" in summaries


def test_rollup_preserves_total_revenue(
    gold_connection: duckdb.DuckDBPyConnection,
    sample_dcd: DataContextDocument,
) -> None:
    create_gold_table(gold_connection, "raw_sales", "gold_sales", sample_dcd)
    create_summary_tables(gold_connection, "gold_sales", sample_dcd)

    raw_total = gold_connection.execute(
        "SELECT SUM(revenue) FROM gold_sales"
    ).fetchone()
    rollup_total = gold_connection.execute(
        'SELECT SUM("revenue") FROM gold_sales_daily'
    ).fetchone()
    assert raw_total is not None
    assert rollup_total is not None
    assert round(raw_total[0], 2) == round(rollup_total[0], 2)


def test_dimension_breakdown_records_sum(
    gold_connection: duckdb.DuckDBPyConnection,
    sample_dcd: DataContextDocument,
) -> None:
    create_gold_table(gold_connection, "raw_sales", "gold_sales", sample_dcd)
    create_summary_tables(gold_connection, "gold_sales", sample_dcd)

    records = gold_connection.execute(
        "SELECT SUM(record_count) FROM gold_sales_by_region"
    ).fetchone()
    assert records is not None
    assert records[0] == 10
