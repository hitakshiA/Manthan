"""Seed Intercom with 80-120 contacts + 400-700 conversations across 35
companies. Drives the Manthan billing-dispute investigation agent.

Reads from seed_world.py for canonical company identity so cross-source
JOINs stay consistent. Bakes the three workflow signals into specific
conversations:

  W1 - Acme Genomics: 4-6 conversations from ops@acme-genomics.test
       across 2025-2026. Includes the "Data export options" thread in
       March 2026 (informational only - NOT a formal cancel), an API
       rate-limit question, a renewal question, onboarding follow-ups.
       Critically: NONE is a formal "please cancel my subscription"
       request.

  W2 - Northwind Logistics: 3-5 conversations from ar@northwind-logi.test.
       Includes the May 2026 "Paid for upgrade but still on Standard tier"
       escalation referencing the $9,000 Stripe receipt, plus earlier
       general-use threads.

  W3 - Mockingbird Media: 3-5 conversations from finance@mockingbird-media.test.
       Includes the March 2026 "Confirming migration to new Stripe billing"
       confirmation referencing legacy-entity cancellation, and the May 2026
       "Why two bills?" duplicate-charge complaint.

Plus ~30 NOISE conversations from other random contacts that contain "cancel"
keywords - red herrings for the agent to filter out.

Idempotent on contacts via `external_id`. Re-runs skip existing contacts.
Conversations are NOT deduplicated (Intercom permits unlimited duplicates)
but the script tracks what it created in-process so a single run doesn't
double-up.

Run:
    .venv/bin/python scripts/seed_intercom.py
"""

from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Make seed_world importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from seed_world import (  # noqa: E402
    COMPANIES,
    WORKFLOWS,
    Company,
    find_company,
    intercom_external_id,
)


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

TOKEN = os.getenv("INTERCOM_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("ERROR: INTERCOM_ACCESS_TOKEN missing from .env")

BASE = "https://api.intercom.io"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Intercom-Version": "2.11",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Rate limit is ~1000/min. We pace at ~10/s to leave headroom for retries.
REQ_SLEEP = 0.1

TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Make output reproducible across runs.
random.seed(20260527)


# ──────────────────────────────────────────────────────────────────────
# HTTP wrapper with retry
# ──────────────────────────────────────────────────────────────────────


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    retries: int = 4,
) -> httpx.Response:
    """Issue an HTTP request with backoff on 429 / 5xx."""
    url = path if path.startswith("http") else f"{BASE}{path}"
    last = None
    for attempt in range(retries):
        last = client.request(method, url, json=json, params=params)
        if last.status_code == 429:
            wait = float(last.headers.get("Retry-After", "2.0"))
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= last.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        return last
    return last  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────
# Lookups
# ──────────────────────────────────────────────────────────────────────


def find_contact_by_external_id(
    client: httpx.Client, external_id: str
) -> str | None:
    body = {
        "query": {
            "field": "external_id",
            "operator": "=",
            "value": external_id,
        }
    }
    r = _request(client, "POST", "/contacts/search", json=body)
    if r.status_code != 200:
        return None
    results = r.json().get("data", [])
    if results:
        return results[0].get("id")
    return None


def find_contact_by_email(
    client: httpx.Client, email: str
) -> str | None:
    body = {
        "query": {
            "field": "email",
            "operator": "=",
            "value": email,
        }
    }
    r = _request(client, "POST", "/contacts/search", json=body)
    if r.status_code != 200:
        return None
    results = r.json().get("data", [])
    if results:
        return results[0].get("id")
    return None


def get_admin_id(client: httpx.Client) -> str:
    """Fetch the authenticated admin ID for admin-initiated parts."""
    r = _request(client, "GET", "/me")
    if r.status_code != 200:
        sys.exit(f"GET /me failed: {r.status_code} {r.text[:200]}")
    return str(r.json().get("id"))


# ──────────────────────────────────────────────────────────────────────
# Contact builders
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ContactPlan:
    """A contact to create. external_id makes this idempotent."""
    slug: str               # company slug
    role_label: str         # primary / it_admin / billing / exec / engineer
    email: str
    name: str
    external_id: str
    signed_up_at: int       # epoch
    last_seen_at: int       # epoch
    # Set after creation:
    intercom_id: str | None = None


def _domain(slug: str) -> str:
    return f"{slug.replace('-', '')}.test"


# Realistic-looking names per role. The "last name" is derived from the
# company slug so the seed is reproducible and the names don't look
# templated.
NAME_FIRSTS_PRIMARY = [
    "Priya", "Jordan", "Sam", "Alex", "Casey", "Riley", "Morgan",
    "Taylor", "Jamie", "Avery", "Quinn", "Reese",
]
NAME_FIRSTS_IT = [
    "Devon", "Chris", "Pat", "Robin", "Drew", "Cory", "Kai",
    "Skylar", "Hayden", "Parker",
]
NAME_FIRSTS_BILLING = [
    "Rachel", "Sandra", "Maria", "Diane", "Linda", "Anna", "Sofia",
    "Carla", "Renee", "Tara",
]
NAME_FIRSTS_EXEC = [
    "Marcus", "Daniel", "Anil", "Lakshmi", "Marcus", "Patrick",
    "Helen", "Ruben", "Karim", "Olivia",
]
NAME_LASTS = [
    "Patel", "Chen", "Garcia", "Murphy", "Kim", "Johnson",
    "Müller", "Singh", "Rodriguez", "Brown", "Suzuki", "Hassan",
    "Nakamura", "Thompson", "Anderson", "Park", "Cohen",
]


