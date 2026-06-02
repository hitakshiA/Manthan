"""Slack bot - Manthan as a Slack-native investigator.

Three inbound paths:
  1. @manthan mention in a channel    → open a new case from the mention text
  2. DM to @manthan                    → open a new case from the DM text
  3. Reply in a bot-posted thread      → route as chat_followup on the same case

One outbound shape:
  Brief card posted to channel (or DM) using Block Kit. Card carries:
    - TLDR + decision + confidence
    - 2-3 top findings (with citations)
    - "View in Manthan" link (deep-link to the UI workspace)
    - "Approve & Execute" button → opens a signature modal
    - "Hold" button → flips status, no execution

When the operator clicks Approve, we open a Block Kit view (modal) asking for
a one-line signature ("Approved - Mark from RevOps"). Submitting the modal
calls /api/cases/{id}/approve with that signature attached to the action
metadata.

Threading rule: every brief we post records its (channel, ts) on the case
row's trigger_payload.slack_thread_ref. Any future Slack event with
thread_ts == ts is treated as a follow-up on that case.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any
from uuid import UUID

import asyncpg
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from manthan_api.db import get_pool

logger = logging.getLogger("services.slack_bot")


def _client() -> WebClient:
    token = os.environ.get("SLACK_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_TOKEN missing - set in .env")
    return WebClient(token=token)


# ──────────────────────────────────────────────────────────────────────
# Inbound: open a new case from a Slack mention or DM
# ──────────────────────────────────────────────────────────────────────


async def open_case_from_slack(
    *,
    org_id: UUID,
    text: str,
    user_id: str,
    user_name: str,
    channel_id: str,
    channel_name: str | None,
    is_dm: bool,
    event_ts: str,
) -> tuple[UUID, str]:
    """Open a case from a Slack mention/DM. Returns (case_id, short_id).

    Tenancy rule (mirrors email_webhook's per-sender routing):
      1. Look up the mentioning Slack user's email via users.info.
         If that email matches a row in the Manthan `members` table,
         OVERRIDE the URL-slug-derived org_id and route the case into
         that member's personal org. This is how we share one
         Slack workspace + one bot token across all signed-in users.
      2. If no match, the case stays in the org passed by the caller
         (resolved from the URL slug, typically `acme`).

    Demo-v3 graft:
      When the matched member's mention lands in #all-manthandemo (or
      any channel whose name contains 'manthan-demo'), attach the
      Vermillion Studios seeded Stripe IDs onto trigger_payload so the
      agent can SELECT against real records, not the runner's own
      personal email which has no Stripe history.

    The investigate worker picks the case up via NOTIFY and starts the
    agent loop. We don't post the brief here - that happens later when
    brief_drafted fires (see `post_brief_to_thread`).
    """
    import secrets

    thread_id = uuid.uuid4()
    short_id = f"SLK-{secrets.randbelow(900000) + 100000}"

    cleaned = text.strip()
    if cleaned.startswith("<@") and ">" in cleaned:
        cleaned = cleaned.split(">", 1)[1].strip()

    surface = "slack_dm" if is_dm else "slack_mention"

    # Resolve the mentioning Slack user's email so we can route the case
    # into their personal Manthan org if they're a signed-in member.
    mentioned_email = _slack_user_email(user_id)
    routed_via_member = False
    async with get_pool().acquire() as conn:
        if mentioned_email:
            member_row = await conn.fetchrow(
                """
                SELECT o.id AS org_id, o.slug AS org_slug
                FROM members m
                JOIN orgs o ON o.id = m.org_id
                WHERE lower(m.email) = $1
                ORDER BY m.created_at ASC
                LIMIT 1
                """,
                mentioned_email.lower(),
            )
            if member_row is not None:
                org_id = member_row["org_id"]
                routed_via_member = True
                logger.info(
                    "slack mention routed to member's own org: slack_user=%s email=%s org=%s",
                    user_id, mentioned_email, member_row["org_slug"],
                )

        # Demo-v3 graft - signed-in member mentioned the bot in the
        # demo channel. Attach Vermillion's seeded Stripe IDs so the
        # agent has real billing data to investigate.
        chan_lower = (channel_name or "").lower()
        demo_v3_active = (
            routed_via_member
            and ("manthan-demo" in chan_lower or "manthandemo" in chan_lower)
        )
        demo_graft: dict[str, Any] = {}
        if demo_v3_active:
            demo_graft = _vermillion_graft()
            logger.info(
                "demo-v3 graft applied: short_id=%s channel=%s",
                short_id, channel_name,
            )

        trigger_payload = {
            "slack_user_id": user_id,
            "slack_user_name": user_name,
            "slack_channel_id": channel_id,
            "slack_channel_name": channel_name,
            "slack_event_ts": event_ts,
            "raw_text": text,
            "cleaned_text": cleaned,
            "mentioned_by_email": mentioned_email,
            **demo_graft,
        }

        trigger_text = cleaned
        if demo_v3_active:
            trigger_text = (
                f"{cleaned}\n\n"
                f"-- demo-v3 enrichment (auto-attached) --\n"
                f"Customer:       Vermillion Studios ({demo_graft['customer_id']})\n"
                f"Disputed charge: {demo_graft['charge_id']}\n"
                f"Dispute id:     {demo_graft['dispute_id']}\n"
                f"Amount:         $4,500 USD"
            )

        async with conn.transaction():
            case_row = await conn.fetchrow(
                """
                INSERT INTO cases (
                    org_id, thread_id, short_id, status, trigger_surface,
                    trigger_payload, case_type, customer_ref, amount_minor, currency
                )
                VALUES ($1, $2, $3, 'investigating', $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                org_id, thread_id, short_id, surface,
                json.dumps(trigger_payload),
                "chargeback" if demo_v3_active else "slack_request",
                "Vermillion Studios" if demo_v3_active else None,
                450000 if demo_v3_active else None,
                "usd" if demo_v3_active else None,
            )
            case_id = case_row["id"]
            await conn.execute(
                """
                INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                VALUES ($1, $2, 1, 'case_opened', $3, $4)
                """,
                org_id, thread_id, f"slack:user:{user_id}",
                json.dumps({
                    "case_id": str(case_id),
                    "short_id": short_id,
                    "trigger_surface": surface,
                    "trigger_text": trigger_text,
                    "slack_user_id": user_id,
                    "slack_user_name": user_name,
                    "slack_channel_id": channel_id,
                    "slack_channel_name": channel_name,
                    "slack_event_ts": event_ts,
                    "mentioned_by_email": mentioned_email,
                    **demo_graft,
                }),
            )
    logger.info(
        "slack opened case %s (surface=%s user=%s member_routed=%s demo_v3=%s)",
        short_id, surface, user_name, routed_via_member, bool(demo_graft),
    )
    return case_id, short_id


