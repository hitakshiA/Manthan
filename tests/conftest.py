"""Top-level pytest fixtures.

- ``_isolated_settings``: autouse fixture that sets a safe
  ``OPENROUTER_API_KEY`` and clears the settings cache before every test.
- ``gold_connection``: a DuckDB in-memory connection with
  ``sample_sales.csv`` preloaded as ``raw_sales``.
- ``sample_dcd``: a fully-populated Data Context Document built from
  ``sample_sales.csv`` using deterministic (non-LLM) classifications —
  used by every test that needs a DCD without reaching out to an LLM.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from src.core.config import get_settings
from src.ingestion.base import LoadResult
from src.profiling.agent import ProfilingResult
from src.profiling.classifier import ColumnClassification
from src.profiling.enricher import MetricProposal
from src.profiling.pii_detector import classify_column
from src.profiling.statistical import profile_columns
from src.semantic.generator import build_dcd
from src.semantic.schema import DataContextDocument

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force every test to see a fresh, test-safe Settings singleton."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key-fixture")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def gold_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """DuckDB connection with ``sample_sales.csv`` loaded as ``raw_sales``."""
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE raw_sales AS SELECT * FROM read_csv(?, auto_detect=true)",
            [str(_FIXTURES_DIR / "sample_sales.csv")],
        )
        yield connection
    finally:
        connection.close()


@pytest.fixture
def sample_dcd(gold_connection: duckdb.DuckDBPyConnection) -> DataContextDocument:
    """Deterministic DCD built from sample_sales.csv without an LLM."""
    profiles = profile_columns(gold_connection, "raw_sales")
    classifications = [
        ColumnClassification(
            name="order_id",
            role="identifier",
            description="Unique order identifier",
            aggregation=None,
        ),
        ColumnClassification(
            name="order_date",
            role="temporal",
            description="Date when the order was placed",
            aggregation=None,
        ),
        ColumnClassification(
            name="region",
            role="dimension",
            description="Sales region",
            aggregation=None,
        ),
        ColumnClassification(
            name="revenue",
            role="metric",
            description="Total order amount in USD",
            aggregation="SUM",
        ),
        ColumnClassification(
            name="quantity",
            role="metric",
            description="Units ordered",
            aggregation="SUM",
        ),
        ColumnClassification(
            name="customer_segment",
            role="dimension",
            description="Customer segment",
            aggregation=None,
        ),
    ]
    pii_flags = [classify_column(p) for p in profiles]

    load_result = LoadResult(
        table_name="raw_sales",
        source_type="csv",
        original_filename="sample_sales.csv",
        ingested_at=datetime.now(UTC),
        row_count=10,
        column_count=6,
        raw_size_bytes=512,
    )

    profiling_result = ProfilingResult(
        table_name="raw_sales",
        column_profiles=profiles,
        classifications=classifications,
        pii_flags=pii_flags,
        temporal_column="order_date",
        temporal_grain="daily",
        metric_proposals=[
            MetricProposal(
                name="average_revenue_per_order_id",
                formula="SUM(revenue) / COUNT(DISTINCT order_id)",
                description="Average revenue per unique order",
                depends_on=["revenue", "order_id"],
            )
        ],
    )

    return build_dcd(
        dataset_id="ds_test000001",
        load_result=load_result,
        profiling_result=profiling_result,
    )
