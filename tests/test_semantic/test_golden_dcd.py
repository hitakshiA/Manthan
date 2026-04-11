"""Golden DCD tests for three canonical synthetic datasets.

Uses ``httpx.MockTransport`` to stub the LLM classifier with a
hand-crafted JSON response per dataset so the pipeline is fully
deterministic. Asserts that the regenerated DCD matches a small set
of structural expectations — column roles, hierarchies, agent
instructions — rather than doing a full byte-for-byte YAML diff (the
latter would break on trivial changes like ``ingested_at``
timestamps, which is noise).

These tests are the contract between the pipeline and downstream
agent consumers: if a change breaks any of them, something the agent
relies on has shifted and the DCD schema docs should be updated.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
import pytest
from src.core.llm import LlmClient
from src.ingestion.base import LoadResult
from src.profiling.agent import profile_dataset
from src.semantic.generator import build_dcd
from src.semantic.schema import DataContextDocument

_GOLDEN_DIR = Path(__file__).parent.parent / "fixtures" / "golden"


def _mock_llm(classifications: list[dict[str, object]]) -> LlmClient:
    payload = {"classifications": classifications}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(payload),
                        }
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://openrouter.test/api/v1",
        headers={"Authorization": "Bearer test"},
    )
    return LlmClient(client=client)


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(":memory:")
    try:
        yield con
    finally:
        con.close()


def _load_csv(
    con: duckdb.DuckDBPyConnection, path: Path, table_name: str
) -> LoadResult:
    con.execute(
        f"CREATE TABLE {table_name} AS SELECT * FROM read_csv(?, auto_detect=true)",
        [str(path)],
    )
    row = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    row_count = int(row[0]) if row else 0
    col_row = con.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = ?",
        [table_name],
    ).fetchone()
    column_count = int(col_row[0]) if col_row else 0
    return LoadResult(
        table_name=table_name,
        source_type="csv",
        original_filename=path.name,
        ingested_at=datetime.now(UTC),
        row_count=row_count,
        column_count=column_count,
        raw_size_bytes=path.stat().st_size,
    )


async def _run_pipeline(
    connection: duckdb.DuckDBPyConnection,
    csv_path: Path,
    classifications: list[dict[str, object]],
) -> DataContextDocument:
    table_name = f"raw_{csv_path.stem}"
    load_result = _load_csv(connection, csv_path, table_name)
    async with _mock_llm(classifications) as llm:
        profiling_result = await profile_dataset(connection, table_name, llm)
    return build_dcd(
        dataset_id="ds_golden0001",
        load_result=load_result,
        profiling_result=profiling_result,
    )


_RETAIL_CLASSIFICATIONS = [
    {
        "name": "order_id",
        "role": "identifier",
        "description": "Unique order identifier",
        "aggregation": None,
        "confidence": 0.98,
        "reasoning": "Name ends in _id and the value pattern is unique per row.",
        "synonyms": ["transaction_id"],
    },
    {
        "name": "order_date",
        "role": "temporal",
        "description": "Date the order was placed",
        "aggregation": None,
        "confidence": 0.99,
        "reasoning": "Column name and DATE dtype match the temporal definition.",
        "synonyms": ["date"],
    },
    {
        "name": "region",
        "role": "dimension",
        "description": "Geographic sales region",
        "aggregation": None,
        "confidence": 0.95,
        "reasoning": "Low-cardinality categorical string of region names.",
        "synonyms": ["territory", "area"],
    },
    {
        "name": "product_category",
        "role": "dimension",
        "description": "Top-level product category",
        "aggregation": None,
        "confidence": 0.95,
        "reasoning": "Categorical string with a small set of distinct values.",
        "synonyms": ["category"],
    },
    {
        "name": "quantity",
        "role": "metric",
        "description": "Units ordered",
        "aggregation": "SUM",
        "confidence": 0.97,
        "reasoning": "Small positive integers that users aggregate.",
        "synonyms": ["units", "qty"],
    },
    {
        "name": "unit_price",
        "role": "metric",
        "description": "Price per unit in USD",
        "aggregation": "AVG",
        "confidence": 0.9,
        "reasoning": "Continuous numeric; users typically average price per unit.",
        "synonyms": ["price"],
    },
    {
        "name": "revenue",
        "role": "metric",
        "description": "Total order revenue in USD",
        "aggregation": "SUM",
        "confidence": 0.98,
        "reasoning": "Monetary continuous value; users always sum revenue.",
        "synonyms": ["sales", "total"],
    },
    {
        "name": "customer_segment",
        "role": "dimension",
        "description": "Customer segmentation tag",
        "aggregation": None,
        "confidence": 0.92,
        "reasoning": "Small categorical attribute used for grouping.",
        "synonyms": ["segment"],
    },
]


_HR_CLASSIFICATIONS = [
    {
        "name": "employee_id",
        "role": "identifier",
        "description": "Unique employee identifier",
        "aggregation": None,
        "confidence": 0.99,
        "reasoning": "Name ends in _id and values are unique per row.",
        "synonyms": ["emp_id"],
    },
    {
        "name": "department",
        "role": "dimension",
        "description": "Organizational department",
        "aggregation": None,
        "confidence": 0.95,
        "reasoning": "Low-cardinality categorical string.",
        "synonyms": ["org"],
    },
    {
        "name": "role",
        "role": "dimension",
        "description": "Job title",
        "aggregation": None,
        "confidence": 0.9,
        "reasoning": "Categorical string of job titles.",
        "synonyms": ["title", "position"],
    },
    {
        "name": "hire_date",
        "role": "temporal",
        "description": "Date the employee joined the company",
        "aggregation": None,
        "confidence": 0.99,
        "reasoning": "DATE dtype and name contains 'date'.",
        "synonyms": ["start_date"],
    },
    {
        "name": "annual_salary",
        "role": "metric",
        "description": "Annual base salary in USD",
        "aggregation": "AVG",
        "confidence": 0.96,
        "reasoning": "Monetary per-employee value averaged at group level.",
        "synonyms": ["salary", "compensation"],
    },
    {
        "name": "manager_id",
        "role": "identifier",
        "description": "Employee id of the direct manager",
        "aggregation": None,
        "confidence": 0.85,
        "reasoning": "Self-referential identifier column pointing back at employee_id.",
        "synonyms": ["supervisor_id"],
    },
]


_MARKETING_CLASSIFICATIONS = [
    {
        "name": "campaign_id",
        "role": "identifier",
        "description": "Marketing campaign identifier",
        "aggregation": None,
        "confidence": 0.97,
        "reasoning": "Name ends in _id and the values follow a campaign-code pattern.",
        "synonyms": ["campaign"],
    },
    {
        "name": "week",
        "role": "temporal",
        "description": "ISO-week string the row was bucketed into",
        "aggregation": None,
        "confidence": 0.95,
        "reasoning": "String but follows YYYY-WXX pattern signifying weekly grain.",
        "synonyms": ["iso_week"],
    },
    {
        "name": "channel",
        "role": "dimension",
        "description": "Marketing channel",
        "aggregation": None,
        "confidence": 0.95,
        "reasoning": "Low-cardinality categorical attribute.",
        "synonyms": ["medium"],
    },
    {
        "name": "stage",
        "role": "dimension",
        "description": "Funnel stage (Awareness / Consideration / Purchase)",
        "aggregation": None,
        "confidence": 0.95,
        "reasoning": "Categorical with a fixed funnel vocabulary.",
        "synonyms": ["funnel_stage"],
    },
    {
        "name": "users",
        "role": "metric",
        "description": "Unique users reached or engaged",
        "aggregation": "SUM",
        "confidence": 0.95,
        "reasoning": "Integer count; users aggregate by summing.",
        "synonyms": ["visitors", "audience"],
    },
    {
        "name": "conversions",
        "role": "metric",
        "description": "Conversion count",
        "aggregation": "SUM",
        "confidence": 0.97,
        "reasoning": "Integer count; users always sum conversions.",
        "synonyms": ["events"],
    },
    {
        "name": "spend_usd",
        "role": "metric",
        "description": "Marketing spend in USD",
        "aggregation": "SUM",
        "confidence": 0.98,
        "reasoning": "Continuous monetary value; always summed.",
        "synonyms": ["spend", "cost"],
    },
]


@pytest.mark.asyncio
async def test_retail_sales_golden(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    dcd = await _run_pipeline(
        connection,
        _GOLDEN_DIR / "retail_sales.csv",
        _RETAIL_CLASSIFICATIONS,
    )
    columns = {c.name: c for c in dcd.dataset.columns}

    # Role contract
    assert columns["order_id"].role == "identifier"
    assert columns["order_date"].role == "temporal"
    assert columns["region"].role == "dimension"
    assert columns["revenue"].role == "metric"
    assert columns["revenue"].aggregation == "SUM"
    assert columns["unit_price"].aggregation == "AVG"

    # Enriched fields populated
    assert columns["revenue"].classification_confidence == 0.98
    assert columns["revenue"].synonyms == ["sales", "total"]
    assert columns["revenue"].classification_reasoning is not None
    assert "sum" in columns["revenue"].classification_reasoning.lower()

    # Temporal metadata
    assert dcd.dataset.temporal.column == "order_date"
    assert dcd.dataset.temporal.grain in ("daily", "irregular")

    # Agent instructions mention identifier discipline
    instructions = " ".join(dcd.dataset.agent_instructions)
    assert "identifier" in instructions.lower()
    assert "order_id" in instructions

    # YAML round-trips
    restored = DataContextDocument.from_yaml(dcd.to_yaml())
    assert restored.dataset.columns[6].role == "metric"


@pytest.mark.asyncio
async def test_hr_roster_golden(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    dcd = await _run_pipeline(
        connection,
        _GOLDEN_DIR / "hr_roster.csv",
        _HR_CLASSIFICATIONS,
    )
    columns = {c.name: c for c in dcd.dataset.columns}

    assert columns["employee_id"].role == "identifier"
    assert columns["manager_id"].role == "identifier"
    assert columns["hire_date"].role == "temporal"
    assert columns["annual_salary"].role == "metric"
    assert columns["annual_salary"].aggregation == "AVG"

    # Confidence + synonyms preserved end-to-end
    assert columns["annual_salary"].classification_confidence == 0.96
    assert "salary" in columns["annual_salary"].synonyms

    # Both identifier columns must appear in the agent-instruction directive
    instructions = " ".join(dcd.dataset.agent_instructions)
    assert "employee_id" in instructions
    assert "manager_id" in instructions


@pytest.mark.asyncio
async def test_marketing_funnel_golden(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    dcd = await _run_pipeline(
        connection,
        _GOLDEN_DIR / "marketing_funnel.csv",
        _MARKETING_CLASSIFICATIONS,
    )
    columns = {c.name: c for c in dcd.dataset.columns}

    assert columns["campaign_id"].role == "identifier"
    assert columns["channel"].role == "dimension"
    assert columns["stage"].role == "dimension"
    assert columns["users"].aggregation == "SUM"
    assert columns["conversions"].aggregation == "SUM"
    assert columns["spend_usd"].aggregation == "SUM"

    # Three metric rules appear in the agent instructions
    instructions = " ".join(dcd.dataset.agent_instructions)
    assert instructions.count("SUM") >= 3

    # Temporal column is the ISO-week string (classifier marked it temporal
    # even though the dtype is VARCHAR)
    assert dcd.dataset.temporal.column == "week"
