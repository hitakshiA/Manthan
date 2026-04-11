"""Shared application state for the FastAPI process.

Consolidates the per-process resources every API handler needs: the
dataset registry, a persistent DuckDB connection, the data-directory
path (from :class:`Settings`), and in-memory maps from ``dataset_id`` to
the Data Context Document and Gold table name assigned during
ingestion. The state is created lazily via :func:`get_state` so it is
easy to override in tests using FastAPI's ``dependency_overrides``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import duckdb

from src.core.config import get_settings
from src.core.database import create_connection
from src.ingestion.registry import DatasetRegistry
from src.profiling.clarification import (
    ClarificationAnswer,
    ClarificationQuestion,
)
from src.semantic.schema import DataContextDocument
from src.tools.python_session import PythonSessionManager


@dataclass
class AppState:
    """Per-process state shared across API handlers."""

    registry: DatasetRegistry
    connection: duckdb.DuckDBPyConnection
    data_directory: Path
    dcds: dict[str, DataContextDocument] = field(default_factory=dict)
    gold_table_names: dict[str, str] = field(default_factory=dict)
    clarifications: dict[str, list[ClarificationQuestion]] = field(default_factory=dict)
    clarification_answers: dict[str, list[ClarificationAnswer]] = field(
        default_factory=dict
    )
    dataset_progress: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    python_sessions: PythonSessionManager = field(default_factory=PythonSessionManager)

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
    return AppState(
        registry=DatasetRegistry(),
        connection=create_connection(settings=settings),
        data_directory=data_directory,
    )
