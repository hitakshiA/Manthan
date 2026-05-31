"""Seed Zendesk with ~35 organizations, ~120 users, and ~1000 tickets.

Drives the Manthan billing-dispute investigation agent. Reads from
seed_world.py for canonical company identity so cross-source JOINs stay
consistent.

Idempotent - uses Zendesk's `create_or_update` endpoints (which key off
`external_id` for orgs and `external_id` for users). Tickets don't have
a natural idempotency key, so a local JSON file at
`.manthan/zendesk_seed_state.json` tracks which workflow-signal tickets
have already been created. The non-signal noise tickets are skipped on
re-run if the state file shows them done.

Workflow signals baked in:

  W1 - Acme Genomics: 2-3 tickets, NONE cancel-related. Tests that the
       agent JOINs through zendesk.users to confirm "no formal cancel"
       rather than assuming silence means cancel.
  W2 - Northwind Logistics: urgent open ticket about paid Enterprise
       upgrade still on Standard tier.
  W3 - Mockingbird Media: urgent open ticket about double-billing across
       the migration cutover.

Plus ~30-50 red-herring "cancel" / "refund" tickets from random other
companies (Globex, yellow-health, etc.) so the agent must distinguish
signal from noise.

Run:
    .venv/bin/python scripts/seed_zendesk.py
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

import httpx
from dotenv import load_dotenv

# Make seed_world importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from seed_world import COMPANIES, WORKFLOWS, Company  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN")
EMAIL_WITH_TOKEN = os.getenv("ZENDESK_USER_EMAIL_WITH_TOKEN")
API_TOKEN = os.getenv("ZENDESK_API_TOKEN")
if not (SUBDOMAIN and EMAIL_WITH_TOKEN and API_TOKEN):
    sys.exit("ERROR: ZENDESK_SUBDOMAIN / ZENDESK_USER_EMAIL_WITH_TOKEN / ZENDESK_API_TOKEN missing from .env")

BASE = f"https://{SUBDOMAIN}.zendesk.com/api/v2"
AUTH = (EMAIL_WITH_TOKEN, API_TOKEN)
TIMEOUT = httpx.Timeout(60.0, connect=15.0)

# Pace ourselves comfortably under the trial limit (~700 req/min).
# Slightly cautious value - we only really need this for non-bulk calls.
REQ_SLEEP = 0.05

# State file for tracking what tickets we've already created (idempotency).
STATE_PATH = SCRIPT_DIR.parent / ".manthan" / "zendesk_seed_state.json"

# Deterministic randomness so re-runs are reproducible.
RNG = random.Random(42)


# ──────────────────────────────────────────────────────────────────────
# State / persistence
# ──────────────────────────────────────────────────────────────────────


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


# ──────────────────────────────────────────────────────────────────────
# HTTP wrapper with retry on 429 / 5xx
# ──────────────────────────────────────────────────────────────────────


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
    retries: int = 4,
) -> httpx.Response:
    url = path if path.startswith("http") else f"{BASE}{path}"
    last: httpx.Response | None = None
    for attempt in range(retries):
        r = client.request(method, url, json=json_body, params=params)
        last = r
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", "2.0"))
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        return r
    return last  # type: ignore[return-value]


def _wait_for_job(
    client: httpx.Client, job_url: str, *, timeout_s: float = 120.0
) -> dict[str, Any]:
    """Poll a Zendesk job_status URL until completed/failed."""
    deadline = time.time() + timeout_s
    delay = 0.5
    while time.time() < deadline:
        r = _request(client, "GET", job_url)
        if r.status_code != 200:
            return {"status": "error", "message": f"poll {r.status_code}"}
        js = r.json().get("job_status", {})
        status = js.get("status")
        if status in ("completed", "failed", "killed"):
            return js
        time.sleep(delay)
        delay = min(delay * 1.5, 3.0)
    return {"status": "timeout"}


# ──────────────────────────────────────────────────────────────────────
# Domain helpers
# ──────────────────────────────────────────────────────────────────────


def _domain(c: Company) -> str:
    return f"{c.slug.replace('-', '')}.test"


def _name_from_email(email: str, fallback: str = "Customer") -> str:
    """Build a passable display name from an email's local part."""
    local = email.split("@", 1)[0]
    parts = [p for p in local.replace(".", "-").replace("_", "-").split("-") if p]
    if not parts:
        return fallback
    if len(parts) == 1:
        return parts[0].title()
    return " ".join(p.title() for p in parts[:2])


