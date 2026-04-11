"""Stateful host-process Python sessions for agent-driven analysis.

Each session is a long-lived ``python -m src.sandbox.repl`` subprocess
that holds a persistent ``globals`` dict. The manager keeps sessions
keyed by a caller-supplied ``session_id`` so an agent can chain
variables across many turns without re-loading data.

## Why a host subprocess instead of Docker

The Docker-based :mod:`src.tools.python_tool` gave us isolation at the
cost of state: every call spun a fresh container. Agents need the
opposite tradeoff — they need to carry a DataFrame across ten tool
calls, build up temp views in one turn and query them in the next,
save a chart after iterating on it. A host subprocess is the simplest
way to get that.

## Security posture

For a hackathon running on a trusted developer machine this is fine.
For a production multi-tenant deployment you would want either per-
session Docker containers (one container for the life of the session)
or a true sandbox like gVisor. We intentionally leave that out of
scope — see SPEC.md §7.3.
"""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.core.exceptions import SandboxError
from src.core.logger import get_logger

_logger = get_logger()

_DEFAULT_TIMEOUT_SECONDS = 60
_DEFAULT_IDLE_TIMEOUT_SECONDS = 30 * 60  # drop sessions idle for 30 min
_BOOTSTRAP_TIMEOUT_SECONDS = 30
_SHUTDOWN_GRACE_SECONDS = 5


@dataclass
class SessionResponse:
    """Structured result of a single ``execute`` call."""

    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    repr: str | None = None
    files_created: list[dict[str, Any]] = field(default_factory=list)
    timed_out: bool = False


