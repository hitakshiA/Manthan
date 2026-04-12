"""Agent task-store HTTP router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.agent_tasks import AgentTask
from src.core.state import AppState, get_state

router = APIRouter(prefix="/tasks", tags=["tasks"])

StateDep = Annotated[AppState, Depends(get_state)]


class TaskCreateRequest(BaseModel):
    session_id: str
    title: str
    description: str
    depends_on: list[str] = Field(default_factory=list)


class TaskUpdateRequest(BaseModel):
    status: str | None = None
    title: str | None = None
    description: str | None = None
    result: str | None = None


class TaskResponse(BaseModel):
    id: str
    session_id: str
    title: str
    description: str
    status: str
    depends_on: list[str]
    result: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_task(cls, task: AgentTask) -> TaskResponse:
        return cls(
            id=task.id,
            session_id=task.session_id,
            title=task.title,
            description=task.description,
            status=task.status,
            depends_on=list(task.depends_on),
            result=task.result,
            created_at=task.created_at.isoformat(),
            updated_at=task.updated_at.isoformat(),
        )


@router.post("", response_model=TaskResponse)
def create_task(request: TaskCreateRequest, state: StateDep) -> TaskResponse:
    task = state.agent_tasks.create(
        session_id=request.session_id,
        title=request.title,
        description=request.description,
        depends_on=request.depends_on,
    )
    return TaskResponse.from_task(task)


@router.get("", response_model=list[TaskResponse])
def list_tasks(session_id: str, state: StateDep) -> list[TaskResponse]:
    return [
        TaskResponse.from_task(t) for t in state.agent_tasks.list_session(session_id)
    ]


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, state: StateDep) -> TaskResponse:
    task = state.agent_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Unknown task_id: {task_id}")
    return TaskResponse.from_task(task)


@router.post("/{task_id}/update", response_model=TaskResponse)
def update_task(
    task_id: str, request: TaskUpdateRequest, state: StateDep
) -> TaskResponse:
    try:
        task = state.agent_tasks.update(
            task_id,
            status=request.status,
            title=request.title,
            description=request.description,
            result=request.result,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TaskResponse.from_task(task)


@router.delete("/{task_id}")
def delete_task(task_id: str, state: StateDep) -> dict[str, bool]:
    return {"removed": state.agent_tasks.delete(task_id)}