def _name_for(slug: str, role_label: str, seed_n: int) -> str:
    pool = {
        "primary":   NAME_FIRSTS_PRIMARY,
        "it":        NAME_FIRSTS_IT,
        "billing":   NAME_FIRSTS_BILLING,
        "exec":      NAME_FIRSTS_EXEC,
        "engineer":  NAME_FIRSTS_IT,
    }.get(role_label, NAME_FIRSTS_PRIMARY)
    # Use slug + role + n to deterministically pick names (so re-runs match).
    h_first = (hash((slug, role_label, "first", seed_n)) % len(pool))
    h_last = (hash((slug, role_label, "last", seed_n)) % len(NAME_LASTS))
    return f"{pool[h_first]} {NAME_LASTS[h_last]}"


def _email_for(slug: str, role_label: str) -> str:
    domain = _domain(slug)
    local = {
        "it":       "itadmin",
        "billing":  "cfo",
        "exec":     "ceo",
        "engineer": "eng",
    }.get(role_label, "team")
    return f"{local}@{domain}"


def _to_epoch(y: int, m: int = 6, d: int = 15) -> int:
    return int(datetime(y, m, d, 9, 0, 0, tzinfo=timezone.utc).timestamp())


def build_contact_plans() -> list[ContactPlan]:
    """Build the full plan of contacts to create.

    - 1 primary per company (the c.email from COMPANIES)
    - 1-3 additional per company (IT admin, billing, exec)
    - target 80-120 total
    """
    plans: list[ContactPlan] = []
    now = int(time.time())

    for c in COMPANIES:
        signup_epoch = _to_epoch(c.signup_year, 3, 14)
        # last_seen_at: red/cancelled = older, green/yellow = recent
        if c.health == "red":
            last_seen = now - 86400 * random.randint(45, 180)
        elif c.health == "yellow":
            last_seen = now - 86400 * random.randint(7, 30)
        else:
            last_seen = now - 86400 * random.randint(0, 7)

        # 1) Primary contact (from COMPANIES.email)
        plans.append(ContactPlan(
            slug=c.slug,
            role_label="primary",
            email=c.email,
            name=_name_for(c.slug, "primary", 0),
            external_id=f"{intercom_external_id(c.slug)}_primary",
            signed_up_at=signup_epoch,
            last_seen_at=last_seen,
        ))

        # 2) Additional contacts. Workflow companies always get 2 extra.
        # Other companies: random 1-3.
        if c.slug in ("acme-genomics", "northwind-logi", "mockingbird-media"):
            extra_roles = ["it", "billing"]
        elif c.health == "red":
            # Churning companies - only 1 extra contact.
            extra_roles = random.choice([["billing"], ["exec"]])
        else:
            extra_roles = random.choice([
                ["it", "billing"],
                ["it"],
                ["billing"],
                ["it", "billing", "exec"],
                ["billing", "exec"],
                ["it", "engineer"],
            ])

        for i, role in enumerate(extra_roles, start=1):
            extra_signup = signup_epoch + 86400 * random.randint(7, 90)
            extra_last_seen = last_seen - 86400 * random.randint(0, 14)
            plans.append(ContactPlan(
                slug=c.slug,
                role_label=role,
                email=_email_for(c.slug, role),
                name=_name_for(c.slug, role, i),
                external_id=f"{intercom_external_id(c.slug)}_{role}_{i}",
                signed_up_at=extra_signup,
                last_seen_at=max(extra_last_seen, extra_signup),
            ))

    return plans


# ──────────────────────────────────────────────────────────────────────
# Conversation builders
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ConvoPlan:
    contact_email: str
    contact_external_id: str
    subject: str            # only used in our log; Intercom user_message has no subject
    body: str               # the message body (will become the conversation source)
    created_at: int         # epoch
    final_state: str        # "open" / "closed" / "snoozed"
    # If set, this is one of the workflow signal conversations. We log its ID.
    tag: str | None = None  # "W1.export" / "W2.upgrade" / "W3.duplicate" etc.
    # Optional admin reply body to send after creation (for realism).
    admin_reply: str | None = None
    # Set after creation:
    conversation_id: str | None = None
    message_id: str | None = None


# ── Body snippet pools (per topic) ─────────────────────────────────────

