"""Tests for the Parquet loader."""

from pathlib import Path

import duckdb
import pytest
from src.ingestion.loaders.parquet_loader import ParquetLoader


@pytest.fixture
def loader() -> ParquetLoader:
    return ParquetLoader()


@pytest.fixture
def connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    yield con
    con.close()


class TestDetect:
    def test_detects_parquet(self, loader: ParquetLoader) -> None:
        assert loader.detect(Path("data.parquet"))

    def test_detects_parquet_case_insensitive(self, loader: ParquetLoader) -> None:
        assert loader.detect(Path("DATA.PARQUET"))

    def test_detects_pq(self, loader: ParquetLoader) -> None:
        assert loader.detect(Path("data.pq"))

    def test_rejects_csv(self, loader: ParquetLoader) -> None:
        assert not loader.detect(Path("data.csv"))


class TestLoad:
    def test_loads_parquet_file(
        self,
        loader: ParquetLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_parquet_path: Path,
    ) -> None:
        result = loader.load(sample_parquet_path, connection, "raw_sales_parquet")

        assert result.table_name == "raw_sales_parquet"
        assert result.source_type == "parquet"
        assert result.row_count == 10
        assert result.column_count == 6

    def test_loaded_data_matches_csv_source(
        self,
        loader: ParquetLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_parquet_path: Path,
    ) -> None:
        loader.load(sample_parquet_path, connection, "raw_sales_parquet")
        total = connection.execute(
            "SELECT SUM(revenue) FROM raw_sales_parquet"
        ).fetchone()
        assert total is not None
        assert round(total[0], 2) == 1983.24
