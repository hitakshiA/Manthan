"""Coral-faithful scenarios - every row uses REAL Coral column names.

These scenarios are designed to be tested EXCLUSIVELY through the real
Coral binary via MCP. No flat mock. No shortcuts.

Constraints we honor:
  - Column names match the real Coral source manifests
    (/coral/sources/<core|community>/<source>/manifest.yaml).
  - Tables only exist if real Coral exposes them (no fake `slack.messages`
    or `posthog.person_summary`).
  - Heavy volume: 1000+ rows per noisy table.
  - Adversarial noise: similar emails across companies, sparse fields,
    overlapping policy docs, mixed timestamp formats, dup-named entities.

10 sources used across the battery, with each scenario touching a
DIFFERENT subset of 4-7 sources to exercise different source-selection
patterns:

  S01  Friendly fraud - stripe + intercom + zendesk + gmail + notion + salesforce
  S02  SLA partial    - stripe + salesforce + pagerduty + datadog + notion + intercom
  S03  AE promise     - stripe + salesforce + gmail + hubspot + notion
  S04  VAT compliance - stripe + salesforce + hubspot + intercom + notion + sentry
  S05  Migration orphan - stripe + salesforce + intercom + notion + zendesk
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))


# ──────────────────────────────────────────────────────────────────────
# Noise pools (used across scenarios for adversarial volume)
# ──────────────────────────────────────────────────────────────────────

# Real-feeling company emails. The Acme variants are intentional
# collisions that test if the agent filters by exact email vs LIKE.
_NOISE_EMAILS: list[str] = [
    # Plausible business emails
    "ar@northwind-logi.example", "billing@globex.example",
    "ap@helix-bio.example", "finance@bottega-romano.example",
    "support@quantum-synth.io", "ops@vertex-mining.example",
    "team@helio-energy.example", "billing@delta-payments.example",
    "support@cobra-cybersec.example", "team@meridian-tech.example",
    "ar@hydra-finance.example", "ops@cascade-cloud.example",
    "billing@nexus-data.example", "support@orion-labs.example",
    "ap@helios-bio.example",  # Sounds like Helix Bio (typo trap)
    "finance@stellar-ai.example", "ops@phoenix-fund.example",
    "billing@apex-software.example", "support@summit-payments.example",
    "team@horizon-genomics.example",  # Sounds like Acme Genomics (industry collision)
    "ops@acme-logistics.example",  # The classic Acme name collision
    "ops@acme-consulting.example",  # Another Acme
    "billing@acme-fintech.example",  # Another Acme
]

_NOISE_COMPANIES: list[tuple[str, str]] = [
    # (company_name, primary_email)
    ("Northwind Logistics", "ar@northwind-logi.example"),
    ("Globex Software", "billing@globex.example"),
    ("Helix Bio", "ap@helix-bio.example"),
    ("Helios Bio", "ap@helios-bio.example"),  # Typo-trap of Helix
    ("Bottega Romano S.r.l.", "finance@bottega-romano.example"),
    ("Quantum Synth", "support@quantum-synth.io"),
    ("Quantum Synth Corp", "info@quantum-synth-corp.example"),  # Different entity
    ("Vertex Mining", "ops@vertex-mining.example"),
    ("Acme Logistics", "ops@acme-logistics.example"),  # Acme collision
    ("Acme Consulting", "ops@acme-consulting.example"),
    ("Acme Fintech", "billing@acme-fintech.example"),
    ("Helio Energy", "team@helio-energy.example"),
    ("Saga Foods", "billing@saga-foods.example"),  # Different from Saga Robotics
    ("Meridian Tech", "team@meridian-tech.example"),
    ("Cascade Cloud", "ops@cascade-cloud.example"),
    ("Orion Labs", "support@orion-labs.example"),
    ("Stellar AI", "finance@stellar-ai.example"),
    ("Phoenix Fund", "ops@phoenix-fund.example"),
    ("Apex Software", "billing@apex-software.example"),
    ("Summit Payments", "support@summit-payments.example"),
    ("Horizon Genomics", "team@horizon-genomics.example"),
    ("Hydra Finance", "ar@hydra-finance.example"),
    ("Nexus Data", "billing@nexus-data.example"),
    ("Delta Payments", "billing@delta-payments.example"),
    ("Cobra Cybersec", "support@cobra-cybersec.example"),
]


def _rand_email() -> str:
    return random.choice(_NOISE_EMAILS)


def _rand_company() -> tuple[str, str]:
    return random.choice(_NOISE_COMPANIES)


def _rand_ts_iso(year: int = 2026, month: int | None = None) -> str:
    """ISO 8601 timestamp string."""
    m = month if month else random.randint(1, 6)
    d = random.randint(1, 27)
    h = random.randint(0, 23)
    mi = random.randint(0, 59)
    return f"{year}-{m:02d}-{d:02d}T{h:02d}:{mi:02d}:00"


def _rand_ts_epoch(year: int = 2026, month: int | None = None) -> int:
    """Epoch-seconds timestamp (Intercom uses this)."""
    import datetime as _dt
    m = month if month else random.randint(1, 6)
    d = random.randint(1, 27)
    h = random.randint(0, 23)
    mi = random.randint(0, 59)
    return int(_dt.datetime(year, m, d, h, mi).timestamp())


def _maybe_null(value: Any, p: float = 0.3) -> Any:
    """Return value with probability (1-p), else None - for sparse fields."""
    return None if random.random() < p else value


# ──────────────────────────────────────────────────────────────────────
# Real-schema row factories
# Each function returns a dict whose KEYS match REAL Coral column names
# for that (source, table). Cols not provided default to None.
# ──────────────────────────────────────────────────────────────────────


def make_stripe_dispute(
    *,
    id: str,
    customer: str,
    charge: str,
    amount: int,
    reason: str,
    status: str = "needs_response",
    created: str | None = None,
    evidence_due_by: str | None = None,
    currency: str = "usd",
) -> dict[str, Any]:
    """Real stripe.disputes row (only the fields the agent will care about)."""
    return {
        "id": id,
        "amount": amount,
        "charge": charge,
        "created": created or _rand_ts_iso(),
        "currency": currency,
        "evidence_due_by": evidence_due_by,
        "is_charge_refundable": True,
        "livemode": True,
        "metadata": "",
        "object": "dispute",
        "reason": reason,
        "status": status,
        # Convenience denorm column (NOT in real Stripe - kept as extra)
        "customer": customer,
    }


def make_stripe_charge(
    *,
    id: str,
    customer: str,
    amount: int,
    status: str = "succeeded",
    created: str | None = None,
    currency: str = "usd",
    description: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "amount": amount,
        "amount_captured": amount if status == "succeeded" else 0,
        "amount_refunded": 0,
        "captured": status == "succeeded",
        "created": created or _rand_ts_iso(),
        "currency": currency,
        "customer": customer,
        "description": description,
        "disputed": False,
        "livemode": True,
        "object": "charge",
        "paid": status == "succeeded",
        "refunded": False,
        "status": status,
    }


def make_stripe_subscription(
    *,
    id: str,
    customer: str,
    status: str,
    cancel_at_period_end: bool = False,
    canceled_at: str | None = None,
    current_period_start: str | None = None,
    current_period_end: str | None = None,
    created: str | None = None,
    plan_nickname: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "cancel_at_period_end": cancel_at_period_end,
        "canceled_at": canceled_at,
        "collection_method": "charge_automatically",
        "created": created or _rand_ts_iso(),
        "current_period_start": current_period_start,
        "current_period_end": current_period_end,
        "customer": customer,
        "livemode": True,
        "object": "subscription",
        "status": status,
        # Extras (not in real Stripe subscriptions but useful for tests)
        "plan_nickname": plan_nickname,
    }


def make_stripe_customer(
    *,
    id: str,
    email: str,
    name: str | None = None,
    created: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "email": email,
        "name": name,
        "created": created or _rand_ts_iso(),
        "description": description,
        "delinquent": False,
        "livemode": True,
        "object": "customer",
    }


def make_stripe_invoice(
    *,
    id: str,
    customer: str,
    amount_due: int,
    amount_paid: int,
    status: str = "open",
    due_date: str | None = None,
    created: str | None = None,
    description: str | None = None,
    currency: str = "usd",
) -> dict[str, Any]:
    return {
        "id": id,
        "amount_due": amount_due,
        "amount_paid": amount_paid,
        "amount_remaining": amount_due - amount_paid,
        "currency": currency,
        "customer": customer,
        "due_date": due_date,
        "created": created or _rand_ts_iso(),
        "description": description,
        "livemode": True,
        "object": "invoice",
        "paid": amount_paid >= amount_due,
        "status": status,
    }


def make_intercom_conversation(
    *,
    id: str,
    source_subject: str,
    source_author_email: str,
    source_author_name: str | None = None,
    state: str = "closed",
    created_at: int | None = None,
    updated_at: int | None = None,
    source_body_snippet: str | None = None,  # Convenience (not in real schema)
) -> dict[str, Any]:
    """Real intercom.conversations row.

    NOTE: the real intercom.conversations table does NOT include the
    body text. Agents needing message content would typically join to
    `intercom.conversation_parts` or use the API's expand=conversation_parts.
    We add a `source_body_snippet` extra column for convenience so tests
    have one place to read the message intent. In real production an
    agent would have to make a second join.
    """
    ts = created_at or _rand_ts_epoch()
    return {
        "id": id,
        "title": source_subject,
        "state": state,
        "open": state == "open",
        "read": True,
        "priority": "not_priority",
        "created_at": ts,
        "updated_at": updated_at or ts + 3600,
        "source_type": "conversation",
        "source_delivered_as": "customer_initiated",
        "source_subject": source_subject,
        "source_author_type": "user",
        "source_author_email": source_author_email,
        "source_author_name": source_author_name or source_author_email.split("@")[0],
        "ai_agent_participated": False,
        # Extra - agent reads this for content, real Coral would JOIN
        "source_body_snippet": source_body_snippet,
    }


def make_intercom_contact(
    *,
    id: str,
    email: str,
    name: str | None = None,
    last_seen_at: int | None = None,
    last_replied_at: int | None = None,
    created_at: int | None = None,
) -> dict[str, Any]:
    ts = created_at or _rand_ts_epoch(2024)
    return {
        "id": id,
        "external_id": email,
        "role": "user",
        "email": email,
        "name": name or email.split("@")[0],
        "created_at": ts,
        "updated_at": ts + 86400,
        "signed_up_at": ts,
        "last_seen_at": last_seen_at or _rand_ts_epoch(2026, 5),
        "last_replied_at": last_replied_at,
        "has_hard_bounced": False,
        "unsubscribed_from_emails": False,
    }


def make_zendesk_user(
    *,
    id: int,
    email: str,
    name: str | None = None,
    organization_id: int | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "email": email,
        "name": name or email.split("@")[0],
        "organization_id": organization_id,
        "role": "end-user",
        "active": True,
        "created_at": _rand_ts_iso(2024),
        "updated_at": _rand_ts_iso(2026),
        "url": f"https://zd.example/api/v2/users/{id}.json",
        "verified": True,
    }


def make_zendesk_ticket(
    *,
    id: int,
    subject: str,
    description: str,
    status: str,
    requester_id: int,
    priority: str = "normal",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Real zendesk.tickets row. requester_id joins to zendesk.users."""
    return {
        "id": id,
        "subject": subject,
        "description": description,
        "status": status,
        "priority": priority,
        "type": "question",
        "requester_id": requester_id,
        "submitter_id": requester_id,
        "assignee_id": None,
        "organization_id": None,
        "group_id": None,
        "created_at": created_at or _rand_ts_iso(),
        "updated_at": created_at or _rand_ts_iso(),
        "tags": "[]",
        "via": "web",
        "url": f"https://zd.example/api/v2/tickets/{id}.json",
        "external_id": None,
    }


