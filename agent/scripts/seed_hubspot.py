"""Seed HubSpot at SCALED volume: 35 companies + 80-100 contacts + 50-70 deals + 80-150 tickets.

Drives the Manthan billing-dispute investigation agent. Reads from
seed_world.py for canonical company identity so cross-source JOINs stay
consistent.

Idempotent - re-runs check existence by domain (companies), email
(contacts), and dealname/subject (deals/tickets) before creating.

The three workflow targets get specific signals baked in:

  W1 - Acme Genomics: description note about data export request +
       multiple disputes despite continued usage (no formal cancel).
  W2 - Northwind Logistics: associated "Enterprise Upgrade Q2 2026" deal
       at $9,000 closedwon + open ticket about Standard tier still showing.
  W3 - Mockingbird Media: description note about Stripe migration +
       "Migration Cutover" deal at $5,500 closedwon + double-billing ticket.

Run:
    .venv/bin/python scripts/seed_hubspot.py
"""

from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Make seed_world importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from seed_world import COMPANIES, WORKFLOWS, Company, find_company  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("ERROR: HUBSPOT_ACCESS_TOKEN missing from .env")

BASE = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Rate limit: 100 req per 10s for Private Apps → small inter-request sleep.
REQ_SLEEP = 0.12

TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Deterministic randomness so re-runs pick the same noise pattern.
RNG = random.Random(20260527)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _employees_from_arr(arr_usd: int) -> int:
    if arr_usd >= 120_000:
        return 500
    if arr_usd >= 60_000:
        return 200
    if arr_usd >= 24_000:
        return 50
    return 10


INDUSTRY_MAP: dict[str, str] = {
    "genomics": "BIOTECHNOLOGY",
    "logistics": "LOGISTICS_AND_SUPPLY_CHAIN",
    "media": "ONLINE_MEDIA",
    "consulting": "MANAGEMENT_CONSULTING",
    "biotech": "BIOTECHNOLOGY",
    "food": "FOOD_BEVERAGES",
    "software": "COMPUTER_SOFTWARE",
    "manufacturing": "ELECTRICAL_ELECTRONIC_MANUFACTURING",
    "ai-infra": "COMPUTER_SOFTWARE",
    "mining": "MINING_METALS",
    "energy": "OIL_ENERGY",
    "hospitality": "HOSPITALITY",
    "cloud-infra": "INTERNET",
    "ai-research": "RESEARCH",
    "finance": "FINANCIAL_SERVICES",
    "fintech": "FINANCIAL_SERVICES",
    "data-platform": "COMPUTER_SOFTWARE",
    "security": "COMPUTER_NETWORK_SECURITY",
    "research": "RESEARCH",
    "healthcare": "HOSPITAL_HEALTH_CARE",
    "venture-capital": "VENTURE_CAPITAL_PRIVATE_EQUITY",
    "real-estate": "REAL_ESTATE",
    "design-agency": "DESIGN",
}


def _domain(c: Company) -> str:
    return f"{c.slug.replace('-', '')}.test"


def _email_domain(c: Company) -> str:
    """Domain used in contact emails.

    HubSpot rejects ``.test`` TLDs in email validation (INVALID_EMAIL), so
    we route emails through ``<slug>.example.com`` instead. The company
    record itself can keep the ``.test`` domain.
    """
    return f"{c.slug.replace('-', '')}.example.com"


def _translate_email(c: Company, email: str) -> str:
    """Translate a ``.test`` email to the HubSpot-friendly ``.example.com``.

    Falls back to ``<local>@<slug>.example.com`` if the source email is
    already in some other shape.
    """
    if "@" not in email:
        return email
    local, _, _ = email.partition("@")
    return f"{local}@{_email_domain(c)}"


def _hubspot_description(c: Company) -> str:
    """Build a description property for the company."""
    if c.slug == "acme-genomics":
        # W1 signal - daisy-chained chargebacks.
        return (
            "Customer asked about data export options in March 2026. "
            "CSM Priya flagged yellow health - possible churn but no "
            "formal cancel request on file. Multiple chargebacks filed "
            "despite continued usage of the platform. Multiple disputes "
            "filed in 2025-2026 despite continued active product usage. "
            "CSM flagged for review. Renewed May 2026."
        )
    if c.slug == "mockingbird-media":
        # W3 signal - migration from legacy billing.
        return (
            "Migrated from legacy billing entity to Stripe in March 2026. "
            "Acquisition integration in progress - legacy subscription "
            "should have been terminated at end-of-March cutover per the "
            "post-acquisition runbook. Customer has reported duplicate "
            "charges across legacy and Stripe entities."
        )
    if c.slug == "northwind-logi":
        return (
            "Strategic enterprise account. Upgraded to Enterprise tier "
            "Q2 2026 - paid $9,000 upgrade fee on May 12 2026 but "
            "entitlement system showed customer remained on Standard "
            "tier. Webhook handler crash flagged in engineering. "
            "Renewal cycle November. " + (c.notes or "")
        ).strip()
    return c.notes or ""


def _company_properties(c: Company) -> dict[str, str]:
    props: dict[str, str] = {
        "name": c.name,
        "domain": _domain(c),
        "country": c.country,
        "annualrevenue": str(c.arr_usd),
        "numberofemployees": str(_employees_from_arr(c.arr_usd)),
        "description": _hubspot_description(c),
    }
    industry = INDUSTRY_MAP.get(c.industry)
    if industry:
        props["industry"] = industry
    return props


# ──────────────────────────────────────────────────────────────────────
# HTTP wrapper with auto-throttling + retry
# ──────────────────────────────────────────────────────────────────────


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    retries: int = 3,
) -> httpx.Response:
    url = path if path.startswith("http") else f"{BASE}{path}"
    for attempt in range(retries):
        r = client.request(method, url, json=json, params=params)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", "1.0"))
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        return r
    return r


# ──────────────────────────────────────────────────────────────────────
# Lookups
# ──────────────────────────────────────────────────────────────────────


