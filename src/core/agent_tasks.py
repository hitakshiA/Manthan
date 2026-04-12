"""Per-session agent task store.

A small in-memory registry of tasks the agent is working on during a
conversation. Scoped to a ``session_id`` so a master agent and its
subagents each track their own plans independently. Unlike the cross-
session :mod:`src.core.memory` store, this one does not persist across
restarts — tasks are ephemeral to the agent's working set.

The agent uses this to:

- Decompose a complex question into sub-tasks at plan time
- Mark each sub-task ``in_progress`` before executing
- Record results as ``completed`` so a later turn can pick up where it
  left off
- Track ``depends_on`` edges for sequential plans
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

TaskStatus = Literal["pending", "in_progress", "completed", "cancelled"]

_VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "in_progress", "completed", "cancelled"}
)


@dataclass
class AgentTask:
    """One task in the agent's working set."""

    id: str
    session_id: str
    title: str
    description: str
    status: TaskStatus = "pending"
    depends_on: list[str] = field(default_factory=list)
    result: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AgentTaskStore:
    """Thread-safe per-session task list."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        session_id: str,
        title: str,
        description: str,
        depends_on: list[str] | None = None,
    ) -> AgentTask:
        task = AgentTask(
            id=f"task_{uuid4().hex[:10]}",
            session_id=session_id,
            title=title,
            description=description,
            depends_on=list(depends_on or []),
        )
        with self._lock:
            self._tasks[task.id] = task
        return task

    def update(
        self,
        task_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        description: str | None = None,
        result: str | None = None,
    ) -> AgentTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Unknown task_id: {task_id}")
            if status is not None:
                if status not in _VALID_STATUSES:
                    raise ValueError(
                        f"Invalid status {status!r}; must be one of "
                        f"{sorted(_VALID_STATUSES)}"
                    )
                task.status = status  # type: ignore[assignment]
            if title is not None:
                task.title = title
            if description is not None:
                task.description = description
            if result is not None:
                task.result = result
            task.updated_at = datetime.now(UTC)
            return task

    def get(self, task_id: str) -> AgentTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_session(self, session_id: str) -> list[AgentTask]:
        with self._lock:
            tasks = [t for t in self._tasks.values() if t.session_id == session_id]
        return sorted(tasks, key=lambda t: t.created_at)

    def delete(self, task_id: str) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def drop_session(self, session_id: str) -> int:
        with self._lock:
            to_remove = [
                tid for tid, t in self._tasks.items() if t.session_id == session_id
            ]
            for tid in to_remove:
                del self._tasks[tid]
            return len(to_remove)
