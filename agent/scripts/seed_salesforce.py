"""Seed Salesforce Dev Org with the 35-company directory + matching
contacts, opportunities, and cases.

Drives the Manthan v2 billing-dispute investigation agent. Reads from
seed_world.py for canonical company identity so cross-source JOINs stay
consistent.

Idempotent - re-runs check existence by Name (Accounts), Email (Contacts),
Name+AccountId (Opportunities), and Subject+AccountId (Cases) before
creating.

The W7 anchor sits on Nexus Data's Opportunity description: a verbal
pricing-review promise the customer is at-risk on. The agent must surface
that from `salesforce.opportunities.description`.

We DO NOT touch the dev-org sample accounts (Edge Communications,
Burlington Textiles, Pyramid Construction, Dickenson plc, Grand Hotels &
Resorts, etc.) - they sit alongside our 35 as noise.

Run:
    .venv/bin/python scripts/refresh_salesforce_token.py
    .venv/bin/python scripts/seed_salesforce.py
"""

from __future__ import annotations

import hashlib
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Make seed_world importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from seed_world import COMPANIES, Company  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

API_URL = os.getenv("SALESFORCE_API_URL")
TOKEN = os.getenv("SALESFORCE_ACCESS_TOKEN")
if not API_URL or not TOKEN:
    sys.exit(
        "ERROR: SALESFORCE_API_URL and SALESFORCE_ACCESS_TOKEN must be set in .env. "
        "Run scripts/refresh_salesforce_token.py first."
    )

API_VERSION = "v59.0"
BASE = f"{API_URL.rstrip('/')}/services/data/{API_VERSION}"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Pace ~5-8 req/sec - well under Dev Edition's 5k/day cap.
REQ_SLEEP = 0.15
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Deterministic RNG so re-runs pick the same noise pattern.
RNG = random.Random(20260527)

# Accounts created by the dev-org template - never touch these.
DEV_ORG_SAMPLE_ACCOUNTS = {
    "Edge Communications",
    "Burlington Textiles Corp of America",
    "Pyramid Construction Inc.",
    "Dickenson plc",
    "Grand Hotels & Resorts Ltd",
    "United Oil & Gas Corp.",
    "United Oil & Gas, Singapore",
    "United Oil & Gas, UK",
    "Express Logistics and Transport",
    "University of Arizona",
    "GenePoint",
    "sForce",
    "Sample Account for Entitlements",
}

# W-target slugs that get the Stripe email as a 3rd contact (mirror cross-
# system identity drift the agent must JOIN on).
W_TARGET_SLUGS = {
    "acme-genomics",
    "northwind-logi",
    "mockingbird-media",
    "helix-bio",
    "summit-payments",
    "cascade-cloud",
    "nexus-data",
}


# ──────────────────────────────────────────────────────────────────────
# Industry mapping - seed_world.py industries → Salesforce picklist values
# ──────────────────────────────────────────────────────────────────────

# seed_world.py country strings → Salesforce BillingCountry labels.
# The Dev Org has state/country picklists enabled, which rejects "USA" /
# "UK" - the BillingCountryCode picklist's labels are full names ("United
# States", "United Kingdom"). Anything not listed here falls through
# unchanged (most are already full names in seed_world.py).
COUNTRY_MAP: dict[str, str] = {
    "USA": "United States",
    "US": "United States",
    "UK": "United Kingdom",
}


def _billing_country(country: str) -> str:
    return COUNTRY_MAP.get(country, country)


INDUSTRY_MAP: dict[str, str] = {
    "genomics": "Biotechnology",
    "logistics": "Transportation",
    "media": "Media",
    "consulting": "Consulting",
    "biotech": "Biotechnology",
    "food": "Food & Beverage",
    "software": "Technology",
    "manufacturing": "Manufacturing",
    "ai-infra": "Technology",
    "mining": "Manufacturing",
    "energy": "Energy",
    "hospitality": "Hospitality",
    "cloud-infra": "Technology",
    "ai-research": "Technology",
    "finance": "Finance",
    "fintech": "Finance",
    "data-platform": "Technology",
    "security": "Technology",
    "research": "Biotechnology",
    "healthcare": "Healthcare",
    "venture-capital": "Finance",
    "real-estate": "Construction",
    "design-agency": "Entertainment",
}


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _slug_hash(slug: str, salt: str = "") -> int:
    """Stable 32-bit hash from slug + salt for deterministic randomness."""
    raw = f"{slug}|{salt}".encode()
    return int(hashlib.sha1(raw).hexdigest()[:8], 16)


def _employees_for(slug: str) -> int:
    """Pick a plausible employee count from a slug-stable hash, 20–500."""
    return 20 + (_slug_hash(slug, "employees") % 481)


