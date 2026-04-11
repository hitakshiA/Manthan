"""Ingestion gateway: source detection and loader dispatch.

The gateway is the single entry point for Bronze-stage ingestion. Callers
hand it a path, a DuckDB connection, and a target table name; it walks its
registered loaders, picks the first one whose ``detect`` returns ``True``,
and delegates the load. This keeps the API layer and the registry
completely ignorant of which loader handles which format.

Use :func:`create_default_gateway` to get a gateway wired up with every
loader currently supported by the data layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb

from src.core.exceptions import IngestionError
from src.ingestion.base import Loader, LoadResult
from src.ingestion.loaders.csv_loader import CsvLoader
from src.ingestion.loaders.parquet_loader import ParquetLoader


class IngestionGateway:
    """Route input files to the first loader that claims them."""

    def __init__(self, loaders: Sequence[Loader]) -> None:
        self._loaders: list[Loader] = list(loaders)

    def load(
        self,
        input_path: Path,
        connection: duckdb.DuckDBPyConnection,
        table_name: str,
    ) -> LoadResult:
        """Load ``input_path`` into ``connection`` as ``table_name``.

        Raises:
            IngestionError: If no registered loader can handle the path.
        """
        for loader in self._loaders:
            if loader.detect(input_path):
                return loader.load(input_path, connection, table_name)
        raise IngestionError(
            f"No loader registered for source: {input_path.name} "
            f"(suffix {input_path.suffix!r})"
        )


def create_default_gateway() -> IngestionGateway:
    """Return a gateway wired up with every built-in loader.

    Currently: :class:`CsvLoader` and :class:`ParquetLoader`. Excel, JSON,
    and database loaders will be added in subsequent phases.
    """
    return IngestionGateway(
        loaders=[
            CsvLoader(),
            ParquetLoader(),
        ]
    )
