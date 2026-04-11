"""Excel loader via DuckDB's ``excel`` extension.

Handles ``.xlsx``, ``.xls``, and ``.xlsm`` inputs. The ``excel`` extension
is auto-installed on first use; subsequent calls reuse the cached binary.
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


class ExcelLoader:
    """Load Excel workbooks into DuckDB."""

    _EXTENSIONS: ClassVar[frozenset[str]] = frozenset({".xlsx", ".xls", ".xlsm"})
    source_type: ClassVar[str] = "excel"

    def detect(self, input_path: Path) -> bool:
        return input_path.suffix.lower() in self._EXTENSIONS

    def load(
        self,
        input_path: Path,
        connection: duckdb.DuckDBPyConnection,
        table_name: str,
    ) -> LoadResult:
        validate_identifier(table_name)
        try:
            connection.execute("INSTALL excel")
            connection.execute("LOAD excel")
            connection.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_xlsx(?)",
                [str(input_path)],
            )
        except duckdb.Error as exc:
            raise IngestionError(
                f"Failed to read Excel {input_path.name}: {exc}"
            ) from exc

        return LoadResult(
            table_name=table_name,
            source_type="excel",
            original_filename=input_path.name,
            ingested_at=datetime.now(UTC),
            row_count=count_rows(connection, table_name),
            column_count=count_columns(connection, table_name),
            raw_size_bytes=input_path.stat().st_size,
        )