ONBOARDING_BODIES = [
    "Hi - just kicking off our integration. Where do I find the API key in the dashboard?",
    "Onboarding question: can you point me to docs for SSO setup? We use Okta.",
    "Quick onboarding follow-up - webhook signing secret rotated, all good now.",
    "Following up from the onboarding call. Got the team provisioned today.",
    "Hi team, we're getting started this week. Any best practices for the bulk-import endpoint?",
    "Account setup question - how do we add more seats to our workspace?",
]
PRICING_BODIES = [
    "Comparing plans - what's the difference between Pro Annual and Enterprise on the SLA side?",
    "Hi, we're evaluating you against a competitor. Can we get a custom quote for 50 seats?",
    "Question on pricing - is there a discount for annual prepay vs monthly?",
    "How is overage billed on the Pro plan? Couldn't find it on the pricing page.",
    "Can you walk us through the volume tiers for the API plan?",
]
INTEGRATION_BODIES = [
    "Stripe webhook integration question - getting 502s intermittently from your endpoint.",
    "Our Segment destination is dropping events. Can someone from your eng team take a look?",
    "Slack notification integration won't authorize - getting redirect loop on OAuth callback.",
    "Trying to set up Salesforce sync. The setup wizard hangs at the credentials step.",
    "Snowflake export integration: can we configure the destination schema?",
    "Tableau connector returns empty results even though the API has data.",
]
FEATURE_REQUESTS = [
    "Feature request: can you add per-environment API keys? Right now we share one across staging/prod.",
    "We'd love a bulk-edit feature for tags. Right now it's one-at-a-time which is slow.",
    "Feature request: export to Parquet. CSV is fine but bulky for our data lake.",
    "Any plans for a Terraform provider? We're trying to IaC our setup.",
    "Could you add a dark mode? Eyestrain on our team is real.",
]
BILLING_BODIES = [
    "Invoice for last month didn't show up in our portal. Can you re-send?",
    "Billing question - we're moving payment methods. Where do I update the card on file?",
    "Got charged twice this month it looks like. Can you verify and credit us back if so?",
    "Need a W-9 for our vendor onboarding system. Can you send one over?",
    "Can we get our invoices auto-emailed to ap@? Currently only the admin sees them.",
    "Tax question - we're tax-exempt in our state. Where do we upload the exemption form?",
]
RATE_LIMIT_BODIES = [
    "Hit 429s during our nightly batch job. Is the burst limit configurable?",
    "Our API is being throttled - getting `rate_limit_exceeded` even though we're under the documented limit.",
    "Quick question on rate limits - does the limit reset on the minute boundary or rolling?",
]
SUPPORT_GENERAL = [
    "Search isn't returning recent records. Last 24h is missing from results.",
    "How do I revoke an API token? Couldn't find it in admin settings.",
    "We accidentally deleted a workspace. Is there a way to restore it?",
    "Dashboard is loading slowly today - anyone else reporting this?",
    "Two-factor auth setup question. Got locked out of my account last week.",
    "Our notification emails are landing in spam. Any DKIM setup we need on our side?",
    "Audit log filter UI is broken in Safari. Works fine in Chrome.",
    "We need a SOC 2 report for our compliance review. Where do I download it?",
    "Webhooks fired for events that already happened a week ago - bug?",
    "The CSV download truncates at 10,000 rows. Is there a way to get all of them?",
]
DOWNGRADE_BODIES = [
    "Want to downgrade from Pro to Standard at next renewal. What's the process?",
    "Considering moving to a lower tier - what features would we lose on Standard?",
    "Plan downgrade question: if we downgrade mid-cycle is it pro-rated?",
]
RENEWAL_BODIES = [
    "When does our annual renew this year? Want to plan the budget.",
    "Renewal question - can we add seats at the same per-seat rate when renewing?",
    "Following up on renewal terms. Are you offering multi-year discounts?",
]

# NOISE: red-herring "cancel" mentions from OTHER companies (not the
# workflow targets). The agent should NOT mistake these for the
# workflow customers' cancel intent.
CANCEL_NOISE_BODIES = [
    "Please cancel my subscription effective end of month. Going with a competitor.",
    "Cancel my account - we no longer need this service.",
    "Refund request - we cancelled last month and were still charged.",
    "Considering cancellation due to pricing. Anything you can do?",
    "We've decided to wind down the trial. Please cancel before it converts.",
    "Looking to cancel before renewal hits next week.",
    "Cancel request - sending this through formal channels as well.",
    "We're cancelling our contract. Please confirm in writing.",
    "Refund + cancel - see attached for the unauthorized charge.",
    "Per our termination clause, please cancel our subscription effective immediately.",
]


def _epoch(y: int, m: int, d: int, hr: int = 10, mn: int = 0) -> int:
    return int(datetime(y, m, d, hr, mn, 0, tzinfo=timezone.utc).timestamp())


def _final_state_pick() -> str:
    """Pick state weighted: ~70% closed, ~20% open, ~10% snoozed."""
    r = random.random()
    if r < 0.70:
        return "closed"
    if r < 0.90:
        return "open"
    return "snoozed"


def _admin_reply_for(body: str) -> str | None:
    """Pick a plausible admin reply for an inbound message, ~60% of the time."""
    if random.random() > 0.6:
        return None
    canned = [
        "Thanks for reaching out - looking into this now and will follow up shortly.",
        "Got it. I've flagged this to our team. We'll have an update by EOD.",
        "Acknowledged - circling back to engineering on this.",
        "Thanks for the report. Can you share a screenshot or the request ID?",
        "I've routed this to the right team. They'll reply directly.",
        "Got it - should be resolved on our end. Let us know if anything else.",
        "Thanks! Documented the request - we'll include it in the next review.",
    ]
    return random.choice(canned)


# ── Workflow conversation templates ────────────────────────────────────