class PythonSession:
    """A single long-lived worker with persistent globals.

    Not thread-safe on its own; the :class:`PythonSessionManager`
    serialises calls against the same session via its per-session lock.
    """

    def __init__(
        self,
        *,
        session_id: str,
        dataset_directory: Path,
        output_directory: Path,
    ) -> None:
        self.session_id = session_id
        self.dataset_directory = dataset_directory.resolve()
        self.output_directory = output_directory.resolve()
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._last_used = time.time()

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def last_used(self) -> float:
        return self._last_used

    def start(self) -> None:
        """Spawn the worker subprocess and send the bootstrap request."""
        self.output_directory.mkdir(parents=True, exist_ok=True)
        try:
            self._process = subprocess.Popen(
                [sys.executable, "-m", "src.sandbox.repl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered
            )
        except OSError as exc:
            raise SandboxError(f"Failed to start Python session worker: {exc}") from exc

        assert self._process.stdin is not None
        assert self._process.stdout is not None

        bootstrap = json.dumps(
            {
                "data_dir": str(self.dataset_directory),
                "output_dir": str(self.output_directory),
            }
        )
        try:
            self._process.stdin.write(bootstrap + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._kill()
            raise SandboxError(
                f"Failed to send bootstrap to session worker: {exc}"
            ) from exc

        ready_line = self._read_line(_BOOTSTRAP_TIMEOUT_SECONDS)
        if ready_line is None:
            self._kill()
            raise SandboxError(
                "Session worker did not signal ready within the bootstrap timeout"
            )
        try:
            ack = json.loads(ready_line)
        except json.JSONDecodeError as exc:
            self._kill()
            raise SandboxError(
                f"Session worker returned invalid bootstrap JSON: {exc}"
            ) from exc
        if not ack.get("ready"):
            self._kill()
            raise SandboxError(
                f"Session worker bootstrap failed: {ack.get('error', 'unknown')}"
            )
        _logger.info(
            "sandbox.session_started",
            session_id=self.session_id,
            bootstrapped_files=ack.get("bootstrapped_files", []),
        )

    def execute(
        self,
        code: str,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> SessionResponse:
        """Run ``code`` in the session's persistent globals."""
        with self._lock:
            if not self.alive:
                raise SandboxError(
                    f"Session {self.session_id!r} is not alive; restart required"
                )
            assert self._process is not None
            assert self._process.stdin is not None

            self._last_used = time.time()

            before = _snapshot_output_files(self.output_directory)
            started = time.perf_counter()

            try:
                payload = json.dumps({"code": code}) + "\n"
                self._process.stdin.write(payload)
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._kill()
                raise SandboxError(
                    f"Failed to send code to session worker: {exc}"
                ) from exc

            response_line = self._read_line(timeout_seconds)
            elapsed_ms = (time.perf_counter() - started) * 1000.0

            if response_line is None:
                self._kill()
                return SessionResponse(
                    stdout="",
                    stderr=(
                        f"Session execution exceeded {timeout_seconds}s "
                        "timeout; session has been terminated."
                    ),
                    exit_code=-1,
                    execution_time_ms=round(elapsed_ms, 3),
                    timed_out=True,
                )

            try:
                result = json.loads(response_line)
            except json.JSONDecodeError as exc:
                self._kill()
                raise SandboxError(
                    f"Session worker returned invalid JSON: {exc}; "
                    f"raw={response_line!r}"
                ) from exc

            after = _snapshot_output_files(self.output_directory)
            new_files = _diff_output_files(before, after)

            return SessionResponse(
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                exit_code=int(result.get("exit_code", 0)),
                execution_time_ms=round(elapsed_ms, 3),
                repr=result.get("repr"),
                files_created=new_files,
                timed_out=False,
            )

    def stop(self) -> None:
        """Terminate the worker and release its handles."""
        with self._lock:
            self._kill()

    def _read_line(self, timeout_seconds: float) -> str | None:
        """Read one line from the worker's stdout with a timeout.

        Returns ``None`` if the timeout elapses or the pipe closes.
        """
        if self._process is None or self._process.stdout is None:
            return None
        sel = selectors.DefaultSelector()
        sel.register(self._process.stdout, selectors.EVENT_READ)
        try:
            events = sel.select(timeout_seconds)
        finally:
            sel.unregister(self._process.stdout)
        if not events:
            return None
        line = self._process.stdout.readline()
        if not line:
            return None
        return line

    def _kill(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except Exception:
                pass
        self._process = None


class PythonSessionManager:
    """Per-dataset registry of live :class:`PythonSession` workers."""

    def __init__(
        self,
        *,
        idle_timeout_seconds: float = _DEFAULT_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._sessions: dict[str, PythonSession] = {}
        self._lock = threading.Lock()
        self._idle_timeout_seconds = idle_timeout_seconds

    def get_or_create(
        self,
        *,
        session_id: str | None,
        dataset_directory: Path,
        output_directory: Path,
    ) -> PythonSession:
        """Return the named session, starting it if absent or dead."""
        resolved_id = session_id or f"sess_{uuid4().hex[:12]}"
        with self._lock:
            self._sweep_idle_locked()
            session = self._sessions.get(resolved_id)
            if session is None or not session.alive:
                session = PythonSession(
                    session_id=resolved_id,
                    dataset_directory=dataset_directory,
                    output_directory=output_directory,
                )
                session.start()
                self._sessions[resolved_id] = session
            return session

    def drop(self, session_id: str) -> None:
        """Stop and remove a session by id (no error if absent)."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.stop()

    def list_sessions(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions.keys())

    def shutdown_all(self) -> None:
        """Stop every live session. Called at process exit."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.stop()

    def _sweep_idle_locked(self) -> None:
        """Drop sessions idle longer than the configured timeout."""
        now = time.time()
        stale = [
            sid
            for sid, session in self._sessions.items()
            if now - session.last_used > self._idle_timeout_seconds
        ]
        for sid in stale:
            session = self._sessions.pop(sid, None)
            if session is not None:
                session.stop()
                _logger.info("sandbox.session_idle_swept", session_id=sid)


def _snapshot_output_files(output_directory: Path) -> dict[str, float]:
    """Map relative file path → mtime for everything currently in ``/output``."""
    if not output_directory.exists():
        return {}
    snapshot: dict[str, float] = {}
    for entry in output_directory.rglob("*"):
        if entry.is_file():
            try:
                snapshot[str(entry.relative_to(output_directory))] = (
                    entry.stat().st_mtime
                )
            except OSError:
                continue
    return snapshot


def _diff_output_files(
    before: dict[str, float],
    after: dict[str, float],
) -> list[dict[str, Any]]:
    """Return files created or modified between the two snapshots."""
    diff: list[dict[str, Any]] = []
    for relative, mtime in after.items():
        if relative not in before or before[relative] < mtime:
            diff.append({"name": Path(relative).name, "path": relative, "size": 0})
    return diff


@contextmanager
def ephemeral_manager() -> Iterator[PythonSessionManager]:
    """Yield a session manager that shuts all sessions down on exit."""
    manager = PythonSessionManager()
    try:
        yield manager
    finally:
        manager.shutdown_all()
