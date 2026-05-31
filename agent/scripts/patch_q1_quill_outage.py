"""Patch Q1R - Quill Logistics alleged-Q1-outage chargeback.

Seeds evidence across all 11 connected sources so the Manthan agent
investigating the $9k chargeback can recommend FIGHT with overwhelming
corroboration:

  Stripe       - $9k test-mode dispute on a Pro Annual charge with
                 metadata semantic_reason=service_outage_claim and the
                 disputed-window dates.
  Salesforce   - "Quill Logistics" account, Pro Annual, $40k ARR,
                 CSM=Amelia, renewal Mar 2027, healthy account notes.
  HubSpot      - Company record, last-contact note about VP Eng asking
                 about Standard tier ("evaluating, not cancelling").
  Intercom     - 4 Q1 conversations, none about outage or cancellation.
                 Latest about onboarding new team members.
  Zendesk      - Zero tickets in the alleged-outage Q1 window; 2 older
                 feature-request tickets from 2025, both solved.
  Slack        - One post in #cs-escalations from Amelia (CSM) about
                 the April downgrade conversation - NOT about outage.
  Notion       - "Chargeback Response Playbook v3" codifying the FIGHT
                 path when ops data is clean AND PostHog shows usage,
                 plus a "Pro Annual Refund Policy 2026" page.
  PostHog      - Q1 activity: 22 logins, 8 distinct users, 47 critical-
                 path actions (create_shipment, generate_invoice).
  Sentry       - Q1 baseline ~0.4% error rate tagged to Quill's tenant,
                 no spikes.
  Datadog      - Synthetic monitor "us-east-1 Quill region uptime" with
                 a Q1 narrative of 99.97% uptime, p95 within SLA.
  PagerDuty    - Zero P1/P2 incidents in Q1 touching Quill's region.

Idempotent: every resource is looked up by name/idem-key before creation.

Run:
    cd agent && uv run python scripts/patch_q1_quill_outage.py
"""

