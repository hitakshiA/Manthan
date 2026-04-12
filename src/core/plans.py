"""Plan mode / approval gate — the agent's structured plan primitive.

When the master agent is about to do something expensive or
consequential (run 20 SQL queries, materialize a large dataset, make
a claim grounded in a DCD interpretation), it **must** be able to
show its work *before* spending resources and let the user confirm
the interpretation is sound. This module backs that flow.

## The plan object

A plan is a structured snapshot of the agent's reasoning:

- ``user_question`` — exactly what the user asked (verbatim)
- ``interpretation`` — agent's plain-language restatement of what
  the user is really asking for
- ``citations`` — specific DCD columns / computed_metrics /
  agent_instructions the interpretation relies on. If the agent
  misread a column's role or aggregation, this is where it shows
- ``steps`` — the concrete tool calls the agent intends to run, in
  order, with parameters. Each step declares its tool, arguments,
  a one-line description, and optional ``depends_on`` edges
- ``expected_cost`` — a rough estimate (number of tool calls,
  number of LLM calls) so the user can see how much work they're
  approving
- ``risks`` — caveats the agent is aware of (e.g. "this query scans
  the whole Gold table, no index hint available")

## State machine

```
  draft
    └──submit──▶ pending
                  ├──approve──▶ approved
                  │              └──execute_start──▶ executing
                  │                                    ├──execute_done──▶ executed
                  │                                    └──execute_done(fail)─▶ failed
                  ├──reject──▶ rejected
                  └──amend──▶ amended ──submit──▶ pending
```

A plan is **draft** while the agent is building it (can still be
mutated). Once ``submit`` is called the plan is **pending** and the
agent blocks on ``wait_for_decision`` until the user approves,
rejects, or amends it. Rejection is terminal; amendment reopens the
plan for the agent to revise and resubmit. Approved plans stay in
``approved`` state until the agent calls ``execute_start`` (for
auditability) and transition to ``executed`` or ``failed`` when the
tool calls finish.

## Why Layer 1 hosts this rather than Layer 2

Because the approval flow is stateful and long-lived — a plan can
sit in ``pending`` for minutes while the user reads it. Layer 1's
HTTP API gives every Layer 2 consumer the same blocking wait
semantics for free (``POST /plans/{id}/wait``), and the SQLite audit
log gives us a persistent trail of what plans ran against which data
on behalf of which session.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

PlanStatus = Literal[
    "draft",
    "pending",
    "approved",
    "rejected",
    "amended",
    "executing",
    "executed",
    "failed",
]

_VALID_STATUSES: frozenset[str] = frozenset(
    {
        "draft",
        "pending",
        "approved",
        "rejected",
        "amended",
        "executing",
        "executed",
        "failed",
    }
)

_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS plan_audit (
    plan_id       TEXT NOT NULL,
    event         TEXT NOT NULL,
    status_before TEXT,
    status_after  TEXT,
    actor         TEXT,
    note          TEXT,
    recorded_at   TEXT NOT NULL,
    PRIMARY KEY (plan_id, recorded_at)
);

CREATE INDEX IF NOT EXISTS idx_plan_audit_plan ON plan_audit (plan_id);
"""


@dataclass
class PlanCitation:
    """A DCD reference backing the agent's interpretation."""

    kind: str  # column | metric | agent_instruction | verified_query | hierarchy
    identifier: str
    reason: str


@dataclass
class PlanStep:
    """One concrete tool call in the plan."""

    id: str
    tool: str
    description: str
    arguments: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    status: Literal["pending", "running", "succeeded", "failed", "skipped"] = "pending"
    result_summary: str | None = None


@dataclass
class Plan:
    """The full plan object — what the agent proposes and the user approves."""

    id: str
    session_id: str
    dataset_id: str | None
    user_question: str
    interpretation: str
    citations: list[PlanCitation]
    steps: list[PlanStep]
    expected_cost: dict[str, int]
    risks: list[str]
    status: PlanStatus = "draft"
    approval_feedback: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    _decision_event: threading.Event = field(default_factory=threading.Event)


