"""Subagent scopes for multi-agent analysis.

A subagent is an isolated **workspace** — not a second LLM runtime.
Layer 1 owns the scope (its own session_id, its own task list, its
own memory scope, its own Python session); Layer 2 runs the actual
LLM loop inside that scope. This keeps Layer 1 a toolbox without
baking in an agent runtime, while still giving a master agent a
clean way to spread analysis across multiple independent workspaces
without polluting its own context window.

## Lifecycle

```
  spawned ──execute──▶ running ──complete──▶ completed
                              └──fail──▶ failed
```

When a subagent is spawned the store assigns a fresh ``session_id``,
records the parent pointer, and captures the task the subagent was
given. When Layer 2 finishes the subagent's work it calls
``complete`` with a short result summary; the summary can optionally
be written to the parent's memory scope so the master agent picks it
up on its next turn.

## Hierarchy

Subagents can spawn their own subagents. The ``parent_session_id``
field lets a UI render the tree. Depth limits should be enforced by
Layer 2 (this store does not police depth, but does reject cycles).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

SubagentStatus = Literal["spawned", "running", "completed", "failed", "cancelled"]

_VALID_STATUSES: frozenset[str] = frozenset(
    {"spawned", "running", "completed", "failed", "cancelled"}
)


@dataclass
class Subagent:
    """One isolated subagent workspace."""

    id: str
    session_id: str
    parent_session_id: str | None
    dataset_id: str | None
    task: str
    context_hint: str | None
    status: SubagentStatus = "spawned"
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SubagentStore:
    """Thread-safe subagent registry."""

    def __init__(self) -> None:
        self._subagents: dict[str, Subagent] = {}
        self._lock = threading.Lock()

    def spawn(
        self,
        *,
        parent_session_id: str | None,
        dataset_id: str | None,
        task: str,
        context_hint: str | None = None,
    ) -> Subagent:
        subagent_id = f"sub_{uuid4().hex[:10]}"
        session_id = f"sess_sub_{uuid4().hex[:10]}"
        subagent = Subagent(
            id=subagent_id,
            session_id=session_id,
            parent_session_id=parent_session_id,
            dataset_id=dataset_id,
            task=task,
            context_hint=context_hint,
        )
        with self._lock:
            self._subagents[subagent_id] = subagent
        return subagent

    def mark_running(self, subagent_id: str) -> Subagent:
        return self._transition(subagent_id, "running")

    def complete(self, subagent_id: str, *, result: str | None = None) -> Subagent:
        with self._lock:
            sub = self._require(subagent_id)
            sub.status = "completed"
            sub.result = result
            sub.updated_at = datetime.now(UTC)
            return sub

    def fail(self, subagent_id: str, *, error: str) -> Subagent:
        with self._lock:
            sub = self._require(subagent_id)
            sub.status = "failed"
            sub.error = error
            sub.updated_at = datetime.now(UTC)
            return sub

    def cancel(self, subagent_id: str) -> Subagent:
        return self._transition(subagent_id, "cancelled")

    def get(self, subagent_id: str) -> Subagent | None:
        with self._lock:
            return self._subagents.get(subagent_id)

    def list_parent(self, parent_session_id: str) -> list[Subagent]:
        with self._lock:
            subs = [
                s
                for s in self._subagents.values()
                if s.parent_session_id == parent_session_id
            ]
        return sorted(subs, key=lambda s: s.created_at)

    def list_all(self) -> list[Subagent]:
        with self._lock:
            return sorted(self._subagents.values(), key=lambda s: s.created_at)

    def drop(self, subagent_id: str) -> bool:
        with self._lock:
            return self._subagents.pop(subagent_id, None) is not None

    def _transition(self, subagent_id: str, new_status: str) -> Subagent:
        if new_status not in _VALID_STATUSES:
            raise ValueError(f"Invalid subagent status: {new_status}")
        with self._lock:
            sub = self._require(subagent_id)
            sub.status = new_status  # type: ignore[assignment]
            sub.updated_at = datetime.now(UTC)
            return sub

    def _require(self, subagent_id: str) -> Subagent:
        sub = self._subagents.get(subagent_id)
        if sub is None:
            raise KeyError(f"Unknown subagent_id: {subagent_id}")
        return sub