def _fake_phone(slug: str) -> str:
    """Generate a deterministic synthetic +1 phone number for the seeded customer."""
    h = _slug_hash(slug, "phone")
    area = 200 + (h % 700)            # 200-899
    mid = 200 + ((h >> 8) % 800)      # 200-999
    last = (h >> 16) % 10000          # 0000-9999
    return f"+1 {area} {mid:03d} {last:04d}"


def _arr_tier(arr_usd: int) -> str:
    if arr_usd >= 100_000:
        return "large"
    if arr_usd >= 40_000:
        return "mid"
    return "small"


def _account_description(c: Company) -> str:
    """Plaintext description with structured tags + narrative.

    The agent text-searches these, so keep the tag block stable.
    """
    health = c.health.upper()
    tier = _arr_tier(c.arr_usd)
    narrative = (c.notes or "").strip()
    if not narrative:
        narrative = (
            f"{c.name} is a {c.industry} customer based in {c.country}, "
            f"signed up in {c.signup_year} on the {c.plan} plan. Account is "
            f"currently in {health.lower()} health with no escalations on file."
        )
    return (
        f"[company_slug={c.slug}] [health={health}] [arr_tier={tier}]\n"
        f"{narrative}"
    )


def _close_date(slug: str) -> str:
    """Deterministic close date in April–early May 2026."""
    # 35 possible days: Apr 1 → May 5
    day_index = _slug_hash(slug, "close") % 35
    if day_index < 30:
        return f"2026-04-{day_index + 1:02d}"
    return f"2026-05-{day_index - 29:02d}"


# ──────────────────────────────────────────────────────────────────────
# Name pools (deterministic per (slug, role))
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


def _pick_name(slug: str, role: str) -> tuple[str, str]:
    """Deterministic name picker keyed by slug + role."""
    seed = _slug_hash(slug, f"name:{role}")
    r = random.Random(seed)
    return r.choice(FIRST_NAMES), r.choice(LAST_NAMES)


# AE names for opportunity descriptions.
AE_NAMES = [
    "Sam Reyes", "Lina Park", "Devon Wright", "Maya Patel",
    "Theo Brennan", "Jules Okafor", "Riley Chen", "Casey Marquez",
]


def _ae_name(slug: str) -> str:
    if slug == "nexus-data":
        return "Jamie Park"  # W7 anchor names this AE
    return AE_NAMES[_slug_hash(slug, "ae") % len(AE_NAMES)]


# ──────────────────────────────────────────────────────────────────────
# HTTP wrapper - retries on 429/5xx, refreshes auth on 401
# ──────────────────────────────────────────────────────────────────────


class AuthRefreshError(RuntimeError):
    pass


def _refresh_token_inline() -> str:
    """Try to refresh via the sibling script, return the new token."""
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "refresh_salesforce_token.py")],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise AuthRefreshError(
            f"refresh_salesforce_token.py failed: {proc.stderr.strip()}"
        )
    # Reload .env to pick up the new token.
    load_dotenv(ENV_PATH, override=True)
    new_token = os.getenv("SALESFORCE_ACCESS_TOKEN")
    if not new_token:
        raise AuthRefreshError("SALESFORCE_ACCESS_TOKEN missing after refresh")
    return new_token


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: dict | list | None = None,
    params: dict | None = None,
    retries: int = 4,
) -> httpx.Response:
    """HTTP request with throttle, retry, and one-shot token refresh."""
    url = path if path.startswith("http") else f"{BASE}{path}"
    refreshed_once = False
    last: httpx.Response | None = None
    for attempt in range(retries):
        r = client.request(method, url, json=json, params=params)
        last = r
        if r.status_code == 401 and not refreshed_once:
            # Token expired mid-run - refresh once and retry.
            try:
                new_token = _refresh_token_inline()
            except AuthRefreshError as e:
                print(f"  auth refresh failed: {e}")
                return r
            client.headers["Authorization"] = f"Bearer {new_token}"
            refreshed_once = True
            continue
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", "1.0"))
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        return r
    return last  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────
# SOQL helpers
# ──────────────────────────────────────────────────────────────────────