def _slack_user_email(user_id: str) -> str | None:
    """Look up a Slack user's email via users.info. Requires the bot
    token to have the users:read.email scope. Returns None on any
    failure - the caller falls back to URL-slug org routing."""
    try:
        resp = _client().users_info(user=user_id)
    except SlackApiError as e:
        logger.warning("slack users.info failed for %s: %s", user_id, e)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("slack users.info unexpected error for %s: %s", user_id, e)
        return None
    user = resp.get("user") or {}
    profile = user.get("profile") or {}
    email = profile.get("email")
    return str(email).strip().lower() if email else None


def _vermillion_graft() -> dict[str, Any]:
    """Seeded Vermillion Studios chargeback IDs the agent will use when
    a Manthan member mentions the bot in #all-manthandemo. Mirrors the
    demo_v2 Maya graft over email; uses the existing `vermillion`
    scenario's Stripe IDs (see api/demo.py)."""
    return {
        "demo_v3": True,
        "customer_id": "cus_UbE7T8oTOj7vBT",
        "charge_id": "ch_3Tc2QNCNe0SBMhzI1ZxM1yrK",
        "dispute_id": "du_1Tc2QQCNe0SBMhzImPgJOJiO",
        "hubspot_company_id": "324968425171",
    }


# ──────────────────────────────────────────────────────────────────────
# Inbound: route a thread reply to chat_followup
# ──────────────────────────────────────────────────────────────────────


