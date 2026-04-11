"""End-to-end Bronze -> Silver -> Gold orchestration.

Wires together the ingestion gateway, the profiling agent, the DCD
generator, and the Gold materialization stage into a single
``ingest_and_profile`` entry point used by the API layer. Separated
from ``src/api/datasets.py`` so the orchestration is testable without
spinning up FastAPI.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from src.core.llm import LlmClient
from src.core.state import AppState
from src.ingestion.base import validate_identifier
from src.ingestion.gateway import create_default_gateway
from src.ingestion.registry import DatasetEntry
from src.ingestion.validators import validate_file
from src.materialization.exporter import export_dataset
from src.materialization.optimizer import create_gold_table
from src.materialization.query_generator import generate_verified_queries
from src.materialization.summarizer import create_summary_tables
from src.profiling.agent import profile_dataset
from src.semantic.generator import build_dcd

_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9_]")

LlmClientFactory = Callable[[], LlmClient]


async def ingest_and_profile(
    *,
    state: AppState,
    file_path: Path,
    max_upload_size_mb: int = 500,
    llm_client_factory: LlmClientFactory = LlmClient,
) -> DatasetEntry:
    """Run the full pipeline for ``file_path`` and return the registry entry.

    Args:
        state: The shared :class:`AppState`. Its ``registry``,
            ``connection``, ``data_directory``, ``dcds``, and
            ``gold_table_names`` are updated in place.
        file_path: Local path to the source file.
        max_upload_size_mb: Size-limit passed to :func:`validate_file`.
        llm_client_factory: Callable producing an :class:`LlmClient`.
            Tests inject a factory that returns an LlmClient wired to
            an ``httpx.MockTransport``.

    Returns:
        The :class:`DatasetEntry` after status has been advanced to
        ``gold``.
    """
    validate_file(file_path, max_size_mb=max_upload_size_mb)

    stem = _sanitize_name(file_path.stem)
    raw_table_name = f"raw_{stem}"
    validate_identifier(raw_table_name)

    # Bronze
    gateway = create_default_gateway()
    load_result = gateway.load(file_path, state.connection, raw_table_name)
    entry = state.registry.register(load_result)

    # Silver
    llm_client = llm_client_factory()
    async with llm_client as llm:
        profiling_result = await profile_dataset(state.connection, raw_table_name, llm)
    state.registry.update_status(entry.dataset_id, "silver")

    # Build DCD
    dcd = build_dcd(
        dataset_id=entry.dataset_id,
        load_result=load_result,
        profiling_result=profiling_result,
    )

    # Gold: optimize + summaries + verified queries + export
    gold_table_name = f"gold_{stem}_{entry.dataset_id[3:]}"
    validate_identifier(gold_table_name)
    create_gold_table(state.connection, raw_table_name, gold_table_name, dcd)
    summary_tables = create_summary_tables(state.connection, gold_table_name, dcd)

    verified_queries = generate_verified_queries(dcd, gold_table=gold_table_name)
    dcd = dcd.model_copy(
        update={
            "dataset": dcd.dataset.model_copy(
                update={"verified_queries": verified_queries}
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

    return state.registry.get(entry.dataset_id)


def _sanitize_name(raw: str) -> str:
    """Convert ``raw`` into a lowercase identifier-safe string."""
    cleaned = _INVALID_NAME_CHARS.sub("_", raw.lower())
    cleaned = cleaned.strip("_") or "dataset"
    if not cleaned[0].isalpha() and cleaned[0] != "_":
        cleaned = f"d_{cleaned}"
    return cleaned
