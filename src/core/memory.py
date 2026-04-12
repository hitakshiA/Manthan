"""Cross-session persistent memory store.

Layer 2 agents accumulate knowledge across conversations: the business's
definition of 'active user', a user's preferred currency formatting, a
known data-quality caveat, a follow-up analysis from last week. That
knowledge has to survive server restarts so that a follow-up
conversation picks up where the previous one left off — otherwise every
interaction starts cold.

The store is a small SQLite database at
``{data_directory}/agent_memory.db``. Entries are keyed by a
``(scope_type, scope_id, key)`` triple. Scope types:

- ``dataset`` — notes attached to a specific ``ds_*`` id
- ``user`` — preferences for a specific user (opaque id)
- ``global`` — facts that apply to the whole deployment
- ``session`` — ephemeral memory for a single conversation that should
  outlive individual tool calls but not individual sessions; wiped on
  explicit drop

Each entry stores a JSON-encoded value plus a category (preference,
definition, caveat, fact, note) and a free-text description. The
category lets Layer 2 filter when pulling context: ``get all
preferences for user=hitakshi``, ``get all caveats for dataset=ds_x``.

The store is write-through, safe for concurrent access from multiple
FastAPI workers thanks to SQLite's WAL mode.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from src.core.exceptions import ManthanError

ScopeType = Literal["dataset", "user", "global", "session"]
MemoryCategory = Literal["preference", "definition", "caveat", "fact", "note"]

_VALID_SCOPES: frozenset[str] = frozenset({"dataset", "user", "global", "session"})
_VALID_CATEGORIES: frozenset[str] = frozenset(
    {"preference", "definition", "caveat", "fact", "note"}
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    scope_type TEXT NOT NULL,
    scope_id   TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    category   TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope_type, scope_id, key)
);

CREATE INDEX IF NOT EXISTS idx_memory_scope
    ON memory (scope_type, scope_id);

CREATE INDEX IF NOT EXISTS idx_memory_category
    ON memory (scope_type, scope_id, category);
"""


class MemoryError(ManthanError):
    """Raised when a memory operation fails."""


@dataclass(frozen=True)
class MemoryEntry:
    """One row from the memory store."""

    scope_type: ScopeType
    scope_id: str
    key: str
    value: Any
    category: MemoryCategory
    description: str | None
    created_at: datetime
    updated_at: datetime


