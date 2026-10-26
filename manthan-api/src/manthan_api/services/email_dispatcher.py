"""Email dispatcher - single send path for Manthan-branded customer email.

Used by:
  - api/email_webhook.py        → send_ack_email (auto-ack on case open)
  - adapters/resend.py          → render_branded_html for agent-drafted
                                   customer_email actions

Why a dispatcher and not just calling Resend directly:
  - One place owns the From/Reply-To choices ("manthan@miny-labs.com"
    inbound vs. "manthan@demo.manthan.quest" outbound display address).
  - One place writes the `customer_email_sent` event so the timeline +
    audit log stay accurate regardless of which surface triggered it.
  - Stripe-dispute lookups (the sketch wanted dispute IDs surfaced in
    both the ack and the resolution emails) live here, not duplicated
    across surfaces.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import UUID

from manthan_api.db import get_pool
from manthan_api.services.email_templates import (
    render_ack_email,
    render_action_email,
    render_plain_text_fallback,
    render_resolution_email,
    render_welcome_email,
)

logger = logging.getLogger("services.email_dispatcher")


# ──────────────────────────────────────────────────────────────────────
# From / Reply-To choices.
#
# Inbound mailbox = "manthan@miny-labs.com" (Resend inbound parsing).
# Outbound display = "Manthan <manthan@demo.manthan.quest>" so the brand
# domain is what the customer sees in their inbox. Reply-To still
# points to the inbound mailbox so customer replies route back through
# the webhook.
# ──────────────────────────────────────────────────────────────────────

DEFAULT_FROM_DISPLAY = os.environ.get(
    "MANTHAN_EMAIL_FROM",
    "Manthan <manthan@demo.manthan.quest>",
)
DEFAULT_REPLY_TO = os.environ.get(
    "MANTHAN_EMAIL_REPLY_TO",
    os.environ.get("RESEND_FROM_ADDRESS", "manthan@miny-labs.com"),
)


# ──────────────────────────────────────────────────────────────────────
# Public entry points
# ──────────────────────────────────────────────────────────────────────


async def send_ack_email(
    *,
    org_id: UUID,
    case_id: UUID,
    short_id: str,
    customer_email: str,
    customer_name: str,
    subject_received: str,
) -> None:
    """Send the "got your message, investigating" ack.

    Pulls a Stripe dispute id from the case's trigger_payload if the
    investigator has already linked one. (Usually it's not there yet on
    inbound; the dispute id appears later when the agent's investigation
    finds it. The ack still fires immediately without it.)"""
    stripe_dispute_id = await _stripe_dispute_for_case(case_id)

    subj, html_body = render_ack_email(
        customer_name=customer_name,
        customer_email=customer_email,
        subject_received=subject_received,
        case_short_id=short_id,
        stripe_dispute_id=stripe_dispute_id,
    )
    text_body = render_plain_text_fallback(html_body)

    external_ref = await _send_via_resend(
        to=customer_email,
        subject=subj,
        html_body=html_body,
        text_body=text_body,
        tag="auto_ack",
    )
    if external_ref:
        await _record_customer_email_sent(
            org_id=org_id,
            case_id=case_id,
            kind="ack",
            external_ref=external_ref,
            subject=subj,
            customer_email=customer_email,
        )


async def send_nudge_email(
    *,
    org_id: UUID,
    customer_email: str,
    customer_name: str,
    subject_received: str,
) -> None:
    """Send the "I see your message but it's brief" reply when the
    email-webhook's intent classifier judged the inbound as chat-shaped
    rather than an investigation request. No case is opened; this is
    purely conversational. Replies via Resend like any other ack -
    just with copy that points the user at what Manthan actually does.
    """
    short_subject = (subject_received or "your message").strip()
    if len(short_subject) > 60:
        short_subject = short_subject[:57] + "…"
    name = (customer_name or "").strip() or customer_email.split("@", 1)[0]
    subj = f"Re: {short_subject}"
    text_body = (
        f"Hi {name},\n\n"
        "Thanks for emailing! I'm Manthan, an autonomous billing "
        "investigator. I resolve chargebacks, refund requests, failed "
        "payments, and dispute responses by reading across every "
        "connected system in one query and queueing the right actions "
        "for approval.\n\n"
        "Your message was a little brief - if you'd like me to "
        "investigate, just reply with details about the dispute. "
        "Something like:\n\n"
        "  > I was charged twice for my Caldera Pro subscription on "
        "May 22 - both charges are for $89. Please refund the "
        "duplicate.\n\n"
        "  > Please dispute charge ch_xxx for $4,500 - the service "
        "wasn't delivered.\n\n"
        "Reply with the customer's details (amount, charge id, what "
        "happened) and I'll dig in across all your connected sources.\n\n"
        "- Manthan"
    )
    html_body = (
        '<div style="font-family:ui-sans-serif,system-ui,-apple-system,'
        '\'Segoe UI\',Roboto,sans-serif;font-size:14.5px;line-height:1.55;'
        'color:#1a1d20;max-width:560px;">'
        f"<p>Hi {name},</p>"
        "<p>Thanks for emailing! I'm <strong>Manthan</strong>, an "
        "autonomous billing investigator. I resolve chargebacks, refund "
        "requests, failed payments, and dispute responses by reading "
        "across every connected system in one query and queueing the "
        "right actions for approval.</p>"
        "<p>Your message was a little brief - if you'd like me to "
        "investigate, just reply with details about the dispute. "
        "Something like:</p>"
        '<blockquote style="border-left:3px solid #16d05e;background:'
        '#f7faf7;padding:8px 12px;margin:8px 0;color:#3c4040;">'
        "I was charged twice for my Caldera Pro subscription on May 22 - "
        "both charges are for $89. Please refund the duplicate."
        "</blockquote>"
        '<blockquote style="border-left:3px solid #16d05e;background:'
        '#f7faf7;padding:8px 12px;margin:8px 0;color:#3c4040;">'
        "Please dispute charge ch_xxx for $4,500 - the service wasn't "
        "delivered."
        "</blockquote>"
        "<p>Reply with the customer's details (amount, charge id, what "
        "happened) and I'll dig in.</p>"
        "<p>— Manthan</p>"
        "</div>"
    )
    await _send_via_resend(
        to=customer_email,
        subject=subj,
        html_body=html_body,
        text_body=text_body,
        tag="nudge",
    )


async def send_welcome_email(
    *,
    clerk_user_id: str,
    email: str,
    first_name: str | None,
    last_name: str | None,
    demo_url: str | None = None,
) -> bool:
    """Send the MVP welcome email and persist the dedup row.

    Idempotent: if `auth_signups.welcome_sent_at` is already set for this
    Clerk user, we no-op. Otherwise we render, send, and mark sent.
    Returns True if an email was actually sent this call.
    """
    # 1. Dedup check - INSERT ... ON CONFLICT means we claim the slot
    #    atomically. If we lose the race we return False without sending.
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO auth_signups
                (clerk_user_id, email, first_name, last_name, source)
            VALUES ($1, $2, $3, $4, 'clerk')
            ON CONFLICT (clerk_user_id) DO UPDATE
              SET clerk_user_id = EXCLUDED.clerk_user_id
            RETURNING welcome_sent_at
            """,
            clerk_user_id, email, first_name, last_name,
        )
    if row and row["welcome_sent_at"] is not None:
        logger.info("welcome email already sent (clerk_user_id=%s)", clerk_user_id)
        return False

    # 2. Render + send.
    demo = demo_url or os.environ.get(
        "WEB_APP_ORIGIN", "https://demo.manthan.quest"
    ).rstrip("/") + "/app"
    subj, html_body = render_welcome_email(
        first_name=first_name,
        email=email,
        demo_url=demo,
    )
    text_body = render_plain_text_fallback(html_body)
    external_ref = await _send_via_resend(
        to=email,
        subject=subj,
        html_body=html_body,
        text_body=text_body,
        tag="welcome_mvp",
    )

    # 3. Mark sent (only when Resend gave us a message id back).
    if external_ref:
        async with get_pool().acquire() as conn:
            await conn.execute(
                """
                UPDATE auth_signups
                SET welcome_sent_at = now(),
                    welcome_email_id = $2
                WHERE clerk_user_id = $1
                """,
                clerk_user_id, external_ref,
            )
        logger.info(
            "welcome email sent (clerk_user_id=%s email=%s msg=%s)",
            clerk_user_id, email, external_ref,
        )
        return True
    return False


