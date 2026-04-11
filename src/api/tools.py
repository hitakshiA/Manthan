"""Agent tool API endpoints.

Thin HTTP shells around ``src.tools.sql_tool``, ``context_tool``,
``schema_tool``, and the stateful ``python_session`` runtime.

The Python endpoint is session-aware: pass ``session_id`` to chain
variables across calls, omit it to start a fresh session and receive
the generated id in the response.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.exceptions import SandboxError, SqlValidationError, ToolError
from src.core.state import AppState, get_state
from src.tools.context_tool import get_context
from src.tools.schema_tool import SchemaSummary, get_schema
from src.tools.sql_tool import SqlResult, run_sql

router = APIRouter(prefix="/tools", tags=["tools"])

StateDep = Annotated[AppState, Depends(get_state)]


class SqlRequest(BaseModel):
    """Body of ``POST /tools/sql``."""

    dataset_id: str
    sql: str
    max_rows: int = Field(default=1000, ge=1, le=100_000)


@router.post("/sql", response_model=SqlResult)
def execute_sql(request: SqlRequest, state: StateDep) -> SqlResult:
    if request.dataset_id not in state.dcds:
        raise HTTPException(
            status_code=404, detail=f"Unknown dataset: {request.dataset_id}"
        )
    try:
        return run_sql(state.connection, request.sql, max_rows=request.max_rows)
    except SqlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/context/{dataset_id}")
def context(
    dataset_id: str,
    state: StateDep,
    query: str | None = None,
) -> dict[str, str]:
    dcd = state.dcds.get(dataset_id)
    if dcd is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    return {"dataset_id": dataset_id, "yaml": get_context(dcd, query=query)}


@router.get("/schema/{dataset_id}", response_model=SchemaSummary)
def schema(dataset_id: str, state: StateDep) -> SchemaSummary:
    dcd = state.dcds.get(dataset_id)
    if dcd is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    return get_schema(dcd)


class PythonRequest(BaseModel):
    """Body of ``POST /tools/python``.

    Pass ``session_id`` to reuse an existing stateful session (variables
    defined in a previous call are still in scope). Omit it to start a
    fresh session; the generated id is returned in the response.
    """

    dataset_id: str
    code: str
    session_id: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class PythonResponse(BaseModel):
    """Response from ``POST /tools/python``."""

    session_id: str
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    repr: str | None = None
    files_created: list[dict[str, Any]] = Field(default_factory=list)
    timed_out: bool = False


@router.post("/python", response_model=PythonResponse)
def execute_python(request: PythonRequest, state: StateDep) -> PythonResponse:
    if request.dataset_id not in state.dcds:
        raise HTTPException(
            status_code=404, detail=f"Unknown dataset: {request.dataset_id}"
        )
    dataset_dir = Path(state.data_directory) / request.dataset_id / "data"
    output_dir = Path(state.data_directory) / request.dataset_id / "output"
    if not dataset_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Dataset directory missing: {dataset_dir}",
        )

    try:
        session = state.python_sessions.get_or_create(
            session_id=request.session_id,
            dataset_directory=dataset_dir,
            output_directory=output_dir,
        )
        result = session.execute(request.code, timeout_seconds=request.timeout_seconds)
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return PythonResponse(
        session_id=session.session_id,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        execution_time_ms=result.execution_time_ms,
        repr=result.repr,
        files_created=result.files_created,
        timed_out=result.timed_out,
    )


@router.delete("/python/sessions/{session_id}")
def stop_python_session(session_id: str, state: StateDep) -> dict[str, str]:
    """Explicitly terminate a stateful Python session."""
    state.python_sessions.drop(session_id)
    return {"session_id": session_id, "status": "stopped"}


@router.get("/python/sessions")
def list_python_sessions(state: StateDep) -> dict[str, list[str]]:
    """Return every live Python session id."""
    return {"sessions": state.python_sessions.list_sessions()}
