"""Demo trigger endpoints - fire pre-seeded scenarios with one click.

This route exists so the demo presenter can launch each of the 3 baked
scenarios without running shell commands. UI hits it; backend synthesizes
the right inbound payload (Stripe webhook, Slack mention, or email) and
forwards to the real surface handler so the same code path runs.

Only enabled in dev mode (settings.is_dev). In prod this stays off so it
can't be used to skip-the-line a real case.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from manthan_api.config import get_settings
from manthan_api.db import get_conn, get_pool
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/demo", tags=["demo"])


# ──────────────────────────────────────────────────────────────────────
# Pre-baked scenario triggers - match the seeded fixture data
# ──────────────────────────────────────────────────────────────────────


SCENARIOS = {
    "quill": {
        "label": "Quill Logistics · $9k Q1-outage chargeback (Stripe webhook)",
        "surface": "stripe_webhook",
        "case_type": "chargeback",
        "customer_ref": "Quill Logistics",
        "amount_minor": 900000,
        "currency": "usd",
        "trigger_text": (
            "Stripe chargeback opened: Quill Logistics filed a $9,000 dispute "
            "on charge ch_3Tc27rCNe0SBMhzI0YNVF6dn (dispute du_1Tc27tCNe0SBMhzIZtlzYANU). "
            "Reason: product_not_received. Their CFO says service was down during Q1 - "
            "investigate across our 11 connected systems and recommend fight vs. refund."
        ),
        "trigger_payload": {
            "event_id": "evt_demo_quill",
            "event_type": "charge.dispute.created",
            "event_object": {
                "id": "du_1Tc27tCNe0SBMhzIZtlzYANU",
                "amount": 900000,
                "currency": "usd",
                "reason": "product_not_received",
                "charge": "ch_3Tc27rCNe0SBMhzI0YNVF6dn",
                "customer": "cus_UbEaY6PNSHT340",
                "customer_email": "ar@quill-logistics.test",
            },
        },
        "short_id_prefix": "QLO",
    },
    "vermillion": {
        "label": "Vermillion Studios · $4.5k seat-count chargeback (Slack mention)",
        "surface": "manual_slack",
        "case_type": "chargeback",
        "customer_ref": "Vermillion Studios",
        "amount_minor": 450000,
        "currency": "usd",
        "trigger_text": (
            "@manthan - Vermillion Studios just filed a chargeback for $4,500 on "
            "charge ch_3Tc2QNCNe0SBMhzI1ZxM1yrK (dispute du_1Tc2QQCNe0SBMhzImPgJOJiO). "
            "Their CFO says we billed for 25 seats but they only have 15. Look into it "
            "across the connected systems and recommend fight vs. refund."
        ),
        "trigger_payload": {
            "slack_user_id": "U_demo_presenter",
            "slack_user_name": "Demo Presenter",
            "slack_channel_id": "C_demo_cs_escalations",
            "slack_channel_name": "cs-escalations",
            "via": "demo_trigger",
        },
        "short_id_prefix": "VRM",
    },
    "aperture": {
        "label": "Aperture Analytics · $8,400 chargeback (Stripe webhook)",
        "surface": "stripe_webhook",
        "case_type": "chargeback",
        "customer_ref": "Aperture Analytics",
        "amount_minor": 840000,
        "currency": "usd",
        # Trigger text is intentionally MINIMAL - the raw signal a real
        # Stripe webhook would carry. The agent has to derive everything
        # (customer, window, claim, applicable policy, math) from the
        # actual upstream sources via Coral. No editorializing here,
        # no expected-answer hints, no list of which sources to query.
        "trigger_text": (
            "Stripe chargeback opened on charge ch_3Tch1LCNe0SBMhzI0FIYdCkF "
            "(dispute du_1Tch1OCNe0SBMhzIAppAdJjT). Amount $8,400 USD. "
            "Reason: product_not_as_described."
        ),
        "trigger_payload": {
            "event_id": "evt_demo_aperture",
            "event_type": "charge.dispute.created",
            "event_object": {
                # Exactly the shape a real Stripe charge.dispute.created
                # webhook carries. No internal workflow tags, no policy
                # hints, no expected-amount fields - those would be
                # cheating; the agent has to discover them through Coral.
                "id": "du_1Tch1OCNe0SBMhzIAppAdJjT",
                "amount": 840000,
                "currency": "usd",
                "reason": "product_not_as_described",
                "charge": "ch_3Tch1LCNe0SBMhzI0FIYdCkF",
                "customer": "cus_UbupgHb6AcYfmg",
            },
        },
        "short_id_prefix": "APR",
    },
    "maya": {
        "label": "Maya Patel · $89 duplicate-charge email (autonomous)",
        "surface": "inbound_email",
        "case_type": "refund_request",
        # In-world customer name shown throughout the brief, templated
        # emails, and HubSpot/Slack posts. The actual delivery address
        # comes from trigger_payload.from_addr (the inbound-email handler
        # source-of-truth) and gets rewritten by MANTHAN_DEMO_EMAIL_OVERRIDE
        # for demo deliveries - see resend.py.
        "customer_ref": "Maya Patel",
        "amount_minor": 8900,
        "currency": "usd",
        # Trigger text includes the duplicate charge id (ch_3Tc2dTCNe0SBMhzI0vIpjd62)
        # so _synthesize_actions can extract it via the ch_* regex and draft
        # a stripe_refund action against the right charge.
        "trigger_text": (
            "Customer email from Maya Patel <hitakshi220@gmail.com> to support@manthan.quest:\n\n"
            "Subject: Charged twice for Caldera Pro - please refund\n\n"
            "Hi, I was charged $89 twice on 2026-05-22 for my Caldera Pro subscription. "
            "Please refund the duplicate. Thanks, Maya\n\n"
            "-- enriched context (added by inbound handler) --\n"
            "Resolved customer: cus_UbF7BXDTnXgUCt (Maya Patel Design)\n"
            "Original charge:   ch_3Tc2dRCNe0SBMhzI1z6GoLeI  (2026-05-22 14:21:03 UTC, $89, succeeded)\n"
            "Duplicate charge:  ch_3Tc2dTCNe0SBMhzI0vIpjd62  (2026-05-22 14:25:09 UTC, $89, succeeded - refund this one)"
        ),
        "trigger_payload": {
            "message_id": f"<demo-maya-{uuid.uuid4()}@gmail.com>",
            "from_addr": "hitakshi220@gmail.com",
            "from_name": "Maya Patel",
            "subject": "Charged twice for Caldera Pro - please refund",
            "duplicate_charge_id": "ch_3Tc2dTCNe0SBMhzI0vIpjd62",
            "original_charge_id": "ch_3Tc2dRCNe0SBMhzI1z6GoLeI",
            "customer_id": "cus_UbF7BXDTnXgUCt",
            "via": "demo_trigger",
        },
        "short_id_prefix": "MAY",
    },
}


class TriggerRequest(BaseModel):
    """Per-trigger overrides.

    `demo_email_to` - when set, the customer_email action delivers to
    this address (the operator's own login inbox in the demo flow)
    instead of the simulated customer's address or the env-level
    `MANTHAN_DEMO_EMAIL_OVERRIDE`. Also forces the case to require
    manual approval - policy auto-approval is skipped so the operator
    gets to see + approve the brief before the email fires.
    """
    demo_email_to: str | None = None


class TriggerResponse(BaseModel):
    case_id: str
    short_id: str
    scenario: str


@router.get("/scenarios")
async def list_scenarios(ctx: TenantCtx = Depends(get_ctx)) -> dict[str, Any]:
    if not get_settings().is_dev:
        raise HTTPException(status_code=404, detail="demo triggers disabled in production")
    return {
        "scenarios": [
            {"id": k, "label": v["label"], "surface": v["surface"]}
            for k, v in SCENARIOS.items()
        ],
    }


@router.post("/trigger/{scenario_id}", response_model=TriggerResponse)
async def trigger_scenario(
    scenario_id: str,
    body: TriggerRequest | None = None,
    ctx: TenantCtx = Depends(get_ctx),
) -> TriggerResponse:
    """Fire a pre-baked scenario by id.

    Creates the case + case_opened event in one transaction; the investigate
    worker picks up the NOTIFY and starts investigating immediately.
    """
    if not get_settings().is_dev:
        raise HTTPException(status_code=404, detail="demo triggers disabled in production")

    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_id}")

    import secrets
    short_id = f"{scenario['short_id_prefix']}-{secrets.randbelow(900000) + 100000}"
    thread_id = uuid.uuid4()

    # Merge per-trigger overrides into the scenario's trigger_payload so
    # they persist on the case for the investigator + actor to consume.
    trigger_payload = dict(scenario["trigger_payload"])
    if body and body.demo_email_to:
        trigger_payload["demo_email_to"] = body.demo_email_to

    async with get_conn() as conn:
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
                ctx.org_id, thread_id, short_id, scenario["surface"],
                # asyncpg's JSONB codec already serializes dicts - DON'T json.dumps
                # (would double-encode → data->>'x' returns NULL).
                trigger_payload,
                scenario["case_type"], scenario["customer_ref"],
                scenario["amount_minor"], scenario["currency"],
            )
            case_id = case_row["id"]
            await conn.execute(
                """
                INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                VALUES ($1, $2, 1, 'case_opened', 'demo:trigger', $3)
                """,
                ctx.org_id, thread_id,
                {
                    "case_id": str(case_id),
                    "short_id": short_id,
                    "trigger_surface": scenario["surface"],
                    "trigger_text": scenario["trigger_text"],
                    "customer_ref": scenario["customer_ref"],
                    "amount_minor": scenario["amount_minor"],
                    "case_type": scenario["case_type"],
                    **trigger_payload,
                },
            )
    return TriggerResponse(
        case_id=str(case_id),
        short_id=short_id,
        scenario=scenario_id,
    )


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_demo(ctx: TenantCtx = Depends(get_ctx)) -> None:
    """Wipe live cases for the demo tenant so each take starts clean.

    Keeps: orgs, members, policy_rules, sources.
    Deletes: cases, events, findings, actions, policy_matches.
    """
    if not get_settings().is_dev:
        raise HTTPException(status_code=404, detail="demo reset disabled in production")
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM policy_matches WHERE org_id=$1", ctx.org_id)
            await conn.execute("DELETE FROM actions WHERE org_id=$1", ctx.org_id)
            await conn.execute("DELETE FROM findings WHERE org_id=$1", ctx.org_id)
            # events have ON DELETE CASCADE from thread? Let's be explicit.
            await conn.execute("DELETE FROM events WHERE org_id=$1", ctx.org_id)
            await conn.execute("DELETE FROM cases WHERE org_id=$1", ctx.org_id)
