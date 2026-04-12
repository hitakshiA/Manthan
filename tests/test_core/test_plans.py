"""Unit tests for :mod:`src.core.plans` — the plan approval gate."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from src.core.plans import PlanCitation, PlanStep, PlanStore


@pytest.fixture
def store(tmp_path: Path) -> PlanStore:
    return PlanStore(tmp_path / "plan_audit.db")


def _make_plan(store: PlanStore, session_id: str = "sess_1") -> str:
    plan = store.create_draft(
        session_id=session_id,
        dataset_id="ds_abc",
        user_question="How did revenue change last month?",
        interpretation=(
            "Compute sum(amount) grouped by month for the two most recent "
            "calendar months and return the percent change."
        ),
        citations=[
            PlanCitation(
                kind="column",
                identifier="amount",
                reason="primary measure for revenue",
            ),
            PlanCitation(
                kind="column",
                identifier="order_date",
                reason="temporal axis for month bucketing",
            ),
        ],
        steps=[
            PlanStep(
                id="step_1",
                tool="run_sql",
                description="Aggregate revenue by month",
                arguments={"sql": "SELECT ..."},
            ),
            PlanStep(
                id="step_2",
                tool="run_python",
                description="Compute percent change",
                arguments={"code": "df.pct_change()"},
                depends_on=["step_1"],
            ),
        ],
        expected_cost={"tool_calls": 2, "llm_calls": 1},
        risks=["Full table scan on gold table"],
    )
    return plan.id


def test_draft_creation_status(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    plan = store.get(plan_id)
    assert plan is not None
    assert plan.status == "draft"
    assert len(plan.citations) == 2
    assert len(plan.steps) == 2


def test_submit_advances_to_pending(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    plan = store.submit(plan_id)
    assert plan.status == "pending"


def test_cannot_submit_non_draft(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    with pytest.raises(ValueError, match="can only submit from draft/amended"):
        store.submit(plan_id)


def test_approve_flow(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    approved = store.approve(plan_id, actor="hitakshi")
    assert approved.status == "approved"


def test_reject_records_feedback(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    rejected = store.reject(plan_id, feedback="Wrong interpretation of 'last month'")
    assert rejected.status == "rejected"
    assert rejected.approval_feedback == "Wrong interpretation of 'last month'"


def test_amend_reopens_for_revision(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    amended = store.amend(
        plan_id,
        interpretation="Use trailing 30 days instead of calendar month",
        feedback="Calendar month is wrong in this context",
    )
    assert amended.status == "amended"
    assert amended.interpretation.startswith("Use trailing 30 days")
    # Can resubmit after amendment
    resubmitted = store.submit(plan_id)
    assert resubmitted.status == "pending"


def test_cannot_approve_draft(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    with pytest.raises(ValueError, match="can only decide on a pending plan"):
        store.approve(plan_id)


def test_execution_lifecycle(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    store.approve(plan_id)
    store.start_execution(plan_id)
    executed = store.finish_execution(plan_id, success=True, note="2 rows returned")
    assert executed.status == "executed"


def test_execution_failure_transitions_to_failed(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    store.approve(plan_id)
    store.start_execution(plan_id)
    failed = store.finish_execution(plan_id, success=False, note="SQL timeout")
    assert failed.status == "failed"


def test_cannot_execute_unapproved(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    with pytest.raises(ValueError, match="can only execute an approved plan"):
        store.start_execution(plan_id)


def test_wait_for_decision_unblocks_on_approve(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)

    def _approve_soon() -> None:
        time.sleep(0.05)
        store.approve(plan_id, actor="user")

    thread = threading.Thread(target=_approve_soon)
    thread.start()

    plan = store.wait_for_decision(plan_id, timeout_seconds=2.0)
    thread.join()

    assert plan.status == "approved"


def test_wait_for_decision_times_out_while_pending(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    start = time.monotonic()
    plan = store.wait_for_decision(plan_id, timeout_seconds=0.1)
    elapsed = time.monotonic() - start
    assert plan.status == "pending"
    assert elapsed >= 0.1


def test_audit_trail_records_state_transitions(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    store.approve(plan_id, actor="hitakshi")

    events = store.audit_trail(plan_id)
    event_names = [e["event"] for e in events]
    assert event_names == ["created", "submit", "approve"]

    approve_event = events[-1]
    assert approve_event["status_before"] == "pending"
    assert approve_event["status_after"] == "approved"
    assert approve_event["actor"] == "hitakshi"


def test_audit_trail_captures_rejection_note(store: PlanStore) -> None:
    plan_id = _make_plan(store)
    store.submit(plan_id)
    store.reject(plan_id, feedback="not what i meant", actor="user")

    events = store.audit_trail(plan_id)
    reject = events[-1]
    assert reject["event"] == "reject"
    assert reject["note"] == "not what i meant"


def test_audit_log_persists_across_store_instances(tmp_path: Path) -> None:
    path = tmp_path / "plan_audit.db"
    store1 = PlanStore(path)
    plan_id = _make_plan(store1)
    store1.submit(plan_id)
    store1.approve(plan_id)

    store2 = PlanStore(path)
    events = store2.audit_trail(plan_id)
    assert len(events) == 3
    assert [e["event"] for e in events] == ["created", "submit", "approve"]


def test_list_session_filters(store: PlanStore) -> None:
    p1 = _make_plan(store, session_id="a")
    p2 = _make_plan(store, session_id="b")
    _make_plan(store, session_id="a")

    a_plans = store.list_session("a")
    b_plans = store.list_session("b")
    assert len(a_plans) == 2
    assert len(b_plans) == 1
    assert b_plans[0].id == p2
    assert any(p.id == p1 for p in a_plans)