def find_company_by_domain(client: httpx.Client, domain: str) -> str | None:
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "domain", "operator": "EQ", "value": domain,
        }]}],
        "properties": ["domain", "name"],
        "limit": 1,
    }
    r = _request(client, "POST", "/crm/v3/objects/companies/search", json=body)
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def find_contact_by_email(client: httpx.Client, email: str) -> str | None:
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "email", "operator": "EQ", "value": email,
        }]}],
        "properties": ["email"],
        "limit": 1,
    }
    r = _request(client, "POST", "/crm/v3/objects/contacts/search", json=body)
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def find_deal_by_name(client: httpx.Client, name: str) -> str | None:
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "dealname", "operator": "EQ", "value": name,
        }]}],
        "properties": ["dealname"],
        "limit": 1,
    }
    r = _request(client, "POST", "/crm/v3/objects/deals/search", json=body)
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def find_ticket_by_subject(client: httpx.Client, subject: str) -> str | None:
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "subject", "operator": "EQ", "value": subject,
        }]}],
        "properties": ["subject"],
        "limit": 1,
    }
    r = _request(client, "POST", "/crm/v3/objects/tickets/search", json=body)
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


# ──────────────────────────────────────────────────────────────────────
# Creators
# ──────────────────────────────────────────────────────────────────────


def upsert_company(client: httpx.Client, c: Company) -> tuple[str | None, str]:
    domain = _domain(c)
    props = _company_properties(c)
    existing_id = find_company_by_domain(client, domain)

    if existing_id:
        r = _request(
            client, "PATCH",
            f"/crm/v3/objects/companies/{existing_id}",
            json={"properties": props},
        )
        if r.status_code in (200, 201):
            return existing_id, "updated"
        if r.status_code == 400 and "industry" in props:
            props2 = {k: v for k, v in props.items() if k != "industry"}
            r = _request(
                client, "PATCH",
                f"/crm/v3/objects/companies/{existing_id}",
                json={"properties": props2},
            )
            if r.status_code in (200, 201):
                return existing_id, "updated (no industry)"
        print(f"  update fail {c.slug}: {r.status_code} {r.text[:200]}")
        return existing_id, "error"

    r = _request(
        client, "POST", "/crm/v3/objects/companies",
        json={"properties": props},
    )
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    if r.status_code == 400 and "industry" in props:
        props2 = {k: v for k, v in props.items() if k != "industry"}
        r = _request(
            client, "POST", "/crm/v3/objects/companies",
            json={"properties": props2},
        )
        if r.status_code in (200, 201):
            return r.json().get("id"), "created (no industry)"
    print(f"  create fail {c.slug}: {r.status_code} {r.text[:200]}")
    return None, "error"


def upsert_contact(
    client: httpx.Client,
    *,
    email: str,
    firstname: str,
    lastname: str,
    company_name: str,
    company_id: str,
    jobtitle: str | None = None,
    phone: str | None = None,
) -> tuple[str | None, str]:
    existing_id = find_contact_by_email(client, email)

    props: dict[str, str] = {
        "email": email,
        "firstname": firstname,
        "lastname": lastname,
        "company": company_name,
    }
    if jobtitle:
        props["jobtitle"] = jobtitle
    if phone:
        props["phone"] = phone

    if existing_id:
        r = _request(
            client, "PATCH",
            f"/crm/v3/objects/contacts/{existing_id}",
            json={"properties": props},
        )
        contact_id = existing_id
        action = "updated"
        if r.status_code not in (200, 201):
            print(f"  contact update fail {email}: {r.status_code} {r.text[:200]}")
            action = "error"
    else:
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
        r = _request(client, "POST", "/crm/v3/objects/contacts", json=body)
        if r.status_code in (200, 201):
            contact_id = r.json().get("id")
            action = "created"
        else:
            print(f"  contact create fail {email}: {r.status_code} {r.text[:200]}")
            return None, "error"

    # Ensure association exists even on update path.
    if contact_id and company_id:
        _request(
            client, "PUT",
            f"/crm/v4/objects/contact/{contact_id}/associations/default/company/{company_id}",
        )

    return contact_id, action


def upsert_deal(
    client: httpx.Client,
    *,
    name: str,
    amount: int,
    close_date: str,
    stage: str,
    company_id: str,
    description: str | None = None,
) -> tuple[str | None, str]:
    existing_id = find_deal_by_name(client, name)
    props: dict[str, str] = {
        "dealname": name,
        "amount": str(amount),
        "closedate": close_date,
        "dealstage": stage,
        "pipeline": "default",
    }
    if description:
        props["description"] = description

    if existing_id:
        r = _request(
            client, "PATCH",
            f"/crm/v3/objects/deals/{existing_id}",
            json={"properties": props},
        )
        deal_id = existing_id
        action = "updated"
        if r.status_code not in (200, 201):
            print(f"  deal update fail {name!r}: {r.status_code} {r.text[:200]}")
            action = "error"
    else:
        body = {
            "properties": props,
            "associations": [{
                "to": {"id": company_id},
                "types": [{
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": 341,  # deal -> company primary
                }],
            }],
        }
        r = _request(client, "POST", "/crm/v3/objects/deals", json=body)
        if r.status_code in (200, 201):
            deal_id = r.json().get("id")
            action = "created"
        else:
            print(f"  deal create fail {name!r}: {r.status_code} {r.text[:200]}")
            return None, "error"

    if deal_id and company_id:
        _request(
            client, "PUT",
            f"/crm/v4/objects/deal/{deal_id}/associations/default/company/{company_id}",
        )

    return deal_id, action


