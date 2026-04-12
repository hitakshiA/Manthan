"""HTTP-level smoke tests for the agent primitive routers."""

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


def test_memory_crud(client: TestClient) -> None:
    body = {
        "scope_type": "dataset",
        "scope_id": "ds_1",
        "key": "active_user_def",
        "value": {"window_days": 30},
        "category": "definition",
        "description": "Business definition",
    }
    created = client.post("/memory", json=body).json()
    assert created["value"] == {"window_days": 30}

    fetched = client.get("/memory/dataset/ds_1/active_user_def").json()
    assert fetched["category"] == "definition"

    listed = client.get("/memory/dataset/ds_1").json()
    assert len(listed) == 1

    search = client.get("/memory/search/", params={"query": "active"}).json()
    assert len(search) == 1

    deleted = client.delete("/memory/dataset/ds_1/active_user_def").json()
    assert deleted["removed"] is True


def test_memory_rejects_invalid_scope(client: TestClient) -> None:
    body = {"scope_type": "bogus", "scope_id": "x", "key": "k", "value": 1}
    response = client.post("/memory", json=body)
    assert response.status_code == 400


def test_agent_tasks_flow(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "session_id": "s1",
            "title": "Inspect schema",
            "description": "Run get_schema",
        },
    ).json()
    task_id = created["id"]
    assert created["status"] == "pending"

    updated = client.post(
        f"/tasks/{task_id}/update",
        json={"status": "in_progress"},
    ).json()
    assert updated["status"] == "in_progress"

    listed = client.get("/tasks", params={"session_id": "s1"}).json()
    assert len(listed) == 1


def test_ask_user_long_poll(client: TestClient) -> None:
    body = {
        "session_id": "s1",
        "prompt": "Calendar month or trailing 30?",
        "options": ["calendar", "trailing_30"],
    }
    question = client.post("/ask_user", json=body).json()
    qid = question["id"]

    def _answer_soon() -> None:
        time.sleep(0.1)
        client.post(f"/ask_user/{qid}/answer", json={"answer": "trailing_30"})

    thread = threading.Thread(target=_answer_soon)
    thread.start()
    response = client.post(
        f"/ask_user/{qid}/wait", params={"timeout_seconds": 3.0}
    ).json()
    thread.join()

    assert response["status"] == "answered"
    assert response["answer"] == "trailing_30"
    assert response["timed_out"] is False


def test_ask_user_timeout(client: TestClient) -> None:
    body = {"session_id": "s1", "prompt": "?"}
    qid = client.post("/ask_user", json=body).json()["id"]
    response = client.post(
        f"/ask_user/{qid}/wait", params={"timeout_seconds": 1.0}
    ).json()
    assert response["status"] == "pending"
    assert response["timed_out"] is True


def test_subagent_spawn_complete_writes_memory(client: TestClient) -> None:
    spawned = client.post(
        "/subagents/spawn",
        json={
            "parent_session_id": "master_1",
            "dataset_id": "ds_x",
            "task": "Investigate churn drivers",
        },
    ).json()
    sub_id = spawned["id"]
    assert spawned["status"] == "spawned"

    client.post(f"/subagents/{sub_id}/running")
    completed = client.post(
        f"/subagents/{sub_id}/complete",
        json={
            "result": "Found 3 drivers",
            "write_to_parent_memory": True,
            "memory_key": "churn_drivers_summary",
        },
    ).json()
    assert completed["status"] == "completed"

    # Result should now be in the parent session's memory scope
    memory_response = client.get(
        "/memory/session/master_1/churn_drivers_summary"
    ).json()
    assert memory_response["value"] == "Found 3 drivers"
    assert memory_response["category"] == "note"
