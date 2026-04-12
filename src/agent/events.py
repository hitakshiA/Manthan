"""SSE event types for streaming agent output to Layer 3."""

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


def thinking(text: str) -> AgentEvent:
    return AgentEvent(type="thinking", data={"text": text})


def tool_call(name: str, args_preview: str) -> AgentEvent:
    return AgentEvent(type="tool_call", data={"tool": name, "args": args_preview[:200]})


def tool_result(name: str, preview: str) -> AgentEvent:
    return AgentEvent(type="tool_result", data={"tool": name, "preview": preview[:300]})


def waiting_for_user(question_id: str, prompt: str) -> AgentEvent:
    return AgentEvent(
        type="waiting_for_user",
        data={"question_id": question_id, "prompt": prompt[:500]},
    )


def plan_pending(plan_id: str, interpretation: str) -> AgentEvent:
    return AgentEvent(
        type="plan_pending",
        data={"plan_id": plan_id, "interpretation": interpretation[:500]},
    )


def progress(step: int, total: int, description: str) -> AgentEvent:
    return AgentEvent(
        type="progress",
        data={"step": step, "total": total, "description": description},
    )


def done(summary: str, turns: int, mode: str | None = None) -> AgentEvent:
    return AgentEvent(
        type="done",
        data={"summary": summary[:1000], "turns": turns, "mode": mode},
    )


def error(message: str, recoverable: bool = True) -> AgentEvent:
    return AgentEvent(
        type="error",
        data={"message": message[:500], "recoverable": recoverable},
    )