def upsert_ticket(
    client: httpx.Client,
    *,
    subject: str,
    content: str,
    stage: str,
    priority: str,
    company_id: str,
) -> tuple[str | None, str]:
    existing_id = find_ticket_by_subject(client, subject)
    props: dict[str, str] = {
        "subject": subject,
        "content": content,
        "hs_pipeline": "0",
        "hs_pipeline_stage": stage,
        "hs_ticket_priority": priority,
    }

    if existing_id:
        r = _request(
            client, "PATCH",
            f"/crm/v3/objects/tickets/{existing_id}",
            json={"properties": props},
        )
        ticket_id = existing_id
        action = "updated"
        if r.status_code not in (200, 201):
            print(f"  ticket update fail {subject!r}: {r.status_code} {r.text[:200]}")
            action = "error"
    else:
        body = {
            "properties": props,
            "associations": [{
                "to": {"id": company_id},
                "types": [{
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": 26,  # ticket -> company primary
                }],
            }],
        }
        r = _request(client, "POST", "/crm/v3/objects/tickets", json=body)
        if r.status_code in (200, 201):
            ticket_id = r.json().get("id")
            action = "created"
        else:
            print(f"  ticket create fail {subject!r}: {r.status_code} {r.text[:200]}")
            return None, "error"

    if ticket_id and company_id:
        _request(
            client, "PUT",
            f"/crm/v4/objects/ticket/{ticket_id}/associations/default/company/{company_id}",
        )

    return ticket_id, action


# ──────────────────────────────────────────────────────────────────────
# Contact plan - 2-4 contacts per company (primary, finance, exec, IT)
# ──────────────────────────────────────────────────────────────────────


FIRST_NAMES = [
    "Aaron", "Adriana", "Aiko", "Alex", "Amir", "Ana", "Anika", "Anna",
    "Bea", "Ben", "Caleb", "Carmen", "Chris", "Daniela", "David", "Dimitri",
    "Elena", "Eli", "Emma", "Erik", "Felix", "Fiona", "Gabriel", "Gina",
    "Hannah", "Harper", "Ines", "Isaac", "Jada", "Jamie", "Jordan", "Julia",
    "Kai", "Kavya", "Lara", "Leo", "Liam", "Lucia", "Maya", "Marco",
    "Naomi", "Nikhil", "Olga", "Owen", "Priya", "Quinn", "Rafael", "Riley",
    "Sara", "Sven", "Tara", "Theo", "Uma", "Vera", "Victor", "Wren",
    "Yara", "Yuki", "Zara", "Zane",
]
LAST_NAMES = [
    "Adler", "Banerjee", "Carter", "Choi", "Diaz", "Engel", "Fischer",
    "Garcia", "Hassan", "Iyer", "Johansson", "Kovacs", "Lin", "Marquez",
    "Nakamura", "Okafor", "Petrov", "Quinn", "Reyes", "Schmidt", "Tanaka",
    "Ulrich", "Vargas", "Wong", "Xu", "Yamamoto", "Zhang", "Andersson",
    "Beauchamp", "Castellano", "Devereux", "Ekberg", "Falconer", "Greco",
    "Holm", "Iversen", "Jansson", "Kowalski", "Lange", "Mendes",
]


def _pick_name(slug: str, salt: str) -> tuple[str, str]:
    """Deterministic name picker keyed by slug+salt."""
    seed = hash(f"{slug}|{salt}") & 0xFFFFFFFF
    r = random.Random(seed)
    return r.choice(FIRST_NAMES), r.choice(LAST_NAMES)


@dataclass
class ContactPlan:
    role: str  # "primary" | "finance" | "exec" | "it"
    email_prefix: str
    jobtitle: str


CONTACT_ROLES: list[ContactPlan] = [
    ContactPlan("primary", "", "Operations Lead"),
    ContactPlan("finance", "cfo", "Chief Financial Officer"),
    ContactPlan("exec", "ceo", "Chief Executive Officer"),
    ContactPlan("it", "it", "Head of IT"),
]


def _build_contact_plan(c: Company) -> list[dict]:
    """Build 2-4 contacts for this company depending on ARR.

    Workflow targets always get all 4. Bigger companies get all 4,
    mid get 3, smaller get 2.
    """
    workflow_slugs = {w.target_company_slug for w in WORKFLOWS.values()}
    if c.slug in workflow_slugs or c.arr_usd >= 60_000:
        roles = CONTACT_ROLES  # all 4
    elif c.arr_usd >= 24_000:
        roles = CONTACT_ROLES[:3]  # primary + finance + exec
    else:
        roles = CONTACT_ROLES[:2]  # primary + finance

    domain = _email_domain(c)
    out: list[dict] = []
    for role in roles:
        if role.role == "primary":
            # Use the source email's local part but route to a HubSpot-
            # friendly domain (HubSpot rejects ``.test`` TLDs).
            email = _translate_email(c, c.email)
            local = email.split("@", 1)[0]
            parts = local.replace(".", "-").split("-")
            first = (parts[0] or "Contact").title()
            last = (parts[-1] if len(parts) > 1 else c.name.split()[0]).title()
        else:
            email = f"{role.email_prefix}@{domain}"
            first, last = _pick_name(c.slug, role.role)
        out.append({
            "role": role.role,
            "email": email,
            "firstname": first,
            "lastname": last,
            "jobtitle": role.jobtitle,
        })
    return out


# ──────────────────────────────────────────────────────────────────────
# Deal plan generator - renewals, new business, lost, expansion, open
# ──────────────────────────────────────────────────────────────────────


@dataclass
class DealSpec:
    company_slug: str
    name: str
    amount: int
    close_date: str
    stage: str
    description: str = ""


def _arr_jitter(arr: int, factor: float) -> int:
    return int(round(arr * factor))


