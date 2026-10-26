"""Audit log endpoint - flat stream of high-signal events across all cases.

Filters down to the events that matter for compliance/transparency review:
  case_opened, policy_matched, human_approved, action_executed, action_failed,
  brief_drafted, case_closed.

Joins to cases for short_id + customer + amount context so the UI doesn't
have to do N round-trips per row.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/audit", tags=["audit"])


AUDIT_TYPES = (
    "case_opened",
    "policy_matched",
    "human_approved",
    "human_hold",
    "action_executed",
    "action_failed",
    "brief_drafted",
    "case_closed",
    "agent_reply",
)


class AuditEvent(BaseModel):
    id: int
    seq: int
    type: str
    actor: str
    data: dict[str, Any]
    summary: str | None
    created_at: str
    case_id: UUID
    case_short_id: str
    customer_ref: str | None
    amount_minor: int | None


@router.get("/recent", response_model=list[AuditEvent])
async def audit_recent(
    ctx: TenantCtx = Depends(get_ctx),
    limit: int = 200,
) -> list[AuditEvent]:
    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""
            SELECT e.id, e.seq, e.type, e.actor, e.data, e.summary, e.created_at,
                   c.id AS case_id, c.short_id AS case_short_id,
                   c.customer_ref, c.amount_minor
            FROM events e
            JOIN cases c ON c.thread_id = e.thread_id AND c.org_id = e.org_id
            WHERE e.org_id = $1
              AND e.type = ANY($2::text[])
            ORDER BY e.created_at DESC
            LIMIT $3
            """,
            ctx.org_id, list(AUDIT_TYPES), limit,
        )
    return [
        AuditEvent(
            id=r["id"],
            seq=r["seq"],
            type=r["type"],
            actor=r["actor"],
            data=r["data"] if isinstance(r["data"], dict) else {},
            summary=r["summary"],
            created_at=r["created_at"].isoformat(),
            case_id=r["case_id"],
            case_short_id=r["case_short_id"],
            customer_ref=r["customer_ref"],
            amount_minor=r["amount_minor"],
        )
        for r in rows
    ]