class MemoryStore:
    """SQLite-backed cross-session memory."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._lock = threading.Lock()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            str(self._database_path), isolation_level=None, timeout=10.0
        )
        try:
            yield conn
        finally:
            conn.close()

    def put(
        self,
        *,
        scope_type: str,
        scope_id: str,
        key: str,
        value: Any,
        category: str = "note",
        description: str | None = None,
    ) -> MemoryEntry:
        """Insert or update a memory entry."""
        _validate_scope(scope_type)
        _validate_category(category)
        _validate_key(key)

        now = datetime.now(UTC)
        now_iso = now.isoformat()
        value_json = json.dumps(value, default=str)

        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "SELECT created_at FROM memory "
                "WHERE scope_type = ? AND scope_id = ? AND key = ?",
                (scope_type, scope_id, key),
            )
            row = cursor.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO memory "
                    "(scope_type, scope_id, key, value, category, "
                    " description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        scope_type,
                        scope_id,
                        key,
                        value_json,
                        category,
                        description,
                        now_iso,
                        now_iso,
                    ),
                )
                created_at = now
            else:
                conn.execute(
                    "UPDATE memory SET value = ?, category = ?, "
                    "description = ?, updated_at = ? "
                    "WHERE scope_type = ? AND scope_id = ? AND key = ?",
                    (
                        value_json,
                        category,
                        description,
                        now_iso,
                        scope_type,
                        scope_id,
                        key,
                    ),
                )
                created_at = _parse_iso(row[0])

        return MemoryEntry(
            scope_type=scope_type,  # type: ignore[arg-type]
            scope_id=scope_id,
            key=key,
            value=value,
            category=category,  # type: ignore[arg-type]
            description=description,
            created_at=created_at,
            updated_at=now,
        )

    def get(self, *, scope_type: str, scope_id: str, key: str) -> MemoryEntry | None:
        """Return one entry, or ``None`` if absent."""
        _validate_scope(scope_type)
        _validate_key(key)

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT scope_type, scope_id, key, value, category, "
                "       description, created_at, updated_at "
                "FROM memory "
                "WHERE scope_type = ? AND scope_id = ? AND key = ?",
                (scope_type, scope_id, key),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def delete(self, *, scope_type: str, scope_id: str, key: str) -> bool:
        """Delete one entry. Returns ``True`` iff something was removed."""
        _validate_scope(scope_type)
        _validate_key(key)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM memory WHERE scope_type = ? AND scope_id = ? AND key = ?",
                (scope_type, scope_id, key),
            )
            return cursor.rowcount > 0

    def list_scope(
        self,
        *,
        scope_type: str,
        scope_id: str,
        category: str | None = None,
    ) -> list[MemoryEntry]:
        """Return every entry in a scope, optionally filtered by category."""
        _validate_scope(scope_type)
        if category is not None:
            _validate_category(category)

        with self._connect() as conn:
            if category is None:
                cursor = conn.execute(
                    "SELECT scope_type, scope_id, key, value, category, "
                    "       description, created_at, updated_at "
                    "FROM memory "
                    "WHERE scope_type = ? AND scope_id = ? "
                    "ORDER BY updated_at DESC",
                    (scope_type, scope_id),
                )
            else:
                cursor = conn.execute(
                    "SELECT scope_type, scope_id, key, value, category, "
                    "       description, created_at, updated_at "
                    "FROM memory "
                    "WHERE scope_type = ? AND scope_id = ? AND category = ? "
                    "ORDER BY updated_at DESC",
                    (scope_type, scope_id, category),
                )
            rows = cursor.fetchall()
        return [_row_to_entry(row) for row in rows]

    def search(self, *, query: str, scope_type: str | None = None) -> list[MemoryEntry]:
        """Return entries whose key or description contains ``query``."""
        needle = f"%{query.lower()}%"
        with self._connect() as conn:
            if scope_type is None:
                cursor = conn.execute(
                    "SELECT scope_type, scope_id, key, value, category, "
                    "       description, created_at, updated_at "
                    "FROM memory "
                    "WHERE LOWER(key) LIKE ? OR LOWER(description) LIKE ? "
                    "ORDER BY updated_at DESC LIMIT 100",
                    (needle, needle),
                )
            else:
                _validate_scope(scope_type)
                cursor = conn.execute(
                    "SELECT scope_type, scope_id, key, value, category, "
                    "       description, created_at, updated_at "
                    "FROM memory "
                    "WHERE scope_type = ? "
                    "  AND (LOWER(key) LIKE ? OR LOWER(description) LIKE ?) "
                    "ORDER BY updated_at DESC LIMIT 100",
                    (scope_type, needle, needle),
                )
            rows = cursor.fetchall()
        return [_row_to_entry(row) for row in rows]

    def drop_scope(self, *, scope_type: str, scope_id: str) -> int:
        """Delete every entry in a scope. Returns count deleted."""
        _validate_scope(scope_type)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM memory WHERE scope_type = ? AND scope_id = ?",
                (scope_type, scope_id),
            )
            return cursor.rowcount

    def close(self) -> None:
        """No-op; each call opens a fresh connection via ``_connect``."""


def _row_to_entry(row: tuple[Any, ...]) -> MemoryEntry:
    return MemoryEntry(
        scope_type=row[0],
        scope_id=row[1],
        key=row[2],
        value=json.loads(row[3]),
        category=row[4],
        description=row[5],
        created_at=_parse_iso(row[6]),
        updated_at=_parse_iso(row[7]),
    )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _validate_scope(scope_type: str) -> None:
    if scope_type not in _VALID_SCOPES:
        raise MemoryError(
            f"Invalid scope_type {scope_type!r}; must be one of {sorted(_VALID_SCOPES)}"
        )


def _validate_category(category: str) -> None:
    if category not in _VALID_CATEGORIES:
        raise MemoryError(
            f"Invalid category {category!r}; must be one of {sorted(_VALID_CATEGORIES)}"
        )


def _validate_key(key: str) -> None:
    if not isinstance(key, str) or not key:
        raise MemoryError("Memory key must be a non-empty string")
    if len(key) > 256:
        raise MemoryError("Memory key exceeds maximum length of 256")
