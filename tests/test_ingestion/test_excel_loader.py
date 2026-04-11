"""Tests for the Excel loader."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import openpyxl
import pytest
from src.core.exceptions import SqlValidationError
from src.ingestion.loaders.excel_loader import ExcelLoader


@pytest.fixture
def loader() -> ExcelLoader:
    return ExcelLoader()


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture
def sample_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "sample.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["order_id", "region", "revenue"])
    ws.append([1, "North", 100.50])
    ws.append([2, "South", 89.00])
    ws.append([3, "East", 299.99])
    wb.save(path)
    return path


class TestDetect:
    def test_detects_xlsx(self, loader: ExcelLoader) -> None:
        assert loader.detect(Path("data.xlsx"))

    def test_detects_xls(self, loader: ExcelLoader) -> None:
        assert loader.detect(Path("data.xls"))

    def test_detects_xlsm(self, loader: ExcelLoader) -> None:
        assert loader.detect(Path("data.xlsm"))

    def test_rejects_csv(self, loader: ExcelLoader) -> None:
        assert not loader.detect(Path("data.csv"))


class TestLoad:
    def test_loads_sample_xlsx(
        self,
        loader: ExcelLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_xlsx: Path,
    ) -> None:
        result = loader.load(sample_xlsx, connection, "raw_xlsx")
        assert result.source_type == "excel"
        assert result.row_count == 3
        assert result.column_count == 3
        total = connection.execute("SELECT SUM(revenue) FROM raw_xlsx").fetchone()
        assert total is not None
        assert round(total[0], 2) == 489.49

    def test_rejects_invalid_identifier(
        self,
        loader: ExcelLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_xlsx: Path,
    ) -> None:
        with pytest.raises(SqlValidationError):
            loader.load(sample_xlsx, connection, "raw; DROP TABLE x")