W1_CONVERSATIONS: list[ConvoPlan] = [
    # Earlier 2025 - onboarding follow-up
    ConvoPlan(
        contact_email="ops@acme-genomics.test",
        contact_external_id="ext_acme-genomics_primary",
        subject="Onboarding follow-up",
        body=(
            "Hi team - wrapping up our onboarding. We've got the data "
            "pipeline running into our prod environment and the team is "
            "trained up. Thanks for the help!"
        ),
        created_at=_epoch(2025, 7, 18, 14, 12),
        final_state="closed",
        tag="W1.onboarding",
        admin_reply=(
            "Awesome - glad it's running smoothly. Reach out anytime."
        ),
    ),
    # Renewal questions Q1 2026
    ConvoPlan(
        contact_email="ops@acme-genomics.test",
        contact_external_id="ext_acme-genomics_primary",
        subject="Renewal questions",
        body=(
            "When does our annual renew this year? We're trying to plan "
            "the FY26 budget and want to make sure the line item lands "
            "before the freeze."
        ),
        created_at=_epoch(2026, 2, 4, 9, 45),
        final_state="closed",
        tag="W1.renewal",
        admin_reply=(
            "Hi Priya - your Pro Annual renews on May 8, 2026. I'll loop "
            "in your AE for any pricing questions."
        ),
    ),
    # March 2026 - Data export options (the critical one)
    ConvoPlan(
        contact_email="ops@acme-genomics.test",
        contact_external_id="ext_acme-genomics_primary",
        subject="Data export options",
        body=(
            "Hi team - we're evaluating whether to continue with you for "
            "another year and need to understand what data export looks "
            "like. Could you walk us through the formats? We're not "
            "planning to cancel right now, just want to know what's "
            "available."
        ),
        created_at=_epoch(2026, 3, 11, 11, 7),
        final_state="closed",
        tag="W1.export",
        admin_reply=(
            "Hi Priya - happy to walk you through it. We support CSV, "
            "JSON, and Parquet via the /exports API plus scheduled S3 "
            "drops. Want me to set up a 30-min walkthrough?"
        ),
    ),
    # Follow-up to the export thread
    ConvoPlan(
        contact_email="ops@acme-genomics.test",
        contact_external_id="ext_acme-genomics_primary",
        subject="Re: Data export options",
        body=(
            "Thanks for the walkthrough - that's helpful. No action "
            "needed for now."
        ),
        created_at=_epoch(2026, 3, 14, 16, 22),
        final_state="closed",
        tag="W1.export_followup",
    ),
    # April 2026 - API rate limit
    ConvoPlan(
        contact_email="ops@acme-genomics.test",
        contact_external_id="ext_acme-genomics_primary",
        subject="API rate limit question",
        body=(
            "Hit 429s during nightly ingest. Can you bump to 200rps? "
            "Our batch window is tight and we can't shift it."
        ),
        created_at=_epoch(2026, 4, 22, 8, 30),
        final_state="closed",
        tag="W1.ratelimit",
        admin_reply=(
            "Bumped your account to 200rps. Let us know if you still see "
            "throttling and we'll dig in further."
        ),
    ),
    # May 2026 - general check-in (post renewal, still using)
    ConvoPlan(
        contact_email="ops@acme-genomics.test",
        contact_external_id="ext_acme-genomics_primary",
        subject="Dashboard slow",
        body=(
            "Dashboard has been sluggish loading the Q2 reports view. "
            "Anyone else noticing? Not blocking but annoying."
        ),
        created_at=_epoch(2026, 5, 19, 13, 50),
        final_state="open",
        tag="W1.dashboard",
    ),
]


W2_CONVERSATIONS: list[ConvoPlan] = [
    # General use Q4 2024
    ConvoPlan(
        contact_email="ar@northwind-logi.test",
        contact_external_id="ext_northwind-logi_primary",
        subject="Bulk import question",
        body=(
            "Hi - running our first bulk import for the warehouse data. "
            "Can the importer handle 2M rows in a single job or should "
            "we chunk?"
        ),
        created_at=_epoch(2024, 11, 13, 9, 18),
        final_state="closed",
        tag="W2.bulk",
        admin_reply=(
            "Chunk to 500k for best results. The importer can handle 2M "
            "but you'll get faster feedback in smaller batches."
        ),
    ),
    # Q1 2025 - integration with their ERP
    ConvoPlan(
        contact_email="ar@northwind-logi.test",
        contact_external_id="ext_northwind-logi_primary",
        subject="NetSuite connector setup",
        body=(
            "We're wiring up the NetSuite connector. The OAuth handshake "
            "fails on the callback. Can someone walk us through?"
        ),
        created_at=_epoch(2025, 2, 6, 15, 42),
        final_state="closed",
        tag="W2.netsuite",
        admin_reply=(
            "Sent you a Loom walkthrough. The common gotcha is the "
            "callback URL needs to match exactly including trailing slash."
        ),
    ),
    # March 2026 - pre-upgrade question
    ConvoPlan(
        contact_email="ar@northwind-logi.test",
        contact_external_id="ext_northwind-logi_primary",
        subject="Enterprise upgrade - what's included",
        body=(
            "Looking at moving to Enterprise. What's the timeline once "
            "we sign? Specifically need the SSO + audit log features "
            "ASAP for our compliance review."
        ),
        created_at=_epoch(2026, 3, 27, 10, 5),
        final_state="closed",
        tag="W2.preupgrade",
        admin_reply=(
            "Once payment lands, the upgrade is automatic - usually within "
            "a few minutes. SSO and audit log become available immediately "
            "after."
        ),
    ),
    # May 2026 - the URGENT escalation (W2 signal)
    ConvoPlan(
        contact_email="ar@northwind-logi.test",
        contact_external_id="ext_northwind-logi_primary",
        subject="Paid for upgrade but still on Standard tier",
        body=(
            "We paid the $9,000 Enterprise upgrade on May 12. Got the "
            "Stripe receipt. But our account is still showing Standard "
            "tier. Multiple users have been blocked from Enterprise-only "
            "features. URGENT please escalate."
        ),
        created_at=_epoch(2026, 5, 14, 8, 3),
        final_state="open",
        tag="W2.upgrade",
        admin_reply=(
            "Apologies for the trouble - escalating this to engineering "
            "now. I see the Stripe charge but I'm not seeing the "
            "entitlement flip on our side. Will follow up within the hour."
        ),
    ),
    # May 2026 - follow-up still chasing
    ConvoPlan(
        contact_email="ar@northwind-logi.test",
        contact_external_id="ext_northwind-logi_primary",
        subject="Still no Enterprise access",
        body=(
            "Following up - it's been 48 hours and we still don't have "
            "Enterprise. Team is blocked. Need a status update today."
        ),
        created_at=_epoch(2026, 5, 16, 11, 30),
        final_state="open",
        tag="W2.upgrade_followup",
    ),
]


