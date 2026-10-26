"""Resend adapter - send customer emails.

Two paths the agent can take:

1. **Branded template (preferred)** - payload carries
   `template='resolution'|'action_item'|'ack'` plus structured fields
   (`headline`, `body_paragraphs`, `customer_name`, `stripe_dispute_url`,
   etc.). The adapter renders Manthan-branded HTML via
   `services.email_templates` so every outbound email looks like it
   came from the same brand voice.

2. **Raw HTML (escape hatch)** - payload carries `body_html` directly.
   Useful for power users / unusual cases. The agent's prompt should
   default to (1) unless it explicitly needs custom HTML.

Either way: From defaults to "Manthan <manthan@demo.manthan.quest>" so
the customer sees the brand domain; Reply-To routes back to the
inbound mailbox so their replies hit the webhook.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import resend

from manthan_api.config import get_settings

from . import AdapterError, ExecutionResult


def send(payload: dict[str, Any], idempotency_key: str) -> ExecutionResult:
    """Send an email via Resend.

    Payload keys (template path):
      template: "resolution" | "action_item" | "ack"
      to: str | list[str]
      customer_name: str (optional, fallback parsed from to)
      headline: str (required for resolution / action_item)
      body_paragraphs: list[str] (one paragraph per item)
      stripe_dispute_url: str (optional)
      signed_by: str (optional - "Mark Johnson, Director, RevOps")
      subject: str (override; default generated from headline + case_id)
      case_short_id: str (optional; threaded into footer)
      purpose: str (action_item only - eyebrow like "Quick question")

    Payload keys (raw path):
      to, subject, body_text, body_html
      cc, bcc
      in_reply_to, references (set the headers for email-client threading)
    """
    settings = get_settings()
    api_key = settings.resend_api_key or os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise AdapterError("RESEND_API_KEY missing - set in .env to enable email sends")
    resend.api_key = api_key

    to = payload.get("to")
    if not to:
        raise AdapterError("resend.send payload requires `to`")

    # Resolve from + reply-to with sensible defaults pulled from env.
    from_display = (
        payload.get("from")
        or os.environ.get("MANTHAN_EMAIL_FROM")
        or settings.resend_from_address
        or "Manthan <manthan@demo.manthan.quest>"
    )
    reply_to = (
        payload.get("reply_to")
        or os.environ.get("MANTHAN_EMAIL_REPLY_TO")
        or settings.resend_from_address
    )

    # ── Branded-template path ──
    template = payload.get("template")
    if template:
        primary_to = to if isinstance(to, str) else to[0]
        try:
            from manthan_api.services.email_dispatcher import render_branded_html
            subject, body_html, body_text = asyncio.run(
                render_branded_html(
                    template=template,
                    case_short_id=str(payload.get("case_short_id") or ""),
                    customer_email=primary_to,
                    customer_name=payload.get("customer_name"),
                    payload=payload,
                )
            )
        except RuntimeError as e:
            # asyncio.run inside an existing loop - we should be running
            # inside the actor's `asyncio.to_thread`, so no loop in this
            # thread. But defend in case the call shape changes.
            raise AdapterError(f"branded render failed: {e}")
        except Exception as e:  # noqa: BLE001
            raise AdapterError(f"branded render failed: {e}")
        # Allow the agent to override subject if it wants.
        subject = payload.get("subject") or subject
    else:
        # ── Raw path ──
        subject = payload.get("subject")
        body_text = payload.get("body_text", "")
        # Accept either `body_html` (Resend's native key) or `html` (the
        # name the investigator templater uses). Without the fallback,
        # branded HTML emails ship as plain-text only.
        body_html = payload.get("body_html") or payload.get("html")
        if not subject:
            raise AdapterError("resend.send payload requires `subject` when no template is set")

    # Demo-mode delivery override: in production the brief shows the
    # real customer email (e.g. billing@aperture-analytics.co) and the
    # Resend send goes there. For the design-partner demo we keep the
    # visible "to" intact in the action payload + brief, but ROUTE the
    # actual send to the operator's real inbox via this env var. The
    # subject gets a `[demo → <real>]` prefix so the operator's inbox
    # is clear about which customer's email this would have been.
    #
    # Per-case bypass: when the trigger plumbs the operator's own login
    # email as `to` (Aperture demo flow), we want the email to land at
    # that exact address with no rewrite or subject prefix. The
    # enrichment loop sets `bypass_demo_override: True` on the payload
    # for those cases.
    actual_to = to
    if payload.get("bypass_demo_override"):
        pass  # keep `to` as-is, no env override, no subject prefix
    else:
        override = os.environ.get("MANTHAN_DEMO_EMAIL_OVERRIDE")
        if override and isinstance(to, str) and to.lower() != override.lower():
            actual_to = override
            subject = f"[demo → {to}] {subject}"

    params: dict[str, Any] = {
        "from": from_display,
        "to": [actual_to] if isinstance(actual_to, str) else actual_to,
        "subject": subject,
    }
    if body_html:
        params["html"] = body_html
    if body_text:
        params["text"] = body_text
    if payload.get("cc"):
        params["cc"] = payload["cc"]
    if payload.get("bcc"):
        params["bcc"] = payload["bcc"]
    if reply_to:
        params["reply_to"] = reply_to

    # Threading headers - only used by the raw path. We deliberately
    # DON'T set these on the branded path: the email-as-identifier
    # routing means we don't need RFC-2822 threading to find the case.
    headers = {"X-Manthan-Idempotency-Key": idempotency_key}
    in_reply_to = payload.get("in_reply_to")
    if in_reply_to:
        headers["In-Reply-To"] = in_reply_to
    refs = payload.get("references")
    if refs:
        if isinstance(refs, list):
            headers["References"] = " ".join(refs)
        else:
            headers["References"] = str(refs)
    params["headers"] = headers

    # Tag for Resend analytics - separates ack from resolution etc.
    params["tags"] = [
        {"name": "manthan_template", "value": str(template or "raw")},
    ]

    try:
        r = resend.Emails.send(params)
    except Exception as e:  # noqa: BLE001
        raise AdapterError(f"resend send failed: {e}")

    email_id = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
    if not email_id:
        raise AdapterError(f"resend send returned no id: {r}")
    return ExecutionResult(
        external_ref=str(email_id),
        summary=f"Email sent to {to}: {subject}",
        raw={
            "id": email_id,
            "to": to,
            "subject": subject,
            "template": template or "raw",
        },
    )
