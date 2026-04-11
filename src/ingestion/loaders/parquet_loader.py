"""Parquet loader backed by DuckDB's ``read_parquet``.

Parquet files are already columnar and self-describing so no type
inference is needed; DuckDB reads them directly with predicate pushdown
against row group statistics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import duckdb

from src.core.exceptions import IngestionError
from src.ingestion.base import (
    LoadResult,
    count_columns,
    count_rows,
    validate_identifier,
)


class ParquetLoader:
    """Load Parquet files into DuckDB via ``read_parquet``."""

    _EXTENSIONS: ClassVar[frozenset[str]] = frozenset({".parquet", ".pq"})
    source_type: ClassVar[str] = "parquet"

    def detect(self, input_path: Path) -> bool:
        """Return ``True`` for files with a ``.parquet`` or ``.pq`` suffix."""
        return input_path.suffix.lower() in self._EXTENSIONS

    def load(
        self,
        input_path: Path,
        connection: duckdb.DuckDBPyConnection,
        table_name: str,
    ) -> LoadResult:
        """Load ``input_path`` into DuckDB as ``table_name``.

        Raises:
            SqlValidationError: If ``table_name`` is not a valid identifier.
            IngestionError: If DuckDB fails to read the Parquet file.
        """
        validate_identifier(table_name)
        try:
            connection.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT * FROM read_parquet(?)",
                [str(input_path)],
            )
        except duckdb.Error as exc:
            raise IngestionError(
                f"Failed to read Parquet {input_path.name}: {exc}"
            ) from exc

        return LoadResult(
            table_name=table_name,
            source_type="parquet",
            original_filename=input_path.name,
            ingested_at=datetime.now(UTC),
            row_count=count_rows(connection, table_name),
            column_count=count_columns(connection, table_name),
            raw_size_bytes=input_path.stat().st_size,
        )
