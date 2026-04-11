"""Tests for src.materialization.quality."""

from __future__ import annotations

import duckdb
from src.materialization.optimizer import create_gold_table
from src.materialization.quality import run_quality_suite
from src.semantic.schema import DataContextDocument


def test_quality_suite_passes_on_clean_data(
    gold_connection: duckdb.DuckDBPyConnection,
    sample_dcd: DataContextDocument,
) -> None:
    create_gold_table(gold_connection, "raw_sales", "gold_sales", sample_dcd)
    report = run_quality_suite(gold_connection, "gold_sales", sample_dcd)
    assert report.table_name == "gold_sales"
    assert report.total_expectations > 0
    assert report.success_percent == 100.0
