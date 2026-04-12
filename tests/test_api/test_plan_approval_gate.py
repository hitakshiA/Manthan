"""End-to-end test for the plan approval gate HTTP flow.

Simulates the agent submitting a plan, the user long-polling and
approving it, and the agent unblocking to execute.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from src.core.database import create_connection
from src.core.memory import MemoryStore
from src.core.plans import PlanStore
from src.core.state import AppState, get_state
from src.ingestion.registry import DatasetRegistry
from src.main import app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    connection = create_connection()
    state = AppState(
        registry=DatasetRegistry(),
        connection=connection,
        data_directory=tmp_path,
        memory=MemoryStore(tmp_path / "agent_memory.db"),
        plans=PlanStore(tmp_path / "plan_audit.db"),
    )
    app.dependency_overrides[get_state] = lambda: state
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        connection.close()


def _create_body() -> dict[str, object]:
    return {
        "session_id": "sess_1",
        "dataset_id": "ds_demo",
        "user_question": "What drove the drop in revenue last week?",
        "interpretation": (
            "Compare daily revenue for the past 7 days to the 7 days "
            "before, grouped by product category."
        ),
        "citations": [
            {
                "kind": "column",
                "identifier": "amount",
                "reason": "revenue measure",
            },
            {
                "kind": "column",
                "identifier": "product_category",
                "reason": "dimension to slice by",
            },
        ],
        "steps": [
            {
                "tool": "run_sql",
                "description": "Daily revenue by category",
                "arguments": {"sql": "SELECT ..."},
            },
            {
                "tool": "run_python",
                "description": "Compute week-over-week deltas",
                "arguments": {"code": "df.diff()"},
                "depends_on": ["step_1"],
            },
        ],
        "expected_cost": {"tool_calls": 2, "llm_calls": 1},
        "risks": ["Week boundary handling"],
    }


def test_draft_to_approved_flow(client: TestClient) -> None:
    response = client.post("/plans", json=_create_body())
    assert response.status_code == 200
    plan = response.json()
    plan_id = plan["id"]
    assert plan["status"] == "draft"
    assert len(plan["citations"]) == 2
    assert plan["steps"][0]["id"] == "step_1"

    # Submit
    submitted = client.post(f"/plans/{plan_id}/submit").json()
    assert submitted["status"] == "pending"

    # Approve
    approved = client.post(
        f"/plans/{plan_id}/approve", json={"actor": "hitakshi"}
    ).json()
    assert approved["status"] == "approved"

    # Execute
    client.post(f"/plans/{plan_id}/execute_start")
    executed = client.post(
        f"/plans/{plan_id}/execute_done",
        json={"success": True, "note": "ok"},
    ).json()
    assert executed["status"] == "executed"

    # Audit trail
    audit = client.get(f"/plans/{plan_id}/audit").json()
    event_names = [e["event"] for e in audit["events"]]
    assert event_names == [
        "created",
        "submit",
        "approve",
        "execute_start",
        "execute_done",
    ]


def test_long_poll_unblocks_on_approval(client: TestClient) -> None:
    plan_id = client.post("/plans", json=_create_body()).json()["id"]
    client.post(f"/plans/{plan_id}/submit")

    def _approve_soon() -> None:
        time.sleep(0.1)
        client.post(f"/plans/{plan_id}/approve", json={"actor": "u"})

    thread = threading.Thread(target=_approve_soon)
    thread.start()

    response = client.post(f"/plans/{plan_id}/wait", params={"timeout_seconds": 3.0})
    thread.join()

    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["timed_out"] is False


def test_long_poll_times_out_when_no_decision(client: TestClient) -> None:
    plan_id = client.post("/plans", json=_create_body()).json()["id"]
    client.post(f"/plans/{plan_id}/submit")

    response = client.post(f"/plans/{plan_id}/wait", params={"timeout_seconds": 1.0})
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["timed_out"] is True


def test_reject_flow(client: TestClient) -> None:
    plan_id = client.post("/plans", json=_create_body()).json()["id"]
    client.post(f"/plans/{plan_id}/submit")

    rejected = client.post(
        f"/plans/{plan_id}/reject",
        json={"feedback": "Wrong window", "actor": "user"},
    ).json()
    assert rejected["status"] == "rejected"
    assert rejected["approval_feedback"] == "Wrong window"


def test_amend_then_resubmit(client: TestClient) -> None:
    plan_id = client.post("/plans", json=_create_body()).json()["id"]
    client.post(f"/plans/{plan_id}/submit")

    amended = client.post(
        f"/plans/{plan_id}/amend",
        json={
            "interpretation": "Use trailing 7 days instead",
            "feedback": "rolling, not calendar",
        },
    ).json()
    assert amended["status"] == "amended"
    assert amended["interpretation"] == "Use trailing 7 days instead"

    resubmitted = client.post(f"/plans/{plan_id}/submit").json()
    assert resubmitted["status"] == "pending"


def test_tool_discovery_returns_manifest(client: TestClient) -> None:
    response = client.get("/tools/list")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "1.0"
    assert payload["tool_count"] >= 13
    tool_names = {t["name"] for t in payload["tools"]}
    assert {"run_sql", "run_python", "plan", "ask_user", "memory"} <= tool_names