async def render_branded_html(
    *,
    template: str,
    case_short_id: str,
    customer_email: str,
    customer_name: str | None,
    payload: dict[str, Any],
) -> tuple[str, str, str]:
    """Render one of the three branded templates from a payload-shape
    dict. Used by the Resend adapter when the agent's drafted action
    includes `template=resolution|action_item|ack`.

    Returns (subject, html_body, text_body). The caller (the adapter)
    threads this through Resend with the From/Reply-To shared in this
    file.
    """
    if template == "resolution":
        subj, html_body = render_resolution_email(
            customer_name=customer_name,
            customer_email=customer_email,
            headline=str(payload.get("headline") or ""),
            body_paragraphs=_split_body(payload),
            case_short_id=case_short_id,
            stripe_dispute_url=payload.get("stripe_dispute_url"),
            signed_by=payload.get("signed_by"),
            subject_override=payload.get("subject"),
        )
    elif template == "action_item" or template == "action":
        subj, html_body = render_action_email(
            customer_name=customer_name,
            customer_email=customer_email,
            purpose=str(payload.get("purpose") or "Update"),
            headline=str(payload.get("headline") or ""),
            body_paragraphs=_split_body(payload),
            case_short_id=case_short_id,
            call_to_action=payload.get("call_to_action"),
            stripe_dispute_url=payload.get("stripe_dispute_url"),
            signed_by=payload.get("signed_by"),
            subject_override=payload.get("subject"),
        )
    elif template == "ack":
        subj, html_body = render_ack_email(
            customer_name=customer_name,
            customer_email=customer_email,
            subject_received=str(payload.get("subject_received") or ""),
            case_short_id=case_short_id,
            stripe_dispute_id=payload.get("stripe_dispute_id"),
        )
    else:
        raise ValueError(f"unknown email template: {template!r}")

    text_body = render_plain_text_fallback(html_body)
    return subj, html_body, text_body


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _split_body(payload: dict[str, Any]) -> list[str]:
    """Accept either body_paragraphs (preferred) or body_text (legacy).
    Splits body_text on blank lines into paragraphs."""
    paras = payload.get("body_paragraphs")
    if isinstance(paras, list) and paras:
        return [str(p) for p in paras if str(p).strip()]
    text = str(payload.get("body_text") or payload.get("body") or "")
    if not text.strip():
        return []
    return [p.strip() for p in text.split("\n\n") if p.strip()]


