"""End-to-end Bronze → Silver → Gold orchestration.

Two entry points share the same Silver + Gold tail:

- :func:`ingest_and_profile` — file-based (CSV, Parquet, Excel, JSON)
- :func:`ingest_database_and_profile` — database source via DuckDB
  scanner extensions (Postgres, MySQL, SQLite)
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from src.core import metrics
from src.core.llm import LlmClient
from src.core.state import AppState
from src.ingestion.base import LoadResult, validate_identifier
from src.ingestion.gateway import create_default_gateway
from src.ingestion.loaders.db_loader import DbLoadRequest, load_from_database
from src.ingestion.registry import DatasetEntry
from src.ingestion.relationships import detect_relationships
from src.ingestion.validators import validate_file
from src.materialization.exporter import export_dataset
from src.materialization.optimizer import create_gold_table
from src.materialization.quality import run_quality_suite
from src.materialization.query_generator import generate_verified_queries
from src.materialization.summarizer import create_summary_tables
from src.profiling.agent import profile_dataset
from src.profiling.clarification import generate_questions
from src.semantic.generator import (
    build_dcd,
    build_dcd_table_from_profile,
    dcd_table_from_primary_dcd,
)

_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9_]")

LlmClientFactory = Callable[[], LlmClient]


async def ingest_and_profile(
    *,
    state: AppState,
    file_path: Path,
    max_upload_size_mb: int = 500,
    original_filename: str | None = None,
    llm_client_factory: LlmClientFactory = LlmClient,
) -> DatasetEntry:
    """Run the full pipeline for a file-based source."""
    validate_file(file_path, max_size_mb=max_upload_size_mb)

    display_name = original_filename or file_path.name
    stem = _sanitize_name(Path(display_name).stem)
    raw_table_name = f"raw_{stem}"
    validate_identifier(raw_table_name)

    gateway = create_default_gateway()
    load_result = gateway.load(file_path, state.connection, raw_table_name)
    if original_filename:
        load_result = load_result.model_copy(
            update={"original_filename": original_filename}
        )
    entry = state.registry.register(load_result)

    return await _finish_pipeline(
        state=state,
        entry=entry,
        raw_table_name=raw_table_name,
        stem=stem,
        load_result=load_result,
        llm_client_factory=llm_client_factory,
    )


async def ingest_multi_file_and_profile(
    *,
    state: AppState,
    files: list[tuple[Path, str]],
    max_upload_size_mb: int = 500,
    llm_client_factory: LlmClientFactory = LlmClient,
) -> DatasetEntry:
    """Run the pipeline for a dataset composed of several related files.

    Each file is loaded as its own ``raw_*`` table and profiled
    individually. The first file becomes the **primary** table and is
    materialized to Gold (sorted, ENUM'd, summary tables, verified
    queries, Parquet exported). Additional files are profiled and
    attached to the DCD under ``tables`` for the agent to query via
    ``run_sql`` against the raw tables directly.

    Foreign keys between the tables are detected by column-name +
    value-containment analysis and populated into
    ``DcdDataset.relationships``.

    Args:
        files: Pairs of ``(local_path, original_filename)`` for each
            file to load. The first entry is treated as the primary
            table.
    """
    if not files:
        raise ValueError("ingest_multi_file_and_profile requires at least one file")

    primary_path, primary_name = files[0]
    primary_entry = await ingest_and_profile(
        state=state,
        file_path=primary_path,
        max_upload_size_mb=max_upload_size_mb,
        original_filename=primary_name,
        llm_client_factory=llm_client_factory,
    )

    if len(files) == 1:
        return primary_entry

    dcd = state.dcds[primary_entry.dataset_id]
    gateway = create_default_gateway()
    additional_tables = []
    all_raw_table_names = [
        f"raw_{_sanitize_name(Path(primary_name).stem)}",
    ]

    for extra_path, extra_name in files[1:]:
        validate_file(extra_path, max_size_mb=max_upload_size_mb)
        stem = _sanitize_name(Path(extra_name).stem)
        raw_table_name = f"raw_{stem}_{uuid_suffix()}"
        validate_identifier(raw_table_name)
        load_result = gateway.load(extra_path, state.connection, raw_table_name)
        load_result = load_result.model_copy(update={"original_filename": extra_name})

        llm_client = llm_client_factory()
        async with llm_client as llm:
            extra_profile = await profile_dataset(state.connection, raw_table_name, llm)

        additional_tables.append(
            build_dcd_table_from_profile(
                table_name=raw_table_name,
                original_filename=extra_name,
                load_result=load_result,
                profiling_result=extra_profile,
            )
        )
        all_raw_table_names.append(raw_table_name)
        metrics.increment("ingestion.rows_loaded", load_result.row_count)

    relationships = detect_relationships(state.connection, all_raw_table_names)

    # The primary table also lives in the DCD.tables list so the agent
    # can enumerate all tables uniformly.
    primary_as_table = dcd_table_from_primary_dcd(dcd, all_raw_table_names[0])
    tables = [primary_as_table, *additional_tables]

    updated_dataset = dcd.dataset.model_copy(
        update={
            "tables": tables,
            "relationships": relationships,
        }
    )
    updated_dcd = dcd.model_copy(update={"dataset": updated_dataset})
    state.dcds[primary_entry.dataset_id] = updated_dcd

    _record_progress(
        state,
        primary_entry.dataset_id,
        "gold",
        f"multi-file dataset: {len(tables)} tables, "
        f"{len(relationships)} relationships detected",
    )

    return primary_entry


async def ingest_database_and_profile(
    *,
    state: AppState,
    db_request: DbLoadRequest,
    llm_client_factory: LlmClientFactory = LlmClient,
) -> DatasetEntry:
    """Run the full pipeline for a database source."""
    stem = _sanitize_name(db_request.destination_table)
    raw_table_name = f"raw_{stem}"
    validate_identifier(raw_table_name)
    db_request = db_request.model_copy(update={"destination_table": raw_table_name})

    load_result = load_from_database(state.connection, db_request)
    entry = state.registry.register(load_result)

    return await _finish_pipeline(
        state=state,
        entry=entry,
        raw_table_name=raw_table_name,
        stem=stem,
        load_result=load_result,
        llm_client_factory=llm_client_factory,
    )


async def _finish_pipeline(
    *,
    state: AppState,
    entry: DatasetEntry,
    raw_table_name: str,
    stem: str,
    load_result: LoadResult,
    llm_client_factory: LlmClientFactory,
) -> DatasetEntry:
    """Shared Silver + Gold tail used by both ingestion entry points."""
    _record_progress(state, entry.dataset_id, "bronze", "raw table loaded")
    metrics.increment("ingestion.rows_loaded", load_result.row_count)
    metrics.increment("ingestion.datasets_total")

    llm_client = llm_client_factory()
    async with llm_client as llm:
        profiling_result = await profile_dataset(state.connection, raw_table_name, llm)
    state.registry.update_status(entry.dataset_id, "silver")
    _record_progress(state, entry.dataset_id, "silver", "profiling complete")
    metrics.increment("profiling.datasets_total")

    state.clarifications[entry.dataset_id] = generate_questions(profiling_result)

    dcd = build_dcd(
        dataset_id=entry.dataset_id,
        load_result=load_result,
        profiling_result=profiling_result,
    )

    gold_table_name = f"gold_{stem}_{entry.dataset_id[3:]}"
    validate_identifier(gold_table_name)
    create_gold_table(state.connection, raw_table_name, gold_table_name, dcd)
    summary_tables = create_summary_tables(state.connection, gold_table_name, dcd)
    metrics.increment("materialization.summary_tables", len(summary_tables))

    verified_queries = generate_verified_queries(
        dcd, gold_table=gold_table_name, connection=state.connection
    )
    dcd = dcd.model_copy(
        update={
            "dataset": dcd.dataset.model_copy(
                update={"verified_queries": verified_queries}
            )
        }
    )

    quality_report = run_quality_suite(state.connection, gold_table_name, dcd)
    metrics.observe(
        "materialization.quality_success_percent",
        quality_report.success_percent,
    )
    dcd = dcd.model_copy(
        update={
            "dataset": dcd.dataset.model_copy(
                update={
                    "quality": dcd.dataset.quality.model_copy(
                        update={
                            "overall_score": min(
                                dcd.dataset.quality.overall_score,
                                quality_report.success_percent / 100.0,
                            )
                        }
                    )
                }
            )
        }
    )

    export_dataset(
        connection=state.connection,
        dataset_id=entry.dataset_id,
        gold_table=gold_table_name,
        summary_tables=summary_tables,
        dcd=dcd,
        data_directory=state.data_directory,
    )

    state.dcds[entry.dataset_id] = dcd
    state.gold_table_names[entry.dataset_id] = gold_table_name
    state.registry.update_status(entry.dataset_id, "gold")
    _record_progress(
        state,
        entry.dataset_id,
        "gold",
        f"materialized ({quality_report.success_percent:.0f}% quality)",
    )
    metrics.increment("materialization.datasets_total")

    return state.registry.get(entry.dataset_id)


def _record_progress(
    state: AppState,
    dataset_id: str,
    stage: str,
    message: str,
) -> None:
    events = state.dataset_progress.setdefault(dataset_id, [])
    events.append(
        {
            "dataset_id": dataset_id,
            "stage": stage,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )


def _sanitize_name(raw: str) -> str:
    """Convert ``raw`` into a lowercase identifier-safe string."""
    cleaned = _INVALID_NAME_CHARS.sub("_", raw.lower())
    cleaned = cleaned.strip("_") or "dataset"
    if not cleaned[0].isalpha() and cleaned[0] != "_":
        cleaned = f"d_{cleaned}"
    return cleaned


def uuid_suffix() -> str:
    """Return a short random suffix for disambiguating multi-file raw tables."""
    from uuid import uuid4

    return uuid4().hex[:6]