def _build_deal_plan() -> list[DealSpec]:
    """Build a varied deal plan ~50-70 deals."""
    plan: list[DealSpec] = []
    current_year = 2026

    # ---- Hard-coded workflow signal deals ----
    plan.append(DealSpec(
        company_slug="northwind-logi",
        name="Northwind - Enterprise Upgrade Q2 2026",
        amount=9000,
        close_date="2026-05-12",
        stage="closedwon",
        description=(
            "Customer paid $9,000 Enterprise upgrade fee. Stripe charge "
            "succeeded but webhook handler crashed (see Sentry/Datadog) - "
            "entitlement never flipped. Customer remained on Standard tier. "
            "Refund + manual upgrade required."
        ),
    ))
    plan.append(DealSpec(
        company_slug="mockingbird-media",
        name="Mockingbird - Migration Cutover",
        amount=5500,
        close_date="2026-03-15",
        stage="closedwon",
        description=(
            "Migration cutover from legacy billing entity to Stripe. "
            "Per runbook the legacy entity should have been terminated "
            "end-of-March."
        ),
    ))

    # ---- Per-company history: New Business + yearly renewals ----
    for c in COMPANIES:
        # New Business in the signup year.
        new_biz_month = RNG.randint(1, 11)
        new_biz_amount = _arr_jitter(c.arr_usd, RNG.uniform(0.7, 1.0))
        plan.append(DealSpec(
            company_slug=c.slug,
            name=f"{c.name} - New Business {c.signup_year}",
            amount=new_biz_amount,
            close_date=f"{c.signup_year}-{new_biz_month:02d}-{RNG.randint(2, 27):02d}",
            stage="closedwon",
            description=f"Initial {c.plan} purchase.",
        ))

        # Renewal deals: one per year after signup, up to current_year.
        for year in range(c.signup_year + 1, current_year + 1):
            month = RNG.randint(1, 11)
            day = RNG.randint(2, 27)
            amount = _arr_jitter(c.arr_usd, RNG.uniform(0.95, 1.15))
            plan.append(DealSpec(
                company_slug=c.slug,
                name=f"{c.name} - {c.plan} Renewal {year}",
                amount=amount,
                close_date=f"{year}-{month:02d}-{day:02d}",
                stage="closedwon",
                description=f"Annual renewal for {year}.",
            ))

    # ---- Closed-lost deals (competitive evals lost) ----
    lost_candidates = [
        ("acme-logistics", "Acme Logistics - Renewal Lost 2026", 18000, "2026-04-22"),
        ("helix-bio", "Helix Bio - Expansion Lost", 24000, "2025-12-04"),
        ("delta-payments", "Delta Payments - Competitive Eval Lost", 30000, "2025-11-18"),
        ("voyager-shipping", "Voyager Shipping - Renewal Lost", 60000, "2025-10-25"),
        ("titan-marine", "Titan Marine - Competitive Eval Lost", 28000, "2025-09-08"),
        ("ember-design", "Ember Design - Downgrade Lost", 9000, "2025-08-15"),
        ("alchemy-foods", "Alchemy Foods - Renewal Lost", 14000, "2026-02-09"),
    ]
    for slug, name, amt, dt in lost_candidates:
        plan.append(DealSpec(
            company_slug=slug, name=name, amount=amt,
            close_date=dt, stage="closedlost",
            description="Competitive evaluation - lost to alternative vendor.",
        ))

    # ---- Expansion deals (add-on seat purchases) for ~10 customers ----
    expansion_candidates = [
        ("acme-genomics", "Acme Genomics - Seat Expansion", 12000, "2025-09-14", "closedwon"),
        ("northwind-logi", "Northwind - Add-On Seats 2025", 18000, "2025-08-22", "closedwon"),
        ("stellar-ai", "Stellar AI - Premium Tier Expansion", 36000, "2026-01-19", "closedwon"),
        ("phoenix-fund", "Phoenix Fund - Multi-Region Expansion", 42000, "2025-10-03", "closedwon"),
        ("cascade-cloud", "Cascade Cloud - Storage Expansion", 14000, "2026-02-27", "closedwon"),
        ("nexus-data", "Nexus Data - Premium Tier Add-On", 30000, "2025-04-08", "closedwon"),
        ("zephyr-ventures", "Zephyr Ventures - Power User Seats", 22000, "2024-11-15", "closedwon"),
        ("solstice-care", "Solstice Care - Compliance Tier Add-On", 28000, "2025-07-12", "closedwon"),
        ("globex-software", "Globex Software - API Tier Upgrade", 12000, "2025-06-29", "closedwon"),
        ("helio-energy", "Helio Energy - Multi-Site Expansion", 24000, "2025-12-18", "closedwon"),
    ]
    for slug, name, amt, dt, st in expansion_candidates:
        plan.append(DealSpec(
            company_slug=slug, name=name, amount=amt,
            close_date=dt, stage=st,
            description="Add-on expansion - additional seats or modules.",
        ))

    # ---- Open pipeline deals (in-progress) ----
    open_candidates = [
        ("quantum-synth", "Quantum Synth - Enterprise Upgrade 2026", 84000, "2026-09-30", "presentationscheduled"),
        ("orion-labs", "Orion Labs - Compliance Tier Eval", 24000, "2026-08-15", "qualifiedtobuy"),
        ("apex-software", "Apex Software - Pro Tier Upgrade", 18000, "2026-07-22", "decisionmakerboughtin"),
        ("hydra-finance", "Hydra Finance - APAC Expansion", 36000, "2026-09-10", "contractsent"),
        ("cobra-cybersec", "Cobra Cybersec - Premium Tier", 30000, "2026-08-03", "presentationscheduled"),
        ("polaris-pay", "Polaris Pay - Renewal + Expansion 2026", 48000, "2026-10-12", "qualifiedtobuy"),
        ("horizon-genomics", "Horizon Genomics - Multi-Site Pilot", 18000, "2026-07-18", "decisionmakerboughtin"),
        ("summit-payments", "Summit Payments - Enterprise Migration", 96000, "2026-09-05", "contractsent"),
    ]
    for slug, name, amt, dt, st in open_candidates:
        plan.append(DealSpec(
            company_slug=slug, name=name, amount=amt,
            close_date=dt, stage=st,
            description="Active pipeline opportunity.",
        ))

    return plan


# ──────────────────────────────────────────────────────────────────────
# Ticket plan generator - varied subjects, statuses, priorities
# ──────────────────────────────────────────────────────────────────────


