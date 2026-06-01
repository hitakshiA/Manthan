"""Resend Receiving API - fetch the actual email body from a webhook id.

Resend's `email.received` webhook delivers metadata only (from, to, subject,
message_id, email_id) - the body lives behind a separate Receiving API call
keyed by the email_id. This module is a thin httpx wrapper around that
endpoint:

    GET https://api.resend.com/emails/receiving/{id}
    Authorization: Bearer <RESEND_API_KEY>

Response carries `from`, `to`, `subject`, `text`, `html`, `headers`,
`attachments`, `raw.download_url`. We only need text + html for the agent
to investigate.

Why a separate module (rather than inlining in email_webhook.py):
  - Keeps the webhook handler thin and testable.
  - Future paths (e.g. polling `/emails/receiving` for missed webhooks)
    can reuse this client.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("manthan_api.resend_inbound")

_BASE_URL = "https://api.resend.com"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def fetch_received_email(email_id: str) -> dict[str, Any] | None:
    """Fetch the full received-email record by id.

    Returns the parsed response dict on success, None on any error
    (missing API key, network failure, non-2xx, malformed JSON). The
    caller decides how to degrade - typically: continue creating the
    case with whatever metadata the webhook gave us, and log the gap.
    """
    if not email_id:
        return None
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning(
            "RESEND_API_KEY missing - cannot fetch received email body for id=%s",
            email_id,
        )
        return None
    url = f"{_BASE_URL}/emails/receiving/{email_id}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            r = await http.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as e:
        logger.warning("resend receiving fetch network error id=%s: %s", email_id, e)
        return None
    if r.status_code >= 400:
        logger.warning(
            "resend receiving fetch HTTP %d id=%s body=%s",
            r.status_code, email_id, r.text[:200],
        )
        return None
    try:
        return r.json()
    except ValueError as e:
        logger.warning("resend receiving fetch JSON parse failed id=%s: %s", email_id, e)
        return None
