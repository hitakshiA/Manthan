"""Case endpoints - the inbox view + per-case detail + create.

All endpoints are tenant-scoped via the `get_ctx` dependency. No cross-tenant
data leakage is possible without explicit elevation.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx
from manthan_api.models import (
    Case,
    CaseList,
    CaseStatus,
    Citation,
    CreateCaseRequest,
    Finding,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])


# ──────────────────────────────────────────────────────────────────────
# GET /api/cases  - the inbox view
# ──────────────────────────────────────────────────────────────────────


async def fetch_cases_for_org(
    org_id: UUID,
    *,
    member_id: UUID | None = None,
    scope: Literal["all", "mine", "watching"] = "all",
    status_: CaseStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Case], int]:
    """Shared fetcher used by GET /api/cases and the inbox SSE stream.

    Returns (cases, total_matching_filters). Joins in the latest brief
    TLDR and the most-recent prettifier-written event summary so the
    inbox cards can show a one-line description without a per-row second
    fetch.
    """
    where = ["org_id = $1"]
    params: list[object] = [org_id]

    if scope == "mine" and member_id is not None:
        where.append(f"assigned_member_id = ${len(params) + 1}")
        params.append(member_id)

    if status_:
        where.append(f"status = ${len(params) + 1}")
        params.append(status_)

    where_sql = " AND ".join(where)
    case_where_sql = (
        where_sql
        .replace("org_id", "c.org_id")
        .replace("status", "c.status")
        .replace("assigned_member_id", "c.assigned_member_id")
    )

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                c.id, c.org_id, c.short_id, c.status, c.trigger_surface, c.case_type,
                c.customer_ref, c.amount_minor, c.currency,
                c.decision_action, c.decision_amount_minor, c.decision_confidence,
                c.assigned_member_id, c.created_at, c.resolved_at,
                (
                    SELECT data->>'tldr'
                    FROM events
                    WHERE org_id = c.org_id
                      AND thread_id = c.thread_id
                      AND type = 'brief_drafted'
                    ORDER BY seq DESC
                    LIMIT 1
                ) AS brief_tldr,
                (
                    SELECT summary
                    FROM events
                    WHERE org_id = c.org_id
                      AND thread_id = c.thread_id
                      AND summary IS NOT NULL
                      AND type IN (
                          'tool_call', 'tool_result', 'finding_recorded',
                          'reflexion', 'brief_drafted', 'agent_thought'
                      )
                    ORDER BY seq DESC
                    LIMIT 1
                ) AS latest_pretty_summary
            FROM cases c
            WHERE {case_where_sql}
            ORDER BY c.created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params,
            limit,
            offset,
        )
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM cases WHERE {where_sql}",
            *params,
        )

    cases: list[Case] = []
    for r in rows:
        rd = dict(r)
        brief_tldr = rd.pop("brief_tldr", None)
        latest_pretty = rd.pop("latest_pretty_summary", None)
        # Pick the best one-line summary for the inbox card:
        # 1. Brief TLDR (set once the agent concludes)
        # 2. Latest prettifier-written event summary (during investigation)
        # 3. None - frontend falls back to a synthetic line
        rd["card_summary"] = _shorten_summary(brief_tldr or latest_pretty)
        cases.append(Case(**rd))
    return cases, total or 0


@router.get("", response_model=CaseList)
async def list_cases(
    ctx: TenantCtx = Depends(get_ctx),
    scope: Literal["all", "mine", "watching"] = Query("all"),
    status_: CaseStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CaseList:
    """List cases for the current org.

    `scope=mine` filters to cases assigned to the current member.
    `scope=watching` is a placeholder for future watchlist.
    """
    cases, total = await fetch_cases_for_org(
        ctx.org_id,
        member_id=ctx.member_id,
        scope=scope,
        status_=status_,
        limit=limit,
        offset=offset,
    )
    return CaseList(cases=cases, total=total)


def _shorten_summary(s: str | None, max_len: int = 220) -> str | None:
    if not s:
        return None
    s = " ".join(s.split())  # collapse whitespace
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


# ──────────────────────────────────────────────────────────────────────
# GET /api/cases/{id}/trigger_email
#   The original email that opened this case, for email-triggered cases.
#   Webui shows it in a modal labelled "Original email".
# ──────────────────────────────────────────────────────────────────────


@router.get("/{case_id}/trigger_email")
async def get_trigger_email(
    case_id: UUID,
    ctx: TenantCtx = Depends(get_ctx),
) -> dict:
    """Return the raw inbound email that opened this case.

    Pulls fields off `cases.trigger_payload` - only relevant for cases
    with `trigger_surface='inbound_email'`. Returns 404 for other
    surfaces so the UI can hide the affordance.
    """
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT trigger_surface, customer_ref, trigger_payload, created_at
            FROM cases
            WHERE org_id=$1 AND id=$2
            """,
            ctx.org_id, case_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")
    if row["trigger_surface"] != "inbound_email":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="case was not opened via email",
        )
    payload = row["trigger_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload = payload or {}
    return {
        "from_addr": payload.get("from_addr") or row["customer_ref"],
        "from_name": payload.get("from_name") or "",
        "subject": payload.get("subject") or "",
        "received_at": payload.get("received_at") or row["created_at"].isoformat(),
        "message_id": payload.get("message_id") or "",
        "text": payload.get("raw_text") or "",
        "html": payload.get("raw_html") or "",
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/cases/{id}  - case detail (with findings)
# ──────────────────────────────────────────────────────────────────────


@router.get("/{case_id}", response_model=Case)
async def get_case(
    case_id: UUID,
    ctx: TenantCtx = Depends(get_ctx),
) -> Case:
    async with get_conn() as conn:
        case_row = await conn.fetchrow(
            """
            SELECT id, org_id, short_id, status, trigger_surface, case_type,
                   customer_ref, amount_minor, currency,
                   decision_action, decision_amount_minor, decision_confidence,
                   assigned_member_id, created_at, resolved_at
            FROM cases
            WHERE org_id = $1 AND id = $2
            """,
            ctx.org_id,
            case_id,
        )
        if case_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")

        finding_rows = await conn.fetch(
            """
            SELECT id, seq, text, confidence, citations, created_at
            FROM findings
            WHERE org_id = $1 AND case_id = $2
            ORDER BY seq ASC
            """,
            ctx.org_id,
            case_id,
        )

    from manthan_api.services.citation_links import resolve_url

    findings = []
    for fr in finding_rows:
        cites_data = fr["citations"] or []
        if isinstance(cites_data, str):
            cites_data = json.loads(cites_data)
        # Resolve a deep-link URL for each citation so the UI can render
        # citation chips as clickable links straight to the source record.
        enriched = []
        for c in cites_data:
            if not isinstance(c, dict):
                continue
            url = resolve_url(c.get("source"), c.get("table"), c.get("ref"))
            enriched.append(Citation(
                source=c.get("source", "unknown"),
                table=c.get("table", ""),
                ref=c.get("ref", ""),
                field=c.get("field"),
                url=url,
            ))
        findings.append(
            Finding(
                id=fr["id"],
                seq=fr["seq"],
                text=fr["text"],
                confidence=float(fr["confidence"]) if fr["confidence"] is not None else None,
                citations=enriched,
                created_at=fr["created_at"],
            )
        )

    # Denormalise the latest brief + policy match onto the case detail so
    # the UI's "Decision" block shows the rationale + which rule matched
    # without needing a second roundtrip.
    from manthan_api.models import BriefSummary, PolicyMatchSummary

    async with get_conn() as conn:
        thread_id = await conn.fetchval(
            "SELECT thread_id FROM cases WHERE id=$1", case_id,
        )
        brief_row = await conn.fetchrow(
            """
            SELECT data, created_at FROM events
            WHERE org_id=$1 AND thread_id=$2 AND type='brief_drafted'
            ORDER BY seq DESC LIMIT 1
            """,
            ctx.org_id, thread_id,
        )
        match_row = await conn.fetchrow(
            """
            SELECT r.name AS rule_name, m.mode, m.matched_at
            FROM policy_matches m
            JOIN policy_rules r ON r.id = m.rule_id
            WHERE m.case_id=$1
            ORDER BY m.matched_at DESC LIMIT 1
            """,
            case_id,
        )

    brief_summary = None
    if brief_row:
        b = brief_row["data"] if isinstance(brief_row["data"], dict) else json.loads(brief_row["data"])
        decision = b.get("decision") or {}
        brief_summary = BriefSummary(
            tldr=b.get("tldr"),
            decision_rationale=decision.get("rationale") or b.get("decision_rationale"),
            decision_action=decision.get("action") or b.get("decision_action"),
            decision_amount_minor=decision.get("amount_minor") or b.get("decision_amount_minor"),
            decision_confidence=decision.get("confidence") or b.get("decision_confidence"),
            hitl_question=b.get("hitl_question"),
            generated_at=brief_row["created_at"],
        )

    policy_match_summary = None
    if match_row:
        policy_match_summary = PolicyMatchSummary(
            rule_name=match_row["rule_name"],
            mode=match_row["mode"],
            matched_at=match_row["matched_at"],
        )

    return Case(
        **dict(case_row),
        findings=findings,
        brief=brief_summary,
        policy_match=policy_match_summary,
    )


# ──────────────────────────────────────────────────────────────────────
# POST /api/cases  - manual trigger from the web "+ New" button or API
# ──────────────────────────────────────────────────────────────────────


@router.post("", response_model=Case, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CreateCaseRequest,
    ctx: TenantCtx = Depends(get_ctx),
) -> Case:
    """Open a new case manually.

    Writes a `case_opened` event; the agent worker picks it up via
    LISTEN/NOTIFY and starts investigating.
    """
    thread_id = uuid.uuid4()
    short_id = _next_short_id()

    async with get_conn() as conn:
        async with conn.transaction():
            case_row = await conn.fetchrow(
                """
                INSERT INTO cases (
                    org_id, thread_id, short_id, status, trigger_surface,
                    trigger_payload, case_type, customer_ref, amount_minor, currency
                )
                VALUES ($1, $2, $3, 'investigating', 'web_new',
                        $4, $5, $6, $7, $8)
                RETURNING id, org_id, short_id, status, trigger_surface, case_type,
                          customer_ref, amount_minor, currency,
                          decision_action, decision_amount_minor, decision_confidence,
                          assigned_member_id, created_at, resolved_at
                """,
                ctx.org_id,
                thread_id,
                short_id,
                json.dumps(
                    {
                        "trigger_text": body.trigger_text,
                        "case_type": body.case_type,
                        "metadata": body.metadata,
                        "submitted_by_member_id": str(ctx.member_id),
                    }
                ),
                body.case_type,
                body.customer_ref,
                body.amount_minor,
                body.currency,
            )

            # case_opened event - agent worker reacts to this via LISTEN.
            await conn.execute(
                """
                INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                VALUES ($1, $2, 1, 'case_opened', $3, $4)
                """,
                ctx.org_id,
                thread_id,
                f"human:member:{ctx.member_id}",
                json.dumps(
                    {
                        "case_id": str(case_row["id"]),
                        "short_id": short_id,
                        "trigger_surface": "web_new",
                        "trigger_text": body.trigger_text,
                        "case_type": body.case_type,
                        "customer_ref": body.customer_ref,
                        "amount_minor": body.amount_minor,
                    }
                ),
            )

    return Case(**dict(case_row))


# ──────────────────────────────────────────────────────────────────────
# GET /api/cases/{id}/brief.pdf  - render the brief as a one-page PDF
# ──────────────────────────────────────────────────────────────────────


@router.get("/{case_id}/brief.pdf")
async def get_brief_pdf(
    case_id: UUID,
    ctx: TenantCtx = Depends(get_ctx),
) -> Response:
    """Polished one-page PDF of the case brief.

    Used as a Slack attachment (asky PDF) and as a "Download brief" link
    in the UI. Generated on-demand from latest case state.
    """
    from manthan_api.services.brief_pdf import render_brief_pdf
    try:
        pdf = await render_brief_pdf(ctx.org_id, case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="manthan-brief-{case_id}.pdf"',
        },
    )


def _next_short_id() -> str:
    """Generate a human-friendly short id like CASE-4821.

    For now: random 4-digit number prefixed with CASE-. Later: per-org sequence
    with monotonic ordering.
    """
    import secrets

    return f"CASE-{secrets.randbelow(9000) + 1000}"
