"""Tests for src.materialization.query_generator."""

from __future__ import annotations

import duckdb
from src.materialization.optimizer import create_gold_table
from src.materialization.query_generator import generate_verified_queries
from src.semantic.schema import DataContextDocument


def test_generates_pairs(sample_dcd: DataContextDocument) -> None:
    pairs = generate_verified_queries(sample_dcd, gold_table="gold_sales")
    assert len(pairs) >= 6
    intents = {p.intent for p in pairs}
    assert {"breakdown", "summary", "trend", "change"}.issubset(intents)


def test_generated_sql_executes_on_gold_table(
    gold_connection: duckdb.DuckDBPyConnection,
    sample_dcd: DataContextDocument,
) -> None:
    create_gold_table(gold_connection, "raw_sales", "gold_sales", sample_dcd)
    pairs = generate_verified_queries(sample_dcd, gold_table="gold_sales")

    for pair in pairs:
        result = gold_connection.execute(pair.sql).fetchall()
        assert result is not None
