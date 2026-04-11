"""Tests for src.profiling.agent (end-to-end Silver pipeline)."""

from __future__ import annotations

import json

import duckdb
import httpx
import pytest
from src.core.llm import LlmClient
from src.profiling.agent import profile_dataset


def _build_mock_llm(content: str) -> LlmClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": content}}]},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://openrouter.test/api/v1",
        headers={"Authorization": "Bearer test"},
    )
    return LlmClient(client=client)


_SAMPLE_CLASSIFICATIONS = json.dumps(
    {
        "classifications": [
            {
                "name": "order_id",
                "role": "identifier",
                "description": "Unique order identifier",
                "aggregation": None,
            },
            {
                "name": "order_date",
                "role": "temporal",
                "description": "Date when the order was placed",
                "aggregation": None,
            },
            {
                "name": "region",
                "role": "dimension",
                "description": "Sales region",
                "aggregation": None,
            },
            {
                "name": "revenue",
                "role": "metric",
                "description": "Total order amount",
                "aggregation": "SUM",
            },
            {
                "name": "quantity",
                "role": "metric",
                "description": "Units ordered",
                "aggregation": "SUM",
            },
            {
                "name": "customer_segment",
                "role": "dimension",
                "description": "Customer segment tag",
                "aggregation": None,
            },
        ]
    }
)


@pytest.mark.asyncio
async def test_profile_dataset_runs_end_to_end(
    raw_sales_connection: duckdb.DuckDBPyConnection,
) -> None:
    async with _build_mock_llm(_SAMPLE_CLASSIFICATIONS) as llm:
        result = await profile_dataset(raw_sales_connection, "raw_sales", llm)

    assert result.table_name == "raw_sales"
    assert len(result.column_profiles) == 6
    assert len(result.classifications) == 6
    assert len(result.pii_flags) == 6

    # Temporal detection should pick order_date (classified or by dtype).
    assert result.temporal_column == "order_date"
    assert result.temporal_grain in ("daily", "irregular")

    # Metric proposals fire because we have revenue + order_id.
    metric_names = {m.name for m in result.metric_proposals}
    assert any("revenue" in n for n in metric_names)

    # No warnings about metric aggregation (classifier gave SUM for all metrics).
    aggregation_warnings = [w for w in result.warnings if "aggregation rule" in w]
    assert aggregation_warnings == []


@pytest.mark.asyncio
async def test_profile_dataset_surfaces_warnings_when_classifier_is_wrong(
    raw_sales_connection: duckdb.DuckDBPyConnection,
) -> None:
    # Classify region (VARCHAR) as a metric — should produce warnings.
    bogus = json.dumps(
        {
            "classifications": [
                {
                    "name": "region",
                    "role": "metric",
                    "description": "oops",
                    "aggregation": None,  # also no aggregation → second warning
                }
            ]
        }
    )
    async with _build_mock_llm(bogus) as llm:
        result = await profile_dataset(raw_sales_connection, "raw_sales", llm)

    assert any("aggregation rule" in w for w in result.warnings)
    assert any("dtype is VARCHAR" in w for w in result.warnings)
