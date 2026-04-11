"""Shared fixtures for profiling tests.

Provides a DuckDB connection with the sample sales CSV already loaded
into a ``raw_sales`` table so that every test in this package can target
the same known-good dataset.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def raw_sales_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield an in-memory DuckDB connection with the sample CSV loaded.

    The table is named ``raw_sales`` and contains 10 rows with the six
    columns defined in ``tests/fixtures/sample_sales.csv``.
    """
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE raw_sales AS SELECT * FROM read_csv(?, auto_detect=true)",
            [str(FIXTURES_DIR / "sample_sales.csv")],
        )
        yield connection
    finally:
        connection.close()
