"""End-to-end API tests for the datasets + tools routers.

Uses ``httpx.MockTransport`` to stub the LLM classifier so the profiling
agent runs without any network traffic, then drives the full Bronze ->
Silver -> Gold pipeline through the FastAPI routes.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from src.api.datasets import get_llm_client_factory
from src.core.database import create_connection
from src.core.llm import LlmClient
from src.core.memory import MemoryStore
from src.core.plans import PlanStore
from src.core.state import AppState, get_state
from src.ingestion.registry import DatasetRegistry
from src.main import app

_STUBBED_CLASSIFICATIONS = {
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
            "description": "Order placement date",
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
            "description": "Customer segment",
            "aggregation": None,
        },
    ]
}


def _mock_llm_factory() -> Callable[[], LlmClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(_STUBBED_CLASSIFICATIONS),
                        }
                    }
                ]
            },
        )

    def factory() -> LlmClient:
        return LlmClient(
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://openrouter.test/api/v1",
                headers={"Authorization": "Bearer test"},
            )
        )

    return factory


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    """Yield a FastAPI TestClient with a fresh AppState + mocked LLM."""
    connection = create_connection()
    state = AppState(
        registry=DatasetRegistry(),
        connection=connection,
        data_directory=tmp_path,
        memory=MemoryStore(tmp_path / "agent_memory.db"),
        plans=PlanStore(tmp_path / "plan_audit.db"),
    )
    app.dependency_overrides[get_state] = lambda: state
    app.dependency_overrides[get_llm_client_factory] = _mock_llm_factory
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        connection.close()


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_full_pipeline_upload_then_query(api_client: TestClient) -> None:
    # 1. Upload the sample CSV.
    with (FIXTURES_DIR / "sample_sales.csv").open("rb") as fh:
        response = api_client.post(
            "/datasets/upload",
            files={"file": ("sample_sales.csv", fh, "text/csv")},
        )
    assert response.status_code == 200, response.text
    summary = response.json()
    dataset_id = summary["dataset_id"]
    assert summary["row_count"] == 10
    assert summary["status"] == "gold"

    # 2. List datasets — should include the new one.
    listing = api_client.get("/datasets").json()
    assert any(d["dataset_id"] == dataset_id for d in listing)

    # 3. Fetch the DCD as YAML.
    context_response = api_client.get(f"/datasets/{dataset_id}/context")
    assert context_response.status_code == 200
    assert "dataset:" in context_response.text
    assert "revenue" in context_response.text

    # 4. Schema summary.
    schema_response = api_client.get(f"/datasets/{dataset_id}/schema")
    assert schema_response.status_code == 200
    schema = schema_response.json()
    assert schema["row_count"] == 10
    assert any(c["name"] == "revenue" for c in schema["columns"])
    assert schema["verified_queries"]  # verified queries populated

    # 5. Run a SQL query via the tools endpoint — use a verified query.
    verified_sql = schema["verified_queries"][0]["sql"]
    sql_response = api_client.post(
        "/tools/sql",
        json={
            "dataset_id": dataset_id,
            "sql": verified_sql,
            "max_rows": 100,
        },
    )
    assert sql_response.status_code == 200, sql_response.text
    sql_result = sql_response.json()
    assert sql_result["columns"]
    assert sql_result["row_count"] >= 1
    assert not sql_result["truncated"]


def test_sql_endpoint_rejects_ddl(api_client: TestClient) -> None:
    # Upload first so a dataset exists.
    with (FIXTURES_DIR / "sample_sales.csv").open("rb") as fh:
        upload = api_client.post(
            "/datasets/upload",
            files={"file": ("sample_sales.csv", fh, "text/csv")},
        )
    dataset_id = upload.json()["dataset_id"]

    response = api_client.post(
        "/tools/sql",
        json={
            "dataset_id": dataset_id,
            "sql": "DROP TABLE raw_sales",
        },
    )
    assert response.status_code == 400


def test_sql_endpoint_unknown_dataset(api_client: TestClient) -> None:
    response = api_client.post(
        "/tools/sql",
        json={"dataset_id": "ds_doesnotexist", "sql": "SELECT 1"},
    )
    assert response.status_code == 404


def test_context_endpoint_unknown_dataset(api_client: TestClient) -> None:
    response = api_client.get("/datasets/ds_doesnotexist/context")
    assert response.status_code == 404


def test_delete_endpoint(api_client: TestClient) -> None:
    with (FIXTURES_DIR / "sample_sales.csv").open("rb") as fh:
        upload = api_client.post(
            "/datasets/upload",
            files={"file": ("sample_sales.csv", fh, "text/csv")},
        )
    dataset_id = upload.json()["dataset_id"]

    delete = api_client.delete(f"/datasets/{dataset_id}")
    assert delete.status_code == 200

    # After delete the dataset should no longer be listed.
    listing = api_client.get("/datasets").json()
    assert all(d["dataset_id"] != dataset_id for d in listing)
