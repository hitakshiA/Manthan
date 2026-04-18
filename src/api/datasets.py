"""Dataset management API endpoints.

Exposes the ``/datasets`` router: upload, list, get, context retrieval,
lightweight schema summary, and delete.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.pipeline import (
    LlmClientFactory,
    _sanitize_name,
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

# Module-level anchor for fire-and-forget background tasks. asyncio's
# scheduler holds only a weak reference to tasks it hasn't awaited, so
# without this anchor long-running ingestion jobs can be garbage-
# collected mid-pipeline. Callers add(), and discard() on completion.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


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


class UrlConnectRequest(BaseModel):
    """Body of ``POST /datasets/connect-url``.

    Minimum: a URL pointing to a CSV/Parquet/JSON. Optional: a
    ``connection_id`` (when the file lives behind credentials stored
    in the vault) OR an inline ``secret`` block that follows the
    cloud_loader conventions (``access_key_id`` + ``secret_access_key``
    for S3, ``hmac_key_id`` + ``hmac_secret`` for GCS, etc.).
    """

    url: str
    connection_id: str | None = None
    secret: dict[str, Any] | None = None
    entity_slug: str | None = None
    entity_name: str | None = None


@router.post("/connect-url", response_model=DatasetSummary)
async def connect_url(
    state: StateDep,
    request: UrlConnectRequest,
) -> DatasetSummary:
    """Ingest a dataset from a URL (http, s3, gs, az://) via DuckDB httpfs.

    The full normal pipeline runs after materialization — profiling,
    classification, Gold + summary tables, entity + DCD history.
    """
    from src.ingestion.loaders.cloud_loader import CloudLoadRequest, load_from_url

    # Resolve the secret block: from vault, inline, or none (public URL).
    secret = request.secret
    if request.connection_id and state.credentials is not None:
        try:
            record = state.credentials.get(request.connection_id)
            secret = record.secret
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Derive a raw table name from the URL's last segment.
    stem_raw = request.url.rsplit("/", 1)[-1] or "url_dataset"
    stem = _sanitize_name(Path(stem_raw).stem)
    raw_table = f"raw_{stem}"

    # Fetch + materialize as a bronze table. Inside the connection lock
    # because DuckDB's CREATE TABLE isn't thread-safe against queries.
    with state.connection_lock:
        try:
            load_result = load_from_url(
                state.connection,
                CloudLoadRequest(
                    url=request.url,
                    destination_table=raw_table,
                    secret=secret,
                ),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"URL load failed: {exc}"
            ) from exc

    # Register dataset + run the shared Silver/Gold tail.
    entry = state.registry.register(load_result)
    try:
        final_entry = await _finish_pipeline_external(
            state=state,
            entry=entry,
            raw_table_name=raw_table,
            stem=stem,
            load_result=load_result,
            skip_clarification=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"URL ingest failed: {exc}"
        ) from exc

    return _summarize(state, final_entry.dataset_id)


async def _finish_pipeline_external(
    *,
    state: AppState,
    entry: Any,
    raw_table_name: str,
    stem: str,
    load_result: Any,
    skip_clarification: bool = True,
) -> Any:
    """Shim so connect-url can reuse the pipeline's Silver+Gold tail."""
    from src.api.pipeline import _finish_pipeline

    return await _finish_pipeline(
        state=state,
        entry=entry,
        raw_table_name=raw_table_name,
        stem=stem,
        load_result=load_result,
        llm_client_factory=LlmClient,
        skip_clarification=skip_clarification,
    )


class AsyncUploadResponse(BaseModel):
    dataset_id: str
    status: str


@router.post("/upload-async", response_model=AsyncUploadResponse)
@limiter.limit("10/minute")
async def upload_dataset_async(
    request: Request,
    state: StateDep,
    llm_client_factory: LlmFactoryDep,
    file: Annotated[UploadFile, File(...)],
) -> AsyncUploadResponse:
    """Upload a dataset and run the pipeline in the background.

    Returns the ``dataset_id`` immediately. Connect to
    ``GET /datasets/{dataset_id}/progress`` for real-time SSE progress.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload requires a filename")

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        temp_path = Path(tmp.name)

    # Pre-create the SSE queue so pipeline events are captured from the start.
    # We use a temporary placeholder ID, then swap after registration.
    # Actually: the pipeline itself creates the entry and dataset_id.
    # So we run the fast Bronze ingestion part synchronously to get the ID,
    # then background the rest. But that couples us to pipeline internals.
    #
    # Simpler approach: pre-generate the dataset_id, create the queue,
    # and run the full pipeline in background. The ingest_and_profile
    # function assigns the real ID via registry.register() — but we
    # don't know it upfront. Instead, let's just run it all in background
    # and have the queue keyed by a temporary ID that we'll remap.
    #
    # Simplest correct approach: run gateway.load() synchronously (fast,
    # <1s) to get the dataset_id, then background the rest.
    from src.ingestion.validators import validate_file

    settings = get_settings()
    try:
        validate_file(temp_path, max_size_mb=settings.max_upload_size_mb)
    except Exception as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Create the SSE queue and launch the full pipeline in background.
    # Pre-generate a temp ID; the pipeline remaps the queue to the real
    # dataset_id after registry.register() via progress_queue_key.
    from uuid import uuid4

    dataset_id = f"ds_{uuid4().hex[:10]}"

    # Create a progress channel: events are buffered in a list so late
    # SSE connections can replay, plus a queue for real-time streaming.
    channel: dict[str, object] = {
        "queue": asyncio.Queue(),
        "buffer": [],
        "done": False,
    }
    state.dataset_progress_queues[dataset_id] = channel  # type: ignore[assignment]

    async def _run_pipeline() -> None:
        try:
            await ingest_and_profile(
                state=state,
                file_path=temp_path,
                max_upload_size_mb=settings.max_upload_size_mb,
                original_filename=file.filename,
                llm_client_factory=llm_client_factory,
                progress_queue_key=dataset_id,
            )
        except Exception as exc:
            _push_error(state, dataset_id, str(exc))
        finally:
            temp_path.unlink(missing_ok=True)

    # Hold a module-level reference to the background task so it isn't
    # GC'd mid-flight (see RUF006). The pipeline records its own state
    # in AppState; completion just drops the reference.
    task = asyncio.create_task(_run_pipeline())
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)

    return AsyncUploadResponse(dataset_id=dataset_id, status="processing")


def _push_error(state: AppState, dataset_id: str, message: str) -> None:
    from src.api.pipeline import _push_sse_event

    _push_sse_event(state, dataset_id, {"type": "error", "message": message})


@router.get("/{dataset_id}/progress")
async def stream_pipeline_progress(
    dataset_id: str,
    state: StateDep,
) -> StreamingResponse:
    """SSE stream of pipeline progress events for a dataset.

    Replays buffered events first (handles late connections), then
    streams new events in real-time until a terminal event.
    """
    channel = state.dataset_progress_queues.get(dataset_id)
    if channel is None:
        # Check if already completed — replay from progress list
        progress = state.dataset_progress.get(dataset_id)
        if progress:

            async def _replay() -> AsyncIterator[str]:
                yield f"data: {json.dumps({'type': 'complete', 'dataset_id': dataset_id})}\n\n"

            return StreamingResponse(_replay(), media_type="text/event-stream")
        raise HTTPException(
            status_code=404,
            detail=f"No active pipeline for dataset: {dataset_id}",
        )

    async def _stream() -> AsyncIterator[str]:
        buf: list[dict[str, object]] = channel["buffer"]  # type: ignore[assignment]
        queue: asyncio.Queue[dict[str, object]] = channel["queue"]  # type: ignore[assignment]
        done: bool = channel["done"]  # type: ignore[assignment]

        # Replay buffered events (handles late SSE connections)
        replayed = len(buf)
        for evt in list(buf):
            yield f"data: {json.dumps(evt)}\n\n"
            if evt.get("type") in ("complete", "error"):
                return

        if done:
            return

        # Drain queue items that were already in the buffer to avoid dupes
        drained = 0
        while not queue.empty() and drained < replayed:
            try:
                queue.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break

        # Stream new events in real-time
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300.0)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                yield f"data: {json.dumps(event)}\n\n"

                if event.get("type") in ("complete", "error"):
                    break
        finally:
            await asyncio.sleep(5)
            state.dataset_progress_queues.pop(dataset_id, None)

    return StreamingResponse(_stream(), media_type="text/event-stream")


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
    # Discover ALL summary tables (not just hardcoded suffixes).
    # Use the thread-safe helper — parallel browser schema calls land
    # on different threads, and concurrent DuckDB access on one
    # connection segfaults the native engine.
    summary_tables: list[str] = []
    gold_table = state.gold_table_names.get(dataset_id)
    if gold_table:
        try:
            rows = state.connection_fetchall(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE ? AND table_name != ?",
                [f"{gold_table}%", gold_table],
            )
            summary_tables = [r[0] for r in rows]
        except Exception:
            pass
    return get_schema(dcd, summary_tables=summary_tables)


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, state: StateDep) -> dict[str, str]:
    try:
        state.registry.delete(dataset_id)
    except IngestionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    state.dcds.pop(dataset_id, None)
    state.gold_table_names.pop(dataset_id, None)
    state.rebuild_entity_index()
    return {"dataset_id": dataset_id, "status": "deleted"}


@router.post("/{slug_or_id}/refresh")
async def refresh_dataset(
    slug_or_id: str,
    file: Annotated[UploadFile, File()],
    state: StateDep,
) -> dict[str, Any]:
    """Re-ingest a dataset in place, preserving entity identity + customizations.

    The exec uploads a new version of a CSV (or an updated export). Manthan:

        1. Resolves slug or id → target dataset
        2. Captures the user-authored customizations (entity name,
           metrics, column labels/synonyms/pii)
        3. Runs the normal ingest pipeline under a temporary dataset_id
           (so the existing one keeps serving reads)
        4. Merges customizations onto the new DCD
        5. Atomically rebinds the target dataset_id to the new
           physical table; drops the old physical + parquet files
        6. Deletes the temporary dataset_id
        7. Logs a dcd_history entry

    Stable identity across refresh is what makes governed metrics
    load-bearing — the exec keeps saying "revenue" and Manthan keeps
    composing it the same way, even as the underlying data changes.
    """
    from src.core.dcd_history import log_dcd_change

    # ── 1. Resolve target ─────────────────────────────────
    target_dcd = state.resolve_entity(slug_or_id)
    if target_dcd is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown dataset/entity: {slug_or_id}"
        )
    target_id = target_dcd.dataset.id

    # ── 2. Capture customizations from current DCD ────────
    old_entity = target_dcd.dataset.entity
    preserved_entity_name = old_entity.name if old_entity else None
    preserved_metrics = list(old_entity.metrics) if old_entity else []
    preserved_col_edits: dict[str, dict[str, Any]] = {}
    for col in target_dcd.dataset.columns:
        edits: dict[str, Any] = {}
        if col.label:
            edits["label"] = col.label
        if col.pii:
            edits["pii"] = col.pii
        if col.synonyms:
            edits["synonyms"] = list(col.synonyms)
        if edits:
            preserved_col_edits[col.name] = edits

    # ── 3. Stage the new file + run pipeline ──────────────
    max_mb = get_settings().max_upload_size_mb
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        new_path = Path(tmp.name)

    try:
        new_entry = await ingest_and_profile(
            state=state,
            file_path=new_path,
            max_upload_size_mb=max_mb,
            original_filename=file.filename or "refresh",
            llm_client_factory=LlmClient,
            skip_clarification=True,  # refresh is autonomous
        )
    except (
        IngestionError,
        ProfilingError,
        SqlValidationError,
        DcdValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_id = new_entry.dataset_id
    new_dcd = state.dcds[new_id]
    old_physical = state.gold_table_names[target_id]
    new_physical = state.gold_table_names[new_id]

    # ── 4. Merge customizations onto the new DCD ──────────
    # ALWAYS preserve the original slug + name; the entity identity
    # is what makes refresh feel seamless to the exec. Also preserve
    # any metrics whose referenced columns still exist.
    merged_entity = new_dcd.dataset.entity
    if merged_entity is not None and old_entity is not None:
        update_fields: dict[str, Any] = {
            "slug": old_entity.slug,
            "name": preserved_entity_name or old_entity.name,
        }
        new_col_names = {c.name for c in new_dcd.dataset.columns}
        surviving_metrics = []
        for m in preserved_metrics:
            expr_ok = all(
                candidate in new_col_names
                for candidate in _extract_column_refs(m.expression)
            )
            if expr_ok:
                surviving_metrics.append(m)
        update_fields["metrics"] = surviving_metrics
        merged_entity = merged_entity.model_copy(update=update_fields)

    new_columns = []
    for col in new_dcd.dataset.columns:
        if col.name in preserved_col_edits:
            new_columns.append(col.model_copy(update=preserved_col_edits[col.name]))
        else:
            new_columns.append(col)

    merged_dcd = new_dcd.model_copy(
        update={
            "dataset": new_dcd.dataset.model_copy(
                update={
                    "id": target_id,  # rebind to the stable id
                    "entity": merged_entity,
                    "columns": new_columns,
                }
            )
        }
    )

    # ── 5. Atomic rebind in state ─────────────────────────
    state.dcds[target_id] = merged_dcd
    state.gold_table_names[target_id] = new_physical

    # ── 6. Tear down the temporary dataset_id entry ───────
    state.dcds.pop(new_id, None)
    state.gold_table_names.pop(new_id, None)
    with contextlib.suppress(Exception):
        state.registry.delete(new_id)

    # Drop the old physical table + parquet cache (best effort).
    try:
        with state.connection_lock:
            state.connection.execute(f'DROP TABLE IF EXISTS "{old_physical}"')
            state.connection.execute(f'DROP VIEW IF EXISTS "{old_physical}"')
    except Exception:
        pass

    # Persist the merged DCD to disk and write a history entry.
    yaml_path = state.data_directory / target_id / "manthan-context.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(merged_dcd.to_yaml())
    log_dcd_change(
        data_directory=state.data_directory,
        dataset_id=target_id,
        new_dcd=merged_dcd,
        changed_by="pipeline.refresh",
        reason=f"in-place refresh from {file.filename}",
    )

    state.rebuild_entity_index()
    # Intentionally return a compact dict — the DatasetEntry model has
    # optional load_result fields that Pydantic 2 serializes strictly,
    # which was 500'ing with datetime-on-datetime mismatches. The UI
    # only needs ``dataset_id`` + ``row_count`` here; the full schema
    # comes from a subsequent ``/datasets/{id}/schema`` call.
    return {
        "dataset_id": target_id,
        "row_count": merged_dcd.dataset.source.row_count,
        "entity_slug": merged_entity.slug if merged_entity else None,
        "physical_table": merged_entity.physical_table if merged_entity else None,
        "metrics_preserved": len(surviving_metrics) if merged_entity else 0,
        "status": "refreshed",
    }


def _extract_column_refs(expression: str) -> list[str]:
    """Pull likely column references from a metric SQL expression.

    Used by the refresh path to decide whether a preserved metric
    still makes sense against the new schema. Heuristic only — we
    look for bare identifiers and quoted identifiers inside the
    aggregation, ignoring SQL keywords.
    """
    import re

    # Match `"col_name"` or bare `col_name` (word-boundary).
    refs: set[str] = set()
    for match in re.finditer(r'"([^"]+)"', expression):
        refs.add(match.group(1))
    # Ignore standard SQL keywords + common aggregation functions.
    stopwords = {
        "sum",
        "count",
        "avg",
        "min",
        "max",
        "distinct",
        "case",
        "when",
        "then",
        "else",
        "end",
        "null",
        "is",
        "not",
        "and",
        "or",
        "true",
        "false",
        "from",
        "where",
        "as",
    }
    for match in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", expression):
        token = match.group(1)
        if token.lower() in stopwords:
            continue
        # numbers, uppercase-only SQL-looking things
        if token.isdigit():
            continue
        refs.add(token)
    return list(refs)


@router.get("/{dataset_id}/history")
def get_dataset_history(
    dataset_id: str,
    state: StateDep,
    limit: int = 50,
    include_snapshots: bool = False,
) -> list[dict[str, Any]]:
    """Return the append-only change log for this dataset's DCD.

    Every ingest and every schema/metric edit appends an entry with
    ``timestamp`` + ``changed_by`` + ``reason`` + a full DCD
    snapshot (under ``snapshot``, opt-in via the query flag).
    """
    from src.core.dcd_history import read_dcd_history

    if dataset_id not in state.dcds:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    return read_dcd_history(
        data_directory=state.data_directory,
        dataset_id=dataset_id,
        limit=limit,
        include_snapshots=include_snapshots,
    )


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
    row = state.connection_fetchone(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1",
        [table_name],
    )
    return row is not None
