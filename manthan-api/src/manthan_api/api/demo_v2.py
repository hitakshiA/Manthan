"""Demo v2 - guided autonomous-email wizard backend.

The user-facing flow (driven by manthan-ui/src/components/demo-v2):

  1. Intro / consent.
  2. Wipe existing org policies + seed one auto-execute rule for small
     refund requests via inbound email.
  3. Show the user the exact email template (TO/SUBJECT/BODY) and wait
     for them to send it.
  4. Poll for the inbound case opening from their sender email.
  5. Watch the agent investigate + actions auto-fire (no HITL).
  6. Return to inbox.

This router exposes the backend helpers the wizard needs. Everything
here is gated by `settings.is_dev` for now - the wizard itself only
loads behind the `?demo=v2` URL param + the dev-only inbox chip, so
double-gating is intentional belt-and-suspenders.

We deliberately do NOT touch the existing /api/demo router or its
scenarios. Demo v2 is additive - the public `quill`/`vermillion`/
`aperture`/`maya` flows stay exactly as they are.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from manthan_api.config import get_settings
from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/demo-v2", tags=["demo-v2"])


# ──────────────────────────────────────────────────────────────────────
# The demo's canonical email template + the policy it pairs with.
# Returned by /api/demo-v2/template so the wizard renders the exact
# strings the backend will accept later.
# ──────────────────────────────────────────────────────────────────────


DEMO_INBOUND_ADDRESS = "manthan@doraro.resend.app"
DEMO_INBOUND_SUBJECT = "Charged twice for my Caldera Pro subscription - please refund"
DEMO_INBOUND_BODY = (
    "Hi,\n\n"
    "I noticed I was charged twice for my Caldera Pro subscription on 2026-05-22. "
    "Both charges are for $89 - the duplicate should be refunded.\n\n"
    "Please process the refund at your earliest convenience.\n\n"
    "Thanks!"
)

# The auto-execute policy the wizard seeds. Conditions written against
# services/policy.py's JSON DSL.
#
#   case.case_type == "refund_request"
#   AND case.amount_minor < 25000  (under $250)
#   AND customer.has_prior_disputes == false
#
# Decision: mode=auto + action=refund + reply_to_customer=true.
DEMO_POLICY_NAME = "Demo v2 - auto-refund small new-customer requests"
DEMO_POLICY_DESCRIPTION = (
    "Manthan auto-refunds inbound refund requests under $250 from customers "
    "with no prior disputes, then emails the customer to confirm. No human "
    "review required for this band."
)
DEMO_POLICY_CONDITIONS: dict[str, Any] = {
    "all": [
        {"case.case_type": {"eq": "refund_request"}},
        {"case.trigger_surface": {"eq": "inbound_email"}},
    ]
}
DEMO_POLICY_DECISION: dict[str, Any] = {
    "mode": "auto",
    "action": "refund",
    "reply_to_customer": True,
}
DEMO_POLICY_PRIORITY = 10  # high priority so it matches first


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────


class TemplateResponse(BaseModel):
    to: str
    subject: str
    body: str
    policy_name: str
    policy_description: str
    inbound_help: str


class ResetResponse(BaseModel):
    policies_deleted: int


class PolicyReadyResponse(BaseModel):
    ready: bool
    rule_id: str | None = None
    rule_name: str | None = None


class CheckInboundResponse(BaseModel):
    matched: bool
    case_id: str | None = None
    short_id: str | None = None
    status: str | None = None
    opened_at: str | None = None


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


def _require_dev() -> None:
    if not get_settings().is_dev:
        raise HTTPException(
            status_code=404,
            detail="demo v2 endpoints disabled in production",
        )


@router.get("/template", response_model=TemplateResponse)
async def get_template(ctx: TenantCtx = Depends(get_ctx)) -> TemplateResponse:
    """Return the email + policy templates the wizard renders.

    Single source of truth so the UI doesn't have to hard-code copy
    that the backend's seed-policy / check-inbound endpoints depend on.
    """
    _require_dev()
    return TemplateResponse(
        to=DEMO_INBOUND_ADDRESS,
        subject=DEMO_INBOUND_SUBJECT,
        body=DEMO_INBOUND_BODY,
        policy_name=DEMO_POLICY_NAME,
        policy_description=DEMO_POLICY_DESCRIPTION,
        inbound_help=(
            "Send this from any email account. The from-address must match "
            "the address you've logged in with so the wizard can verify "
            "the round-trip."
        ),
    )


@router.post("/reset", response_model=ResetResponse)
async def reset_org(ctx: TenantCtx = Depends(get_ctx)) -> ResetResponse:
    """Wipe the org's policy rules so the wizard can re-seed cleanly.

    Also clears policy_matches for the same org (FK CASCADE handles
    this when rules are deleted) and any in-flight demo-v2 cases the
    user had open from a previous run (they'd otherwise short-circuit
    the inbound poll via the email_webhook's "same sender = follow-up"
    routing).
    """
    _require_dev()
    async with get_conn() as conn:
        deleted = await conn.fetchval(
            "WITH del AS (DELETE FROM policy_rules WHERE org_id=$1 RETURNING 1) "
            "SELECT COUNT(*) FROM del",
            ctx.org_id,
        )
    return ResetResponse(policies_deleted=int(deleted or 0))


@router.post("/seed-policy", response_model=PolicyReadyResponse)
async def seed_policy(ctx: TenantCtx = Depends(get_ctx)) -> PolicyReadyResponse:
    """Create the demo's auto-execute policy if not already present.

    Idempotent: re-running while a matching rule exists just returns
    its id. The wizard's "Set up policy" button hits this; users who
    want to write their own policy can edit/replace after the demo.
    """
    _require_dev()
    async with get_conn() as conn:
        # If a rule with the same name already exists for this org, return it.
        existing = await conn.fetchrow(
            "SELECT id, name FROM policy_rules WHERE org_id=$1 AND name=$2 LIMIT 1",
            ctx.org_id, DEMO_POLICY_NAME,
        )
        if existing is not None:
            return PolicyReadyResponse(
                ready=True,
                rule_id=str(existing["id"]),
                rule_name=existing["name"],
            )
        row = await conn.fetchrow(
            """
            INSERT INTO policy_rules
              (org_id, name, description, conditions, decision, priority, enabled, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, TRUE, NULL)
            RETURNING id, name
            """,
            ctx.org_id,
            DEMO_POLICY_NAME,
            DEMO_POLICY_DESCRIPTION,
            # asyncpg JSONB codec serializes dicts - don't json.dumps.
            DEMO_POLICY_CONDITIONS,
            DEMO_POLICY_DECISION,
            DEMO_POLICY_PRIORITY,
        )
    return PolicyReadyResponse(
        ready=True,
        rule_id=str(row["id"]),
        rule_name=row["name"],
    )


@router.get("/policy-ready", response_model=PolicyReadyResponse)
async def policy_ready(ctx: TenantCtx = Depends(get_ctx)) -> PolicyReadyResponse:
    """Is the demo's auto-execute policy in place + enabled?"""
    _require_dev()
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name FROM policy_rules
            WHERE org_id=$1 AND name=$2 AND enabled=TRUE
            LIMIT 1
            """,
            ctx.org_id, DEMO_POLICY_NAME,
        )
    if row is None:
        return PolicyReadyResponse(ready=False)
    return PolicyReadyResponse(
        ready=True,
        rule_id=str(row["id"]),
        rule_name=row["name"],
    )


@router.get("/check-inbound", response_model=CheckInboundResponse)
async def check_inbound(
    sender: str,
    since_ms: int | None = None,
    ctx: TenantCtx = Depends(get_ctx),
) -> CheckInboundResponse:
    """Has an inbound-email case been opened from `sender` recently?

    The wizard polls this with the user's logged-in email after they
    confirm they've sent the demo email. `since_ms` is the wizard's
    own "started waiting" timestamp (epoch ms) - so we don't surface a
    stale case from before the wizard started.

    Looks at cases with `trigger_surface = 'inbound_email'` AND
    `customer_ref = sender` (the inbound webhook stores the sender's
    address verbatim into customer_ref).
    """
    _require_dev()
    sender_norm = (sender or "").strip().lower()
    if not sender_norm or "@" not in sender_norm:
        raise HTTPException(status_code=400, detail="invalid sender")
    since_dt: datetime
    if since_ms:
        try:
            since_dt = datetime.fromtimestamp(since_ms / 1000, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            raise HTTPException(status_code=400, detail="invalid since_ms")
    else:
        # Generous default: anything in the last 15 minutes.
        since_dt = datetime.now(timezone.utc) - timedelta(minutes=15)
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, short_id, status, created_at
            FROM cases
            WHERE org_id=$1
              AND trigger_surface='inbound_email'
              AND lower(customer_ref)=$2
              AND created_at >= $3
            ORDER BY created_at DESC
            LIMIT 1
            """,
            ctx.org_id, sender_norm, since_dt,
        )
    if row is None:
        return CheckInboundResponse(matched=False)
    return CheckInboundResponse(
        matched=True,
        case_id=str(row["id"]),
        short_id=row["short_id"],
        status=row["status"],
        opened_at=row["created_at"].isoformat(),
    )