async def route_thread_reply(
    *,
    org_id: UUID,
    thread_ts: str,
    channel_id: str,
    user_id: str,
    user_name: str,
    text: str,
) -> bool:
    """Route a thread reply on a known case to the right handler.

    Three branches based on what the reply looks like + case state:

      1. The case is `awaiting_signature` and this reply parses as
         `Full Name, Role`  →  capture signature + fire approval.
      2. Reply is an approve verb (`approve`, `lgtm`, etc.)
         →  ask the operator for Full Name + Role; mark the case
            `awaiting_signature`.
      3. Anything else → treat as `human_followup` (chat_loop picks
         it up, agent answers or re-investigates with memory).

    Returns True if we handled the reply (case was recognised).
    """
    async with get_pool().acquire() as conn:
        case_row = await conn.fetchrow(
            """
            SELECT id, short_id, thread_id,
                   trigger_payload->>'slack_awaiting_signature' AS awaiting_sig
            FROM cases
            WHERE org_id = $1
              AND trigger_payload->>'slack_thread_ts' = $2
              AND trigger_payload->>'slack_thread_channel' = $3
            LIMIT 1
            """,
            org_id, thread_ts, channel_id,
        )
        if case_row is None:
            return False
        thread_id = case_row["thread_id"]
        case_id = case_row["id"]
        short_id = case_row["short_id"]
        awaiting_sig = bool(case_row["awaiting_sig"]) and case_row["awaiting_sig"] != "false"

    # ── Branch 1: in-progress e-signature flow ──
    if awaiting_sig:
        parsed = parse_signature_reply(text)
        if parsed is None:
            await post_reply_to_thread(
                channel_id=channel_id,
                thread_ts=thread_ts,
                text=build_signature_invalid_text(),
            )
            return True
        full_name, role = parsed
        await _consume_signature_and_approve(
            org_id=org_id,
            case_id=case_id,
            short_id=short_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            slack_user_id=user_id,
            slack_user_name=user_name,
            full_name=full_name,
            role=role,
        )
        return True

    # ── Branch 2: text-approve verb ──
    if is_approval_text(text):
        await _request_signature_in_thread(
            org_id=org_id,
            case_id=case_id,
            short_id=short_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )
        return True

    # ── Branch 3: chat follow-up. Memory continues - chat_loop reads
    #    the agent_thread state from the checkpointer when it picks
    #    this event up. ──
    async with get_pool().acquire() as conn:
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
                    SELECT $1, $2, s, 'human_followup', $3, $4 FROM next
                    """,
                    org_id, thread_id,
                    f"slack:user:{user_id}",
                    json.dumps({
                        "message": text,
                        "intent": "general",
                        "slack_user_id": user_id,
                        "slack_user_name": user_name,
                        "slack_channel_id": channel_id,
                        "via": "slack_thread",
                    }),
                )
                break
            except asyncpg.UniqueViolationError:
                if attempt == 4:
                    raise
                import asyncio
                await asyncio.sleep(0.02 * (attempt + 1))

    logger.info("routed slack thread reply to case %s", case_id)
    return True


async def _request_signature_in_thread(
    *,
    org_id: UUID,
    case_id: UUID,
    short_id: str,
    channel_id: str,
    thread_ts: str,
) -> None:
    """Set the `awaiting_signature` flag and ask the operator for their
    full name + role. The next thread reply hits Branch 1 above and
    parses the answer."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE cases
            SET trigger_payload = trigger_payload ||
                jsonb_build_object('slack_awaiting_signature', 'true')
            WHERE org_id=$1 AND id=$2
            """,
            org_id, case_id,
        )
    await post_reply_to_thread(
        channel_id=channel_id,
        thread_ts=thread_ts,
        text=build_signature_prompt_text(short_id),
    )


async def _consume_signature_and_approve(
    *,
    org_id: UUID,
    case_id: UUID,
    short_id: str,
    channel_id: str,
    thread_ts: str,
    slack_user_id: str,
    slack_user_name: str,
    full_name: str,
    role: str,
) -> None:
    """Capture a parsed signature and fire the same approval path the
    Block Kit modal uses. Clears the awaiting_signature flag."""
    signature = f"{full_name}, {role}"
    signer_display = f"{full_name} · {role}"

    try:
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                approved = await conn.fetch(
                    """
                    UPDATE actions
                    SET status='approved',
                        approved_at=now(),
                        payload = payload || jsonb_build_object(
                            'approved_via', 'slack_chat',
                            'approval_signature', $3::text,
                            'approval_full_name', $4::text,
                            'approval_role', $5::text,
                            'approved_by_slack_user', $6::text
                        )
                    WHERE org_id=$1 AND case_id=$2 AND status='drafted'
                    RETURNING id
                    """,
                    org_id, case_id, signature, full_name, role, slack_user_name,
                )
                await conn.execute(
                    "UPDATE cases SET status='acting' WHERE id=$1",
                    case_id,
                )
                await conn.execute(
                    """
                    UPDATE cases
                    SET trigger_payload = trigger_payload ||
                        jsonb_build_object('slack_awaiting_signature', 'false',
                                           'slack_signer_display', $2::text)
                    WHERE id=$1
                    """,
                    case_id, signer_display,
                )
                thread_id = await conn.fetchval(
                    "SELECT thread_id FROM cases WHERE id=$1", case_id,
                )
                for attempt in range(5):
                    try:
                        await conn.execute(
                            """
                            WITH next AS (
                                SELECT COALESCE(MAX(seq), 0) + 1 AS s
                                FROM events WHERE org_id=$1 AND thread_id=$2
                            )
                            INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                            SELECT $1, $2, s, 'human_approved', $3, $4 FROM next
                            """,
                            org_id, thread_id,
                            f"slack:user:{slack_user_id}",
                            json.dumps({
                                "action_ids": [str(r["id"]) for r in approved],
                                "signature": signature,
                                "full_name": full_name,
                                "role": role,
                                "slack_user_name": slack_user_name,
                                "via": "slack_chat",
                            }),
                        )
                        break
                    except Exception:
                        if attempt == 4:
                            raise
                        import asyncio
                        await asyncio.sleep(0.02 * (attempt + 1))
    except Exception as e:  # noqa: BLE001
        logger.exception("slack-chat approve failed: %s", e)
        await post_reply_to_thread(
            channel_id=channel_id,
            thread_ts=thread_ts,
            text=f":warning: Couldn't approve `{short_id}` - {type(e).__name__}: {e}",
        )
        return

    await post_reply_to_thread(
        channel_id=channel_id,
        thread_ts=thread_ts,
        text=(
            f":white_check_mark: Signed by *{full_name}* - _{role}_.\n"
            f"Executing {len(approved)} action(s). I'll post the final "
            "receipts here when they land."
        ),
    )


# ──────────────────────────────────────────────────────────────────────
# Outbound: post the brief card to Slack
# ──────────────────────────────────────────────────────────────────────


def build_brief_blocks(
    *,
    short_id: str,
    customer: str,
    amount_display: str,
    tldr: str,
    decision_action: str,
    decision_confidence: float | None,
    top_findings: list[str],
    suggested_actions: list[dict[str, str]],
    deep_link: str,
    case_id: str,
    requester_slack_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build the Block Kit shape for a brief card.

    Sketch fidelity:
      - Header  "Manthan brief · SLK-XXX"
      - Greeting line `hey @user, I have completed my analysis.`
      - TL;DR (one paragraph)
      - Recommendation pill + confidence
      - Top findings (3)
      - Suggested actions ("I suggest the following actions")
      - Inline hint: reply `approve` here to fire them
      - Approve / Hold / Open buttons

    Suggested actions come in as a list of {emoji, title, target} dicts -
    rendered as a bullet list with the source emoji at the start.
    """
    decision_emoji = {
        "fight": ":crossed_swords:",
        "refund": ":money_with_wings:",
        "accept": ":white_check_mark:",
        "escalate": ":bell:",
    }.get(decision_action or "", ":mag:")

    conf_pct = f"{int((decision_confidence or 0) * 100)}%" if decision_confidence else "-"

    findings_text = "\n".join(f"• {f}" for f in top_findings[:3]) or "_No findings yet._"

    if suggested_actions:
        actions_text = "\n".join(
            f"{a.get('emoji', ':zap:')} *{a.get('title', 'Action')}*"
            + (f"  _{a['target']}_" if a.get("target") else "")
            for a in suggested_actions[:8]
        )
    else:
        actions_text = "_No actions drafted - nothing for you to approve here._"

    greeting = "hey "
    if requester_slack_id:
        greeting += f"<@{requester_slack_id}>, "
    greeting += "I've completed my analysis."

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Manthan brief · {short_id}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": greeting},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Customer*\n{customer}"},
                {"type": "mrkdwn", "text": f"*Amount*\n{amount_display}"},
                {"type": "mrkdwn", "text": f"*Recommendation*\n{decision_emoji} {decision_action or 'pending'}"},
                {"type": "mrkdwn", "text": f"*Confidence*\n{conf_pct}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*TL;DR*\n{tldr[:600] or '_no summary yet_'}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Key findings*\n{findings_text[:1500]}"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*I suggest the following actions*\n{actions_text[:1900]}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        ":raising_hand: Reply *`approve`* in this thread to fire them · "
                        "or ask any follow-up question."
                    ),
                },
            ],
        },
        {
            "type": "actions",
            "block_id": f"manthan_actions::{case_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve & Execute"},
                    "style": "primary",
                    "action_id": "manthan_approve",
                    "value": case_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Hold for review"},
                    "action_id": "manthan_hold",
                    "value": case_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open in Manthan ↗"},
                    "url": deep_link,
                    "action_id": "manthan_view",
                    "value": case_id,
                },
            ],
        },
    ]
    return blocks


