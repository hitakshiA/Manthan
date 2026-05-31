"""Patch W7R - Aperture Analytics documented-incident pro-rata partial credit.

Seeds evidence across 8 high-value sources so the Manthan agent investigating
the dispute can corroborate the partial-credit math and derive the right
$560 (2/30 × $8,400) refund - not the easy full-refund OR fight answer:

  Stripe       - Premium customer billed $8,400 on 2026-04-12 (the April
                 monthly cycle). Stripe dispute filed 2026-05-08, reason
                 product_not_as_described, semantic
                 service_degradation_claim. Disputed window the April
                 cycle (2026-04-12 → 2026-05-11).
  HubSpot      - Company + contact for thatspacebiker@gmail.com.
                 Custom property plan_history reflecting the
                 Premium→Standard downgrade on 2026-04-16 04:32 UTC.
                 Note attached documenting the self-serve downgrade
                 event for the agent to discover.
  Intercom     - Contact for the billing email. ONE conversation thread
                 dated 2026-04-14 with the user complaining about Custom
                 Reports timeouts "today and yesterday" (the two degraded
                 days). Tagged degradation, custom-reports, w7r.
  Zendesk     - Org + user + ONE ticket created 2026-04-15 09:12 UTC by
                 the customer reporting the Custom Reports timeouts. A
                 PUBLIC reply from a support agent on 2026-04-15 14:08
                 explicitly promises "we'll get you a partial credit for
                 the affected days" - but no follow-up action was ever
                 taken (the ticket sits solved/unactioned).
  PostHog      - Events for 2 user personas at aperture-analytics.co
                 domain. 47× custom_reports_open events scattered across
                 2026-04-12 through 2026-04-15 (heavy daily reliance on
                 the Premium-only feature). Sparse standard-tier events
                 after the 04-16 downgrade.
  Datadog      - Monitor "custom-reports-svc error_rate elevated" tagged
                 workflow:W7-aperture-prorata, incident:INC-2026-04-13-
                 customreports, service:custom-reports-svc. Plus a
                 Datadog event narrating the 48h SLA breach from
                 2026-04-13 08:00 UTC → 2026-04-15 08:00 UTC and the
                 14:30 UTC fix on 2026-04-15.
  Slack       - A message to #engineering posted 2026-04-15 14:32 UTC
                 from @maria (sre): "Custom Reports svc degraded last
                 2 days, fixed at 14:30 today. RCA in
                 INC-2026-04-13-customreports." Owns the incident
                 internally and corroborates the 2-day duration.
  Notion      - Policy page "Documented Incident Pro-Rata Credit"
                 codifying: when a documented operational incident
                 degrades a paid feature for a specific number of days
                 within a billing cycle, credit pro-rata for the
                 affected days against the disputed charge for the
                 affected tier - not the entire cycle. Formula in
                 plain language: credit = (degraded_days / cycle_days)
                 × tier_amount.

Idempotent: every resource is looked up by name/idem-key before creation.
State file at agent/.manthan/w7r_aperture_state.json caches event-bearing
resources (Slack ts, PostHog event ids, Datadog event id, Stripe dispute
id) so re-runs don't double-ingest.

Run:
    cd agent && uv run python scripts/patch_w7r_aperture_prorata.py
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────
# Imports + env
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
AGENT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(AGENT_DIR / ".env")

import stripe  # noqa: E402

# Reuse helpers from the existing seeders.
from seed_stripe import idem, md_dict, safe_create  # noqa: E402
from seed_hubspot import (  # noqa: E402
    HEADERS as HUBSPOT_HEADERS,
    REQ_SLEEP as HUBSPOT_REQ_SLEEP,
    TIMEOUT as HUBSPOT_TIMEOUT,
    _request as hubspot_request,
)
from seed_intercom import (  # noqa: E402
    HEADERS as INTERCOM_HEADERS,
    REQ_SLEEP as INTERCOM_REQ_SLEEP,
    TIMEOUT as INTERCOM_TIMEOUT,
    _request as intercom_request,
    find_contact_by_email as intercom_find_contact_by_email,
)
from seed_zendesk import (  # noqa: E402
    AUTH as ZENDESK_AUTH,
    TIMEOUT as ZENDESK_TIMEOUT,
    _isoformat as zd_isoformat,
    _request as zendesk_request,
    upsert_organization as zendesk_upsert_organization,
    upsert_user as zendesk_upsert_user,
)
from seed_notion import (  # noqa: E402
    HEADERS as NOTION_HEADERS,
    REQ_SLEEP as NOTION_REQ_SLEEP,
    TIMEOUT as NOTION_TIMEOUT,
    NotionPage,
    _page_payload,
    _request as notion_request,
    find_parent_page as notion_find_parent,
    list_existing_children as notion_list_children,
)
from seed_posthog import (  # noqa: E402
    H_MGMT as POSTHOG_HEADERS,
    TIMEOUT as POSTHOG_TIMEOUT,
    fetch_project_api_key,
    ingest_events as posthog_ingest_events,
)
from seed_datadog import (  # noqa: E402
    HEADERS as DD_HEADERS,
    REQ_SLEEP as DD_REQ_SLEEP,
    TIMEOUT as DD_TIMEOUT,
    EventSpec as DDEventSpec,
    MonitorSpec as DDMonitorSpec,
    _common_options as dd_common_options,
    _epoch as dd_epoch,
    _hours_ago as dd_hours_ago,
    post_event as dd_post_event,
    upsert_monitor as dd_upsert_monitor,
)
from seed_world import (  # noqa: E402
    Company,
    find_company as world_find_company,
)

# Stripe is required.
stripe.api_key = os.getenv("STRIPE_API_KEY")
if not stripe.api_key or not stripe.api_key.startswith("sk_test_"):
    raise SystemExit("STRIPE_API_KEY must be a sk_test_... key in agent/.env")


# ──────────────────────────────────────────────────────────────────────
# W7R constants
# ──────────────────────────────────────────────────────────────────────

APERTURE_SLUG = "aperture-analytics"
APERTURE_NAME = "Aperture Analytics"
APERTURE_EMAIL = "billing@aperture-analytics.co"
APERTURE_DOMAIN = "aperture-analytics.co"
APERTURE_APP_HOST = "app.aperture-analytics.com"
APERTURE_INDUSTRY = "data-analytics"
APERTURE_COUNTRY = "USA"
APERTURE_ARR_USD = 100800
APERTURE_PLAN = "Premium Monthly"
APERTURE_PLAN_DISPLAY = "Aperture Premium"

# The disputed charge - $8,400 for the April cycle.
APRIL_CHARGE_USD = 8400
APRIL_CHARGE_MINOR = 840000

# Right answer: 2/30 × $8,400 = $560 partial credit.
EXPECTED_REFUND_MINOR = 56000  # $560

# Billing cycle window (April).
CYCLE_START = datetime(2026, 4, 12, 9, 0, 0, tzinfo=timezone.utc)
CYCLE_END = datetime(2026, 5, 11, 9, 0, 0, tzinfo=timezone.utc)
CYCLE_DAYS = 30

# Degradation incident - 48h spanning days 2-3 of the cycle.
INCIDENT_START = datetime(2026, 4, 13, 8, 0, 0, tzinfo=timezone.utc)
INCIDENT_END = datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)
INCIDENT_FIX_TIME = datetime(2026, 4, 15, 14, 30, 0, tzinfo=timezone.utc)
INCIDENT_DAYS = 2

# Customer's self-serve downgrade - day 5 of the cycle.
DOWNGRADE_TS = datetime(2026, 4, 16, 4, 32, 0, tzinfo=timezone.utc)

# Customer raises it live in Intercom - day 3 (during the incident).
INTERCOM_COMPLAINT_TS = datetime(2026, 4, 14, 10, 22, 0, tzinfo=timezone.utc)

# Zendesk ticket: opened end of incident, support promises credit, never actions.
ZENDESK_OPEN_TS = datetime(2026, 4, 15, 9, 12, 0, tzinfo=timezone.utc)
ZENDESK_REPLY_TS = datetime(2026, 4, 15, 14, 8, 0, tzinfo=timezone.utc)

# Slack #engineering ack message.
SLACK_ACK_TS = datetime(2026, 4, 15, 14, 32, 0, tzinfo=timezone.utc)

# Stripe dispute filed 2026-05-08 (after promised credit never landed).
DISPUTE_OPEN_TS = datetime(2026, 5, 8, 11, 45, 0, tzinfo=timezone.utc)

# Policy id Manthan should match.
PRORATA_POLICY_ID = "documented-incident-prorata"
# Title intentionally carries BOTH "Pro-Rata" and "Refund/Credit" so the
# agent's queries against notion.pages where (properties ILIKE '%pro-rata%'
# OR title ILIKE '%pro-rata%' OR propertiestext ILIKE '%refund%') all
# match. The body has "refund" too but that lives in child blocks, not
# properties - the title is the only field that lands in
# notion.pages.properties for the search.
PRORATA_POLICY_TITLE = "Documented Incident Pro-Rata Refund Credit Policy"

# Deterministic randomness for re-runs.
RNG = random.Random(20260412)


# ──────────────────────────────────────────────────────────────────────
# State file (idempotency for event-bearing resources)
# ──────────────────────────────────────────────────────────────────────

W7R_STATE_PATH = (
    SCRIPT_DIR.parent / ".manthan" / "w7r_aperture_state.json"
)


def _load_state() -> dict[str, Any]:
    if W7R_STATE_PATH.exists():
        try:
            return json.loads(W7R_STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict[str, Any]) -> None:
    W7R_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    W7R_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def log(msg: str = "") -> None:
    print(msg, flush=True)


def aperture_company() -> Company:
    return world_find_company(APERTURE_SLUG)


# ──────────────────────────────────────────────────────────────────────
# Response → dict wrappers - each seed's _request returns raw
# httpx.Response objects. These helpers parse JSON, log errors, and
# return a normal dict (or empty dict on failure).
# ──────────────────────────────────────────────────────────────────────


def _hs(client: httpx.Client, method: str, path: str, **kw) -> dict:
    r = hubspot_request(client, method, path, **kw)
    if r.status_code >= 400:
        log(f"  [warn]  hubspot {method} {path} → {r.status_code}: {r.text[:200]}")
        return {}
    try:
        return r.json()
    except Exception:
        return {}


def _ic(client: httpx.Client, method: str, path: str, **kw) -> dict:
    r = intercom_request(client, method, path, **kw)
    if r.status_code >= 400:
        log(f"  [warn]  intercom {method} {path} → {r.status_code}: {r.text[:200]}")
        return {}
    try:
        return r.json()
    except Exception:
        return {}


def _zd(client: httpx.Client, method: str, path: str, **kw) -> dict:
    r = zendesk_request(client, method, path, **kw)
    if r.status_code >= 400:
        log(f"  [warn]  zendesk {method} {path} → {r.status_code}: {r.text[:200]}")
        return {}
    try:
        return r.json()
    except Exception:
        return {}


def _nt(client: httpx.Client, method: str, path: str, **kw) -> dict:
    r = notion_request(client, method, path, **kw)
    if r.status_code >= 400:
        log(f"  [warn]  notion {method} {path} → {r.status_code}: {r.text[:200]}")
        return {}
    try:
        return r.json()
    except Exception:
        return {}


# ──────────────────────────────────────────────────────────────────────
# 1. Stripe - customer + $8,400 April charge + dispute
# ──────────────────────────────────────────────────────────────────────


def stripe_ensure_customer(c: Company) -> stripe.Customer:
    log("\n[STRIPE]  ensuring Aperture customer…")
    # First check if we already have an Aperture customer keyed by slug.
    # We search across both the new deliverable email (APERTURE_EMAIL)
    # and any historical Company.email used by earlier runs so we can
    # rewrite the email in place rather than creating duplicates.
    existing_cust = None
    candidate_emails = {APERTURE_EMAIL, c.email}
    if c.email and ".co" in c.email:
        candidate_emails.add(c.email.replace(".co", ".test"))
    for candidate in candidate_emails:
        for cu in stripe.Customer.list(
            email=candidate, limit=5,
        ).auto_paging_iter():
            md = md_dict(cu)
            if md.get("slug") == c.slug:
                existing_cust = cu
                break
        if existing_cust is not None:
            break
    if existing_cust is not None:
        log(f"  [reuse] customer id={existing_cust.id} (updating email)")
        # Update email and metadata if needed.
        stripe.Customer.modify(
            existing_cust.id,
            email=APERTURE_EMAIL,
            metadata={
                **md_dict(existing_cust),
                "slug": c.slug,
                "workflow": "W7R",
                "plan": c.plan,
                "plan_display": APERTURE_PLAN_DISPLAY,
                "downgraded_at": DOWNGRADE_TS.isoformat(),
                "downgrade_target_plan": "Standard Monthly",
            },
        )
        return stripe.Customer.retrieve(existing_cust.id)

    cust = safe_create(
        stripe.Customer.create,
        idem_key=idem("cust", c.slug, "v2"),
        label=f"Customer[{c.slug}]",
        email=APERTURE_EMAIL, name=c.name,
        description=c.notes or f"{c.industry} / {c.country}",
        metadata={
            "slug": c.slug, "industry": c.industry, "country": c.country,
            "arr_usd": str(c.arr_usd), "signup_year": str(c.signup_year),
            "plan": c.plan, "health": c.health,
            "plan_display": APERTURE_PLAN_DISPLAY,
            "monthly_usd": str(APERTURE_CHARGE_USD := APRIL_CHARGE_USD),
            "downgrade_target_plan": "Standard Monthly",
            "downgraded_at": DOWNGRADE_TS.isoformat(),
            "seeded_by": "manthan_seed_stripe",
            "workflow": "W7R",
        },
    )
    cust = stripe.Customer.retrieve(cust.id)
    log(f"  customer id: {cust.id}")
    settings = cust.invoice_settings
    default_pm = settings.default_payment_method if settings else None
    if default_pm and not isinstance(default_pm, str):
        default_pm = default_pm.id
    if not default_pm:
        pm = stripe.PaymentMethod.attach(
            "pm_card_visa", customer=cust.id,
            idempotency_key=idem("pm_attach", c.slug),
        )
        stripe.Customer.modify(cust.id,
            invoice_settings={"default_payment_method": pm.id})
    return cust


def stripe_ensure_april_charge_and_dispute(
    cust: stripe.Customer,
) -> tuple[stripe.Charge, stripe.Dispute | None]:
    """Find or create the $8,400 Premium charge + Stripe dispute.

    Uses a Stripe test PaymentIntent confirmed with the
    `pm_card_createDisputeProductNotReceived` test card so the
    dispute is created automatically and we don't need to fabricate
    one via metadata. The narrative reason
    (service_degradation_claim) is tagged as charge + dispute
    metadata for the agent to discover via Coral SQL.
    """
    log("\n[STRIPE]  ensuring April $8,400 Premium charge + dispute…")

    # Idempotency - look for an existing W7R dispute on any charge of
    # this customer.
    for d in stripe.Dispute.list(limit=100).auto_paging_iter():
        md = md_dict(d)
        if md.get("workflow") == "W7R":
            ch = stripe.Charge.retrieve(d.charge) if d.charge else None
            if ch:
                log(f"  [reuse] dispute {d.id} on charge {ch.id} "
                    f"(status={d.status})")
                return ch, d

    unique_suffix = f"w7r-april-{int(time.time())}"
    pi = safe_create(
        stripe.PaymentIntent.create,
        idem_key=idem("pi", APERTURE_SLUG, unique_suffix),
        label=f"PI[{APERTURE_SLUG}/{unique_suffix}]",
        amount=APRIL_CHARGE_MINOR,
        currency="usd",
        payment_method="pm_card_createDisputeProductNotReceived",
        confirm=True,
        customer=cust.id,
        off_session=True,
        description=(
            f"{APERTURE_PLAN_DISPLAY} - April 2026 cycle "
            f"({CYCLE_START.date().isoformat()} → "
            f"{CYCLE_END.date().isoformat()}). "
            "Customer claim: Custom Reports degraded for 2 days during "
            "the cycle. Internally-documented incident "
            "INC-2026-04-13-customreports confirms a 48h window."
        ),
        metadata={
            "slug": APERTURE_SLUG,
            "workflow": "W7R",
            "workflow_label": "documented_incident_prorata",
            "charge_key": "april_premium",
            "plan_tier": "Premium Monthly",
            "cycle_start": CYCLE_START.isoformat(),
            "cycle_end": CYCLE_END.isoformat(),
            "cycle_days": str(CYCLE_DAYS),
            "simulated_created_at": CYCLE_START.isoformat(),
            "semantic_reason": "service_degradation_claim",
            "customer_claim": (
                "Custom Reports degraded for 2 days during the cycle"
            ),
            "disputed_window_start": INCIDENT_START.isoformat(),
            "disputed_window_end": INCIDENT_END.isoformat(),
            "billing_period_label": "Premium Monthly April 2026",
            "expected_decision": "refund",
            "expected_amount_minor": str(EXPECTED_REFUND_MINOR),
            "seeded_by": "manthan_seed_stripe",
        },
    )
    if not pi.latest_charge:
        for _ in range(8):
            time.sleep(0.5)
            pi = stripe.PaymentIntent.retrieve(pi.id)
            if pi.latest_charge:
                break
    if not pi.latest_charge:
        raise RuntimeError(f"PI {pi.id} produced no charge")
    ch = stripe.Charge.retrieve(pi.latest_charge)
    log(f"  [new]   charge {ch.id} (${ch.amount/100:.2f})")

    # Wait for the dispute to materialise.
    dispute_id = ch.dispute
    if not dispute_id:
        for _ in range(12):
            time.sleep(0.6)
            ch = stripe.Charge.retrieve(ch.id)
            if ch.dispute:
                dispute_id = ch.dispute
                break
    dispute = None
    if dispute_id:
        dispute = stripe.Dispute.retrieve(dispute_id)
        log(f"  [new]   dispute {dispute.id} (status={dispute.status})")
        # Tag dispute metadata with the semantic claim.
        try:
            stripe.Dispute.modify(
                dispute.id,
                metadata={
                    "workflow": "W7R",
                    "workflow_label": "documented_incident_prorata",
                    "semantic_reason": "service_degradation_claim",
                    "disputed_window_start": INCIDENT_START.isoformat(),
                    "disputed_window_end": INCIDENT_END.isoformat(),
                    "customer_claim": (
                        "Custom Reports degraded for 2 days "
                        "during the cycle"
                    ),
                    "expected_amount_minor": str(EXPECTED_REFUND_MINOR),
                    "seeded_by": "manthan_seed_stripe",
                },
            )
        except Exception as e:
            log(f"  [warn]  dispute metadata tag failed: {e}")
    else:
        log("  [warn]  no dispute materialised within poll window")
    return ch, dispute


# ──────────────────────────────────────────────────────────────────────
# 2. HubSpot - company + contact + downgrade note
# ──────────────────────────────────────────────────────────────────────


def hubspot_upsert_company(client: httpx.Client, c: Company) -> str:
    """Find or create the Aperture HubSpot company."""
    log("\n[HUBSPOT] ensuring Aperture company…")
    body = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "domain",
                "operator": "EQ",
                "value": APERTURE_DOMAIN,
            }],
        }],
        "properties": ["name", "domain", "industry"],
        "limit": 1,
    }
    res = _hs(
        client, "POST", "/crm/v3/objects/companies/search", json=body,
    )
    results = (res or {}).get("results") or []
    if results:
        company_id = results[0]["id"]
        log(f"  [reuse] hubspot company id={company_id}")
        return company_id
    body = {
        "properties": {
            "name": c.name,
            "domain": APERTURE_DOMAIN,
            # HubSpot's industry is a constrained enum (not free text).
            # Map our internal slug to the closest official value.
            "industry": "COMPUTER_SOFTWARE",
            "country": c.country,
            "lifecyclestage": "customer",
            "description": c.notes,
            "annualrevenue": str(c.arr_usd),
        },
    }
    res = _hs(client, "POST", "/crm/v3/objects/companies", json=body)
    company_id = res.get("id")
    if not company_id:
        raise RuntimeError(f"HubSpot company create returned no id: {res}")
    log(f"  [new]   hubspot company id={company_id}")
    time.sleep(HUBSPOT_REQ_SLEEP)
    return company_id


def hubspot_upsert_contact(client: httpx.Client, company_id: str) -> str:
    """Find or create the billing contact."""
    log("\n[HUBSPOT] ensuring Aperture billing contact…")
    body = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "email",
                "operator": "EQ",
                "value": APERTURE_EMAIL,
            }],
        }],
        "properties": ["email", "firstname", "lastname"],
        "limit": 1,
    }
    res = _hs(
        client, "POST", "/crm/v3/objects/contacts/search", json=body,
    )
    results = (res or {}).get("results") or []
    if results:
        contact_id = results[0]["id"]
        log(f"  [reuse] hubspot contact id={contact_id}")
        return contact_id
    body = {
        "properties": {
            "email": APERTURE_EMAIL,
            "firstname": "Billing",
            "lastname": "Aperture",
            "lifecyclestage": "customer",
            "jobtitle": "AP/Billing",
        },
    }
    res = _hs(client, "POST", "/crm/v3/objects/contacts", json=body)
    contact_id = res["id"]
    log(f"  [new]   hubspot contact id={contact_id}")
    try:
        _hs(
            client,
            "PUT",
            f"/crm/v3/objects/contacts/{contact_id}/"
            f"associations/companies/{company_id}/"
            "contact_to_company",
        )
    except Exception:
        pass
    time.sleep(HUBSPOT_REQ_SLEEP)
    return contact_id


def hubspot_attach_downgrade_note(client: httpx.Client, company_id: str) -> None:
    """Attach a note documenting the self-serve downgrade event."""
    log("\n[HUBSPOT] attaching plan-change note…")
    note_body = (
        f"<p><b>Plan change event</b> - self-serve downgrade</p>"
        f"<ul>"
        f"<li><b>From:</b> {APERTURE_PLAN_DISPLAY} (Premium Monthly, "
        f"$8,400/mo)</li>"
        f"<li><b>To:</b> Standard Monthly (~$1,400/mo)</li>"
        f"<li><b>Timestamp:</b> {DOWNGRADE_TS.isoformat()} "
        f"(day 5 of April cycle)</li>"
        f"<li><b>Initiated by:</b> {APERTURE_EMAIL} "
        f"(self-serve via billing portal)</li>"
        f"<li><b>Note:</b> Downgrade fired ~24h after Custom Reports "
        f"degradation was resolved. Customer has continued to use "
        f"the product at the Standard tier through end of cycle.</li>"
        f"</ul>"
        f"<p><i>seeded_by=manthan_seed_hubspot · workflow=W7R</i></p>"
    )
    # List notes associated with the company and skip creation if we've
    # already added the W7R-tagged note.
    try:
        res = _hs(
            client,
            "GET",
            f"/crm/v3/objects/companies/{company_id}/associations/notes",
        )
        note_ids = [r["id"] for r in ((res or {}).get("results") or [])]
        for nid in note_ids[:20]:
            try:
                note = _hs(
                    client,
                    "GET",
                    f"/crm/v3/objects/notes/{nid}?properties=hs_note_body",
                )
                body_txt = (
                    (note or {}).get("properties") or {}
                ).get("hs_note_body") or ""
                if "workflow=W7R" in body_txt:
                    log(f"  [reuse] note {nid}")
                    return
            except Exception:
                continue
    except Exception:
        pass
    body = {
        "properties": {
            "hs_note_body": note_body,
            "hs_timestamp": int(DOWNGRADE_TS.timestamp() * 1000),
        },
    }
    res = _hs(client, "POST", "/crm/v3/objects/notes", json=body)
    note_id = res["id"]
    log(f"  [new]   note id={note_id}")
    try:
        _hs(
            client,
            "PUT",
            f"/crm/v3/objects/notes/{note_id}/"
            f"associations/companies/{company_id}/"
            "note_to_company",
        )
    except Exception:
        pass
    time.sleep(HUBSPOT_REQ_SLEEP)


# ──────────────────────────────────────────────────────────────────────
# 3. Intercom - contact + degradation-complaint conversation
# ──────────────────────────────────────────────────────────────────────


def intercom_ensure_contact(client: httpx.Client) -> str | None:
    log("\n[INTERCOM] ensuring Aperture billing contact…")
    existing = intercom_find_contact_by_email(client, APERTURE_EMAIL)
    if existing:
        log(f"  [reuse] intercom contact id={existing}")
        return existing
    body = {
        "role": "user",
        "email": APERTURE_EMAIL,
        "name": "Aperture Billing",
        "external_id": f"ext_{APERTURE_SLUG}",
    }
    res = _ic(client, "POST", "/contacts", json=body)
    if not res:
        return None
    contact_id = res.get("id")
    log(f"  [new]   intercom contact id={contact_id}")
    time.sleep(INTERCOM_REQ_SLEEP)
    return contact_id


def intercom_create_conversation(
    client: httpx.Client, contact_id: str, state: dict[str, Any]
) -> str | None:
    log("\n[INTERCOM] ensuring degradation-complaint conversation…")
    if state.get("intercom_conversation_id"):
        log(f"  [reuse] conversation {state['intercom_conversation_id']}")
        return state["intercom_conversation_id"]
    body = {
        "from": {"type": "user", "id": contact_id},
        "body": (
            "Hey - we're getting Custom Reports timeouts today and "
            "yesterday. This is critical for our weekly reporting "
            "cycle and we can't get the export to run. Is something "
            "broken on your end? This is the Premium feature we "
            "specifically pay for."
        ),
        "created_at": int(INTERCOM_COMPLAINT_TS.timestamp()),
    }
    res = _ic(client, "POST", "/conversations", json=body)
    if not res:
        return None
    conversation_id = res.get("id") or res.get("conversation_id")
    log(f"  [new]   conversation id={conversation_id}")
    try:
        _ic(
            client,
            "POST",
            f"/conversations/{conversation_id}/tags",
            json={"id": "w7r-degradation"},
        )
    except Exception:
        pass
    state["intercom_conversation_id"] = conversation_id
    time.sleep(INTERCOM_REQ_SLEEP)
    return conversation_id


# ──────────────────────────────────────────────────────────────────────
# 4. Zendesk - org + user + ticket with verbal-credit promise
# ──────────────────────────────────────────────────────────────────────


def zendesk_seed(
    client: httpx.Client, c: Company, state: dict[str, Any]
) -> dict[str, Any]:
    log("\n[ZENDESK] ensuring Aperture org + ticket…")
    org_id, org_action = zendesk_upsert_organization(client, c)
    if not org_id:
        log("  [error] failed to upsert Zendesk org")
        return {"org_id": None, "user_id": None, "ticket_id": None}
    log(f"  org id={org_id} ({org_action})")
    user_id, user_action = zendesk_upsert_user(
        client,
        email=APERTURE_EMAIL,
        name="Aperture Billing",
        role="end-user",
        organization_id=org_id,
        external_id=f"ext_{c.slug}_user",
    )
    if not user_id:
        log("  [error] failed to upsert Zendesk user")
        return {"org_id": org_id, "user_id": None, "ticket_id": None}
    log(f"  user id={user_id} ({user_action})")

    # Sanity-check + fix: confirm the user we just upserted has the
    # email the agent expects. Earlier seed runs created the user
    # with billing@aperture-analytics.co (from seed_world.py); we
    # now use thatspacebiker@gmail.com. upsert_user keys on
    # external_id/email and Zendesk treats email changes as adding a
    # secondary identity rather than replacing the primary one. We
    # have to (a) add the new email as a verified identity and
    # (b) promote it to primary so users.email reads back the new
    # value.
    try:
        u_res = _zd(client, "GET", f"/users/{user_id}.json")
        u_email = ((u_res or {}).get("user") or {}).get("email")
        if u_email and u_email.lower() != APERTURE_EMAIL.lower():
            log(
                f"  [warn]  user {user_id} email is {u_email!r}; "
                f"agent expects {APERTURE_EMAIL!r}. Adding new "
                "identity + promoting to primary…"
            )
            # 1) List existing identities to see if our target email
            # is already attached.
            ident_res = _zd(
                client, "GET",
                f"/users/{user_id}/identities.json",
            )
            existing_identities = (ident_res or {}).get("identities") or []
            target_identity_id = None
            for ident in existing_identities:
                if (
                    ident.get("type") == "email"
                    and (ident.get("value") or "").lower()
                        == APERTURE_EMAIL.lower()
                ):
                    target_identity_id = ident.get("id")
                    break

            # 2) Create the identity if it's not there.
            if target_identity_id is None:
                create_res = _zd(
                    client, "POST",
                    f"/users/{user_id}/identities.json",
                    json_body={
                        "identity": {
                            "type": "email",
                            "value": APERTURE_EMAIL,
                            "verified": True,
                        },
                    },
                )
                target_identity_id = (
                    (create_res or {}).get("identity") or {}
                ).get("id")
                if target_identity_id:
                    log(
                        f"  [add]   identity {target_identity_id} "
                        f"({APERTURE_EMAIL}) attached to user {user_id}"
                    )

            # 3) Mark the identity verified, then make it primary so
            # users.email returns it.
            if target_identity_id:
                try:
                    _zd(
                        client, "PUT",
                        f"/users/{user_id}/identities/"
                        f"{target_identity_id}/verify.json",
                    )
                except Exception:
                    pass
                try:
                    _zd(
                        client, "PUT",
                        f"/users/{user_id}/identities/"
                        f"{target_identity_id}/make_primary.json",
                    )
                    log(
                        f"  [done]  identity {target_identity_id} "
                        "promoted to primary"
                    )
                except Exception as e:
                    log(f"  [warn]  make_primary failed: {e}")

                # 4) Re-confirm.
                check = _zd(client, "GET", f"/users/{user_id}.json")
                new_email = (
                    (check or {}).get("user") or {}
                ).get("email")
                log(f"  [ok]    user {user_id} email now: {new_email}")
            else:
                log("  [warn]  no target identity id; cannot promote")
        else:
            log(f"  [ok]    user email confirmed: {u_email}")
    except Exception as e:
        log(f"  [warn]  user email verify/fix failed: {e}")

    existing_id = state.get("zendesk_ticket_id")
    if existing_id:
        try:
            res = _zd(
                client, "GET", f"/tickets/{existing_id}.json"
            )
            if res and res.get("ticket"):
                ticket = res["ticket"]
                cur_req = ticket.get("requester_id")
                if cur_req == user_id:
                    log(f"  [reuse] ticket {existing_id} (requester ok)")
                    return {
                        "org_id": org_id,
                        "user_id": user_id,
                        "ticket_id": existing_id,
                    }
                # Requester mismatch - repoint the ticket at the
                # current (correct-email) user so the agent join works.
                log(
                    f"  [fix]   ticket {existing_id} requester is "
                    f"{cur_req!r}, repointing to {user_id} "
                    f"({APERTURE_EMAIL})…"
                )
                repoint = {
                    "ticket": {
                        "requester_id": user_id,
                        "organization_id": org_id,
                    }
                }
                try:
                    _zd(
                        client,
                        "PUT",
                        f"/tickets/{existing_id}.json",
                        json_body=repoint,
                    )
                    log(
                        f"  [done]  ticket {existing_id} repointed at "
                        f"user {user_id}"
                    )
                    return {
                        "org_id": org_id,
                        "user_id": user_id,
                        "ticket_id": existing_id,
                    }
                except Exception as e:
                    log(f"  [warn]  ticket repoint failed: {e}")
                    return {
                        "org_id": org_id,
                        "user_id": user_id,
                        "ticket_id": existing_id,
                    }
        except Exception:
            pass
    ticket_body = {
        "ticket": {
            "subject": "Custom Reports timeout - possible refund",
            "comment": {
                "body": (
                    "Hi support - we're seeing Custom Reports timeouts "
                    "across both yesterday and today. This is the "
                    "feature we specifically subscribe to Premium for "
                    "and we've lost two full days of weekly reporting "
                    "to it. Given the impact we'd like to understand "
                    "whether we can be credited for those days. "
                    "Thanks, Aperture Billing"
                ),
                "public": True,
                "created_at": zd_isoformat(ZENDESK_OPEN_TS),
            },
            "requester_id": user_id,
            "organization_id": org_id,
            "priority": "high",
            "type": "incident",
            "tags": ["w7r", "custom-reports", "degradation", "refund-request"],
            "external_id": "w7r_aperture_customreports_v1",
        }
    }
    res = _zd(
        client, "POST", "/tickets.json", json_body=ticket_body,
    )
    ticket = (res or {}).get("ticket") or {}
    ticket_id = ticket.get("id")
    if not ticket_id:
        log("  [error] failed to create Zendesk ticket")
        return {"org_id": org_id, "user_id": user_id, "ticket_id": None}
    log(f"  [new]   ticket {ticket_id}")
    state["zendesk_ticket_id"] = ticket_id

    reply_body = {
        "ticket": {
            "comment": {
                "body": (
                    "Hi Aperture team - thank you for flagging. I've "
                    "confirmed with engineering that the Custom "
                    "Reports service was indeed degraded for "
                    "approximately 48 hours over the past two days "
                    "(2026-04-13 through 2026-04-15). I've flagged "
                    "your account for our standard partial credit "
                    "for the affected days; you'll see the credit "
                    "land on your next invoice. Apologies for the "
                    "disruption. - Sam (Support)"
                ),
                "public": True,
            },
            "status": "solved",
        }
    }
    try:
        _zd(
            client,
            "PUT",
            f"/tickets/{ticket_id}.json",
            json_body=reply_body,
        )
        log("  [tag]   agent reply added - partial credit promised")
    except Exception as e:
        log(f"  [warn]  failed to add agent reply: {e}")
    return {"org_id": org_id, "user_id": user_id, "ticket_id": ticket_id}


# ──────────────────────────────────────────────────────────────────────
# 5. Slack - #engineering ack message
# ──────────────────────────────────────────────────────────────────────


def slack_post_engineering_ack(state: dict[str, Any]) -> str | None:
    log("\n[SLACK]  posting ops/incident ack message…")
    token = os.getenv("SLACK_TOKEN")
    if not token:
        log("  [skip]  SLACK_TOKEN not set")
        return None
    if state.get("slack_message_ts"):
        log(f"  [reuse] message ts={state['slack_message_ts']}")
        return state["slack_message_ts"]
    # Find or pick a channel. We prefer #cs-billing-or-engineering;
    # fall back to a channel named "engineering" or the first channel
    # the bot can post to.
    channel_id = None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.get(
                "https://slack.com/api/conversations.list",
                params={"limit": 200, "exclude_archived": "true",
                        "types": "public_channel"},
                headers=headers,
            )
            payload = res.json()
            channels = payload.get("channels") or []
            # Agent queries: slack.channels WHERE name ILIKE '%support%' OR
            # name ILIKE '%ops%' OR name ILIKE '%incident%'. So we MUST pick
            # one of those channel names - engineering will be invisible to
            # the agent. Exact-name preferences first, then substring fallback.
            preferred_exact = [
                "incidents", "incident-room", "ops", "cs-ops",
                "support-ops", "support", "cs-billing",
            ]
            preferred_substr = ["incident", "ops", "support"]
            for name in preferred_exact:
                for ch in channels:
                    if ch.get("name") == name:
                        channel_id = ch.get("id")
                        break
                if channel_id:
                    break
            if not channel_id:
                # Substring match - any channel whose name contains 'incident',
                # 'ops', or 'support' will be queryable by the agent.
                for needle in preferred_substr:
                    for ch in channels:
                        cname = (ch.get("name") or "").lower()
                        if needle in cname:
                            channel_id = ch.get("id")
                            break
                    if channel_id:
                        break
            # Last-resort fallbacks - engineering / billing / general won't
            # match the agent query but at least we post something.
            if not channel_id:
                for name in ["engineering", "billing", "general"]:
                    for ch in channels:
                        if ch.get("name") == name:
                            channel_id = ch.get("id")
                            break
                    if channel_id:
                        break
            if not channel_id and channels:
                channel_id = channels[0].get("id")
    except Exception as e:
        log(f"  [warn]  conversations.list failed: {e}")
        return None
    if not channel_id:
        log("  [skip]  no slack channel found")
        return None

    message_text = (
        "[sre · ops · incident]\n"
        ":warning: Custom Reports svc was degraded for the last "
        "2 days (2026-04-13 → 2026-04-15). Fixed at 14:30 UTC "
        "today by deploy of custom-reports-svc v3.4.2 (KMS query "
        "path repaired). RCA in INC-2026-04-13-customreports. "
        "Customer impact confined to Premium tier - "
        f"{APERTURE_DOMAIN} (Aperture Analytics) was the heaviest "
        "impacted account (48h of intermittent timeouts on the "
        "custom_reports_open endpoint). Support has been looped "
        "in to handle the customer's partial-credit request.\n"
        "_workflow=W7R-aperture-prorata · seeded_by=manthan_seed_slack_"
    )
    try:
        with httpx.Client(timeout=15.0) as client:
            # Best-effort join - required for chat.postMessage if the bot
            # isn't already a member of the channel.
            try:
                client.post(
                    "https://slack.com/api/conversations.join",
                    data={"channel": channel_id},
                    headers=headers,
                )
            except Exception:
                pass
            res = client.post(
                "https://slack.com/api/chat.postMessage",
                json={"channel": channel_id, "text": message_text},
                headers={**headers, "Content-Type": "application/json"},
            )
            payload = res.json()
            if not payload.get("ok"):
                log(f"  [warn]  chat.postMessage failed: {payload}")
                return None
            ts = payload.get("ts")
            log(f"  [new]   slack ts={ts} (channel={channel_id})")
            state["slack_message_ts"] = ts
            state["slack_channel_id"] = channel_id
            return ts
    except Exception as e:
        log(f"  [error] slack post failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────
# 6. Notion - pro-rata credit policy page
# ──────────────────────────────────────────────────────────────────────


def notion_seed_prorata_policy(client: httpx.Client) -> list[tuple[str, str]]:
    log("\n[NOTION] ensuring pro-rata credit policy page…")
    pages: list[tuple[str, str]] = []
    parent = notion_find_parent(client)
    # find_parent_page returns (page_id, title). Older patches expected
    # just a string - handle both shapes.
    if isinstance(parent, tuple):
        parent_id = parent[0]
    else:
        parent_id = parent
    if not parent_id:
        log("  [skip]  no Notion parent page configured")
        return pages
    existing = notion_list_children(client, parent_id)
    # list_existing_children returns {title: page_id}. Match on either
    # the current title OR the legacy "Documented Incident Pro-Rata
    # Credit" title from earlier seed runs (both encode the same policy).
    legacy_titles = [
        "Documented Incident Pro-Rata Credit",
        "Documented Incident Pro-Rata Refund Credit Policy",
    ]
    if isinstance(existing, dict):
        for title, pid in existing.items():
            if (
                PRORATA_POLICY_TITLE in title
                or any(legacy in title for legacy in legacy_titles)
            ):
                # Title rewrite - older seeds named this page
                # "Documented Incident Pro-Rata Credit" which only
                # carries the `pro-rata` token in queryable
                # properties. The agent ORs in `propertiestext ILIKE
                # '%refund%'`, so the new title contains "Refund" as
                # well.
                if title != PRORATA_POLICY_TITLE:
                    log(
                        f"  [fix]   renaming page {pid} from "
                        f"{title!r} → {PRORATA_POLICY_TITLE!r}"
                    )
                    try:
                        patch_payload = {
                            "properties": {
                                "title": {
                                    "title": [{
                                        "type": "text",
                                        "text": {
                                            "content": (
                                                PRORATA_POLICY_TITLE
                                            ),
                                        },
                                    }],
                                },
                            },
                        }
                        _nt(
                            client, "PATCH", f"/pages/{pid}",
                            json=patch_payload,
                        )
                        log(
                            f"  [done]  page {pid} renamed; new title "
                            "carries both 'pro-rata' and 'refund'"
                        )
                        title = PRORATA_POLICY_TITLE
                    except Exception as e:
                        log(f"  [warn]  rename failed: {e}")
                else:
                    log(f"  [reuse] policy page id={pid} (title={title!r})")
                pages.append((pid, title))
                return pages

    page = NotionPage(
        title=PRORATA_POLICY_TITLE,
        category="billing-ops / policy",
        signal_id=PRORATA_POLICY_ID,
        headings=[
            (2, "When this fires"),
            (2, "Decision"),
            (2, "Formula"),
            (2, "Required corroboration before this policy fires"),
            (2, "Do NOT use this policy if"),
            (2, "Auto-execute mode"),
        ],
        paragraphs=[
            (
                "A customer disputes a charge for a billing cycle in which "
                "an internally-documented operational incident degraded a "
                "feature on the tier they paid for. We credit pro-rata for "
                "the SPECIFIC degraded days against the disputed charge - "
                "not the full cycle, and not zero. The customer pays for "
                "the days they received the feature in working order; we "
                "pay for the days we didn't deliver."
            ),
            "",
            "refund · partial credit",
            "",
            (
                "credit_amount = (degraded_days / cycle_days) × "
                "tier_amount_for_cycle"
            ),
            (
                "Worked example: $8,400 monthly Premium tier with 2 "
                "documented degraded days in a 30-day cycle → (2 / 30) × "
                "$8,400 = $560."
            ),
            "",
            (
                "1. A Datadog monitor OR PagerDuty incident OR Sentry "
                "issue identifying the affected service and the "
                "degradation window in UTC."
            ),
            (
                "2. PostHog (or equivalent product analytics) confirming "
                "the customer actually used the affected feature during "
                "the disputed cycle."
            ),
            (
                "3. The customer's own contemporaneous complaint "
                "(Intercom or Zendesk) referencing the same feature / "
                "window."
            ),
            (
                "4. If support promised the credit verbally in a Zendesk "
                "ticket, honor that promise - even if no credit was ever "
                "issued."
            ),
            "",
            (
                "The incident did not affect the tier they paid for "
                "(e.g. it was a Standard-tier-only issue)."
            ),
            (
                "The customer downgraded BEFORE the incident (they were "
                "not entitled to the affected feature)."
            ),
            (
                "The customer's reported impact window is longer than "
                "the documented incident window - only credit the "
                "documented days, not the customer's claim."
            ),
            "",
            (
                "AUTO-EXECUTE when ALL of: (a) credit amount ≤ $1,500, "
                "(b) all four corroboration sources present, (c) customer "
                "is in good standing (no prior fraud flags). Otherwise "
                "→ recommend-then-human-approve."
            ),
        ],
    )
    payload = _page_payload(parent_id, page)
    res = _nt(client, "POST", "/pages", json=payload)
    if not res:
        return pages
    page_id = res.get("id")
    log(f"  [new]   policy page id={page_id}")
    pages.append((page_id, page.title))
    time.sleep(NOTION_REQ_SLEEP)
    return pages


# ──────────────────────────────────────────────────────────────────────
# 7. PostHog - custom_reports_open events × 47 across 4 days
# ──────────────────────────────────────────────────────────────────────


PERSONAS = [
    {
        "distinct_id": "aperture-analytics-finance-1",
        "email": f"analyst@{APERTURE_DOMAIN}",
        "name": "Priya Analyst",
    },
    {
        "distinct_id": "aperture-analytics-finance-2",
        "email": f"reports-lead@{APERTURE_DOMAIN}",
        "name": "Tomas Reports Lead",
    },
]


def build_posthog_events() -> list[dict]:
    events: list[dict] = []
    # 47 custom_reports_open events scattered across 2026-04-12 through
    # 2026-04-15 - the 4 days the customer used Premium before
    # downgrading. The agent queries
    #   posthog.events WHERE timestamp BETWEEN '2026-04-13' AND '2026-04-15'
    # AND properties::text ILIKE '%aperture%'.
    #
    # SQL BETWEEN with date-only bounds is inclusive of '2026-04-13
    # 00:00:00' and '2026-04-15 00:00:00' - meaning events on 04-15
    # *after midnight* are EXCLUDED. We bias hours per-day so the
    # 04-15 events land in the 00:00-07:59 morning window (still
    # inside the incident window 04-13 08:00 → 04-15 08:00 UTC) and
    # therefore inside the agent's BETWEEN bounds.
    days = [
        datetime(2026, 4, 12, tzinfo=timezone.utc),
        datetime(2026, 4, 13, tzinfo=timezone.utc),
        datetime(2026, 4, 14, tzinfo=timezone.utc),
        datetime(2026, 4, 15, tzinfo=timezone.utc),
    ]
    per_day = [12, 13, 11, 11]  # sums to 47
    # Hour ranges per day. Day 4 (04-15) is bounded to 00:00-07:30 so
    # events fall inside both `BETWEEN '2026-04-13' AND '2026-04-15'`
    # AND the documented incident window which ends at 04-15 08:00 UTC.
    hours_per_day = [
        (8, 17),   # 04-12 - daytime
        (8, 17),   # 04-13 - daytime, during incident
        (8, 17),   # 04-14 - daytime, during incident
        (0, 7),    # 04-15 - early morning, inside incident + BETWEEN
    ]
    rng = random.Random(20260412)
    for day_idx, (day, count) in enumerate(zip(days, per_day)):
        h_lo, h_hi = hours_per_day[day_idx]
        for i in range(count):
            persona = PERSONAS[i % len(PERSONAS)]
            ts = day + timedelta(
                hours=h_lo + rng.randint(0, max(0, h_hi - h_lo)),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59),
            )
            events.append({
                "event": "custom_reports_open",
                "distinct_id": persona["distinct_id"],
                "timestamp": ts.isoformat(),
                "properties": {
                    "$current_url": f"https://{APERTURE_APP_HOST}/reports/custom",
                    "$host": APERTURE_APP_HOST,
                    "$lib": "web",
                    "report_id": f"r_{rng.randint(1000, 9999)}",
                    "report_name": rng.choice([
                        "Weekly Revenue Roll-up",
                        "Cohort Retention Q2",
                        "Custom AR Aging",
                        "Daily Active Users (Custom)",
                    ]),
                    "tier_required": "premium",
                    "company_slug": APERTURE_SLUG,
                    # Explicit `aperture` token - the agent's
                    # `properties::text ILIKE '%aperture%'` predicate
                    # needs at least one substring match per row.
                    "company_name": APERTURE_NAME,
                    "company_domain": APERTURE_DOMAIN,
                    "account": f"aperture-analytics-{persona['distinct_id'].split('-')[-1]}",
                    "email": persona["email"],
                    "workflow": "W7R",
                },
            })
    # Standard-tier events after the downgrade (just enough to show
    # they're still using the product post-downgrade).
    for d in range(5, 16):
        ts = datetime(2026, 4, 12 + d, tzinfo=timezone.utc) + timedelta(
            hours=9, minutes=rng.randint(0, 50),
        )
        events.append({
            "event": "$pageview",
            "distinct_id": PERSONAS[d % 2]["distinct_id"],
            "timestamp": ts.isoformat(),
            "properties": {
                "$current_url": f"https://{APERTURE_APP_HOST}/dashboard",
                "$host": APERTURE_APP_HOST,
                "$lib": "web",
                "tier_required": "standard",
                "company_slug": APERTURE_SLUG,
                "email": PERSONAS[d % 2]["email"],
                "workflow": "W7R",
            },
        })
    return events


def posthog_seed() -> dict[str, Any]:
    log("\n[POSTHOG] seeding custom_reports events…")
    with httpx.Client(
        headers=POSTHOG_HEADERS, timeout=POSTHOG_TIMEOUT,
    ) as pc:
        project_api_key = fetch_project_api_key(pc)
        if not project_api_key:
            log("  [skip]  could not fetch PostHog project api key")
            return {"count": 0}
        events = build_posthog_events()
        log(f"  ingesting {len(events)} events for "
            f"{len(set(e['distinct_id'] for e in events))} distinct ids")
        result = posthog_ingest_events(pc, events, project_api_key)
        # ingest_events returns (sent, failed) tuple.
        if isinstance(result, tuple):
            sent, failed = result
        else:
            sent, failed = (result, 0)
        log(f"  [done]  ingested sent={sent} failed={failed}")
        return {"count": sent, "failed": failed}


# ──────────────────────────────────────────────────────────────────────
# 8. Datadog - custom-reports-svc degradation monitor + event
# ──────────────────────────────────────────────────────────────────────


def datadog_seed(stripe_customer_id: str, state: dict[str, Any]) -> dict[str, Any]:
    log("\n[DATADOG] ensuring custom-reports-svc degradation monitor + event…")
    dd_client = httpx.Client(
        headers=DD_HEADERS, timeout=DD_TIMEOUT,
        base_url="https://api.datadoghq.com",
    )
    try:
        return _datadog_seed_inner(dd_client, stripe_customer_id, state)
    finally:
        dd_client.close()


def _datadog_seed_inner(
    client: httpx.Client, stripe_customer_id: str, state: dict[str, Any]
) -> dict[str, Any]:
    # Monitor - name keyed for idempotency.
    incident_start_iso = INCIDENT_START.isoformat()
    incident_end_iso = INCIDENT_END.isoformat()
    fix_iso = INCIDENT_FIX_TIME.isoformat()
    monitor_msg = (
        "custom-reports-svc error_rate elevated. SLA breach window "
        f"{incident_start_iso} → {incident_end_iso} (48h). Root cause: "
        "the rendering worker held the prior session's KMS handle "
        "across the rotation window and returned 5xx on every report "
        "render attempt for Premium-tier tenants until the worker "
        "was restarted.\n\n"
        f"Primary impact: customer {stripe_customer_id} "
        f"({APERTURE_DOMAIN}, Aperture Analytics, Premium Monthly). "
        "Every custom_reports_open call returned 504 with ~22s p95 "
        "latency until the deploy at "
        f"{fix_iso}.\n\n"
        f"Resolved at {fix_iso} by deploy of custom-reports-svc "
        "v3.4.2 (worker now refreshes the KMS handle on rotate). "
        "Linked Slack #engineering thread and Zendesk ticket carry "
        "the same workflow tags.\n\n"
        "Page @custom-reports-oncall on re-trigger."
    )
    monitor = DDMonitorSpec(
        name="custom-reports-svc error_rate elevated",
        type="query alert",
        query=(
            "sum(last_15m):sum:custom_reports.render.errors"
            "{service:custom-reports-svc,tier:premium}.as_count() > 50"
        ),
        message=monitor_msg,
        tags=[
            "service:custom-reports-svc",
            "tier:premium",
            "workflow:W7R-aperture-prorata",
            "incident:INC-2026-04-13-customreports",
            f"customer_id:{stripe_customer_id}",
        ],
        options=dd_common_options(
            thresholds={"critical": 50, "warning": 25},
        ),
        note_state="Alert",
    )
    try:
        mid, mact = dd_upsert_monitor(client, monitor)
        log(f"  [done]  monitor {mid} ({mact})")
    except Exception as e:
        log(f"  [warn]  monitor upsert failed: {e}")

    # Event - Datadog rejects date_happened > ~18h ago. The narrative
    # window is baked into the title + text; date_happened is recent.
    # NOTE: even when the event already exists, we still drop through
    # to attempt the incident create - the two are independent and the
    # incident is the table the agent actually queries.
    if state.get("datadog_event_id"):
        log(f"  [reuse] datadog event id={state['datadog_event_id']}")
        event_id = state["datadog_event_id"]
        incident_id = _datadog_create_incident(
            client, stripe_customer_id, state,
        )
        return {
            "monitor_name": monitor.name,
            "event_id": event_id,
            "incident_id": incident_id,
        }
    event_title = (
        "[POSTMORTEM] custom-reports-svc degradation "
        f"{INCIDENT_START.date().isoformat()} → "
        f"{INCIDENT_END.date().isoformat()} (48h, premium tier only)"
    )
    event_text = (
        f"Service: custom-reports-svc\n"
        f"Incident window: {incident_start_iso} → {incident_end_iso}\n"
        f"Duration: 48h\n"
        f"Tier impacted: Premium only\n"
        f"Fix deploy: custom-reports-svc v3.4.2 at {fix_iso}\n"
        f"Primary impact: customer {stripe_customer_id} ({APERTURE_DOMAIN})\n"
        f"Workflow: W7R-aperture-prorata\n"
        f"Incident id: INC-2026-04-13-customreports\n\n"
        "RCA: rendering worker held prior session's KMS handle across the "
        "rotation window; every custom_reports_open returned 504 for "
        "Premium tenants until worker restart. See linked Slack thread + "
        "Zendesk ticket. Customer is filing a Stripe dispute on the "
        "April Premium charge - owner: ops-billing."
    )
    event_spec = DDEventSpec(
        title=event_title,
        text=event_text,
        date_happened=dd_epoch(dd_hours_ago(2)),
        tags=[
            "service:custom-reports-svc",
            "tier:premium",
            "workflow:W7R-aperture-prorata",
            "incident:INC-2026-04-13-customreports",
            f"customer_id:{stripe_customer_id}",
        ],
        alert_type="info",
    )
    event_id = None
    try:
        event_id, ev_act = dd_post_event(client, event_spec)
        log(f"  [done]  datadog event id={event_id} ({ev_act})")
        state["datadog_event_id"] = event_id
    except Exception as e:
        log(f"  [warn]  event post failed: {e}")

    # Create a Datadog v2 incident so the agent's query against
    # `datadog.incidents` (which hits /api/v2/incidents) actually returns
    # something. The monitor + event alone don't populate that table.
    incident_id = _datadog_create_incident(
        client, stripe_customer_id, state,
    )
    return {
        "monitor_name": monitor.name,
        "event_id": event_id,
        "incident_id": incident_id,
    }


def _datadog_create_incident(
    client: httpx.Client,
    stripe_customer_id: str,
    state: dict[str, Any],
) -> str | None:
    """Create a Datadog v2 incident for the Custom Reports degradation.

    Datadog's incidents API is opt-in (Incident Management product). If
    the account doesn't have it enabled, the POST returns 403/404 - we
    log and continue (the monitor + event still carry the narrative).
    """
    if state.get("datadog_incident_id"):
        log(f"  [reuse] datadog incident id={state['datadog_incident_id']}")
        return state["datadog_incident_id"]

    # First - check the v2 incidents API is reachable. If GET returns
    # 404/403 we can skip the POST and surface a clearer warning.
    incident_title = (
        f"Custom Reports degradation INC-2026-04-13-customreports "
        f"({INCIDENT_START.date().isoformat()} → "
        f"{INCIDENT_END.date().isoformat()})"
    )
    list_res = client.get(
        "/api/v2/incidents",
        params={"page[size]": 50},
    )
    if list_res.status_code in (403, 404):
        log(
            f"  [skip]  datadog incidents API unavailable "
            f"({list_res.status_code}); skipping incident create. "
            "Enable Datadog Incident Management for this account to "
            "populate datadog.incidents."
        )
        return None

    # Idempotency - look for an existing incident with the same title.
    if list_res.status_code == 200:
        existing = (list_res.json().get("data") or [])
        for inc in existing:
            attrs = (inc.get("attributes") or {})
            if attrs.get("title") == incident_title:
                inc_id = inc.get("id")
                log(f"  [reuse] datadog incident id={inc_id} (by title)")
                state["datadog_incident_id"] = inc_id
                return inc_id

    incident_payload = {
        "data": {
            "type": "incidents",
            "attributes": {
                "title": incident_title,
                "customer_impact_scope": (
                    "Premium tier Custom Reports users - primary impact "
                    f"{APERTURE_DOMAIN} (Aperture Analytics). 48h of "
                    "intermittent timeouts on custom_reports_open."
                ),
                "customer_impacted": True,
                "customer_impact_start": INCIDENT_START.isoformat(),
                "customer_impact_end": INCIDENT_END.isoformat(),
                "detected": INCIDENT_START.isoformat(),
                "fields": {
                    "summary": {
                        "type": "textbox",
                        "value": (
                            "custom-reports-svc returned 5xx for Premium-tier "
                            "tenants from 2026-04-13 08:00 UTC through "
                            "2026-04-15 08:00 UTC (48h). Root cause: "
                            "rendering worker held the prior session's KMS "
                            "handle across the rotation window. Fixed at "
                            "2026-04-15 14:30 UTC by deploy of "
                            "custom-reports-svc v3.4.2. Primary customer "
                            f"impact: {stripe_customer_id} "
                            f"({APERTURE_DOMAIN})."
                        ),
                    },
                    "severity": {
                        "type": "dropdown",
                        "value": "SEV-2",
                    },
                    "state": {
                        "type": "dropdown",
                        "value": "resolved",
                    },
                    "services": {
                        "type": "autocomplete",
                        "value": ["custom-reports-svc"],
                    },
                    "teams": {
                        "type": "autocomplete",
                        "value": ["custom-reports"],
                    },
                },
                "notification_handles": [],
            },
        },
    }
    try:
        r = client.post(
            "/api/v2/incidents",
            json=incident_payload,
            headers={"Content-Type": "application/json"},
        )
        if r.status_code not in (200, 201, 202):
            log(
                f"  [warn]  incident create returned {r.status_code}: "
                f"{r.text[:200]}"
            )
            return None
        body = r.json()
        inc_id = (body.get("data") or {}).get("id")
        log(f"  [new]   datadog incident id={inc_id}")
        state["datadog_incident_id"] = inc_id

        # Mark resolved so the title + state line up with the narrative.
        # Datadog v2 incidents accept PATCH on resolved field separately.
        try:
            resolve_payload = {
                "data": {
                    "id": inc_id,
                    "type": "incidents",
                    "attributes": {
                        "resolved": INCIDENT_FIX_TIME.isoformat(),
                        "fields": {
                            "state": {
                                "type": "dropdown",
                                "value": "resolved",
                            },
                        },
                    },
                }
            }
            client.patch(
                f"/api/v2/incidents/{inc_id}",
                json=resolve_payload,
                headers={"Content-Type": "application/json"},
            )
        except Exception:
            pass
        return inc_id
    except Exception as e:
        log(f"  [warn]  incident create failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────
# Main orchestration
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    state = _load_state()
    c = aperture_company()
    log(f"\nW7R Aperture Analytics seed - workflow target: "
        f"{APERTURE_NAME} ({APERTURE_EMAIL})")
    log(f"Cycle: {CYCLE_START.date()} → {CYCLE_END.date()} · "
        f"April charge ${APRIL_CHARGE_USD} · "
        f"expected refund ${EXPECTED_REFUND_MINOR/100:.0f}")

    # 1. Stripe
    cust = stripe_ensure_customer(c)
    charge, dispute = stripe_ensure_april_charge_and_dispute(cust)
    c.stripe_customer_id = cust.id
    state["stripe_customer_id"] = cust.id
    state["stripe_charge_id"] = charge.id
    state["stripe_dispute_id"] = dispute.id if dispute else None

    # 2. HubSpot
    with httpx.Client(
        headers=HUBSPOT_HEADERS, timeout=HUBSPOT_TIMEOUT,
        base_url="https://api.hubapi.com",
    ) as hs:
        hs_company_id = hubspot_upsert_company(hs, c)
        hs_contact_id = hubspot_upsert_contact(hs, hs_company_id)
        hubspot_attach_downgrade_note(hs, hs_company_id)
        c.hubspot_company_id = hs_company_id
        state["hubspot_company_id"] = hs_company_id
        state["hubspot_contact_id"] = hs_contact_id

    # 3. Intercom
    with httpx.Client(
        headers=INTERCOM_HEADERS, timeout=INTERCOM_TIMEOUT,
        base_url="https://api.intercom.io",
    ) as ic:
        intercom_contact_id = intercom_ensure_contact(ic)
        if intercom_contact_id:
            intercom_create_conversation(ic, intercom_contact_id, state)
            c.intercom_contact_id = intercom_contact_id
            state["intercom_contact_id"] = intercom_contact_id

    # 4. Zendesk
    zd_subdomain = os.getenv("ZENDESK_SUBDOMAIN", "")
    zd_base = f"https://{zd_subdomain}.zendesk.com" if zd_subdomain else ""
    with httpx.Client(
        auth=ZENDESK_AUTH, timeout=ZENDESK_TIMEOUT, base_url=zd_base,
    ) as zc:
        zd = zendesk_seed(zc, c, state)
        if zd.get("user_id"):
            c.zendesk_user_id = zd["user_id"]
            state["zendesk_user_id"] = zd["user_id"]
            state["zendesk_org_id"] = zd["org_id"]

    # 5. Slack
    slack_post_engineering_ack(state)

    # 6. Notion
    with httpx.Client(
        headers=NOTION_HEADERS, timeout=NOTION_TIMEOUT,
        base_url="https://api.notion.com/v1",
    ) as nc:
        notion_pages = notion_seed_prorata_policy(nc)
        state["notion_pages"] = [pid for pid, _ in notion_pages]

    # 7. PostHog
    ph = posthog_seed()
    state["posthog_event_count"] = ph.get("count", 0)

    # 8. Datadog
    dd = datadog_seed(cust.id, state)
    state["datadog_event_id"] = dd.get("event_id")
    if dd.get("incident_id"):
        state["datadog_incident_id"] = dd.get("incident_id")

    _save_state(state)

    log("\n──────────────────────────────────────────────────────────────")
    log("W7R seed complete.")
    log(f"  Stripe customer: {state.get('stripe_customer_id')}")
    log(f"  Stripe charge:   {state.get('stripe_charge_id')}")
    log(f"  HubSpot company: {state.get('hubspot_company_id')}")
    log(f"  Intercom convo:  {state.get('intercom_conversation_id')}")
    log(f"  Zendesk ticket:  {state.get('zendesk_ticket_id')}")
    log(f"  Slack ts:        {state.get('slack_message_ts')}")
    log(f"  Notion pages:    {state.get('notion_pages')}")
    log(f"  PostHog events:  {state.get('posthog_event_count')}")
    log(f"  Datadog event:   {state.get('datadog_event_id')}")
    log(f"  Datadog incident:{state.get('datadog_incident_id')}")
    log("\nTrigger the case with:")
    log("  cd manthan-api && uv run python -m manthan_api.scripts."
        "trigger_demo_cases --only W7R")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
