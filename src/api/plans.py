"""Plan mode / approval gate HTTP router."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.plans import Plan, PlanCitation, PlanStep, plan_to_dict
from src.core.state import AppState, get_state

router = APIRouter(prefix="/plans", tags=["plans"])

StateDep = Annotated[AppState, Depends(get_state)]

_DEFAULT_WAIT_SECONDS = 600.0
_MAX_WAIT_SECONDS = 1800.0


class CitationBody(BaseModel):
    kind: str = Field(
        ...,
        description="column | metric | agent_instruction | verified_query | hierarchy",
    )
    identifier: str
    reason: str


class StepBody(BaseModel):
    id: str | None = None
    tool: str
    description: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class PlanCreateRequest(BaseModel):
    session_id: str
    dataset_id: str | None = None
    user_question: str
    interpretation: str
    citations: list[CitationBody] = Field(default_factory=list)
    steps: list[StepBody] = Field(default_factory=list)
    expected_cost: dict[str, int] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)


class PlanApprovalRequest(BaseModel):
    actor: str | None = None
    feedback: str | None = None


class PlanAmendRequest(BaseModel):
    interpretation: str | None = None
    citations: list[CitationBody] | None = None
    steps: list[StepBody] | None = None
    risks: list[str] | None = None
    feedback: str | None = None
    actor: str | None = None


class PlanExecutionResult(BaseModel):
    success: bool
    note: str | None = None


def _to_citations(bodies: list[CitationBody] | None) -> list[PlanCitation]:
    if bodies is None:
        return []
    return [
        PlanCitation(kind=b.kind, identifier=b.identifier, reason=b.reason)
        for b in bodies
    ]


def _to_steps(bodies: list[StepBody] | None) -> list[PlanStep]:
    if bodies is None:
        return []
    steps: list[PlanStep] = []
    for i, body in enumerate(bodies):
        steps.append(
            PlanStep(
                id=body.id or f"step_{i + 1}",
                tool=body.tool,
                description=body.description,
                arguments=body.arguments,
                depends_on=list(body.depends_on),
            )
        )
    return steps


def _plan_response(plan: Plan) -> dict[str, Any]:
    return plan_to_dict(plan)


@router.post("")
def create_plan(request: PlanCreateRequest, state: StateDep) -> dict[str, Any]:
    plan = state.plans.create_draft(
        session_id=request.session_id,
        dataset_id=request.dataset_id,
        user_question=request.user_question,
        interpretation=request.interpretation,
        citations=_to_citations(request.citations),
        steps=_to_steps(request.steps),
        expected_cost=request.expected_cost,
        risks=request.risks,
    )
    return _plan_response(plan)


@router.post("/{plan_id}/submit")
def submit_plan(plan_id: str, state: StateDep) -> dict[str, Any]:
    try:
        plan = state.plans.submit(plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _plan_response(plan)


@router.post("/{plan_id}/wait")
def wait_for_decision(
    plan_id: str,
    state: StateDep,
    timeout_seconds: float = _DEFAULT_WAIT_SECONDS,
) -> dict[str, Any]:
    timeout = min(max(1.0, timeout_seconds), _MAX_WAIT_SECONDS)
    try:
        plan = state.plans.wait_for_decision(plan_id, timeout_seconds=timeout)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = _plan_response(plan)
    payload["timed_out"] = plan.status == "pending"
    return payload


@router.post("/{plan_id}/approve")
def approve(
    plan_id: str, request: PlanApprovalRequest, state: StateDep
) -> dict[str, Any]:
    try:
        plan = state.plans.approve(plan_id, actor=request.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _plan_response(plan)


@router.post("/{plan_id}/reject")
def reject(
    plan_id: str, request: PlanApprovalRequest, state: StateDep
) -> dict[str, Any]:
    try:
        plan = state.plans.reject(
            plan_id, feedback=request.feedback, actor=request.actor
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _plan_response(plan)


@router.post("/{plan_id}/amend")
def amend(plan_id: str, request: PlanAmendRequest, state: StateDep) -> dict[str, Any]:
    try:
        plan = state.plans.amend(
            plan_id,
            interpretation=request.interpretation,
            citations=_to_citations(request.citations),
            steps=_to_steps(request.steps),
            risks=request.risks,
            feedback=request.feedback,
            actor=request.actor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _plan_response(plan)


@router.post("/{plan_id}/execute_start")
def execute_start(plan_id: str, state: StateDep) -> dict[str, Any]:
    try:
        plan = state.plans.start_execution(plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _plan_response(plan)


@router.post("/{plan_id}/execute_done")
def execute_done(
    plan_id: str, request: PlanExecutionResult, state: StateDep
) -> dict[str, Any]:
    try:
        plan = state.plans.finish_execution(
            plan_id, success=request.success, note=request.note
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _plan_response(plan)


@router.get("/{plan_id}")
def get_plan(plan_id: str, state: StateDep) -> dict[str, Any]:
    plan = state.plans.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Unknown plan_id: {plan_id}")
    return _plan_response(plan)


@router.get("")
def list_plans(session_id: str, state: StateDep) -> list[dict[str, Any]]:
    return [_plan_response(p) for p in state.plans.list_session(session_id)]


@router.get("/{plan_id}/audit")
def audit_trail(plan_id: str, state: StateDep) -> dict[str, Any]:
    """Return the audit trail for a plan.

    The Plan object itself lives in process memory and is lost across
    restarts, but the audit trail is SQLite-backed (see
    :class:`src.core.plans.PlanStore._audit_path`) and survives. We
    serve whatever audit rows exist for ``plan_id`` without gating on
    the in-memory Plan object — an agent that ran a plan yesterday and
    comes back today after a restart can still ask "what did I do?".
    If no audit rows exist for this plan_id, return 404.
    """
    events = state.plans.audit_trail(plan_id)
    if not events:
        raise HTTPException(
            status_code=404, detail=f"No audit trail for plan_id: {plan_id}"
        )
    return {"plan_id": plan_id, "events": events}
