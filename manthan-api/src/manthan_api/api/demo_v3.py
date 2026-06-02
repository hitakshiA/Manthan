"""Demo v3 - guided Slack-Thread wizard backend.

The companion to demo_v2 (autonomous-email). Where v2 walks the user
through emailing manthan@doraro.resend.app and watching Manthan
auto-resolve the case, v3 walks them through joining a shared Slack
workspace, mentioning @manthantest in #all-manthandemo, and watching
the same end-to-end flow but with the Slack thread as the trigger.

Endpoints (all gated by `is_dev`):
  GET /api/demo-v3/template         canonical mention text + invite link
  GET /api/demo-v3/check-slack-member?email=...
                                    has this user joined the shared
                                    ManthanDemo workspace yet
  GET /api/demo-v3/check-slack-inbound?slack_email=...&since_ms=...
                                    has a Slack-triggered case been
                                    opened for this user recently

The actual case creation happens in `services/slack_bot.py` once the
user @-mentions the bot - that path is shared with the existing
ad-hoc Slack ingestion. This router only exposes the *introspection*
endpoints the wizard polls.

Per-tenant routing context:
  - We share one Slack workspace + one bot token across all signed-in
    Manthan users. Identity is bridged by matching the mentioning
    Slack user's email to a Manthan `members` row (the slack_bot
    extension landed alongside this router).
  - The shared `acme` org doesn't matter here; lookups happen against
    `ctx.org_id` which is whatever org the signed-in user resolves
    into (their personal org via tenant middleware).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from manthan_api.config import get_settings
from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/demo-v3", tags=["demo-v3"])
logger = logging.getLogger("manthan_api.demo_v3")


# ──────────────────────────────────────────────────────────────────────
# The demo's canonical Slack mention copy. Returned by /template so the
# wizard renders the exact text the backend will accept later.
# ──────────────────────────────────────────────────────────────────────


DEMO_SLACK_INVITE_URL = (
    "https://join.slack.com/t/manthandemo/shared_invite/"
    "zt-3yxxjnocn-ViOL51MH2gkA1fMCskWHxA"
)
DEMO_SLACK_WORKSPACE = "ManthanDemo"
DEMO_SLACK_CHANNEL = "#all-manthandemo"
DEMO_SLACK_BOT_HANDLE = "@manthantest"
DEMO_SLACK_MENTION_TEXT = (
    "@manthantest look into the chargeback from Vermillion Studios for "
    "$4,500 - they say we billed for 25 seats but they only have 15"
)


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────


class TemplateResponse(BaseModel):
    invite_url: str
    workspace_name: str
    channel: str
    bot_handle: str
    mention_text: str
    inbound_help: str


class CheckSlackMemberResponse(BaseModel):
    member: bool
    slack_user_id: str | None = None
    slack_display_name: str | None = None


class CheckSlackInboundResponse(BaseModel):
    matched: bool
    case_id: str | None = None
    short_id: str | None = None
    status: str | None = None
    opened_at: str | None = None


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _require_dev() -> None:
    if not get_settings().is_dev:
        raise HTTPException(
            status_code=404,
            detail="demo v3 endpoints disabled in production",
        )


async def _slack_lookup_by_email(email: str) -> dict[str, Any] | None:
    """Call Slack's users.lookupByEmail to check if a user with this
    email is a member of the ManthanDemo workspace. Returns the user
    object (with id, name, profile) on success, None if not found or
    if the call errored."""
    token = os.environ.get("SLACK_TOKEN")
    if not token:
        logger.warning("SLACK_TOKEN unset - cannot check workspace membership")
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as http:
            r = await http.get(
                "https://slack.com/api/users.lookupByEmail",
                params={"email": email},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as e:
        logger.warning("slack lookup network error for %s: %s", email, e)
        return None
    if r.status_code >= 400:
        logger.warning("slack lookup HTTP %d for %s", r.status_code, email)
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not data.get("ok"):
        # Common: "users_not_found" when the user hasn't joined yet.
        # Not an error - we just return None and the wizard keeps polling.
        return None
    return data.get("user")


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get("/template", response_model=TemplateResponse)
async def get_template(ctx: TenantCtx = Depends(get_ctx)) -> TemplateResponse:
    """Return the wizard's canonical strings - invite URL, channel,
    mention text. Single source of truth so the UI never drifts from
    the backend's expectations."""
    _require_dev()
    return TemplateResponse(
        invite_url=DEMO_SLACK_INVITE_URL,
        workspace_name=DEMO_SLACK_WORKSPACE,
        channel=DEMO_SLACK_CHANNEL,
        bot_handle=DEMO_SLACK_BOT_HANDLE,
        mention_text=DEMO_SLACK_MENTION_TEXT,
        inbound_help=(
            f"Join {DEMO_SLACK_WORKSPACE} via the invite link, open "
            f"{DEMO_SLACK_CHANNEL}, and post the mention from the same "
            "email you're signed into Manthan with so we can route the "
            "case to your workspace."
        ),
    )


