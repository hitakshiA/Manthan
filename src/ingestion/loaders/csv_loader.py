"""CSV loader backed by DuckDB's ``read_csv`` with auto-detection.

Handles ``.csv``, ``.tsv``, and ``.txt`` inputs. Delegates delimiter,
encoding, and type inference to DuckDB's auto-detection with an explicit
sample size matching SPEC.md §5.2.
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

# Number of rows DuckDB samples to infer types during auto-detection.
# Matches SPEC.md §5.2. Kept as a module-level constant rather than a
# Settings field because it is an implementation detail of this loader
# and not something operators routinely tune.
_CSV_AUTO_DETECT_SAMPLE_SIZE = 10000


class CsvLoader:
    """Load CSV/TSV files into DuckDB via ``read_csv`` auto-detection."""

    _EXTENSIONS: ClassVar[frozenset[str]] = frozenset({".csv", ".tsv", ".txt"})
    source_type: ClassVar[str] = "csv"

    def detect(self, input_path: Path) -> bool:
        """Return ``True`` for files with a ``.csv``, ``.tsv``, or ``.txt`` suffix."""
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
            IngestionError: If DuckDB fails to parse the CSV.
        """
        validate_identifier(table_name)
        try:
            connection.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT * FROM read_csv(?, auto_detect=true, "
                f"sample_size={_CSV_AUTO_DETECT_SAMPLE_SIZE})",
                [str(input_path)],
            )
        except duckdb.Error as exc:
            raise IngestionError(
                f"Failed to parse CSV {input_path.name}: {exc}"
            ) from exc

        return LoadResult(
            table_name=table_name,
            source_type="csv",
            original_filename=input_path.name,
            ingested_at=datetime.now(UTC),
            row_count=count_rows(connection, table_name),
            column_count=count_columns(connection, table_name),
            raw_size_bytes=input_path.stat().st_size,
        )
