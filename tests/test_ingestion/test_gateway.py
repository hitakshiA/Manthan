"""Tests for the ingestion gateway dispatcher."""

from pathlib import Path

import duckdb
import pytest
from src.core.exceptions import IngestionError
from src.ingestion.gateway import IngestionGateway, create_default_gateway


@pytest.fixture
def connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    yield con
    con.close()


def test_default_gateway_routes_csv(
    connection: duckdb.DuckDBPyConnection, sample_csv_path: Path
) -> None:
    gateway = create_default_gateway()
    result = gateway.load(sample_csv_path, connection, "raw_sales")
    assert result.source_type == "csv"
    assert result.row_count == 10


def test_default_gateway_routes_parquet(
    connection: duckdb.DuckDBPyConnection, sample_parquet_path: Path
) -> None:
    gateway = create_default_gateway()
    result = gateway.load(sample_parquet_path, connection, "raw_sales_parquet")
    assert result.source_type == "parquet"
    assert result.row_count == 10


def test_gateway_raises_when_no_loader_matches(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    unsupported = tmp_path / "data.xyz"
    unsupported.write_text("nope")
    gateway = create_default_gateway()
    with pytest.raises(IngestionError, match="No loader registered"):
        gateway.load(unsupported, connection, "raw_unsupported")


def test_empty_gateway_rejects_everything(
    connection: duckdb.DuckDBPyConnection, sample_csv_path: Path
) -> None:
    gateway = IngestionGateway(loaders=[])
    with pytest.raises(IngestionError):
        gateway.load(sample_csv_path, connection, "raw_sales")