# ──────────────────────────────────────────────────────────────────────
# Outbound: investigating card (replaces ":hourglass: On it" plain text)
# ──────────────────────────────────────────────────────────────────────


def build_investigating_card(
    *,
    short_id: str,
    customer_hint: str | None,
    requester_slack_id: str | None,
    deep_link: str,
    surface_label: str,
) -> list[dict[str, Any]]:
    """The "Checking it out" card posted as the first acknowledgment.

    Sketch annotation: "This should be enclosed in a box pretty way" with
    a URL to the case opened in the Inbox.
    """
    who = f"<@{requester_slack_id}>" if requester_slack_id else "you"
    customer_line = (
        f"*Customer (parsed)*\n{customer_hint}"
        if customer_hint
        else "*Customer*\nIdentifying from the message…"
    )
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":mag: Investigating · {short_id}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"On it, {who}. I'm pulling threads across the connected "
                    "sources (Stripe, Salesforce, HubSpot, Intercom, Zendesk, "
                    "Slack, Notion, PostHog, Sentry, Datadog, PagerDuty)."
                ),
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": customer_line},
                {"type": "mrkdwn", "text": f"*Triggered via*\n{surface_label}"},
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Watch live in Manthan ↗"},
                    "url": deep_link,
                    "action_id": "manthan_view",
                    "value": "investigating",
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "I'll drop the brief here as soon as I'm done - usually 30–60 seconds.",
                },
            ],
        },
    ]


