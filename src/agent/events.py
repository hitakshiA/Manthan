"""SSE event types for streaming agent output to Layer 3.

Every decision point in the agent loop emits an event. Layer 3
renders these as a live activity feed — the user sees exactly
what the agent is doing, thinking, and waiting on at all times.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


class AgentEvent(BaseModel):
    """One SSE event emitted during the agent loop."""

    type: str
    data: dict[str, Any]

    def to_sse(self) -> str:
        return f"data: {json.dumps({'type': self.type, **self.data})}\n\n"


# ── Lifecycle events ──


def session_start(session_id: str, dataset_id: str, model: str) -> AgentEvent:
    return AgentEvent(
        type="session_start",
        data={
            "session_id": session_id,
            "dataset_id": dataset_id,
            "model": model,
        },
    )


def done(
    summary: str,
    turns: int,
    tool_calls: int = 0,
    elapsed: float = 0.0,
    mode: str | None = None,
    render_spec: dict[str, Any] | None = None,
) -> AgentEvent:
    return AgentEvent(
        type="done",
        data={
            "summary": summary[:2000],
            "turns": turns,
            "tool_calls": tool_calls,
            "elapsed_seconds": round(elapsed, 2),
            "mode": mode,
            "render_spec": render_spec,
        },
    )


def error(message: str, recoverable: bool = True) -> AgentEvent:
    return AgentEvent(
        type="error",
        data={"message": message[:500], "recoverable": recoverable},
    )


# ── Discovery events (before the loop starts) ──


def discovering_tables(dataset_id: str) -> AgentEvent:
    return AgentEvent(
        type="discovering_tables",
        data={"dataset_id": dataset_id, "status": "scanning"},
    )


def tables_found(table_names: list[str], total: int) -> AgentEvent:
    return AgentEvent(
        type="tables_found",
        data={
            "tables": table_names[:20],
            "total": total,
        },
    )


def loading_schema(dataset_id: str) -> AgentEvent:
    return AgentEvent(
        type="loading_schema",
        data={"dataset_id": dataset_id},
    )


def checking_memory(dataset_id: str) -> AgentEvent:
    return AgentEvent(
        type="checking_memory",
        data={"dataset_id": dataset_id},
    )


def memory_found(count: int) -> AgentEvent:
    return AgentEvent(
        type="memory_found",
        data={"prior_analyses": count},
    )


# ── Thinking events ──


def thinking(text: str) -> AgentEvent:
    return AgentEvent(
        type="thinking",
        data={"text": text[:500]},
    )


def deciding_gate(gate: str, decision: str, reason: str) -> AgentEvent:
    """Agent passed through a decision gate."""
    return AgentEvent(
        type="deciding",
        data={
            "gate": gate,
            "decision": decision,
            "reason": reason[:200],
        },
    )


# ── Tool events ──


def tool_start(name: str, args: dict[str, Any], turn: int) -> AgentEvent:
    return AgentEvent(
        type="tool_start",
        data={
            "tool": name,
            "turn": turn,
            "args_preview": _preview_args(name, args),
        },
    )


def tool_complete(name: str, preview: str, elapsed_ms: float) -> AgentEvent:
    return AgentEvent(
        type="tool_complete",
        data={
            "tool": name,
            "preview": preview[:400],
            "elapsed_ms": round(elapsed_ms, 1),
        },
    )


def tool_error(name: str, error_msg: str, will_retry: bool) -> AgentEvent:
    return AgentEvent(
        type="tool_error",
        data={
            "tool": name,
            "error": error_msg[:300],
            "will_retry": will_retry,
        },
    )


# ── Human-in-the-loop events ──


def waiting_for_user(question_id: str, prompt: str, options: list[str]) -> AgentEvent:
    return AgentEvent(
        type="waiting_for_user",
        data={
            "question_id": question_id,
            "prompt": prompt[:500],
            "options": options[:10],
        },
    )


def user_answered(answer: str) -> AgentEvent:
    return AgentEvent(
        type="user_answered",
        data={"answer": answer[:300]},
    )


# ── Plan events ──


def plan_created(plan_id: str, interpretation: str, steps: int) -> AgentEvent:
    return AgentEvent(
        type="plan_created",
        data={
            "plan_id": plan_id,
            "interpretation": interpretation[:300],
            "steps": steps,
        },
    )


def plan_pending(plan_id: str, interpretation: str) -> AgentEvent:
    return AgentEvent(
        type="plan_pending",
        data={
            "plan_id": plan_id,
            "interpretation": interpretation[:500],
        },
    )


def plan_approved(plan_id: str) -> AgentEvent:
    return AgentEvent(
        type="plan_approved",
        data={"plan_id": plan_id},
    )


# ── Progress events ──


def progress(step: int, total: int, description: str) -> AgentEvent:
    return AgentEvent(
        type="progress",
        data={
            "step": step,
            "total": total,
            "description": description[:200],
        },
    )


def turn_complete(turn: int, tools_used: list[str]) -> AgentEvent:
    return AgentEvent(
        type="turn_complete",
        data={"turn": turn, "tools_used": tools_used},
    )


# ── Subagent events ──


def subagent_spawned(subagent_id: str, task: str) -> AgentEvent:
    return AgentEvent(
        type="subagent_spawned",
        data={
            "subagent_id": subagent_id,
            "task": task[:200],
        },
    )


def subagent_complete(subagent_id: str, result_preview: str) -> AgentEvent:
    return AgentEvent(
        type="subagent_complete",
        data={
            "subagent_id": subagent_id,
            "result": result_preview[:300],
        },
    )


# ── Helpers ──


def _preview_args(name: str, args: dict[str, Any]) -> str:
    """Human-readable preview of tool arguments."""
    if name == "run_sql":
        return args.get("sql", "")[:150]
    if name == "run_python":
        code = args.get("code", "")
        first_line = code.split("\n")[0] if code else ""
        return f"{first_line}... ({len(code)} chars)"
    if name == "ask_user":
        return args.get("prompt", "")[:150]
    if name == "create_plan":
        return args.get("interpretation", "")[:150]
    return json.dumps(args)[:150]
