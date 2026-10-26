"""Action adapters - the write-side of the agent.

Each adapter takes a `payload: dict` from a DraftedAction and performs
the real-world write. Returns ExecutionResult on success or raises.

Idempotency is enforced by the Action Executor via an idempotency_key
column on the `actions` table. Adapters must accept and honour an
`idempotency_key` parameter where the upstream API supports it (Stripe
does; Resend, Notion, Linear, Slack don't - for those the executor
checks the actions table before calling).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ExecutionResult:
    """Returned by every adapter on success."""

    external_ref: str           # e.g. "re_xxx" from Stripe
    summary: str                # 1-line for the audit log
    raw: dict[str, Any] | None = None


class AdapterError(Exception):
    """Raised by adapters when the write fails (after retries)."""