class PlanStore:
    """Thread-safe plan registry with SQLite-backed audit log."""

    def __init__(self, audit_database_path: Path) -> None:
        self._plans: dict[str, Plan] = {}
        self._lock = threading.Lock()
        self._audit_path = audit_database_path
        audit_database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._audit_connect() as conn:
            conn.executescript(_AUDIT_SCHEMA)
            conn.execute("PRAGMA journal_mode = WAL")

    @contextmanager
    def _audit_connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            str(self._audit_path), isolation_level=None, timeout=10.0
        )
        try:
            yield conn
        finally:
            conn.close()

    def _record_audit(
        self,
        *,
        plan_id: str,
        event: str,
        status_before: str | None,
        status_after: str | None,
        actor: str | None = None,
        note: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._audit_connect() as conn:
            conn.execute(
                "INSERT INTO plan_audit "
                "(plan_id, event, status_before, status_after, "
                " actor, note, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (plan_id, event, status_before, status_after, actor, note, now),
            )

    def create_draft(
        self,
        *,
        session_id: str,
        dataset_id: str | None,
        user_question: str,
        interpretation: str,
        citations: list[PlanCitation],
        steps: list[PlanStep],
        expected_cost: dict[str, int] | None = None,
        risks: list[str] | None = None,
    ) -> Plan:
        plan = Plan(
            id=f"plan_{uuid4().hex[:12]}",
            session_id=session_id,
            dataset_id=dataset_id,
            user_question=user_question,
            interpretation=interpretation,
            citations=list(citations),
            steps=list(steps),
            expected_cost=dict(expected_cost or {}),
            risks=list(risks or []),
        )
        with self._lock:
            self._plans[plan.id] = plan
        self._record_audit(
            plan_id=plan.id,
            event="created",
            status_before=None,
            status_after="draft",
            actor="agent",
        )
        return plan

    def submit(self, plan_id: str) -> Plan:
        """Advance ``draft`` or ``amended`` → ``pending`` (awaiting approval)."""
        with self._lock:
            plan = self._require(plan_id)
            if plan.status not in ("draft", "amended"):
                raise ValueError(
                    f"Plan {plan_id!r} is {plan.status!r}; "
                    "can only submit from draft/amended"
                )
            before = plan.status
            plan.status = "pending"
            plan.updated_at = datetime.now(UTC)
            plan._decision_event.clear()
        self._record_audit(
            plan_id=plan_id,
            event="submit",
            status_before=before,
            status_after="pending",
            actor="agent",
        )
        return plan

    def approve(self, plan_id: str, *, actor: str | None = None) -> Plan:
        return self._decide(
            plan_id,
            new_status="approved",
            event="approve",
            actor=actor,
            feedback=None,
        )

    def reject(
        self, plan_id: str, *, feedback: str | None = None, actor: str | None = None
    ) -> Plan:
        return self._decide(
            plan_id,
            new_status="rejected",
            event="reject",
            actor=actor,
            feedback=feedback,
        )

    def amend(
        self,
        plan_id: str,
        *,
        interpretation: str | None = None,
        citations: list[PlanCitation] | None = None,
        steps: list[PlanStep] | None = None,
        risks: list[str] | None = None,
        feedback: str | None = None,
        actor: str | None = None,
    ) -> Plan:
        with self._lock:
            plan = self._require(plan_id)
            if plan.status != "pending":
                raise ValueError(
                    f"Plan {plan_id!r} is {plan.status!r}; "
                    "can only amend a pending plan"
                )
            before = plan.status
            if interpretation is not None:
                plan.interpretation = interpretation
            if citations is not None:
                plan.citations = list(citations)
            if steps is not None:
                plan.steps = list(steps)
            if risks is not None:
                plan.risks = list(risks)
            if feedback is not None:
                plan.approval_feedback = feedback
            plan.status = "amended"
            plan.updated_at = datetime.now(UTC)
            plan._decision_event.set()
        self._record_audit(
            plan_id=plan_id,
            event="amend",
            status_before=before,
            status_after="amended",
            actor=actor,
            note=feedback,
        )
        return plan

    def start_execution(self, plan_id: str) -> Plan:
        with self._lock:
            plan = self._require(plan_id)
            if plan.status != "approved":
                raise ValueError(
                    f"Plan {plan_id!r} is {plan.status!r}; "
                    "can only execute an approved plan"
                )
            before = plan.status
            plan.status = "executing"
            plan.updated_at = datetime.now(UTC)
        self._record_audit(
            plan_id=plan_id,
            event="execute_start",
            status_before=before,
            status_after="executing",
            actor="agent",
        )
        return plan

    def finish_execution(
        self,
        plan_id: str,
        *,
        success: bool,
        note: str | None = None,
    ) -> Plan:
        with self._lock:
            plan = self._require(plan_id)
            if plan.status != "executing":
                raise ValueError(
                    f"Plan {plan_id!r} is {plan.status!r}; "
                    "finish_execution requires executing state"
                )
            before = plan.status
            plan.status = "executed" if success else "failed"
            plan.updated_at = datetime.now(UTC)
        self._record_audit(
            plan_id=plan_id,
            event="execute_done",
            status_before=before,
            status_after=plan.status,
            actor="agent",
            note=note,
        )
        return plan

    def wait_for_decision(self, plan_id: str, timeout_seconds: float) -> Plan:
        """Block on the agent side until the user approves/rejects/amends."""
        with self._lock:
            plan = self._require(plan_id)
            event = plan._decision_event

        event.wait(timeout=timeout_seconds)

        with self._lock:
            return self._plans[plan_id]

    def get(self, plan_id: str) -> Plan | None:
        with self._lock:
            return self._plans.get(plan_id)

    def list_session(self, session_id: str) -> list[Plan]:
        with self._lock:
            plans = [p for p in self._plans.values() if p.session_id == session_id]
        return sorted(plans, key=lambda p: p.created_at, reverse=True)

    def audit_trail(self, plan_id: str) -> list[dict[str, Any]]:
        with self._audit_connect() as conn:
            cursor = conn.execute(
                "SELECT event, status_before, status_after, actor, note, recorded_at "
                "FROM plan_audit WHERE plan_id = ? ORDER BY recorded_at",
                (plan_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "event": row[0],
                "status_before": row[1],
                "status_after": row[2],
                "actor": row[3],
                "note": row[4],
                "recorded_at": row[5],
            }
            for row in rows
        ]

    def _require(self, plan_id: str) -> Plan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise KeyError(f"Unknown plan_id: {plan_id}")
        return plan

    def _decide(
        self,
        plan_id: str,
        *,
        new_status: str,
        event: str,
        actor: str | None,
        feedback: str | None,
    ) -> Plan:
        with self._lock:
            plan = self._require(plan_id)
            if plan.status != "pending":
                raise ValueError(
                    f"Plan {plan_id!r} is {plan.status!r}; "
                    "can only decide on a pending plan"
                )
            if new_status not in _VALID_STATUSES:
                raise ValueError(f"Invalid new_status: {new_status}")
            before = plan.status
            plan.status = new_status  # type: ignore[assignment]
            plan.approval_feedback = feedback
            plan.updated_at = datetime.now(UTC)
            plan._decision_event.set()
        self._record_audit(
            plan_id=plan_id,
            event=event,
            status_before=before,
            status_after=new_status,
            actor=actor,
            note=feedback,
        )
        return plan


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    """Serializable dict representation (no event, no internal fields)."""
    return {
        "id": plan.id,
        "session_id": plan.session_id,
        "dataset_id": plan.dataset_id,
        "user_question": plan.user_question,
        "interpretation": plan.interpretation,
        "citations": [
            {
                "kind": c.kind,
                "identifier": c.identifier,
                "reason": c.reason,
            }
            for c in plan.citations
        ],
        "steps": [
            {
                "id": s.id,
                "tool": s.tool,
                "description": s.description,
                "arguments": s.arguments,
                "depends_on": list(s.depends_on),
                "status": s.status,
                "result_summary": s.result_summary,
            }
            for s in plan.steps
        ],
        "expected_cost": dict(plan.expected_cost),
        "risks": list(plan.risks),
        "status": plan.status,
        "approval_feedback": plan.approval_feedback,
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
    }


def plan_from_json(data: str) -> dict[str, Any]:
    """Parse a stored plan JSON string back into a dict."""
    return json.loads(data)