def make_salesforce_account(
    *,
    id: str,
    name: str,
    industry: str | None = None,
    annual_revenue: int | None = None,
    number_of_employees: int | None = None,
    owner_id: str | None = None,
    billing_country: str | None = None,
    type_: str = "Customer - Direct",
) -> dict[str, Any]:
    """Real salesforce.accounts row."""
    return {
        "id": id,
        "name": name,
        "type": type_,
        "industry": industry,
        "annual_revenue": annual_revenue,
        "number_of_employees": number_of_employees,
        "phone": None,
        "website": None,
        "billing_city": None,
        "billing_country": billing_country,
        "owner_id": owner_id,
        "created_date": _rand_ts_iso(2024),
    }


def make_salesforce_opportunity(
    *,
    id: str,
    name: str,
    stage_name: str,
    amount: int,
    close_date: str,
    account_id: str,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "stage_name": stage_name,
        "amount": amount,
        "close_date": close_date,
        "account_id": account_id,
        "owner_id": None,
        "probability": 100 if stage_name == "Closed Won" else 50,
        "type": "Renewal" if "Renewal" in name else "New Business",
        "is_closed": stage_name in ("Closed Won", "Closed Lost"),
        "is_won": stage_name == "Closed Won",
        "created_date": _rand_ts_iso(2024),
    }


