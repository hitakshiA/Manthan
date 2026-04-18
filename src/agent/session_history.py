"""Per-session chat history for the agent loop.

The agent is stateless across requests — a fresh ``ManthanAgent`` is
constructed for every ``/agent/query`` call. This module keeps the LLM
conversation transcript keyed by ``session_id`` so follow-up questions
(typed or fired by follow-up chips) answer with full awareness of what
the exec already asked and what was reported back.

Scope:
- In-memory write-through cache backed by per-session JSON files in
  ``data/session_history/``. Survives a backend crash or supervisor
  restart — the user keeps their conversation.
- Capped to the last N messages *per session* to bound context size.
  Trimming preserves the invariant that every ``tool`` message is
  preceded by the ``assistant`` message whose ``tool_calls`` it
  satisfies.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

# Upper bound on messages kept per session. One "turn" is typically
# user → assistant(content + tool_calls) → N×tool → assistant(summary),
# so 200 holds roughly 30–40 turns of back-and-forth — enough for a
# long exec session without running away on OpenRouter context.
_MAX_MESSAGES_PER_SESSION = 200

_log = logging.getLogger(__name__)

_histories: dict[str, list[dict[str, Any]]] = {}
_lock = Lock()


def _store_dir() -> Path:
    """Resolve the on-disk store directory lazily so tests can override."""
    try:
        from src.core.config import get_settings

        base = Path(get_settings().data_directory)
    except Exception:
        base = Path("data")
    d = base / "session_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_file(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_id)[
        :128
    ]
    return _store_dir() / f"{safe}.json"


def _load_from_disk(session_id: str) -> list[dict[str, Any]]:
    path = _session_file(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception as exc:  # corrupt file — don't crash, just reset
        _log.warning("session_history: ignoring corrupt %s (%s)", path, exc)
    return []


def _persist(session_id: str, messages: list[dict[str, Any]]) -> None:
    path = _session_file(session_id)
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(messages), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        _log.warning("session_history: failed to persist %s (%s)", path, exc)


def get_history(session_id: str) -> list[dict[str, Any]]:
    """Return a copy of the stored messages for a session.

    Falls back to the on-disk file when the in-memory cache is cold
    (e.g. immediately after a backend restart).
    """
    with _lock:
        cached = _histories.get(session_id)
        if cached is not None:
            return list(cached)
    # Cache miss — fall through to disk (outside the lock so we don't
    # hold it during I/O)
    loaded = _load_from_disk(session_id)
    with _lock:
        _histories.setdefault(session_id, loaded)
        return list(_histories[session_id])


def set_history(session_id: str, messages: list[dict[str, Any]]) -> None:
    """Replace the stored messages for a session, trimmed to the cap."""
    trimmed = _trim(messages)
    with _lock:
        _histories[session_id] = trimmed
    _persist(session_id, trimmed)


def clear(session_id: str) -> None:
    with _lock:
        _histories.pop(session_id, None)
    path = _session_file(session_id)
    if path.exists():
        with contextlib.suppress(Exception):
            path.unlink()


def _trim(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(messages) <= _MAX_MESSAGES_PER_SESSION:
        return list(messages)

    start = len(messages) - _MAX_MESSAGES_PER_SESSION
    # Advance `start` until we're not cutting into a tool-call chain.
    # A safe boundary is a "user" message, or an "assistant" message
    # that has no tool_calls.
    while start < len(messages):
        m = messages[start]
        role = m.get("role")
        if role == "user":
            break
        if role == "assistant" and not m.get("tool_calls"):
            break
        start += 1
    return list(messages[start:])
