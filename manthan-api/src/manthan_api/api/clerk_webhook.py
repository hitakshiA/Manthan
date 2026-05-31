"""Clerk webhook - fires the MVP welcome email when a user signs up.

Wire flow:
    Clerk dashboard → POST /webhooks/clerk → verify svix signature →
    if event is `user.created` → extract primary email + name →
    `email_dispatcher.send_welcome_email` (idempotent via auth_signups
    table) → 200 OK.

Why a webhook (and not just calling send_welcome from a UI action):
    1. Clerk owns the source of truth for "user created" - webhook
       fires once per real signup, regardless of which client did it.
    2. Idempotency comes for free at the DB layer (auth_signups primary
       key on clerk_user_id), so Clerk redelivery is safe.
    3. The UI doesn't need to know about emails - auth code stays clean.

Svix signature scheme is identical to what Resend inbound uses, so we
share verification with email_webhook.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from base64 import b64decode
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from manthan_api.config import get_settings

router = APIRouter(prefix="/webhooks/clerk", tags=["clerk"])
logger = logging.getLogger("manthan_api.clerk")


@router.post("", status_code=status.HTTP_200_OK)
async def clerk_events(
    request: Request,
    background: BackgroundTasks,
) -> dict[str, Any]:
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    settings = get_settings()

    secret = getattr(settings, "clerk_webhook_secret", None) or _env_secret()
    if secret:
        if not _verify_svix(body, headers, secret):
            raise HTTPException(status_code=401, detail="invalid Clerk signature")
    elif not settings.is_dev:
        raise HTTPException(
            status_code=500,
            detail="CLERK_WEBHOOK_SECRET not configured",
        )
    else:
        logger.warning(
            "CLERK_WEBHOOK_SECRET unset - skipping signature check (dev only)"
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    event_type = payload.get("type") or payload.get("event_type") or ""
    data = payload.get("data") or {}

    if event_type == "user.created":
        try:
            args = _extract_user_args(data)
        except ValueError as e:
            # Bad payload (no email, etc.) - ack but don't try to send.
            logger.warning("user.created payload skipped: %s", e)
            return {"ok": True, "skipped": True, "reason": str(e)}
        # Background-send so we ACK Clerk within their 3s window.
        background.add_task(_send_welcome_async, **args)
        return {"ok": True, "queued": True, "event": event_type}

    # Other event types (user.updated, session.created, etc.) - ack and
    # ignore for now. Easy to extend here if we want to react to them.
    return {"ok": True, "ignored": True, "event": event_type}


def _extract_user_args(data: dict) -> dict[str, Any]:
    """Pull (clerk_user_id, email, first_name, last_name) out of the
    Clerk user.created payload. Raises ValueError if no usable email."""
    clerk_user_id = (
        data.get("id")
        or data.get("user_id")
        or ""
    )
    if not clerk_user_id:
        raise ValueError("missing clerk user id")

    # Primary email - Clerk gives an array of email_addresses with
    # primary_email_address_id pointing at the chosen one. Fall back to
    # the first email address if none is marked primary.
    primary_id = data.get("primary_email_address_id")
    emails = data.get("email_addresses") or []
    chosen = None
    for e in emails:
        if isinstance(e, dict) and e.get("id") == primary_id:
            chosen = e
            break
    if chosen is None and emails:
        chosen = emails[0] if isinstance(emails[0], dict) else None
    email = (chosen or {}).get("email_address") if chosen else None
    if not email:
        # Some payloads (test events) put email at top-level.
        email = data.get("email_address") or data.get("email")
    if not email:
        raise ValueError("no email in payload")

    first_name = (data.get("first_name") or "").strip() or None
    last_name = (data.get("last_name") or "").strip() or None
    return {
        "clerk_user_id": str(clerk_user_id),
        "email": str(email).lower(),
        "first_name": first_name,
        "last_name": last_name,
    }


async def _send_welcome_async(
    *,
    clerk_user_id: str,
    email: str,
    first_name: str | None,
    last_name: str | None,
) -> None:
    """Background-runnable wrapper around the dispatcher. Catches its
    own errors so a single failed send doesn't crash the worker."""
    try:
        from manthan_api.services.email_dispatcher import send_welcome_email
        await send_welcome_email(
            clerk_user_id=clerk_user_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("welcome email send failed (user=%s): %s", clerk_user_id, e)


# ──────────────────────────────────────────────────────────────────────
# Svix signature verification (same scheme Resend uses)
# ──────────────────────────────────────────────────────────────────────


def _env_secret() -> str | None:
    import os
    return os.environ.get("CLERK_WEBHOOK_SECRET")


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
        key = secret.encode()
    base = f"{msg_id}.{ts}.".encode() + body
    expected = hmac.new(key, base, hashlib.sha256).digest()
    expected_b64 = "v1," + _b64(expected)
    return any(hmac.compare_digest(expected_b64, s.strip()) for s in sigs.split(" "))


def _b64(data: bytes) -> str:
    from base64 import b64encode
    return b64encode(data).decode()
