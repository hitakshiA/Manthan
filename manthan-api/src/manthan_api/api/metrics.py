"""Org-scoped metrics for the AppShell sidebar + TopBar.

Cheap aggregations over cases + actions. Polled by the UI every ~10s.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from manthan_api.api.sources import SOURCE_REGISTRY
from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


class DashboardMetrics(BaseModel):
    inbox_count: int          # active (investigating + awaiting_approval + acting)
    active_count: int         # investigating + acting (in-flight)
    done_count: int           # resolved
    escalated_count: int      # escalated
    errored_count: int        # errored
    awaiting_count: int       # awaiting_approval specifically (TopBar)
    sources_count: int        # connected sources
    recovered_this_month_minor: int  # refund/partial_credit sums for current month


@router.get("/dashboard", response_model=DashboardMetrics)
async def dashboard_metrics(ctx: TenantCtx = Depends(get_ctx)) -> DashboardMetrics:
    async with get_conn() as conn:
        # Case counts by status
        rows = await conn.fetch(
            """
            SELECT status, count(*) AS n
            FROM cases
            WHERE org_id = $1
            GROUP BY status
            """,
            ctx.org_id,
        )
        by_status = {r["status"]: r["n"] for r in rows}

        # Sources connected. Note: the `sources` DB table is currently
        # unused in v1 (the Sources page derives state from env vars at
        # request time, not from a stored config). Match that source of
        # truth so the sidebar count agrees with the page: count
        # registered sources whose required env vars are all set.
        sources = sum(
            1 for s in SOURCE_REGISTRY
            if all(os.environ.get(e) for e in s["envs"])
        )

        # $ recovered this month (sum of decision_amount_minor for resolved
        # refund / partial_credit cases). Treats acting + resolved as the
        # set of "money has either fired or is approved".
        recovered = await conn.fetchval(
            """
            SELECT COALESCE(SUM(decision_amount_minor), 0)
            FROM cases
            WHERE org_id = $1
              AND decision_action IN ('refund', 'partial_credit')
              AND status IN ('acting', 'resolved')
              AND created_at >= date_trunc('month', now())
            """,
            ctx.org_id,
        )

    investigating = by_status.get("investigating", 0)
    awaiting = by_status.get("awaiting_approval", 0)
    acting = by_status.get("acting", 0)

    return DashboardMetrics(
        inbox_count=investigating + awaiting + acting,
        active_count=investigating + acting,
        done_count=by_status.get("resolved", 0),
        escalated_count=by_status.get("escalated", 0),
        errored_count=by_status.get("errored", 0),
        awaiting_count=awaiting,
        sources_count=sources or 0,
        recovered_this_month_minor=int(recovered or 0),
    )


@router.get("/timeseries")
async def timeseries(
    ctx: TenantCtx = Depends(get_ctx),
    days: int = 30,
) -> dict:
    """Daily aggregates for the /app/metrics charts.

    Returns one row per day for the last `days`:
      - cases_opened
      - cases_resolved
      - cases_by_decision (counts of refund/fight/accept/escalate)
      - recovered_minor (sum of decision_amount_minor for refund-type)
    """
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            WITH days AS (
                SELECT generate_series(
                    date_trunc('day', now()) - ($1::int - 1) * INTERVAL '1 day',
                    date_trunc('day', now()),
                    INTERVAL '1 day'
                )::date AS d
            )
            SELECT
                days.d AS day,
                COUNT(c.id) FILTER (
                    WHERE c.created_at::date = days.d
                ) AS opened,
                COUNT(c.id) FILTER (
                    WHERE c.resolved_at::date = days.d
                ) AS resolved,
                COUNT(c.id) FILTER (
                    WHERE c.created_at::date = days.d AND c.decision_action='refund'
                ) AS refunds,
                COUNT(c.id) FILTER (
                    WHERE c.created_at::date = days.d AND c.decision_action='fight'
                ) AS fights,
                COUNT(c.id) FILTER (
                    WHERE c.created_at::date = days.d AND c.decision_action='escalate'
                ) AS escalates,
                COALESCE(SUM(c.decision_amount_minor) FILTER (
                    WHERE c.created_at::date = days.d
                      AND c.decision_action IN ('refund', 'partial_credit')
                      AND c.status IN ('acting', 'resolved')
                ), 0) AS recovered_minor
            FROM days
            LEFT JOIN cases c ON c.org_id = $2
                AND (c.created_at::date = days.d OR c.resolved_at::date = days.d)
            GROUP BY days.d
            ORDER BY days.d ASC
            """,
            days, ctx.org_id,
        )

    return {
        "days": [
            {
                "day": r["day"].isoformat(),
                "opened": r["opened"],
                "resolved": r["resolved"],
                "refunds": r["refunds"],
                "fights": r["fights"],
                "escalates": r["escalates"],
                "recovered_minor": int(r["recovered_minor"] or 0),
            }
            for r in rows
        ],
    }
