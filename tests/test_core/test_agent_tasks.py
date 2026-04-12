"""Unit tests for :mod:`src.core.agent_tasks`."""

from __future__ import annotations

import pytest
from src.core.agent_tasks import AgentTaskStore


def test_create_and_list_scoped_by_session() -> None:
    store = AgentTaskStore()
    t1 = store.create(session_id="s1", title="A", description="do a")
    store.create(session_id="s2", title="B", description="do b")
    store.create(session_id="s1", title="C", description="do c")

    tasks = store.list_session("s1")
    assert [t.title for t in tasks] == ["A", "C"]
    assert t1.status == "pending"


def test_update_status_transitions() -> None:
    store = AgentTaskStore()
    task = store.create(session_id="s", title="t", description="d")
    store.update(task.id, status="in_progress")
    store.update(task.id, status="completed", result="ok")

    refreshed = store.get(task.id)
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.result == "ok"


def test_invalid_status_raises() -> None:
    store = AgentTaskStore()
    task = store.create(session_id="s", title="t", description="d")
    with pytest.raises(ValueError, match="Invalid status"):
        store.update(task.id, status="nonsense")


def test_unknown_task_raises_keyerror() -> None:
    store = AgentTaskStore()
    with pytest.raises(KeyError):
        store.update("task_missing", status="completed")


def test_depends_on_preserved() -> None:
    store = AgentTaskStore()
    t1 = store.create(session_id="s", title="first", description="")
    t2 = store.create(
        session_id="s", title="second", description="", depends_on=[t1.id]
    )
    assert t2.depends_on == [t1.id]


def test_drop_session() -> None:
    store = AgentTaskStore()
    store.create(session_id="s1", title="a", description="")
    store.create(session_id="s1", title="b", description="")
    store.create(session_id="s2", title="c", description="")

    removed = store.drop_session("s1")
    assert removed == 2
    assert store.list_session("s1") == []
    assert len(store.list_session("s2")) == 1
