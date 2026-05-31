"""Inbound email webhook - Resend delivers parsed messages here.

Routing rule (per the design sketch - "email doesn't have to be in the
same thread, but same email of user; main identifier is email of user"):

  1. Dedupe by message_id (skip exact replays).
  2. **Lookup any open email-originated case for this sender email.**
     If found → append `human_followup` event to that case. The agent's
     chat_loop replies via Resend. The fact that the customer started a
     new email thread doesn't matter - we identify them by address.
  3. Otherwise open a new case.
  4. Either way: schedule an immediate Manthan-branded ack email back
     to the customer (only on new-case path - follow-ups don't get
     re-acked because the agent will produce a real reply shortly).

Resend signs payloads with svix (svix-id / svix-timestamp / svix-signature
headers). Verify, then process.

Inbound payload shape (Resend):
    {
      "type": "email.received",
      "data": {
        "from": "jane@example.com",
        "from_name": "Jane Patel",
        "to": ["manthan@miny-labs.com"],
        "subject": "Charged twice for ...",
        "text": "Hi, I was charged twice on May 22 ...",
        "html": "...",
        "message_id": "<abc@gmail.com>",
        "received_at": "2026-05-22T14:30:00Z"
      }
    }

For dev mode (no signature secret set), we accept any payload - useful for
local testing via curl.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import uuid
from base64 import b64decode
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from manthan_api.config import get_settings
from manthan_api.db import get_conn

router = APIRouter(prefix="/webhooks/email", tags=["email"])
logger = logging.getLogger("manthan_api.email")


@router.post("/{org_slug}", status_code=status.HTTP_200_OK)
async def receive_email(
    org_slug: str,
    request: Request,
    background: BackgroundTasks,
) -> dict[str, Any]:
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    settings = get_settings()

    # Verify svix-style signature if secret is configured.
    secret = settings.resend_inbound_webhook_secret
    if secret:
        if not _verify_svix(body, headers, secret):
            raise HTTPException(status_code=401, detail="invalid webhook signature")
    elif not settings.is_dev:
        raise HTTPException(
            status_code=500,
            detail="RESEND_INBOUND_WEBHOOK_SECRET not configured",
        )
    else:
        logger.warning("RESEND_INBOUND_WEBHOOK_SECRET unset - skipping signature check (dev only)")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    # Resend wraps the email in {type, data}; accept either shape.
    email_data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    msg_id = email_data.get("message_id") or email_data.get("id") or ""
    from_addr = _normalise_address(email_data.get("from"))
    from_name = email_data.get("from_name") or ""
    subject = email_data.get("subject") or "(no subject)"
    text = email_data.get("text") or email_data.get("body_text") or ""
    html_body = email_data.get("html") or ""

    if not from_addr:
        raise HTTPException(status_code=400, detail="missing from address")

    # Resolve org.
    async with get_conn() as conn:
        org_row = await conn.fetchrow("SELECT id FROM orgs WHERE slug = $1", org_slug)
        if org_row is None:
            raise HTTPException(status_code=404, detail="org not found")
        org_id = org_row["id"]

        # Dedupe by message_id (defensive - Resend usually doesn't
        # redeliver, but the SLA contract says we never double-process).
        if msg_id:
            already = await conn.fetchval(
                """
                SELECT 1 FROM cases
                WHERE org_id = $1
                  AND trigger_surface = 'inbound_email'
                  AND trigger_payload->>'message_id' = $2
                LIMIT 1
                """,
                org_id, msg_id,
            )
            if already:
                return {"received": True, "deduplicated": True}

        # ── Email-as-identifier routing ──
        # Look for any open case with this sender as the customer_ref.
        # "Open" = anything not in a terminal state. If there's a
        # resolved-recently case (last 7 days) we ALSO match - the
        # customer is likely following up on the same issue.
        case_row = await conn.fetchrow(
            """
            SELECT id, thread_id, short_id FROM cases
            WHERE org_id = $1
              AND trigger_surface = 'inbound_email'
              AND lower(customer_ref) = $2
              AND (
                  status IN ('investigating','awaiting_approval','acting')
                  OR (status = 'resolved' AND resolved_at > now() - interval '7 days')
              )
            ORDER BY created_at DESC
            LIMIT 1
            """,
            org_id, from_addr,
        )

        if case_row is not None:
            # Same customer, open or recent case - append a follow-up.
            await _append_event_with_retry(
                conn,
                org_id=org_id,
                thread_id=case_row["thread_id"],
                type_="human_followup",
                actor=f"email:{from_addr}",
                data={
                    "message": text,
                    "intent": "general",
                    "via": "email_reply",
                    "from_addr": from_addr,
                    "from_name": from_name,
                    "subject": subject,
                    "message_id": msg_id,
                    "raw_html": html_body[:50000] if html_body else None,
                },
            )
            logger.info(
                "email follow-up routed to case %s (from=%s)",
                case_row["short_id"], from_addr,
            )
            return {
                "received": True,
                "routed_as": "followup",
                "case_id": str(case_row["id"]),
                "short_id": case_row["short_id"],
            }

        # Otherwise open a new case.
        thread_id = uuid.uuid4()
        import secrets
        short_id = f"EML-{secrets.randbelow(900000) + 100000}"

        trigger_text = (
            f"Customer email from {from_name or from_addr} <{from_addr}>:\n\n"
            f"Subject: {subject}\n\n{text[:2000]}"
        )

        async with conn.transaction():
            new_case = await conn.fetchrow(
                """
                INSERT INTO cases (
                    org_id, thread_id, short_id, status, trigger_surface,
                    trigger_payload, case_type, customer_ref
                )
                VALUES ($1, $2, $3, 'investigating', 'inbound_email',
                        $4, $5, $6)
                RETURNING id
                """,
                org_id, thread_id, short_id,
                json.dumps({
                    "message_id": msg_id,
                    "from_addr": from_addr,
                    "from_name": from_name,
                    "subject": subject,
                    "received_at": email_data.get("received_at"),
                    "raw_text": text,
                    "raw_html": html_body[:50000] if html_body else None,
                }),
                "refund_request",  # default; investigation may refine
                from_addr,
            )
            case_id = new_case["id"]
            await conn.execute(
                """
                INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                VALUES ($1, $2, 1, 'case_opened', $3, $4)
                """,
                org_id, thread_id,
                f"email:{from_addr}",
                json.dumps({
                    "case_id": str(case_id),
                    "short_id": short_id,
                    "trigger_surface": "inbound_email",
                    "trigger_text": trigger_text,
                    "from_addr": from_addr,
                    "from_name": from_name,
                    "subject": subject,
                    "message_id": msg_id,
                }),
            )

    logger.info("email opened case %s from=%s subject=%r", short_id, from_addr, subject[:60])

    # Schedule the auto-ack email - runs after we return the 200 to
    # Resend so the webhook latency stays small.
    background.add_task(
        _send_auto_ack,
        org_id=org_id,
        case_id=case_id,
        short_id=short_id,
        from_addr=from_addr,
        from_name=from_name,
        subject_received=subject,
    )

    return {"received": True, "case_id": str(case_id), "short_id": short_id}


# ──────────────────────────────────────────────────────────────────────
# Auto-ack
# ──────────────────────────────────────────────────────────────────────


async def _send_auto_ack(
    *,
    org_id,
    case_id,
    short_id: str,
    from_addr: str,
    from_name: str,
    subject_received: str,
) -> None:
    """Send the "got your message" Manthan-branded ack email."""
    try:
        from manthan_api.services.email_dispatcher import send_ack_email
        await send_ack_email(
            org_id=org_id,
            case_id=case_id,
            short_id=short_id,
            customer_email=from_addr,
            customer_name=from_name,
            subject_received=subject_received,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("auto-ack send failed for case=%s: %s", short_id, e)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _normalise_address(addr: Any) -> str:
    """Pull a bare email address out of a header value.
        'Jane Patel <jane@example.com>' → 'jane@example.com'."""
    if not addr:
        return ""
    s = str(addr).strip()
    m = re.search(r"<([^>]+)>", s)
    if m:
        s = m.group(1)
    return s.strip().lower()


async def _append_event_with_retry(
    conn,
    *,
    org_id,
    thread_id,
    type_: str,
    actor: str,
    data: dict[str, Any],
) -> None:
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
                org_id, thread_id, type_, actor, json.dumps(data),
            )
            return
        except Exception:
            if attempt == 4:
                raise
            await asyncio.sleep(0.02 * (attempt + 1))


# ──────────────────────────────────────────────────────────────────────
# Svix signature verification (Resend uses this scheme)
# ──────────────────────────────────────────────────────────────────────


def _verify_svix(body: bytes, headers: dict[str, str], secret: str) -> bool:
    msg_id = headers.get("svix-id", "")
    ts = headers.get("svix-timestamp", "")
    sigs = headers.get("svix-signature", "")
    if not msg_id or not ts or not sigs:
        return False
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_"):]
    try:
        key = b64decode(secret)
    except Exception:
        # Some secrets aren't base64 - use raw bytes.
        key = secret.encode()
    base = f"{msg_id}.{ts}.".encode() + body
    expected = hmac.new(key, base, hashlib.sha256).digest()
    expected_b64 = "v1," + _b64(expected)
    return any(hmac.compare_digest(expected_b64, s.strip()) for s in sigs.split(" "))


def _b64(data: bytes) -> str:
    from base64 import b64encode
    return b64encode(data).decode()
