"""Event store + thread state.

For v0 this is an in-memory store. The shape mirrors the locked Postgres
schema in the engineering plan, so swapping to Postgres later is a
drop-in (replace EventStore with an async ORM-backed version).

The event log is the single source of truth. Case state (current step,
retry count, what's been tried) is derived from the log, not stored
separately. This is the 12-Factor Agents pattern (#3 + #5).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .types import Event


class EventStore:
    """Append-only event log, keyed by case_id.

    Replace with a Postgres-backed implementation when we add the
    `events` table from the engineering plan. The interface stays
    identical.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[Event]] = {}

    def append(
        self,
        case_id: str,
        kind: str,
        actor: str,
        data: dict[str, Any],
        *,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> Event:
        """Append one event. Auto-assigns the next seq number."""
        events = self._events.setdefault(case_id, [])
        evt = Event(
            case_id=case_id,
            seq=len(events),
            kind=kind,  # type: ignore[arg-type]
            actor=actor,
            data=data,
            ts=datetime.utcnow(),
            trace_id=trace_id,
            span_id=span_id,
        )
        events.append(evt)
        return evt

    def list_for_case(self, case_id: str) -> list[Event]:
        return list(self._events.get(case_id, []))

    def filter_for_case(
        self, case_id: str, kinds: Iterable[str]
    ) -> list[Event]:
        kinds_set = set(kinds)
        return [e for e in self._events.get(case_id, []) if e.kind in kinds_set]

    def all_cases(self) -> list[str]:
        return list(self._events.keys())


# ──────────────────────────────────────────────────────────────────────
# Thread serializer - turns events into an LLM-readable prompt
# ──────────────────────────────────────────────────────────────────────


def events_to_messages(events: list[Event]) -> list[dict[str, Any]]:
    """Serialize an event log into OpenAI-shape chat messages.

    Each event becomes one message. Tool calls and tool results get
    paired by id so the model can follow the trace. This is the
    XML-tagged-event pattern from 12-Factor #3, adapted to OpenAI's
    chat format.

    Caller appends the SYSTEM prompt at the front before sending.
    """
    messages: list[dict[str, Any]] = []
    for e in events:
        match e.kind:
            case "case_opened":
                trigger = e.data
                txt = f"<case_opened>\n{_yaml_like(trigger)}\n</case_opened>"
                messages.append({"role": "user", "content": txt})

            case "agent_thought":
                # The model's own reasoning, replayed as an assistant turn.
                messages.append({"role": "assistant", "content": e.data.get("text", "")})

            case "tool_call":
                # OpenAI-shape tool call. seq number doubles as the call ID.
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": e.data["id"],
                                "type": "function",
                                "function": {
                                    "name": e.data["name"],
                                    "arguments": json.dumps(e.data.get("arguments", {})),
                                },
                            }
                        ],
                    }
                )

            case "tool_result":
                # Pair to the tool_call by id.
                content = json.dumps(e.data.get("result", {}), default=str)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": e.data["tool_call_id"],
                        "content": content,
                    }
                )

            case "finding_recorded":
                txt = f"<finding idx={e.data['idx']} confidence={e.data['confidence']}>{e.data['text']} (cites: {e.data['citations']})</finding>"
                messages.append({"role": "assistant", "content": txt})

            case "reflexion":
                txt = f"<reflexion>{e.data.get('verdict', '')}: {e.data.get('reasoning', '')}</reflexion>"
                messages.append({"role": "assistant", "content": txt})

            case "human_response":
                # Human typed a free-form message (the "respond" decision type).
                surface = e.data.get("surface", "unknown")
                txt = f"<human_message from={surface}>{e.data['text']}</human_message>"
                messages.append({"role": "user", "content": txt})

            case _:
                # Other event kinds aren't directly prompt-relevant (case_closed,
                # action_fired, etc.). Skip them; the audit log keeps them.
                pass

    return messages


def _yaml_like(d: dict[str, Any], indent: int = 0) -> str:
    """Lightweight YAML-ish renderer for the trigger payload.

    Avoids YAML lib dependency in this file; the LLM reads it fine.
    """
    lines: list[str] = []
    pad = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            lines.append(_yaml_like(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{pad}{k}:")
            for item in v:
                if isinstance(item, dict):
                    lines.append(f"{pad}- ")
                    lines.append(_yaml_like(item, indent + 1))
                else:
                    lines.append(f"{pad}  - {item}")
        else:
            lines.append(f"{pad}{k}: {v}")
    return "\n".join(lines)
