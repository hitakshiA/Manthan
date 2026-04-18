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

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

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
    # Entity-slug → dataset_id map. Lets the agent reference a dataset
    # by its stable business-facing slug (``orders``) instead of the
    # UUID-suffixed physical name (``gold_orders_16b49dbd39``). Built
    # from ``dcds`` via :meth:`rebuild_entity_index`, which is called
    # on startup after rehydration and after every successful ingest.
    entity_to_dataset: dict[str, str] = field(default_factory=dict)
    clarifications: dict[str, list[ClarificationQuestion]] = field(default_factory=dict)
    clarification_answers: dict[str, list[ClarificationAnswer]] = field(
        default_factory=dict
    )
    dataset_progress: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    dataset_progress_queues: dict[str, dict[str, object]] = field(
        default_factory=dict
    )
    python_sessions: PythonSessionManager = field(default_factory=PythonSessionManager)
    agent_tasks: AgentTaskStore = field(default_factory=AgentTaskStore)
    ask_user: AskUserRegistry = field(default_factory=AskUserRegistry)
    subagents: SubagentStore = field(default_factory=SubagentStore)
    # Phase 5 — envelope-encrypted credential store for Postgres /
    # Snowflake / BigQuery / GSheets / S3 connections. Created lazily
    # in :func:`get_state`; ``None`` until first use.
    credentials: Any = None  # CredentialVault, defer import to break cycle
    # DuckDB connections are NOT thread-safe. FastAPI runs sync `def`
    # handlers in a ThreadPoolExecutor, so concurrent schema / SQL
    # requests can segfault the native engine. This lock serializes
    # access to ``connection`` across threads. Hold it for the shortest
    # time possible — short lookups only, never full agent turns.
    connection_lock: threading.Lock = field(default_factory=threading.Lock)

    def close(self) -> None:
        """Close the underlying DuckDB connection and shut down sessions."""
        self.python_sessions.shutdown_all()
        with self.connection_lock:
            self.connection.close()

    def connection_execute(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> duckdb.DuckDBPyConnection:
        """Thread-safe wrapper around ``self.connection.execute``.

        Returns the same object as ``connection.execute`` would — the
        relation object — but the DuckDB call itself is serialized.
        Callers should consume the relation (``.fetchall()`` /
        ``.fetchone()``) while still holding the lock when they expect
        to read results. Prefer :meth:`connection_fetchall` /
        :meth:`connection_fetchone` for the common case.
        """
        with self.connection_lock:
            return self.connection.execute(sql, params) if params is not None else self.connection.execute(sql)

    def connection_fetchall(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> list[tuple[Any, ...]]:
        with self.connection_lock:
            rel = (
                self.connection.execute(sql, params)
                if params is not None
                else self.connection.execute(sql)
            )
            return rel.fetchall()

    def connection_fetchone(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> tuple[Any, ...] | None:
        with self.connection_lock:
            rel = (
                self.connection.execute(sql, params)
                if params is not None
                else self.connection.execute(sql)
            )
            return rel.fetchone()

    def rebuild_entity_index(self) -> None:
        """Refresh ``entity_to_dataset`` from the current ``dcds`` map.

        Cheap to call — just walks every DCD and records its entity
        slug. Called after ingest and after rehydration. Collisions
        (two datasets claim the same slug) resolve to the most recent
        ingest.
        """
        index: dict[str, str] = {}
        for dataset_id, dcd in self.dcds.items():
            entity = dcd.dataset.entity
            if entity and entity.slug:
                index[entity.slug] = dataset_id
        self.entity_to_dataset = index

    def resolve_entity(self, slug_or_id: str) -> DataContextDocument | None:
        """Resolve a slug OR a raw dataset_id to its DCD.

        Lets callers accept either identifier without branching. The
        slug path requires the entity index to be populated; if a
        caller hits an empty index, :meth:`rebuild_entity_index`
        should be called first.
        """
        if slug_or_id in self.dcds:
            return self.dcds[slug_or_id]
        dataset_id = self.entity_to_dataset.get(slug_or_id)
        if dataset_id and dataset_id in self.dcds:
            return self.dcds[dataset_id]
        return None


@lru_cache(maxsize=1)
def get_state() -> AppState:
    """Return the cached :class:`AppState` for this process."""
    settings = get_settings()
    data_directory = Path(settings.data_directory)
    data_directory.mkdir(parents=True, exist_ok=True)
    from src.core.credentials import CredentialVault

    state = AppState(
        registry=DatasetRegistry(),
        connection=create_connection(settings=settings),
        data_directory=data_directory,
        memory=MemoryStore(data_directory / "agent_memory.db"),
        plans=PlanStore(data_directory / "plan_audit.db"),
    )
    state.credentials = CredentialVault(data_directory=data_directory)
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
        # Migrate legacy DCDs (v1.0 — no ``entity`` block) in-place.
        # The primary parquet is the Gold table; the remaining parquets
        # are the rollups. We don't re-import the original filename's
        # stem (it isn't recoverable post-sanitization), so we pull it
        # out of the gold table name by stripping the ``gold_`` prefix
        # and the ``_<uuid>`` suffix.
        if dcd.dataset.entity is None or not dcd.dataset.entity.metrics:
            # (a) legacy v1.0 DCD → synthesize the whole entity
            # (b) v1.1 DCD persisted before metric auto-seeding existed →
            #     preserve slug/name/rollups, reseed metrics from columns
            from src.semantic.generator import build_entity

            suffix = dcd.dataset.id[3:]  # strip "ds_"
            stem = gold_table_name
            if stem.startswith("gold_"):
                stem = stem[len("gold_") :]
            if stem.endswith("_" + suffix):
                stem = stem[: -(len(suffix) + 1)]
            summary_tables = [p.stem for p in all_parquets if p.stem != gold_table_name]
            entity = build_entity(
                stem=stem,
                gold_table_name=gold_table_name,
                summary_tables=summary_tables,
                dataset_description=dcd.dataset.description,
                dataset_name=dcd.dataset.name,
                columns=list(dcd.dataset.columns),
            )
            # If the existing entity had a curated slug/name the user
            # picked, preserve them — only the metrics are being seeded.
            if dcd.dataset.entity is not None:
                entity = entity.model_copy(
                    update={
                        "slug": dcd.dataset.entity.slug,
                        "name": dcd.dataset.entity.name,
                        "description": dcd.dataset.entity.description or entity.description,
                    }
                )
            dcd = dcd.model_copy(
                update={"dataset": dcd.dataset.model_copy(update={"entity": entity})}
            )
        state.dcds[dcd.dataset.id] = dcd
        state.gold_table_names[dcd.dataset.id] = gold_table_name
        restored += 1

    state.rebuild_entity_index()

    if restored:
        _logger.info(
            "state.rehydrate.complete",
            datasets_restored=restored,
            entities_indexed=len(state.entity_to_dataset),
        )
    return restored
