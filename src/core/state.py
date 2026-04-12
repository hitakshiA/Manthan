"""Shared application state for the FastAPI process.

Consolidates the per-process resources every API handler needs: the
dataset registry, a persistent DuckDB connection, the data-directory
path (from :class:`Settings`), and in-memory maps from ``dataset_id`` to
the Data Context Document and Gold table name assigned during
ingestion. The state is created lazily via :func:`get_state` so it is
easy to override in tests using FastAPI's ``dependency_overrides``.

On startup, :func:`get_state` calls :func:`rehydrate_datasets_from_disk`
which walks ``data/ds_*`` directories, reads the persisted DCD YAML, and
re-attaches the Gold parquet as a DuckDB view. This gives datasets
survival across server restarts — an agent that uploaded yesterday can
continue querying today without re-ingesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import duckdb

from src.core.agent_tasks import AgentTaskStore
from src.core.ask_user import AskUserRegistry
from src.core.config import get_settings
from src.core.database import create_connection
from src.core.logger import get_logger
from src.core.memory import MemoryStore
from src.core.plans import PlanStore
from src.core.subagents import SubagentStore
from src.ingestion.base import LoadResult, quote_identifier, validate_identifier
from src.ingestion.registry import DatasetEntry, DatasetRegistry
from src.profiling.clarification import (
    ClarificationAnswer,
    ClarificationQuestion,
)
from src.semantic.schema import DataContextDocument
from src.tools.python_session import PythonSessionManager

_logger = get_logger()


@dataclass
class AppState:
    """Per-process state shared across API handlers."""

    registry: DatasetRegistry
    connection: duckdb.DuckDBPyConnection
    data_directory: Path
    memory: MemoryStore
    plans: PlanStore
    dcds: dict[str, DataContextDocument] = field(default_factory=dict)
    gold_table_names: dict[str, str] = field(default_factory=dict)
    clarifications: dict[str, list[ClarificationQuestion]] = field(default_factory=dict)
    clarification_answers: dict[str, list[ClarificationAnswer]] = field(
        default_factory=dict
    )
    dataset_progress: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    python_sessions: PythonSessionManager = field(default_factory=PythonSessionManager)
    agent_tasks: AgentTaskStore = field(default_factory=AgentTaskStore)
    ask_user: AskUserRegistry = field(default_factory=AskUserRegistry)
    subagents: SubagentStore = field(default_factory=SubagentStore)

    def close(self) -> None:
        """Close the underlying DuckDB connection and shut down sessions."""
        self.python_sessions.shutdown_all()
        self.connection.close()


@lru_cache(maxsize=1)
def get_state() -> AppState:
    """Return the cached :class:`AppState` for this process."""
    settings = get_settings()
    data_directory = Path(settings.data_directory)
    data_directory.mkdir(parents=True, exist_ok=True)
    state = AppState(
        registry=DatasetRegistry(),
        connection=create_connection(settings=settings),
        data_directory=data_directory,
        memory=MemoryStore(data_directory / "agent_memory.db"),
        plans=PlanStore(data_directory / "plan_audit.db"),
    )
    rehydrate_datasets_from_disk(state)
    return state


def rehydrate_datasets_from_disk(state: AppState) -> int:
    """Restore previously-ingested datasets from disk into the registry.

    Walks ``state.data_directory/ds_*`` subdirectories. For each one,
    reads the persisted ``manthan-context.yaml``, re-attaches the Gold
    parquet files as DuckDB views (so ``run_sql`` / ``run_python`` can
    query them), and populates the in-memory registry, ``dcds``, and
    ``gold_table_names`` maps. Silently skips directories that are
    incomplete (missing YAML, missing Gold parquet, or parse errors).

    Returns:
        The number of datasets successfully rehydrated.
    """
    restored = 0
    for ds_dir in sorted(state.data_directory.glob("ds_*")):
        if not ds_dir.is_dir():
            continue
        dcd_path = ds_dir / "manthan-context.yaml"
        if not dcd_path.exists():
            continue
        try:
            dcd = DataContextDocument.from_yaml(dcd_path.read_text())
        except Exception as exc:  # pragma: no cover — defensive
            _logger.warning(
                "state.rehydrate.bad_dcd",
                ds_dir=str(ds_dir),
                error=str(exc)[:200],
            )
            continue

        # Find the primary Gold parquet (the one without a _by_ /
        # _daily / _monthly / _weekly / _quarterly / _yearly suffix).
        parquet_dir = ds_dir / "data"
        primary: Path | None = None
        if parquet_dir.exists():
            suffix_skip = (
                "_daily.parquet",
                "_monthly.parquet",
                "_weekly.parquet",
                "_quarterly.parquet",
                "_yearly.parquet",
            )
            for p in sorted(parquet_dir.glob("gold_*.parquet")):
                if "_by_" in p.name:
                    continue
                if any(p.name.endswith(s) for s in suffix_skip):
                    continue
                primary = p
                break

        if primary is None:
            continue

        gold_table_name = primary.stem  # e.g. gold_yellow_tripdata_2024_01_xxxx
        try:
            validate_identifier(gold_table_name)
        except Exception:
            continue

        # Attach all parquet files (primary + summary rollups) as views.
        all_parquets = sorted(parquet_dir.glob("gold_*.parquet"))
        try:
            for p in all_parquets:
                tname = p.stem
                try:
                    validate_identifier(tname)
                except Exception:
                    continue
                escaped = str(p).replace("'", "''")
                state.connection.execute(
                    f"CREATE OR REPLACE VIEW {quote_identifier(tname)} "
                    f"AS SELECT * FROM read_parquet('{escaped}')"
                )
        except duckdb.Error as exc:  # pragma: no cover — defensive
            _logger.warning(
                "state.rehydrate.attach_failed",
                ds_dir=str(ds_dir),
                error=str(exc)[:200],
            )
            continue

        # Register dataset with synthesized LoadResult metadata from the DCD.
        source = dcd.dataset.source
        try:
            load_result = LoadResult(
                table_name=gold_table_name,
                source_type=source.type,
                original_filename=source.original_filename or gold_table_name,
                ingested_at=source.ingested_at or datetime.now(UTC),
                row_count=source.row_count,
                column_count=len(dcd.dataset.columns),
                raw_size_bytes=source.raw_size_bytes,
            )
        except Exception as exc:  # pragma: no cover — defensive
            _logger.warning(
                "state.rehydrate.bad_load_result",
                ds_dir=str(ds_dir),
                error=str(exc)[:200],
            )
            continue

        # Insert directly into the registry with the real dataset_id
        # (the one embedded in the DCD, not a fresh one). Uses a private
        # attribute because the public ``register`` API always mints a
        # new id.
        now = datetime.now(UTC)
        entry = DatasetEntry(
            dataset_id=dcd.dataset.id,
            load_result=load_result,
            status="gold",
            created_at=now,
            updated_at=now,
        )
        state.registry._entries[dcd.dataset.id] = entry
        state.dcds[dcd.dataset.id] = dcd
        state.gold_table_names[dcd.dataset.id] = gold_table_name
        restored += 1

    if restored:
        _logger.info(
            "state.rehydrate.complete",
            datasets_restored=restored,
        )
    return restored