# ──────────────────────────────────────────────────────────────────────
# Outbound: actions-performed close card
# ──────────────────────────────────────────────────────────────────────


def build_actions_performed_card(
    *,
    short_id: str,
    customer: str,
    executed: list[dict[str, str]],
    failed: list[dict[str, str]],
    signer_display: str | None,
    deep_link: str,
) -> list[dict[str, Any]]:
    """The "Actions performed · Case closed" card.

    `executed` and `failed` are lists of {emoji, title, ref_text, ref_url?}.
    `signer_display` is the display name + role of the operator who
    approved, e.g. "Mark Johnson, Director of Revenue Accounting".
    """
    def _format_row(a: dict[str, str], glyph: str) -> str:
        line = f"{glyph} *{a.get('title', 'Action')}*"
        ref = a.get("ref_text")
        url = a.get("ref_url")
        if ref and url:
            line += f"  ·  <{url}|{ref}>"
        elif ref:
            line += f"  ·  `{ref}`"
        return line

    executed_text = "\n".join(_format_row(a, ":white_check_mark:") for a in executed) or "-"
    failed_text = "\n".join(_format_row(a, ":warning:") for a in failed)

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":checkered_flag: Case closed · {short_id}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Customer*\n{customer}"},
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*Approved by*\n{signer_display}"
                        if signer_display
                        else "*Approved by*\n(autonomous)"
                    ),
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Actions performed*\n{executed_text[:2000]}",
            },
        },
    ]

    if failed_text:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Did not complete*\n{failed_text[:1000]}",
                },
            }
        )

    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Open the closed case in Manthan ↗",
                    },
                    "url": deep_link,
                    "action_id": "manthan_view",
                    "value": "closed",
                },
            ],
        }
    )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "Need to revisit? Reply in this thread - I'll re-open "
                        "the conversation and re-investigate if needed."
                    ),
                },
            ],
        }
    )
    return blocks


# ──────────────────────────────────────────────────────────────────────
# Customer-name parsing - pulled out of the mention text for the
# investigating card.
# ──────────────────────────────────────────────────────────────────────