# Pipeline stage IDs from /crm/v3/pipelines/tickets:
# 1=New, 2=Waiting on contact, 3=Waiting on us, 4=Closed
TICKET_STAGES = ["1", "2", "3", "4"]
TICKET_PRIORITIES = ["LOW", "MEDIUM", "HIGH"]


@dataclass
class TicketTemplate:
    subject_template: str
    content_template: str
    typical_priority: str
    typical_stage: str  # "open" or "closed"


TICKET_TEMPLATES: list[TicketTemplate] = [
    TicketTemplate(
        "Onboarding kickoff - need help configuring SSO",
        "Hi team, we just signed and want to set up SSO via Okta before "
        "rolling the platform out to our team. Can someone walk us through "
        "the SAML metadata exchange? We'd like to schedule a 30-min call "
        "this week if possible.",
        "MEDIUM", "closed",
    ),
    TicketTemplate(
        "Password reset for admin user",
        "Our admin user lost MFA access after switching phones. Can you "
        "reset their account so we can re-enroll? Account email is on file.",
        "MEDIUM", "closed",
    ),
    TicketTemplate(
        "Feature request: bulk CSV import",
        "Would love to bulk import contacts via CSV instead of one-by-one. "
        "Is this on the roadmap? Happy to be a beta tester.",
        "LOW", "open",
    ),
    TicketTemplate(
        "Integration help - Salesforce sync stopped",
        "Our SFDC sync stopped pushing new contacts ~3 days ago. We see "
        "no errors in the dashboard. Can you investigate?",
        "HIGH", "open",
    ),
    TicketTemplate(
        "Question about API rate limits",
        "We're hitting 429 errors when running our nightly export. What's "
        "the rate limit on the v3 API and can it be raised?",
        "MEDIUM", "closed",
    ),
    TicketTemplate(
        "Billing question - invoice doesn't match quote",
        "We were quoted $X for the Pro annual plan but the invoice we "
        "just received is higher. Can someone walk us through the line items?",
        "MEDIUM", "closed",
    ),
    TicketTemplate(
        "How do I export historical reports?",
        "We need to pull last 12 months of usage data for an internal "
        "audit. Is there a self-serve export, or do we need to file a "
        "request with support?",
        "LOW", "closed",
    ),
    TicketTemplate(
        "Login redirect loop on staging URL",
        "When we log in from app-staging.example.com we get bounced back "
        "to the login screen indefinitely. Production works fine. "
        "Chrome 120, no extensions.",
        "HIGH", "closed",
    ),
    TicketTemplate(
        "Add 5 new seats - need procurement quote",
        "We want to add 5 seats to our Pro plan. Can you send a formal "
        "PDF quote to procurement@? They need it for PO approval.",
        "MEDIUM", "open",
    ),
    TicketTemplate(
        "Slack notifications stopped",
        "Slack alerts from your platform stopped firing yesterday. "
        "Other integrations (PagerDuty, email) still work. Tested with "
        "a fresh webhook URL, same result.",
        "HIGH", "open",
    ),
    TicketTemplate(
        "Renewal - clarify auto-renew terms",
        "Our renewal is coming up. Can someone clarify whether the contract "
        "auto-renews and what notice we need to give to opt out? "
        "Procurement is asking.",
        "MEDIUM", "open",
    ),
    TicketTemplate(
        "Dashboards loading slowly",
        "Our main usage dashboard takes 25-40s to load this week. Last "
        "month it was instant. Are you having a regional outage?",
        "MEDIUM", "closed",
    ),
    TicketTemplate(
        "Need SOC 2 report for security review",
        "Our InfoSec team needs the latest SOC 2 Type 2 report. Can you "
        "share via secure link? NDA already signed.",
        "LOW", "closed",
    ),
    TicketTemplate(
        "Webhook events arriving out of order",
        "We're seeing webhook events arriving out of chronological order "
        "in our system. The event timestamps are correct but the delivery "
        "order is shuffled.",
        "MEDIUM", "open",
    ),
    TicketTemplate(
        "User can't see admin panel",
        "Newly invited team member confirmed their email but can't see "
        "the admin section. They should have admin role per the invite.",
        "MEDIUM", "closed",
    ),
    TicketTemplate(
        "Bug: date filter off by one day",
        "When I filter the activity log by 'last 7 days' it includes today "
        "and 8 days back instead of 7. Reproducible.",
        "LOW", "closed",
    ),
    TicketTemplate(
        "Help routing webhook to multiple endpoints",
        "We want the same webhook to fan out to two endpoints. Is this "
        "natively supported or do we need a middleware?",
        "LOW", "open",
    ),
    TicketTemplate(
        "Question about data retention policy",
        "What's the retention period for deleted records? We're working "
        "through a GDPR review and need a precise number.",
        "MEDIUM", "open",
    ),
    TicketTemplate(
        "Export to S3 failing with auth error",
        "Our scheduled export to s3://… now fails with an AccessDenied. "
        "Our IAM role and bucket policy haven't changed. Started ~Friday.",
        "HIGH", "open",
    ),
    TicketTemplate(
        "Need to update the billing contact email",
        "Please update billing contact from ap@old to ap@new - we changed "
        "our finance email forwarder.",
        "LOW", "closed",
    ),
    TicketTemplate(
        "Setup help for new region deployment",
        "We're expanding to EU and need to deploy a second tenant in "
        "Frankfurt. Can you walk us through data residency setup?",
        "MEDIUM", "open",
    ),
    TicketTemplate(
        "API key rotation procedure",
        "Quarterly security review - we need to rotate our API keys. "
        "What's the recommended procedure for zero-downtime rotation?",
        "LOW", "closed",
    ),
    TicketTemplate(
        "Custom field type not appearing in API",
        "We added a custom field via the UI but it's not showing up in "
        "GET /v3/objects responses. Cache issue?",
        "MEDIUM", "closed",
    ),
    TicketTemplate(
        "Looking for white-glove migration assistance",
        "We're migrating from a competitor and have ~50k records. Do you "
        "offer migration assistance or do we need a partner?",
        "MEDIUM", "open",
    ),
]


