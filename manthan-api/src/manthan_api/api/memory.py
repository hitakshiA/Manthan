"""Episodic memory - past cases per customer.

Powers /app/memory in the UI. For each customer the org has seen, returns
a count + outcome breakdown + recent case list. This is the surface that
makes "the agent remembers Northwind has filed 3 disputes this year"
visible to the operator.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/customers")
async def list_customers(
    ctx: TenantCtx = Depends(get_ctx),
    limit: int = 100,
) -> dict[str, Any]:
    """List customers with case history, ordered by total case volume."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT
                customer_ref,
                COUNT(*) AS total_cases,
                COUNT(*) FILTER (WHERE status='resolved')           AS resolved,
                COUNT(*) FILTER (WHERE status='awaiting_approval')  AS awaiting,
                COUNT(*) FILTER (WHERE status='investigating')      AS investigating,
                COUNT(*) FILTER (WHERE status='escalated' OR status='errored') AS escalated,
                COUNT(*) FILTER (WHERE decision_action='refund')   AS refunds,
                COUNT(*) FILTER (WHERE decision_action='fight')    AS fights,
                SUM(COALESCE(decision_amount_minor, 0)) FILTER (WHERE decision_action='refund') AS refunded_total_minor,
                MAX(created_at) AS last_seen
            FROM cases
            WHERE org_id=$1 AND customer_ref IS NOT NULL
            GROUP BY customer_ref
            ORDER BY total_cases DESC, last_seen DESC
            LIMIT $2
            """,
            ctx.org_id, limit,
        )

    return {
        "customers": [
            {
                "customer_ref": r["customer_ref"],
                "total_cases": r["total_cases"],
                "resolved": r["resolved"],
                "awaiting": r["awaiting"],
                "investigating": r["investigating"],
                "escalated": r["escalated"],
                "refunds": r["refunds"],
                "fights": r["fights"],
                "refunded_total_minor": int(r["refunded_total_minor"] or 0),
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            }
            for r in rows
        ],
    }


@router.get("/customers/{customer_ref}/cases")
async def customer_cases(
    customer_ref: str,
    ctx: TenantCtx = Depends(get_ctx),
) -> dict[str, Any]:
    """Past cases for one customer - used in the drill-down view."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT id, short_id, status, case_type, trigger_surface,
                   decision_action, decision_amount_minor,
                   amount_minor, currency, created_at, resolved_at
            FROM cases
            WHERE org_id=$1 AND customer_ref=$2
            ORDER BY created_at DESC
            LIMIT 100
            """,
            ctx.org_id, customer_ref,
        )
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no cases for {customer_ref}",
            )

    return {
        "customer_ref": customer_ref,
        "cases": [
            {
                "id": str(r["id"]),
                "short_id": r["short_id"],
                "status": r["status"],
                "case_type": r["case_type"],
                "trigger_surface": r["trigger_surface"],
                "decision_action": r["decision_action"],
                "decision_amount_minor": r["decision_amount_minor"],
                "amount_minor": r["amount_minor"],
                "currency": r["currency"],
                "created_at": r["created_at"].isoformat(),
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            }
            for r in rows
        ],
    }