from __future__ import annotations

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
import sentry_sdk  # noqa: E402

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
    find_contact_by_external_id as intercom_find_contact_by_external_id,
    get_admin_id as intercom_get_admin_id,
)
from seed_zendesk import (  # noqa: E402
    AUTH as ZENDESK_AUTH,
    TIMEOUT as ZENDESK_TIMEOUT,
    TrialCapHit,
    _isoformat as zd_isoformat,
    _request as zendesk_request,
    import_ticket as zendesk_import_ticket,
    load_state as zendesk_load_state,
    save_state as zendesk_save_state,
    upsert_organization as zendesk_upsert_organization,
    upsert_user as zendesk_upsert_user,
)
from seed_slack import (  # noqa: E402
    HEADERS as SLACK_HEADERS,
    TIMEOUT as SLACK_TIMEOUT,
    slack_call,
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
    PROJECT_ID as POSTHOG_PROJECT_ID,
    TIMEOUT as POSTHOG_TIMEOUT,
    fetch_project_api_key,
    ingest_events as posthog_ingest_events,
)
from seed_sentry import (  # noqa: E402
    HEADERS as SENTRY_HEADERS,
    INGEST_SLEEP,
    ORG as SENTRY_ORG,
    TIMEOUT as SENTRY_TIMEOUT,
    _init_for_project as sentry_init_for_project,
    _request as sentry_request,
    ensure_project as sentry_ensure_project,
    ensure_team as sentry_ensure_team,
    get_project_dsn as sentry_get_project_dsn,
    list_projects as sentry_list_projects,
    list_teams as sentry_list_teams,
    ping_org as sentry_ping_org,
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
from seed_pagerduty import (  # noqa: E402
    HEADERS as PD_HEADERS,
    REQ_SLEEP as PD_REQ_SLEEP,
    TIMEOUT as PD_TIMEOUT,
    _incident_key as pd_incident_key,
    _request as pagerduty_request,
    create_incident as pd_create_incident,
    fetch_all_incident_keys as pd_fetch_all_incident_keys,
    find_service_id_by_name as pd_find_service_by_name,
    first_escalation_policy_id as pd_first_escalation_policy_id,
    update_incident_status as pd_update_incident_status,
    upsert_service as pd_upsert_service,
)
from seed_world import (  # noqa: E402
    Company,
    find_company as world_find_company,
    intercom_external_id,
)


# Salesforce is optional - only seed it if the access token is valid.
SALESFORCE_AVAILABLE = bool(
    os.getenv("SALESFORCE_API_URL") and os.getenv("SALESFORCE_ACCESS_TOKEN")
)
if SALESFORCE_AVAILABLE:
    try:
        from seed_salesforce import (  # noqa: E402
            HEADERS as SF_HEADERS,
            TIMEOUT as SF_TIMEOUT,
            upsert_account as sf_upsert_account,
        )
    except Exception:
        SALESFORCE_AVAILABLE = False


# Stripe is required - bail loudly if not configured.
stripe.api_key = os.getenv("STRIPE_API_KEY")
if not stripe.api_key or not stripe.api_key.startswith("sk_test_"):
    raise SystemExit("STRIPE_API_KEY must be a sk_test_... key in agent/.env")


# ──────────────────────────────────────────────────────────────────────
# Q1R constants
# ──────────────────────────────────────────────────────────────────────

QUILL_SLUG = "quill-logi"
QUILL_NAME = "Quill Logistics"
QUILL_EMAIL = "ar@quill-logistics.test"
QUILL_DOMAIN = "quill-logistics.test"
QUILL_HS_DOMAIN = "quill-logi.test"  # mirrors seed_hubspot._domain() shape
QUILL_INDUSTRY = "logistics"
QUILL_COUNTRY = "USA"
QUILL_REGION = "us-east-1"
QUILL_ARR_USD = 40000
QUILL_PLAN = "Pro Annual"
QUILL_DISPUTED_AMOUNT_MINOR = 9_000_00  # $9,000

# Q1 2026 disputed window
DISPUTED_WINDOW_START = "2026-01-01"
DISPUTED_WINDOW_END = "2026-03-31"
CHARGE_DATE = "2026-03-15"
RENEWAL_DATE = "2027-03-15"

# Deterministic randomness so re-runs are reproducible.
RNG = random.Random(20260315)


# ──────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────


def log(msg: str = "") -> None:
    print(msg, flush=True)


# ──────────────────────────────────────────────────────────────────────
# 1. Stripe - customer, subscription, charge, dispute
# ──────────────────────────────────────────────────────────────────────


def quill_company() -> Company:
    return world_find_company(QUILL_SLUG)


def stripe_ensure_customer(c: Company) -> stripe.Customer:
    log("\n[STRIPE]  ensuring Quill customer…")
    cust = safe_create(
        stripe.Customer.create,
        idem_key=idem("cust", c.slug),
        label=f"Customer[{c.slug}]",
        email=c.email, name=c.name,
        description=c.notes or f"{c.industry} / {c.country}",
        metadata={
            "slug": c.slug, "industry": c.industry, "country": c.country,
            "arr_usd": str(c.arr_usd), "signup_year": str(c.signup_year),
            "plan": c.plan, "health": c.health,
            "region": QUILL_REGION,
            "seeded_by": "manthan_seed_stripe",
            "workflow": "Q1R",
        },
    )
    cust = stripe.Customer.retrieve(cust.id)
    log(f"  customer id: {cust.id}")
    # Attach a default payment method if missing.
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


def stripe_find_pro_annual_price() -> stripe.Price:
    """Reuse the existing pro_annual current price seeded by seed_stripe."""
    for pr in stripe.Price.list(limit=100, active=None).auto_paging_iter():
        md = md_dict(pr)
        if (md.get("seeded_by") == "manthan_seed_stripe"
                and md.get("price_key") == "pro_annual_current"):
            return pr
    raise SystemExit(
        "ERROR: no Pro Annual current price found in Stripe - "
        "run seed_stripe.py first."
    )


def stripe_ensure_subscription(
    cust: stripe.Customer, price_id: str
) -> stripe.Subscription:
    log("\n[STRIPE]  ensuring Pro Annual subscription…")
    # Idempotency: look for an existing primary sub on this customer.
    for s in stripe.Subscription.list(
        customer=cust.id, limit=10, status="all"
    ).auto_paging_iter():
        md = md_dict(s)
        if md.get("slug") == QUILL_SLUG and md.get("sub_role") == "primary":
            log(f"  [reuse] subscription {s.id} (status={s.status})")
            return s
    sub = safe_create(
        stripe.Subscription.create,
        idem_key=idem("sub", QUILL_SLUG, "primary-v2"),
        label=f"Subscription[{QUILL_SLUG}/primary]",
        customer=cust.id,
        items=[{"price": price_id}],
        default_payment_method=cust.invoice_settings.default_payment_method,
        metadata={
            "slug": QUILL_SLUG, "plan": QUILL_PLAN, "plan_key": "pro_annual",
            "seeded_by": "manthan_seed_stripe",
            "billing_source": "stripe_primary",
            "sub_role": "primary",
            "signup_year": "2024",
            "workflow": "Q1R",
        },
    )
    log(f"  [new]   subscription {sub.id} (status={sub.status})")
    return sub


def stripe_find_q1r_dispute() -> stripe.Dispute | None:
    """Look for an existing Q1R dispute (idempotency)."""
    for d in stripe.Dispute.list(limit=100).auto_paging_iter():
        md = md_dict(d)
        if md.get("workflow") == "Q1R" and md.get("slug") == QUILL_SLUG:
            return d
    return None


def stripe_create_disputed_charge_and_dispute(
    cust: stripe.Customer,
) -> tuple[stripe.Charge, stripe.Dispute]:
    """Create the $9k disputed Pro Annual renewal charge and capture the
    resulting dispute object.

    Stripe test mode only emits disputes from specific test cards.
    `pm_card_createDisputeProductNotReceived` is the closest test reason
    to a "service outage / didn't receive product" claim.
    """
    existing = stripe_find_q1r_dispute()
    if existing:
        ch = stripe.Charge.retrieve(existing.charge) if existing.charge else None
        if ch:
            log(f"  [reuse] Q1R dispute {existing.id} on charge {ch.id} "
                f"(status={existing.status})")
            return ch, existing

    log("\n[STRIPE]  creating $9,000 disputed Pro Annual charge…")
    unique_suffix = f"q1r-disp-{int(time.time())}"
    pi = safe_create(
        stripe.PaymentIntent.create,
        idem_key=idem("pi", QUILL_SLUG, unique_suffix),
        label=f"PI[{QUILL_SLUG}/{unique_suffix}]",
        amount=QUILL_DISPUTED_AMOUNT_MINOR,
        currency="usd",
        payment_method="pm_card_createDisputeProductNotReceived",
        confirm=True,
        customer=cust.id,
        off_session=True,
        description=(
            f"{QUILL_NAME} - Pro Annual renewal ({CHARGE_DATE}). "
            "Customer claim: 'service outage during Q1 2026, couldn't "
            "access the product.' Operational data shows no such outage "
            "and PostHog confirms active usage during the disputed window."
        ),
        metadata={
            "slug": QUILL_SLUG,
            "simulated_created_at": CHARGE_DATE,
            "workflow": "Q1R",
            "workflow_label": "alleged_outage_fight",
            "semantic_reason": "service_outage_claim",
            "customer_claim": (
                "Service outage during Q1, we couldn't access the product."
            ),
            "disputed_window_start": DISPUTED_WINDOW_START,
            "disputed_window_end": DISPUTED_WINDOW_END,
            "charge_category": "subscription_renewal",
            "billing_period_label": "Pro Annual 2026-Q1 renewal",
            "region": QUILL_REGION,
            "prior_disputes_count": "0",
            "expected_decision": "fight",
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

    # Wait for the dispute to materialise.
    dispute_id = ch.dispute
    if not dispute_id:
        for _ in range(10):
            time.sleep(0.6)
            ch = stripe.Charge.retrieve(ch.id)
            if ch.dispute:
                dispute_id = ch.dispute
                break
    if not dispute_id:
        raise RuntimeError(
            f"No dispute materialised on charge {ch.id} "
            "(test card may have changed behavior)"
        )

    disp = stripe.Dispute.retrieve(dispute_id)
    # Tag the dispute with Q1R metadata + the disputed-window markers.
    disp = stripe.Dispute.modify(
        disp.id,
        metadata={
            "slug": QUILL_SLUG,
            "workflow": "Q1R",
            "workflow_label": "alleged_outage_fight",
            "semantic_reason": "service_outage_claim",
            "customer_claim": (
                "Service outage during Q1, we couldn't access the product."
            ),
            "disputed_window_start": DISPUTED_WINDOW_START,
            "disputed_window_end": DISPUTED_WINDOW_END,
            "simulated_created_at": "2026-03-25",
            "region": QUILL_REGION,
            "expected_decision": "fight",
            "stripe_customer_id": cust.id,
            "prior_disputes_count": "0",
            "seeded_by": "manthan_seed_stripe",
        },
    )
    # Best-effort: also stamp the charge's metadata with the customer id
    # so any downstream cross-reference is clean.
    try:
        stripe.Charge.modify(
            ch.id,
            description=(
                f"{QUILL_NAME} - Pro Annual renewal ({CHARGE_DATE}). "
                "Customer claim: 'service outage during Q1 2026, couldn't "
                "access the product.' Operational data shows no such outage."
            ),
            metadata={
                "slug": QUILL_SLUG,
                "simulated_created_at": CHARGE_DATE,
                "workflow": "Q1R",
                "semantic_reason": "service_outage_claim",
                "disputed_window_start": DISPUTED_WINDOW_START,
                "disputed_window_end": DISPUTED_WINDOW_END,
                "stripe_customer_id": cust.id,
                "region": QUILL_REGION,
                "seeded_by": "manthan_seed_stripe",
            },
        )
    except stripe.error.StripeError as e:
        log(f"  [charge-modify-skip] {ch.id}: {str(e)[:120]}")

    log(f"  charge   {ch.id}  amount=${ch.amount/100:,.2f}")
    log(f"  dispute  {disp.id}  reason={disp.reason}  status={disp.status}")
    return ch, disp


# ──────────────────────────────────────────────────────────────────────
# 2. Salesforce - Quill Logistics account (optional)
# ──────────────────────────────────────────────────────────────────────


def salesforce_seed(c: Company, stripe_customer_id: str) -> str | None:
    if not SALESFORCE_AVAILABLE:
        log("\n[SALESFORCE]  SKIP - SALESFORCE_ACCESS_TOKEN not configured.")
        return None
    log("\n[SALESFORCE]  ensuring Quill Logistics account…")
    try:
        with httpx.Client(headers=SF_HEADERS, timeout=SF_TIMEOUT) as client:
            account_id, action = sf_upsert_account(client, c)
        if account_id:
            log(f"  [{action}] account → {account_id}")
            return account_id
        log(f"  [{action}] account create failed")
        return None
    except Exception as e:
        log(f"  [skip] Salesforce error: {type(e).__name__}: {str(e)[:200]}")
        return None


# ──────────────────────────────────────────────────────────────────────
# 3. HubSpot - company + contacts + the "VP Eng pricing" note
# ──────────────────────────────────────────────────────────────────────


def hubspot_find_company_by_domain(
    client: httpx.Client, domain: str
) -> str | None:
    r = hubspot_request(
        client, "POST", "/crm/v3/objects/companies/search",
        json={
            "filterGroups": [{"filters": [{
                "propertyName": "domain", "operator": "EQ", "value": domain,
            }]}],
            "properties": ["name", "domain"],
            "limit": 1,
        },
    )
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def hubspot_upsert_company(
    client: httpx.Client, c: Company, stripe_customer_id: str
) -> str | None:
    existing = hubspot_find_company_by_domain(client, QUILL_HS_DOMAIN)
    description = (
        "Pro Annual customer. Renewed normally in March 2026. "
        "Expanded usage in Q1 2026 across the shipment + invoicing "
        "modules. Last contact 2026-04-29: VP Engineering asked about "
        "Standard tier pricing - explicitly framed as 'evaluating, not "
        "cancelling.' Filed a $9,000 chargeback on the March renewal "
        "in late March 2026 claiming a Q1 outage; operational data shows "
        "no such outage and product usage continued throughout Q1. "
        f"Stripe customer: {stripe_customer_id}. Workflow: Q1R."
    )
    props = {
        "name": c.name,
        "domain": QUILL_HS_DOMAIN,
        "country": c.country,
        "annualrevenue": str(c.arr_usd),
        "description": description,
        "lifecyclestage": "customer",
        "industry": "LOGISTICS_AND_SUPPLY_CHAIN",
    }
    if existing:
        r = hubspot_request(
            client, "PATCH",
            f"/crm/v3/objects/companies/{existing}",
            json={"properties": props},
        )
        if r.status_code in (200, 201):
            return existing
        # Retry without industry on rejection.
        if r.status_code == 400 and "industry" in props:
            props2 = {k: v for k, v in props.items() if k != "industry"}
            r = hubspot_request(
                client, "PATCH",
                f"/crm/v3/objects/companies/{existing}",
                json={"properties": props2},
            )
            if r.status_code in (200, 201):
                return existing
        log(f"  company update fail: {r.status_code} {r.text[:200]}")
        return existing
    r = hubspot_request(
        client, "POST", "/crm/v3/objects/companies",
        json={"properties": props},
    )
    if r.status_code in (200, 201):
        return r.json().get("id")
    if r.status_code == 400 and "industry" in props:
        props2 = {k: v for k, v in props.items() if k != "industry"}
        r = hubspot_request(
            client, "POST", "/crm/v3/objects/companies",
            json={"properties": props2},
        )
        if r.status_code in (200, 201):
            return r.json().get("id")
    log(f"  company create fail: {r.status_code} {r.text[:200]}")
    return None


HUBSPOT_NOTE_SIGNATURE = "[manthan_patch_q1_quill_outage]"
HUBSPOT_NOTE_BODY = (
    f"{HUBSPOT_NOTE_SIGNATURE} 2026-04-29 - VP Engineering at Quill "
    "Logistics asked our AE about Standard tier pricing for comparison. "
    "They explicitly framed it as 'evaluating, not cancelling.' "
    "Renewed normally a few weeks earlier on Pro Annual. No outage "
    "complaint at any point in Q1. Filed a $9k chargeback on the March "
    "renewal claiming Q1 outage - ops data (Sentry/Datadog/PagerDuty) "
    "shows clean operations, PostHog shows active usage. Fight per the "
    "Chargeback Response Playbook v3."
)


def hubspot_find_note(
    client: httpx.Client, company_id: str, signature: str
) -> str | None:
    r = hubspot_request(
        client, "GET",
        f"/crm/v4/objects/companies/{company_id}/associations/notes",
        params={"limit": 100},
    )
    if r.status_code != 200:
        return None
    note_ids = [
        rec.get("toObjectId") for rec in r.json().get("results", [])
        if rec.get("toObjectId")
    ]
    for nid in note_ids:
        r2 = hubspot_request(
            client, "GET", f"/crm/v3/objects/notes/{nid}",
            params={"properties": "hs_note_body"},
        )
        if r2.status_code != 200:
            continue
        body = r2.json().get("properties", {}).get("hs_note_body") or ""
        if signature in body:
            return str(nid)
    return None


def hubspot_attach_note(
    client: httpx.Client, company_id: str
) -> str | None:
    existing = hubspot_find_note(client, company_id, HUBSPOT_NOTE_SIGNATURE)
    if existing:
        return existing
    body = {
        "properties": {
            "hs_note_body": HUBSPOT_NOTE_BODY,
            "hs_timestamp": str(int(time.time() * 1000)),
        },
        "associations": [{
            "to": {"id": company_id},
            "types": [{
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 190,  # note -> company
            }],
        }],
    }
    r = hubspot_request(client, "POST", "/crm/v3/objects/notes", json=body)
    if r.status_code in (200, 201):
        return r.json().get("id")
    log(f"  note create fail: {r.status_code} {r.text[:200]}")
    return None


def hubspot_seed(c: Company, stripe_customer_id: str) -> tuple[str | None, str | None]:
    log("\n[HUBSPOT]  ensuring Quill Logistics company + VP-Eng note…")
    with httpx.Client(headers=HUBSPOT_HEADERS, timeout=HUBSPOT_TIMEOUT) as client:
        cid = hubspot_upsert_company(client, c, stripe_customer_id)
        log(f"  company id: {cid}")
        time.sleep(HUBSPOT_REQ_SLEEP)
        if not cid:
            return None, None
        nid = hubspot_attach_note(client, cid)
        log(f"  note id   : {nid}")
        time.sleep(HUBSPOT_REQ_SLEEP)
    return cid, nid


# ──────────────────────────────────────────────────────────────────────
# 4. Intercom - 4 Q1 conversations (none about outage or cancel)
# ──────────────────────────────────────────────────────────────────────


def intercom_ensure_contact(client: httpx.Client) -> str | None:
    ext_id = f"{intercom_external_id(QUILL_SLUG)}_primary"
    existing = intercom_find_contact_by_external_id(client, ext_id)
    if existing:
        log(f"  [reuse] contact {existing}")
        return existing
    by_email = intercom_find_contact_by_email(client, QUILL_EMAIL)
    if by_email:
        update = {
            "external_id": ext_id,
            "name": "Amelia Park",
            "signed_up_at": int(datetime(2024, 5, 14, 9, 0, 0,
                                         tzinfo=timezone.utc).timestamp()),
            "last_seen_at": int(time.time()) - 86400 * 2,
        }
        intercom_request(client, "PUT", f"/contacts/{by_email}", json=update)
        return by_email
    payload = {
        "role": "user",
        "email": QUILL_EMAIL,
        "name": "Amelia Park",
        "external_id": ext_id,
        "signed_up_at": int(datetime(2024, 5, 14, 9, 0, 0,
                                     tzinfo=timezone.utc).timestamp()),
        "last_seen_at": int(time.time()) - 86400 * 2,
    }
    r = intercom_request(client, "POST", "/contacts", json=payload)
    if r.status_code in (200, 201):
        return r.json().get("id")
    if r.status_code == 409:
        return intercom_find_contact_by_email(client, QUILL_EMAIL)
    log(f"  contact create fail: {r.status_code} {r.text[:200]}")
    return None


def _epoch(y: int, m: int, d: int, hh: int = 10, mm: int = 0) -> int:
    return int(datetime(y, m, d, hh, mm, 0, tzinfo=timezone.utc).timestamp())


Q1R_INTERCOM_CONVOS = [
    {
        "subject": "Onboarding new team members",
        "body": (
            "Hi - we've got 3 new analysts joining the logistics team "
            "next week and I'd like them invited to our workspace with "
            "viewer access. Do you have a self-serve flow for that or "
            "do I send the list to support?"
        ),
        "created_at": _epoch(2026, 1, 18, 14, 22),
        "final_state": "closed",
        "admin_reply": (
            "Hi Amelia - you can invite them yourself from "
            "Settings → Team. Need anything more, just shout."
        ),
        "tag": "Q1R.onboarding",
    },
    {
        "subject": "Invoice template for AP team",
        "body": (
            "Our AP team needs the PO number on each invoice line. Can "
            "I configure that in billing settings or does it need an "
            "engineering ticket?"
        ),
        "created_at": _epoch(2026, 2, 6, 10, 5),
        "final_state": "closed",
        "admin_reply": (
            "Configurable in Settings → Billing → Invoice template - "
            "just add the PO field there. Let me know if you can't see it."
        ),
        "tag": "Q1R.invoice",
    },
    {
        "subject": "Bulk shipment API question",
        "body": (
            "We're integrating the bulk_shipment_create endpoint into "
            "our WMS and getting occasional 429s when we push 5k+ rows "
            "in one batch. What's the recommended chunk size?"
        ),
        "created_at": _epoch(2026, 2, 27, 9, 41),
        "final_state": "closed",
        "admin_reply": (
            "Best results at 500-row chunks with a 200ms pause between. "
            "We've bumped your throughput on the customer object so you "
            "shouldn't hit 429 anymore."
        ),
        "tag": "Q1R.api",
    },
    {
        "subject": "Onboarding new team members (round 2)",
        "body": (
            "Following up - the second batch of analysts is starting "
            "next Monday. Can you confirm the invite flow handles 6 "
            "users at once or should I stagger?"
        ),
        "created_at": _epoch(2026, 3, 21, 13, 18),
        "final_state": "closed",
        "admin_reply": (
            "All 6 in one go is fine. Looking forward to a busy Q2 - "
            "your usage growth is great."
        ),
        "tag": "Q1R.onboarding2",
    },
]


def intercom_seed() -> tuple[str | None, list[str]]:
    log("\n[INTERCOM]  ensuring contact + 4 Q1 conversations…")
    convo_ids: list[str] = []
    with httpx.Client(headers=INTERCOM_HEADERS, timeout=INTERCOM_TIMEOUT) as client:
        admin_id = intercom_get_admin_id(client)
        contact_id = intercom_ensure_contact(client)
        if not contact_id:
            log("  ERROR: could not establish Intercom contact for Quill")
            return None, []

        # Idempotency: search ALL conversations created by this contact
        # via Intercom's POST /conversations/search endpoint, then match
        # source.body against our Q1R specs. Intercom wraps inbound bodies
        # in <p>...</p>, so we normalize by stripping the wrapper tags
        # before comparison.
        existing_bodies: list[str] = []
        try:
            search_body = {
                "query": {
                    "field": "source.author.id",
                    "operator": "=",
                    "value": contact_id,
                },
                "pagination": {"per_page": 60},
            }
            r = intercom_request(
                client, "POST", "/conversations/search", json=search_body,
            )
            if r.status_code == 200:
                for c in r.json().get("conversations", []):
                    src_body = (c.get("source") or {}).get("body") or ""
                    # Strip the leading/trailing <p>…</p> Intercom adds.
                    stripped = (
                        src_body.replace("<p>", "").replace("</p>", "").strip()
                    )
                    if stripped:
                        existing_bodies.append(stripped)
        except Exception:
            pass

        for spec in Q1R_INTERCOM_CONVOS:
            # Match on the first 60 chars of the body - distinct enough
            # across our 4 Q1R specs to avoid cross-matches.
            body_key = spec["body"][:60]
            if any(body_key in existing for existing in existing_bodies):
                log(f"  [reuse] {spec['tag']}: convo already exists")
                convo_ids.append("(existing)")
                continue
            payload = {
                "from": {"type": "user", "id": contact_id},
                "body": spec["body"],
                "created_at": spec["created_at"],
            }
            r = intercom_request(client, "POST", "/conversations", json=payload)
            if r.status_code not in (200, 201):
                log(f"  ! convo create {spec['tag']} fail: "
                    f"{r.status_code} {r.text[:200]}")
                continue
            j = r.json()
            convo_id = j.get("conversation_id")
            if not convo_id:
                log(f"  ! convo {spec['tag']}: no conversation_id returned")
                continue
            # Admin reply.
            if spec.get("admin_reply"):
                reply = {
                    "message_type": "comment",
                    "type": "admin",
                    "admin_id": admin_id,
                    "body": f"<p>{spec['admin_reply']}</p>",
                }
                intercom_request(
                    client, "POST",
                    f"/conversations/{convo_id}/reply",
                    json=reply,
                )
            # Close.
            if spec["final_state"] == "closed":
                close = {
                    "message_type": "close",
                    "type": "admin",
                    "admin_id": admin_id,
                    "body": "Resolved.",
                }
                intercom_request(
                    client, "POST",
                    f"/conversations/{convo_id}/parts",
                    json=close,
                )
            convo_ids.append(convo_id)
            log(f"  [new]   {spec['tag']} convo {convo_id}")
            time.sleep(INTERCOM_REQ_SLEEP)
    return contact_id, convo_ids


# ──────────────────────────────────────────────────────────────────────
# 5. Zendesk - org + 2 older feature-request tickets (zero in Q1)
# ──────────────────────────────────────────────────────────────────────


Q1R_ZENDESK_TICKETS = [
    {
        "subject": "Feature request: route optimization heat map",
        "body": (
            "Hi team - would love a heat-map overlay on the route "
            "optimization view. Right now we eyeball the dense corridors. "
            "Happy to be a beta tester."
        ),
        "priority": "low",
        "status": "solved",
        "days_ago_from_anchor": (datetime(2026, 5, 27, tzinfo=timezone.utc)
                                 - datetime(2025, 8, 14, tzinfo=timezone.utc)
                                 ).days,
        "type": "question",
    },
    {
        "subject": "Feature request: per-warehouse rate cards in API",
        "body": (
            "Our rate cards differ per warehouse. The current API treats "
            "them as account-level - could you add a warehouse_id "
            "qualifier so we can model differential rates per site?"
        ),
        "priority": "low",
        "status": "solved",
        "days_ago_from_anchor": (datetime(2026, 5, 27, tzinfo=timezone.utc)
                                 - datetime(2025, 11, 4, tzinfo=timezone.utc)
                                 ).days,
        "type": "question",
    },
]


def zendesk_seed(c: Company) -> dict[str, Any]:
    log("\n[ZENDESK]  ensuring organization + user + 2 older tickets…")
    state = zendesk_load_state()
    state.setdefault("organizations", {})
    state.setdefault("users", {})
    state.setdefault("q1r_quill_tickets", [])

    with httpx.Client(
        headers={"Content-Type": "application/json"},
        auth=ZENDESK_AUTH, timeout=ZENDESK_TIMEOUT,
    ) as client:
        # Org
        org_id = state["organizations"].get(QUILL_SLUG)
        if not org_id:
            org_id, action = zendesk_upsert_organization(client, c)
            if org_id:
                state["organizations"][QUILL_SLUG] = org_id
                zendesk_save_state(state)
                log(f"  org [{action}] id={org_id}")
            else:
                log(f"  ! could not upsert Zendesk org for {QUILL_SLUG}")
                return {"org_id": None, "ticket_ids": []}
        else:
            log(f"  org [reuse] id={org_id}")
        # User
        user_ext = "ext_quill-logi_0"
        user_id = state["users"].get(user_ext)
        if not user_id:
            user_id, action = zendesk_upsert_user(
                client,
                email=QUILL_EMAIL,
                name="Amelia Park",
                role="end-user",
                organization_id=org_id,
                external_id=user_ext,
            )
            if user_id:
                state["users"][user_ext] = user_id
                zendesk_save_state(state)
                log(f"  user [{action}] id={user_id}")
            else:
                log(f"  ! could not upsert Zendesk user for {QUILL_SLUG}")
                return {"org_id": org_id, "ticket_ids": []}
        else:
            log(f"  user [reuse] id={user_id}")

        # Tickets - idempotency via state['q1r_quill_tickets']
        existing_tids = state.get("q1r_quill_tickets", [])
        if existing_tids:
            # Verify each one still exists; if all good, skip create.
            still_exist = []
            for tid in existing_tids:
                r = zendesk_request(client, "GET", f"/tickets/{tid}.json")
                if r.status_code == 200:
                    still_exist.append(tid)
            if len(still_exist) >= len(Q1R_ZENDESK_TICKETS):
                log(f"  [reuse] {len(still_exist)} existing Q1R tickets")
                return {"org_id": org_id, "ticket_ids": still_exist}

        now = datetime(2026, 5, 27, tzinfo=timezone.utc)
        new_tids: list[int] = []
        for spec in Q1R_ZENDESK_TICKETS:
            created_at = now - timedelta(days=spec["days_ago_from_anchor"])
            updated_at = created_at + timedelta(days=2)
            ticket_spec = {
                "subject": f"[{c.name}] {spec['subject']}",
                "body": spec["body"],
                "priority": spec["priority"],
                "status": spec["status"],
                "type": spec["type"],
                "created_at": zd_isoformat(created_at),
                "updated_at": zd_isoformat(updated_at),
                "requester_id": user_id,
                "requester_email": QUILL_EMAIL,
            }
            try:
                tid = zendesk_import_ticket(client, ticket_spec)
            except TrialCapHit:
                log("  ! Zendesk trial cap hit - stopping ticket creation")
                break
            if tid:
                new_tids.append(tid)
                log(f"  [new] ticket {tid}: {spec['subject'][:50]}")
            else:
                log(f"  ! ticket create fail: {spec['subject'][:50]}")
        state["q1r_quill_tickets"] = new_tids
        zendesk_save_state(state)
        return {"org_id": org_id, "ticket_ids": new_tids}


# ──────────────────────────────────────────────────────────────────────
# 6. Slack - one post in #cs-escalations about the April downgrade convo
# ──────────────────────────────────────────────────────────────────────


SLACK_Q1R_MESSAGE = (
    "Q1R / Quill Logistics - quick CSM note. Had a call yesterday "
    "(2026-04-15) with Quill's VP Eng on downgrade options. They want "
    "to compare Standard tier pricing against current Pro Annual but "
    "explicitly framed it as 'evaluating, not cancelling.' Renewed "
    "normally in March, usage was up across Q1 across shipments + "
    "invoicing. No outage complaints. Logging for the AE."
)

# Local state file for Slack message-ts idempotency. The bot lacks
# `channels:history`, so we can't dedup via conversations.history.
SLACK_STATE_PATH = (
    SCRIPT_DIR.parent / ".manthan" / "q1r_quill_outage_state.json"
)


def _load_slack_state() -> dict[str, Any]:
    if SLACK_STATE_PATH.exists():
        try:
            import json
            return json.loads(SLACK_STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_slack_state(state: dict[str, Any]) -> None:
    import json
    SLACK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SLACK_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def slack_seed() -> tuple[str | None, str | None]:
    log("\n[SLACK]    posting CSM downgrade-conversation note to #cs-escalations…")
    state = _load_slack_state()
    with httpx.Client(timeout=SLACK_TIMEOUT) as client:
        auth = slack_call(client, "auth.test")
        if not auth.get("ok"):
            log(f"  ! Slack auth failed: {auth}")
            return None, None
        # Find the channel id.
        ch_list = slack_call(
            client, "conversations.list",
            params={"limit": 200, "exclude_archived": "true"},
        )
        channel_id = None
        for c in ch_list.get("channels", []):
            if c.get("name") == "cs-escalations":
                channel_id = c["id"]
                break
        if not channel_id:
            # Try to create it.
            log("  cs-escalations not found - creating…")
            create = slack_call(
                client, "conversations.create",
                json={"name": "cs-escalations", "is_private": False},
            )
            if create.get("ok"):
                channel_id = create["channel"]["id"]
            else:
                log(f"  ! could not create #cs-escalations: {create.get('error')}")
                return None, None

        # Ensure the bot is a member so we can post.
        slack_call(
            client, "conversations.join",
            json={"channel": channel_id},
        )

        # Idempotency path A: local state file (the bot lacks
        # channels:history scope, so we can't dedupe via the API).
        cached_ts = state.get("slack_q1r_message_ts")
        cached_ch = state.get("slack_q1r_channel_id")
        if cached_ts and cached_ch == channel_id:
            log(f"  [reuse] Slack message ts={cached_ts} (from state file)")
            return channel_id, cached_ts

        # Idempotency path B: best-effort conversations.history. This
        # only works if the bot ever gains channels:history scope; we
        # try silently and fall through to a fresh post on miss.
        history = slack_call(
            client, "conversations.history",
            params={"channel": channel_id, "limit": 100},
        )
        if history.get("ok"):
            for m in history.get("messages", []):
                if "Q1R / Quill Logistics" in (m.get("text") or ""):
                    ts = m.get("ts")
                    log(f"  [reuse] Slack message ts={ts}")
                    state["slack_q1r_message_ts"] = ts
                    state["slack_q1r_channel_id"] = channel_id
                    _save_slack_state(state)
                    return channel_id, ts

        # Post.
        post = slack_call(
            client, "chat.postMessage",
            json={"channel": channel_id, "text": SLACK_Q1R_MESSAGE},
        )
        if post.get("ok"):
            ts = post.get("ts")
            log(f"  [new]   Slack post ts={ts}")
            state["slack_q1r_message_ts"] = ts
            state["slack_q1r_channel_id"] = channel_id
            _save_slack_state(state)
            return channel_id, ts
        # Auto-join if bot isn't a member.
        if post.get("error") == "not_in_channel":
            slack_call(
                client, "conversations.join",
                json={"channel": channel_id},
            )
            post = slack_call(
                client, "chat.postMessage",
                json={"channel": channel_id, "text": SLACK_Q1R_MESSAGE},
            )
            if post.get("ok"):
                ts = post.get("ts")
                log(f"  [new]   Slack post ts={ts}")
                state["slack_q1r_message_ts"] = ts
                state["slack_q1r_channel_id"] = channel_id
                _save_slack_state(state)
                return channel_id, ts
        log(f"  ! Slack post failed: {post.get('error')}")
        return channel_id, None


# ──────────────────────────────────────────────────────────────────────
# 7. Notion - Chargeback Response Playbook v3 + Pro Annual Refund Policy
# ──────────────────────────────────────────────────────────────────────


Q1R_NOTION_PAGES = [
    NotionPage(
        title="Chargeback Response Playbook v3",
        category="Policy & SOP",
        signal_id="Q1R",
        headings=[(2, "Chargeback Response Playbook v3")],
        paragraphs=[
            "Owner: RevOps (priya@miny-labs.com) + Billing Engineering. "
            "Status: CURRENT - authoritative. Doc version 3.1 (2026-05). "
            "Last reviewed 2026-05-20. Supersedes Playbook v2 (2024).",

            "Scope: this playbook governs how we respond to Stripe "
            "chargebacks and customer-initiated refund requests when "
            "the customer alleges product unavailability, outage, or "
            "non-delivery. It is the authoritative reference for the "
            "FIGHT-vs-REFUND decision when the customer's framing "
            "centers on 'we couldn't access the product.'",

            "",
            "Section 1 - The corroboration test.",
            "Before responding to any outage-claim chargeback, the "
            "investigator MUST corroborate the alleged unavailability "
            "across BOTH the operational stack and the usage signal:",

            "(a) Operational stack - Sentry, Datadog, and PagerDuty.",
            "  - Sentry: pull error events for the customer's tenant in "
            "    the alleged-outage window. A real outage shows a clear "
            "    spike above the customer's tenant baseline (typically "
            "    0.3-0.5% error rate). Anything within baseline = no "
            "    outage signal.",
            "  - Datadog: pull the synthetic uptime monitor for the "
            "    customer's region. Real outages drop uptime below "
            "    99.9% for the affected window. 99.97%+ = clean.",
            "  - PagerDuty: pull P1/P2 incidents declared in the window "
            "    that touched the customer's region. Real outages declare "
            "    at least one P1; zero P1 = no outage.",

            "(b) Usage signal - PostHog.",
            "  - Pull distinct_user_id activity for the customer in the "
            "    disputed window. Count logins, distinct users, and "
            "    critical-path actions (e.g. create_shipment, "
            "    generate_invoice for a logistics customer). Active usage "
            "    is incompatible with the customer's 'couldn't access' "
            "    framing.",

            "",
            "Section 2 - The FIGHT decision rule.",
            "Fight chargebacks where the customer alleges outage but "
            "Sentry/Datadog/PagerDuty show clean operations during the "
            "disputed window AND the customer continued using the "
            "product (PostHog usage signal). This combination is "
            "incompatible with a good-faith outage claim. Cite policy "
            "ID CRP-2026-V3-S2 in the dispute submission.",

            "Evidence package for FIGHT: (i) Stripe charge succeeded + "
            "subscription active, (ii) Sentry error-rate snapshot for "
            "the customer's tenant across the alleged window, "
            "(iii) Datadog regional uptime + p95 latency snapshot, "
            "(iv) PagerDuty incident list for the window, "
            "(v) PostHog event count + distinct users + critical-path "
            "actions. Attach as PDF + cite raw IDs in the submission "
            "notes.",

            "",
            "Section 3 - The REFUND decision rule.",
            "Refund chargebacks where the operational stack confirms an "
            "outage OR the customer's PostHog activity is consistent "
            "with the 'couldn't access' claim. In vendor-failure cases "
            "see also 'Vendor failure refund policy.'",

            "",
            "Section 4 - Repeat-dispute pattern.",
            "If the customer has prior won-by-customer disputes in the "
            "trailing 14 months, escalate to RD-2026 SOP (Refunds & "
            "Disputes - 2026 SOP) regardless of operational data. "
            "First-time disputers with clean ops + active usage = FIGHT.",

            "",
            "Section 5 - Communication.",
            "On FIGHT: submit Stripe evidence with the corroboration "
            "package; do NOT email the customer until evidence is "
            "filed. On REFUND: refund full + apologize via the "
            "VFR-2026 or RD-2026 template depending on cause.",

            "Reference: policy id CRP-2026-V3. "
            "Internal URL https://miny-labs.notion.site/sop-chargeback-"
            "response-v3 . Approved by ops-leads + VP Finance. "
            "Next review: 2026-10-15.",
        ],
    ),
    NotionPage(
        title="Pro Annual Refund Policy 2026",
        category="Policy & SOP",
        signal_id="Q1R",
        headings=[(2, "Pro Annual Refund Policy 2026")],
        paragraphs=[
            "Owner: RevOps + Finance. Status: CURRENT - authoritative. "
            "Last reviewed 2026-03-01.",

            "Scope: refund rules for Pro Annual subscriptions, including "
            "the 30-day post-charge window and chargeback handling.",

            "",
            "Section 1 - Refund window.",
            "Refunds on Pro Annual subscriptions are granted in full "
            "ONLY within 30 days of the charge date. After 30 days the "
            "subscription is considered consumed for the prepaid year; "
            "no refunds, no prorated returns. Renewals fall under the "
            "same rule: a renewal charge is refundable for 30 days from "
            "the renewal date.",

            "Exceptions: vendor-failure cases (see VFR-2026), SLA-breach "
            "cases (see SLA-2026-04), and post-acquisition migration "
            "cleanup (PAM-2026) override this default - refund per the "
            "specific policy.",

            "",
            "Section 2 - Chargeback handling.",
            "If a customer files a Stripe chargeback after the 30-day "
            "refund window has closed and outside of the exception "
            "categories above, the default position is to fight per the "
            "Chargeback Response Playbook v3 (CRP-2026-V3).",

            "Specifically: a chargeback filed more than 30 days after "
            "the charge that alleges product non-delivery / outage "
            "without any prior outage complaint in support channels "
            "(Intercom, Zendesk) is a candidate for FIGHT - corroborate "
            "via the operational stack and PostHog before submitting.",

            "",
            "Section 3 - Communication template.",
            "When fighting, do NOT engage the customer directly until "
            "evidence is submitted. When refunding (within policy), use "
            "the standard 'refund issued' email template.",

            "Reference: policy id PAR-2026. Internal URL "
            "https://miny-labs.notion.site/sop-pro-annual-refund-2026 . "
            "Next review: 2026-09-15.",
        ],
    ),
]


def notion_seed() -> list[tuple[str, str]]:
    log("\n[NOTION]   ensuring Q1R playbook + Pro Annual refund policy pages…")
    out: list[tuple[str, str]] = []
    with httpx.Client(headers=NOTION_HEADERS, timeout=NOTION_TIMEOUT) as client:
        try:
            parent_id, parent_title = notion_find_parent(client)
            log(f"  parent: {parent_title} ({parent_id})")
        except SystemExit as e:
            log(f"  ! Notion parent page not found: {e}")
            return out
        time.sleep(NOTION_REQ_SLEEP)
        existing = notion_list_children(client, parent_id)
        for page in Q1R_NOTION_PAGES:
            if page.title in existing:
                log(f"  [reuse] {page.title} → {existing[page.title]}")
                out.append((page.title, existing[page.title]))
                continue
            payload = _page_payload(parent_id, page)
            r = notion_request(client, "POST", "/pages", json=payload)
            if r.status_code in (200, 201):
                pid = r.json().get("id", "")
                log(f"  [new]   {page.title} → {pid[:8]}…")
                out.append((page.title, pid))
            else:
                log(f"  ! Notion create fail {page.title!r}: "
                    f"{r.status_code} {r.text[:200]}")
            time.sleep(NOTION_REQ_SLEEP)
    return out


# ──────────────────────────────────────────────────────────────────────
# 8. PostHog - Q1 usage events for Quill
# ──────────────────────────────────────────────────────────────────────


# 8 distinct user personas for Quill.
QUILL_POSTHOG_PERSONAS = [
    {"distinct_id": "quill-logi-user-1", "role": "ar-lead",
     "email": f"ar-lead@{QUILL_DOMAIN}", "name": "Amelia Park"},
    {"distinct_id": "quill-logi-user-2", "role": "vp-eng",
     "email": f"vp-eng@{QUILL_DOMAIN}", "name": "Marcus Chen"},
    {"distinct_id": "quill-logi-user-3", "role": "ops-analyst",
     "email": f"ops1@{QUILL_DOMAIN}", "name": "Priya Singh"},
    {"distinct_id": "quill-logi-user-4", "role": "ops-analyst",
     "email": f"ops2@{QUILL_DOMAIN}", "name": "Jordan Reyes"},
    {"distinct_id": "quill-logi-user-5", "role": "warehouse-lead",
     "email": f"wh-east@{QUILL_DOMAIN}", "name": "Sara Nakamura"},
    {"distinct_id": "quill-logi-user-6", "role": "warehouse-lead",
     "email": f"wh-west@{QUILL_DOMAIN}", "name": "Devon Patel"},
    {"distinct_id": "quill-logi-user-7", "role": "finance",
     "email": f"finance@{QUILL_DOMAIN}", "name": "Lina Kim"},
    {"distinct_id": "quill-logi-user-8", "role": "admin",
     "email": f"admin@{QUILL_DOMAIN}", "name": "Tomas Garcia"},
]

# Q1 2026 window for usage events.
Q1_START = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
Q1_END = datetime(2026, 3, 31, 18, 0, 0, tzinfo=timezone.utc)


def _q1_random_ts(rng: random.Random) -> datetime:
    span_s = int((Q1_END - Q1_START).total_seconds())
    offset = rng.randint(0, span_s)
    return Q1_START + timedelta(seconds=offset)


def _q1_random_iso(rng: random.Random) -> str:
    return _q1_random_ts(rng).isoformat()


def build_posthog_events(stripe_customer_id: str) -> list[dict]:
    """Build the Q1 activity events for Quill.

    Target: 22 logins, 8 distinct users active, 47 critical-path actions.
    Plus $identify events for each persona to ensure Person rows exist.
    """
    events: list[dict] = []
    rng = random.Random(20260101)

    base_props = {
        "company_slug": QUILL_SLUG,
        "company": QUILL_NAME,
        "plan": QUILL_PLAN,
        "arr_usd": QUILL_ARR_USD,
        "industry": QUILL_INDUSTRY,
        "country": QUILL_COUNTRY,
        "region": QUILL_REGION,
        "stripe_customer_id": stripe_customer_id,
        "seeded_by": "patch_q1_quill_outage",
        "workflow": "Q1R",
        "$lib": "manthan-q1r-patch",
    }

    # 1) $identify per persona - establishes the Person row in PostHog.
    for p in QUILL_POSTHOG_PERSONAS:
        events.append({
            "event": "$identify",
            "distinct_id": p["distinct_id"],
            "properties": {
                **base_props,
                "$set": {
                    "email": p["email"],
                    "name": p["name"],
                    "company": QUILL_NAME,
                    "company_slug": QUILL_SLUG,
                    "plan": QUILL_PLAN,
                    "role": p["role"],
                    "team": "logistics",
                    "arr_usd": QUILL_ARR_USD,
                    "stripe_customer_id": stripe_customer_id,
                    "seeded_by": "patch_q1_quill_outage",
                    "workflow": "Q1R",
                    # Marker so the agent can verify product usage.
                    "active_in_disputed_window": True,
                },
                "$set_once": {
                    "first_seen": "2024-05-14T09:00:00Z",
                    "signup_year": 2024,
                },
            },
            "timestamp": (Q1_START - timedelta(days=1)).isoformat(),
        })

    # 2) 22 logins across the 8 personas in Q1.
    for i in range(22):
        persona = QUILL_POSTHOG_PERSONAS[i % len(QUILL_POSTHOG_PERSONAS)]
        ts = _q1_random_ts(rng)
        events.append({
            "event": "user_logged_in",
            "distinct_id": persona["distinct_id"],
            "properties": {
                **base_props,
                "role": persona["role"],
                "login_method": rng.choice(["password", "sso", "sso", "sso"]),
                "user_agent": "Manthan-Q1R-Seed/1.0",
            },
            "timestamp": ts.isoformat(),
        })

    # 3) 47 critical-path actions across the 8 personas in Q1.
    CRITICAL_ACTIONS = [
        ("create_shipment", "shipments"),
        ("create_shipment", "shipments"),
        ("create_shipment", "shipments"),
        ("generate_invoice", "invoices"),
        ("generate_invoice", "invoices"),
        ("update_warehouse_inventory", "inventory"),
        ("dispatch_route", "routing"),
        ("dispatch_route", "routing"),
        ("reconcile_payments", "finance"),
        ("export_monthly_report", "reports"),
    ]
    for i in range(47):
        persona = QUILL_POSTHOG_PERSONAS[i % len(QUILL_POSTHOG_PERSONAS)]
        action, area = CRITICAL_ACTIONS[i % len(CRITICAL_ACTIONS)]
        ts = _q1_random_ts(rng)
        props = {
            **base_props,
            "role": persona["role"],
            "action": action,
            "area": area,
            "is_critical_path": True,
        }
        if action == "create_shipment":
            props["shipment_id"] = f"shp_q1r_{i:04d}"
            props["origin_warehouse"] = rng.choice([
                "wh-east-01", "wh-east-02", "wh-west-01"
            ])
        elif action == "generate_invoice":
            props["invoice_id"] = f"inv_q1r_{i:04d}"
            props["amount_usd"] = round(rng.uniform(120, 9800), 2)
        elif action == "dispatch_route":
            props["route_id"] = f"rt_q1r_{i:04d}"
            props["stops_count"] = rng.randint(8, 75)
        events.append({
            "event": action,
            "distinct_id": persona["distinct_id"],
            "properties": props,
            "timestamp": ts.isoformat(),
        })

    return events


def posthog_seed(stripe_customer_id: str) -> dict[str, Any]:
    log("\n[POSTHOG]  ingesting Q1 usage events for Quill…")
    out = {"events_sent": 0, "events_error": 0, "personas": len(QUILL_POSTHOG_PERSONAS)}
    state = _load_slack_state()
    if state.get("posthog_q1r_seeded_for_customer") == stripe_customer_id:
        log("  [reuse] PostHog Q1 events already ingested for this customer "
            "(state file). Skipping to avoid event duplication.")
        out["events_sent"] = state.get("posthog_q1r_events_sent", 0)
        return out
    with httpx.Client(headers=POSTHOG_HEADERS, timeout=POSTHOG_TIMEOUT) as client:
        project_key = fetch_project_api_key(client)
        if not project_key:
            log("  ! PostHog project key unavailable - skipping ingestion.")
            return out
        events = build_posthog_events(stripe_customer_id)
        log(f"  persons={len(QUILL_POSTHOG_PERSONAS)}  events={len(events)}")
        sent, errs = posthog_ingest_events(client, events, project_key)
        out["events_sent"] = sent
        out["events_error"] = errs
        log(f"  ingested {sent}  errors {errs}")
    state["posthog_q1r_seeded_for_customer"] = stripe_customer_id
    state["posthog_q1r_events_sent"] = sent
    _save_slack_state(state)
    return out


# ──────────────────────────────────────────────────────────────────────
# 9. Sentry - Q1 baseline error events tagged to Quill's tenant
# ──────────────────────────────────────────────────────────────────────


Q1R_SENTRY_PROJECT_SLUG = "api-gateway"
Q1R_SENTRY_TEAM_SLUG = "platform"
Q1R_SENTRY_TITLE = (
    "ValueError: Optional warehouse_id missing on inbound shipment "
    "payload - backfilled with account default"
)


def sentry_seed(stripe_customer_id: str) -> int:
    """Ingest ~22 baseline-error events tagged to Quill's tenant in Q1.

    Distributed across the Q1 window to look like routine baseline noise
    (not a spike). The agent should see ~0.4% error rate consistent with
    a clean operation.
    """
    log("\n[SENTRY]   ingesting Q1 baseline error events for Quill tenant…")
    state = _load_slack_state()
    if state.get("sentry_q1r_seeded_for_customer") == stripe_customer_id:
        log("  [reuse] Sentry Q1 events already ingested for this customer "
            "(state file). Skipping to avoid event duplication.")
        return state.get("sentry_q1r_events_count", 0)
    with httpx.Client(headers=SENTRY_HEADERS, timeout=SENTRY_TIMEOUT) as client:
        try:
            sentry_ping_org(client)
        except SystemExit as e:
            log(f"  ! Sentry org ping failed: {e}")
            return 0
        existing_teams = {t["slug"]: t for t in sentry_list_teams(client)}
        if Q1R_SENTRY_TEAM_SLUG not in existing_teams:
            sentry_ensure_team(client, "Platform Eng", Q1R_SENTRY_TEAM_SLUG)
        existing_projects = {p["slug"]: p for p in sentry_list_projects(client)}
        if Q1R_SENTRY_PROJECT_SLUG not in existing_projects:
            sentry_ensure_project(
                client, Q1R_SENTRY_TEAM_SLUG,
                "API Gateway", Q1R_SENTRY_PROJECT_SLUG, "python",
            )
        dsn = sentry_get_project_dsn(client, Q1R_SENTRY_PROJECT_SLUG)

    # Initialise the sentry_sdk for the api-gateway project.
    sentry_init_for_project(dsn)
    total_events = 22  # ~0.4% baseline error rate
    rng = random.Random(20260131)
    Q1R_FINGERPRINT = ["ValueError", Q1R_SENTRY_TITLE]

    for i in range(total_events):
        ts = _q1_random_ts(rng).isoformat()
        narrative_date = ts[:10]
        with sentry_sdk.push_scope() as scope:
            scope.level = "warning"  # type: ignore[assignment]
            scope.fingerprint = Q1R_FINGERPRINT
            scope.set_tag("service", "api-gateway")
            scope.set_tag("env", "production")
            scope.set_tag("tenant", QUILL_SLUG)
            scope.set_tag("customer_slug", QUILL_SLUG)
            scope.set_tag("customer_id", stripe_customer_id)
            scope.set_tag("customer_domain", QUILL_DOMAIN)
            scope.set_tag("region", QUILL_REGION)
            scope.set_tag("workflow", "Q1R")
            scope.set_tag("narrative_date", narrative_date)
            scope.set_context(
                "tenant_context",
                {
                    "customer_id": stripe_customer_id,
                    "company_slug": QUILL_SLUG,
                    "region": QUILL_REGION,
                    "narrative_event_time": ts,
                    "baseline_error_rate_pct": 0.4,
                    "is_outage": False,
                    "note": (
                        "Routine baseline error tagged to Quill's tenant "
                        "during the Q1 2026 disputed-outage window. Part of "
                        "normal baseline noise - no spike, no outage."
                    ),
                },
            )
            try:
                raise ValueError(
                    f"{Q1R_SENTRY_TITLE} (customer {stripe_customer_id} "
                    f"narrative_time {ts})"
                )
            except ValueError:
                sentry_sdk.capture_exception()
        time.sleep(INGEST_SLEEP)

    # Baseline-confirming summary message.
    with sentry_sdk.push_scope() as scope:
        scope.level = "info"  # type: ignore[assignment]
        scope.fingerprint = Q1R_FINGERPRINT
        scope.set_tag("service", "api-gateway")
        scope.set_tag("env", "production")
        scope.set_tag("tenant", QUILL_SLUG)
        scope.set_tag("customer_id", stripe_customer_id)
        scope.set_tag("workflow", "Q1R")
        sentry_sdk.capture_message(
            f"Q1 2026 baseline error-rate summary for tenant {QUILL_SLUG} "
            f"(customer {stripe_customer_id}): ~0.4% across the 90-day "
            "window 2026-01-01 → 2026-03-31, no anomaly spike, no outage. "
            "Used as the corroboration baseline for chargeback Q1R "
            "(alleged-outage refund claim).",
            level="info",
        )
    sentry_sdk.flush(timeout=15.0)
    log(f"  Sentry events ingested: {total_events + 1}")
    state["sentry_q1r_seeded_for_customer"] = stripe_customer_id
    state["sentry_q1r_events_count"] = total_events + 1
    _save_slack_state(state)
    return total_events + 1


# ──────────────────────────────────────────────────────────────────────
# 10. Datadog - synthetic monitor for us-east-1 region (Q1 uptime 99.97%)
# ──────────────────────────────────────────────────────────────────────


def q1r_datadog_monitor(stripe_customer_id: str) -> DDMonitorSpec:
    msg = (
        "Synthetic uptime monitor for the us-east-1 region serving "
        f"Quill Logistics ({stripe_customer_id}). \n\n"
        f"Q1 2026 narrative summary "
        f"({DISPUTED_WINDOW_START} → {DISPUTED_WINDOW_END}):\n"
        "  - Uptime: 99.97% (well within SLA)\n"
        "  - p95 latency: 247ms (within 800ms SLA)\n"
        "  - p99 latency: 612ms (within 1.5s SLA)\n"
        "  - Zero SEV-1 or SEV-2 incidents in this region during Q1.\n\n"
        "This monitor is the authoritative regional uptime reference "
        "for chargeback workflow Q1R (Quill Logistics alleged-outage "
        "claim). When investigating an alleged-outage chargeback, "
        f"correlate the customer's region (Quill = {QUILL_REGION}) "
        "with this monitor's history and Datadog event log."
    )
    return DDMonitorSpec(
        name=f"synthetic.us-east-1 uptime (Quill Logistics region)",
        type="query alert",
        query=(
            "avg(last_1h):avg:synthetics.test.uptime"
            "{region:us-east-1,test_name:quill-logi-region-pulse} < 0.999"
        ),
        message=msg,
        tags=[
            "env:prod",
            "team:platform",
            "service:synthetics",
            f"region:{QUILL_REGION}",
            f"customer_id:{stripe_customer_id}",
            f"customer_domain:{QUILL_DOMAIN}",
            "customer_slug:quill-logi",
            "workflow:Q1R-quill-q1-outage",
            "status:ok",
            f"narrative_window:{DISPUTED_WINDOW_START}_{DISPUTED_WINDOW_END}",
            "narrative_uptime_pct:99.97",
        ],
        options=dd_common_options(
            {"critical": 0.999, "warning": 0.9995},
            notify_no_data=False,
        ),
        note_state="OK",
    )


def q1r_datadog_event(stripe_customer_id: str) -> DDEventSpec:
    return DDEventSpec(
        title=(
            f"Q1 2026 regional health summary - {QUILL_REGION} "
            f"(workflow:Q1R Quill Logistics)"
        ),
        text=(
            f"Synthetic + APM rollup for region {QUILL_REGION} during "
            f"the chargeback Q1R disputed window "
            f"({DISPUTED_WINDOW_START} → {DISPUTED_WINDOW_END}).\n\n"
            "Narrative summary:\n"
            "  - Synthetic uptime: 99.97% (SLA: 99.9%) - clean.\n"
            "  - p95 latency: 247ms (SLA: 800ms) - clean.\n"
            "  - p99 latency: 612ms (SLA: 1.5s) - clean.\n"
            "  - Zero SEV-1 incidents touching this region.\n"
            "  - Two routine sub-5-minute SEV-3 blips on auth-service "
            "    (2026-02-14 and 2026-03-08), each resolved < 5 min, "
            "    impacted ~0.3% of region traffic, no customer-reported "
            "    outage.\n\n"
            f"Customer in scope: {stripe_customer_id} ({QUILL_NAME}, "
            f"{QUILL_DOMAIN}, Pro Annual). This event is the Datadog "
            "anchor for the Q1R chargeback investigation. Tag-search "
            "by workflow:Q1R-quill-q1-outage or "
            f"customer_id:{stripe_customer_id} to locate."
        ),
        date_happened=dd_epoch(dd_hours_ago(4)),
        tags=[
            "service:synthetics",
            "service:api-gateway",
            "env:prod",
            "team:platform",
            f"region:{QUILL_REGION}",
            f"customer_id:{stripe_customer_id}",
            f"customer_domain:{QUILL_DOMAIN}",
            "customer_slug:quill-logi",
            "workflow:Q1R-quill-q1-outage",
            f"narrative_window:{DISPUTED_WINDOW_START}_{DISPUTED_WINDOW_END}",
            "summary:regional-health-rollup",
        ],
        alert_type="success",
    )


def datadog_seed(stripe_customer_id: str) -> tuple[int | None, int | None]:
    log("\n[DATADOG]  ensuring synthetic monitor + regional health event…")
    mon_spec = q1r_datadog_monitor(stripe_customer_id)
    evt_spec = q1r_datadog_event(stripe_customer_id)
    monitor_id = None
    event_id = None
    with httpx.Client(headers=DD_HEADERS, timeout=DD_TIMEOUT) as client:
        mid, action = dd_upsert_monitor(client, mon_spec)
        monitor_id = mid
        log(f"  monitor [{action}] id={mid}  name={mon_spec.name}")
        time.sleep(DD_REQ_SLEEP)
        eid, eaction = dd_post_event(client, evt_spec)
        event_id = eid
        log(f"  event   [{eaction}] id={eid}")
    return monitor_id, event_id


# ──────────────────────────────────────────────────────────────────────
# 11. PagerDuty - zero P1/P2 incidents in Q1 touching Quill's region.
#
# We can't seed "zero incidents" directly. Instead we make the absence
# corroborable by seeding a LOW-urgency "Q1 regional incident summary"
# incident that explicitly documents: zero P1, zero P2, only routine
# SEV-3 sub-5-minute blips. Marked resolved with a note. The agent's
# PagerDuty query for the region in Q1 will find this summary and
# corroborate the no-outage claim.
# ──────────────────────────────────────────────────────────────────────


Q1R_PD_SERVICE = "api-gateway"
Q1R_PD_SERVICE_DESC = (
    "Public-facing HTTPS edge → routes to upstream services. Handles "
    "rate limiting, request signing, mTLS termination."
)
Q1R_PD_TITLE = (
    f"api-gateway: Q1 2026 regional health summary - us-east-1 "
    "(workflow:Q1R Quill Logistics no-outage corroboration)"
)


def q1r_pd_body(stripe_customer_id: str) -> str:
    return (
        f"Regional Q1 2026 health rollup for {QUILL_REGION}, scoped to "
        f"customer {stripe_customer_id} ({QUILL_NAME}, {QUILL_DOMAIN}).\n\n"
        "Purpose: this incident exists as a queryable anchor for the "
        "Q1R chargeback investigation (Quill Logistics filed a $9k "
        "chargeback alleging a Q1 2026 outage). The customer's region "
        f"is {QUILL_REGION}. This incident summarises what actually "
        f"happened in that region during the disputed window "
        f"({DISPUTED_WINDOW_START} → {DISPUTED_WINDOW_END}).\n\n"
        "Findings:\n"
        f"  - Zero P1 incidents declared in {QUILL_REGION} during Q1 2026.\n"
        f"  - Zero P2 incidents declared in {QUILL_REGION} during Q1 2026.\n"
        f"  - Two routine SEV-3 micro-blips: 2026-02-14 (~3 min "
        f"auth-svc latency bump), 2026-03-08 (~4 min CDN cache miss "
        f"storm). Neither affected Quill's tenant (verified via Sentry "
        f"tenant-tagged events) and neither qualifies as an outage by "
        f"any reasonable definition.\n"
        f"  - Synthetic uptime monitor (Datadog) shows 99.97% over the "
        f"window - well above SLA.\n\n"
        f"Conclusion: no outage in {QUILL_REGION} during Q1 2026 that "
        f"could plausibly support Quill's chargeback claim. Recommend "
        f"FIGHT per Chargeback Response Playbook v3 (CRP-2026-V3-S2).\n\n"
        f"Cross-references: Sentry tenant baseline for {stripe_customer_id}, "
        f"Datadog synthetic 'us-east-1 uptime (Quill Logistics region)', "
        f"PostHog Q1 activity (22 logins, 8 distinct users, 47 critical-"
        f"path actions on Quill's tenant), Notion playbook "
        f"'Chargeback Response Playbook v3'."
    )


def pagerduty_seed(stripe_customer_id: str) -> str | None:
    log("\n[PAGERDUTY] ensuring api-gateway service + Q1 regional summary…")
    with httpx.Client(headers=PD_HEADERS, timeout=PD_TIMEOUT) as client:
        # 1. Find or initialise an escalation policy.
        ep_id = None
        sid, ep_existing = pd_find_service_by_name(client, Q1R_PD_SERVICE)
        if ep_existing:
            ep_id = ep_existing
        if not ep_id:
            r = pagerduty_request(client, "GET", "/services",
                                  params={"limit": 25})
            if r.status_code == 200:
                for s in r.json().get("services", []):
                    if s.get("escalation_policy", {}).get("id"):
                        ep_id = s["escalation_policy"]["id"]
                        break
        if not ep_id:
            ep_id = pd_first_escalation_policy_id(client)
        if not ep_id:
            log("  ! no escalation policy in PagerDuty - cannot seed")
            return None

        # 2. Service.
        sid, action = pd_upsert_service(
            client, Q1R_PD_SERVICE, Q1R_PD_SERVICE_DESC, ep_id
        )
        log(f"  service [{action}] {Q1R_PD_SERVICE} → {sid}")
        if not sid:
            return None
        time.sleep(PD_REQ_SLEEP)

        # 3. Idempotency.
        existing_keys = pd_fetch_all_incident_keys(client)
        ikey = pd_incident_key(Q1R_PD_SERVICE, Q1R_PD_TITLE, salt="Q1R")
        if ikey in existing_keys:
            log(f"  Q1R incident already seeded (key={ikey})")
            r = pagerduty_request(
                client, "GET", "/incidents",
                params={"incident_key": ikey},
            )
            if r.status_code == 200:
                incs = r.json().get("incidents", [])
                if incs:
                    return incs[0].get("id")
            return None

        # 4. Create LOW-urgency summary incident + resolve.
        inc_id, inc_num = pd_create_incident(
            client, sid,
            Q1R_PD_TITLE,
            "low",  # low-urgency summary, not an active page
            q1r_pd_body(stripe_customer_id),
            ikey,
        )
        if not inc_id:
            log("  ! could not create Q1R summary incident")
            return None
        log(f"  incident [created] id={inc_id} number={inc_num}")
        time.sleep(PD_REQ_SLEEP)
        if pd_update_incident_status(client, inc_id, "resolved"):
            log(f"  incident [resolved]")
        return inc_id


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    log("=" * 72)
    log("Manthan Q1R patch - Quill Logistics alleged-outage chargeback")
    log("=" * 72)

    c = quill_company()
    log(f"\nCustomer: {c.name} / {c.slug}")
    log(f"  email   : {c.email}")
    log(f"  ARR     : ${c.arr_usd:,}")
    log(f"  plan    : {c.plan}")
    log(f"  region  : {QUILL_REGION}")

    # 1. Stripe - required (drives the chargeback)
    cust = stripe_ensure_customer(c)
    price = stripe_find_pro_annual_price()
    sub = stripe_ensure_subscription(cust, price.id)
    ch, disp = stripe_create_disputed_charge_and_dispute(cust)
    stripe_customer_id = cust.id

    # 2. Salesforce - best-effort
    sf_account_id = salesforce_seed(c, stripe_customer_id)

    # 3. HubSpot
    hs_cid, hs_nid = hubspot_seed(c, stripe_customer_id)

    # 4. Intercom
    ic_contact_id, ic_convos = intercom_seed()

    # 5. Zendesk
    zd_result = zendesk_seed(c)

    # 6. Slack
    slack_channel_id, slack_ts = slack_seed()

    # 7. Notion
    notion_pages = notion_seed()

    # 8. PostHog
    ph_result = posthog_seed(stripe_customer_id)

    # 9. Sentry
    sentry_event_count = sentry_seed(stripe_customer_id)

    # 10. Datadog
    dd_monitor_id, dd_event_id = datadog_seed(stripe_customer_id)

    # 11. PagerDuty
    pd_incident_id = pagerduty_seed(stripe_customer_id)

    # ── Summary ──
    log("\n" + "═" * 72)
    log("Q1R SEED SUMMARY")
    log("═" * 72)
    log(f"Stripe customer        : {stripe_customer_id}")
    log(f"Stripe subscription    : {sub.id}")
    log(f"Stripe charge          : {ch.id}  ${ch.amount/100:,.2f}")
    log(f"Stripe dispute         : {disp.id}  reason={disp.reason} "
        f"status={disp.status}")
    log(f"Salesforce account     : {sf_account_id or '(skipped)'}")
    log(f"HubSpot company        : {hs_cid}")
    log(f"HubSpot VP-Eng note    : {hs_nid}")
    log(f"Intercom contact       : {ic_contact_id}")
    log(f"Intercom Q1 convos     : {len(ic_convos)}")
    log(f"Zendesk org            : {zd_result.get('org_id')}")
    log(f"Zendesk older tickets  : {len(zd_result.get('ticket_ids', []))}")
    log(f"Slack channel          : {slack_channel_id}  ts={slack_ts}")
    log(f"Notion pages           : {len(notion_pages)}")
    for title, pid in notion_pages:
        log(f"  - {title}: {pid[:8]}…")
    log(f"PostHog events sent    : {ph_result.get('events_sent')} "
        f"errors={ph_result.get('events_error')}")
    log(f"Sentry events ingested : {sentry_event_count}")
    log(f"Datadog monitor        : {dd_monitor_id}")
    log(f"Datadog summary event  : {dd_event_id}")
    log(f"PagerDuty Q1 summary   : {pd_incident_id}")

    log("\nQ1R is seeded. To trigger the case in the API, route the "
        "Stripe dispute id below into your trigger flow:")
    log(f"  dispute_id = {disp.id}")
    log(f"  charge_id  = {ch.id}")
    log(f"  customer   = {stripe_customer_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
