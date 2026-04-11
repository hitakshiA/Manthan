"""JSON loader via DuckDB's ``read_json_auto``.

Handles ``.json``, ``.jsonl``, and ``.ndjson`` inputs. Nested objects are
flattened to columns by DuckDB's auto-detection, and arrays are exploded
to rows where the top-level document is an array of records.
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


class JsonLoader:
    """Load JSON / NDJSON files into DuckDB."""

    _EXTENSIONS: ClassVar[frozenset[str]] = frozenset({".json", ".jsonl", ".ndjson"})
    source_type: ClassVar[str] = "json"

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
            connection.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT * FROM read_json_auto(?)",
                [str(input_path)],
            )
        except duckdb.Error as exc:
            raise IngestionError(
                f"Failed to read JSON {input_path.name}: {exc}"
            ) from exc

        return LoadResult(
            table_name=table_name,
            source_type="json",
            original_filename=input_path.name,
            ingested_at=datetime.now(UTC),
            row_count=count_rows(connection, table_name),
            column_count=count_columns(connection, table_name),
            raw_size_bytes=input_path.stat().st_size,
        )