W3_CONVERSATIONS: list[ConvoPlan] = [
    # General Q4 2025 - content publishing question
    ConvoPlan(
        contact_email="finance@mockingbird-media.test",
        contact_external_id="ext_mockingbird-media_primary",
        subject="Invoice format question",
        body=(
            "Hi - quick question on the invoice format. Our AP team "
            "needs the PO number on each invoice line. Is that "
            "configurable?"
        ),
        created_at=_epoch(2025, 10, 9, 14, 0),
        final_state="closed",
        tag="W3.invoice_format",
        admin_reply=(
            "Yes - you can add a custom PO field in the billing settings. "
            "It'll appear on all invoices going forward."
        ),
    ),
    # Feb 2026 - pre-migration coordination
    ConvoPlan(
        contact_email="finance@mockingbird-media.test",
        contact_external_id="ext_mockingbird-media_primary",
        subject="Pre-migration billing coordination",
        body=(
            "Per the email from your CSM, we're consolidating onto your "
            "new Stripe billing in March. Want to make sure we don't "
            "double-pay during the transition. Who's the right person "
            "on the finance side to coordinate with?"
        ),
        created_at=_epoch(2026, 2, 21, 11, 12),
        final_state="closed",
        tag="W3.premigration",
        admin_reply=(
            "Connecting you with our migrations team - they'll handle "
            "the cutover. Cc'd Gina on this thread."
        ),
    ),
    # March 2026 - migration confirmation (W3 signal)
    ConvoPlan(
        contact_email="finance@mockingbird-media.test",
        contact_external_id="ext_mockingbird-media_primary",
        subject="Confirming migration to new Stripe billing",
        body=(
            "Hi team - confirming our billing migration on March 12. "
            "We'll start paying on the new Stripe entity going forward. "
            "Please cancel the legacy subscription on the old entity at "
            "period-end as discussed."
        ),
        created_at=_epoch(2026, 3, 12, 9, 7),
        final_state="closed",
        tag="W3.migration",
        admin_reply=(
            "Confirmed - migration to new Stripe entity recorded for "
            "March 12. Legacy subscription will be terminated at end of "
            "billing period per the runbook."
        ),
    ),
    # April 2026 - random question on dashboards
    ConvoPlan(
        contact_email="finance@mockingbird-media.test",
        contact_external_id="ext_mockingbird-media_primary",
        subject="Dashboard share link",
        body=(
            "Is there a way to share a dashboard view with someone "
            "outside our workspace? Read-only is fine."
        ),
        created_at=_epoch(2026, 4, 18, 13, 25),
        final_state="closed",
        tag="W3.dashboard_share",
        admin_reply=(
            "Yes - use the 'Share via link' option in the dashboard menu. "
            "You can set it to read-only and expire after N days."
        ),
    ),
    # May 2026 - Why two bills (W3 signal)
    ConvoPlan(
        contact_email="finance@mockingbird-media.test",
        contact_external_id="ext_mockingbird-media_primary",
        subject="Why two bills?",
        body=(
            "We're seeing TWO charges this month - one on the new Stripe "
            "entity and one on the legacy entity. The legacy was supposed "
            "to be cancelled. Please refund the duplicate."
        ),
        created_at=_epoch(2026, 5, 6, 10, 18),
        final_state="open",
        tag="W3.duplicate",
        admin_reply=(
            "Looking into this immediately. I see the duplicate on the "
            "legacy side - should have been terminated end of March per "
            "the migration runbook. Will refund and confirm."
        ),
    ),
]


# ──────────────────────────────────────────────────────────────────────
# Conversation plan builder
# ──────────────────────────────────────────────────────────────────────


def _pick_body_for(c: Company) -> str:
    """Pick a generic conversation body, weighted by company plan/health."""
    pool: list[tuple[float, list[str]]] = [
        (0.18, SUPPORT_GENERAL),
        (0.15, INTEGRATION_BODIES),
        (0.12, BILLING_BODIES),
        (0.12, ONBOARDING_BODIES),
        (0.10, PRICING_BODIES),
        (0.10, FEATURE_REQUESTS),
        (0.08, RATE_LIMIT_BODIES),
        (0.08, RENEWAL_BODIES),
        (0.07, DOWNGRADE_BODIES),
    ]
    r = random.random()
    acc = 0.0
    for weight, msgs in pool:
        acc += weight
        if r <= acc:
            return random.choice(msgs)
    return random.choice(SUPPORT_GENERAL)