def parse_customer_hint(text: str) -> str | None:
    """Pull a likely customer reference out of free-text Slack mention.

    Heuristic catches:
      "by xxx@gmail.com"   →  xxx@gmail.com
      "for Northwind"      →  Northwind
      "about ACME Corp"    →  ACME Corp
      "dispute by Quill"   →  Quill
    Returns None if nothing matches.
    """
    import re

    if not text:
        return None
    # Email - common pattern.
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if m:
        return m.group(0)
    # Phrases.
    for word in ("by", "for", "about", "from"):
        m = re.search(
            rf"\b{word}\s+([A-Z][A-Za-z0-9&_\.\- ]{{1,40}}?)(?:\s|[.,?!]|$)",
            text,
        )
        if m:
            return m.group(1).strip()
    return None


# ──────────────────────────────────────────────────────────────────────
# Approval-command detection
# ──────────────────────────────────────────────────────────────────────


_APPROVAL_TOKENS = {
    "approve",
    "approved",
    "approveit",
    "approve.",
    "go",
    "go ahead",
    "fire",
    "fire it",
    "ship it",
    "lgtm",
    "yes",
    "y",
    "ok",
    "okay",
    ":+1:",
    ":thumbsup:",
    ":white_check_mark:",
    ":ok_hand:",
}


def is_approval_text(text: str) -> bool:
    """True when a thread reply looks like an approval verb.

    We're permissive - false positives just trigger the e-signature
    question, which is a graceful confirmation step. Better one extra
    "your name + role please?" than a missed approve."""
    if not text:
        return False
    t = text.strip().lower()
    if t in _APPROVAL_TOKENS:
        return True
    # Things like "approve please" / "approve this"
    first_word = t.split()[0] if t else ""
    if first_word in {"approve", "approved", "go", "yes", "ship", "fire", "lgtm"}:
        return True
    if t.startswith("approve") or t.startswith("go ahead"):
        return True
    return False


