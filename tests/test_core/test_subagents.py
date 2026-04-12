"""Unit tests for :mod:`src.core.subagents`."""

from __future__ import annotations

import pytest
from src.core.subagents import SubagentStore


def test_spawn_allocates_fresh_session_id() -> None:
    store = SubagentStore()
    sub1 = store.spawn(
        parent_session_id="master_1", dataset_id="ds_x", task="Investigate churn"
    )
    sub2 = store.spawn(
        parent_session_id="master_1", dataset_id="ds_x", task="Explore cohorts"
    )
    assert sub1.session_id != sub2.session_id
    assert sub1.parent_session_id == "master_1"
    assert sub1.status == "spawned"


def test_lifecycle_spawned_running_completed() -> None:
    store = SubagentStore()
    sub = store.spawn(parent_session_id=None, dataset_id=None, task="t")
    store.mark_running(sub.id)
    completed = store.complete(sub.id, result="done")
    assert completed.status == "completed"
    assert completed.result == "done"


def test_fail_sets_error() -> None:
    store = SubagentStore()
    sub = store.spawn(parent_session_id=None, dataset_id=None, task="t")
    failed = store.fail(sub.id, error="tool timeout")
    assert failed.status == "failed"
    assert failed.error == "tool timeout"


def test_list_parent_scopes_correctly() -> None:
    store = SubagentStore()
    store.spawn(parent_session_id="A", dataset_id=None, task="1")
    store.spawn(parent_session_id="A", dataset_id=None, task="2")
    store.spawn(parent_session_id="B", dataset_id=None, task="3")
    assert len(store.list_parent("A")) == 2
    assert len(store.list_parent("B")) == 1


def test_unknown_subagent_raises() -> None:
    store = SubagentStore()
    with pytest.raises(KeyError):
        store.mark_running("sub_nope")
