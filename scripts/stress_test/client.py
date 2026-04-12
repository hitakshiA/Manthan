"""Thin HTTP client for the Layer 1 stress test harness.

Not an agent — just typed wrappers around the Manthan REST API so the
test harness can call primitives without writing curl strings. The
agent reasoning loop (me) calls these helpers and decides what to do
next based on the responses.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8000"
ARTIFACTS_ROOT = Path("docs/stress_test_artifacts")


@dataclass
class TraceEntry:
    method: str
    path: str
    request: dict[str, Any] | None
    status: int
    response: Any
    elapsed_ms: float


@dataclass
class Trace:
    """Append-only HTTP trace written to JSONL per scenario."""

    cell_id: str
    entries: list[TraceEntry] = field(default_factory=list)

    def append(self, entry: TraceEntry) -> None:
        self.entries.append(entry)

    def write(self) -> Path:
        out = ARTIFACTS_ROOT / "traces" / f"{self.cell_id}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as f:
            for e in self.entries:
                f.write(
                    json.dumps(
                        {
                            "method": e.method,
                            "path": e.path,
                            "request": e.request,
                            "status": e.status,
                            "response": e.response,
                            "elapsed_ms": round(e.elapsed_ms, 1),
                        }
                    )
                    + "\n"
                )
        return out


class L1Client:
    """Typed helpers for Manthan Layer 1 endpoints."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 900.0,
        trace: Trace | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._trace = trace

    def __enter__(self) -> L1Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    # ---------------------------- internals -------------------------------

    def _record(
        self,
        method: str,
        path: str,
        request: Any,
        response: httpx.Response,
        elapsed_ms: float,
    ) -> None:
        if self._trace is None:
            return
        try:
            body: Any = response.json()
        except Exception:
            body = response.text[:4000]
        self._trace.append(
            TraceEntry(
                method=method,
                path=path,
                request=request if isinstance(request, dict) else None,
                status=response.status_code,
                response=body,
                elapsed_ms=elapsed_ms,
            )
        )

    def _timed(
        self, method: str, path: str, *, json_body: Any = None, params: Any = None
    ) -> httpx.Response:
        t0 = time.perf_counter()
        r = self._client.request(method, path, json=json_body, params=params)
        dt = (time.perf_counter() - t0) * 1000.0
        self._record(method, path, json_body or params, r, dt)
        return r

    # ---------------------------- datasets --------------------------------

    def upload_single(self, path: Path) -> dict[str, Any]:
        t0 = time.perf_counter()
        with path.open("rb") as f:
            r = self._client.post(
                "/datasets/upload",
                files={"file": (path.name, f, "application/octet-stream")},
            )
        dt = (time.perf_counter() - t0) * 1000.0
        self._record("POST", "/datasets/upload", {"file": path.name}, r, dt)
        r.raise_for_status()
        return r.json()

    def upload_multi(self, paths: list[Path]) -> dict[str, Any]:
        t0 = time.perf_counter()
        handles = [(p.name, p.open("rb"), "application/octet-stream") for p in paths]
        try:
            files = [("files", h) for h in handles]
            r = self._client.post("/datasets/upload-multi", files=files)
        finally:
            for _, fh, _ in handles:
                fh.close()
        dt = (time.perf_counter() - t0) * 1000.0
        self._record(
            "POST",
            "/datasets/upload-multi",
            {"files": [p.name for p in paths]},
            r,
            dt,
        )
        r.raise_for_status()
        return r.json()

    def get_context(self, dataset_id: str, query: str | None = None) -> tuple[int, str]:
        params = {"query": query} if query else None
        t0 = time.perf_counter()
        r = self._client.get(f"/datasets/{dataset_id}/context", params=params)
        dt = (time.perf_counter() - t0) * 1000.0
        self._record("GET", f"/datasets/{dataset_id}/context", params, r, dt)
        return r.status_code, r.text

    def get_schema(self, dataset_id: str) -> dict[str, Any]:
        r = self._timed("GET", f"/datasets/{dataset_id}/schema")
        r.raise_for_status()
        return r.json()

    def list_datasets(self) -> list[dict[str, Any]]:
        r = self._timed("GET", "/datasets")
        r.raise_for_status()
        return r.json()

    # ---------------------------- tools -----------------------------------

    def run_sql(
        self, dataset_id: str, sql: str, max_rows: int = 1000
    ) -> dict[str, Any]:
        r = self._timed(
            "POST",
            "/tools/sql",
            json_body={"dataset_id": dataset_id, "sql": sql, "max_rows": max_rows},
        )
        r.raise_for_status()
        return r.json()

    def run_python(
        self,
        dataset_id: str,
        code: str,
        session_id: str | None = None,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "dataset_id": dataset_id,
            "code": code,
            "timeout_seconds": timeout_seconds,
        }
        if session_id:
            body["session_id"] = session_id
        r = self._timed("POST", "/tools/python", json_body=body)
        r.raise_for_status()
        return r.json()

    # ---------------------------- plans -----------------------------------

    def create_plan(
        self,
        *,
        session_id: str,
        dataset_id: str | None,
        user_question: str,
        interpretation: str,
        citations: list[dict[str, str]],
        steps: list[dict[str, Any]],
        expected_cost: dict[str, int] | None = None,
        risks: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "session_id": session_id,
            "dataset_id": dataset_id,
            "user_question": user_question,
            "interpretation": interpretation,
            "citations": citations,
            "steps": steps,
            "expected_cost": expected_cost or {},
            "risks": risks or [],
        }
        r = self._timed("POST", "/plans", json_body=body)
        r.raise_for_status()
        return r.json()

    def submit_plan(self, plan_id: str) -> dict[str, Any]:
        r = self._timed("POST", f"/plans/{plan_id}/submit")
        r.raise_for_status()
        return r.json()

    def approve_plan(self, plan_id: str, actor: str | None = None) -> dict[str, Any]:
        r = self._timed("POST", f"/plans/{plan_id}/approve", json_body={"actor": actor})
        r.raise_for_status()
        return r.json()

    def wait_plan(self, plan_id: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        r = self._timed(
            "POST",
            f"/plans/{plan_id}/wait",
            params={"timeout_seconds": timeout_seconds},
        )
        r.raise_for_status()
        return r.json()

    def plan_start(self, plan_id: str) -> dict[str, Any]:
        r = self._timed("POST", f"/plans/{plan_id}/execute_start")
        r.raise_for_status()
        return r.json()

    def plan_done(
        self, plan_id: str, success: bool = True, note: str | None = None
    ) -> dict[str, Any]:
        r = self._timed(
            "POST",
            f"/plans/{plan_id}/execute_done",
            json_body={"success": success, "note": note},
        )
        r.raise_for_status()
        return r.json()

    def audit_plan(self, plan_id: str) -> dict[str, Any]:
        r = self._timed("GET", f"/plans/{plan_id}/audit")
        r.raise_for_status()
        return r.json()

    # ---------------------------- ask_user --------------------------------

    def ask_user(
        self,
        *,
        session_id: str,
        prompt: str,
        options: list[str] | None = None,
        allow_free_text: bool = True,
        context: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "session_id": session_id,
            "prompt": prompt,
            "options": options or [],
            "allow_free_text": allow_free_text,
            "context": context,
        }
        r = self._timed("POST", "/ask_user", json_body=body)
        r.raise_for_status()
        return r.json()

    def wait_ask_user(
        self, question_id: str, timeout_seconds: float = 60.0
    ) -> dict[str, Any]:
        r = self._timed(
            "POST",
            f"/ask_user/{question_id}/wait",
            params={"timeout_seconds": timeout_seconds},
        )
        r.raise_for_status()
        return r.json()

    def answer_question(self, question_id: str, answer: str) -> dict[str, Any]:
        r = self._timed(
            "POST", f"/ask_user/{question_id}/answer", json_body={"answer": answer}
        )
        r.raise_for_status()
        return r.json()

    # ---------------------------- memory ----------------------------------

    def memory_put(
        self,
        *,
        scope_type: str,
        scope_id: str,
        key: str,
        value: Any,
        category: str = "note",
        description: str | None = None,
    ) -> dict[str, Any]:
        r = self._timed(
            "POST",
            "/memory",
            json_body={
                "scope_type": scope_type,
                "scope_id": scope_id,
                "key": key,
                "value": value,
                "category": category,
                "description": description,
            },
        )
        r.raise_for_status()
        return r.json()

    def memory_get(
        self, scope_type: str, scope_id: str, key: str
    ) -> dict[str, Any] | None:
        r = self._timed("GET", f"/memory/{scope_type}/{scope_id}/{key}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def memory_search(
        self, query: str, scope_type: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"query": query}
        if scope_type:
            params["scope_type"] = scope_type
        r = self._timed("GET", "/memory/search/", params=params)
        r.raise_for_status()
        return r.json()

    # ---------------------------- tasks -----------------------------------

    def task_create(
        self,
        *,
        session_id: str,
        title: str,
        description: str,
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        r = self._timed(
            "POST",
            "/tasks",
            json_body={
                "session_id": session_id,
                "title": title,
                "description": description,
                "depends_on": depends_on or [],
            },
        )
        r.raise_for_status()
        return r.json()

    def task_update(
        self, task_id: str, *, status: str | None = None, result: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if status is not None:
            body["status"] = status
        if result is not None:
            body["result"] = result
        r = self._timed("POST", f"/tasks/{task_id}/update", json_body=body)
        r.raise_for_status()
        return r.json()

    # ---------------------------- subagents -------------------------------

    def spawn_subagent(
        self,
        *,
        parent_session_id: str | None,
        dataset_id: str | None,
        task: str,
        context_hint: str | None = None,
    ) -> dict[str, Any]:
        r = self._timed(
            "POST",
            "/subagents/spawn",
            json_body={
                "parent_session_id": parent_session_id,
                "dataset_id": dataset_id,
                "task": task,
                "context_hint": context_hint,
            },
        )
        r.raise_for_status()
        return r.json()

    def subagent_running(self, subagent_id: str) -> dict[str, Any]:
        r = self._timed("POST", f"/subagents/{subagent_id}/running")
        r.raise_for_status()
        return r.json()

    def complete_subagent(
        self,
        subagent_id: str,
        *,
        result: str,
        write_to_parent_memory: bool = True,
        memory_key: str | None = None,
    ) -> dict[str, Any]:
        r = self._timed(
            "POST",
            f"/subagents/{subagent_id}/complete",
            json_body={
                "result": result,
                "write_to_parent_memory": write_to_parent_memory,
                "memory_key": memory_key,
            },
        )
        r.raise_for_status()
        return r.json()