def _subject_from_body(body: str) -> str:
    """Derive a short pseudo-subject from a body for logging only."""
    first_sentence = body.split(".")[0].split("-")[0].split("?")[0].strip()
    return first_sentence[:60]


def _random_time_in_range(
    contact_signed_up_at: int, contact_last_seen_at: int
) -> int:
    """Random epoch between the contact's signup and last-seen."""
    lo = contact_signed_up_at
    hi = max(contact_last_seen_at, lo + 86400)
    return random.randint(lo, hi)


def build_generic_conversation_plans(
    contact_plans: list[ContactPlan],
) -> list[ConvoPlan]:
    """Build 3-10 generic conversations per contact, spread across tenure."""
    plans: list[ConvoPlan] = []
    workflow_emails = {
        "ops@acme-genomics.test",
        "ar@northwind-logi.test",
        "finance@mockingbird-media.test",
    }
    for ct in contact_plans:
        # Workflow PRIMARY contacts don't get generic noise - their entire
        # convo set is from the W1/W2/W3 templates.
        if ct.email in workflow_emails and ct.role_label == "primary":
            continue
        # Other contacts: 3-10 conversations each. Tail off for red/churning.
        company = find_company(ct.slug)
        if company.health == "red":
            n_convos = random.randint(2, 5)
        elif company.health == "yellow":
            n_convos = random.randint(3, 7)
        else:
            n_convos = random.randint(3, 9)

        for _ in range(n_convos):
            ts = _random_time_in_range(ct.signed_up_at, ct.last_seen_at)
            body = _pick_body_for(company)
            plans.append(ConvoPlan(
                contact_email=ct.email,
                contact_external_id=ct.external_id,
                subject=_subject_from_body(body),
                body=body,
                created_at=ts,
                final_state=_final_state_pick(),
                admin_reply=_admin_reply_for(body),
            ))
    return plans


def build_noise_cancel_conversations(
    contact_plans: list[ContactPlan],
) -> list[ConvoPlan]:
    """Generate ~30 'cancel' noise conversations from non-workflow contacts.

    These are red herrings - the agent must not associate these with the
    W1/W2/W3 customers.
    """
    workflow_slugs = {"acme-genomics", "northwind-logi", "mockingbird-media"}
    candidates = [
        ct for ct in contact_plans
        if ct.slug not in workflow_slugs
    ]
    # Bias toward red/yellow health companies (more realistic for cancel).
    red_yellow = [
        ct for ct in candidates
        if find_company(ct.slug).health in ("red", "yellow")
    ]
    sample_pool = red_yellow if len(red_yellow) >= 30 else candidates
    chosen = random.sample(sample_pool, min(30, len(sample_pool)))

    plans: list[ConvoPlan] = []
    for ct in chosen:
        body = random.choice(CANCEL_NOISE_BODIES)
        ts = _random_time_in_range(ct.signed_up_at, ct.last_seen_at)
        plans.append(ConvoPlan(
            contact_email=ct.email,
            contact_external_id=ct.external_id,
            subject=_subject_from_body(body),
            body=body,
            created_at=ts,
            final_state=_final_state_pick(),
            tag="NOISE.cancel",
            admin_reply=(
                "Got it - I'll get your request processed. You'll see "
                "confirmation by email."
            ),
        ))
    return plans


# ──────────────────────────────────────────────────────────────────────
# Creators
# ──────────────────────────────────────────────────────────────────────


def upsert_contact(
    client: httpx.Client, plan: ContactPlan
) -> tuple[str | None, str]:
    """Create or find a contact by external_id. Returns (id, action)."""
    existing = find_contact_by_external_id(client, plan.external_id)
    if existing:
        # Update last_seen_at and signed_up_at to keep things consistent.
        update = {
            "name": plan.name,
            "signed_up_at": plan.signed_up_at,
            "last_seen_at": plan.last_seen_at,
        }
        r = _request(
            client, "PUT", f"/contacts/{existing}", json=update
        )
        if r.status_code in (200, 201):
            return existing, "updated"
        return existing, "exists"

    # Also check by email (in case external_id mismatched but contact exists).
    by_email = find_contact_by_email(client, plan.email)
    if by_email:
        # Update with external_id this time so future lookups work.
        update = {
            "external_id": plan.external_id,
            "name": plan.name,
            "signed_up_at": plan.signed_up_at,
            "last_seen_at": plan.last_seen_at,
        }
        r = _request(client, "PUT", f"/contacts/{by_email}", json=update)
        if r.status_code in (200, 201):
            return by_email, "linked"
        return by_email, "exists_no_ext"

    payload = {
        "role": "user",
        "email": plan.email,
        "name": plan.name,
        "external_id": plan.external_id,
        "signed_up_at": plan.signed_up_at,
        "last_seen_at": plan.last_seen_at,
    }
    r = _request(client, "POST", "/contacts", json=payload)
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    # On 409 / duplicate, try search-by-email one more time.
    if r.status_code == 409:
        existing2 = find_contact_by_email(client, plan.email)
        if existing2:
            return existing2, "exists_409"
    print(f"  contact create fail {plan.email}: {r.status_code} {r.text[:200]}")
    return None, "error"


