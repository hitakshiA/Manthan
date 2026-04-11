"""Shared fixtures for ingestion tests.

Provides paths to checked-in synthetic test data (``tests/fixtures/``) and
helpers that produce Parquet files at runtime so we don't have to check
binary fixtures into git.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_csv_path() -> Path:
    """Path to the checked-in 10-row synthetic sales CSV."""
    path = FIXTURES_DIR / "sample_sales.csv"
    assert path.exists(), f"Missing fixture: {path}"
    return path


@pytest.fixture
def sample_parquet_path(tmp_path: Path, sample_csv_path: Path) -> Path:
    """Generate a Parquet copy of the sample CSV in a tmp dir.

    Uses the DuckDB Python relation API (``read_csv`` + ``write_parquet``)
    because DuckDB's SQL ``COPY ... TO`` statement does not accept a
    parameter-bound destination path.
    """
    destination = tmp_path / "sample_sales.parquet"
    connection = duckdb.connect(":memory:")
    try:
        connection.read_csv(str(sample_csv_path)).write_parquet(str(destination))
    finally:
        connection.close()
    return destination
