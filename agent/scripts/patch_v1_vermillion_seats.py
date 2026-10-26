"""Patch V1R - Vermillion Studios seat-count chargeback.

Seeds evidence across all 11 connected sources so the Manthan agent
investigating the $4,500 chargeback can recommend FIGHT + a reconciliation
call with overwhelming corroboration:

  Stripe       - $4,500 test-mode dispute on a Pro Annual seat invoice
                 (25 seats x $180/mo) with metadata
                 semantic_reason=seat_count_dispute, claimed_seats=15,
                 billed_seats=25, prior_disputes_count=0.
  Salesforce   - "Vermillion Studios" account, Pro Annual, $54k ARR.
                 Plus a closed-won Opportunity "Seat Expansion +10 (Pro
                 Annual)" dated 2026-02-08 noting the COO Sarah Chen
                 DocuSigned the addendum. Activated 2026-02-15.
  HubSpot      - Company record + signed Note engagement dated 2026-02-08
                 attributing the 25-seat addendum signature to COO Sarah
                 Chen.
  Intercom     - 3 Feb-Mar 2026 conversations from admin Lisa Martinez
                 about ONBOARDING new team members (SSO, provisioning).
                 No billing complaints.
  Zendesk      - Zero billing-dispute tickets in 90 days. 2 unrelated
                 solved feature-request tickets from 2025 to show
                 normal customer behavior.
  Slack        - One post in #deal-desk from the AE on 2026-02-08
                 confirming Vermillion expansion to 25 seats provisioned
                 by CS, addendum signed by COO Sarah Chen.
  Notion       - "Seat Disputes - Playbook for the 'we only have N seats'
                 chargeback" codifying the FIGHT + reconciliation-call
                 path when addendum exists AND seats are used.
  PostHog      - April 2026 activity: 24 distinct user IDs from
                 @vermillion-design.test domain (logins + project actions).
  Sentry       - ~10 baseline error events tagged to Vermillion's tenant
                 (no seat-provisioning errors).
  Datadog      - Auth API log monitor + event/log showing 24 unique user
                 IDs from vermillion-design.test authenticating during
                 the disputed period (proves seats USED, not just
                 provisioned).
  PagerDuty    - Zero relevant incidents. One low-priority noise
                 incident summarising "no seat-provisioning incidents
                 in window" as a queryable anchor.

Idempotent: every resource is looked up by name/idem-key before creation.

Run:
    cd agent && uv run python scripts/patch_v1_vermillion_seats.py
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
            upsert_contact as sf_upsert_contact,
            upsert_opportunity as sf_upsert_opportunity,
        )
    except Exception:
        SALESFORCE_AVAILABLE = False


# Stripe is required - bail loudly if not configured.
stripe.api_key = os.getenv("STRIPE_API_KEY")
if not stripe.api_key or not stripe.api_key.startswith("sk_test_"):
    raise SystemExit("STRIPE_API_KEY must be a sk_test_... key in agent/.env")


# ──────────────────────────────────────────────────────────────────────
# V1R constants
# ──────────────────────────────────────────────────────────────────────

VERMILLION_SLUG = "vermillion-design"
VERMILLION_NAME = "Vermillion Studios"
VERMILLION_EMAIL = "finance@vermillion-design.test"
VERMILLION_DOMAIN = "vermillion-design.test"
VERMILLION_HS_DOMAIN = "vermillion-design.test"
VERMILLION_INDUSTRY = "design-agency"
VERMILLION_COUNTRY = "USA"
VERMILLION_REGION = "us-east-1"
VERMILLION_ARR_USD = 54000
VERMILLION_PLAN = "Pro Annual"

# Seat math: 25 seats × $180/mo = $4,500/mo invoice
VERMILLION_SEATS_BILLED = 25
VERMILLION_SEATS_CLAIMED = 15  # what the CFO claims in the chargeback
VERMILLION_SEATS_USED = 24      # actual active users (24/25)
VERMILLION_PRICE_PER_SEAT_USD = 180
VERMILLION_DISPUTED_AMOUNT_MINOR = 4_500_00  # $4,500

# Disputed billing window - April 2026 invoice
DISPUTED_INVOICE_DATE = "2026-04-12"
DISPUTED_WINDOW_START = "2026-04-01"
DISPUTED_WINDOW_END = "2026-04-30"
ADDENDUM_SIGNED_DATE = "2026-02-08"
ADDENDUM_ACTIVATED_DATE = "2026-02-15"

# Key people
COO_FULL_NAME = "Sarah Chen"
COO_TITLE = "COO"
COO_EMAIL = f"sarah.chen@{VERMILLION_DOMAIN}"
ADMIN_FULL_NAME = "Lisa Martinez"
ADMIN_TITLE = "Workspace Admin"
ADMIN_EMAIL = f"lisa@{VERMILLION_DOMAIN}"
CFO_FULL_NAME = "Marcus Webb"  # the one who filed the chargeback
CFO_TITLE = "CFO"
CFO_EMAIL = VERMILLION_EMAIL  # finance@vermillion-design.test

# Deterministic randomness so re-runs are reproducible.
RNG = random.Random(20260412)


# ──────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────


def log(msg: str = "") -> None:
    print(msg, flush=True)


# ──────────────────────────────────────────────────────────────────────
# 1. Stripe - customer, subscription, charge, dispute
# ──────────────────────────────────────────────────────────────────────


def vermillion_company() -> Company:
    return world_find_company(VERMILLION_SLUG)


def stripe_ensure_customer(c: Company) -> stripe.Customer:
    log("\n[STRIPE]  ensuring Vermillion customer…")
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
            "region": VERMILLION_REGION,
            "seeded_by": "manthan_seed_stripe",
            "workflow": "V1R",
            "seats_total": str(VERMILLION_SEATS_BILLED),
            "seats_active": str(VERMILLION_SEATS_USED),
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
    log("\n[STRIPE]  ensuring Pro Annual subscription (25 seats)…")
    # Idempotency: look for an existing primary sub on this customer.
    for s in stripe.Subscription.list(
        customer=cust.id, limit=10, status="all"
    ).auto_paging_iter():
        md = md_dict(s)
        if md.get("slug") == VERMILLION_SLUG and md.get("sub_role") == "primary":
            log(f"  [reuse] subscription {s.id} (status={s.status})")
            return s
    sub = safe_create(
        stripe.Subscription.create,
        idem_key=idem("sub", VERMILLION_SLUG, "primary-v1"),
        label=f"Subscription[{VERMILLION_SLUG}/primary]",
        customer=cust.id,
        items=[{"price": price_id, "quantity": VERMILLION_SEATS_BILLED}],
        default_payment_method=cust.invoice_settings.default_payment_method,
        metadata={
            "slug": VERMILLION_SLUG, "plan": VERMILLION_PLAN,
            "plan_key": "pro_annual",
            "seeded_by": "manthan_seed_stripe",
            "billing_source": "stripe_primary",
            "sub_role": "primary",
            "signup_year": "2024",
            "workflow": "V1R",
            "seats_original": "15",
            "seats_current": str(VERMILLION_SEATS_BILLED),
            "addendum_signed_date": ADDENDUM_SIGNED_DATE,
            "addendum_signer": COO_FULL_NAME,
            "addendum_signer_title": COO_TITLE,
        },
    )
    log(f"  [new]   subscription {sub.id} (status={sub.status}) "
        f"qty={VERMILLION_SEATS_BILLED}")
    return sub


def stripe_find_v1r_dispute() -> stripe.Dispute | None:
    """Look for an existing V1R dispute (idempotency)."""
    for d in stripe.Dispute.list(limit=100).auto_paging_iter():
        md = md_dict(d)
        if md.get("workflow") == "V1R" and md.get("slug") == VERMILLION_SLUG:
            return d
    return None


def stripe_create_disputed_charge_and_dispute(
    cust: stripe.Customer,
) -> tuple[stripe.Charge, stripe.Dispute]:
    """Create the $4,500 disputed seat invoice charge and capture the
    resulting dispute object.

    Stripe test mode only emits disputes from specific test cards.
    `pm_card_createDisputeProductNotReceived` is the closest test reason
    to a "billed for seats we don't have" claim.
    """
    existing = stripe_find_v1r_dispute()
    if existing:
        ch = stripe.Charge.retrieve(existing.charge) if existing.charge else None
        if ch:
            log(f"  [reuse] V1R dispute {existing.id} on charge {ch.id} "
                f"(status={existing.status})")
            return ch, existing

    log("\n[STRIPE]  creating $4,500 disputed seat-invoice charge…")
    unique_suffix = f"v1r-disp-{int(time.time())}"
    pi = safe_create(
        stripe.PaymentIntent.create,
        idem_key=idem("pi", VERMILLION_SLUG, unique_suffix),
        label=f"PI[{VERMILLION_SLUG}/{unique_suffix}]",
        amount=VERMILLION_DISPUTED_AMOUNT_MINOR,
        currency="usd",
        payment_method="pm_card_createDisputeProductNotReceived",
        confirm=True,
        customer=cust.id,
        off_session=True,
        description=(
            f"{VERMILLION_NAME} - Pro Annual seat invoice "
            f"({DISPUTED_INVOICE_DATE}). {VERMILLION_SEATS_BILLED} seats x "
            f"${VERMILLION_PRICE_PER_SEAT_USD}/mo. Customer claim "
            "(CFO Marcus Webb): 'billed for 25 seats but we only have 15.' "
            "Reality: COO Sarah Chen signed +10 seat addendum on "
            f"{ADDENDUM_SIGNED_DATE}; team uses 24/25 seats. CFO missed "
            "the internal handoff."
        ),
        metadata={
            "slug": VERMILLION_SLUG,
            "simulated_created_at": DISPUTED_INVOICE_DATE,
            "workflow": "V1R",
            "workflow_label": "seat_count_dispute_fight",
            "semantic_reason": "seat_count_dispute",
            "customer_claim": (
                "Billed for 25 seats but we only have 15."
            ),
            "claimed_seats": str(VERMILLION_SEATS_CLAIMED),
            "billed_seats": str(VERMILLION_SEATS_BILLED),
            "active_seats": str(VERMILLION_SEATS_USED),
            "disputed_window_start": DISPUTED_WINDOW_START,
            "disputed_window_end": DISPUTED_WINDOW_END,
            "charge_category": "seat_invoice_monthly",
            "billing_period_label": "Pro Annual April 2026 seat invoice",
            "invoice_label": "INV-2026-04-12",
            "region": VERMILLION_REGION,
            "prior_disputes_count": "0",
            "expected_decision": "fight",
            "expected_followup": "offer_reconciliation_call",
            "addendum_signed_date": ADDENDUM_SIGNED_DATE,
            "addendum_signer": COO_FULL_NAME,
            "addendum_signer_title": COO_TITLE,
            "filer_name": CFO_FULL_NAME,
            "filer_title": CFO_TITLE,
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
    # Tag the dispute with V1R metadata.
    disp = stripe.Dispute.modify(
        disp.id,
        metadata={
            "slug": VERMILLION_SLUG,
            "workflow": "V1R",
            "workflow_label": "seat_count_dispute_fight",
            "semantic_reason": "seat_count_dispute",
            "customer_claim": (
                "Billed for 25 seats but we only have 15."
            ),
            "claimed_seats": str(VERMILLION_SEATS_CLAIMED),
            "billed_seats": str(VERMILLION_SEATS_BILLED),
            "active_seats": str(VERMILLION_SEATS_USED),
            "disputed_window_start": DISPUTED_WINDOW_START,
            "disputed_window_end": DISPUTED_WINDOW_END,
            "simulated_created_at": "2026-04-22",
            "invoice_label": "INV-2026-04-12",
            "region": VERMILLION_REGION,
            "expected_decision": "fight",
            "expected_followup": "offer_reconciliation_call",
            "addendum_signed_date": ADDENDUM_SIGNED_DATE,
            "addendum_signer": COO_FULL_NAME,
            "addendum_signer_title": COO_TITLE,
            "filer_name": CFO_FULL_NAME,
            "filer_title": CFO_TITLE,
            "stripe_customer_id": cust.id,
            "prior_disputes_count": "0",
            "seeded_by": "manthan_seed_stripe",
        },
    )
    # Best-effort: stamp the charge metadata.
    try:
        stripe.Charge.modify(
            ch.id,
            description=(
                f"{VERMILLION_NAME} - Pro Annual seat invoice "
                f"({DISPUTED_INVOICE_DATE}). {VERMILLION_SEATS_BILLED} seats x "
                f"${VERMILLION_PRICE_PER_SEAT_USD}/mo. Customer claim "
                "(CFO Marcus Webb): 'billed for 25 seats but we only have 15.' "
                "Reality: COO Sarah Chen signed +10 seat addendum on "
                f"{ADDENDUM_SIGNED_DATE}; team uses 24/25 seats."
            ),
            metadata={
                "slug": VERMILLION_SLUG,
                "simulated_created_at": DISPUTED_INVOICE_DATE,
                "workflow": "V1R",
                "semantic_reason": "seat_count_dispute",
                "claimed_seats": str(VERMILLION_SEATS_CLAIMED),
                "billed_seats": str(VERMILLION_SEATS_BILLED),
                "active_seats": str(VERMILLION_SEATS_USED),
                "disputed_window_start": DISPUTED_WINDOW_START,
                "disputed_window_end": DISPUTED_WINDOW_END,
                "invoice_label": "INV-2026-04-12",
                "stripe_customer_id": cust.id,
                "region": VERMILLION_REGION,
                "seeded_by": "manthan_seed_stripe",
            },
        )
    except stripe.error.StripeError as e:
        log(f"  [charge-modify-skip] {ch.id}: {str(e)[:120]}")

    log(f"  charge   {ch.id}  amount=${ch.amount/100:,.2f}")
    log(f"  dispute  {disp.id}  reason={disp.reason}  status={disp.status}")
    return ch, disp


# ──────────────────────────────────────────────────────────────────────
# 2. Salesforce - Vermillion account + Seat Expansion Opportunity
# ──────────────────────────────────────────────────────────────────────


SF_OPP_NAME = "Vermillion Studios - Seat Expansion +10 (Pro Annual)"
SF_OPP_DESCRIPTION = (
    f"[manthan_patch_v1_vermillion_seats] Seat expansion from 15 to 25 "
    f"seats on Pro Annual plan. COO Sarah Chen e-signed the addendum via "
    f"DocuSign on {ADDENDUM_SIGNED_DATE}. Activated {ADDENDUM_ACTIVATED_DATE} "
    f"after CS-led seat provisioning (8 designers + 2 producers added to "
    f"workspace). Increment: +10 seats x ${VERMILLION_PRICE_PER_SEAT_USD}/mo = "
    f"+$1,800 MRR (+$21,600 ARR). Addendum filed in DocuSign envelope "
    f"DSE-2026-VRM-0208. Internal handoff to CFO Marcus Webb was logged "
    f"in the AE's deal-desk thread but Marcus appears to have missed it - "
    f"hence the $4,500 chargeback he filed on the April seat invoice. "
    f"This Opportunity is the authoritative contract-evidence anchor for "
    f"V1R chargeback investigation."
)


def salesforce_seed(
    c: Company, stripe_customer_id: str
) -> tuple[str | None, str | None, str | None]:
    if not SALESFORCE_AVAILABLE:
        log("\n[SALESFORCE]  SKIP - SALESFORCE_ACCESS_TOKEN not configured.")
        return None, None, None
    log("\n[SALESFORCE]  ensuring Vermillion Studios account + addendum opp…")
    try:
        with httpx.Client(headers=SF_HEADERS, timeout=SF_TIMEOUT) as client:
            account_id, action = sf_upsert_account(client, c)
            if not account_id:
                log(f"  [{action}] account create failed")
                return None, None, None
            log(f"  [{action}] account → {account_id}")

            # COO contact (the addendum signer).
            coo_id, coo_action = sf_upsert_contact(
                client,
                account_id=account_id,
                email=COO_EMAIL,
                first_name="Sarah",
                last_name="Chen",
                title=COO_TITLE,
            )
            log(f"  [{coo_action}] COO contact → {coo_id}")

            # The seat-expansion Opportunity (closed-won).
            seat_increment_amount = 10 * VERMILLION_PRICE_PER_SEAT_USD * 12
            opp_id, opp_action = sf_upsert_opportunity(
                client,
                account_id=account_id,
                name=SF_OPP_NAME,
                amount=seat_increment_amount,
                close_date=ADDENDUM_SIGNED_DATE,
                description=SF_OPP_DESCRIPTION,
                opp_type="Existing Customer - Upgrade",
            )
            log(f"  [{opp_action}] opportunity → {opp_id}")

            return account_id, coo_id, opp_id
    except Exception as e:
        log(f"  [skip] Salesforce error: {type(e).__name__}: {str(e)[:200]}")
        return None, None, None


# ──────────────────────────────────────────────────────────────────────
# 3. HubSpot - company + COO-signed addendum note
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
    existing = hubspot_find_company_by_domain(client, VERMILLION_HS_DOMAIN)
    description = (
        f"25-person design agency. Pro Annual customer. Original 15-seat "
        f"contract; expanded to 25 seats via DocuSigned addendum signed by "
        f"COO Sarah Chen on {ADDENDUM_SIGNED_DATE}, activated "
        f"{ADDENDUM_ACTIVATED_DATE}. Team actively uses 24/25 seats. CFO "
        f"Marcus Webb filed a $4,500 chargeback on the April 2026 seat "
        f"invoice (INV-2026-04-12) claiming 'we only have 15 seats' - "
        f"appears the COO->CFO internal handoff broke down. Workspace "
        f"admin Lisa Martinez has been ASKING about onboarding flows for "
        f"new hires, which corroborates the actual seat growth. "
        f"Stripe customer: {stripe_customer_id}. Workflow: V1R."
    )
    props = {
        "name": c.name,
        "domain": VERMILLION_HS_DOMAIN,
        "country": c.country,
        "annualrevenue": str(c.arr_usd),
        "description": description,
        "lifecyclestage": "customer",
        "industry": "MARKETING_AND_ADVERTISING",
    }
    if existing:
        r = hubspot_request(
            client, "PATCH",
            f"/crm/v3/objects/companies/{existing}",
            json={"properties": props},
        )
        if r.status_code in (200, 201):
            return existing
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


HUBSPOT_NOTE_SIGNATURE = "[manthan_patch_v1_vermillion_seats]"
HUBSPOT_NOTE_BODY = (
    f"{HUBSPOT_NOTE_SIGNATURE} {ADDENDUM_SIGNED_DATE} - Vermillion Studios "
    f"seat expansion addendum SIGNED. COO {COO_FULL_NAME} e-signed via "
    f"DocuSign (envelope DSE-2026-VRM-0208) adding 10 seats to the Pro "
    f"Annual contract (15 -> 25 total). +$1,800 MRR / +$21,600 ARR. "
    f"Activated by CS on {ADDENDUM_ACTIVATED_DATE}; 8 new designers + 2 "
    f"new producers provisioned to the workspace. Internal handoff to CFO "
    f"{CFO_FULL_NAME} attempted via deal-desk thread same day. "
    f"NOTE: Marcus subsequently filed a $4,500 chargeback on INV-2026-04-12 "
    f"claiming 'we only have 15 seats' - recommend FIGHT and offer a "
    f"reconciliation call per the Seat Disputes Playbook (SD-2026-V1). "
    f"COO signature + DocuSign envelope are dispositive."
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
    # Use the addendum-signed date as the note timestamp so the timeline
    # reflects the actual contract event.
    ts_ms = int(datetime(2026, 2, 8, 14, 30, 0,
                         tzinfo=timezone.utc).timestamp() * 1000)
    body = {
        "properties": {
            "hs_note_body": HUBSPOT_NOTE_BODY,
            "hs_timestamp": str(ts_ms),
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
) -> tuple[str | None, str | None]:
    log("\n[HUBSPOT]  ensuring Vermillion company + COO-signed addendum note…")
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
# 4. Intercom - 3 onboarding conversations from admin Lisa Martinez
# ──────────────────────────────────────────────────────────────────────


def intercom_ensure_contact(client: httpx.Client) -> str | None:
    """Create/find Lisa Martinez (the workspace admin) as the Intercom
    contact. She's the one actively talking to support about onboarding
    new hires - strong positive signal for the seat-usage case."""
    ext_id = f"{intercom_external_id(VERMILLION_SLUG)}_admin"
    existing = intercom_find_contact_by_external_id(client, ext_id)
    if existing:
        log(f"  [reuse] contact {existing}")
        return existing
    by_email = intercom_find_contact_by_email(client, ADMIN_EMAIL)
    if by_email:
        update = {
            "external_id": ext_id,
            "name": ADMIN_FULL_NAME,
            "signed_up_at": int(datetime(2024, 8, 6, 9, 0, 0,
                                         tzinfo=timezone.utc).timestamp()),
            "last_seen_at": int(time.time()) - 86400 * 3,
        }
        intercom_request(client, "PUT", f"/contacts/{by_email}", json=update)
        return by_email
    payload = {
        "role": "user",
        "email": ADMIN_EMAIL,
        "name": ADMIN_FULL_NAME,
        "external_id": ext_id,
        "signed_up_at": int(datetime(2024, 8, 6, 9, 0, 0,
                                     tzinfo=timezone.utc).timestamp()),
        "last_seen_at": int(time.time()) - 86400 * 3,
    }
    r = intercom_request(client, "POST", "/contacts", json=payload)
    if r.status_code in (200, 201):
        return r.json().get("id")
    if r.status_code == 409:
        return intercom_find_contact_by_email(client, ADMIN_EMAIL)
    log(f"  contact create fail: {r.status_code} {r.text[:200]}")
    return None


def _epoch(y: int, m: int, d: int, hh: int = 10, mm: int = 0) -> int:
    return int(datetime(y, m, d, hh, mm, 0, tzinfo=timezone.utc).timestamp())


V1R_INTERCOM_CONVOS = [
    {
        "subject": "Walking through SSO setup for new hires",
        "body": (
            "Hi - we've got a batch of new designers starting next week "
            "and I want to make sure they're set up cleanly. Can you walk "
            "me through setting up SSO for our new hires? We're on Okta "
            "and I'd rather not provision them one-by-one. Want them "
            "added to the workspace as Member, not Admin."
        ),
        "created_at": _epoch(2026, 2, 11, 14, 12),
        "final_state": "closed",
        "admin_reply": (
            "Hi Lisa - yes, SSO via Okta is the cleanest path. Settings -> "
            "Team -> SSO -> Connect Okta will walk you through SAML setup. "
            "Once that's live, group-based JIT provisioning will add anyone "
            "in your 'workspace-members' Okta group on first login. Happy "
            "to hop on a 10-min call if anything's unclear."
        ),
        "tag": "V1R.sso-setup",
    },
    {
        "subject": "Adding 8 more designers next month",
        "body": (
            "Hey - we're adding 8 more designers next month to support "
            "the new client engagements (couple of agencies subbed work "
            "to us). What's the cleanest way to provision seats? Do I "
            "just invite them through the workspace and the seat count "
            "auto-updates, or does our AE need to handle the contract "
            "side first?"
        ),
        "created_at": _epoch(2026, 2, 19, 10, 47),
        "final_state": "closed",
        "admin_reply": (
            "Hi Lisa - your AE handles the seat-count amendment on the "
            "contract side, and once that's signed our CS team provisions "
            "the workspace capacity. Then you invite users normally and "
            "they consume seats up to the contract maximum. I'll loop in "
            "your AE Priya to coordinate timing. Sounds like growth is good!"
        ),
        "tag": "V1R.seat-expansion",
    },
    {
        "subject": "Welcome flow working for the new team",
        "body": (
            "Quick follow-up - got the welcome flow working for the new "
            "team. SSO is humming, Okta JIT provisioning is creating users "
            "cleanly, and the new designers are already in their first "
            "shared workspace. Thanks for the help last month. Will be in "
            "touch about Asana integration next."
        ),
        "created_at": _epoch(2026, 3, 6, 16, 30),
        "final_state": "closed",
        "admin_reply": (
            "That's great to hear, Lisa. Glad the rollout went smoothly. "
            "Ping us anytime on the Asana side - we have a native "
            "integration that may shortcut the work."
        ),
        "tag": "V1R.welcome-flow",
    },
]


def intercom_seed() -> tuple[str | None, list[str]]:
    log("\n[INTERCOM]  ensuring admin contact + 3 onboarding conversations…")
    convo_ids: list[str] = []
    with httpx.Client(headers=INTERCOM_HEADERS, timeout=INTERCOM_TIMEOUT) as client:
        admin_id = intercom_get_admin_id(client)
        contact_id = intercom_ensure_contact(client)
        if not contact_id:
            log("  ERROR: could not establish Intercom contact for Vermillion")
            return None, []

        # Idempotency: search ALL conversations created by this contact
        # via Intercom's POST /conversations/search endpoint, then match
        # source.body against our V1R specs.
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
                    stripped = (
                        src_body.replace("<p>", "").replace("</p>", "").strip()
                    )
                    if stripped:
                        existing_bodies.append(stripped)
        except Exception:
            pass

        for spec in V1R_INTERCOM_CONVOS:
            # Match on the first 60 chars of body - distinct across V1R specs.
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
# 5. Zendesk - org + 2 older feature-request tickets (zero billing in 90d)
# ──────────────────────────────────────────────────────────────────────


# Both tickets are old (2025) and unrelated to billing/seats - they
# establish that Vermillion is a normal, non-complaining customer.
V1R_ZENDESK_TICKETS = [
    {
        "subject": "Feature request: per-project brand kit isolation",
        "body": (
            "When we work with multiple agency clients, we'd love to "
            "scope brand kits to a specific project rather than the "
            "whole workspace. Right now all the kits show up everywhere "
            "and it's a real footgun on shared screens during client "
            "presentations. Would prioritize this highly."
        ),
        "priority": "low",
        "status": "solved",
        "days_ago_from_anchor": (datetime(2026, 5, 27, tzinfo=timezone.utc)
                                 - datetime(2025, 7, 23, tzinfo=timezone.utc)
                                 ).days,
        "type": "question",
    },
    {
        "subject": "Feature request: Figma plugin handoff metadata",
        "body": (
            "Our handoff flow exports from Figma into your shared "
            "workspace. Would be great if your importer could read "
            "the Figma metadata (component name, variant, designer) "
            "rather than us re-tagging everything manually. Happy to "
            "share our current workaround if it's useful."
        ),
        "priority": "low",
        "status": "solved",
        "days_ago_from_anchor": (datetime(2026, 5, 27, tzinfo=timezone.utc)
                                 - datetime(2025, 10, 17, tzinfo=timezone.utc)
                                 ).days,
        "type": "question",
    },
]


def zendesk_seed(c: Company) -> dict[str, Any]:
    log("\n[ZENDESK]  ensuring organization + user + 2 older tickets…")
    state = zendesk_load_state()
    state.setdefault("organizations", {})
    state.setdefault("users", {})
    state.setdefault("v1r_vermillion_tickets", [])

    with httpx.Client(
        headers={"Content-Type": "application/json"},
        auth=ZENDESK_AUTH, timeout=ZENDESK_TIMEOUT,
    ) as client:
        # Org
        org_id = state["organizations"].get(VERMILLION_SLUG)
        if not org_id:
            org_id, action = zendesk_upsert_organization(client, c)
            if org_id:
                state["organizations"][VERMILLION_SLUG] = org_id
                zendesk_save_state(state)
                log(f"  org [{action}] id={org_id}")
            else:
                log(f"  ! could not upsert Zendesk org for {VERMILLION_SLUG}")
                return {"org_id": None, "ticket_ids": []}
        else:
            log(f"  org [reuse] id={org_id}")
        # User - the workspace admin Lisa Martinez (active CS contact).
        user_ext = f"ext_{VERMILLION_SLUG}_0"
        user_id = state["users"].get(user_ext)
        if not user_id:
            user_id, action = zendesk_upsert_user(
                client,
                email=ADMIN_EMAIL,
                name=ADMIN_FULL_NAME,
                role="end-user",
                organization_id=org_id,
                external_id=user_ext,
            )
            if user_id:
                state["users"][user_ext] = user_id
                zendesk_save_state(state)
                log(f"  user [{action}] id={user_id}")
            else:
                log(f"  ! could not upsert Zendesk user for {VERMILLION_SLUG}")
                return {"org_id": org_id, "ticket_ids": []}
        else:
            log(f"  user [reuse] id={user_id}")

        # Tickets - idempotency via state['v1r_vermillion_tickets']
        existing_tids = state.get("v1r_vermillion_tickets", [])
        if existing_tids:
            still_exist = []
            for tid in existing_tids:
                r = zendesk_request(client, "GET", f"/tickets/{tid}.json")
                if r.status_code == 200:
                    still_exist.append(tid)
            if len(still_exist) >= len(V1R_ZENDESK_TICKETS):
                log(f"  [reuse] {len(still_exist)} existing V1R tickets")
                return {"org_id": org_id, "ticket_ids": still_exist}

        now = datetime(2026, 5, 27, tzinfo=timezone.utc)
        new_tids: list[int] = []
        for spec in V1R_ZENDESK_TICKETS:
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
                "requester_email": ADMIN_EMAIL,
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
        state["v1r_vermillion_tickets"] = new_tids
        zendesk_save_state(state)
        return {"org_id": org_id, "ticket_ids": new_tids}


# ──────────────────────────────────────────────────────────────────────
# 6. Slack - #deal-desk post from AE confirming seat expansion
# ──────────────────────────────────────────────────────────────────────


SLACK_V1R_MESSAGE = (
    f"V1R / Vermillion Studios expansion to 25 seats provisioned by CS, "
    f"addendum signed by COO {COO_FULL_NAME}. {ADDENDUM_SIGNED_DATE} - "
    f"DocuSign envelope DSE-2026-VRM-0208 closed. Originally 15 seats on "
    f"Pro Annual; +10 seats added (8 designers + 2 producers) to support "
    f"new client work. CS provisioned the workspace capacity "
    f"{ADDENDUM_ACTIVATED_DATE}. +$1,800 MRR / +$21,600 ARR. Looping in "
    f"CFO {CFO_FULL_NAME} on the billing side so April invoice reflects "
    f"the new headcount. NOTE FOR FUTURE: if billing pings come in, COO "
    f"signature on the envelope is dispositive."
)

# Local state file for idempotency.
V1R_STATE_PATH = (
    SCRIPT_DIR.parent / ".manthan" / "v1r_vermillion_state.json"
)


def _load_v1r_state() -> dict[str, Any]:
    if V1R_STATE_PATH.exists():
        try:
            import json
            return json.loads(V1R_STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_v1r_state(state: dict[str, Any]) -> None:
    import json
    V1R_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    V1R_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def slack_seed() -> tuple[str | None, str | None]:
    log("\n[SLACK]    posting AE seat-expansion confirmation to #deal-desk…")
    state = _load_v1r_state()
    with httpx.Client(timeout=SLACK_TIMEOUT) as client:
        auth = slack_call(client, "auth.test")
        if not auth.get("ok"):
            log(f"  ! Slack auth failed: {auth}")
            return None, None
        # Find the #deal-desk channel (sales-style channel per spec).
        ch_list = slack_call(
            client, "conversations.list",
            params={"limit": 200, "exclude_archived": "true"},
        )
        channel_id = None
        for c in ch_list.get("channels", []):
            if c.get("name") == "deal-desk":
                channel_id = c["id"]
                break
        if not channel_id:
            log("  deal-desk not found - creating…")
            create = slack_call(
                client, "conversations.create",
                json={"name": "deal-desk", "is_private": False},
            )
            if create.get("ok"):
                channel_id = create["channel"]["id"]
            else:
                log(f"  ! could not create #deal-desk: {create.get('error')}")
                return None, None

        # Ensure the bot is a member so we can post.
        slack_call(
            client, "conversations.join",
            json={"channel": channel_id},
        )

        # Idempotency path A: local state file.
        cached_ts = state.get("slack_v1r_message_ts")
        cached_ch = state.get("slack_v1r_channel_id")
        if cached_ts and cached_ch == channel_id:
            log(f"  [reuse] Slack message ts={cached_ts} (from state file)")
            return channel_id, cached_ts

        # Idempotency path B: best-effort conversations.history.
        history = slack_call(
            client, "conversations.history",
            params={"channel": channel_id, "limit": 100},
        )
        if history.get("ok"):
            for m in history.get("messages", []):
                if "V1R / Vermillion Studios" in (m.get("text") or ""):
                    ts = m.get("ts")
                    log(f"  [reuse] Slack message ts={ts}")
                    state["slack_v1r_message_ts"] = ts
                    state["slack_v1r_channel_id"] = channel_id
                    _save_v1r_state(state)
                    return channel_id, ts

        # Post.
        post = slack_call(
            client, "chat.postMessage",
            json={"channel": channel_id, "text": SLACK_V1R_MESSAGE},
        )
        if post.get("ok"):
            ts = post.get("ts")
            log(f"  [new]   Slack post ts={ts}")
            state["slack_v1r_message_ts"] = ts
            state["slack_v1r_channel_id"] = channel_id
            _save_v1r_state(state)
            return channel_id, ts
        if post.get("error") == "not_in_channel":
            slack_call(
                client, "conversations.join",
                json={"channel": channel_id},
            )
            post = slack_call(
                client, "chat.postMessage",
                json={"channel": channel_id, "text": SLACK_V1R_MESSAGE},
            )
            if post.get("ok"):
                ts = post.get("ts")
                log(f"  [new]   Slack post ts={ts}")
                state["slack_v1r_message_ts"] = ts
                state["slack_v1r_channel_id"] = channel_id
                _save_v1r_state(state)
                return channel_id, ts
        log(f"  ! Slack post failed: {post.get('error')}")
        return channel_id, None


# ──────────────────────────────────────────────────────────────────────
# 7. Notion - Seat Disputes Playbook
# ──────────────────────────────────────────────────────────────────────


V1R_NOTION_PAGES = [
    NotionPage(
        title="Seat Disputes - Playbook for the 'we only have N seats' chargeback",
        category="Policy & SOP",
        signal_id="V1R",
        headings=[(2, "Seat Disputes Playbook (SD-2026-V1)")],
        paragraphs=[
            "Owner: RevOps (priya@miny-labs.com) + Billing Engineering + "
            "Deal Desk. Status: CURRENT - authoritative. Doc version 1.0 "
            "(2026-05). Last reviewed 2026-05-20. Internal policy id "
            "SD-2026-V1.",

            "Scope: this playbook governs how we respond to Stripe "
            "chargebacks and customer-initiated refund requests where "
            "the customer alleges they were billed for MORE seats than "
            "they actually have ('we only have N seats but you billed "
            "for M'). It is the authoritative reference for the "
            "FIGHT-vs-REFUND decision in seat-count disputes.",

            "",
            "Section 1 - The three-step verification.",
            "When a customer disputes seat count, verify in order:",

            "(1) Signed contract addendum in Salesforce or HubSpot.",
            "  - Look for a closed-won Opportunity OR a HubSpot Note "
            "    engagement reflecting a seat-increase amendment in the "
            "    trailing 12 months.",
            "  - REQUIRED: signature from a COO-level (or higher) "
            "    executive on the customer side. A workspace admin's "
            "    signature is NOT sufficient; it must be C-suite or "
            "    VP-of-Finance.",
            "  - Verify DocuSign envelope ID or e-signature artifact is "
            "    captured in the CRM note. If the signature exists in "
            "    one CRM but not the other, that's still sufficient for "
            "    FIGHT (CRM sync gaps are common).",

            "(2) Actual seat usage in PostHog AND Datadog auth logs.",
            "  - PostHog: count DISTINCT user IDs from the customer's "
            "    email domain (@customer-domain.test) active in the "
            "    DISPUTED billing period (not just the trailing 90 days). "
            "    Compare against billed_seats from Stripe invoice metadata.",
            "  - Datadog: query the auth API log monitor for the same "
            "    domain in the disputed window. Count unique user IDs "
            "    authenticating. This second source is critical because "
            "    PostHog covers product events but Datadog auth logs "
            "    prove the seats are LOGGING IN - i.e. actually used, "
            "    not just provisioned-and-abandoned.",
            "  - Threshold: if at least 80% of billed seats show "
            "    active authentication in the disputed window, the seats "
            "    are considered USED.",

            "(3) Absence of prior support tickets challenging the seat count.",
            "  - Search Zendesk + Intercom for the trailing 90 days for "
            "    tickets/conversations from the customer about: 'billing', "
            "    'wrong seats', 'over-billed', 'incorrect invoice'. "
            "  - ZERO billing-dispute tickets in 90 days = customer was "
            "    NOT confused about the seat count internally. The "
            "    chargeback is likely a CFO/finance handoff failure, "
            "    not a billing error.",
            "  - BONUS signal: if the workspace admin has been actively "
            "    ASKING about onboarding new team members in the same "
            "    window (SSO setup, provisioning flow, welcome emails), "
            "    that's strong corroboration that headcount grew "
            "    legitimately.",

            "",
            "Section 2 - The FIGHT + reconciliation-call decision rule.",
            "Fight the chargeback AND offer a reconciliation call with "
            "the customer's CFO when:",
            "  (a) the signed addendum exists in CRM (per Section 1.1), AND",
            "  (b) actual seat usage meets or exceeds the 80% threshold "
            "      (per Section 1.2), AND",
            "  (c) the customer has zero billing complaints in 90 days "
            "      (per Section 1.3).",

            "The combination of these three signals indicates the "
            "chargeback is a customer-side INTERNAL handoff failure - "
            "almost always the COO or AE handled the expansion without "
            "looping in the CFO/AP team. The CFO sees an invoice that "
            "looks 67% larger than expected and files a chargeback "
            "without consulting their COO. The reconciliation call "
            "exists to repair this internal communication failure WITHOUT "
            "burning the customer relationship.",

            "Cite policy ID SD-2026-V1-S2 in the dispute submission. "
            "Evidence package for FIGHT: (i) Stripe charge succeeded "
            "+ subscription with quantity reflecting new seat count, "
            "(ii) Salesforce Opportunity OR HubSpot note showing the "
            "addendum signature with COO name + DocuSign envelope, "
            "(iii) PostHog distinct-user count for the customer domain "
            "in the disputed window, (iv) Datadog auth-log unique-user "
            "count for the same window, (v) Zendesk + Intercom support "
            "history excerpt confirming zero billing complaints in 90 "
            "days. Attach as PDF + cite raw IDs in the submission notes.",

            "",
            "Section 3 - The REFUND decision rule.",
            "Refund the chargeback when ANY of these are true:",
            "  - No signed addendum exists in either CRM, OR",
            "  - Actual seat usage is below 50% of billed seats (seats "
            "    provisioned but abandoned - likely sales-led over-sell), OR",
            "  - The customer has filed prior billing complaints in the "
            "    trailing 90 days that we failed to resolve.",
            "In all three cases the customer has a legitimate grievance. "
            "Refund the disputed period + adjust the contract.",

            "",
            "Section 4 - The reconciliation call playbook.",
            "When fighting under Section 2, the AE (NOT the CFO of the "
            "customer or our billing team) initiates a reconciliation "
            "call. Script template:",
            "  1. Acknowledge the chargeback without conceding.",
            "  2. Walk through the addendum signature with their CFO + "
            "     COO on the same call.",
            "  3. Share the seat-usage snapshot (PostHog + Datadog).",
            "  4. Offer to formalize a quarterly billing-review cadence "
            "     so future expansions don't surprise the AP team.",
            "  5. If the CFO accepts: customer withdraws the chargeback "
            "     and Stripe credits us automatically.",
            "Do NOT issue a goodwill refund in the reconciliation call. "
            "The signed addendum is binding; offering money back signals "
            "uncertainty about our own contract.",

            "",
            "Section 5 - Edge cases.",
            "Repeat seat-count disputes from the same customer in any "
            "12-month window: escalate to VP Customer Success and the "
            "Deal Desk lead regardless of Section 1-2 outcome. Two "
            "chargebacks against the same contract within 12 months is "
            "a relationship signal that must be addressed at the "
            "executive level, not via Stripe evidence alone.",

            "Reference: policy id SD-2026-V1. "
            "Internal URL https://miny-labs.notion.site/sop-seat-disputes-v1 . "
            "Approved by VP CS + VP Finance + Deal Desk lead. "
            "Next review: 2026-11-15.",
        ],
    ),
]


def notion_seed() -> list[tuple[str, str]]:
    log("\n[NOTION]   ensuring V1R Seat Disputes Playbook page…")
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
        for page in V1R_NOTION_PAGES:
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
# 8. PostHog - April 2026 activity (24 distinct users active)
# ──────────────────────────────────────────────────────────────────────


# 24 active users from @vermillion-design.test (the 25th seat is
# provisioned-but-not-yet-active - a new hire). The mix reflects a
# real design agency: producers, designers, an AD, finance, ops.
def _build_personas() -> list[dict]:
    """Build 24 distinct user personas tied to vermillion-design.test."""
    roles = [
        ("creative-director", "Avery Quinn"),
        ("art-director", "Mateo Rivera"),
        ("design-lead", "Priya Iyer"),
        ("senior-designer", "Jordan Hale"),
        ("senior-designer", "Sora Tanaka"),
        ("senior-designer", "Theo Brandt"),
        ("designer", "Naomi Kessler"),
        ("designer", "Ravi Sundaram"),
        ("designer", "Camille Okafor"),
        ("designer", "Wes Yamamoto"),
        ("designer", "Inez Costa"),
        ("designer", "Bryn Mitchell"),
        ("junior-designer", "Lior Mendel"),
        ("junior-designer", "Phoebe Aoki"),
        ("junior-designer", "Diego Salinas"),
        ("producer", "Astrid Linde"),
        ("producer", "Quentin Marsh"),
        ("producer", "Hattie Lansing"),
        ("senior-producer", "Owen Falk"),
        ("ops-lead", "Imogen Park"),
        ("workspace-admin", ADMIN_FULL_NAME),  # Lisa Martinez
        ("operations", "Mateus Oliveira"),
        ("finance-ops", "Selene Vukovic"),
        ("coo", COO_FULL_NAME),  # Sarah Chen
    ]
    personas = []
    for i, (role, name) in enumerate(roles, start=1):
        # email: first-last lowercase with hyphen
        local = name.lower().replace(" ", ".")
        personas.append({
            "distinct_id": f"vermillion-design-user-{i:02d}",
            "role": role,
            "email": f"{local}@{VERMILLION_DOMAIN}",
            "name": name,
        })
    return personas


VERMILLION_POSTHOG_PERSONAS = _build_personas()


# April 2026 disputed-billing window for usage events.
APRIL_START = datetime(2026, 4, 1, 8, 0, 0, tzinfo=timezone.utc)
APRIL_END = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)


def _april_random_ts(rng: random.Random) -> datetime:
    span_s = int((APRIL_END - APRIL_START).total_seconds())
    offset = rng.randint(0, span_s)
    return APRIL_START + timedelta(seconds=offset)


def build_posthog_events(stripe_customer_id: str) -> list[dict]:
    """Build the April 2026 activity for Vermillion.

    Each of 24 personas gets:
      - $identify (establishes Person row)
      - 3-6 logins across the month (~96 logins total)
      - 5-12 project-creation / file-action events (~180 critical actions)
    """
    events: list[dict] = []
    rng = random.Random(20260401)

    base_props = {
        "company_slug": VERMILLION_SLUG,
        "company": VERMILLION_NAME,
        "plan": VERMILLION_PLAN,
        "arr_usd": VERMILLION_ARR_USD,
        "industry": VERMILLION_INDUSTRY,
        "country": VERMILLION_COUNTRY,
        "region": VERMILLION_REGION,
        "stripe_customer_id": stripe_customer_id,
        "seeded_by": "patch_v1_vermillion_seats",
        "workflow": "V1R",
        "$lib": "manthan-v1r-patch",
    }

    # 1) $identify per persona - establishes Person row.
    for p in VERMILLION_POSTHOG_PERSONAS:
        events.append({
            "event": "$identify",
            "distinct_id": p["distinct_id"],
            "properties": {
                **base_props,
                "$set": {
                    "email": p["email"],
                    "name": p["name"],
                    "company": VERMILLION_NAME,
                    "company_slug": VERMILLION_SLUG,
                    "company_domain": VERMILLION_DOMAIN,
                    "plan": VERMILLION_PLAN,
                    "role": p["role"],
                    "team": "design",
                    "arr_usd": VERMILLION_ARR_USD,
                    "stripe_customer_id": stripe_customer_id,
                    "seeded_by": "patch_v1_vermillion_seats",
                    "workflow": "V1R",
                    "active_in_disputed_window": True,
                },
                "$set_once": {
                    "first_seen": "2024-08-06T09:00:00Z",
                    "signup_year": 2024,
                },
            },
            "timestamp": (APRIL_START - timedelta(days=1)).isoformat(),
        })

    # 2) Logins - 3 to 6 per persona, ~24 personas x 4 avg = ~96 logins.
    for p in VERMILLION_POSTHOG_PERSONAS:
        n_logins = rng.randint(3, 6)
        for _ in range(n_logins):
            ts = _april_random_ts(rng)
            events.append({
                "event": "user_logged_in",
                "distinct_id": p["distinct_id"],
                "properties": {
                    **base_props,
                    "role": p["role"],
                    "email": p["email"],
                    "login_method": rng.choice(["sso", "sso", "sso", "password"]),
                    "user_agent": "Manthan-V1R-Seed/1.0",
                },
                "timestamp": ts.isoformat(),
            })

    # 3) Project-creation + file actions - design-agency critical path.
    CRITICAL_ACTIONS = [
        ("create_project", "projects"),
        ("create_project", "projects"),
        ("upload_design_file", "files"),
        ("upload_design_file", "files"),
        ("upload_design_file", "files"),
        ("comment_on_design", "collaboration"),
        ("comment_on_design", "collaboration"),
        ("share_with_client", "delivery"),
        ("export_brand_kit", "brand-kit"),
        ("invite_collaborator", "team"),
    ]
    for p in VERMILLION_POSTHOG_PERSONAS:
        # Designers do more actions; admin/finance/coo do fewer.
        if "designer" in p["role"] or "art-director" in p["role"]:
            n_actions = rng.randint(8, 12)
        elif "producer" in p["role"]:
            n_actions = rng.randint(6, 10)
        else:
            n_actions = rng.randint(3, 6)
        for i in range(n_actions):
            action, area = CRITICAL_ACTIONS[
                (i + hash(p["distinct_id"])) % len(CRITICAL_ACTIONS)
            ]
            ts = _april_random_ts(rng)
            props = {
                **base_props,
                "role": p["role"],
                "email": p["email"],
                "action": action,
                "area": area,
                "is_critical_path": True,
            }
            if action == "create_project":
                props["project_id"] = f"prj_v1r_{p['distinct_id'][-2:]}_{i:02d}"
                props["client_name"] = rng.choice([
                    "Helios Cosmetics", "Northwind Apparel",
                    "Bottega Romano", "Quill Living", "Solstice Coffee",
                ])
            elif action == "upload_design_file":
                props["file_id"] = f"f_v1r_{p['distinct_id'][-2:]}_{i:02d}"
                props["file_format"] = rng.choice(
                    ["figma", "psd", "ai", "sketch"]
                )
                props["file_size_mb"] = round(rng.uniform(1.2, 84.0), 1)
            elif action == "share_with_client":
                props["share_url"] = (
                    f"https://vermillion-design.test/share/"
                    f"{p['distinct_id'][-2:]}-{i:02d}"
                )
            events.append({
                "event": action,
                "distinct_id": p["distinct_id"],
                "properties": props,
                "timestamp": ts.isoformat(),
            })

    return events


def posthog_seed(stripe_customer_id: str) -> dict[str, Any]:
    log("\n[POSTHOG]  ingesting April 2026 usage events for Vermillion…")
    out = {
        "events_sent": 0, "events_error": 0,
        "personas": len(VERMILLION_POSTHOG_PERSONAS),
    }
    state = _load_v1r_state()
    if state.get("posthog_v1r_seeded_for_customer") == stripe_customer_id:
        log("  [reuse] PostHog V1R events already ingested for this customer "
            "(state file). Skipping to avoid event duplication.")
        out["events_sent"] = state.get("posthog_v1r_events_sent", 0)
        return out
    with httpx.Client(headers=POSTHOG_HEADERS, timeout=POSTHOG_TIMEOUT) as client:
        project_key = fetch_project_api_key(client)
        if not project_key:
            log("  ! PostHog project key unavailable - skipping ingestion.")
            return out
        events = build_posthog_events(stripe_customer_id)
        log(f"  persons={len(VERMILLION_POSTHOG_PERSONAS)}  events={len(events)}")
        sent, errs = posthog_ingest_events(client, events, project_key)
        out["events_sent"] = sent
        out["events_error"] = errs
        log(f"  ingested {sent}  errors {errs}")
    state["posthog_v1r_seeded_for_customer"] = stripe_customer_id
    state["posthog_v1r_events_sent"] = sent
    _save_v1r_state(state)
    return out


# ──────────────────────────────────────────────────────────────────────
# 9. Sentry - ~10 baseline events tagged to Vermillion (no provisioning errors)
# ──────────────────────────────────────────────────────────────────────


V1R_SENTRY_PROJECT_SLUG = "api-gateway"
V1R_SENTRY_TEAM_SLUG = "platform"
V1R_SENTRY_TITLE = (
    "ValueError: optional file_metadata.tag missing on design upload - "
    "backfilled with workspace default"
)


def sentry_seed(stripe_customer_id: str) -> int:
    """Ingest ~10 baseline error events tagged to Vermillion's tenant
    across April 2026. Routine baseline noise - no seat-provisioning
    errors, which is itself evidence (no provisioning failures means
    the +10 seat expansion worked cleanly).
    """
    log("\n[SENTRY]   ingesting baseline error events for Vermillion tenant…")
    state = _load_v1r_state()
    if state.get("sentry_v1r_seeded_for_customer") == stripe_customer_id:
        log("  [reuse] Sentry V1R events already ingested for this customer "
            "(state file). Skipping to avoid event duplication.")
        return state.get("sentry_v1r_events_count", 0)
    with httpx.Client(headers=SENTRY_HEADERS, timeout=SENTRY_TIMEOUT) as client:
        try:
            sentry_ping_org(client)
        except SystemExit as e:
            log(f"  ! Sentry org ping failed: {e}")
            return 0
        existing_teams = {t["slug"]: t for t in sentry_list_teams(client)}
        if V1R_SENTRY_TEAM_SLUG not in existing_teams:
            sentry_ensure_team(client, "Platform Eng", V1R_SENTRY_TEAM_SLUG)
        existing_projects = {p["slug"]: p for p in sentry_list_projects(client)}
        if V1R_SENTRY_PROJECT_SLUG not in existing_projects:
            sentry_ensure_project(
                client, V1R_SENTRY_TEAM_SLUG,
                "API Gateway", V1R_SENTRY_PROJECT_SLUG, "python",
            )
        dsn = sentry_get_project_dsn(client, V1R_SENTRY_PROJECT_SLUG)

    sentry_init_for_project(dsn)
    total_events = 10
    rng = random.Random(20260412)
    V1R_FINGERPRINT = ["ValueError", V1R_SENTRY_TITLE]

    for i in range(total_events):
        ts = _april_random_ts(rng).isoformat()
        narrative_date = ts[:10]
        with sentry_sdk.push_scope() as scope:
            scope.level = "warning"  # type: ignore[assignment]
            scope.fingerprint = V1R_FINGERPRINT
            scope.set_tag("service", "api-gateway")
            scope.set_tag("env", "production")
            scope.set_tag("tenant", VERMILLION_SLUG)
            scope.set_tag("customer_slug", VERMILLION_SLUG)
            scope.set_tag("customer_id", stripe_customer_id)
            scope.set_tag("customer_domain", VERMILLION_DOMAIN)
            scope.set_tag("region", VERMILLION_REGION)
            scope.set_tag("workflow", "V1R")
            scope.set_tag("narrative_date", narrative_date)
            scope.set_context(
                "tenant_context",
                {
                    "customer_id": stripe_customer_id,
                    "company_slug": VERMILLION_SLUG,
                    "region": VERMILLION_REGION,
                    "narrative_event_time": ts,
                    "baseline_error_rate_pct": 0.3,
                    "is_outage": False,
                    "is_seat_provisioning_error": False,
                    "note": (
                        "Routine baseline error tagged to Vermillion's "
                        "tenant during April 2026 (the disputed-invoice "
                        "month). Part of normal noise - no seat-"
                        "provisioning errors, no outage, no spike."
                    ),
                },
            )
            try:
                raise ValueError(
                    f"{V1R_SENTRY_TITLE} (customer {stripe_customer_id} "
                    f"narrative_time {ts})"
                )
            except ValueError:
                sentry_sdk.capture_exception()
        time.sleep(INGEST_SLEEP)

    # Baseline-confirming summary message.
    with sentry_sdk.push_scope() as scope:
        scope.level = "info"  # type: ignore[assignment]
        scope.fingerprint = V1R_FINGERPRINT
        scope.set_tag("service", "api-gateway")
        scope.set_tag("env", "production")
        scope.set_tag("tenant", VERMILLION_SLUG)
        scope.set_tag("customer_id", stripe_customer_id)
        scope.set_tag("workflow", "V1R")
        sentry_sdk.capture_message(
            f"April 2026 baseline error-rate summary for tenant "
            f"{VERMILLION_SLUG} (customer {stripe_customer_id}): ~0.3% "
            "across the month, no anomaly spike, zero seat-provisioning "
            "errors. Used as the corroboration baseline for chargeback "
            "V1R (seat-count dispute).",
            level="info",
        )
    sentry_sdk.flush(timeout=15.0)
    log(f"  Sentry events ingested: {total_events + 1}")
    state["sentry_v1r_seeded_for_customer"] = stripe_customer_id
    state["sentry_v1r_events_count"] = total_events + 1
    _save_v1r_state(state)
    return total_events + 1


# ──────────────────────────────────────────────────────────────────────
# 10. Datadog - auth API log monitor + 24-unique-user authentication event
# ──────────────────────────────────────────────────────────────────────


def v1r_datadog_monitor(stripe_customer_id: str) -> DDMonitorSpec:
    msg = (
        "Auth-API distinct-user monitor for the Vermillion Studios tenant "
        f"({stripe_customer_id}). \n\n"
        f"April 2026 narrative summary ({DISPUTED_WINDOW_START} -> "
        f"{DISPUTED_WINDOW_END}):\n"
        f"  - Distinct users authenticating from @{VERMILLION_DOMAIN}: "
        f"{VERMILLION_SEATS_USED} of {VERMILLION_SEATS_BILLED} billed "
        f"seats (96% active).\n"
        "  - Auth success rate: 99.94% (within SLA)\n"
        "  - SSO success rate: 99.97% (Okta JIT provisioning OK)\n"
        "  - Zero seat-provisioning errors across the window.\n\n"
        "This monitor is the authoritative auth-side reference for "
        "chargeback workflow V1R (Vermillion Studios seat-count dispute). "
        "When investigating an alleged seat-count chargeback, correlate "
        "the customer's domain + the disputed-window date range with this "
        "monitor's history."
    )
    return DDMonitorSpec(
        name=f"auth.api distinct users (Vermillion Studios tenant)",
        type="query alert",
        query=(
            "sum(last_1h):sum:auth.api.unique_users"
            "{customer_domain:vermillion-design.test} < 15"
        ),
        message=msg,
        tags=[
            "env:prod",
            "team:platform",
            "service:auth-api",
            f"region:{VERMILLION_REGION}",
            f"customer_id:{stripe_customer_id}",
            f"customer_domain:{VERMILLION_DOMAIN}",
            f"customer_slug:{VERMILLION_SLUG}",
            "workflow:V1R-vermillion-seats",
            "status:ok",
            f"narrative_window:{DISPUTED_WINDOW_START}_{DISPUTED_WINDOW_END}",
            f"narrative_unique_users:{VERMILLION_SEATS_USED}",
            f"narrative_billed_seats:{VERMILLION_SEATS_BILLED}",
        ],
        options=dd_common_options(
            {"critical": 15, "warning": 18},
            notify_no_data=False,
        ),
        note_state="OK",
    )


def v1r_datadog_event(stripe_customer_id: str) -> DDEventSpec:
    return DDEventSpec(
        title=(
            f"April 2026 auth-usage summary - Vermillion Studios "
            f"(workflow:V1R seat-count corroboration)"
        ),
        text=(
            f"Auth API log rollup for tenant {VERMILLION_SLUG} during "
            f"the chargeback V1R disputed window "
            f"({DISPUTED_WINDOW_START} -> {DISPUTED_WINDOW_END}).\n\n"
            "Narrative summary:\n"
            f"  - Unique users authenticating from @{VERMILLION_DOMAIN}: "
            f"{VERMILLION_SEATS_USED}/{VERMILLION_SEATS_BILLED} billed seats "
            "(96% active).\n"
            "  - Auth API success rate: 99.94%.\n"
            "  - SSO JIT-provisioning success rate: 99.97% (Okta).\n"
            "  - Zero seat-provisioning errors in the window.\n"
            "  - No regional incidents touching Vermillion's tenant.\n\n"
            "Distinct authenticated user IDs in window (24):\n"
            + "\n".join(
                f"    - {p['distinct_id']}  ({p['role']})  {p['email']}"
                for p in VERMILLION_POSTHOG_PERSONAS
            ) +
            "\n\n"
            "Note: the 25th seat (provisioned but not yet active) belongs "
            "to a new hire onboarding in May. This is consistent with the "
            "ramp pattern after the Feb 2026 +10 seat addendum.\n\n"
            f"Customer in scope: {stripe_customer_id} ({VERMILLION_NAME}, "
            f"{VERMILLION_DOMAIN}, Pro Annual). This event is the Datadog "
            "anchor for the V1R chargeback investigation. Tag-search by "
            "workflow:V1R-vermillion-seats or "
            f"customer_id:{stripe_customer_id} to locate."
        ),
        date_happened=dd_epoch(dd_hours_ago(4)),
        tags=[
            "service:auth-api",
            "service:api-gateway",
            "env:prod",
            "team:platform",
            f"region:{VERMILLION_REGION}",
            f"customer_id:{stripe_customer_id}",
            f"customer_domain:{VERMILLION_DOMAIN}",
            f"customer_slug:{VERMILLION_SLUG}",
            "workflow:V1R-vermillion-seats",
            f"narrative_window:{DISPUTED_WINDOW_START}_{DISPUTED_WINDOW_END}",
            f"narrative_unique_users:{VERMILLION_SEATS_USED}",
            f"narrative_billed_seats:{VERMILLION_SEATS_BILLED}",
            "summary:auth-usage-rollup",
        ],
        alert_type="success",
    )


def datadog_seed(stripe_customer_id: str) -> tuple[int | None, int | None]:
    log("\n[DATADOG]  ensuring auth-API monitor + auth-usage event…")
    mon_spec = v1r_datadog_monitor(stripe_customer_id)
    evt_spec = v1r_datadog_event(stripe_customer_id)
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
# 11. PagerDuty - zero seat-provisioning incidents.
#
# Seed a LOW-urgency "April 2026 seat-provisioning summary" incident as
# a queryable anchor that documents: zero P1/P2/P3 seat-provisioning
# incidents touching Vermillion's tenant. Marked resolved.
# ──────────────────────────────────────────────────────────────────────


V1R_PD_SERVICE = "auth-api"
V1R_PD_SERVICE_DESC = (
    "Authentication API - handles login, SSO JIT provisioning, session "
    "issuance, and workspace member seat resolution."
)
V1R_PD_TITLE = (
    f"auth-api: April 2026 seat-provisioning summary - Vermillion Studios "
    f"(workflow:V1R seat-count corroboration)"
)


def v1r_pd_body(stripe_customer_id: str) -> str:
    return (
        f"April 2026 seat-provisioning health rollup for tenant "
        f"{VERMILLION_SLUG} ({VERMILLION_NAME}, {VERMILLION_DOMAIN}), "
        f"scoped to customer {stripe_customer_id}.\n\n"
        "Purpose: this incident exists as a queryable anchor for the "
        "V1R chargeback investigation (Vermillion Studios filed a $4,500 "
        "chargeback on the April seat invoice claiming 'billed for 25 "
        "seats but we only have 15'). This incident summarises seat-"
        f"provisioning health for the disputed window "
        f"({DISPUTED_WINDOW_START} -> {DISPUTED_WINDOW_END}).\n\n"
        "Findings:\n"
        f"  - Zero P1 incidents touching Vermillion's tenant in April 2026.\n"
        f"  - Zero P2 incidents touching Vermillion's tenant in April 2026.\n"
        f"  - Zero seat-provisioning failures or rollbacks. The "
        f"    Feb 2026 +10 seat expansion (15 -> 25) provisioned cleanly "
        f"    on {ADDENDUM_ACTIVATED_DATE} and the workspace capacity has "
        f"    been stable since.\n"
        f"  - Datadog auth-API monitor shows {VERMILLION_SEATS_USED} "
        f"    distinct users from @{VERMILLION_DOMAIN} authenticating in "
        f"    the window - 96% of the 25 billed seats are actively used.\n"
        f"  - One routine SEV-3 noise blip: 2026-04-19 (~2 min Okta SSO "
        f"    callback latency), affected ~0.4% of tenant logins, "
        f"    auto-recovered, no customer impact.\n\n"
        f"Conclusion: no seat-provisioning issue in April 2026 that "
        f"could plausibly support Vermillion's chargeback claim. The "
        f"customer's COO Sarah Chen signed the +10 seat addendum on "
        f"{ADDENDUM_SIGNED_DATE} (DocuSign envelope DSE-2026-VRM-0208); "
        f"seats are provisioned and used. Recommend FIGHT + offer "
        f"reconciliation call with CFO Marcus Webb per Seat Disputes "
        f"Playbook (SD-2026-V1-S2).\n\n"
        f"Cross-references: Salesforce Opportunity 'Vermillion Studios "
        f"- Seat Expansion +10 (Pro Annual)', HubSpot note "
        f"[manthan_patch_v1_vermillion_seats], Datadog auth-API monitor "
        f"'auth.api distinct users (Vermillion Studios tenant)', PostHog "
        f"April activity ({VERMILLION_SEATS_USED} distinct users, ~96 "
        f"logins, ~180 critical-path actions on Vermillion's tenant), "
        f"Notion playbook 'Seat Disputes Playbook'."
    )


def pagerduty_seed(stripe_customer_id: str) -> str | None:
    log("\n[PAGERDUTY] ensuring auth-api service + April seat-summary…")
    with httpx.Client(headers=PD_HEADERS, timeout=PD_TIMEOUT) as client:
        # 1. Find or initialise an escalation policy.
        ep_id = None
        sid, ep_existing = pd_find_service_by_name(client, V1R_PD_SERVICE)
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
            client, V1R_PD_SERVICE, V1R_PD_SERVICE_DESC, ep_id
        )
        log(f"  service [{action}] {V1R_PD_SERVICE} → {sid}")
        if not sid:
            return None
        time.sleep(PD_REQ_SLEEP)

        # 3. Idempotency.
        existing_keys = pd_fetch_all_incident_keys(client)
        ikey = pd_incident_key(V1R_PD_SERVICE, V1R_PD_TITLE, salt="V1R")
        if ikey in existing_keys:
            log(f"  V1R incident already seeded (key={ikey})")
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
            V1R_PD_TITLE,
            "low",
            v1r_pd_body(stripe_customer_id),
            ikey,
        )
        if not inc_id:
            log("  ! could not create V1R summary incident")
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
    log("Manthan V1R patch - Vermillion Studios seat-count chargeback")
    log("=" * 72)

    c = vermillion_company()
    log(f"\nCustomer: {c.name} / {c.slug}")
    log(f"  email   : {c.email}")
    log(f"  ARR     : ${c.arr_usd:,}")
    log(f"  plan    : {c.plan}")
    log(f"  region  : {VERMILLION_REGION}")
    log(f"  seats   : {VERMILLION_SEATS_BILLED} billed "
        f"({VERMILLION_SEATS_USED} active)")
    log(f"  claim   : {VERMILLION_SEATS_CLAIMED} seats "
        f"(per CFO {CFO_FULL_NAME})")
    log(f"  reality : COO {COO_FULL_NAME} signed +10 addendum "
        f"{ADDENDUM_SIGNED_DATE}")

    # 1. Stripe - required (drives the chargeback)
    cust = stripe_ensure_customer(c)
    price = stripe_find_pro_annual_price()
    sub = stripe_ensure_subscription(cust, price.id)
    ch, disp = stripe_create_disputed_charge_and_dispute(cust)
    stripe_customer_id = cust.id

    # 2. Salesforce - best-effort
    sf_account_id, sf_coo_contact_id, sf_opp_id = salesforce_seed(
        c, stripe_customer_id
    )

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
    log("V1R SEED SUMMARY")
    log("═" * 72)
    log(f"Stripe customer        : {stripe_customer_id}")
    log(f"Stripe subscription    : {sub.id}  qty={VERMILLION_SEATS_BILLED}")
    log(f"Stripe charge          : {ch.id}  ${ch.amount/100:,.2f}")
    log(f"Stripe dispute         : {disp.id}  reason={disp.reason} "
        f"status={disp.status}")
    log(f"Salesforce account     : {sf_account_id or '(skipped)'}")
    log(f"Salesforce COO contact : {sf_coo_contact_id or '(skipped)'}")
    log(f"Salesforce seat opp    : {sf_opp_id or '(skipped)'}")
    log(f"HubSpot company        : {hs_cid}")
    log(f"HubSpot addendum note  : {hs_nid}")
    log(f"Intercom contact       : {ic_contact_id}")
    log(f"Intercom convos        : {len(ic_convos)}")
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
    log(f"PagerDuty V1R summary  : {pd_incident_id}")

    log("\nV1R is seeded. To trigger the case in the API, route the "
        "Stripe dispute id below into your trigger flow:")
    log(f"  dispute_id    = {disp.id}")
    log(f"  charge_id     = {ch.id}")
    log(f"  customer_id   = {stripe_customer_id}")
    log(f"  sf_account_id = {sf_account_id or '(skipped)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