def create_conversation(
    client: httpx.Client,
    plan: ConvoPlan,
    contact_id: str,
    admin_id: str,
) -> tuple[str | None, str | None, str]:
    """Create the inbound user conversation, then optionally:
       - admin reply,
       - close / snooze.
    Returns (conversation_id, message_id, action).
    """
    payload = {
        "from": {"type": "user", "id": contact_id},
        "body": plan.body,
        "created_at": plan.created_at,
    }
    r = _request(client, "POST", "/conversations", json=payload)
    if r.status_code not in (200, 201):
        print(
            f"  convo create fail {plan.contact_email} "
            f"@{plan.created_at}: {r.status_code} {r.text[:200]}"
        )
        return None, None, "error"
    j = r.json()
    msg_id = j.get("id")
    convo_id = j.get("conversation_id")
    if not convo_id:
        print(
            f"  convo create returned no conversation_id: "
            f"{r.status_code} {r.text[:300]}"
        )
        return None, msg_id, "error"

    # Optional admin reply.
    if plan.admin_reply:
        reply = {
            "message_type": "comment",
            "type": "admin",
            "admin_id": admin_id,
            "body": f"<p>{plan.admin_reply}</p>",
        }
        rr = _request(
            client, "POST", f"/conversations/{convo_id}/reply", json=reply
        )
        # Don't fail the whole conversation if reply errors - just log.
        if rr.status_code not in (200, 201):
            print(
                f"    admin reply fail convo={convo_id}: "
                f"{rr.status_code} {rr.text[:150]}"
            )

    # Final state: close or snooze. (open = no action needed.)
    if plan.final_state == "closed":
        close = {
            "message_type": "close",
            "type": "admin",
            "admin_id": admin_id,
            "body": "Resolved.",
        }
        rc = _request(
            client, "POST", f"/conversations/{convo_id}/parts", json=close
        )
        if rc.status_code not in (200, 201):
            print(
                f"    close fail convo={convo_id}: "
                f"{rc.status_code} {rc.text[:150]}"
            )
    elif plan.final_state == "snoozed":
        snooze = {
            "message_type": "snoozed",
            "admin_id": admin_id,
            "snoozed_until": int(time.time()) + 86400 * random.randint(1, 7),
        }
        rs = _request(
            client, "POST", f"/conversations/{convo_id}/parts", json=snooze
        )
        if rs.status_code not in (200, 201):
            print(
                f"    snooze fail convo={convo_id}: "
                f"{rs.status_code} {rs.text[:150]}"
            )

    return convo_id, msg_id, "created"


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    counts = {
        "contacts_created": 0,
        "contacts_updated": 0,
        "contacts_linked": 0,
        "contacts_error": 0,
        "convos_created": 0,
        "convos_error": 0,
    }
    errors: list[str] = []

    # email → intercom contact id (we keep both keys for convenience)
    email_to_id: dict[str, str] = {}
    extid_to_id: dict[str, str] = {}

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        admin_id = get_admin_id(client)
        print(f"Authenticated as admin id={admin_id}\n")

        # ── 1. Contacts ──────────────────────────────────────────────
        contact_plans = build_contact_plans()
        print(f"Seeding {len(contact_plans)} contacts…")
        for plan in contact_plans:
            cid, action = upsert_contact(client, plan)
            if cid:
                email_to_id[plan.email] = cid
                extid_to_id[plan.external_id] = cid
                plan.intercom_id = cid

            if action == "created":
                counts["contacts_created"] += 1
            elif action == "updated":
                counts["contacts_updated"] += 1
            elif action == "linked":
                counts["contacts_linked"] += 1
            elif "exists" in action:
                counts["contacts_updated"] += 1
            else:
                counts["contacts_error"] += 1
                errors.append(f"contact {plan.email}: {action}")

            # Compact status every 10.
            if (
                (counts["contacts_created"]
                 + counts["contacts_updated"]
                 + counts["contacts_linked"]) % 10 == 0
            ):
                total = (
                    counts["contacts_created"]
                    + counts["contacts_updated"]
                    + counts["contacts_linked"]
                )
                print(
                    f"  …{total}/{len(contact_plans)} contacts processed"
                )
            time.sleep(REQ_SLEEP)

        # ── 2. Conversation plans ────────────────────────────────────
        # Build the merged list:
        #   - W1/W2/W3 specific
        #   - generic 3-10 per non-workflow-primary contact
        #   - ~30 noise cancel conversations
        all_convo_plans: list[ConvoPlan] = []
        all_convo_plans.extend(W1_CONVERSATIONS)
        all_convo_plans.extend(W2_CONVERSATIONS)
        all_convo_plans.extend(W3_CONVERSATIONS)
        generic_plans = build_generic_conversation_plans(contact_plans)
        all_convo_plans.extend(generic_plans)
        noise_plans = build_noise_cancel_conversations(contact_plans)
        all_convo_plans.extend(noise_plans)

        print(
            f"\nSeeding {len(all_convo_plans)} conversations "
            f"(W1={len(W1_CONVERSATIONS)} W2={len(W2_CONVERSATIONS)} "
            f"W3={len(W3_CONVERSATIONS)} generic={len(generic_plans)} "
            f"noise={len(noise_plans)})…"
        )

        # Track workflow-tagged convos so we can print them later.
        workflow_convo_ids: dict[str, list[tuple[str, str]]] = {
            "W1": [],
            "W2": [],
            "W3": [],
            "NOISE": [],
        }

        # Shuffle generic+noise for realism in creation order (workflow
        # ones we can leave at the front; doesn't matter for storage).
        # But process in original order so progress logging is sensible.
        for i, plan in enumerate(all_convo_plans, start=1):
            contact_id = extid_to_id.get(plan.contact_external_id) \
                or email_to_id.get(plan.contact_email)
            if not contact_id:
                counts["convos_error"] += 1
                errors.append(
                    f"convo skipped (no contact id): "
                    f"{plan.contact_email}"
                )
                continue

            convo_id, msg_id, action = create_conversation(
                client, plan, contact_id, admin_id
            )
            if convo_id:
                plan.conversation_id = convo_id
                plan.message_id = msg_id
                counts["convos_created"] += 1
                if plan.tag:
                    bucket = plan.tag.split(".")[0]
                    workflow_convo_ids.setdefault(bucket, []).append(
                        (plan.tag, convo_id)
                    )
            else:
                counts["convos_error"] += 1
                errors.append(
                    f"convo {plan.contact_email} @"
                    f"{plan.created_at}: {action}"
                )

            if i % 50 == 0:
                print(
                    f"  …{i}/{len(all_convo_plans)} conversations "
                    f"created={counts['convos_created']} "
                    f"errors={counts['convos_error']}"
                )
            time.sleep(REQ_SLEEP)

    # ── Workflow verification summary ─────────────────────────────────
    print("\n" + "═" * 70)
    print("WORKFLOW SIGNAL VERIFICATION")
    print("═" * 70)

    w1_primary = extid_to_id.get("ext_acme-genomics_primary")
    w2_primary = extid_to_id.get("ext_northwind-logi_primary")
    w3_primary = extid_to_id.get("ext_mockingbird-media_primary")

    print(f"\nW1 primary contact (ops@acme-genomics.test):    {w1_primary}")
    print(f"W2 primary contact (ar@northwind-logi.test):     {w2_primary}")
    print(f"W3 primary contact (finance@mockingbird-media.test): {w3_primary}")

    def _print_workflow(bucket: str, convos: list[ConvoPlan]) -> None:
        print(f"\n{bucket} conversations ({len(convos)}):")
        for plan in convos:
            tag = plan.tag or "?"
            cid = plan.conversation_id or "(failed)"
            ts = datetime.fromtimestamp(
                plan.created_at, tz=timezone.utc
            ).strftime("%Y-%m-%d")
            state = plan.final_state
            print(
                f"  [{tag:25s}] {ts}  state={state:7s}  "
                f"convo_id={cid}  {plan.subject[:50]}"
            )

    _print_workflow("W1 - Acme Genomics", W1_CONVERSATIONS)
    _print_workflow("W2 - Northwind Logistics", W2_CONVERSATIONS)
    _print_workflow("W3 - Mockingbird Media", W3_CONVERSATIONS)

    # Critical W1 sanity check: NO formal "please cancel" message exists.
    print("\nW1 sanity check: scanning W1 bodies for formal cancel intent…")
    w1_cancel_hits = []
    for plan in W1_CONVERSATIONS:
        body_low = plan.body.lower()
        if (
            ("please cancel" in body_low and "subscription" in body_low)
            or ("cancel my subscription" in body_low)
            or ("cancel effective" in body_low)
        ):
            w1_cancel_hits.append(plan.subject)
    if w1_cancel_hits:
        print(f"  FAIL - W1 contains formal cancel intent: {w1_cancel_hits}")
    else:
        print(
            "  PASS - no formal cancel-subscription message in W1 "
            "(customer kept using product)"
        )

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("SUMMARY")
    print("═" * 70)
    contacts_total = (
        counts["contacts_created"]
        + counts["contacts_updated"]
        + counts["contacts_linked"]
    )
    print(
        f"Contacts (total processed: {contacts_total}): "
        f"created={counts['contacts_created']:3d}  "
        f"updated={counts['contacts_updated']:3d}  "
        f"linked={counts['contacts_linked']:2d}  "
        f"errors={counts['contacts_error']:2d}"
    )
    print(
        f"Conversations: created={counts['convos_created']:3d}  "
        f"errors={counts['convos_error']:2d}"
    )
    print(
        f"  W1 conversations created: "
        f"{sum(1 for p in W1_CONVERSATIONS if p.conversation_id)}/"
        f"{len(W1_CONVERSATIONS)}"
    )
    print(
        f"  W2 conversations created: "
        f"{sum(1 for p in W2_CONVERSATIONS if p.conversation_id)}/"
        f"{len(W2_CONVERSATIONS)}"
    )
    print(
        f"  W3 conversations created: "
        f"{sum(1 for p in W3_CONVERSATIONS if p.conversation_id)}/"
        f"{len(W3_CONVERSATIONS)}"
    )
    noise_created = sum(
        1 for tag_id_list in [workflow_convo_ids.get("NOISE", [])]
        for _ in tag_id_list
    )
    print(f"  Noise cancel-keyword conversations: {noise_created}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  …and {len(errors) - 20} more")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
