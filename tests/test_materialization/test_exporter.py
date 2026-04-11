"""Tests for src.materialization.exporter."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
from src.materialization.exporter import export_dataset
from src.materialization.optimizer import create_gold_table
from src.materialization.query_generator import generate_verified_queries
from src.materialization.summarizer import create_summary_tables
from src.semantic.schema import DataContextDocument


def test_export_writes_parquet_yaml_and_json(
    gold_connection: duckdb.DuckDBPyConnection,
    sample_dcd: DataContextDocument,
    tmp_path: Path,
) -> None:
    create_gold_table(gold_connection, "raw_sales", "gold_sales", sample_dcd)
    summaries = create_summary_tables(gold_connection, "gold_sales", sample_dcd)

    enriched = sample_dcd.model_copy(
        update={
            "dataset": sample_dcd.dataset.model_copy(
                update={
                    "verified_queries": generate_verified_queries(
                        sample_dcd, gold_table="gold_sales"
                    )
                }
            )
        }
    )

    dataset_dir = export_dataset(
        connection=gold_connection,
        dataset_id="ds_test000001",
        gold_table="gold_sales",
        summary_tables=summaries,
        dcd=enriched,
        data_directory=tmp_path,
    )

    assert dataset_dir.exists()
    assert (dataset_dir / "manthan-context.yaml").exists()
    assert (dataset_dir / "verified-queries.json").exists()
    assert (dataset_dir / "data" / "gold_sales.parquet").exists()
    assert (dataset_dir / "data" / "gold_sales_daily.parquet").exists()

    # Verified queries JSON parses and is non-empty.
    queries = json.loads((dataset_dir / "verified-queries.json").read_text())
    assert isinstance(queries, list)
    assert queries

    # Re-read the Parquet and verify row count.
    con = duckdb.connect(":memory:")
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM read_parquet(?)",
            [str(dataset_dir / "data" / "gold_sales.parquet")],
        ).fetchone()
        assert row is not None
        assert row[0] == 10
    finally:
        con.close()