def _isoformat(dt: datetime) -> str:
    """ISO-8601 with Z suffix, no microseconds - Zendesk's preferred form."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ──────────────────────────────────────────────────────────────────────
# Organizations
# ──────────────────────────────────────────────────────────────────────


def upsert_organization(client: httpx.Client, c: Company) -> tuple[int | None, str]:
    """Idempotent org upsert via /organizations/create_or_update.json."""
    body = {
        "organization": {
            "name": c.name,
            "domain_names": [_domain(c)],
            "external_id": f"ext_{c.slug}",
            "details": (c.notes or "")[:255],
        }
    }
    r = _request(
        client,
        "POST",
        "/organizations/create_or_update.json",
        json_body=body,
    )
    if r.status_code in (200, 201):
        oid = r.json().get("organization", {}).get("id")
        action = "created" if r.status_code == 201 else "updated"
        return oid, action
    print(f"  org fail {c.slug}: {r.status_code} {r.text[:200]}")
    return None, "error"


# ──────────────────────────────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────────────────────────────


# Extra user emails per major company. The first email in `c.email` is the
# primary contact, already created separately; these are additional users
# (multiple per company creates volume + variety).
EXTRA_USER_LOCALS = [
    "support", "billing", "ops", "admin", "team", "finance", "analytics",
    "engineering", "security", "tech", "lead", "ceo", "cfo", "cto",
]


def _user_plan(c: Company) -> list[tuple[str, str, str]]:
    """Return (email, name, role) tuples for the company's users.

    Always include the primary (c.email) plus 1-4 extras depending on ARR
    band, so larger accounts have more named contacts.
    """
    domain = _domain(c)
    primary_email = c.email
    users: list[tuple[str, str, str]] = [
        (primary_email, _name_from_email(primary_email), "end-user"),
    ]
    # Extras based on ARR - bigger account → more users.
    if c.arr_usd >= 100_000:
        extras_n = 4
    elif c.arr_usd >= 50_000:
        extras_n = 3
    elif c.arr_usd >= 25_000:
        extras_n = 2
    else:
        extras_n = 1
    # Pick distinct locals deterministically per slug.
    seeded = random.Random(f"users-{c.slug}")
    picked = seeded.sample(EXTRA_USER_LOCALS, extras_n)
    for i, local in enumerate(picked):
        email = f"{local}@{domain}"
        if email == primary_email:
            email = f"{local}{i + 2}@{domain}"
        name = _name_from_email(email)
        # Sprinkle a handful of agent-role users for variety.
        # Make ~5% agents and only on bigger companies.
        role = "agent" if (c.arr_usd >= 60_000 and seeded.random() < 0.18) else "end-user"
        users.append((email, name, role))
    return users


def upsert_user(
    client: httpx.Client,
    *,
    email: str,
    name: str,
    role: str,
    organization_id: int,
    external_id: str,
) -> tuple[int | None, str]:
    body = {
        "user": {
            "name": name,
            "email": email,
            "role": role,
            "organization_id": organization_id,
            "external_id": external_id,
            "verified": True,
        }
    }
    r = _request(client, "POST", "/users/create_or_update.json", json_body=body)
    if r.status_code in (200, 201):
        uid = r.json().get("user", {}).get("id")
        action = "created" if r.status_code == 201 else "updated"
        return uid, action
    # Zendesk trial accounts cap agent users at 5. Auto-downgrade to end-user.
    if r.status_code == 422 and role == "agent" and "more than 5 agents" in r.text:
        body["user"]["role"] = "end-user"
        r = _request(client, "POST", "/users/create_or_update.json", json_body=body)
        if r.status_code in (200, 201):
            uid = r.json().get("user", {}).get("id")
            action = "created" if r.status_code == 201 else "updated"
            return uid, action + " (downgraded to end-user)"
    print(f"  user fail {email}: {r.status_code} {r.text[:200]}")
    return None, "error"


# ──────────────────────────────────────────────────────────────────────
# Ticket content - pools of subject/body templates by category
# ──────────────────────────────────────────────────────────────────────


# Each tuple is (subject_template, body_template). They use `{company}`,
# `{name}`, `{date}` placeholders that get filled in at ticket-generation
# time.
ONBOARDING_TICKETS = [
    (
        "Help with initial workspace setup",
        "Hi, we just signed up for {company} and I'm trying to get our team onboarded. "
        "Could someone walk me through the recommended setup for a team of around 25 people? "
        "Specifically: SSO config, default permissions, and which integrations to enable first.",
    ),
    (
        "SSO configuration not working",
        "We're trying to connect Okta SSO and getting a 'metadata mismatch' error on the IdP side. "
        "Followed the docs but something seems off. Can you help?",
    ),
    (
        "Onboarding question: data import limits",
        "What's the max number of records we can import in a single CSV upload? "
        "We have about 80,000 rows to bring over from our previous tool.",
    ),
    (
        "Trial extension request",
        "Our IT review is taking longer than expected. Any chance we can extend the trial "
        "by another 7-10 days? Pricing approval is in committee Friday.",
    ),
]

INTEGRATION_TICKETS = [
    (
        "Webhook signature verification failing",
        "Our webhook receiver keeps rejecting your events as 'signature_invalid'. "
        "We're using the signing secret from the dashboard. Is there a known issue or "
        "did the signing format change recently?",
    ),
    (
        "Salesforce sync stuck",
        "Our Salesforce integration shows 'syncing' for over 4 hours now. "
        "No errors in the activity log. Should we disconnect and reconnect or wait it out?",
    ),
    (
        "Zapier zap stopped firing",
        "Our 'new lead → Slack channel' zap was working fine until last Tuesday. "
        "Zapier is reporting auth failures on your side. Did something rotate?",
    ),
    (
        "API rate limit clarification",
        "The docs say 100 req/sec but we're getting 429s well below that. "
        "Is the limit per-key, per-IP, or per-account?",
    ),
    (
        "Custom field not appearing in API response",
        "I added a custom field via the admin UI but it's not showing up when I GET "
        "the object via /v1/customers/<id>. Do I need to enable it for API?",
    ),
]

PASSWORD_TICKETS = [
    (
        "Password reset email not arriving",
        "I requested a password reset 30 minutes ago and nothing has arrived. "
        "Checked spam. Email: {email}. Can you trigger it manually?",
    ),
    (
        "Locked out after MFA reset",
        "We rotated our MFA device and now I can't log in. The recovery codes "
        "aren't accepted either. Please help, I have a deck due in 2 hours.",
    ),
    (
        "2FA broken on new phone",
        "Got a new phone, tried to set up authenticator and the QR isn't scanning. "
        "Used recovery codes to get in but want to add 2FA back properly.",
    ),
]

FEATURE_TICKETS = [
    (
        "Feature request: bulk CSV export by tag",
        "It would be amazing to filter by tag and export just that subset to CSV. "
        "Right now I have to export everything and filter locally. Possible to add?",
    ),
    (
        "Feature request: dark mode",
        "Any plans for a proper dark mode? My team works late and the bright dashboard "
        "is rough on the eyes. Browser extensions don't get the contrast right.",
    ),
    (
        "Feature request: per-user reports",
        "Our manager wants a breakdown of per-user activity for performance reviews. "
        "The current reports are team-level only. Is this on the roadmap?",
    ),
    (
        "Feature request: keyboard shortcuts",
        "I use the dashboard heavily and would love hjkl-style nav. Even just j/k for "
        "next/previous in lists would save hours per week.",
    ),
    (
        "Feature: scheduled reports via email",
        "Can we get weekly digest reports auto-emailed every Monday morning? "
        "Right now I have to manually export and forward to my VP.",
    ),
]

BUG_TICKETS = [
    (
        "Dashboard chart shows wrong totals",
        "The 'monthly active users' chart on our dashboard shows 1,247 but the underlying "
        "report shows 1,189. Which one is correct? Screenshot attached (imagine).",
    ),
    (
        "Sidebar collapses unexpectedly",
        "When I switch between tabs the left sidebar collapses on its own. It happens "
        "maybe 1 in 5 times. Chrome on macOS. Not a huge deal but annoying.",
    ),
    (
        "Mobile app crashes on iOS 18",
        "Updated to iOS 18 yesterday, the app now crashes on open. Reinstalled, "
        "same problem. Pixel 7 still works fine for my colleague.",
    ),
    (
        "Date filter inconsistent in reports",
        "Setting 'last 30 days' on the activity report sometimes includes today, "
        "sometimes excludes today. Need consistent behavior for our daily standups.",
    ),
    (
        "Exported PDF missing legend",
        "When I export the trends chart to PDF, the color legend is missing. "
        "PNG export works fine. Could you fix the PDF renderer?",
    ),
]

PLAN_TICKETS = [
    (
        "What's the difference between Pro and Enterprise?",
        "We're outgrowing Pro and considering Enterprise. Specifically: "
        "1) SSO/SAML included? 2) Audit log retention length? 3) Priority support SLA?",
    ),
    (
        "Pricing for additional seats",
        "We're maxed out at our current seat count. What does adding 10 more "
        "look like, and can we do prorated mid-cycle?",
    ),
    (
        "Annual vs monthly billing question",
        "If we switch from monthly to annual mid-term, do we get a refund of the "
        "difference, a credit, or just the discount going forward?",
    ),
    (
        "Volume discount for 100+ seats?",
        "We're scaling fast and looking at 100+ seats by Q3. Is there a volume "
        "tier or do we just stay on per-seat pricing?",
    ),
]

OTHER_NOISE_TICKETS = [
    (
        "Need to download all our data",
        "GDPR request - we need a full export of all data associated with our workspace. "
        "What's the process and how long does it usually take?",
    ),
    (
        "Customer success contact",
        "Who is our CSM? We're due for a quarterly review and want to schedule it.",
    ),
    (
        "Slack channel for outages",
        "Is there a status page or Slack channel for incident comms? "
        "We've seen sporadic 500s and want to know if it's known.",
    ),
    (
        "Migration help",
        "We want to migrate from CompetitorTool to your platform. Do you have "
        "professional services or a CSV import template we can use?",
    ),
    (
        "Documentation typo",
        "On the 'Webhooks v2' doc page there's a section that says 'PSOT' instead of 'POST'. "
        "Small thing but figured I'd flag it.",
    ),
    (
        "How to add custom domain",
        "We want to use a custom domain (app.our-company.com) instead of the default. "
        "What DNS records do we need and is this on our plan?",
    ),
]

NON_BILLING_POOLS = [
    ("onboarding", ONBOARDING_TICKETS),
    ("integration", INTEGRATION_TICKETS),
    ("password", PASSWORD_TICKETS),
    ("feature", FEATURE_TICKETS),
    ("bug", BUG_TICKETS),
    ("plan", PLAN_TICKETS),
    ("other", OTHER_NOISE_TICKETS),
]

# Billing-flavored but NOT workflow-target - these are noise tickets that
# the agent should learn to deprioritize compared to W1/W2/W3.
BILLING_NOISE_TICKETS = [
    (
        "Invoice clarification",
        "Our last invoice has a line item 'platform usage adjustment' for $234.18. "
        "What does this cover? We weren't expecting it.",
    ),
    (
        "VAT not showing on invoice",
        "Our finance team needs our VAT number on the invoice for tax purposes. "
        "Can you update our billing profile and re-issue the latest one?",
    ),
    (
        "Update payment method",
        "Our corporate card expired and the new one isn't getting through your "
        "card-update flow. Browser shows 'declined' but the bank says no decline. "
        "Where do I send the new details?",
    ),
    (
        "Receipt for accounting",
        "Could you send me a PDF receipt for invoice INV-{n}? My accountant needs "
        "it for our quarter-close.",
    ),
    (
        "Question about overage charges",
        "We went over the included quota last month - what's the per-unit overage rate? "
        "Trying to estimate the bill before it lands.",
    ),
]

# Noise "cancel" / "refund" tickets - RED HERRINGS for non-workflow companies.
CANCEL_NOISE_TICKETS = [
    (
        "Cancel one of my seats",
        "We have a teammate leaving next week - can you cancel just their seat "
        "and refund prorated? Account: {company}.",
    ),
    (
        "Considering cancellation",
        "We're evaluating other tools and may not renew this year. Before we make "
        "a final call, can someone get on a 15-min sync to address our concerns?",
    ),
    (
        "Cancel my trial",
        "I signed up for the trial but we ended up going with a different tool. "
        "Please cancel before any charge kicks in. Thanks.",
    ),
    (
        "Refund for accidental upgrade",
        "Last Friday I clicked the wrong button and upgraded our plan to Enterprise. "
        "We don't actually need Enterprise - can you downgrade us back and refund the diff?",
    ),
    (
        "Refund: duplicate charge",
        "I see two identical charges on our card for $499 dated the same day. "
        "Looks like a glitch on your end. Please refund the duplicate.",
    ),
    (
        "Cancel auto-renew",
        "Please turn off auto-renew on our subscription. We may renew manually "
        "later but want to control the timing.",
    ),
    (
        "Cancel one subscription only",
        "We have two workspaces under our billing - please cancel the 'Staging' one "
        "but keep 'Production' active. Confused by the UI on this.",
    ),
    (
        "Need a partial refund",
        "We had to disable the service for 2 weeks while we sorted out an internal issue. "
        "Can we get a credit for those weeks or a partial refund?",
    ),
    (
        "Cancelling because of pricing",
        "Honestly your prices went up too much this year. We'll be cancelling and "
        "moving to a competitor. Please confirm cancel date.",
    ),
    (
        "Refund request - never used",
        "We bought this 6 months ago and never ended up rolling it out. Pretty rough "
        "to have paid for nothing. Any chance of a goodwill refund?",
    ),
]


# ──────────────────────────────────────────────────────────────────────
# Workflow-specific ticket specs
# ──────────────────────────────────────────────────────────────────────


def workflow_tickets_for(slug: str) -> list[dict[str, Any]]:
    """Return ticket specs for the workflow target company.

    Each dict has: subject, body, priority, status, days_ago, type.
    """
    if slug == "acme-genomics":
        # W1 - 2 tickets, NEITHER cancel-related.
        return [
            {
                "subject": "Add new viewer-role user",
                "body": (
                    "Hi team - we'd like to invite analytics@acme-genomics.test as a "
                    "viewer-role user on our workspace. They only need read-only access "
                    "to the dashboards, no admin permissions. Can you set that up or "
                    "point me to where I can do it myself?"
                ),
                "priority": "normal",
                "status": "solved",
                "days_ago": 38,
                "type": "question",
            },
            {
                "subject": "Webhook delivery question",
                "body": (
                    "Quick question - we're seeing some webhook deliveries arrive 2-3 "
                    "minutes after the underlying event. Is that within the expected "
                    "delivery window or should we file a bug? Most deliveries are sub-second "
                    "so the slow ones stand out."
                ),
                "priority": "low",
                "status": "solved",
                "days_ago": 89,
                "type": "question",
            },
        ]
    if slug == "northwind-logi":
        # W2 - urgent open ticket + older context ticket.
        return [
            {
                "subject": "Paid Enterprise upgrade but still on Standard tier",
                "body": (
                    "We paid $9,000 on May 12 via Stripe. Receipt confirms payment. "
                    "Account is still showing Standard tier 5 days later. Multiple users "
                    "blocked from Enterprise-only dashboards. Board demo tomorrow. "
                    "Please ESCALATE."
                ),
                "priority": "urgent",
                "status": "open",
                "days_ago": 5,
                "type": "problem",
            },
            {
                "subject": "Demo follow-up Q1",
                "body": (
                    "Following up on our demo from January - we walked through the "
                    "Enterprise tier features. Any chance of access to the analytics "
                    "dashboard previews or a recording of that session?"
                ),
                "priority": "normal",
                "status": "solved",
                "days_ago": 140,
                "type": "question",
            },
        ]
    if slug == "mockingbird-media":
        # W3 - urgent open ticket + older migration confirmation.
        return [
            {
                "subject": "Why are we being charged twice?",
                "body": (
                    "We see TWO charges this month - one $5,500 from Stripe and one "
                    "$5,500 from your legacy billing platform. The legacy entity was "
                    "supposed to be cancelled when we migrated in March. We've already "
                    "paid the Stripe one. Please refund the legacy and consolidate."
                ),
                "priority": "urgent",
                "status": "open",
                "days_ago": 3,
                "type": "problem",
            },
            {
                "subject": "Migration to Stripe - confirmation needed",
                "body": (
                    "Following our migration kickoff call - can you confirm that the "
                    "legacy billing subscription will be terminated as of end-of-March "
                    "once we cut over to Stripe? Our finance team wants written confirmation "
                    "before they sign off on the new payment method."
                ),
                "priority": "normal",
                "status": "solved",
                "days_ago": 80,
                "type": "question",
            },
        ]
    return []


# ──────────────────────────────────────────────────────────────────────
# Ticket generation
# ──────────────────────────────────────────────────────────────────────


PRIORITIES_NONBILLING = ["low", "low", "normal", "normal", "normal", "high"]
PRIORITIES_BILLING = ["normal", "normal", "high", "high", "urgent"]
# Distribute statuses across closed > solved > others to look real.
STATUSES = [
    ("closed", 0.45),
    ("solved", 0.30),
    ("open", 0.10),
    ("pending", 0.08),
    ("on-hold", 0.07),
]
TYPES = ["question", "incident", "task", "problem"]


def _pick_weighted(rng: random.Random, pairs: list[tuple[str, float]]) -> str:
    total = sum(w for _, w in pairs)
    pick = rng.random() * total
    acc = 0.0
    for name, w in pairs:
        acc += w
        if pick <= acc:
            return name
    return pairs[-1][0]


def _ticket_created_at(rng: random.Random, c: Company) -> datetime:
    """Pick a random ticket creation timestamp between company signup and now."""
    start_year = max(c.signup_year, 2024)
    start = datetime(start_year, 1, 5, tzinfo=timezone.utc)
    # "now" - use 2026-05-27 as anchor (matches today per env context).
    end = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)
    if end <= start:
        end = start + timedelta(days=30)
    span_s = int((end - start).total_seconds())
    offset = rng.randint(0, span_s)
    return start + timedelta(seconds=offset)


def _build_noise_ticket(
    rng: random.Random,
    *,
    c: Company,
    requester_id: int,
    requester_email: str,
    is_billing: bool,
    is_cancel_noise: bool,
) -> dict[str, Any]:
    """Build a non-workflow noise ticket spec dict (un-imported form)."""
    if is_cancel_noise:
        subj_t, body_t = rng.choice(CANCEL_NOISE_TICKETS)
        priority = rng.choice(PRIORITIES_BILLING)
    elif is_billing:
        subj_t, body_t = rng.choice(BILLING_NOISE_TICKETS)
        priority = rng.choice(PRIORITIES_BILLING)
    else:
        _, pool = rng.choice(NON_BILLING_POOLS)
        subj_t, body_t = rng.choice(pool)
        priority = rng.choice(PRIORITIES_NONBILLING)

    status = _pick_weighted(rng, STATUSES)
    ticket_type = rng.choices(TYPES, weights=[5, 2, 1, 1], k=1)[0]
    created_at = _ticket_created_at(rng, c)

    # Solved/closed tickets get an updated_at after creation; open ones same as created.
    if status in ("solved", "closed"):
        updated_at = created_at + timedelta(days=rng.randint(1, 14), hours=rng.randint(0, 23))
        if updated_at > datetime(2026, 5, 27, tzinfo=timezone.utc):
            updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    elif status in ("pending", "on-hold"):
        updated_at = created_at + timedelta(days=rng.randint(0, 5))
    else:
        updated_at = created_at

    subject = subj_t.format(company=c.name, name=c.name, email=requester_email, n=rng.randint(1000, 9999))
    body = body_t.format(company=c.name, name=c.name, email=requester_email, n=rng.randint(1000, 9999))

    return {
        "subject": subject,
        "body": body,
        "priority": priority,
        "status": status,
        "type": ticket_type,
        "created_at": _isoformat(created_at),
        "updated_at": _isoformat(updated_at),
        "requester_id": requester_id,
        "requester_email": requester_email,
    }


def _build_workflow_ticket(
    *,
    c: Company,
    requester_id: int,
    requester_email: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Build a workflow-target ticket spec dict - exact content, dated."""
    created_at = datetime(2026, 5, 27, tzinfo=timezone.utc) - timedelta(days=spec["days_ago"])
    if spec["status"] in ("solved", "closed"):
        updated_at = created_at + timedelta(days=2)
    else:
        updated_at = created_at + timedelta(hours=4)
    return {
        "subject": spec["subject"],
        "body": spec["body"],
        "priority": spec["priority"],
        "status": spec["status"],
        "type": spec.get("type", "question"),
        "created_at": _isoformat(created_at),
        "updated_at": _isoformat(updated_at),
        "requester_id": requester_id,
        "requester_email": requester_email,
        "workflow_tag": True,
    }