def _build_ticket_plan() -> list[tuple[str, str, str, str, str, datetime]]:
    """Build the ticket plan.

    Returns list of (company_slug, subject, content, stage_id, priority, created_at).
    Targets ~100 tickets spread across companies.
    """
    plan: list[tuple[str, str, str, str, str, datetime]] = []
    now = datetime(2026, 5, 27, tzinfo=timezone.utc)

    # ---- W2 signal tickets on northwind-logi ----
    plan.append((
        "northwind-logi",
        "Paid for Enterprise upgrade but still showing Standard tier",
        "We paid the $9k upgrade fee on May 12 but our account is still "
        "on the Standard plan. URGENT - we have a board demo tomorrow. "
        "Stripe receipt shows charge succeeded. Need this fixed today.",
        "1",  # New (open)
        "HIGH",
        datetime(2026, 5, 22, 14, 32, tzinfo=timezone.utc),
    ))
    plan.append((
        "northwind-logi",
        "Question about route-optimization endpoint usage",
        "Our team is using the route-optimization endpoint and seeing "
        "intermittent 5xx errors on payloads over 200 stops. Is there "
        "a known limit? We'd like to understand best practices.",
        "4",  # Closed
        "MEDIUM",
        datetime(2025, 11, 14, 9, 11, tzinfo=timezone.utc),
    ))

    # ---- W3 signal tickets on mockingbird-media ----
    plan.append((
        "mockingbird-media",
        "Why are we getting two bills?",
        "We see one charge from your legacy entity ($5,500) and one from "
        "your new Stripe entity ($5,500). We were told the legacy was "
        "being retired in March. Please refund and consolidate.",
        "1",  # New (open)
        "HIGH",
        datetime(2026, 5, 18, 11, 4, tzinfo=timezone.utc),
    ))
    plan.append((
        "mockingbird-media",
        "Heads-up on March billing migration",
        "Your CS team mentioned the legacy billing entity is being retired "
        "in March 2026 and we'll be migrated to Stripe. Just confirming "
        "our subscription IDs will remain consistent and no action needed "
        "on our side?",
        "4",  # Closed
        "MEDIUM",
        datetime(2026, 2, 8, 15, 47, tzinfo=timezone.utc),
    ))

    # ---- Tickets giving W1 (Acme Genomics) realistic context ----
    plan.append((
        "acme-genomics",
        "Can you confirm data export options?",
        "Hi, we're reviewing our data ownership story for an internal "
        "audit. Can you point us to the data export options? We just "
        "want to know what's available - not cancelling.",
        "4",  # Closed
        "MEDIUM",
        datetime(2026, 3, 4, 10, 22, tzinfo=timezone.utc),
    ))
    plan.append((
        "acme-genomics",
        "Disputed charge on April invoice - please review",
        "Filed a chargeback on the April invoice. We thought our "
        "subscription was paused. Can someone reach out so we can "
        "reconcile?",
        "4",  # Closed
        "HIGH",
        datetime(2026, 4, 11, 16, 8, tzinfo=timezone.utc),
    ))

    # ---- General realistic tickets across all companies ----
    # Spread ~85 more across the 35 companies.
    # Track per-(company, subject) to avoid duplicates in the same run.
    used: set[tuple[str, str]] = set()
    for slug, subj, *_ in plan:
        used.add((slug, subj))

    for c in COMPANIES:
        # Decide a count for this company.
        if c.arr_usd >= 100_000:
            n = RNG.randint(3, 5)
        elif c.arr_usd >= 40_000:
            n = RNG.randint(2, 4)
        else:
            n = RNG.randint(1, 3)
        # Workflow targets already have hand-crafted tickets; give them
        # 1-2 extra generic ones too.
        if c.slug in {"acme-genomics", "northwind-logi", "mockingbird-media"}:
            n = RNG.randint(1, 2)

        added = 0
        attempts = 0
        while added < n and attempts < n * 5:
            attempts += 1
            tpl = RNG.choice(TICKET_TEMPLATES)
            subj = tpl.subject_template
            # Diversify subject lines so they're unique across companies.
            # Always include company name to keep the subject unique.
            subj = f"[{c.name}] {subj}"
            if (c.slug, subj) in used:
                continue
            used.add((c.slug, subj))

            content = tpl.content_template
            # Stage selection: weighted by template's typical state.
            roll = RNG.random()
            if tpl.typical_stage == "closed":
                if roll < 0.7:
                    stage = "4"
                elif roll < 0.85:
                    stage = "3"
                else:
                    stage = "1"
            else:
                if roll < 0.45:
                    stage = "1"
                elif roll < 0.7:
                    stage = "3"
                elif roll < 0.85:
                    stage = "2"
                else:
                    stage = "4"
            # Priority variation.
            priority = tpl.typical_priority
            if RNG.random() < 0.15:
                priority = RNG.choice(TICKET_PRIORITIES)

            # Created date: spread across past 18 months.
            days_ago = RNG.randint(7, 540)
            ts = now - timedelta(days=days_ago, hours=RNG.randint(0, 23),
                                 minutes=RNG.randint(0, 59))
            plan.append((c.slug, subj, content, stage, priority, ts))
            added += 1

    return plan


# ──────────────────────────────────────────────────────────────────────
# Cleanup pass - HubSpot auto-creates "shadow" companies from every new
# contact email's domain. Since our contacts use ``<slug>.example.com``
# emails (.test is rejected for emails), each first contact create
# triggers a phantom Company record with that domain and a null name.
# We periodically scrub those so the company count stays at 35.
# ──────────────────────────────────────────────────────────────────────


