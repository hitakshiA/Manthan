"""Tests for the CSV loader."""

from pathlib import Path

import duckdb
import pytest
from src.core.exceptions import IngestionError, SqlValidationError
from src.ingestion.loaders.csv_loader import CsvLoader


@pytest.fixture
def loader() -> CsvLoader:
    return CsvLoader()


@pytest.fixture
def connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    yield con
    con.close()


class TestDetect:
    def test_detects_csv(self, loader: CsvLoader) -> None:
        assert loader.detect(Path("sales.csv"))

    def test_detects_csv_case_insensitive(self, loader: CsvLoader) -> None:
        assert loader.detect(Path("SALES.CSV"))

    def test_detects_tsv(self, loader: CsvLoader) -> None:
        assert loader.detect(Path("data.tsv"))

    def test_detects_txt(self, loader: CsvLoader) -> None:
        assert loader.detect(Path("data.txt"))

    def test_rejects_parquet(self, loader: CsvLoader) -> None:
        assert not loader.detect(Path("data.parquet"))

    def test_rejects_json(self, loader: CsvLoader) -> None:
        assert not loader.detect(Path("data.json"))


class TestLoad:
    def test_loads_sample_sales_csv(
        self,
        loader: CsvLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_csv_path: Path,
    ) -> None:
        result = loader.load(sample_csv_path, connection, "raw_sales")

        assert result.table_name == "raw_sales"
        assert result.source_type == "csv"
        assert result.original_filename == "sample_sales.csv"
        assert result.row_count == 10
        assert result.column_count == 6
        assert result.raw_size_bytes is not None
        assert result.raw_size_bytes > 0

    def test_loaded_data_is_queryable(
        self,
        loader: CsvLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_csv_path: Path,
    ) -> None:
        loader.load(sample_csv_path, connection, "raw_sales")
        total = connection.execute("SELECT SUM(revenue) FROM raw_sales").fetchone()
        assert total is not None
        # Sum of the revenue column in the fixture.
        assert round(total[0], 2) == 1983.24

    def test_loaded_data_preserves_dimension_values(
        self,
        loader: CsvLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_csv_path: Path,
    ) -> None:
        loader.load(sample_csv_path, connection, "raw_sales")
        regions = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT region FROM raw_sales"
            ).fetchall()
        }
        assert regions == {"North", "South", "East", "West"}

    def test_rejects_invalid_identifier(
        self,
        loader: CsvLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_csv_path: Path,
    ) -> None:
        with pytest.raises(SqlValidationError):
            loader.load(sample_csv_path, connection, "raw; DROP TABLE users")

    def test_wraps_duckdb_errors_as_ingestion_error(
        self,
        loader: CsvLoader,
        connection: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        bogus = tmp_path / "not_really_csv.csv"
        bogus.write_bytes(b"\x00\x01\x02\x03binary garbage\xff\xfe")
        with pytest.raises((IngestionError,)):
            loader.load(bogus, connection, "raw_bogus")