@router.get("/check-slack-member", response_model=CheckSlackMemberResponse)
async def check_slack_member(
    email: str,
    ctx: TenantCtx = Depends(get_ctx),
) -> CheckSlackMemberResponse:
    """Has this email joined the ManthanDemo workspace yet?

    The wizard polls this between the "join workspace" step and the
    "send mention" step - once we can resolve their email via
    users.lookupByEmail, we know they're in and it's safe to ask them
    to @-mention the bot.
    """
    _require_dev()
    norm = (email or "").strip().lower()
    if not norm or "@" not in norm:
        raise HTTPException(status_code=400, detail="invalid email")
    user = await _slack_lookup_by_email(norm)
    if user is None:
        return CheckSlackMemberResponse(member=False)
    profile = user.get("profile") or {}
    return CheckSlackMemberResponse(
        member=True,
        slack_user_id=user.get("id"),
        slack_display_name=(
            profile.get("display_name")
            or profile.get("real_name")
            or user.get("name")
        ),
    )


@router.get("/check-slack-inbound", response_model=CheckSlackInboundResponse)
async def check_slack_inbound(
    slack_email: str,
    since_ms: int | None = None,
    ctx: TenantCtx = Depends(get_ctx),
) -> CheckSlackInboundResponse:
    """Has a Slack-triggered case been opened from this user recently?

    The wizard polls this with the user's logged-in email (= their
    Slack email, which the slack_bot uses to route the case into
    their personal Manthan org). Mirrors check-inbound from demo_v2
    but scoped to Slack triggers.

    Looks for cases with `trigger_surface IN ('slack_mention',
    'slack_dm')` AND trigger_payload->>'mentioned_by_email' = the
    user's email (the slack_bot stamps this when it routes by email
    match - see slack_bot.open_case_from_slack).
    """
    _require_dev()
    norm = (slack_email or "").strip().lower()
    if not norm or "@" not in norm:
        raise HTTPException(status_code=400, detail="invalid slack_email")
    if since_ms:
        try:
            since_dt = datetime.fromtimestamp(since_ms / 1000, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            raise HTTPException(status_code=400, detail="invalid since_ms")
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(minutes=15)
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, short_id, status, created_at
            FROM cases
            WHERE org_id = $1
              AND trigger_surface IN ('slack_mention', 'slack_dm', 'manual_slack')
              AND lower(trigger_payload->>'mentioned_by_email') = $2
              AND created_at >= $3
            ORDER BY created_at DESC
            LIMIT 1
            """,
            ctx.org_id, norm, since_dt,
        )
    if row is None:
        return CheckSlackInboundResponse(matched=False)
    return CheckSlackInboundResponse(
        matched=True,
        case_id=str(row["id"]),
        short_id=row["short_id"],
        status=row["status"],
        opened_at=row["created_at"].isoformat(),
    )