def cleanup_phantom_companies(client: httpx.Client) -> tuple[int, int]:
    """Delete companies that look like phantoms auto-created from contact
    domains.

    A phantom company has:
      - domain ending in ``.example.com``
      - a null/empty ``name``

    Real companies in our seed set have a ``.test`` domain *and* a name,
    so this filter is precise.

    Returns (found, deleted).
    """
    found = 0
    deleted = 0
    after: str | None = None
    while True:
        body: dict = {
            "filterGroups": [{"filters": [
                {"propertyName": "domain", "operator": "CONTAINS_TOKEN", "value": "example.com"},
            ]}],
            "properties": ["name", "domain"],
            "limit": 100,
        }
        if after:
            body["after"] = after
        r = _request(
            client, "POST", "/crm/v3/objects/companies/search", json=body,
        )
        if r.status_code != 200:
            break
        data = r.json()
        for rec in data.get("results", []):
            props = rec.get("properties", {})
            name = props.get("name") or ""
            dom = props.get("domain") or ""
            if dom.endswith(".example.com") and not name.strip():
                found += 1
                rid = rec["id"]
                dr = _request(
                    client, "DELETE",
                    f"/crm/v3/objects/companies/{rid}",
                )
                if dr.status_code in (200, 204):
                    deleted += 1
        paging = data.get("paging") or {}
        after = paging.get("next", {}).get("after")
        if not after:
            break
    return found, deleted


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    counts = {
        "companies_created": 0, "companies_updated": 0, "companies_error": 0,
        "contacts_created": 0, "contacts_updated": 0, "contacts_error": 0,
        "deals_created": 0, "deals_updated": 0, "deals_error": 0,
        "tickets_created": 0, "tickets_updated": 0, "tickets_error": 0,
    }
    errors: list[str] = []
    company_ids: dict[str, str] = {}  # slug → hubspot id

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # ── 1. Companies ────────────────────────────────────────────
        print(f"Seeding {len(COMPANIES)} companies…")
        for c in COMPANIES:
            cid, action = upsert_company(client, c)
            if cid:
                company_ids[c.slug] = cid
            if "created" in action:
                counts["companies_created"] += 1
            elif "updated" in action:
                counts["companies_updated"] += 1
            else:
                counts["companies_error"] += 1
                errors.append(f"company {c.slug}: {action}")
            print(f"  [{action:>22}] {c.slug:25s} → {cid}")
            time.sleep(REQ_SLEEP)

        # ── 2. Contacts ──────────────────────────────────────────────
        contact_plan: list[tuple[Company, dict]] = []
        for c in COMPANIES:
            for ct in _build_contact_plan(c):
                contact_plan.append((c, ct))
        print(f"\nSeeding {len(contact_plan)} contacts across {len(COMPANIES)} companies…")
        for c, ct in contact_plan:
            cid = company_ids.get(c.slug)
            if not cid:
                errors.append(f"contact skipped (no company id): {c.slug}/{ct['email']}")
                counts["contacts_error"] += 1
                continue
            ct_id, action = upsert_contact(
                client,
                email=ct["email"],
                firstname=ct["firstname"],
                lastname=ct["lastname"],
                company_name=c.name,
                company_id=cid,
                jobtitle=ct["jobtitle"],
            )
            if "created" in action:
                counts["contacts_created"] += 1
            elif "updated" in action:
                counts["contacts_updated"] += 1
            else:
                counts["contacts_error"] += 1
                errors.append(f"contact {ct['email']}: {action}")
            print(f"  [{action:>22}] {ct['email']:45s}  ({ct['role']:>8s}) → {ct_id}")
            time.sleep(REQ_SLEEP)

        # ── 3. Deals ─────────────────────────────────────────────────
        deal_plan = _build_deal_plan()
        print(f"\nSeeding {len(deal_plan)} deals…")
        for spec in deal_plan:
            cid = company_ids.get(spec.company_slug)
            if not cid:
                errors.append(f"deal skipped (no company id): {spec.company_slug}")
                counts["deals_error"] += 1
                continue
            d_id, action = upsert_deal(
                client,
                name=spec.name,
                amount=spec.amount,
                close_date=spec.close_date,
                stage=spec.stage,
                company_id=cid,
                description=spec.description or None,
            )
            if "created" in action:
                counts["deals_created"] += 1
            elif "updated" in action:
                counts["deals_updated"] += 1
            else:
                counts["deals_error"] += 1
                errors.append(f"deal {spec.name}: {action}")
            print(f"  [{action:>22}] {spec.name:55s} ${spec.amount:>7d}  {spec.stage}")
            time.sleep(REQ_SLEEP)

        # ── 4. Tickets ───────────────────────────────────────────────
        ticket_plan = _build_ticket_plan()
        print(f"\nSeeding {len(ticket_plan)} tickets…")
        for slug, subj, content, stage, priority, ts in ticket_plan:
            cid = company_ids.get(slug)
            if not cid:
                errors.append(f"ticket skipped (no company id): {slug}")
                counts["tickets_error"] += 1
                continue
            t_id, action = upsert_ticket(
                client,
                subject=subj,
                content=content,
                stage=stage,
                priority=priority,
                company_id=cid,
            )
            if "created" in action:
                counts["tickets_created"] += 1
            elif "updated" in action:
                counts["tickets_updated"] += 1
            else:
                counts["tickets_error"] += 1
                errors.append(f"ticket {subj!r}: {action}")
            print(f"  [{action:>22}] {slug:22s} stage={stage} pri={priority:6s} → {t_id}")
            time.sleep(REQ_SLEEP)

        # ── 5. Scrub phantom companies auto-created from contact emails
        print("\nScrubbing phantom .example.com companies…")
        found, deleted = cleanup_phantom_companies(client)
        print(f"  phantom companies found={found}  deleted={deleted}")

        # ── 6. Workflow signal verification ──────────────────────────
        print("\n" + "─" * 70)
        print("Workflow signal verification")
        print("─" * 70)
        w_ids = verify_workflows(client, company_ids)

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("SUMMARY")
    print("═" * 70)
    total_companies = counts["companies_created"] + counts["companies_updated"]
    total_contacts = counts["contacts_created"] + counts["contacts_updated"]
    total_deals = counts["deals_created"] + counts["deals_updated"]
    total_tickets = counts["tickets_created"] + counts["tickets_updated"]
    print(
        f"Companies: total={total_companies:3d}  "
        f"created={counts['companies_created']:3d}  "
        f"updated={counts['companies_updated']:3d}  "
        f"errors={counts['companies_error']:3d}"
    )
    print(
        f"Contacts : total={total_contacts:3d}  "
        f"created={counts['contacts_created']:3d}  "
        f"updated={counts['contacts_updated']:3d}  "
        f"errors={counts['contacts_error']:3d}"
    )
    print(
        f"Deals    : total={total_deals:3d}  "
        f"created={counts['deals_created']:3d}  "
        f"updated={counts['deals_updated']:3d}  "
        f"errors={counts['deals_error']:3d}"
    )
    print(
        f"Tickets  : total={total_tickets:3d}  "
        f"created={counts['tickets_created']:3d}  "
        f"updated={counts['tickets_updated']:3d}  "
        f"errors={counts['tickets_error']:3d}"
    )
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:25]:
            print(f"  - {e}")
        if len(errors) > 25:
            print(f"  …and {len(errors) - 25} more")

    print("\nWorkflow target HubSpot IDs:")
    print(f"  W1 acme-genomics       company={company_ids.get('acme-genomics')}")
    print(f"  W2 northwind-logi      company={company_ids.get('northwind-logi')}")
    print(f"     deal={w_ids.get('w2_deal_id')}")
    print(f"     ticket={w_ids.get('w2_ticket_id')}")
    print(f"  W3 mockingbird-media   company={company_ids.get('mockingbird-media')}")
    print(f"     deal={w_ids.get('w3_deal_id')}")
    print(f"     ticket={w_ids.get('w3_ticket_id')}")

    return 0 if not errors else 1


