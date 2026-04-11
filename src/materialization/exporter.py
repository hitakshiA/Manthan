"""Parquet export and dataset directory assembly.

After optimization and summary-table creation, :func:`export_dataset`
writes the Gold table and every summary table to Parquet inside a
canonical dataset directory (``/{data_directory}/{dataset_id}/``),
serializes the DCD to ``manthan-context.yaml``, and writes the
verified-queries payload to ``verified-queries.json``.

The resulting directory is the atomic, portable unit of a Manthan
dataset per SPEC §3.3 — copy it anywhere and any DuckDB process can
reconstruct the agent-queryable view.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from src.ingestion.base import validate_identifier
from src.semantic.schema import DataContextDocument


def export_dataset(
    *,
    connection: duckdb.DuckDBPyConnection,
    dataset_id: str,
    gold_table: str,
    summary_tables: list[str],
    dcd: DataContextDocument,
    data_directory: Path,
) -> Path:
    """Materialize every artifact for ``dataset_id`` to Parquet + YAML.

    Args:
        connection: Active DuckDB connection with ``gold_table`` and
            every summary table already created.
        dataset_id: Registry-assigned dataset identifier.
        gold_table: Name of the optimized Gold table.
        summary_tables: Names of all summary tables to export.
        dcd: The Data Context Document for the dataset.
        data_directory: Parent directory under which the per-dataset
            subdirectory is created.

    Returns:
        The absolute path to the created dataset directory.
    """
    validate_identifier(gold_table)
    for name in summary_tables:
        validate_identifier(name)

    dataset_dir = data_directory / dataset_id
    data_dir = dataset_dir / "data"
    metadata_dir = dataset_dir / "metadata"
    data_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    # Gold table -> Parquet
    gold_path = data_dir / f"{gold_table}.parquet"
    connection.table(gold_table).write_parquet(str(gold_path))

    # Summary tables -> Parquet
    for summary in summary_tables:
        summary_path = data_dir / f"{summary}.parquet"
        connection.table(summary).write_parquet(str(summary_path))

    # DCD -> YAML
    (dataset_dir / "manthan-context.yaml").write_text(dcd.to_yaml())

    # Verified queries -> JSON (for few-shot agent prompting)
    verified_queries = [q.model_dump() for q in dcd.dataset.verified_queries]
    (dataset_dir / "verified-queries.json").write_text(
        json.dumps(verified_queries, indent=2, default=str)
    )

    return dataset_dir.resolve()
