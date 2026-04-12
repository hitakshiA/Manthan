"""Subagent scope HTTP router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.core.state import AppState, get_state
from src.core.subagents import Subagent

router = APIRouter(prefix="/subagents", tags=["subagents"])

StateDep = Annotated[AppState, Depends(get_state)]


class SpawnRequest(BaseModel):
    parent_session_id: str | None = None
    dataset_id: str | None = None
    task: str
    context_hint: str | None = None


class CompleteRequest(BaseModel):
    result: str | None = None
    write_to_parent_memory: bool = False
    memory_key: str | None = None


class FailRequest(BaseModel):
    error: str


class SubagentResponse(BaseModel):
    id: str
    session_id: str
    parent_session_id: str | None
    dataset_id: str | None
    task: str
    context_hint: str | None
    status: str
    result: str | None
    error: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_subagent(cls, sub: Subagent) -> SubagentResponse:
        return cls(
            id=sub.id,
            session_id=sub.session_id,
            parent_session_id=sub.parent_session_id,
            dataset_id=sub.dataset_id,
            task=sub.task,
            context_hint=sub.context_hint,
            status=sub.status,
            result=sub.result,
            error=sub.error,
            created_at=sub.created_at.isoformat(),
            updated_at=sub.updated_at.isoformat(),
        )


@router.post("/spawn", response_model=SubagentResponse)
def spawn(request: SpawnRequest, state: StateDep) -> SubagentResponse:
    sub = state.subagents.spawn(
        parent_session_id=request.parent_session_id,
        dataset_id=request.dataset_id,
        task=request.task,
        context_hint=request.context_hint,
    )
    return SubagentResponse.from_subagent(sub)


@router.post("/{subagent_id}/running", response_model=SubagentResponse)
def mark_running(subagent_id: str, state: StateDep) -> SubagentResponse:
    try:
        sub = state.subagents.mark_running(subagent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SubagentResponse.from_subagent(sub)


@router.post("/{subagent_id}/complete", response_model=SubagentResponse)
def complete(
    subagent_id: str, request: CompleteRequest, state: StateDep
) -> SubagentResponse:
    try:
        sub = state.subagents.complete(subagent_id, result=request.result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if (
        request.write_to_parent_memory
        and sub.parent_session_id
        and request.result is not None
    ):
        key = request.memory_key or f"subagent_{sub.id}_result"
        state.memory.put(
            scope_type="session",
            scope_id=sub.parent_session_id,
            key=key,
            value=request.result,
            category="note",
            description=f"Result from subagent {sub.id} task: {sub.task[:80]}",
        )

    return SubagentResponse.from_subagent(sub)


@router.post("/{subagent_id}/fail", response_model=SubagentResponse)
def fail(subagent_id: str, request: FailRequest, state: StateDep) -> SubagentResponse:
    try:
        sub = state.subagents.fail(subagent_id, error=request.error)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SubagentResponse.from_subagent(sub)


@router.get("/{subagent_id}", response_model=SubagentResponse)
def get_subagent(subagent_id: str, state: StateDep) -> SubagentResponse:
    sub = state.subagents.get(subagent_id)
    if sub is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown subagent_id: {subagent_id}"
        )
    return SubagentResponse.from_subagent(sub)


@router.get("", response_model=list[SubagentResponse])
def list_subagents(
    state: StateDep, parent_session_id: str | None = None
) -> list[SubagentResponse]:
    subs = (
        state.subagents.list_parent(parent_session_id)
        if parent_session_id
        else state.subagents.list_all()
    )
    return [SubagentResponse.from_subagent(s) for s in subs]