def verify_workflows(
    client: httpx.Client, company_ids: dict[str, str]
) -> dict[str, str | None]:
    """Confirm W1/W2/W3 signals are baked into HubSpot.

    Returns IDs for W2/W3 deals + tickets for the caller to print.
    """
    out: dict[str, str | None] = {}

    # ---- W1 - Acme Genomics ----
    w1_id = company_ids.get("acme-genomics")
    w1_ok = False
    if w1_id:
        r = _request(
            client, "GET", f"/crm/v3/objects/companies/{w1_id}",
            params={"properties": "description,industry,annualrevenue,name"},
        )
        if r.status_code == 200:
            props = r.json().get("properties", {})
            desc = (props.get("description") or "").lower()
            w1_ok = (
                ("multiple disputes filed in 2025-2026" in desc
                 and "continued active product usage" in desc
                 and "csm flagged for review" in desc)
                or (
                    "data export" in desc
                    and ("chargeback" in desc or "dispute" in desc)
                    and ("no formal" in desc or "no formal cancel" in desc)
                )
            )
            print(
                f"W1 acme-genomics       company={w1_id}  "
                f"industry={props.get('industry')}  "
                f"arr={props.get('annualrevenue')}  signal={w1_ok}"
            )
    if not w1_ok:
        print(f"W1 acme-genomics       company={w1_id}  signal=NO")

    # ---- W2 - Northwind Logistics ----
    w2_id = company_ids.get("northwind-logi")
    w2_deal_id = find_deal_by_name(client, "Northwind - Enterprise Upgrade Q2 2026")
    w2_ticket_id = find_ticket_by_subject(
        client,
        "Paid for Enterprise upgrade but still showing Standard tier",
    )
    out["w2_deal_id"] = w2_deal_id
    out["w2_ticket_id"] = w2_ticket_id
    w2_deal_ok = False
    if w2_deal_id:
        r = _request(
            client, "GET", f"/crm/v3/objects/deals/{w2_deal_id}",
            params={"properties": "dealname,amount,dealstage,closedate"},
        )
        if r.status_code == 200:
            props = r.json().get("properties", {})
            w2_deal_ok = (
                props.get("dealstage") == "closedwon"
                and props.get("amount") in ("9000", "9000.00")
                and (props.get("closedate") or "").startswith("2026-05-12")
            )
    w2_ticket_ok = bool(w2_ticket_id)
    print(
        f"W2 northwind-logi      company={w2_id}  deal={w2_deal_id}  "
        f"ticket={w2_ticket_id}  deal_signal={w2_deal_ok}  "
        f"ticket_signal={w2_ticket_ok}"
    )

    # ---- W3 - Mockingbird Media ----
    w3_id = company_ids.get("mockingbird-media")
    w3_deal_id = find_deal_by_name(client, "Mockingbird - Migration Cutover")
    w3_ticket_id = find_ticket_by_subject(client, "Why are we getting two bills?")
    out["w3_deal_id"] = w3_deal_id
    out["w3_ticket_id"] = w3_ticket_id
    w3_desc_ok = False
    w3_deal_ok = False
    if w3_id:
        r = _request(
            client, "GET", f"/crm/v3/objects/companies/{w3_id}",
            params={"properties": "description"},
        )
        if r.status_code == 200:
            desc = (r.json().get("properties", {}).get("description") or "").lower()
            w3_desc_ok = "migrated" in desc and "stripe" in desc and "legacy" in desc
    if w3_deal_id:
        r = _request(
            client, "GET", f"/crm/v3/objects/deals/{w3_deal_id}",
            params={"properties": "dealname,amount,dealstage,closedate"},
        )
        if r.status_code == 200:
            props = r.json().get("properties", {})
            w3_deal_ok = (
                props.get("dealstage") == "closedwon"
                and props.get("amount") in ("5500", "5500.00")
                and (props.get("closedate") or "").startswith("2026-03-15")
            )
    w3_ticket_ok = bool(w3_ticket_id)
    print(
        f"W3 mockingbird-media   company={w3_id}  deal={w3_deal_id}  "
        f"ticket={w3_ticket_id}  desc_signal={w3_desc_ok}  "
        f"deal_signal={w3_deal_ok}  ticket_signal={w3_ticket_ok}"
    )

    return out


if __name__ == "__main__":
    sys.exit(main())