def make_hubspot_company(
    *,
    id: str,
    name: str,
    domain: str | None = None,
    industry: str | None = None,
    annualrevenue: int | None = None,
    numberofemployees: int | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    """Real hubspot.companies row."""
    return {
        "id": id,
        "name": name,
        "domain": domain,
        "industry": industry,
        "city": None,
        "country": country,
        "hubspot_owner_id": None,
        "numberofemployees": numberofemployees,
        "annualrevenue": annualrevenue,
        "created_at": _rand_ts_iso(2024),
        "updated_at": _rand_ts_iso(2026),
    }


def make_hubspot_deal(
    *,
    id: str,
    dealname: str,
    dealstage: str,
    amount: int,
    closedate: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "dealname": dealname,
        "dealstage": dealstage,
        "pipeline": "default",
        "amount": amount,
        "closedate": closedate,
        "hubspot_owner_id": None,
        "created_at": _rand_ts_iso(2024),
        "updated_at": _rand_ts_iso(2026),
    }


def make_notion_page(
    *,
    id: str,
    title: str,
    body: str,
    status: str = "current",
    tags: str = "",
    last_edited_time: str | None = None,
) -> dict[str, Any]:
    """Real notion.pages row. Title + body conventionally live in `properties`
    as a JSON blob, but for queryability we also surface them as extras."""
    return {
        "id": id,
        "object": "page",
        "created_time": _rand_ts_iso(2025),
        "last_edited_time": last_edited_time or _rand_ts_iso(2026),
        "url": f"https://notion.example/{id}",
        "public_url": None,
        "in_trash": False,
        "parent": "workspace",
        # `properties` is a real Coral col but normally a JSON blob; we
        # also surface title/body/status as queryable extras.
        "properties": f'{{"title": "{title}"}}',
        # Extras - agents read these directly
        "title": title,
        "body": body,
        "status": status,
        "tags": tags,
    }


def make_gmail_thread(
    *,
    id: str,
    snippet: str,
    history_id: str = "1",
    label_ids: str = "INBOX",
) -> dict[str, Any]:
    """Real gmail.threads row.

    Real gmail threads only expose 5 cols including a `snippet` (text preview).
    For richer content we'd JOIN to gmail.messages - but real gmail.messages
    is also limited (4 cols). For test purposes we treat snippet as the
    content surface.
    """
    return {
        "id": id,
        "snippet": snippet,
        "history_id": history_id,
        "label_ids": label_ids,
        "q": "",
    }


def make_pagerduty_incident(
    *,
    id: str,
    title: str,
    severity: str,
    status: str,
    created_at: str,
    resolved_at: str | None = None,
    service_id: str | None = None,
    duration_seconds: int | None = None,
) -> dict[str, Any]:
    """Real pagerduty.incidents row (74 cols total; we set the salient ones)."""
    return {
        "id": id,
        "incident_number": int(id.replace("INC-", "").replace("PD", "") or "0", 10) if id.startswith("INC-") else 0,
        "title": title,
        "description": title,
        "created_at": created_at,
        "updated_at": resolved_at or created_at,
        "status": status,
        "urgency": "high" if severity in ("SEV-1", "SEV-2") else "low",
        "resolved_at": resolved_at,
        "service__id": service_id,
        # Severity isn't a top-level PagerDuty field; we'll surface it as extra
        "severity": severity,
        "duration_seconds": duration_seconds,
    }


def make_datadog_monitor(
    *,
    id: int,
    name: str,
    type_: str,
    status: str,
    message: str,
    tags: str = "",
) -> dict[str, Any]:
    """Real datadog.monitors row."""
    return {
        "id": id,
        "name": name,
        "type": type_,
        "query": f"avg(last_5m):{name} > 1000",
        "status": status,
        "message": message,
        "created": _rand_ts_iso(2025),
        "modified": _rand_ts_iso(2026),
        "tags": tags,
    }


def make_sentry_issue(
    *,
    id: str,
    title: str,
    status: str,
    level: str,
    count: int,
    first_seen: str,
    last_seen: str,
    project: str,
) -> dict[str, Any]:
    """Real sentry.issues row."""
    return {
        "id": id,
        "short_id": id,
        "title": title,
        "status": status,
        "level": level,
        "count": count,
        "user_count": min(count, 50),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "project": project,
        "query": "",
    }


# ──────────────────────────────────────────────────────────────────────
# Noise generators - high-volume adversarial rows
# ──────────────────────────────────────────────────────────────────────


def noise_stripe_customers(n: int, seed: int = 1) -> list[dict[str, Any]]:
    random.seed(seed)
    out = []
    for i in range(n):
        company, email = _rand_company()
        out.append(
            make_stripe_customer(
                id=f"cus_{i:06d}{random.randint(100, 999)}",
                email=email,
                name=company,
                created=_rand_ts_iso(2024 + (i % 3)),
            )
        )
    return out


def noise_stripe_disputes(n: int, seed: int = 2) -> list[dict[str, Any]]:
    """Random old disputes for unrelated customers."""
    random.seed(seed)
    reasons = ["fraudulent", "duplicate", "subscription_canceled",
               "product_not_received", "credit_not_processed", "general"]
    statuses = ["won", "lost", "warning_needs_response", "warning_under_review"]
    out = []
    for i in range(n):
        _, _email = _rand_company()
        out.append(
            make_stripe_dispute(
                id=f"dp_noise_{i:05d}",
                customer=f"cus_noise_{i:05d}",
                charge=f"ch_noise_{i:05d}",
                amount=random.choice([2400, 4200, 8200, 12000, 24000, 50000, 99900]),
                reason=random.choice(reasons),
                status=random.choice(statuses),
                created=_rand_ts_iso(2025 + (i % 2)),
            )
        )
    return out


def noise_intercom_conversations(
    n: int, seed: int = 3
) -> list[dict[str, Any]]:
    random.seed(seed)
    subjects = [
        "Pricing question", "Feature request", "How to invite teammates",
        "Webhook setup", "Account help", "Billing question",
        "Cancel my subscription",  # NOTE: red-herring for cancel queries
        "Refund request",
        "Demo follow-up", "Plan question", "API rate limits",
        "Integration broken", "Renewal date question",
    ]
    bodies = [
        "Hi, I'd like to learn more about pricing.",
        "Can you walk me through how to set up the webhook?",
        "Need help inviting users.",
        "We want to cancel our trial - please don't renew us.",
        "Looking at competing tools, considering moving.",
        "Got an unexpected charge - can you help?",
        "The dashboard is loading slowly.",
        "Do you support SAML?",
    ]
    out = []
    for i in range(n):
        out.append(
            make_intercom_conversation(
                id=str(20000 + i),
                source_subject=random.choice(subjects),
                source_author_email=_rand_email(),
                state=random.choice(["closed", "open", "snoozed"]),
                created_at=_rand_ts_epoch(year=2025 + (i % 2)),
                source_body_snippet=random.choice(bodies),
            )
        )
    return out


def noise_zendesk_tickets(
    n: int, seed: int = 4, user_id_pool: list[int] | None = None
) -> list[dict[str, Any]]:
    random.seed(seed)
    subjects = [
        "How do I export reports?", "Add a new user", "Reset password",
        "Question about API rate limits", "Slow dashboard loading",
        "Cancel one of my seats",  # cancel red-herring
        "Request: SAML SSO support",
        "Bug: graphs not rendering", "Onboarding follow-up",
        "Refund for accidental upgrade", "Integration broken",
        "Plan upgrade question",
    ]
    descs = [
        "Customer asked how to export the monthly report PDF.",
        "Please add user@example.com to our org with viewer role.",
        "Forgot password, can't access dashboard.",
        "Hitting 429s every few minutes.",
    ]
    pool = user_id_pool or list(range(900000, 900050))
    statuses = ["open", "pending", "solved", "closed"]
    out = []
    for i in range(n):
        out.append(
            make_zendesk_ticket(
                id=70000 + i,
                subject=random.choice(subjects),
                description=random.choice(descs),
                status=random.choice(statuses),
                requester_id=random.choice(pool),
                created_at=_rand_ts_iso(2025 + (i % 2)),
            )
        )
    return out


def noise_salesforce_accounts(n: int, seed: int = 5) -> list[dict[str, Any]]:
    random.seed(seed)
    industries = ["biotech", "fintech", "logistics", "software", "ai",
                  "media", "consulting", "manufacturing"]
    out = []
    for i in range(n):
        company, _ = _rand_company()
        out.append(
            make_salesforce_account(
                id=f"001N{i:08d}",
                name=company,
                industry=random.choice(industries),
                annual_revenue=random.choice([500000, 1200000, 5000000,
                                              12000000, 30000000]),
                number_of_employees=random.choice([10, 50, 100, 200, 500]),
                billing_country=random.choice(["USA", "UK", "Germany",
                                               "India", "Italy"]),
            )
        )
    return out


def noise_hubspot_companies(n: int, seed: int = 6) -> list[dict[str, Any]]:
    random.seed(seed)
    out = []
    for i in range(n):
        company, _ = _rand_company()
        out.append(
            make_hubspot_company(
                id=str(50000 + i),
                name=company,
                domain=f"{company.lower().replace(' ', '-')}.example",
                industry=random.choice(["biotech", "fintech", "software"]),
                annualrevenue=random.choice([1000000, 5000000, 20000000]),
                numberofemployees=random.choice([20, 50, 200]),
            )
        )
    return out


def noise_notion_pages(n: int, seed: int = 7) -> list[dict[str, Any]]:
    """Notion pages that look refund/policy related but aren't authoritative."""
    random.seed(seed)
    titles = [
        "Refunds - DEPRECATED 2024 version",
        "Refunds customer-facing FAQ",
        "Onboarding for new finance hires",
        "Quarterly all-hands Q1 2026 notes (mentions refunds)",
        "Sales objections handbook",
        "CSM cancel-save playbook",
        "Engineering on-call runbook",
        "AR aging weekly digest",
        "Legal corp filings 2024",
        "Marketing pricing page draft",
        "HR PTO policy",
        "Notes from board meeting Feb 2025",
        "Customer success quarterly review",
    ]
    bodies = [
        "Archived. See newer version.",
        "Customer-facing copy only. NOT internal policy.",
        "First-week reading.",
        "Pricing run-rate notes.",
        "Sales-stage objection handling.",
        "When an ACTIVE customer wants to cancel - NOT for disputes.",
        "How to handle pager alerts. Unrelated to billing.",
    ]
    statuses = ["archived", "current", "draft", "current", "current"]
    out = []
    for i in range(n):
        out.append(
            make_notion_page(
                id=f"n_noise_{i:04d}",
                title=titles[i % len(titles)],
                body=bodies[i % len(bodies)],
                status=statuses[i % len(statuses)],
                tags=random.choice(["refunds,deprecated", "refunds,faq",
                                    "onboarding", "sales", "csm", "engineering"]),
            )
        )
    return out


def noise_pagerduty_incidents(n: int, seed: int = 8) -> list[dict[str, Any]]:
    random.seed(seed)
    titles = [
        "API gateway latency elevated",
        "Database connection pool exhausted",
        "Worker queue depth above threshold",
        "Cache hit rate dropped",
        "CDN error rate spike",
        "Auth service degraded",
        "Search indexer behind",
    ]
    out = []
    for i in range(n):
        sev = random.choice(["SEV-1", "SEV-2", "SEV-3", "SEV-4"])
        out.append(
            make_pagerduty_incident(
                id=f"PD-INC-{40000 + i:05d}",
                title=random.choice(titles),
                severity=sev,
                status=random.choice(["resolved", "acknowledged", "triggered"]),
                created_at=_rand_ts_iso(2025 + (i % 2), month=random.randint(1, 12)),
                resolved_at=_rand_ts_iso(2025 + (i % 2), month=random.randint(1, 12)),
                service_id=f"PSVC-{random.randint(100, 200)}",
                duration_seconds=random.randint(120, 14400),
            )
        )
    return out


def noise_datadog_monitors(n: int, seed: int = 9) -> list[dict[str, Any]]:
    random.seed(seed)
    monitor_types = ["query alert", "metric alert", "log alert", "service check"]
    out = []
    for i in range(n):
        out.append(
            make_datadog_monitor(
                id=80000 + i,
                name=f"monitor-{i:03d}",
                type_=random.choice(monitor_types),
                status=random.choice(["OK", "Alert", "Warn"]),
                message=random.choice([
                    "P95 latency above SLA",
                    "Error rate threshold breached",
                    "Disk fill projected within 24h",
                ]),
                tags=random.choice([
                    "env:prod,team:platform",
                    "env:staging,team:billing",
                    "env:prod,team:auth",
                ]),
            )
        )
    return out


def noise_sentry_issues(n: int, seed: int = 10) -> list[dict[str, Any]]:
    random.seed(seed)
    titles = [
        "TypeError in /v1/reports endpoint",
        "NullPointerException in legacy reporting",
        "OutOfMemoryError in batch worker",
        "TimeoutException in PDF export",
        "ConnectionResetError in API gateway",
        "JSON decode error in webhook handler",
    ]
    levels = ["error", "warning", "info"]
    projects = ["api-svc", "billing-svc", "reporting-v1",
                "reporting-v3", "auth-svc", "ingest"]
    out = []
    for i in range(n):
        out.append(
            make_sentry_issue(
                id=f"SENT-{20000 + i:05d}",
                title=random.choice(titles),
                status=random.choice(["resolved", "unresolved", "ignored"]),
                level=random.choice(levels),
                count=random.randint(1, 200),
                first_seen=_rand_ts_iso(2025 + (i % 2)),
                last_seen=_rand_ts_iso(2025 + (i % 2)),
                project=random.choice(projects),
            )
        )
    return out


def noise_gmail_threads(n: int, seed: int = 11) -> list[dict[str, Any]]:
    random.seed(seed)
    snippets = [
        "Welcome to the platform!",
        "Q3 forecast review next week",
        "Re: pricing question",
        "Renewal reminder - 30 days",
        "AR follow-up: invoice past due",
        "Please cancel my account",  # red-herring
        "We're not renewing this year - cancellation effective",  # red-herring
        "Webinar invite",
        "Customer success quarterly review",
    ]
    out = []
    for i in range(n):
        out.append(
            make_gmail_thread(
                id=f"gm_noise_{i:05d}",
                snippet=random.choice(snippets),
                history_id=str(100000 + i),
            )
        )
    return out


# Scenarios live in coral_scenarios_data.py to keep this file focused on
# row factories. Import them via `from coral_scenarios_data import SCENARIOS_CORAL`.
