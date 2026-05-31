"""Inbound webhooks - Stripe, Slack (events), Resend (inbound mail).

This is the TRIGGER half of the system: external services push real
billing events here, we verify the signature, dedupe by event id, and
write a `case_opened` row that the investigate worker picks up via
LISTEN/NOTIFY.

Stripe events we react to:
  - charge.dispute.created       → chargeback fight/refund decision
  - radar.early_fraud_warning.created → fraud signal, refund vs. let-ride
  - invoice.payment_failed       → dunning case, retry vs. pause
  - charge.refund.updated        → refund succeeded/failed reconciliation

The case_opened payload uses `trigger_surface=stripe_webhook` and the
full Stripe event lives in `trigger_payload` so the agent can pull
charge/dispute IDs without having to parse them out of natural-language
trigger text.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import stripe
from fastapi import APIRouter, HTTPException, Request, status

from manthan_api.config import get_settings
from manthan_api.db import get_conn

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("manthan_api.webhooks")


# Stripe event types we open a case for. Everything else is ignored
# (acknowledged with 200 so Stripe stops retrying).
TRIGGERING_EVENTS = {
    "charge.dispute.created",
    "charge.dispute.funds_withdrawn",
    "radar.early_fraud_warning.created",
    "invoice.payment_failed",
    "charge.refund.updated",
}


# ──────────────────────────────────────────────────────────────────────
# POST /webhooks/stripe/{org_slug}
# ──────────────────────────────────────────────────────────────────────


@router.post("/stripe/{org_slug}", status_code=status.HTTP_200_OK)
async def stripe_webhook(org_slug: str, request: Request) -> dict[str, Any]:
    """Receive a Stripe webhook. Verifies signature, dedupes, opens a case."""
    settings = get_settings()
    secret = settings.stripe_webhook_secret
    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # Signature verification. In dev with no secret set, we still parse the
    # payload but log a warning - this lets local `stripe trigger` work
    # without `stripe listen` configured.
    if secret:
        try:
            event = stripe.Webhook.construct_event(body, sig_header, secret)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.warning("stripe webhook signature invalid: %s", e)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid signature",
            )
    else:
        if not settings.is_dev:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="STRIPE_WEBHOOK_SECRET not configured",
            )
        logger.warning("STRIPE_WEBHOOK_SECRET unset - skipping signature check (dev only)")
        try:
            event = json.loads(body.decode("utf-8"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid JSON",
            )

    event_id = event.get("id") if isinstance(event, dict) else event["id"]
    event_type = event.get("type") if isinstance(event, dict) else event["type"]
    event_obj = (event.get("data") or {}).get("object") if isinstance(event, dict) else event["data"]["object"]

    # Resolve org by slug.
    async with get_conn() as conn:
        org_row = await conn.fetchrow(
            "SELECT id FROM orgs WHERE slug = $1",
            org_slug,
        )
        if org_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"org not found: {org_slug}",
            )
        org_id = org_row["id"]

        # Idempotency: dedupe by Stripe event id. If we've already opened a
        # case for this event, ack 200 + skip. Stripe retries failures up to
        # 3 days - duplicate fires must not duplicate cases.
        already = await conn.fetchval(
            """
            SELECT 1 FROM cases
            WHERE org_id = $1
              AND trigger_surface = 'stripe_webhook'
              AND trigger_payload->>'event_id' = $2
            LIMIT 1
            """,
            org_id, event_id,
        )
        if already:
            return {"received": True, "deduplicated": True, "event_id": event_id}

    # Bail on uninteresting events with 200 (so Stripe stops retrying).
    if event_type not in TRIGGERING_EVENTS:
        return {"received": True, "ignored": True, "event_type": event_type}

    # Build a trigger payload + a human-readable trigger text. The agent
    # will use trigger_payload to extract IDs precisely, but the text helps
    # the LLM understand context.
    trigger_text, customer_ref, amount_minor, currency, case_type = _summarize_event(
        event_type, event_obj or {}
    )

    short_id = _short_id_from_event(event_type, event_obj or {})
    thread_id = uuid.uuid4()

    async with get_conn() as conn:
        async with conn.transaction():
            case_row = await conn.fetchrow(
                """
                INSERT INTO cases (
                    org_id, thread_id, short_id, status, trigger_surface,
                    trigger_payload, case_type, customer_ref, amount_minor, currency
                )
                VALUES ($1, $2, $3, 'investigating', 'stripe_webhook',
                        $4, $5, $6, $7, $8)
                RETURNING id
                """,
                org_id,
                thread_id,
                short_id,
                # asyncpg JSONB codec serializes dicts - don't json.dumps.
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "event_object": event_obj,
                },
                case_type,
                customer_ref,
                amount_minor,
                currency,
            )
            case_id = case_row["id"]

            # case_opened - the investigate worker fires off NOTIFY.
            await conn.execute(
                """
                INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                VALUES ($1, $2, 1, 'case_opened', 'stripe:webhook', $3)
                """,
                org_id, thread_id,
                {
                    "case_id": str(case_id),
                    "short_id": short_id,
                    "trigger_surface": "stripe_webhook",
                    "trigger_text": trigger_text,
                    "stripe_event_id": event_id,
                    "stripe_event_type": event_type,
                    "case_type": case_type,
                    "customer_ref": customer_ref,
                    "amount_minor": amount_minor,
                    "currency": currency,
                },
            )

    logger.info(
        "stripe webhook opened case %s (event=%s type=%s)",
        short_id, event_id, event_type,
    )
    return {
        "received": True,
        "case_id": str(case_id),
        "short_id": short_id,
        "event_type": event_type,
    }


# ──────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────


def _summarize_event(
    event_type: str, obj: dict[str, Any]
) -> tuple[str, str | None, int | None, str | None, str]:
    """Turn a Stripe event object into (trigger_text, customer_ref, amount, currency, case_type).

    The trigger_text is what the LLM reads first; the rest are projection
    columns the UI/inbox uses for filtering and display.
    """
    if event_type == "charge.dispute.created" or event_type == "charge.dispute.funds_withdrawn":
        amount = obj.get("amount")
        currency = (obj.get("currency") or "usd").lower()
        reason = obj.get("reason") or "unspecified"
        charge_id = obj.get("charge") or "(no charge id)"
        dispute_id = obj.get("id") or "(no dispute id)"
        customer = _customer_label(obj)
        text = (
            f"Stripe chargeback opened by {customer}: "
            f"${(amount or 0) / 100:,.2f} {currency.upper()} "
            f"on charge {charge_id} (dispute {dispute_id}). "
            f"Reason given: {reason}. "
            f"Evidence due {obj.get('evidence_details', {}).get('due_by') or 'unknown'}. "
            f"Decide fight vs. refund."
        )
        return text, customer, amount, currency, "chargeback"

    if event_type == "radar.early_fraud_warning.created":
        amount = (obj.get("charge_details") or {}).get("amount") or obj.get("amount")
        currency = ((obj.get("charge_details") or {}).get("currency") or "usd").lower()
        fraud_type = obj.get("fraud_type") or "unspecified"
        charge_id = obj.get("charge") or "(no charge id)"
        customer = _customer_label(obj)
        text = (
            f"Stripe Radar early-fraud warning on {customer}: "
            f"${(amount or 0) / 100:,.2f} {currency.upper()} "
            f"on charge {charge_id}. "
            f"Card-network fraud type: {fraud_type}. "
            f"Decide refund now (avoid chargeback) vs. let-ride."
        )
        return text, customer, amount, currency, "fraud_signal"

    if event_type == "invoice.payment_failed":
        amount = obj.get("amount_due")
        currency = (obj.get("currency") or "usd").lower()
        attempt = obj.get("attempt_count")
        invoice_id = obj.get("id") or "(no invoice id)"
        customer = _customer_label(obj)
        text = (
            f"Stripe invoice payment failed for {customer}: "
            f"${(amount or 0) / 100:,.2f} {currency.upper()} "
            f"on invoice {invoice_id} (attempt {attempt}). "
            f"Decide: retry, pause subscription, or escalate to dunning."
        )
        return text, customer, amount, currency, "dunning"

    if event_type == "charge.refund.updated":
        amount = obj.get("amount")
        currency = (obj.get("currency") or "usd").lower()
        refund_status = obj.get("status") or "unknown"
        charge_id = obj.get("charge") or "(no charge id)"
        customer = _customer_label(obj)
        text = (
            f"Stripe refund status changed on {customer}: "
            f"${(amount or 0) / 100:,.2f} {currency.upper()} "
            f"on charge {charge_id} - status now '{refund_status}'. "
            f"Reconcile with original case and notify customer."
        )
        return text, customer, amount, currency, "refund_reconciliation"

    # Fallback: shouldn't reach here (gated by TRIGGERING_EVENTS).
    return (f"Stripe event {event_type}", None, None, None, "stripe_event")


def _customer_label(obj: dict[str, Any]) -> str:
    """Pull a readable customer label out of a Stripe object."""
    return (
        obj.get("customer_email")
        or (obj.get("billing_details") or {}).get("email")
        or obj.get("receipt_email")
        or obj.get("customer")
        or "unknown customer"
    )


def _short_id_from_event(event_type: str, obj: dict[str, Any]) -> str:
    """Generate a short_id deterministic from the Stripe event for traceability.

    e.g. dispute du_1Abc234DefGhi → DSP-1ABC23.
    """
    prefix = {
        "charge.dispute.created": "DSP",
        "charge.dispute.funds_withdrawn": "DSP",
        "radar.early_fraud_warning.created": "EFW",
        "invoice.payment_failed": "INV",
        "charge.refund.updated": "RFD",
    }.get(event_type, "STR")
    ext_id = obj.get("id") or ""
    # Strip the type prefix (du_, ch_, in_, etc.), then keep only alnum, take 6.
    suffix_raw = ext_id.split("_", 1)[1] if "_" in ext_id else ext_id
    suffix = "".join(c for c in suffix_raw if c.isalnum())[:6].upper()
    if not suffix:
        import secrets
        suffix = f"{secrets.randbelow(900000) + 100000}"
    return f"{prefix}-{suffix}"