def _soql_escape(s: str) -> str:
    """Escape single quotes + backslashes for SOQL literals."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _query(client: httpx.Client, soql: str) -> list[dict]:
    """Run a SOQL query and return records list (empty on failure)."""
    params = {"q": soql}
    r = _request(client, "GET", "/query", params=params)
    if r.status_code != 200:
        print(f"  query fail: {r.status_code} {r.text[:200]}  soql={soql[:100]}")
        return []
    return r.json().get("records", [])


# ──────────────────────────────────────────────────────────────────────
# Lookups
# ──────────────────────────────────────────────────────────────────────


def find_account_by_name(client: httpx.Client, name: str) -> str | None:
    soql = f"SELECT Id FROM Account WHERE Name = '{_soql_escape(name)}' LIMIT 1"
    recs = _query(client, soql)
    return recs[0]["Id"] if recs else None


def find_contact_by_email(client: httpx.Client, email: str) -> str | None:
    soql = f"SELECT Id FROM Contact WHERE Email = '{_soql_escape(email)}' LIMIT 1"
    recs = _query(client, soql)
    return recs[0]["Id"] if recs else None


def find_opportunity_by_name_account(
    client: httpx.Client, name: str, account_id: str,
) -> str | None:
    soql = (
        "SELECT Id FROM Opportunity "
        f"WHERE Name = '{_soql_escape(name)}' "
        f"AND AccountId = '{account_id}' LIMIT 1"
    )
    recs = _query(client, soql)
    return recs[0]["Id"] if recs else None


def find_case_by_subject_account(
    client: httpx.Client, subject: str, account_id: str,
) -> str | None:
    soql = (
        "SELECT Id FROM Case "
        f"WHERE Subject = '{_soql_escape(subject)}' "
        f"AND AccountId = '{account_id}' LIMIT 1"
    )
    recs = _query(client, soql)
    return recs[0]["Id"] if recs else None


# ──────────────────────────────────────────────────────────────────────
# Upserts
# ──────────────────────────────────────────────────────────────────────


def upsert_account(client: httpx.Client, c: Company) -> tuple[str | None, str]:
    if c.name in DEV_ORG_SAMPLE_ACCOUNTS:
        return None, "skipped (dev sample)"

    fields: dict[str, object] = {
        "Name": c.name,
        "Type": "Customer - Direct",
        "AnnualRevenue": c.arr_usd,
        "NumberOfEmployees": _employees_for(c.slug),
        "Phone": _fake_phone(c.slug),
        "Website": f"https://{c.slug}.test",
        "BillingCountry": _billing_country(c.country),
        "Description": _account_description(c),
    }
    industry = INDUSTRY_MAP.get(c.industry)
    if industry:
        fields["Industry"] = industry

    existing_id = find_account_by_name(client, c.name)
    if existing_id:
        r = _request(
            client, "PATCH",
            f"/sobjects/Account/{existing_id}",
            json=fields,
        )
        if r.status_code in (200, 204):
            return existing_id, "updated"
        print(f"  account update fail {c.slug}: {r.status_code} {r.text[:200]}")
        return existing_id, "error"

    r = _request(client, "POST", "/sobjects/Account", json=fields)
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    print(f"  account create fail {c.slug}: {r.status_code} {r.text[:200]}")
    return None, "error"


def upsert_contact(
    client: httpx.Client,
    *,
    account_id: str,
    email: str,
    first_name: str,
    last_name: str,
    title: str,
) -> tuple[str | None, str]:
    existing_id = find_contact_by_email(client, email)
    fields: dict[str, object] = {
        "AccountId": account_id,
        "Email": email,
        "FirstName": first_name,
        "LastName": last_name,
        "Title": title,
    }
    if existing_id:
        r = _request(
            client, "PATCH",
            f"/sobjects/Contact/{existing_id}",
            json=fields,
        )
        if r.status_code in (200, 204):
            return existing_id, "updated"
        print(f"  contact update fail {email}: {r.status_code} {r.text[:200]}")
        return existing_id, "error"

    r = _request(client, "POST", "/sobjects/Contact", json=fields)
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    print(f"  contact create fail {email}: {r.status_code} {r.text[:200]}")
    return None, "error"


def upsert_opportunity(
    client: httpx.Client,
    *,
    account_id: str,
    name: str,
    amount: int,
    close_date: str,
    description: str,
    opp_type: str = "Existing Customer - Upgrade",
) -> tuple[str | None, str]:
    fields: dict[str, object] = {
        "Name": name,
        "AccountId": account_id,
        "StageName": "Closed Won",
        "CloseDate": close_date,
        "Amount": amount,
        "Type": opp_type,
        "Description": description,
    }
    existing_id = find_opportunity_by_name_account(client, name, account_id)
    if existing_id:
        r = _request(
            client, "PATCH",
            f"/sobjects/Opportunity/{existing_id}",
            json=fields,
        )
        if r.status_code in (200, 204):
            return existing_id, "updated"
        print(f"  opp update fail {name!r}: {r.status_code} {r.text[:200]}")
        return existing_id, "error"

    r = _request(client, "POST", "/sobjects/Opportunity", json=fields)
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    print(f"  opp create fail {name!r}: {r.status_code} {r.text[:200]}")
    return None, "error"


def upsert_case(
    client: httpx.Client,
    *,
    account_id: str,
    subject: str,
    description: str,
    status: str,
    priority: str,
    origin: str,
) -> tuple[str | None, str]:
    fields: dict[str, object] = {
        "AccountId": account_id,
        "Subject": subject,
        "Description": description,
        "Status": status,
        "Priority": priority,
        "Origin": origin,
    }
    existing_id = find_case_by_subject_account(client, subject, account_id)
    if existing_id:
        r = _request(
            client, "PATCH",
            f"/sobjects/Case/{existing_id}",
            json=fields,
        )
        if r.status_code in (200, 204):
            return existing_id, "updated"
        print(f"  case update fail {subject!r}: {r.status_code} {r.text[:200]}")
        return existing_id, "error"

    r = _request(client, "POST", "/sobjects/Case", json=fields)
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    print(f"  case create fail {subject!r}: {r.status_code} {r.text[:200]}")
    return None, "error"


# ──────────────────────────────────────────────────────────────────────
# Per-company plans
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ContactPlan:
    role: str   # "finance" | "ops" | "stripe-mirror"
    email: str
    first_name: str
    last_name: str
    title: str


def _build_contact_plan(c: Company) -> list[ContactPlan]:
    plans: list[ContactPlan] = []

    # Finance lead - CFO
    cf_first, cf_last = _pick_name(c.slug, "finance")
    plans.append(ContactPlan(
        role="finance",
        email=f"cfo@{c.slug}.test",
        first_name=cf_first,
        last_name=cf_last,
        title="CFO",
    ))

    # Ops/Procurement lead
    op_first, op_last = _pick_name(c.slug, "ops")
    # Slug-stable choice between Director of Ops vs Procurement Lead
    title = (
        "Director of Operations"
        if _slug_hash(c.slug, "ops-title") % 2 == 0
        else "Procurement Lead"
    )
    plans.append(ContactPlan(
        role="ops",
        email=f"ops@{c.slug}.test",
        first_name=op_first,
        last_name=op_last,
        title=title,
    ))

    # For W-target accounts, mirror the Stripe email as a 3rd contact so
    # the agent can JOIN by email when given the Stripe-side trigger.
    if c.slug in W_TARGET_SLUGS:
        stripe_email = c.email.lower()
        if stripe_email != f"ops@{c.slug}.test":
            sm_first, sm_last = _pick_name(c.slug, "stripe-mirror")
            plans.append(ContactPlan(
                role="stripe-mirror",
                email=stripe_email,
                first_name=sm_first,
                last_name=sm_last,
                title="Billing Contact",
            ))

    return plans


# Industry-flavoured closed-case topics (subject, description).
CLOSED_CASE_TOPICS: dict[str, list[tuple[str, str]]] = {
    "genomics": [
        ("Q1 invoice clarification",
         "Customer asked us to walk through the Q1 2026 invoice line items - "
         "specifically the sample-processing overage. Resolved on a 20-min call."),
        ("Data export for internal audit",
         "Customer wanted to confirm we can export sequencing data in VCF + BAM "
         "for an internal audit. Pointed them at the export API and sent docs."),
    ],
    "logistics": [
        ("Route-optimization endpoint 5xx",
         "Customer reported intermittent 5xx on payloads with >200 stops. Backend "
         "team identified a serialization bug and patched it the same week."),
        ("Question on shipment-tracking webhook latency",
         "Customer asked about expected webhook latency for the shipment.tracking "
         "event. Sent SLA doc, no action required."),
    ],
    "media": [
        ("Bulk publish via API",
         "Customer wanted to publish 500+ posts in one batch. Walked them through "
         "the bulk endpoint and recommended pagination."),
        ("CMS migration question",
         "Customer asked whether our importer handles their existing CMS schema. "
         "Confirmed yes, sent example mapping file."),
    ],
    "consulting": [
        ("White-label branding setup",
         "Customer requested white-label branding for the customer portal. "
         "Walked them through the theme config."),
        ("Per-seat reporting export",
         "Customer asked for a per-seat utilization export. Pointed them at the "
         "report builder."),
    ],
    "biotech": [
        ("LIMS integration question",
         "Customer asked about integrating with their internal LIMS. Sent the "
         "integration partner list."),
        ("Data residency for EU subsidiary",
         "Customer asked whether EU subsidiary data can be pinned to Frankfurt. "
         "Confirmed yes via the multi-region toggle."),
    ],
    "food": [
        ("Recipe SKU sync issue",
         "Customer's recipe SKU sync hadn't pushed for 3 days. Found a stuck job "
         "queue, restarted, backfilled."),
        ("Allergen flag visibility",
         "Customer asked about surfacing allergen flags in the public storefront "
         "API. Confirmed available, sent example response."),
    ],
    "software": [
        ("SSO config question",
         "Customer wanted to enforce SSO across all users. Walked them through "
         "the IdP-initiated config."),
        ("API rate limit increase",
         "Customer requested a rate-limit bump from 100/s to 250/s for their "
         "nightly batch. Approved and applied."),
    ],
    "manufacturing": [
        ("Shop-floor terminal sync",
         "Customer's tablet-based shop-floor terminal stopped syncing inventory. "
         "Diagnosed a stale auth token, refreshed it."),
        ("Bulk barcode label export",
         "Customer needed 10k barcode labels exported as PDF. Walked them through "
         "the bulk export feature."),
    ],
    "ai-infra": [
        ("GPU inference quota increase",
         "Customer requested additional A100 inference quota. Approved a 2x bump "
         "for their burst load."),
        ("Model versioning question",
         "Customer asked about rolling forward and back across model versions. "
         "Sent the model-registry docs."),
    ],
    "mining": [
        ("Multi-site reporting question",
         "Customer asked how to roll up site-level metrics into a global view. "
         "Walked them through the dashboard builder."),
        ("Offline-first sync question",
         "Customer's remote site loses connectivity often. Confirmed our app "
         "queues writes offline and flushes on reconnect."),
    ],
    "energy": [
        ("Smart-meter feed connectivity",
         "Customer reported smart-meter ingest dropped for a 2-hour window. "
         "Confirmed it was an upstream provider outage, not us."),
        ("Carbon-reporting export",
         "Customer needed a CSV export aligned to GHG Protocol categories. "
         "Walked them through the export schema."),
    ],
    "hospitality": [
        ("PMS sync question",
         "Customer's PMS sync was lagging by ~5 minutes. Diagnosed as expected "
         "behavior given their event volume."),
        ("Localized invoice template",
         "Customer wanted an Italian-language invoice template. Walked them "
         "through the template editor."),
    ],
    "cloud-infra": [
        ("VPC peering question",
         "Customer wanted to peer their VPC with our managed control plane. "
         "Sent the network architecture doc."),
        ("Region failover drill",
         "Customer wanted to test region failover for compliance. Scheduled a "
         "joint failover drill window."),
    ],
    "ai-research": [
        ("Experiment-tracking API question",
         "Customer wanted to programmatically tag experiments. Pointed them at "
         "the experiment-tracker SDK."),
        ("GPU spot vs on-demand cost question",
         "Customer asked us to break down expected cost savings on spot. Sent a "
         "modelling worksheet."),
    ],
    "finance": [
        ("SOC 2 report request",
         "Customer's InfoSec team requested our latest SOC 2 Type II. Sent via "
         "secure portal."),
        ("Vendor risk questionnaire",
         "Customer sent a 200-question vendor risk assessment. Filled and "
         "returned within their SLA."),
    ],
    "fintech": [
        ("Reconciliation export question",
         "Customer asked for a reconciliation export that includes payout IDs. "
         "Walked them through the financial-report builder."),
        ("PCI scope reduction question",
         "Customer wanted to reduce their PCI scope. Confirmed our hosted fields "
         "fully tokenize and sent the SAQ-A guidance."),
    ],
    "data-platform": [
        ("Schema-change replay question",
         "Customer wanted to know how the platform replays schema changes for "
         "late-arriving data. Sent the CDC docs."),
        ("Query-cost budgeting question",
         "Customer asked about per-team query budgets. Walked them through "
         "workload management."),
    ],
    "security": [
        ("SIEM integration question",
         "Customer asked how to fan our audit log out to Splunk. Sent the "
         "webhook-to-HEC config."),
        ("Threat-feed customization",
         "Customer wanted to weight specific threat feeds higher. Walked them "
         "through the scoring config."),
    ],
    "research": [
        ("Dataset citation export",
         "Customer needed BibTeX exports for their published datasets. Walked "
         "them through the citation export."),
        ("Multi-author paper attribution",
         "Customer asked how to attribute multi-author papers in their bibliography. "
         "Sent the contributor-role guide."),
    ],
    "healthcare": [
        ("HIPAA BAA request",
         "Customer's compliance team requested a counter-signed BAA. Sent via "
         "DocuSign, returned within 24h."),
        ("Patient-data export question",
         "Customer asked for a HIPAA-compliant export of patient records. "
         "Walked them through the audit-logged export."),
    ],
    "venture-capital": [
        ("Portfolio dashboard customization",
         "Customer wanted to add a custom diversity-of-founders metric to their "
         "dashboard. Walked them through the metric builder."),
        ("LP reporting export",
         "Customer needed an LP-ready PDF export. Walked them through the "
         "branded report templates."),
    ],
    "real-estate": [
        ("Tenant-portal SSO question",
         "Customer wanted SSO for the tenant portal. Sent the OIDC config."),
        ("Lease abstraction export",
         "Customer asked for a CSV export of lease abstracts. Walked them "
         "through the abstraction report."),
    ],
    "design-agency": [
        ("Brand asset bulk import",
         "Customer wanted to bulk-import 5k brand assets. Walked them through "
         "the bulk uploader."),
        ("Project archival question",
         "Customer asked how to archive completed projects without losing them. "
         "Pointed at the archive feature."),
    ],
}


# Industry-flavoured open-case topics (~30% of accounts get one).
OPEN_CASE_TOPICS: dict[str, list[tuple[str, str]]] = {
    "genomics": [(
        "Inquiry: bulk sequencing batch pricing",
        "Customer asked whether bulk batches >500 samples qualify for tiered "
        "pricing. AE following up.",
    )],
    "logistics": [(
        "Add second region for EU fleet visibility",
        "Customer wants to add a Frankfurt region for their EU fleet tracking. "
        "Solutions team scoping.",
    )],
    "media": [(
        "Question: rights-management API roadmap",
        "Customer asked when fine-grained rights-management API will GA. "
        "Product confirmed Q3 2026.",
    )],
    "consulting": [(
        "Multi-tenant client portal request",
        "Customer wants to spin up isolated tenant workspaces per client. "
        "Awaiting requirements doc.",
    )],
    "biotech": [(
        "Compliance evidence package for ISO 27001",
        "Customer's auditors requested a fresh evidence package. Compliance "
        "team preparing.",
    )],
    "food": [(
        "Recipe-level cost roll-up feature request",
        "Customer wants ingredient-cost roll-up at the recipe level. Product "
        "evaluating.",
    )],
    "software": [(
        "SAML attribute mapping help",
        "Customer's IdP sends attributes in a non-standard shape. Solutions "
        "engineer working through the mapping.",
    )],
    "manufacturing": [(
        "Workorder API throttling question",
        "Customer is hitting throttling on the workorder API during shift "
        "changeover bursts. Backend reviewing burst-bucket sizing.",
    )],
    "ai-infra": [(
        "Reserved-capacity quote request",
        "Customer wants a 12-month reserved-capacity quote for H100s. Sales "
        "engineering scoping.",
    )],
    "mining": [(
        "Remote-site latency optimization",
        "Customer's outback sites see ~600ms latency. Networking reviewing "
        "edge-cache placement.",
    )],
    "energy": [(
        "Smart-grid integration scoping",
        "Customer wants to integrate with state-grid demand-response signals. "
        "Solutions engineering scoping.",
    )],
    "hospitality": [(
        "Channel-manager integration question",
        "Customer asked which channel managers we support natively. Pointed "
        "at our integration directory, awaiting choice.",
    )],
    "cloud-infra": [(
        "Cross-account IAM role help",
        "Customer needs help setting up a cross-account IAM role for their "
        "data team. SE on the call tomorrow.",
    )],
    "ai-research": [(
        "Custom evaluation harness request",
        "Customer wants to plug in their own evaluation harness for model "
        "candidates. Product evaluating.",
    )],
    "finance": [(
        "FX-conversion edge case",
        "Customer noticed a minor rounding difference on EUR→USD conversions. "
        "Finance reviewing.",
    )],
    "fintech": [(
        "Dispute-evidence webhook help",
        "Customer wants webhook fired when dispute evidence is submitted. "
        "Backend confirms event exists, just needs to enable.",
    )],
    "data-platform": [(
        "Slow materialization for wide table",
        "Customer's 400-column materialization is slow. Performance team "
        "looking into columnar pruning.",
    )],
    "security": [(
        "Custom detection rule deployment",
        "Customer wants to deploy 30 custom detection rules. SE preparing the "
        "ruleset import.",
    )],
    "research": [(
        "DOI minting feature request",
        "Customer wants to mint DOIs directly from the platform. Product "
        "evaluating partnership with DataCite.",
    )],
    "healthcare": [(
        "HL7 FHIR endpoint compatibility",
        "Customer asked whether our FHIR endpoints support their R5 use case. "
        "Solutions reviewing.",
    )],
    "venture-capital": [(
        "Quarterly LP report scheduling",
        "Customer wants reports auto-generated and emailed quarterly. "
        "Solutions reviewing.",
    )],
    "real-estate": [(
        "Multi-property roll-up reporting",
        "Customer wants a roll-up across 40 properties. Solutions scoping.",
    )],
    "design-agency": [(
        "Client-presentation export polish",
        "Customer wants a more polished client-presentation export. "
        "Design team reviewing.",
    )],
}


def _opportunity_description(c: Company) -> str:
    """Description for the renewal opportunity. W7 anchor on nexus-data."""
    if c.slug == "nexus-data":
        # Load-bearing W7 signal - surface from salesforce.opportunities.description
        return (
            "Renewal closed by AE Jamie Park. Customer renewed early based on "
            "verbal commit: \"We will conduct a pricing review by EOQ2 2026 "
            "and explore a 15% reduction if usage stays below 70% of "
            "provisioned capacity.\" This commit was made on the 2026-04-18 "
            "deal call but is NOT in the executed contract. Customer is "
            "at-risk if we don't honor.\n"
            "Internal flag: PRICING_REVIEW_PROMISED_BUT_NOT_IN_CONTRACT."
        )
    ae = _ae_name(c.slug)
    return f"Renewal closed by AE {ae}. Standard terms."


def _case_plan(c: Company) -> list[tuple[str, str, str, str, str]]:
    """Return list of (subject, description, status, priority, origin) tuples.

    Always at least one closed case. ~30% of accounts get an additional
    open case for noise.
    """
    plans: list[tuple[str, str, str, str, str]] = []

    closed_topics = CLOSED_CASE_TOPICS.get(c.industry, [
        ("Q1 invoice clarification",
         "Customer asked us to walk through Q1 invoice line items. Resolved on a call."),
        ("Account configuration walkthrough",
         "Customer requested a quick walkthrough of their workspace config. Done."),
    ])
    closed_idx = _slug_hash(c.slug, "closed-case") % len(closed_topics)
    subj, desc = closed_topics[closed_idx]
    closed_priority = "High" if _slug_hash(c.slug, "closed-pri") % 5 == 0 else "Medium"
    closed_origin = ["Email", "Phone", "Web"][_slug_hash(c.slug, "closed-origin") % 3]
    plans.append((subj, desc, "Closed", closed_priority, closed_origin))

    # ~30% get an additional open case.
    if _slug_hash(c.slug, "open-case") % 10 < 3:
        open_topics = OPEN_CASE_TOPICS.get(c.industry, [(
            "Generic follow-up - in progress",
            "Customer follow-up still in flight, awaiting their team.",
        )])
        open_idx = _slug_hash(c.slug, "open-case-idx") % len(open_topics)
        o_subj, o_desc = open_topics[open_idx]
        open_status = "New" if _slug_hash(c.slug, "open-status") % 2 == 0 else "Working"
        open_priority = "High" if _slug_hash(c.slug, "open-pri") % 5 == 0 else "Medium"
        open_origin = ["Email", "Phone", "Web"][_slug_hash(c.slug, "open-origin") % 3]
        plans.append((o_subj, o_desc, open_status, open_priority, open_origin))

    return plans


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    counts = {
        "accounts_created": 0, "accounts_updated": 0, "accounts_error": 0,
        "contacts_created": 0, "contacts_updated": 0, "contacts_error": 0,
        "opps_created": 0, "opps_updated": 0, "opps_error": 0,
        "cases_created": 0, "cases_updated": 0, "cases_error": 0,
    }
    errors: list[str] = []
    account_ids: dict[str, str] = {}
    nexus_opp_id: str | None = None

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # ── 1. Accounts ────────────────────────────────────────────────
        print(f"Seeding {len(COMPANIES)} accounts…")
        for c in COMPANIES:
            aid, action = upsert_account(client, c)
            if aid:
                account_ids[c.slug] = aid
            if "created" in action:
                counts["accounts_created"] += 1
            elif "updated" in action:
                counts["accounts_updated"] += 1
            elif "skipped" in action:
                pass
            else:
                counts["accounts_error"] += 1
                errors.append(f"account {c.slug}: {action}")
            print(f"  [{action:>22}] {c.slug:25s} → {aid}")
            time.sleep(REQ_SLEEP)

        # ── 2. Contacts ────────────────────────────────────────────────
        contact_plans: list[tuple[Company, ContactPlan]] = []
        for c in COMPANIES:
            for cp in _build_contact_plan(c):
                contact_plans.append((c, cp))
        print(f"\nSeeding {len(contact_plans)} contacts across {len(COMPANIES)} accounts…")
        for c, cp in contact_plans:
            aid = account_ids.get(c.slug)
            if not aid:
                errors.append(f"contact skipped (no account): {c.slug}/{cp.email}")
                counts["contacts_error"] += 1
                continue
            ct_id, action = upsert_contact(
                client,
                account_id=aid,
                email=cp.email,
                first_name=cp.first_name,
                last_name=cp.last_name,
                title=cp.title,
            )
            if "created" in action:
                counts["contacts_created"] += 1
            elif "updated" in action:
                counts["contacts_updated"] += 1
            else:
                counts["contacts_error"] += 1
                errors.append(f"contact {cp.email}: {action}")
            print(f"  [{action:>22}] {cp.email:45s}  ({cp.role:>14s}) → {ct_id}")
            time.sleep(REQ_SLEEP)

        # ── 3. Opportunities ───────────────────────────────────────────
        print(f"\nSeeding {len(COMPANIES)} renewal opportunities…")
        for c in COMPANIES:
            aid = account_ids.get(c.slug)
            if not aid:
                errors.append(f"opp skipped (no account): {c.slug}")
                counts["opps_error"] += 1
                continue
            opp_name = f"{c.name} - Y2 Renewal (May 2026)"
            opp_id, action = upsert_opportunity(
                client,
                account_id=aid,
                name=opp_name,
                amount=c.arr_usd,
                close_date=_close_date(c.slug),
                description=_opportunity_description(c),
            )
            if c.slug == "nexus-data":
                nexus_opp_id = opp_id
            if "created" in action:
                counts["opps_created"] += 1
            elif "updated" in action:
                counts["opps_updated"] += 1
            else:
                counts["opps_error"] += 1
                errors.append(f"opp {opp_name!r}: {action}")
            print(f"  [{action:>22}] {opp_name:55s} ${c.arr_usd:>7d} → {opp_id}")
            time.sleep(REQ_SLEEP)

        # ── 4. Cases ───────────────────────────────────────────────────
        case_plans: list[tuple[Company, tuple[str, str, str, str, str]]] = []
        for c in COMPANIES:
            for tpl in _case_plan(c):
                case_plans.append((c, tpl))
        print(f"\nSeeding {len(case_plans)} cases across {len(COMPANIES)} accounts…")
        for c, (subj, desc, status, priority, origin) in case_plans:
            aid = account_ids.get(c.slug)
            if not aid:
                errors.append(f"case skipped (no account): {c.slug}")
                counts["cases_error"] += 1
                continue
            ca_id, action = upsert_case(
                client,
                account_id=aid,
                subject=subj,
                description=desc,
                status=status,
                priority=priority,
                origin=origin,
            )
            if "created" in action:
                counts["cases_created"] += 1
            elif "updated" in action:
                counts["cases_updated"] += 1
            else:
                counts["cases_error"] += 1
                errors.append(f"case {subj!r}: {action}")
            print(f"  [{action:>22}] {c.slug:22s} {status:8s} pri={priority:6s} → {ca_id}")
            time.sleep(REQ_SLEEP)

        # ── 5. W7 anchor verification ──────────────────────────────────
        print("\n" + "─" * 70)
        print("W7 anchor verification (nexus-data opportunity description)")
        print("─" * 70)
        w7_ok = False
        if nexus_opp_id:
            r = _request(
                client, "GET",
                f"/sobjects/Opportunity/{nexus_opp_id}",
                params={"fields": "Id,Name,Amount,Description"},
            )
            if r.status_code == 200:
                payload = r.json()
                desc = payload.get("Description") or ""
                w7_ok = "PRICING_REVIEW_PROMISED_BUT_NOT_IN_CONTRACT" in desc
                print(f"  opportunity id : {nexus_opp_id}")
                print(f"  name           : {payload.get('Name')}")
                print(f"  amount         : {payload.get('Amount')}")
                print(f"  has W7 anchor  : {w7_ok}")
        else:
            print("  nexus-data opportunity id missing - W7 anchor cannot be verified")

        # ── 6. Account-count verification ──────────────────────────────
        all_records = _query(client, "SELECT COUNT(Id) total FROM Account")
        total_accounts = all_records[0].get("total") if all_records else None
        print(f"\nTotal accounts in org: {total_accounts}")

    # ── Summary ────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("SUMMARY")
    print("═" * 70)
    total_accounts_done = counts["accounts_created"] + counts["accounts_updated"]
    total_contacts_done = counts["contacts_created"] + counts["contacts_updated"]
    total_opps_done = counts["opps_created"] + counts["opps_updated"]
    total_cases_done = counts["cases_created"] + counts["cases_updated"]
    print(
        f"Accounts     : total={total_accounts_done:3d}  "
        f"created={counts['accounts_created']:3d}  "
        f"updated={counts['accounts_updated']:3d}  "
        f"errors={counts['accounts_error']:3d}"
    )
    print(
        f"Contacts     : total={total_contacts_done:3d}  "
        f"created={counts['contacts_created']:3d}  "
        f"updated={counts['contacts_updated']:3d}  "
        f"errors={counts['contacts_error']:3d}"
    )
    print(
        f"Opportunities: total={total_opps_done:3d}  "
        f"created={counts['opps_created']:3d}  "
        f"updated={counts['opps_updated']:3d}  "
        f"errors={counts['opps_error']:3d}"
    )
    print(
        f"Cases        : total={total_cases_done:3d}  "
        f"created={counts['cases_created']:3d}  "
        f"updated={counts['cases_updated']:3d}  "
        f"errors={counts['cases_error']:3d}"
    )
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:25]:
            print(f"  - {e}")
        if len(errors) > 25:
            print(f"  …and {len(errors) - 25} more")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
