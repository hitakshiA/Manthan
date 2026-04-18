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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.core.exceptions import SandboxError, SqlValidationError, ToolError
from src.core.rate_limit import limiter
from src.core.state import AppState, get_state
from src.semantic.validator import EntityCatalog, validate_sql
from src.tools.context_tool import get_context
from src.tools.metric_tool import (
    ComputeMetricError,
    MetricRequest,
    compute_metric,
)
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
@limiter.limit("120/minute")
def execute_sql(
    request: Request, sql_request: SqlRequest, state: StateDep
) -> SqlResult:
    if sql_request.dataset_id not in state.dcds:
        raise HTTPException(
            status_code=404, detail=f"Unknown dataset: {sql_request.dataset_id}"
        )
    # Phase 2 semantic validator — runs before DuckDB to catch
    # hallucinated tables/columns and silent metric-filter drops.
    # Failures raise HTTP 400 with an agent-readable repair hint;
    # the agent retries up to its internal limit. Unknown-column
    # and other soft issues are warnings — they don't block exec.
    dcd = state.dcds[sql_request.dataset_id]
    catalog = EntityCatalog.from_dcd(dcd)
    extras = set(state.gold_table_names.values()) | {
        tname for tname in _list_raw_tables(state)
    }
    result = validate_sql(
        sql_request.sql,
        entity=catalog,
        extra_known_tables=extras,
    )
    if not result.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "sql_validation_failed",
                "message": result.error_message(),
                "issues": [
                    {
                        "severity": i.severity,
                        "code": i.code,
                        "message": i.message,
                        "suggestion": i.suggestion,
                    }
                    for i in result.issues
                ],
            },
        )
    try:
        # Serialize DuckDB access — the native connection is not
        # thread-safe and the agent fires many parallel SQL calls.
        with state.connection_lock:
            return run_sql(
                state.connection,
                sql_request.sql,
                max_rows=sql_request.max_rows,
            )
    except SqlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _list_raw_tables(state: AppState) -> list[str]:
    """Quick pass over the registry to collect every raw_* table name
    so the validator allow-lists them for multi-dataset join support."""
    names: list[str] = []
    for dcd in state.dcds.values():
        for tbl in dcd.dataset.tables:
            names.append(tbl.name)
        # Also include each dataset's load_result primary table name
        # from the registry, if accessible.
    return names


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


class MetricResponse(BaseModel):
    """Exec-friendly shape returned by ``POST /tools/metric``.

    Carries both the tabular result and the full auditable context —
    the exact SQL that ran, the metric's declared filter, and the
    dimensions/grain that produced the slice. The ``numeric_claim``
    event emitted by the agent loop in Phase 3 copies directly from
    this object.
    """

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    sql_used: str
    metric_slug: str
    metric_label: str
    metric_description: str | None
    metric_expression: str
    metric_filter: str | None
    metric_unit: str | None
    dimensions: list[str]
    extra_filters: dict[str, Any]
    grain: str | None
    elapsed_ms: float


@router.post("/metric", response_model=MetricResponse)
@limiter.limit("120/minute")
def execute_metric(
    request: Request, metric_request: MetricRequest, state: StateDep
) -> MetricResponse:
    """Governed-metric query path.

    The agent sends a structured request (entity + metric + optional
    dimensions/filters/grain); Manthan composes SQL from the declared
    metric definition and executes it. This bypasses the validator
    because we trust our own composer — the semantic contract is the
    definition.
    """
    try:
        result = compute_metric(state, metric_request)
    except ComputeMetricError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MetricResponse(
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        sql_used=result.sql_used,
        metric_slug=result.metric_slug,
        metric_label=result.metric_label,
        metric_description=result.metric_description,
        metric_expression=result.metric_expression,
        metric_filter=result.metric_filter,
        metric_unit=result.metric_unit,
        dimensions=result.dimensions,
        extra_filters=result.extra_filters,
        grain=result.grain,
        elapsed_ms=round(result.elapsed_ms, 1),
    )


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
