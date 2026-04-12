"""Dataset management API endpoints.

Exposes the ``/datasets`` router: upload, list, get, context retrieval,
lightweight schema summary, and delete.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel

from src.api.pipeline import (
    LlmClientFactory,
    ingest_and_profile,
    ingest_database_and_profile,
    ingest_multi_file_and_profile,
)
from src.core.config import get_settings
from src.core.exceptions import (
    DcdValidationError,
    IngestionError,
    ProfilingError,
    SqlValidationError,
)
from src.core.llm import LlmClient
from src.core.rate_limit import limiter
from src.core.state import AppState, get_state
from src.ingestion.loaders.db_loader import DbLoadRequest
from src.semantic.editor import DcdEditRequest, apply_edits
from src.tools.context_tool import get_context
from src.tools.schema_tool import SchemaSummary, get_schema

router = APIRouter(prefix="/datasets", tags=["datasets"])


def get_llm_client_factory() -> LlmClientFactory:
    """Default LLM client factory dependency — tests override this."""
    return LlmClient


StateDep = Annotated[AppState, Depends(get_state)]
LlmFactoryDep = Annotated[LlmClientFactory, Depends(get_llm_client_factory)]


class DatasetSummary(BaseModel):
    """Short dataset record returned by the list / upload endpoints."""

    dataset_id: str
    name: str
    source_type: str
    row_count: int
    column_count: int
    status: str
    created_at: datetime


def _summarize(state: AppState, dataset_id: str) -> DatasetSummary:
    entry = state.registry.get(dataset_id)
    dcd = state.dcds.get(dataset_id)
    name = dcd.dataset.name if dcd else entry.load_result.original_filename
    return DatasetSummary(
        dataset_id=entry.dataset_id,
        name=name,
        source_type=entry.load_result.source_type,
        row_count=entry.load_result.row_count,
        column_count=entry.load_result.column_count,
        status=entry.status,
        created_at=entry.created_at,
    )


@router.post("/upload", response_model=DatasetSummary)
@limiter.limit("10/minute")
async def upload_dataset(
    request: Request,
    state: StateDep,
    llm_client_factory: LlmFactoryDep,
    file: Annotated[UploadFile, File(...)],
) -> DatasetSummary:
    """Upload a dataset, run ingestion + profiling + materialization."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload requires a filename")

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        temp_path = Path(tmp.name)

    settings = get_settings()
    try:
        entry = await ingest_and_profile(
            state=state,
            file_path=temp_path,
            max_upload_size_mb=settings.max_upload_size_mb,
            original_filename=file.filename,
            llm_client_factory=llm_client_factory,
        )
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProfilingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    return _summarize(state, entry.dataset_id)


@router.post("/upload-multi", response_model=DatasetSummary)
async def upload_multi_file_dataset(
    state: StateDep,
    llm_client_factory: LlmFactoryDep,
    files: Annotated[list[UploadFile], File(...)],
) -> DatasetSummary:
    """Upload multiple related files as one dataset.

    The first file is treated as the primary table (Gold-materialized,
    summary tables, verified queries). Additional files are profiled
    and attached to the DCD under ``tables`` so the agent can query
    them via ``run_sql`` against the raw tables. Foreign keys are
    detected automatically by column-name + value-containment analysis
    and populated into ``DcdDataset.relationships``.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Upload requires at least one file")
    for file in files:
        if not file.filename:
            raise HTTPException(
                status_code=400, detail="Every uploaded file must have a filename"
            )

    staged: list[tuple[Path, str]] = []
    try:
        for file in files:
            suffix = Path(file.filename or "").suffix
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                content = await file.read()
                tmp.write(content)
                staged.append((Path(tmp.name), file.filename or tmp.name))

        settings = get_settings()
        entry = await ingest_multi_file_and_profile(
            state=state,
            files=staged,
            max_upload_size_mb=settings.max_upload_size_mb,
            llm_client_factory=llm_client_factory,
        )
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProfilingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        for path, _ in staged:
            path.unlink(missing_ok=True)

    return _summarize(state, entry.dataset_id)


@router.post("/connect", response_model=DatasetSummary)
async def connect_database(
    state: StateDep,
    llm_client_factory: LlmFactoryDep,
    request: DbLoadRequest,
) -> DatasetSummary:
    """Connect to a database source, pull a table, run the full pipeline."""
    try:
        entry = await ingest_database_and_profile(
            state=state,
            db_request=request,
            llm_client_factory=llm_client_factory,
        )
    except (IngestionError, SqlValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProfilingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _summarize(state, entry.dataset_id)


@router.get("", response_model=list[DatasetSummary])
def list_datasets(state: StateDep) -> list[DatasetSummary]:
    return [
        _summarize(state, entry.dataset_id) for entry in state.registry.list_entries()
    ]


@router.get("/{dataset_id}", response_model=DatasetSummary)
def get_dataset(dataset_id: str, state: StateDep) -> DatasetSummary:
    try:
        return _summarize(state, dataset_id)
    except IngestionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_id}/context")
def get_dataset_context(
    dataset_id: str,
    state: StateDep,
    query: str | None = None,
) -> Response:
    dcd = state.dcds.get(dataset_id)
    if dcd is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    yaml_text = get_context(dcd, query=query)
    return Response(content=yaml_text, media_type="application/x-yaml")


@router.put("/{dataset_id}/context", response_model=DatasetSummary)
def put_dataset_context(
    dataset_id: str,
    state: StateDep,
    request: DcdEditRequest,
) -> DatasetSummary:
    dcd = state.dcds.get(dataset_id)
    if dcd is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    gold_table = state.gold_table_names.get(dataset_id)
    try:
        updated = apply_edits(
            dcd,
            request,
            connection=state.connection,
            gold_table=gold_table,
        )
    except DcdValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state.dcds[dataset_id] = updated
    return _summarize(state, dataset_id)


@router.get("/{dataset_id}/schema", response_model=SchemaSummary)
def get_dataset_schema(dataset_id: str, state: StateDep) -> SchemaSummary:
    dcd = state.dcds.get(dataset_id)
    if dcd is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    summary_tables: list[str] = []
    gold_table = state.gold_table_names.get(dataset_id)
    if gold_table:
        summary_tables = [
            name
            for name in (
                f"{gold_table}_daily",
                f"{gold_table}_monthly",
                f"{gold_table}_by_region",
                f"{gold_table}_by_customer_segment",
            )
            if _table_exists(state, name)
        ]
    return get_schema(dcd, summary_tables=summary_tables)


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, state: StateDep) -> dict[str, str]:
    try:
        state.registry.delete(dataset_id)
    except IngestionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    state.dcds.pop(dataset_id, None)
    state.gold_table_names.pop(dataset_id, None)
    return {"dataset_id": dataset_id, "status": "deleted"}


@router.get("/{dataset_id}/output/{filename:path}")
def get_output_artifact(
    dataset_id: str,
    filename: str,
    state: StateDep,
) -> Response:
    """Serve an artifact written by the Python sandbox (e.g. render_spec.json)."""
    if dataset_id not in state.dcds:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    # Prevent path traversal
    safe = Path(filename).name
    artifact = Path(state.data_directory) / dataset_id / "output" / safe
    if not artifact.exists() or not artifact.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {safe}")
    content = artifact.read_text(encoding="utf-8")
    media = "application/json" if safe.endswith(".json") else "text/plain"
    return Response(content=content, media_type=media)


def _table_exists(state: AppState, table_name: str) -> bool:
    row = state.connection.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1",
        [table_name],
    ).fetchone()
    return row is not None