def import_ticket(client: httpx.Client, spec: dict[str, Any]) -> int | None:
    """POST a single ticket via /imports/tickets.json (preserves created_at).

    Raises TrialCapHit if Zendesk's trial cap blocks the create.
    """
    body = {
        "ticket": {
            "subject": spec["subject"],
            "comments": [
                {
                    "author_id": spec["requester_id"],
                    "value": spec["body"],
                    "created_at": spec["created_at"],
                }
            ],
            "requester_id": spec["requester_id"],
            "priority": spec["priority"],
            "status": spec["status"],
            "type": spec["type"],
            "created_at": spec["created_at"],
            "updated_at": spec["updated_at"],
        }
    }
    r = _request(client, "POST", "/imports/tickets.json", json_body=body)
    if r.status_code in (200, 201):
        return r.json().get("ticket", {}).get("id")
    if r.status_code == 422 and "account has expired" in r.text.lower():
        raise TrialCapHit("single-ticket import blocked by trial cap")
    print(f"  ticket fail: {r.status_code} {r.text[:240]}")
    return None


class TrialCapHit(Exception):
    """Raised when Zendesk's trial-tier ticket cap rejects all writes."""


def import_tickets_bulk(
    client: httpx.Client, specs: list[dict[str, Any]]
) -> list[int]:
    """POST a batch via /imports/tickets/create_many.json - max 100 per call.

    Raises TrialCapHit if all tickets in the batch fail with the trial-tier
    "account has expired" error, so the caller can stop iterating.
    """
    if not specs:
        return []
    body = {
        "tickets": [
            {
                "subject": s["subject"],
                "comments": [
                    {
                        "author_id": s["requester_id"],
                        "value": s["body"],
                        "created_at": s["created_at"],
                    }
                ],
                "requester_id": s["requester_id"],
                "priority": s["priority"],
                "status": s["status"],
                "type": s["type"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
            }
            for s in specs
        ]
    }
    r = _request(
        client, "POST", "/imports/tickets/create_many.json", json_body=body
    )
    if r.status_code not in (200, 201):
        print(f"  bulk import fail: {r.status_code} {r.text[:240]}")
        return []
    job_url = r.json().get("job_status", {}).get("url")
    if not job_url:
        return []
    js = _wait_for_job(client, job_url, timeout_s=180.0)
    if js.get("status") != "completed":
        print(f"  bulk import job didn't complete: {js}")
        return []
    ids: list[int] = []
    expired_count = 0
    for res in js.get("results") or []:
        tid = res.get("id")
        if tid:
            ids.append(tid)
            continue
        err_details = str(res.get("details") or "")
        if "account has expired" in err_details.lower():
            expired_count += 1
        elif res.get("error"):
            print(f"  bulk ticket error: {res}")
    if expired_count and not ids:
        # Whole batch hit the trial cap - surface that to the caller.
        raise TrialCapHit(
            f"trial cap hit: {expired_count}/{len(specs)} tickets blocked"
        )
    return ids


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    state = load_state()
    state.setdefault("organizations", {})  # slug -> zendesk org id
    state.setdefault("users", {})  # external_id -> zendesk user id
    state.setdefault("workflow_tickets", {})  # slug -> [ticket_ids]
    state.setdefault("noise_seeded", False)
    state.setdefault("noise_ticket_count", 0)

    counts = {
        "orgs_created": 0, "orgs_updated": 0, "orgs_error": 0,
        "users_created": 0, "users_updated": 0, "users_error": 0,
        "tickets_created": 0, "tickets_error": 0,
        "workflow_tickets": 0, "cancel_noise_tickets": 0,
        "billing_noise_tickets": 0, "non_billing_tickets": 0,
    }
    status_counts: dict[str, int] = {}
    errors: list[str] = []

    # Track per-company user IDs so we can attach tickets.
    company_users: dict[str, list[tuple[int, str]]] = {}  # slug -> [(uid, email)]
    company_org_id: dict[str, int] = {}

    with httpx.Client(headers={"Content-Type": "application/json"}, auth=AUTH, timeout=TIMEOUT) as client:
        # ── 1. Organizations ──────────────────────────────────────────
        cached_orgs = sum(1 for c in COMPANIES if c.slug in state["organizations"])
        print(
            f"Seeding {len(COMPANIES)} organizations "
            f"({cached_orgs} already in state)…"
        )
        for c in COMPANIES:
            # Idempotent skip via state cache.
            cached = state["organizations"].get(c.slug)
            if cached:
                company_org_id[c.slug] = cached
                counts["orgs_updated"] += 1
                continue
            oid, action = upsert_organization(client, c)
            if oid:
                company_org_id[c.slug] = oid
                state["organizations"][c.slug] = oid
            if action == "created":
                counts["orgs_created"] += 1
            elif action == "updated":
                counts["orgs_updated"] += 1
            else:
                counts["orgs_error"] += 1
                errors.append(f"org {c.slug}: {action}")
            print(f"  [{action:>10}] {c.slug:25s} → {oid}")
            time.sleep(REQ_SLEEP)
        save_state(state)

        # ── 2. Users (primary + extras per company) ────────────────────
        # Skip users already in state (idempotency under trial-cap conditions
        # where re-running can fail user upserts). Also skip users we've
        # tried and given up on so we don't pound the API on every re-run.
        state.setdefault("users_failed_permanent", [])
        failed_permanent = set(state["users_failed_permanent"])
        total_planned_users = sum(len(_user_plan(c)) for c in COMPANIES)
        cached_users = sum(
            1
            for c in COMPANIES
            for i in range(len(_user_plan(c)))
            if f"ext_{c.slug}_{i}" in state["users"]
        )
        print(
            f"\nSeeding ~{total_planned_users} users across "
            f"{len(COMPANIES)} companies ({cached_users} already in state)…"
        )
        for c in COMPANIES:
            org_id = company_org_id.get(c.slug)
            if not org_id:
                errors.append(f"user skip (no org): {c.slug}")
                continue
            users_for_this_co: list[tuple[int, str]] = []
            for i, (email, name, role) in enumerate(_user_plan(c)):
                ext_id = f"ext_{c.slug}_{i}"
                cached = state["users"].get(ext_id)
                if cached:
                    users_for_this_co.append((cached, email))
                    counts["users_updated"] += 1  # treat as existing
                    continue
                if ext_id in failed_permanent:
                    # Don't keep retrying users that hit a hard cap.
                    continue
                uid, action = upsert_user(
                    client,
                    email=email, name=name, role=role,
                    organization_id=org_id, external_id=ext_id,
                )
                if uid:
                    state["users"][ext_id] = uid
                    users_for_this_co.append((uid, email))
                if action.startswith("created"):
                    counts["users_created"] += 1
                elif action.startswith("updated"):
                    counts["users_updated"] += 1
                else:
                    # Mark as permanently failed so re-runs skip.
                    failed_permanent.add(ext_id)
                    state["users_failed_permanent"] = sorted(failed_permanent)
                    counts["users_error"] += 1
                    errors.append(f"user {email}: {action}")
                time.sleep(REQ_SLEEP)
            company_users[c.slug] = users_for_this_co
            print(f"  {c.slug:25s} → {len(users_for_this_co)} users")
        save_state(state)

        # ── 3. Workflow tickets (W1 / W2 / W3) ────────────────────────
        print("\nSeeding workflow tickets (W1/W2/W3)…")
        workflow_slugs = ["acme-genomics", "northwind-logi", "mockingbird-media"]
        workflow_aborted = False
        for slug in workflow_slugs:
            if workflow_aborted:
                break
            users = company_users.get(slug) or []
            if not users:
                errors.append(f"workflow {slug}: no users")
                continue
            # Use the primary user (index 0) for workflow tickets.
            primary_uid, primary_email = users[0]
            existing = state["workflow_tickets"].get(slug, [])
            if existing:
                print(f"  {slug}: already has {len(existing)} workflow tickets → skip")
                counts["workflow_tickets"] += len(existing)
                continue
            specs = workflow_tickets_for(slug)
            new_ids: list[int] = []
            for spec in specs:
                ts = _build_workflow_ticket(
                    c=next(co for co in COMPANIES if co.slug == slug),
                    requester_id=primary_uid,
                    requester_email=primary_email,
                    spec=spec,
                )
                try:
                    tid = import_ticket(client, ts)
                except TrialCapHit:
                    print(f"  TRIAL CAP HIT during {slug} workflow ticket - stop")
                    workflow_aborted = True
                    errors.append(
                        f"workflow {slug}: trial cap hit on '{spec['subject']}'"
                    )
                    break
                if tid:
                    new_ids.append(tid)
                    counts["tickets_created"] += 1
                    counts["workflow_tickets"] += 1
                    status_counts[ts["status"]] = status_counts.get(ts["status"], 0) + 1
                else:
                    counts["tickets_error"] += 1
                    errors.append(f"workflow ticket {slug} '{spec['subject']}'")
                time.sleep(REQ_SLEEP)
            state["workflow_tickets"][slug] = new_ids
            print(f"  {slug}: created {len(new_ids)} workflow tickets → {new_ids}")
        save_state(state)

        # ── 4. Noise tickets ───────────────────────────────────────────
        if state.get("noise_seeded"):
            print(
                f"\nNoise tickets already seeded (count="
                f"{state.get('noise_ticket_count')}) → skipping."
            )
        else:
            print("\nSeeding noise tickets (target ~1000)…")
            noise_specs = _plan_noise_tickets(company_users)
            print(f"  planned {len(noise_specs)} tickets")

            # Bulk import in chunks of 100. Stop early if the trial cap kicks in.
            CHUNK = 100
            created_total = 0
            trial_cap_hit = False
            for i in range(0, len(noise_specs), CHUNK):
                chunk = noise_specs[i:i + CHUNK]
                try:
                    ids = import_tickets_bulk(client, chunk)
                except TrialCapHit as e:
                    trial_cap_hit = True
                    print(f"\n  TRIAL CAP HIT - {e}")
                    print(
                        "  Zendesk trial accounts cap total ticket volume. "
                        "Stopping noise seeding here."
                    )
                    break
                created_total += len(ids)
                counts["tickets_created"] += len(ids)
                counts["tickets_error"] += (len(chunk) - len(ids))
                for s in chunk:
                    status_counts[s["status"]] = status_counts.get(s["status"], 0) + 1
                    body_low = s["body"].lower()
                    subj_low = s["subject"].lower()
                    is_cancel = ("cancel" in subj_low or "cancel" in body_low
                                 or "refund" in subj_low or "refund" in body_low)
                    if is_cancel:
                        counts["cancel_noise_tickets"] += 1
                    else:
                        if any(
                            kw in body_low or kw in subj_low
                            for kw in ("invoice", "vat", "billing", "receipt", "overage", "payment method")
                        ):
                            counts["billing_noise_tickets"] += 1
                        else:
                            counts["non_billing_tickets"] += 1
                if (created_total // 100) > ((created_total - len(ids)) // 100):
                    print(f"  …{created_total} tickets created so far")
            state["noise_seeded"] = True
            state["noise_ticket_count"] = created_total
            state["trial_cap_hit"] = trial_cap_hit
            save_state(state)

        # ── 5. Verification ────────────────────────────────────────────
        print("\n" + "─" * 70)
        print("Workflow signal verification")
        print("─" * 70)
        verify_workflows(client, state)

        # Pull live totals from Zendesk for the summary header.
        live_totals: dict[str, int] = {}
        for name, path in (
            ("orgs", "/organizations/count.json"),
            ("users", "/users/count.json"),
            ("tickets", "/tickets/count.json"),
        ):
            r = _request(client, "GET", path)
            if r.status_code == 200:
                live_totals[name] = r.json().get("count", {}).get("value", -1)

    # ── Summary ────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("SUMMARY")
    print("═" * 70)
    if state.get("trial_cap_hit"):
        print(
            "NOTE: Zendesk trial cap blocked ticket writes partway through.\n"
            "Re-running won't add more tickets on this trial account.\n"
        )
    if live_totals:
        print(
            f"Live Zendesk totals: orgs={live_totals.get('orgs')}  "
            f"users={live_totals.get('users')}  "
            f"tickets={live_totals.get('tickets')}"
        )
        print()
    print(
        f"Organizations: created={counts['orgs_created']:3d}  "
        f"updated={counts['orgs_updated']:3d}  errors={counts['orgs_error']:3d}"
    )
    print(
        f"Users        : created={counts['users_created']:3d}  "
        f"updated={counts['users_updated']:3d}  errors={counts['users_error']:3d}"
    )
    print(
        f"Tickets      : created={counts['tickets_created']:4d}  "
        f"errors={counts['tickets_error']:3d}"
    )
    print(
        f"  workflow tickets   : {counts['workflow_tickets']}"
    )
    print(
        f"  cancel/refund noise: {counts['cancel_noise_tickets']}"
    )
    print(
        f"  billing noise      : {counts['billing_noise_tickets']}"
    )
    print(
        f"  non-billing noise  : {counts['non_billing_tickets']}"
    )
    print("\nTickets by status:")
    for st, n in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {st:10s} {n:5d}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  …and {len(errors) - 20} more")

    print("\nWorkflow target ticket IDs:")
    for slug in ("acme-genomics", "northwind-logi", "mockingbird-media"):
        ids = state["workflow_tickets"].get(slug, [])
        org = state["organizations"].get(slug)
        print(f"  {slug:25s} org={org} tickets={ids}")

    return 0 if not errors else 1


# ──────────────────────────────────────────────────────────────────────
# Noise planning
# ──────────────────────────────────────────────────────────────────────


def _plan_noise_tickets(
    company_users: dict[str, list[tuple[int, str]]],
) -> list[dict[str, Any]]:
    """Plan ~1000 noise tickets across users, mix of billing/non-billing/cancel-noise.

    Returns a flat list of ticket spec dicts ready for bulk import.
    """
    specs: list[dict[str, Any]] = []
    # We aim for ~900-1100 total non-workflow tickets:
    #  - ~10-15% billing-flavored (non-cancel-noise: invoices, VAT, etc.)
    #  - ~4-5% cancel/refund noise (red herrings)
    #  - ~80%+ non-billing realism
    target_min, target_max = 900, 1100

    # Tickets per user, weighted by company ARR + a random factor.
    # 5-15 tickets per user as instructed.
    per_user_specs: list[dict[str, Any]] = []
    for c in COMPANIES:
        users = company_users.get(c.slug) or []
        if not users:
            continue
        # Per-user ticket count: bigger ARR → more tickets (within 5-15).
        if c.arr_usd >= 100_000:
            base = 12
        elif c.arr_usd >= 50_000:
            base = 9
        elif c.arr_usd >= 25_000:
            base = 7
        else:
            base = 6
        for uid, email in users:
            n = max(5, min(15, base + RNG.randint(-3, 3)))
            for _ in range(n):
                # Determine ticket flavor:
                #   - cancel/refund noise: only assigned at most to ~40 picks total later
                #   - billing-noise: ~10-15% per ticket
                #   - rest: non-billing
                roll = RNG.random()
                if roll < 0.12:
                    flavor = "billing"  # invoice/VAT/receipt/etc.
                else:
                    flavor = "non_billing"
                per_user_specs.append({
                    "slug": c.slug, "uid": uid, "email": email, "flavor": flavor,
                })

    # Now sprinkle in ~30-50 cancel/refund noise tickets from random users.
    # Avoid the three workflow-target companies to keep their signal clean.
    workflow_slugs = {"acme-genomics", "northwind-logi", "mockingbird-media"}
    eligible_for_cancel = [
        s for s in per_user_specs if s["slug"] not in workflow_slugs
    ]
    cancel_count = RNG.randint(38, 46)
    cancel_indices = set(
        RNG.sample(range(len(eligible_for_cancel)), k=min(cancel_count, len(eligible_for_cancel)))
    )
    # Convert to set of object identities (using index into eligible list).
    cancel_marker_ids = set()
    for idx in cancel_indices:
        cancel_marker_ids.add(id(eligible_for_cancel[idx]))
    for entry in per_user_specs:
        if id(entry) in cancel_marker_ids:
            entry["flavor"] = "cancel_noise"

    # If we overshoot the upper target, trim non-billing entries.
    if len(per_user_specs) > target_max:
        # Trim from the tail of non-billing entries.
        trim_count = len(per_user_specs) - target_max
        # Walk in reverse, removing non_billing/billing first (keep cancel_noise).
        i = len(per_user_specs) - 1
        while trim_count > 0 and i >= 0:
            if per_user_specs[i]["flavor"] in ("non_billing", "billing"):
                per_user_specs.pop(i)
                trim_count -= 1
            i -= 1
    elif len(per_user_specs) < target_min:
        # Pad with extra non_billing tickets distributed across larger orgs.
        extras_needed = target_min - len(per_user_specs)
        donors = [
            (c, company_users.get(c.slug) or []) for c in COMPANIES
            if c.arr_usd >= 40_000 and (company_users.get(c.slug) or [])
        ]
        i = 0
        while extras_needed > 0 and donors:
            c, users = donors[i % len(donors)]
            uid, email = RNG.choice(users)
            per_user_specs.append({
                "slug": c.slug, "uid": uid, "email": email, "flavor": "non_billing",
            })
            extras_needed -= 1
            i += 1

    # Materialize into full ticket specs.
    for entry in per_user_specs:
        c = next(co for co in COMPANIES if co.slug == entry["slug"])
        flavor = entry["flavor"]
        spec = _build_noise_ticket(
            RNG,
            c=c,
            requester_id=entry["uid"],
            requester_email=entry["email"],
            is_billing=(flavor in ("billing", "cancel_noise")),
            is_cancel_noise=(flavor == "cancel_noise"),
        )
        specs.append(spec)

    RNG.shuffle(specs)
    return specs


# ──────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────


def verify_workflows(client: httpx.Client, state: dict[str, Any]) -> None:
    """Pull each workflow ticket back and sanity-check key fields."""
    expectations = {
        "acme-genomics": {
            "min": 2,
            "subjects_required": ["Add new viewer-role user", "Webhook delivery question"],
            "must_not_contain": ["cancel", "refund"],
        },
        "northwind-logi": {
            "min": 1,
            "subjects_required": ["Paid Enterprise upgrade but still on Standard tier"],
            "urgent_open": True,
        },
        "mockingbird-media": {
            "min": 1,
            "subjects_required": ["Why are we being charged twice?"],
            "urgent_open": True,
        },
    }
    for slug, exp in expectations.items():
        tids = state["workflow_tickets"].get(slug, [])
        if len(tids) < exp["min"]:
            print(f"W {slug}: FAIL - got {len(tids)} tickets, need {exp['min']}")
            continue
        subjects: list[str] = []
        urgent_open_ok = False
        for tid in tids:
            r = _request(client, "GET", f"/tickets/{tid}.json")
            if r.status_code != 200:
                print(f"  ticket {tid}: lookup failed {r.status_code}")
                continue
            t = r.json().get("ticket", {})
            subjects.append(t.get("subject", ""))
            if t.get("priority") == "urgent" and t.get("status") == "open":
                urgent_open_ok = True
        ok = True
        for needed_subj in exp.get("subjects_required", []):
            if not any(needed_subj in s for s in subjects):
                ok = False
                print(f"  {slug}: missing subject {needed_subj!r}")
        if exp.get("urgent_open") and not urgent_open_ok:
            ok = False
            print(f"  {slug}: no urgent+open ticket found")
        for forbidden in exp.get("must_not_contain", []):
            for s in subjects:
                if forbidden in s.lower():
                    ok = False
                    print(f"  {slug}: forbidden term {forbidden!r} in subject {s!r}")
        status = "OK" if ok else "FAIL"
        print(f"W {slug:25s} tickets={tids} signal={status}")


if __name__ == "__main__":
    sys.exit(main())
