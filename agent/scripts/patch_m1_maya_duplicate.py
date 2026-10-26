"""Patch M1R - Maya Patel small autonomous duplicate-charge refund.

Seeds evidence across all 11 connected sources so the Manthan agent
investigating Maya's "I was charged twice" email can corroborate the
duplicate-charge root cause (OUR webhook handler retry bug), confirm
Maya is in good standing, match the autonomous "small-refund-auto"
policy, and refund + auto-reply without a human in the loop:

  Stripe       - Test-mode customer keyed on hitakshi220@gmail.com.
                 Caldera Pro subscription at $89/mo. TWO successful
                 $89 charges on 2026-05-22 four minutes apart:
                 charge A 14:21:03 UTC, charge B 14:25:09 UTC (the
                 duplicate). Both tagged
                 metadata.webhook_retry_chain=evt_xxx_retry. Zero
                 disputes - this is NOT a chargeback yet, just a
                 customer email.
  Salesforce   - "Maya Patel Design" account with the same Gmail
                 address. 18-month tenure. CSM=null. Zero prior
                 disputes.
  HubSpot      - Contact for Maya at hitakshi220@gmail.com. NPS=9,
                 lifecyclestage=customer, long engagement history.
  Intercom     - Bare contact record only. ZERO conversations - Maya
                 has never raised an issue before, which is itself the
                 "good standing" signal the agent must verify.
  Zendesk      - Org + user. Zero tickets in the trailing 90 days.
                 One unrelated 2025 feature-request ticket (solved).
  Slack        - NO internal mention of Maya. She's small enough that
                 CS has never escalated her. (We seed nothing.)
  Notion       - "Small-refund policy - duplicate charges under $200"
                 codifying the AUTONOMOUS path: duplicate charges
                 under $200 from customers in good standing within
                 60 days → AUTO-REFUND + AUTO-REPLY. No human review.
  PostHog      - Maya's normal usage events: ~6 logins in last 7 days,
                 create_design + export_design actions. Nothing
                 anomalous.
  Sentry       - CRITICAL root-cause beat. A RetryError event tagged
                 to stripe-webhook-handler project at exactly
                 2026-05-22T14:25:09 UTC matching the duplicate-charge
                 timestamp. Plus a handful of baseline noise events.
  Datadog      - A log event from webhook-router at 2026-05-22T14:25:09
                 showing the SAME Stripe charge.succeeded event id
                 POSTed twice (handler 500'd first time, Stripe
                 retried 4 min later, both charges processed).
  PagerDuty    - A P3 incident auto-created from the Datadog alert at
                 2026-05-22T14:25 titled "webhook-router 5xx spike",
                 service=webhook-router, status=resolved (resolved
                 2026-05-22T14:32). Proves the system bug was real
                 and already detected.

Idempotent: every resource is looked up by name/idem-key before
creation. State file at agent/.manthan/m1r_maya_state.json caches
event-bearing resources (Sentry events, PostHog events, Datadog
events, Slack ts) so re-runs don't double-ingest.

Run:
    cd agent && uv run python scripts/patch_m1_maya_duplicate.py
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
from seed_sentry import (  # noqa: E402
    HEADERS as SENTRY_HEADERS,
    INGEST_SLEEP,
    TIMEOUT as SENTRY_TIMEOUT,
    _init_for_project as sentry_init_for_project,
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
    _epoch as dd_epoch,
    _hours_ago as dd_hours_ago,
    post_event as dd_post_event,
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
            upsert_contact as sf_upsert_contact,
        )
    except Exception:
        SALESFORCE_AVAILABLE = False


# Stripe is required - bail loudly if not configured.
stripe.api_key = os.getenv("STRIPE_API_KEY")
if not stripe.api_key or not stripe.api_key.startswith("sk_test_"):
    raise SystemExit("STRIPE_API_KEY must be a sk_test_... key in agent/.env")


# ──────────────────────────────────────────────────────────────────────
# M1R constants
# ──────────────────────────────────────────────────────────────────────

MAYA_SLUG = "maya-patel-design"
MAYA_NAME = "Maya Patel Design"
MAYA_FIRST_NAME = "Maya"
MAYA_LAST_NAME = "Patel"
MAYA_EMAIL = "hitakshi220@gmail.com"  # the demo presenter's real Gmail
MAYA_DOMAIN = "gmail.com"
MAYA_INDUSTRY = "design freelancer"
MAYA_COUNTRY = "USA"
MAYA_REGION = "us-east-1"
MAYA_ARR_USD = 1068
MAYA_PLAN = "Pro Monthly"
MAYA_PLAN_DISPLAY = "Caldera Pro"
MAYA_MONTHLY_USD = 89
MAYA_MONTHLY_MINOR = 8900  # the duplicate amount to refund
MAYA_NPS = 9
MAYA_TENURE_MONTHS = 18

# The duplicate happened 2026-05-22 (per scenario spec). Charge A at
# 14:21:03 UTC; webhook handler 500'd on the first delivery; Stripe
# retried 4 minutes later; handler succeeded the second time but the
# upstream charge had already gone through, producing charge B at
# 14:25:09 UTC. Same Stripe charge.succeeded event id was POSTed twice.
CHARGE_DATE = "2026-05-22"
CHARGE_A_TIMESTAMP = "2026-05-22T14:21:03+00:00"  # original
CHARGE_B_TIMESTAMP = "2026-05-22T14:25:09+00:00"  # duplicate (after retry)
# Shared narrative Stripe event id - the one that was retried.
STRIPE_WEBHOOK_RETRY_CHAIN_ID = "evt_test_chargesucc_retry_m1r"
WEBHOOK_RETRY_GAP_SEC = 246  # 14:25:09 - 14:21:03 = 4 min 6 sec

# Policy that fires for M1R.
SMALL_REFUND_POLICY_ID = "small-refund-auto"
SMALL_REFUND_POLICY_TITLE = (
    "Small-refund policy - duplicate charges under $200"
)

# Deterministic randomness so re-runs are reproducible.
RNG = random.Random(20260522)


# ──────────────────────────────────────────────────────────────────────
# State file (idempotency for event-bearing resources)
# ──────────────────────────────────────────────────────────────────────


M1R_STATE_PATH = (
    SCRIPT_DIR.parent / ".manthan" / "m1r_maya_state.json"
)


def _load_state() -> dict[str, Any]:
    if M1R_STATE_PATH.exists():
        try:
            import json
            return json.loads(M1R_STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict[str, Any]) -> None:
    import json
    M1R_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    M1R_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


# ──────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────


def log(msg: str = "") -> None:
    print(msg, flush=True)


# ──────────────────────────────────────────────────────────────────────
# 1. Stripe - customer + Caldera Pro subscription + two $89 charges
# ──────────────────────────────────────────────────────────────────────


def maya_company() -> Company:
    return world_find_company(MAYA_SLUG)


def stripe_ensure_customer(c: Company) -> stripe.Customer:
    log("\n[STRIPE]  ensuring Maya customer…")
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
            "plan_display": MAYA_PLAN_DISPLAY,
            "monthly_usd": str(MAYA_MONTHLY_USD),
            "region": MAYA_REGION,
            "nps": str(MAYA_NPS),
            "tenure_months": str(MAYA_TENURE_MONTHS),
            "prior_disputes_count": "0",
            "csm": "(none)",
            "seeded_by": "manthan_seed_stripe",
            "workflow": "M1R",
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


def stripe_ensure_caldera_price() -> stripe.Price:
    """Find or create the Caldera Pro $89/mo price.

    Maya is on a custom plan that doesn't match the existing Pro Monthly
    test catalog ($420/mo). We create a $89/mo recurring price tagged
    with M1R metadata so the agent can locate the subscription cleanly.
    """
    log("\n[STRIPE]  ensuring Caldera Pro $89/mo price…")
    # Idempotency: search existing prices by our M1R marker.
    for pr in stripe.Price.list(limit=100, active=None).auto_paging_iter():
        md = md_dict(pr)
        if (md.get("seeded_by") == "manthan_seed_stripe"
                and md.get("price_key") == "caldera_pro_monthly"):
            log(f"  [reuse] price {pr.id} (${pr.unit_amount/100:.2f}/{pr.recurring.interval})")
            return pr
    # Locate or create the product.
    product_id = None
    for prod in stripe.Product.list(limit=100, active=None).auto_paging_iter():
        md = md_dict(prod)
        if (md.get("seeded_by") == "manthan_seed_stripe"
                and md.get("product_key") == "caldera_pro"):
            product_id = prod.id
            break
    if not product_id:
        prod = safe_create(
            stripe.Product.create,
            idem_key=idem("product", "caldera_pro"),
            label="Product[caldera_pro]",
            name="Caldera Pro",
            description="Caldera Pro - monthly plan for solo designers.",
            metadata={
                "seeded_by": "manthan_seed_stripe",
                "product_key": "caldera_pro",
                "workflow": "M1R",
            },
        )
        product_id = prod.id
        log(f"  [new] product caldera_pro → {product_id}")
    pr = safe_create(
        stripe.Price.create,
        idem_key=idem("price", "caldera_pro_monthly"),
        label="Price[caldera_pro_monthly]",
        product=product_id,
        unit_amount=MAYA_MONTHLY_MINOR,
        currency="usd",
        recurring={"interval": "month"},
        metadata={
            "seeded_by": "manthan_seed_stripe",
            "price_key": "caldera_pro_monthly",
            "plan_display": MAYA_PLAN_DISPLAY,
            "workflow": "M1R",
        },
    )
    log(f"  [new]   price {pr.id} (${pr.unit_amount/100:.2f}/{pr.recurring.interval})")
    return pr


def stripe_ensure_subscription(
    cust: stripe.Customer, price_id: str
) -> stripe.Subscription:
    log("\n[STRIPE]  ensuring Caldera Pro subscription…")
    for s in stripe.Subscription.list(
        customer=cust.id, limit=10, status="all"
    ).auto_paging_iter():
        md = md_dict(s)
        if md.get("slug") == MAYA_SLUG and md.get("sub_role") == "primary":
            log(f"  [reuse] subscription {s.id} (status={s.status})")
            return s
    sub = safe_create(
        stripe.Subscription.create,
        idem_key=idem("sub", MAYA_SLUG, "primary-v1"),
        label=f"Subscription[{MAYA_SLUG}/primary]",
        customer=cust.id,
        items=[{"price": price_id}],
        default_payment_method=cust.invoice_settings.default_payment_method,
        metadata={
            "slug": MAYA_SLUG, "plan": MAYA_PLAN,
            "plan_display": MAYA_PLAN_DISPLAY,
            "plan_key": "caldera_pro_monthly",
            "seeded_by": "manthan_seed_stripe",
            "billing_source": "stripe_primary",
            "sub_role": "primary",
            "signup_year": "2024",
            "monthly_usd": str(MAYA_MONTHLY_USD),
            "workflow": "M1R",
        },
    )
    log(f"  [new]   subscription {sub.id} (status={sub.status})")
    return sub


def stripe_find_existing_m1r_charges(
    cust: stripe.Customer,
) -> tuple[stripe.Charge | None, stripe.Charge | None]:
    """Look for the M1R charge pair on this customer (idempotency).

    Returns (charge_A, charge_B) - either or both may be None.
    """
    charge_a = None
    charge_b = None
    for ch in stripe.Charge.list(
        customer=cust.id, limit=100,
    ).auto_paging_iter():
        md = md_dict(ch)
        if md.get("workflow") != "M1R" or md.get("slug") != MAYA_SLUG:
            continue
        if md.get("charge_role") == "original":
            charge_a = ch
        elif md.get("charge_role") == "duplicate":
            charge_b = ch
    return charge_a, charge_b


def stripe_create_charge(
    cust: stripe.Customer,
    role: str,           # "original" | "duplicate"
    narrative_ts: str,
    idem_suffix: str,
) -> stripe.Charge:
    """Create a $89 successful charge tagged with M1R metadata.

    Both charges share the webhook_retry_chain id so the agent can
    discover the duplicate by joining on metadata.
    """
    log(f"\n[STRIPE]  creating $89 charge ({role}) at {narrative_ts}…")
    description = (
        f"{MAYA_NAME} - Caldera Pro monthly subscription ($89). "
        f"Charge role: {role}. Narrative timestamp: {narrative_ts}."
    )
    if role == "duplicate":
        description += (
            " Created when our stripe-webhook-handler retry-fired the "
            "same charge.succeeded event (event id "
            f"{STRIPE_WEBHOOK_RETRY_CHAIN_ID}) after the first delivery "
            "500'd. This is OUR bug - Maya should be refunded."
        )
    pi = safe_create(
        stripe.PaymentIntent.create,
        idem_key=idem("pi", MAYA_SLUG, idem_suffix),
        label=f"PI[{MAYA_SLUG}/{idem_suffix}]",
        amount=MAYA_MONTHLY_MINOR,
        currency="usd",
        payment_method="pm_card_visa",
        confirm=True,
        customer=cust.id,
        off_session=True,
        description=description,
        metadata={
            "slug": MAYA_SLUG,
            "workflow": "M1R",
            "workflow_label": "small_refund_auto",
            "charge_role": role,  # "original" | "duplicate"
            "simulated_created_at": narrative_ts,
            "plan_display": MAYA_PLAN_DISPLAY,
            "monthly_usd": str(MAYA_MONTHLY_USD),
            "webhook_retry_chain": STRIPE_WEBHOOK_RETRY_CHAIN_ID,
            "webhook_retry_gap_sec": str(WEBHOOK_RETRY_GAP_SEC),
            "expected_decision": "refund" if role == "duplicate" else "keep",
            "expected_policy": SMALL_REFUND_POLICY_ID,
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
    # Stamp the charge's own metadata too, so a direct charge-search
    # surfaces the workflow tag without going through the PI.
    try:
        stripe.Charge.modify(
            ch.id,
            description=description,
            metadata={
                "slug": MAYA_SLUG,
                "workflow": "M1R",
                "charge_role": role,
                "simulated_created_at": narrative_ts,
                "plan_display": MAYA_PLAN_DISPLAY,
                "monthly_usd": str(MAYA_MONTHLY_USD),
                "webhook_retry_chain": STRIPE_WEBHOOK_RETRY_CHAIN_ID,
                "webhook_retry_gap_sec": str(WEBHOOK_RETRY_GAP_SEC),
                "stripe_customer_id": cust.id,
                "expected_decision": "refund" if role == "duplicate" else "keep",
                "expected_policy": SMALL_REFUND_POLICY_ID,
                "seeded_by": "manthan_seed_stripe",
            },
        )
    except stripe.error.StripeError as e:
        log(f"  [charge-modify-skip] {ch.id}: {str(e)[:120]}")
    log(f"  charge {role}: {ch.id}  amount=${ch.amount/100:,.2f}  status={ch.status}")
    return ch


def stripe_create_duplicate_charges(
    cust: stripe.Customer,
) -> tuple[stripe.Charge, stripe.Charge]:
    """Create (or reuse) the two M1R charges 4 minutes apart."""
    existing_a, existing_b = stripe_find_existing_m1r_charges(cust)
    if existing_a and existing_b:
        log(f"  [reuse] charge A {existing_a.id}, charge B {existing_b.id}")
        return existing_a, existing_b

    ch_a = existing_a or stripe_create_charge(
        cust, "original", CHARGE_A_TIMESTAMP, "m1r-chA-v1"
    )
    ch_b = existing_b or stripe_create_charge(
        cust, "duplicate", CHARGE_B_TIMESTAMP, "m1r-chB-v1"
    )
    return ch_a, ch_b


# ──────────────────────────────────────────────────────────────────────
# 2. Salesforce - Maya Patel Design account + contact
# ──────────────────────────────────────────────────────────────────────


def salesforce_seed(
    c: Company, stripe_customer_id: str
) -> tuple[str | None, str | None]:
    if not SALESFORCE_AVAILABLE:
        log("\n[SALESFORCE]  SKIP - SALESFORCE_ACCESS_TOKEN not configured.")
        return None, None
    log("\n[SALESFORCE]  ensuring Maya Patel Design account + contact…")
    try:
        with httpx.Client(headers=SF_HEADERS, timeout=SF_TIMEOUT) as client:
            account_id, action = sf_upsert_account(client, c)
            if not account_id:
                log(f"  [{action}] account create failed")
                return None, None
            log(f"  [{action}] account → {account_id}")
            contact_id, contact_action = sf_upsert_contact(
                client,
                account_id=account_id,
                email=MAYA_EMAIL,
                first_name=MAYA_FIRST_NAME,
                last_name=MAYA_LAST_NAME,
                title="Owner / Designer",
            )
            log(f"  [{contact_action}] Maya contact → {contact_id}")
            return account_id, contact_id
    except Exception as e:
        log(f"  [skip] Salesforce error: {type(e).__name__}: {str(e)[:200]}")
        return None, None


# ──────────────────────────────────────────────────────────────────────
# 3. HubSpot - company + contact with NPS=9 + engagement-history note
# ──────────────────────────────────────────────────────────────────────


# Maya's solo practice doesn't have a real company domain - we treat
# her Gmail-style identity as the company anchor. We still set a domain
# field so HubSpot's company-search-by-domain works (the V1R pattern).
MAYA_HS_DOMAIN = "mayapateldesign.test"


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
    existing = hubspot_find_company_by_domain(client, MAYA_HS_DOMAIN)
    description = (
        f"Solo designer. Subscribed to {MAYA_PLAN_DISPLAY} at "
        f"${MAYA_MONTHLY_USD}/mo. 18-month customer (signed up 2024). "
        f"NPS=9, no prior disputes, no escalations. Direct contact is "
        f"Maya Patel <{MAYA_EMAIL}>. Workflow: M1R. "
        f"Stripe customer: {stripe_customer_id}."
    )
    props = {
        "name": c.name,
        "domain": MAYA_HS_DOMAIN,
        "country": c.country,
        "annualrevenue": str(c.arr_usd),
        "description": description,
        "lifecyclestage": "customer",
    }
    if existing:
        r = hubspot_request(
            client, "PATCH",
            f"/crm/v3/objects/companies/{existing}",
            json={"properties": props},
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
    log(f"  company create fail: {r.status_code} {r.text[:200]}")
    return None


def hubspot_find_contact_by_email(
    client: httpx.Client, email: str
) -> str | None:
    r = hubspot_request(
        client, "POST", "/crm/v3/objects/contacts/search",
        json={
            "filterGroups": [{"filters": [{
                "propertyName": "email", "operator": "EQ", "value": email,
            }]}],
            "properties": ["email", "firstname", "lastname"],
            "limit": 1,
        },
    )
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def hubspot_upsert_contact(
    client: httpx.Client, company_id: str
) -> str | None:
    existing = hubspot_find_contact_by_email(client, MAYA_EMAIL)
    props = {
        "email": MAYA_EMAIL,
        "firstname": MAYA_FIRST_NAME,
        "lastname": MAYA_LAST_NAME,
        "company": MAYA_NAME,
        "jobtitle": "Owner / Designer",
        "lifecyclestage": "customer",
        "hs_lead_status": "CONNECTED",
    }
    if existing:
        r = hubspot_request(
            client, "PATCH",
            f"/crm/v3/objects/contacts/{existing}",
            json={"properties": props},
        )
        if r.status_code in (200, 201):
            # Re-bind association so the company link is intact.
            if company_id:
                hubspot_request(
                    client, "PUT",
                    f"/crm/v4/objects/contact/{existing}/associations/"
                    f"default/company/{company_id}",
                )
            return existing
        log(f"  contact update fail: {r.status_code} {r.text[:200]}")
        return existing
    body = {
        "properties": props,
        "associations": [{
            "to": {"id": company_id},
            "types": [{
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 279,  # contact -> company primary
            }],
        }],
    }
    r = hubspot_request(client, "POST", "/crm/v3/objects/contacts", json=body)
    if r.status_code in (200, 201):
        return r.json().get("id")
    log(f"  contact create fail: {r.status_code} {r.text[:200]}")
    return None


HUBSPOT_NOTE_SIGNATURE = "[manthan_patch_m1_maya_duplicate]"
HUBSPOT_NOTE_BODY = (
    f"{HUBSPOT_NOTE_SIGNATURE} Maya Patel - long-tenure solo customer "
    f"on {MAYA_PLAN_DISPLAY} (${MAYA_MONTHLY_USD}/mo since signup in "
    f"2024). NPS=9 (most recent survey 2026-04). Zero disputes, zero "
    f"escalations, zero support tickets in 90 days. Listed as 'green' "
    f"health. CSM=null (too small for assigned coverage). Direct support "
    f"contact through Gmail thread only. This contact is the M1R "
    f"good-standing anchor - when the small-refund-auto policy needs to "
    f"verify 'customer in good standing,' this is the record to read."
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


def hubspot_seed(
    c: Company, stripe_customer_id: str
) -> tuple[str | None, str | None, str | None]:
    log("\n[HUBSPOT]  ensuring Maya Patel Design company + contact + note…")
    with httpx.Client(headers=HUBSPOT_HEADERS, timeout=HUBSPOT_TIMEOUT) as client:
        cid = hubspot_upsert_company(client, c, stripe_customer_id)
        log(f"  company id: {cid}")
        time.sleep(HUBSPOT_REQ_SLEEP)
        if not cid:
            return None, None, None
        contact_id = hubspot_upsert_contact(client, cid)
        log(f"  contact id: {contact_id}")
        time.sleep(HUBSPOT_REQ_SLEEP)
        nid = hubspot_attach_note(client, cid)
        log(f"  note id   : {nid}")
        time.sleep(HUBSPOT_REQ_SLEEP)
    return cid, contact_id, nid


# ──────────────────────────────────────────────────────────────────────
# 4. Intercom - bare contact only (NO conversations - first-time issue)
# ──────────────────────────────────────────────────────────────────────


def intercom_ensure_contact(client: httpx.Client) -> str | None:
    """Create/find Maya's Intercom contact WITHOUT any conversations.

    Maya has never raised an issue before - this is the "good standing"
    signal the agent must verify. We seed a bare contact so the agent's
    Intercom lookup returns Maya but with zero conversation history.
    """
    ext_id = f"{intercom_external_id(MAYA_SLUG)}_primary"
    existing = intercom_find_contact_by_external_id(client, ext_id)
    if existing:
        log(f"  [reuse] contact {existing}")
        return existing
    by_email = intercom_find_contact_by_email(client, MAYA_EMAIL)
    if by_email:
        update = {
            "external_id": ext_id,
            "name": "Maya Patel",
            "signed_up_at": int(datetime(2024, 11, 22, 9, 0, 0,
                                         tzinfo=timezone.utc).timestamp()),
            "last_seen_at": int(time.time()) - 86400 * 1,
        }
        intercom_request(client, "PUT", f"/contacts/{by_email}", json=update)
        return by_email
    payload = {
        "role": "user",
        "email": MAYA_EMAIL,
        "name": "Maya Patel",
        "external_id": ext_id,
        "signed_up_at": int(datetime(2024, 11, 22, 9, 0, 0,
                                     tzinfo=timezone.utc).timestamp()),
        "last_seen_at": int(time.time()) - 86400 * 1,
    }
    r = intercom_request(client, "POST", "/contacts", json=payload)
    if r.status_code in (200, 201):
        return r.json().get("id")
    if r.status_code == 409:
        return intercom_find_contact_by_email(client, MAYA_EMAIL)
    log(f"  contact create fail: {r.status_code} {r.text[:200]}")
    return None


def intercom_seed() -> str | None:
    log("\n[INTERCOM]  ensuring Maya contact (NO conversations)…")
    with httpx.Client(headers=INTERCOM_HEADERS, timeout=INTERCOM_TIMEOUT) as client:
        contact_id = intercom_ensure_contact(client)
        if not contact_id:
            log("  ERROR: could not establish Intercom contact for Maya")
            return None
        log(f"  contact id: {contact_id} (no conversations - clean record)")
        time.sleep(INTERCOM_REQ_SLEEP)
    return contact_id


# ──────────────────────────────────────────────────────────────────────
# 5. Zendesk - org + user + 1 older unrelated ticket (zero in 90d)
# ──────────────────────────────────────────────────────────────────────


M1R_ZENDESK_TICKETS = [
    {
        "subject": "How do I change my default export format?",
        "body": (
            "Hi support - when I export my designs they default to PNG. "
            "Is there a way to change the default to JPG or SVG without "
            "having to pick it each time? Thanks!"
        ),
        "priority": "low",
        "status": "solved",
        # Anchor on 2026-05-27 (the same anchor Q1R/V1R use)
        "days_ago_from_anchor": (datetime(2026, 5, 27, tzinfo=timezone.utc)
                                 - datetime(2025, 9, 18, tzinfo=timezone.utc)
                                 ).days,
        "type": "question",
    },
]


def zendesk_seed(c: Company) -> dict[str, Any]:
    log("\n[ZENDESK]  ensuring organization + user + 1 older ticket…")
    state = zendesk_load_state()
    state.setdefault("organizations", {})
    state.setdefault("users", {})
    state.setdefault("m1r_maya_tickets", [])

    with httpx.Client(
        headers={"Content-Type": "application/json"},
        auth=ZENDESK_AUTH, timeout=ZENDESK_TIMEOUT,
    ) as client:
        # Org
        org_id = state["organizations"].get(MAYA_SLUG)
        if not org_id:
            org_id, action = zendesk_upsert_organization(client, c)
            if org_id:
                state["organizations"][MAYA_SLUG] = org_id
                zendesk_save_state(state)
                log(f"  org [{action}] id={org_id}")
            else:
                log(f"  ! could not upsert Zendesk org for {MAYA_SLUG}")
                return {"org_id": None, "ticket_ids": []}
        else:
            log(f"  org [reuse] id={org_id}")
        # User
        user_ext = f"ext_{MAYA_SLUG}_0"
        user_id = state["users"].get(user_ext)
        if not user_id:
            user_id, action = zendesk_upsert_user(
                client,
                email=MAYA_EMAIL,
                name="Maya Patel",
                role="end-user",
                organization_id=org_id,
                external_id=user_ext,
            )
            if user_id:
                state["users"][user_ext] = user_id
                zendesk_save_state(state)
                log(f"  user [{action}] id={user_id}")
            else:
                log(f"  ! could not upsert Zendesk user for {MAYA_SLUG}")
                return {"org_id": org_id, "ticket_ids": []}
        else:
            log(f"  user [reuse] id={user_id}")

        # Tickets - idempotency via state['m1r_maya_tickets']
        existing_tids = state.get("m1r_maya_tickets", [])
        if existing_tids:
            still_exist = []
            for tid in existing_tids:
                r = zendesk_request(client, "GET", f"/tickets/{tid}.json")
                if r.status_code == 200:
                    still_exist.append(tid)
            if len(still_exist) >= len(M1R_ZENDESK_TICKETS):
                log(f"  [reuse] {len(still_exist)} existing M1R tickets")
                return {"org_id": org_id, "ticket_ids": still_exist}

        now = datetime(2026, 5, 27, tzinfo=timezone.utc)
        new_tids: list[int] = []
        for spec in M1R_ZENDESK_TICKETS:
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
                "requester_email": MAYA_EMAIL,
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
        state["m1r_maya_tickets"] = new_tids
        zendesk_save_state(state)
        return {"org_id": org_id, "ticket_ids": new_tids}


# ──────────────────────────────────────────────────────────────────────
# 6. Slack - NO post for Maya (small-customer, no internal escalation)
# ──────────────────────────────────────────────────────────────────────


def slack_seed() -> tuple[None, None]:
    log("\n[SLACK]    SKIP - Maya is too small for CS escalation channels.")
    log("           (Intentional absence: 'no internal mention' is a")
    log("           good-standing signal for the small-refund-auto policy.)")
    return None, None


# ──────────────────────────────────────────────────────────────────────
# 7. Notion - Small-refund policy for duplicate charges under $200
# ──────────────────────────────────────────────────────────────────────


M1R_NOTION_PAGES = [
    NotionPage(
        title=SMALL_REFUND_POLICY_TITLE,
        category="Policy & SOP",
        signal_id="M1R",
        headings=[(2, SMALL_REFUND_POLICY_TITLE)],
        paragraphs=[
            "Owner: RevOps (priya@miny-labs.com) + Billing Engineering. "
            f"Status: CURRENT - authoritative. Policy id "
            f"{SMALL_REFUND_POLICY_ID}. Doc version 1.0 (2026-05). Last "
            "reviewed 2026-05-20. Approved by VP Finance, VP Customer "
            "Success, and Head of Trust & Safety.",

            "Scope: this policy governs how we respond to small "
            "duplicate-charge complaints from customers (typically "
            "delivered via email to support, NOT via a Stripe chargeback) "
            "where the duplicate amount falls below $200 USD AND the "
            "customer is in good standing AND the duplicate occurred "
            "within the past 60 days. Within that envelope, the agent "
            "is authorised to REFUND + AUTO-REPLY without escalating "
            "to a human reviewer. This is the authoritative "
            f"'{SMALL_REFUND_POLICY_ID}' SOP.",

            "",
            "Section 1 - Eligibility checks (all must pass).",

            "(a) Duplicate confirmed in Stripe.",
            "  - Find two successful charges of identical amount on the "
            "    same Stripe customer within a 30-minute window. ",
            "  - At least one of the two charges shares a "
            "    metadata.webhook_retry_chain value with the other, OR "
            "    the two charges share an identical Stripe event id in "
            "    our Datadog/Sentry webhook-router logs.",
            "  - Duplicate amount is strictly less than $200 USD (i.e. "
            "    minor units < 20000).",

            "(b) The duplicate is OUR fault (vendor failure).",
            "  - Sentry: search the stripe-webhook-handler project for "
            "    a RetryError or any 5xx-related error at or within ~5 "
            "    minutes of the duplicate charge's timestamp. A "
            "    matching event = OUR bug.",
            "  - Datadog: confirm the webhook-router service logged the "
            "    same charge.succeeded event id TWICE in the window. "
            "    Same event id processed twice = OUR bug.",
            "  - PagerDuty: confirm a P3-or-lower incident on the "
            "    webhook-router service in the same window. The "
            "    incident may already be resolved (auto-resolved "
            "    incidents are STILL evidence of the bug).",
            "  - If two of three operational sources corroborate the "
            "    retry/duplicate, treat as vendor failure and proceed.",

            "(c) Customer is in good standing.",
            "  - Stripe: zero disputes in the trailing 12 months.",
            "  - HubSpot or Salesforce: lifecyclestage=customer AND "
            "    no 'red' health flag.",
            "  - Intercom + Zendesk: no open tickets and no escalation "
            "    history in the trailing 90 days. A clean record = "
            "    good standing; one routine resolved ticket >90 days "
            "    old is also fine.",
            "  - HubSpot NPS (if available): NPS >= 7 OR no NPS on file.",

            "(d) Timing.",
            "  - The duplicate charge occurred within the past 60 days "
            "    of the customer's complaint (use the complaint's email "
            "    receive timestamp as the anchor).",

            "",
            "Section 2 - Autonomous action (when all eligibility checks pass).",
            "When ALL eligibility checks in Section 1 pass, the agent is "
            "authorised to act WITHOUT human review:",

            "  1. Refund the DUPLICATE charge (the second of the two, "
            "     identified by metadata.charge_role=duplicate or by "
            "     timestamp). Refund full amount via stripe.refunds.",
            "  2. Reply to the customer in the same Gmail thread "
            "     confirming the refund. Include: confirmation that the "
            "     duplicate was caused by an internal webhook retry "
            "     issue (be candid - Maya-grade transparency), the "
            "     specific refunded amount and charge id, the expected "
            "     timing for the refund to appear on her statement "
            "     (5-10 business days), and a brief apology. Do NOT "
            "     include policy ids, internal Sentry/Datadog ids, or "
            "     other internal language in the customer-facing reply.",
            "  3. Document the root cause in the case record (Sentry "
            "     event id, Datadog event id, PagerDuty incident id if "
            "     present, plus the Stripe charge.id of both A and B). "
            "     This documentation is REQUIRED - if the agent can't "
            "     identify the root cause from operational sources, the "
            "     case must escalate to a human instead of auto-firing.",

            "",
            "Section 3 - Escalation triggers (do NOT auto-act).",
            "Escalate to a human reviewer when ANY of the following are "
            "true (these are mutually exclusive - any single condition "
            "escalates the case):",
            "  - Duplicate amount >= $200 USD.",
            "  - Customer has any open dispute in Stripe in the trailing "
            "    12 months, OR has filed a chargeback against this "
            "    company in the past.",
            "  - Customer has an open Zendesk ticket OR Intercom "
            "    conversation that is not yet resolved.",
            "  - Customer's HubSpot health is 'red' or NPS < 5.",
            "  - The agent CANNOT corroborate the duplicate as OUR bug "
            "    via at least two of {Sentry, Datadog, PagerDuty}. "
            "    Unverified root cause is a hard escalation trigger - "
            "    we do NOT auto-refund duplicates that might be the "
            "    customer's pricing-page double-click error.",
            "  - The complaint mentions a Stripe chargeback or dispute "
            "    by name (those go through the chargeback pipeline "
            "    instead).",
            "  - Multiple duplicate-charge complaints from the same "
            "    customer in any 90-day window - escalate so we can "
            "    investigate whether the underlying webhook bug is "
            "    recurring per-customer.",

            "",
            "Section 4 - Customer reply template (informational).",
            "Reply MUST be in the same Gmail thread the customer used. "
            "Tone: friendly, candid, brief. Keep under 120 words. Do "
            "NOT use boilerplate corporate apology language. Avoid "
            "phrases like 'we apologize for any inconvenience' - say "
            "exactly what happened in plain words. Examples of good "
            "openings: 'Hi Maya - you're right about the duplicate. "
            "Here's what happened:' or 'Hey Maya - confirming the "
            "duplicate charge on May 22 and refunding it now.'",

            "",
            "Section 5 - Audit trail.",
            "Every autonomous action under this policy is logged to the "
            "case ledger with: (i) the policy id "
            f"({SMALL_REFUND_POLICY_ID}), (ii) the Stripe refund.id, "
            "(iii) the supporting Sentry/Datadog/PagerDuty ids, and "
            "(iv) the Gmail message id of the customer reply. RevOps "
            "reviews the ledger weekly. If a refund issued under this "
            "policy is later contested by the customer (rare), the "
            "ledger entry is the case-of-record for the post-incident "
            "review.",

            f"Reference: policy id {SMALL_REFUND_POLICY_ID}. "
            "Internal URL https://miny-labs.notion.site/sop-small-refund-auto. "
            "Next review: 2026-11-15.",
        ],
    ),
]


def notion_seed() -> list[tuple[str, str]]:
    log("\n[NOTION]   ensuring small-refund-auto policy page…")
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
        for page in M1R_NOTION_PAGES:
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
# 8. PostHog - Maya's normal usage events (6 logins, design actions)
# ──────────────────────────────────────────────────────────────────────


# Maya is solo - single persona only.
MAYA_POSTHOG_PERSONA = {
    "distinct_id": "maya-patel-design-user-1",
    "role": "owner-designer",
    "email": MAYA_EMAIL,
    "name": "Maya Patel",
}


# Last-7-days window relative to a fixed narrative anchor. We anchor on
# 2026-05-27 (the same anchor Q1R/V1R use) so re-runs are deterministic.
LAST_WEEK_ANCHOR = datetime(2026, 5, 27, 18, 0, 0, tzinfo=timezone.utc)
LAST_WEEK_START = LAST_WEEK_ANCHOR - timedelta(days=7)


def _last_week_random_ts(rng: random.Random) -> datetime:
    span_s = int((LAST_WEEK_ANCHOR - LAST_WEEK_START).total_seconds())
    offset = rng.randint(0, span_s)
    return LAST_WEEK_START + timedelta(seconds=offset)


def build_posthog_events(stripe_customer_id: str) -> list[dict]:
    """Build Maya's normal usage events for the last 7 days.

    Target: 6 logins + ~14 create_design / export_design actions.
    """
    events: list[dict] = []
    rng = random.Random(20260520)

    base_props = {
        "company_slug": MAYA_SLUG,
        "company": MAYA_NAME,
        "company_domain": MAYA_HS_DOMAIN,
        "plan": MAYA_PLAN,
        "plan_display": MAYA_PLAN_DISPLAY,
        "arr_usd": MAYA_ARR_USD,
        "industry": MAYA_INDUSTRY,
        "country": MAYA_COUNTRY,
        "region": MAYA_REGION,
        "stripe_customer_id": stripe_customer_id,
        "seeded_by": "patch_m1_maya_duplicate",
        "workflow": "M1R",
        "$lib": "manthan-m1r-patch",
    }

    # 1) $identify for Maya - establishes Person row.
    events.append({
        "event": "$identify",
        "distinct_id": MAYA_POSTHOG_PERSONA["distinct_id"],
        "properties": {
            **base_props,
            "$set": {
                "email": MAYA_POSTHOG_PERSONA["email"],
                "name": MAYA_POSTHOG_PERSONA["name"],
                "company": MAYA_NAME,
                "company_slug": MAYA_SLUG,
                "company_domain": MAYA_HS_DOMAIN,
                "plan": MAYA_PLAN,
                "plan_display": MAYA_PLAN_DISPLAY,
                "role": MAYA_POSTHOG_PERSONA["role"],
                "team": "solo",
                "arr_usd": MAYA_ARR_USD,
                "stripe_customer_id": stripe_customer_id,
                "nps_latest": MAYA_NPS,
                "tenure_months": MAYA_TENURE_MONTHS,
                "seeded_by": "patch_m1_maya_duplicate",
                "workflow": "M1R",
                "good_standing": True,
            },
            "$set_once": {
                "first_seen": "2024-11-22T09:00:00Z",
                "signup_year": 2024,
            },
        },
        "timestamp": (LAST_WEEK_START - timedelta(days=1)).isoformat(),
    })

    # 2) 6 logins across the last 7 days.
    for _ in range(6):
        ts = _last_week_random_ts(rng)
        events.append({
            "event": "user_logged_in",
            "distinct_id": MAYA_POSTHOG_PERSONA["distinct_id"],
            "properties": {
                **base_props,
                "role": MAYA_POSTHOG_PERSONA["role"],
                "email": MAYA_POSTHOG_PERSONA["email"],
                "login_method": rng.choice(["password", "google_oauth",
                                            "google_oauth"]),
                "user_agent": "Manthan-M1R-Seed/1.0",
            },
            "timestamp": ts.isoformat(),
        })

    # 3) ~14 design actions across the last 7 days.
    CRITICAL_ACTIONS = [
        ("create_design", "designs"),
        ("create_design", "designs"),
        ("export_design", "exports"),
        ("export_design", "exports"),
        ("update_design", "designs"),
        ("share_design", "delivery"),
        ("comment_on_design", "collaboration"),
    ]
    for i in range(14):
        action, area = CRITICAL_ACTIONS[i % len(CRITICAL_ACTIONS)]
        ts = _last_week_random_ts(rng)
        props = {
            **base_props,
            "role": MAYA_POSTHOG_PERSONA["role"],
            "email": MAYA_POSTHOG_PERSONA["email"],
            "action": action,
            "area": area,
            "is_critical_path": True,
        }
        if action == "create_design":
            props["design_id"] = f"des_m1r_{i:04d}"
        elif action == "export_design":
            props["design_id"] = f"des_m1r_{i:04d}"
            props["export_format"] = rng.choice(["png", "jpg", "svg", "pdf"])
            props["export_dpi"] = rng.choice([72, 144, 300])
        elif action == "share_design":
            props["share_url"] = f"https://maya-patel-design.test/share/{i:04d}"
        events.append({
            "event": action,
            "distinct_id": MAYA_POSTHOG_PERSONA["distinct_id"],
            "properties": props,
            "timestamp": ts.isoformat(),
        })

    return events


def posthog_seed(stripe_customer_id: str) -> dict[str, Any]:
    log("\n[POSTHOG]  ingesting Maya's last-7-days usage events…")
    out = {"events_sent": 0, "events_error": 0, "personas": 1}
    state = _load_state()
    if state.get("posthog_m1r_seeded_for_customer") == stripe_customer_id:
        log("  [reuse] PostHog M1R events already ingested for this customer "
            "(state file). Skipping to avoid event duplication.")
        out["events_sent"] = state.get("posthog_m1r_events_sent", 0)
        return out
    with httpx.Client(headers=POSTHOG_HEADERS, timeout=POSTHOG_TIMEOUT) as client:
        project_key = fetch_project_api_key(client)
        if not project_key:
            log("  ! PostHog project key unavailable - skipping ingestion.")
            return out
        events = build_posthog_events(stripe_customer_id)
        log(f"  events={len(events)} (1 persona)")
        sent, errs = posthog_ingest_events(client, events, project_key)
        out["events_sent"] = sent
        out["events_error"] = errs
        log(f"  ingested {sent}  errors {errs}")
    state["posthog_m1r_seeded_for_customer"] = stripe_customer_id
    state["posthog_m1r_events_sent"] = sent
    _save_state(state)
    return out


# ──────────────────────────────────────────────────────────────────────
# 9. Sentry - stripe-webhook-handler RetryError at 14:25:09 UTC + baseline
# ──────────────────────────────────────────────────────────────────────


M1R_SENTRY_PROJECT_SLUG = "stripe-webhook-handler"
M1R_SENTRY_TEAM_SLUG = "platform"
M1R_SENTRY_RETRY_TITLE = (
    "RetryError: webhook delivery 500 - Stripe retried after 4min timeout"
)
M1R_SENTRY_BASELINE_TITLE = (
    "ValueError: optional metadata.idempotency_key missing on inbound "
    "webhook payload - backfilled with event_id"
)


def sentry_seed(stripe_customer_id: str) -> dict[str, Any]:
    """Ingest the M1R root-cause RetryError + baseline noise events.

    The RetryError is the load-bearing beat - it MUST exist so the agent
    can corroborate the duplicate-charge root cause via Sentry. Title +
    fingerprint pin the issue group so re-runs collapse cleanly.
    """
    log("\n[SENTRY]   ingesting stripe-webhook-handler RetryError + baseline…")
    out = {
        "retry_event_seeded": False,
        "baseline_events_seeded": 0,
        "project_slug": M1R_SENTRY_PROJECT_SLUG,
    }
    state = _load_state()
    if state.get("sentry_m1r_seeded_for_customer") == stripe_customer_id:
        log("  [reuse] Sentry M1R events already ingested for this customer "
            "(state file). Skipping to avoid event duplication.")
        out["retry_event_seeded"] = True
        out["baseline_events_seeded"] = state.get(
            "sentry_m1r_baseline_count", 0
        )
        return out
    with httpx.Client(headers=SENTRY_HEADERS, timeout=SENTRY_TIMEOUT) as client:
        try:
            sentry_ping_org(client)
        except SystemExit as e:
            log(f"  ! Sentry org ping failed: {e}")
            return out
        existing_teams = {t["slug"]: t for t in sentry_list_teams(client)}
        if M1R_SENTRY_TEAM_SLUG not in existing_teams:
            sentry_ensure_team(client, "Platform Eng", M1R_SENTRY_TEAM_SLUG)
        existing_projects = {p["slug"]: p for p in sentry_list_projects(client)}
        if M1R_SENTRY_PROJECT_SLUG not in existing_projects:
            sentry_ensure_project(
                client, M1R_SENTRY_TEAM_SLUG,
                "Stripe Webhook Handler", M1R_SENTRY_PROJECT_SLUG, "python",
            )
        dsn = sentry_get_project_dsn(client, M1R_SENTRY_PROJECT_SLUG)

    sentry_init_for_project(dsn)

    # ── The CRITICAL root-cause event ──
    # Sentry timestamps the event at ingest time; we pin the narrative
    # time in tags and context so the agent can locate it by date.
    retry_fingerprint = ["RetryError", M1R_SENTRY_RETRY_TITLE]
    with sentry_sdk.push_scope() as scope:
        scope.level = "error"  # type: ignore[assignment]
        scope.fingerprint = retry_fingerprint
        scope.set_tag("service", "stripe-webhook-handler")
        scope.set_tag("env", "production")
        scope.set_tag("tenant", MAYA_SLUG)
        scope.set_tag("customer_slug", MAYA_SLUG)
        scope.set_tag("customer_id", stripe_customer_id)
        scope.set_tag("customer_email", MAYA_EMAIL)
        scope.set_tag("region", MAYA_REGION)
        scope.set_tag("workflow", "M1R")
        scope.set_tag("narrative_date", CHARGE_DATE)
        scope.set_tag("narrative_timestamp", CHARGE_B_TIMESTAMP)
        scope.set_tag("stripe_event_id", STRIPE_WEBHOOK_RETRY_CHAIN_ID)
        scope.set_tag("error_type", "webhook_retry_500")
        scope.set_context(
            "retry_context",
            {
                "customer_id": stripe_customer_id,
                "company_slug": MAYA_SLUG,
                "region": MAYA_REGION,
                "narrative_event_time": CHARGE_B_TIMESTAMP,
                "stripe_event_id": STRIPE_WEBHOOK_RETRY_CHAIN_ID,
                "retry_attempt": 2,
                "first_attempt_at": CHARGE_A_TIMESTAMP,
                "retry_attempt_at": CHARGE_B_TIMESTAMP,
                "retry_gap_seconds": WEBHOOK_RETRY_GAP_SEC,
                "is_root_cause_of_duplicate": True,
                "note": (
                    "Stripe-webhook-handler returned 500 on the first "
                    "delivery of charge.succeeded event "
                    f"{STRIPE_WEBHOOK_RETRY_CHAIN_ID} for customer "
                    f"{stripe_customer_id} ({MAYA_NAME}) at "
                    f"{CHARGE_A_TIMESTAMP}. Stripe retried 4 min 6 sec "
                    f"later at {CHARGE_B_TIMESTAMP}; second delivery "
                    "succeeded but the upstream charge had already been "
                    "processed on the first delivery's path (in-flight "
                    "request was not idempotency-keyed). Net result: "
                    "TWO successful $89 charges on Maya's card. This is "
                    "the root cause of the duplicate-charge customer "
                    f"complaint that triggered workflow M1R."
                ),
            },
        )
        try:
            raise type("RetryError", (Exception,), {})(
                f"{M1R_SENTRY_RETRY_TITLE} (stripe_event_id "
                f"{STRIPE_WEBHOOK_RETRY_CHAIN_ID} customer "
                f"{stripe_customer_id} narrative_time {CHARGE_B_TIMESTAMP})"
            )
        except Exception:
            sentry_sdk.capture_exception()
    time.sleep(INGEST_SLEEP)
    out["retry_event_seeded"] = True

    # ── Baseline noise - 6 routine events scattered across May 2026 ──
    # Establishes that the RetryError is NOT a recurring pattern - it's
    # the single bug that produced Maya's duplicate.
    baseline_rng = random.Random(20260518)
    may_start = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
    may_end = datetime(2026, 5, 27, 18, 0, 0, tzinfo=timezone.utc)
    baseline_fingerprint = ["ValueError", M1R_SENTRY_BASELINE_TITLE]
    baseline_count = 6
    for _ in range(baseline_count):
        offset = baseline_rng.randint(
            0, int((may_end - may_start).total_seconds())
        )
        ts = may_start + timedelta(seconds=offset)
        narrative_date = ts.isoformat()[:10]
        with sentry_sdk.push_scope() as scope:
            scope.level = "warning"  # type: ignore[assignment]
            scope.fingerprint = baseline_fingerprint
            scope.set_tag("service", "stripe-webhook-handler")
            scope.set_tag("env", "production")
            scope.set_tag("workflow", "M1R")
            scope.set_tag("narrative_date", narrative_date)
            scope.set_tag("error_type", "baseline_noise")
            try:
                raise ValueError(
                    f"{M1R_SENTRY_BASELINE_TITLE} (narrative_time "
                    f"{ts.isoformat()})"
                )
            except ValueError:
                sentry_sdk.capture_exception()
        time.sleep(INGEST_SLEEP)
    out["baseline_events_seeded"] = baseline_count

    # ── Project-wide summary ──
    with sentry_sdk.push_scope() as scope:
        scope.level = "info"  # type: ignore[assignment]
        scope.set_tag("service", "stripe-webhook-handler")
        scope.set_tag("env", "production")
        scope.set_tag("workflow", "M1R")
        scope.set_tag("narrative_date", CHARGE_DATE)
        sentry_sdk.capture_message(
            f"M1R root-cause summary: stripe-webhook-handler RetryError "
            f"on stripe_event_id {STRIPE_WEBHOOK_RETRY_CHAIN_ID} caused "
            f"a duplicate $89 charge for customer {stripe_customer_id} "
            f"({MAYA_NAME}) on {CHARGE_DATE}. First delivery 500'd at "
            f"{CHARGE_A_TIMESTAMP}; Stripe retried at "
            f"{CHARGE_B_TIMESTAMP}. Datadog webhook-router log "
            f"corroborates (same event id POSTed twice). PagerDuty P3 "
            f"webhook-router 5xx spike auto-resolved. This is the "
            f"corroboration anchor for small-refund-auto / M1R.",
            level="info",
        )
    sentry_sdk.flush(timeout=15.0)
    log(f"  Sentry RetryError: 1, baseline noise: {baseline_count}, "
        f"summary: 1")
    state["sentry_m1r_seeded_for_customer"] = stripe_customer_id
    state["sentry_m1r_baseline_count"] = baseline_count
    state["sentry_m1r_retry_seeded"] = True
    _save_state(state)
    return out


# ──────────────────────────────────────────────────────────────────────
# 10. Datadog - webhook-router log event showing same stripe event id 2x
# ──────────────────────────────────────────────────────────────────────


def m1r_datadog_event(stripe_customer_id: str) -> DDEventSpec:
    return DDEventSpec(
        title=(
            f"webhook-router: duplicate POST of Stripe "
            f"{STRIPE_WEBHOOK_RETRY_CHAIN_ID} - "
            f"workflow:M1R root cause for {MAYA_NAME}"
        ),
        text=(
            f"webhook-router log rollup for the duplicate-charge incident "
            f"on {CHARGE_DATE} that produced workflow M1R (customer "
            f"{stripe_customer_id} / {MAYA_NAME} / {MAYA_EMAIL}).\n\n"
            "Narrative trace:\n"
            f"  - {CHARGE_A_TIMESTAMP}  POST /webhooks/stripe  "
            f"event_id={STRIPE_WEBHOOK_RETRY_CHAIN_ID}  "
            "handler=process_charge_succeeded  "
            "response_status=500  duration_ms=29412  "
            f"customer_id={stripe_customer_id}\n"
            f"  - {CHARGE_B_TIMESTAMP}  POST /webhooks/stripe  "
            f"event_id={STRIPE_WEBHOOK_RETRY_CHAIN_ID}  "
            "handler=process_charge_succeeded  "
            "response_status=200  duration_ms=812  "
            f"customer_id={stripe_customer_id}  "
            "stripe_retry_attempt=2\n\n"
            f"Diagnosis: stripe.com retried the same charge.succeeded "
            f"event id {STRIPE_WEBHOOK_RETRY_CHAIN_ID} after the first "
            f"delivery 500'd. The first attempt's handler had ALREADY "
            f"committed the downstream charge insert before throwing - "
            f"the handler is not idempotency-keyed on the Stripe event "
            f"id, so the retry's handler ran the full pipeline a "
            f"second time, producing a duplicate $89 charge on Maya's "
            f"card.\n\n"
            "Same Stripe event id, two charges, four minutes apart, "
            "matching POST timestamps with the Sentry RetryError event "
            f"at {CHARGE_B_TIMESTAMP}. This is the canonical "
            "Datadog-side root-cause anchor for the M1R small-refund-"
            "auto policy.\n\n"
            "Linked sources: "
            f"Sentry project stripe-webhook-handler RetryError @ "
            f"{CHARGE_B_TIMESTAMP}; PagerDuty webhook-router 5xx-spike "
            "P3 (already resolved); Stripe charges (original + "
            f"duplicate) both tagged metadata.webhook_retry_chain="
            f"{STRIPE_WEBHOOK_RETRY_CHAIN_ID}.\n\n"
            "Tag-search by workflow:M1R-maya-duplicate or "
            f"customer_id:{stripe_customer_id} or "
            f"stripe_event_id:{STRIPE_WEBHOOK_RETRY_CHAIN_ID} to locate."
        ),
        date_happened=dd_epoch(dd_hours_ago(4)),
        tags=[
            "service:webhook-router",
            "service:stripe-webhook-handler",
            "env:prod",
            "team:platform",
            f"region:{MAYA_REGION}",
            f"customer_id:{stripe_customer_id}",
            f"customer_email:{MAYA_EMAIL}",
            f"customer_slug:{MAYA_SLUG}",
            "workflow:M1R-maya-duplicate",
            f"stripe_event_id:{STRIPE_WEBHOOK_RETRY_CHAIN_ID}",
            f"narrative_window:{CHARGE_A_TIMESTAMP}_{CHARGE_B_TIMESTAMP}",
            "narrative_duplicate_count:2",
            "summary:webhook-router-retry-duplicate",
            "root_cause:webhook_retry_chain",
        ],
        alert_type="error",
    )


def datadog_seed(stripe_customer_id: str) -> int | None:
    log("\n[DATADOG]  ensuring webhook-router duplicate-POST event…")
    state = _load_state()
    if state.get("datadog_m1r_event_id"):
        log(f"  [reuse] Datadog event "
            f"{state['datadog_m1r_event_id']} (from state file)")
        return state["datadog_m1r_event_id"]
    evt_spec = m1r_datadog_event(stripe_customer_id)
    event_id = None
    with httpx.Client(headers=DD_HEADERS, timeout=DD_TIMEOUT) as client:
        eid, eaction = dd_post_event(client, evt_spec)
        event_id = eid
        log(f"  event   [{eaction}] id={eid}")
    if event_id:
        state["datadog_m1r_event_id"] = event_id
        _save_state(state)
    return event_id


# ──────────────────────────────────────────────────────────────────────
# 11. PagerDuty - P3 webhook-router 5xx spike, status=resolved
# ──────────────────────────────────────────────────────────────────────


M1R_PD_SERVICE = "webhook-router"
M1R_PD_SERVICE_DESC = (
    "Stripe webhook ingress router - receives all incoming Stripe events "
    "and dispatches them to the per-event handler (charge.succeeded, "
    "invoice.payment_succeeded, etc). Owns the response 2xx/5xx Stripe "
    "uses to decide whether to retry."
)
M1R_PD_TITLE = (
    "webhook-router 5xx spike - Stripe event "
    f"{STRIPE_WEBHOOK_RETRY_CHAIN_ID} triggered handler retry "
    f"(workflow:M1R Maya duplicate-charge root cause)"
)


def m1r_pd_body(stripe_customer_id: str) -> str:
    return (
        f"Auto-created P3 incident from Datadog monitor "
        f"'webhook-router 5xx spike' at "
        f"{CHARGE_B_TIMESTAMP[:16].replace('T', ' ')} UTC. Resolved "
        f"automatically at 2026-05-22 14:32 UTC after the next minute "
        f"of traffic showed clean 200s.\n\n"
        f"Service: {M1R_PD_SERVICE}\n"
        f"Severity: P3 (low)\n"
        f"Status: resolved (auto, 2026-05-22T14:32:00Z)\n\n"
        f"Trigger: stripe-webhook-handler returned 500 on the first "
        f"delivery of Stripe charge.succeeded event id "
        f"{STRIPE_WEBHOOK_RETRY_CHAIN_ID} at {CHARGE_A_TIMESTAMP}. "
        f"Stripe retried the same event 4 min 6 sec later at "
        f"{CHARGE_B_TIMESTAMP}; second delivery returned 200 and the "
        f"5xx spike cleared. Datadog log search confirms the same "
        f"stripe_event_id was POSTed twice from webhook-router during "
        f"the window.\n\n"
        f"Customer impact: customer {stripe_customer_id} "
        f"({MAYA_NAME}, {MAYA_EMAIL}) was charged $89 TWICE on "
        f"{CHARGE_DATE} - once at {CHARGE_A_TIMESTAMP} (the first "
        f"delivery's path) and once at {CHARGE_B_TIMESTAMP} (the retry "
        f"path). Net: one duplicate $89 charge that should be refunded "
        f"per the small-refund-auto SOP.\n\n"
        f"Linked Sentry event: RetryError in project "
        f"stripe-webhook-handler at {CHARGE_B_TIMESTAMP} (fingerprint "
        f"['RetryError', 'webhook delivery 500 - Stripe retried after "
        f"4min timeout']).\n\n"
        f"Linked Datadog event: 'webhook-router: duplicate POST of "
        f"Stripe {STRIPE_WEBHOOK_RETRY_CHAIN_ID}'.\n\n"
        f"Tags: workflow:M1R-maya-duplicate, "
        f"customer_id:{stripe_customer_id}, "
        f"stripe_event_id:{STRIPE_WEBHOOK_RETRY_CHAIN_ID}."
    )


def pagerduty_seed(stripe_customer_id: str) -> str | None:
    log("\n[PAGERDUTY] ensuring webhook-router service + P3 5xx-spike incident…")
    with httpx.Client(headers=PD_HEADERS, timeout=PD_TIMEOUT) as client:
        # 1. Find or initialise an escalation policy.
        ep_id = None
        sid, ep_existing = pd_find_service_by_name(client, M1R_PD_SERVICE)
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
            client, M1R_PD_SERVICE, M1R_PD_SERVICE_DESC, ep_id
        )
        log(f"  service [{action}] {M1R_PD_SERVICE} → {sid}")
        if not sid:
            return None
        time.sleep(PD_REQ_SLEEP)

        # 3. Idempotency.
        existing_keys = pd_fetch_all_incident_keys(client)
        ikey = pd_incident_key(M1R_PD_SERVICE, M1R_PD_TITLE, salt="M1R")
        if ikey in existing_keys:
            log(f"  M1R incident already seeded (key={ikey})")
            r = pagerduty_request(
                client, "GET", "/incidents",
                params={"incident_key": ikey},
            )
            if r.status_code == 200:
                incs = r.json().get("incidents", [])
                if incs:
                    return incs[0].get("id")
            return None

        # 4. Create LOW (P3) incident + auto-resolve.
        inc_id, inc_num = pd_create_incident(
            client, sid,
            M1R_PD_TITLE,
            "low",  # P3 → PagerDuty 'low' urgency
            m1r_pd_body(stripe_customer_id),
            ikey,
        )
        if not inc_id:
            log("  ! could not create M1R P3 incident")
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
    log("Manthan M1R patch - Maya Patel small autonomous duplicate refund")
    log("=" * 72)

    c = maya_company()
    log(f"\nCustomer: {c.name} / {c.slug}")
    log(f"  email   : {c.email}")
    log(f"  ARR     : ${c.arr_usd:,}")
    log(f"  plan    : {c.plan} ({MAYA_PLAN_DISPLAY} @ ${MAYA_MONTHLY_USD}/mo)")
    log(f"  region  : {MAYA_REGION}")
    log(f"  health  : {c.health}  (NPS={MAYA_NPS}, tenure={MAYA_TENURE_MONTHS}mo)")

    # 1. Stripe - required (drives the duplicate-charge case)
    cust = stripe_ensure_customer(c)
    price = stripe_ensure_caldera_price()
    sub = stripe_ensure_subscription(cust, price.id)
    ch_a, ch_b = stripe_create_duplicate_charges(cust)
    stripe_customer_id = cust.id

    # 2. Salesforce - best-effort
    sf_account_id, sf_contact_id = salesforce_seed(c, stripe_customer_id)

    # 3. HubSpot
    hs_cid, hs_contact_id, hs_nid = hubspot_seed(c, stripe_customer_id)

    # 4. Intercom (contact only, NO conversations)
    ic_contact_id = intercom_seed()

    # 5. Zendesk
    zd_result = zendesk_seed(c)

    # 6. Slack (intentionally skipped)
    slack_channel_id, slack_ts = slack_seed()

    # 7. Notion
    notion_pages = notion_seed()

    # 8. PostHog
    ph_result = posthog_seed(stripe_customer_id)

    # 9. Sentry
    sentry_result = sentry_seed(stripe_customer_id)

    # 10. Datadog
    dd_event_id = datadog_seed(stripe_customer_id)

    # 11. PagerDuty
    pd_incident_id = pagerduty_seed(stripe_customer_id)

    # ── Summary ──
    log("\n" + "═" * 72)
    log("M1R SEED SUMMARY")
    log("═" * 72)
    log(f"Stripe customer        : {stripe_customer_id}")
    log(f"Stripe subscription    : {sub.id}")
    log(f"Stripe charge A (orig) : {ch_a.id}  ${ch_a.amount/100:,.2f}  "
        f"@ {CHARGE_A_TIMESTAMP}")
    log(f"Stripe charge B (dup)  : {ch_b.id}  ${ch_b.amount/100:,.2f}  "
        f"@ {CHARGE_B_TIMESTAMP}  ← refund target")
    log(f"Stripe webhook_retry_chain: {STRIPE_WEBHOOK_RETRY_CHAIN_ID}")
    log(f"Salesforce account     : {sf_account_id or '(skipped)'}")
    log(f"Salesforce contact     : {sf_contact_id or '(skipped)'}")
    log(f"HubSpot company        : {hs_cid}")
    log(f"HubSpot contact        : {hs_contact_id}")
    log(f"HubSpot good-standing note: {hs_nid}")
    log(f"Intercom contact       : {ic_contact_id}  (no conversations)")
    log(f"Zendesk org            : {zd_result.get('org_id')}")
    log(f"Zendesk older tickets  : {len(zd_result.get('ticket_ids', []))}")
    log(f"Slack                  : (intentionally skipped)")
    log(f"Notion pages           : {len(notion_pages)}")
    for title, pid in notion_pages:
        log(f"  - {title}: {pid[:8]}…")
    log(f"PostHog events sent    : {ph_result.get('events_sent')} "
        f"errors={ph_result.get('events_error')}")
    log(f"Sentry RetryError      : {'seeded' if sentry_result['retry_event_seeded'] else 'MISSING'}")
    log(f"Sentry baseline events : {sentry_result['baseline_events_seeded']}")
    log(f"Sentry project         : {sentry_result['project_slug']}")
    log(f"Datadog event          : {dd_event_id}")
    log(f"PagerDuty incident     : {pd_incident_id}  (P3, resolved)")

    log("\nM1R is seeded. To trigger the case in the demo, have Maya's "
        "real email (hitakshi220@gmail.com) send the duplicate-refund "
        "request to the support inbox. Manthan will look her up by "
        "email and find:")
    log(f"  customer_id        = {stripe_customer_id}")
    log(f"  charge_a_id        = {ch_a.id}  (original)")
    log(f"  charge_b_id        = {ch_b.id}  (duplicate - refund this)")
    log(f"  sentry_project     = {sentry_result['project_slug']}")
    log(f"  datadog_event_id   = {dd_event_id}")
    log(f"  pagerduty_inc_id   = {pd_incident_id}")
    log(f"  policy             = {SMALL_REFUND_POLICY_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
