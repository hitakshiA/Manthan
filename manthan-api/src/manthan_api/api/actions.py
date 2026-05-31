"""Approve / hold / chat - the HITL surface endpoints."""

from __future__ import annotations

import uuid
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/cases", tags=["actions"])


# ──────────────────────────────────────────────────────────────────────
# POST /api/cases/{id}/approve  - flip drafted actions to approved
# ──────────────────────────────────────────────────────────────────────


class ApprovePayload(BaseModel):
    action_ids: list[UUID] | None = Field(
        default=None,
        description="Optional: specific action ids. Default = approve all drafted.",
    )


class ApprovedAction(BaseModel):
    id: UUID
    kind: str
    status: str


class ApproveResponse(BaseModel):
    approved: list[ApprovedAction]
    case_id: UUID


@router.post("/{case_id}/approve", response_model=ApproveResponse)
async def approve_case(
    case_id: UUID,
    body: ApprovePayload,
    ctx: TenantCtx = Depends(get_ctx),
) -> ApproveResponse:
    """Mark drafted actions approved so the Action Executor will fire them."""
    async with get_conn() as conn:
        case_exists = await conn.fetchval(
            "SELECT 1 FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
        if not case_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")

        if body.action_ids:
            rows = await conn.fetch(
                """
                UPDATE actions
                SET status='approved', approved_by=$1, approved_at=now()
                WHERE org_id=$2 AND case_id=$3 AND id = ANY($4::uuid[])
                  AND status='drafted'
                RETURNING id, type AS kind, status
                """,
                ctx.member_id, ctx.org_id, case_id, body.action_ids,
            )
        else:
            rows = await conn.fetch(
                """
                UPDATE actions
                SET status='approved', approved_by=$1, approved_at=now()
                WHERE org_id=$2 AND case_id=$3 AND status='drafted'
                RETURNING id, type AS kind, status
                """,
                ctx.member_id, ctx.org_id, case_id,
            )

        # Flip case status to acting so the UI reflects the transition.
        await conn.execute(
            "UPDATE cases SET status='acting' WHERE id=$1",
            case_id,
        )

        # Append a single human_approved event with the action ids.
        thread_id = await conn.fetchval(
            "SELECT thread_id FROM cases WHERE id=$1", case_id,
        )
        if thread_id:
            await _append_event(
                conn, ctx.org_id, thread_id,
                "human_approved", f"human:member:{ctx.member_id}",
                {
                    "action_ids": [str(r["id"]) for r in rows],
                    "member_email": ctx.member_email,
                },
            )

    return ApproveResponse(
        case_id=case_id,
        approved=[ApprovedAction(id=r["id"], kind=r["kind"], status=r["status"]) for r in rows],
    )


# ──────────────────────────────────────────────────────────────────────
# POST /api/cases/{id}/hold  - pause actions, agent will not execute
# ──────────────────────────────────────────────────────────────────────


@router.post("/{case_id}/hold", status_code=status.HTTP_204_NO_CONTENT)
async def hold_case(
    case_id: UUID,
    ctx: TenantCtx = Depends(get_ctx),
) -> None:
    """Pause drafted actions. Case stays open; agent will not execute."""
    async with get_conn() as conn:
        thread_id = await conn.fetchval(
            "SELECT thread_id FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
        if thread_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")
        await conn.execute(
            "UPDATE cases SET status='awaiting_approval' WHERE id=$1", case_id,
        )
        await _append_event(
            conn, ctx.org_id, thread_id,
            "human_hold", f"human:member:{ctx.member_id}",
            {"member_email": ctx.member_email},
        )


# ──────────────────────────────────────────────────────────────────────
# POST /api/cases/{id}/deny  - reject the agent's recommendation
# (operator decides NOT to fire the drafted actions). Captures the
# reason for the audit trail.
# ──────────────────────────────────────────────────────────────────────


class DenyPayload(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/{case_id}/deny", status_code=status.HTTP_204_NO_CONTENT)
async def deny_case(
    case_id: UUID,
    body: DenyPayload,
    ctx: TenantCtx = Depends(get_ctx),
) -> None:
    """Operator denies the agent's recommendation. Drafted actions are
    flipped to 'denied' so the actor will skip them; case closes as
    resolved-without-action with the reason on file."""
    async with get_conn() as conn:
        thread_id = await conn.fetchval(
            "SELECT thread_id FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
        if thread_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")

        await conn.execute(
            """
            UPDATE actions SET status='denied'
            WHERE case_id=$1 AND status='drafted'
            """,
            case_id,
        )
        await conn.execute(
            "UPDATE cases SET status='resolved', resolved_at=now() WHERE id=$1",
            case_id,
        )
        await _append_event(
            conn, ctx.org_id, thread_id,
            "human_denied", f"human:member:{ctx.member_id}",
            {"member_email": ctx.member_email, "reason": body.reason},
        )


# ──────────────────────────────────────────────────────────────────────
# POST /api/cases/{id}/escalate  - escalate to a human team for review
# beyond Manthan. Marks the case escalated; does not fire actions.
# ──────────────────────────────────────────────────────────────────────


class EscalatePayload(BaseModel):
    reason: str | None = Field(None, max_length=2000)
    to: str | None = Field(None, max_length=200)


@router.post("/{case_id}/escalate", status_code=status.HTTP_204_NO_CONTENT)
async def escalate_case(
    case_id: UUID,
    body: EscalatePayload,
    ctx: TenantCtx = Depends(get_ctx),
) -> None:
    """Hand the case off - Manthan is no longer the owner."""
    async with get_conn() as conn:
        thread_id = await conn.fetchval(
            "SELECT thread_id FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
        if thread_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")
        await conn.execute(
            "UPDATE cases SET status='escalated' WHERE id=$1", case_id,
        )
        await _append_event(
            conn, ctx.org_id, thread_id,
            "human_escalated", f"human:member:{ctx.member_id}",
            {
                "member_email": ctx.member_email,
                "reason": body.reason,
                "to": body.to,
            },
        )


# ──────────────────────────────────────────────────────────────────────
# POST /api/cases/{id}/chat  - user follows up with the agent
# ──────────────────────────────────────────────────────────────────────


class ChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    intent: Literal["question", "edit_request", "re_investigate", "general"] = "general"


@router.post("/{case_id}/chat", status_code=status.HTTP_202_ACCEPTED)
async def chat_with_agent(
    case_id: UUID,
    body: ChatPayload,
    ctx: TenantCtx = Depends(get_ctx),
) -> dict[str, Any]:
    """Append a human_followup event. The investigate worker picks it up
    via NOTIFY, re-invokes the agent loop with the new message in the same
    thread, and the agent's reply streams back via SSE."""
    async with get_conn() as conn:
        thread_id = await conn.fetchval(
            "SELECT thread_id FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
        if thread_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")

        await _append_event(
            conn, ctx.org_id, thread_id,
            "human_followup", f"human:member:{ctx.member_id}",
            {
                "message": body.message,
                "intent": body.intent,
                "member_email": ctx.member_email,
            },
        )
        # Flip case to investigating so the timeline UI re-renders as live.
        await conn.execute(
            "UPDATE cases SET status='investigating' WHERE id=$1", case_id,
        )

    return {"queued": True, "case_id": str(case_id)}


# ──────────────────────────────────────────────────────────────────────
# GET /api/cases/{id}/actions  - list drafted + executed actions
# ──────────────────────────────────────────────────────────────────────


class ActionRow(BaseModel):
    id: UUID
    seq: int
    kind: str
    status: str
    payload: dict[str, Any]
    external_ref: str | None = None
    error_message: str | None = None
    approved_by: UUID | None = None


@router.get("/{case_id}/actions", response_model=list[ActionRow])
async def list_actions(
    case_id: UUID,
    ctx: TenantCtx = Depends(get_ctx),
) -> list[ActionRow]:
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT id, seq, type AS kind, status, payload, external_ref, error_message, approved_by
            FROM actions
            WHERE org_id=$1 AND case_id=$2
            ORDER BY seq ASC
            """,
            ctx.org_id, case_id,
        )
    return [ActionRow(**dict(r)) for r in rows]


# ──────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────


async def _append_event(
    conn,
    org_id: UUID,
    thread_id: UUID,
    type_: str,
    actor: str,
    data: dict[str, Any],
) -> None:
    """Atomic append-with-next-seq."""
    import asyncio

    for attempt in range(5):
        try:
            await conn.execute(
                """
                WITH next AS (
                    SELECT COALESCE(MAX(seq), 0) + 1 AS s
                    FROM events
                    WHERE org_id=$1 AND thread_id=$2
                )
                INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                SELECT $1, $2, s, $3, $4, $5 FROM next
                """,
                org_id, thread_id, type_, actor, data,
            )
            return
        except Exception:
            if attempt == 4:
                raise
            await asyncio.sleep(0.02 * (attempt + 1))