def parse_signature_reply(text: str) -> tuple[str, str] | None:
    """Parse a Slack reply that should contain Full Name + Role.

    Accepted shapes (case-insensitive):
      "Mark Johnson, Director of Revenue Accounting"
      "Mark Johnson - Director of Revenue Accounting"
      "Name: Mark Johnson | Role: Director ..."
      "Mark Johnson (Director ...)"

    Returns (full_name, role) or None if we can't separate the two.
    Single-line replies without a comma/dash/pipe fail parsing and the
    caller asks the operator to retry with the canonical shape.
    """
    if not text:
        return None
    cleaned = text.strip().rstrip(".")
    if not cleaned:
        return None

    # Labelled shape: "Name: X, Role: Y" / "Name - X | Role - Y"
    import re

    name_match = re.search(r"name\s*[:\-=]\s*([^,|\n]+)", cleaned, re.IGNORECASE)
    role_match = re.search(r"role\s*[:\-=]\s*([^,|\n]+)", cleaned, re.IGNORECASE)
    if name_match and role_match:
        return name_match.group(1).strip(" .,"), role_match.group(1).strip(" .,")

    # Parenthesised role: "Mark Johnson (Director ...)"
    paren = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", cleaned)
    if paren:
        return paren.group(1).strip(), paren.group(2).strip()

    # Separator-based: ",", "-", "|"
    for sep in (",", " - ", " - ", " | ", " · "):
        if sep in cleaned:
            parts = [p.strip() for p in cleaned.split(sep, 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                return parts[0], parts[1]
    return None


def build_signature_prompt_text(short_id: str) -> str:
    """In-thread message asking for Full Name + Role."""
    return (
        f":lock: Before I fire the actions on *{short_id}*, I need a "
        "1-line audit signature.\n"
        "*Reply with your full name and role* - e.g. "
        "_Mark Johnson, Director of Revenue Accounting_."
    )


def build_signature_invalid_text() -> str:
    return (
        ":warning: Couldn't separate name from role. Reply in the shape "
        "*Full name, Role* - e.g. _Mark Johnson, Director of Revenue Accounting_."
    )


async def post_brief_to_thread(
    *,
    org_id: UUID,
    case_id: UUID,
    channel_id: str,
    thread_ts: str | None,
) -> str | None:
    """Post (or re-post) the brief card in a Slack channel/thread.

    If thread_ts is given, reply in that thread. Otherwise post a fresh
    message in the channel.

    Saves the resulting message ts on the case so thread replies route
    back to the same case.
    """
    async with get_pool().acquire() as conn:
        case_row = await conn.fetchrow(
            """
            SELECT c.id, c.short_id, c.customer_ref, c.amount_minor, c.currency,
                   c.decision_action, c.decision_confidence,
                   c.trigger_payload->>'slack_user_id' AS requester_slack_id
            FROM cases c
            WHERE c.id = $1
            """,
            case_id,
        )
        if case_row is None:
            return None
        brief_row = await conn.fetchrow(
            """
            SELECT data FROM events
            WHERE org_id = $1
              AND thread_id = (SELECT thread_id FROM cases WHERE id = $2)
              AND type = 'brief_drafted'
            ORDER BY seq DESC LIMIT 1
            """,
            org_id, case_id,
        )
        finding_rows = await conn.fetch(
            """
            SELECT text FROM findings
            WHERE case_id = $1
            ORDER BY confidence DESC NULLS LAST, seq ASC
            LIMIT 3
            """,
            case_id,
        )
        action_rows = await conn.fetch(
            """
            SELECT type, payload FROM actions
            WHERE case_id = $1 AND status IN ('drafted', 'awaiting_approval')
            ORDER BY seq ASC
            LIMIT 8
            """,
            case_id,
        )

    brief_data = (brief_row["data"] if isinstance(brief_row["data"], dict) else {}) if brief_row else {}
    tldr = str(brief_data.get("tldr") or "")
    top_findings = [r["text"] for r in finding_rows]

    customer = case_row["customer_ref"] or "(unknown customer)"
    amount = case_row["amount_minor"] or 0
    currency = (case_row["currency"] or "usd").upper()
    amount_display = f"${amount / 100:,.2f} {currency}"

    web_origin = os.environ.get("WEB_APP_ORIGIN", "https://demo.manthan.quest")
    deep_link = f"{web_origin}/app/case/{case_id}"

    suggested_actions = [
        _action_block_summary(r["type"], r["payload"]) for r in action_rows
    ]

    blocks = build_brief_blocks(
        short_id=case_row["short_id"],
        customer=customer,
        amount_display=amount_display,
        tldr=tldr,
        decision_action=case_row["decision_action"],
        decision_confidence=case_row["decision_confidence"],
        top_findings=top_findings,
        suggested_actions=suggested_actions,
        deep_link=deep_link,
        case_id=str(case_id),
        requester_slack_id=case_row["requester_slack_id"],
    )

    client = _client()
    try:
        resp = client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"Manthan brief - {case_row['short_id']} · {customer}",
            blocks=blocks,
        )
    except SlackApiError as e:
        logger.exception("failed to post Slack brief: %s", e)
        return None

    posted_ts = resp.get("ts")

    # Save (channel, ts) on the case so thread replies route correctly.
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE cases
            SET trigger_payload = trigger_payload ||
                jsonb_build_object(
                    'slack_thread_ts', $1::text,
                    'slack_thread_channel', $2::text
                )
            WHERE id = $3
            """,
            posted_ts, channel_id, case_id,
        )

    # Attach the asky-PDF brief to the same thread. This is segment 4's
    # "asky PDF" + thread Q&A combo: PDF as record, thread for follow-ups.
    try:
        from manthan_api.services.brief_pdf import render_brief_pdf
        pdf_bytes = await render_brief_pdf(org_id, case_id)
        client.files_upload_v2(
            channel=channel_id,
            thread_ts=posted_ts,
            filename=f"manthan-brief-{case_row['short_id']}.pdf",
            content=pdf_bytes,
            initial_comment="Brief attached for your records.",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("PDF upload to Slack failed: %s", e)

    return posted_ts


async def post_reply_to_thread(
    *,
    channel_id: str,
    thread_ts: str,
    text: str,
) -> None:
    """Plain text reply in a Slack thread. Used for chat follow-up replies."""
    client = _client()
    try:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=text,
        )
    except SlackApiError as e:
        logger.warning("slack thread reply failed: %s", e)


async def post_blocks_to_thread(
    *,
    channel_id: str,
    thread_ts: str,
    text: str,
    blocks: list[dict[str, Any]],
) -> None:
    """Block Kit reply in a Slack thread - used for the actions-performed
    card. `text` is the fallback shown on notification previews."""
    client = _client()
    try:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=text,
            blocks=blocks,
        )
    except SlackApiError as e:
        logger.warning("slack blocks reply failed: %s", e)


# ──────────────────────────────────────────────────────────────────────
# Block Kit: signature modal
# ──────────────────────────────────────────────────────────────────────


def build_signature_modal(case_id: str, short_id: str) -> dict[str, Any]:
    """E-signature modal: Full Name + Role, plus an optional note.

    Sketch annotation: "Manthan asks for e-signature, basically asks user
    FULL Name and Role". Both fields are required; both are stored on
    the action payload's `approval_signature` field so the audit log can
    reconstruct who signed off on what.
    """
    return {
        "type": "modal",
        "callback_id": "manthan_approve_modal",
        "private_metadata": case_id,
        "title": {"type": "plain_text", "text": f"Approve {short_id[:16]}"},
        "submit": {"type": "plain_text", "text": "Sign & Execute"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"You're about to fire the drafted actions for "
                        f"*{short_id}*. This will execute against real source "
                        "systems (Stripe, Notion, etc.)."
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":lock: *Audit signature* - required for SOX-grade "
                        "trail. Stored on the action payload + posted in "
                        "the thread."
                    ),
                },
            },
            {
                "type": "input",
                "block_id": "full_name_input",
                "label": {"type": "plain_text", "text": "Your full name"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "full_name",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. Mark Johnson",
                    },
                    "max_length": 120,
                },
            },
            {
                "type": "input",
                "block_id": "role_input",
                "label": {"type": "plain_text", "text": "Your role"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "role",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. Director, Revenue Accounting",
                    },
                    "max_length": 120,
                },
            },
            {
                "type": "input",
                "block_id": "note_input",
                "optional": True,
                "label": {
                    "type": "plain_text",
                    "text": "Notes for the audit log (optional)",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "note",
                    "multiline": True,
                    "max_length": 1000,
                },
            },
        ],
    }


# ──────────────────────────────────────────────────────────────────────
# Action summary helper - turns one drafted action into a brief Slack-
# friendly row used by the brief card and the actions-performed card.
# ──────────────────────────────────────────────────────────────────────


def _action_block_summary(kind: str, payload: dict[str, Any] | None) -> dict[str, str]:
    """Produce {emoji, title, target} for a Slack bullet."""
    p = payload or {}
    emoji = _emoji_for_kind(kind)
    title = "Action"
    target = ""

    if kind == "stripe_refund":
        amt = p.get("amount_minor") or 0
        charge = p.get("charge") or ""
        title = f"Refund ${amt/100:,.0f} via Stripe"
        target = f"on {_short_ref(charge)}" if charge else ""
    elif kind == "stripe_dispute_response":
        dispute = p.get("dispute") or ""
        submit = p.get("submit")
        title = "Submit dispute evidence to Stripe"
        target = f"{_short_ref(dispute)} ({'submit' if submit else 'draft only'})"
    elif kind == "customer_email":
        subj = p.get("subject") or ""
        to = p.get("to") or ""
        title = f"Email customer - {subj[:80]}" if subj else "Email customer"
        target = f"to {to}" if to else ""
    elif kind == "notion_decision_log":
        nt = p.get("title") or ""
        title = "Append Notion decision log"
        target = nt[:80] if nt else ""
    elif kind == "slack_brief":
        ch = p.get("channel") or ""
        title = "Post brief to Slack"
        target = f"#{ch}" if ch else ""
    elif kind == "hubspot_note":
        title = "Append HubSpot CRM note"
    else:
        title = kind.replace("_", " ").title()

    return {"emoji": emoji, "title": title, "target": target}


def _emoji_for_kind(kind: str) -> str:
    if kind.startswith("stripe_"):
        return ":credit_card:"
    if kind.startswith("notion_"):
        return ":notebook:"
    if kind.startswith("slack_"):
        return ":speech_balloon:"
    if kind.startswith("hubspot_"):
        return ":bust_in_silhouette:"
    if kind in ("customer_email",):
        return ":email:"
    return ":zap:"


def _short_ref(ref: str | None) -> str:
    if not ref:
        return ""
    if len(ref) <= 12:
        return ref
    return f"{ref[:6]}…{ref[-4:]}"


def open_modal(trigger_id: str, view: dict[str, Any]) -> None:
    """Open a Block Kit modal in response to a button click."""
    client = _client()
    try:
        client.views_open(trigger_id=trigger_id, view=view)
    except SlackApiError as e:
        logger.warning("views_open failed: %s", e)