async def _send_via_resend(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    tag: str,
) -> str | None:
    """Direct Resend call. Returns the email id on success, None on
    failure (logged, not raised - callers proceed with case open even
    if the ack fails to send)."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY missing - email send skipped (%s)", tag)
        return None
    try:
        import resend  # local import keeps webhook startup light
        resend.api_key = api_key
        params: dict[str, Any] = {
            "from": DEFAULT_FROM_DISPLAY,
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": text_body,
            "reply_to": DEFAULT_REPLY_TO,
            "tags": [{"name": "manthan_kind", "value": tag}],
        }
        r = resend.Emails.send(params)
        eid = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
        if eid:
            logger.info("resend send ok (kind=%s id=%s)", tag, eid)
        return str(eid) if eid else None
    except Exception as e:  # noqa: BLE001
        logger.warning("resend send failed (kind=%s): %s", tag, e)
        return None


async def _record_customer_email_sent(
    *,
    org_id: UUID,
    case_id: UUID,
    kind: str,
    external_ref: str,
    subject: str,
    customer_email: str,
) -> None:
    """Emit a `customer_email_sent` event so the UI timeline + audit log
    surface the outbound message. Same shape Slack uses for its events:
    the actor field tags the source so the prettifier can render."""
    async with get_pool().acquire() as conn:
        thread_id = await conn.fetchval(
            "SELECT thread_id FROM cases WHERE id=$1",
            case_id,
        )
        if thread_id is None:
            return
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
                    SELECT $1, $2, s, 'customer_email_sent', $3, $4 FROM next
                    """,
                    org_id, thread_id,
                    "system:email_dispatcher",
                    json.dumps({
                        "kind": kind,
                        "external_ref": external_ref,
                        "subject": subject,
                        "to": customer_email,
                    }),
                )
                return
            except Exception:
                if attempt == 4:
                    raise
                import asyncio
                await asyncio.sleep(0.02 * (attempt + 1))


async def _stripe_dispute_for_case(case_id: UUID) -> str | None:
    """If the investigation has already found a Stripe dispute that
    pertains to this case, surface its ID. We look in two places:
      1. cases.trigger_payload.stripe_dispute_id (set by webhooks)
      2. findings.citations[*] where source='stripe' and table='disputes'
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              trigger_payload->>'stripe_dispute_id' AS direct,
              (
                SELECT (citation->>'ref')
                FROM findings,
                     jsonb_array_elements(findings.citations) AS citation
                WHERE findings.case_id = cases.id
                  AND citation->>'source' = 'stripe'
                  AND citation->>'table' IN ('disputes','dispute')
                LIMIT 1
              ) AS sniffed
            FROM cases
            WHERE id = $1
            """,
            case_id,
        )
    if row is None:
        return None
    return row["direct"] or row["sniffed"]
