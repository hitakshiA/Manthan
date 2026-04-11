"""Agent tool API endpoints.

Thin HTTP shells around ``src.tools.sql_tool``, ``context_tool``,
``schema_tool``, and ``python_tool`` (Docker sandbox).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.exceptions import SandboxError, SqlValidationError, ToolError
from src.core.state import AppState, get_state
from src.tools.context_tool import get_context
from src.tools.python_tool import SandboxResult, run_python
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
    """Body of ``POST /tools/python``."""

    dataset_id: str
    code: str
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)


@router.post("/python", response_model=SandboxResult)
def execute_python(request: PythonRequest, state: StateDep) -> SandboxResult:
    dcd = state.dcds.get(request.dataset_id)
    if dcd is None:
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
        return run_python(
            code=request.code,
            dataset_directory=dataset_dir,
            output_directory=output_dir,
            timeout_seconds=request.timeout_seconds,
        )
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
