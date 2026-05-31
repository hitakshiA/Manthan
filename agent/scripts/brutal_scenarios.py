"""Brutal-data scenarios - DuckDB-backed, real volume + noise.

Each scenario provides a duckdb_world: dict[source][table][rows]. The
mock spins up an in-memory DuckDB and the agent's SQL runs against it
for real. The agent has to:
  - Filter by customer email/id/timestamp
  - Read body text (not pre-extracted summaries) to judge intent
  - Aggregate with COUNT/MAX/ORDER BY
  - Pick the right policy doc out of many similarly-named ones
  - Distinguish records of multiple superficially-similar customers

Goal: replicate how messy real B2B SaaS data actually looks. No
answer-keys pre-extracted into named columns. The data is the data.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# scripts/ isn't a package; bolt to sys.path so we can re-use the
# Scenario dataclass from scenarios.py.
sys.path.insert(0, str(Path(__file__).parent))
from scenarios import Scenario

# ----------------------------------------------------------------------
# Noise-generation helpers
# ----------------------------------------------------------------------

_OTHER_CUSTOMER_EMAILS = [
    "ops@northwind-logi.example", "billing@globex.example",
    "ar@saga-robotics.example", "ap@helix-bio.example",
    "joe@joescoffee-pdx.example", "support@quantum-synth.io",
    "finance@bottega-romano.example", "admin@acme-logistics.example",  # collides on "acme"
    "team@helio-energy.example", "ops@vertex-mining.example",
    "billing@delta-payments.example", "support@cobra-cybersec.example",
    "team@meridian-tech.example", "ar@hydra-finance.example",
]

_NOISE_TICKET_SUBJECTS = [
    "How do I export reports?", "Add a new user", "Reset password",
    "Question about API rate limits", "Billing question - Q1 invoice",
    "Slow dashboard loading", "Cancel one of my seats",
    "Request: SAML SSO support", "Bug: graphs not rendering",
    "Onboarding call follow-up", "Renewal date question",
    "Refund for accidental upgrade", "Integration broken",
]

_NOISE_INTERCOM_SUBJECTS = [
    "Pricing question", "Feature request", "Onboarding help",
    "Plan question", "Cancel subscription",  # NOTE: this is for ANOTHER customer
    "Billing receipt request", "How to invite teammates",
    "Webhook setup", "Help with dashboard", "Account merging",
]

_NOISE_SLACK_TEXTS = [
    "anyone seen the Q3 forecast?", "FYI: API latency spike at 3pm",
    "team lunch tomorrow", "merging deploy queue",
    "@channel pls review PR-2241",
    "Helio Energy renewal looks shaky", "Acme Logistics churn risk flagged",  # red herring - wrong "Acme"
    "Customer dispute on Northwind invoice - handling", "Vertex Mining onboarding stuck",
    "Quantum Synth fraud-review approved", "Meridian Tech expansion deal closing",
]

_DEPRECATED_NOTION_PAGES = [
    {
        "id": "n_0001",
        "title": "Refunds policy - DEPRECATED 2024 version",
        "body": "Historical SOP from 2024. Refunds capped at 30 days. Note: superseded by 2026 SOP - do not apply.",
        "status": "archived",
        "updated_at": "2024-08-12T00:00:00",
        "tags": "refunds,deprecated",
    },
    {
        "id": "n_0002",
        "title": "Refunds - customer-facing FAQ",
        "body": "Public-facing FAQ for customer self-help. Talk points only, NOT internal policy.",
        "status": "current",
        "updated_at": "2025-09-01T00:00:00",
        "tags": "refunds,public,faq",
    },
    {
        "id": "n_0003",
        "title": "Onboarding for new finance hires",
        "body": "First-week reading. Mentions refunds but is HR-flavored, not authoritative.",
        "status": "current",
        "updated_at": "2025-12-01T00:00:00",
        "tags": "onboarding,refunds",
    },
    {
        "id": "n_0004",
        "title": "Quarterly all-hands Q1 2026 notes",
        "body": "Mentioned: refunds run-rate is down 12% YoY. CFO targets further reduction. Not a policy doc.",
        "status": "current",
        "updated_at": "2026-01-25T00:00:00",
        "tags": "all-hands,refunds",
    },
]


def _noise_intercom(n: int, base_id: int = 1000) -> list[dict[str, Any]]:
    """N unrelated Intercom conversations from other customers."""
    out: list[dict[str, Any]] = []
    for i in range(n):
        email = _OTHER_CUSTOMER_EMAILS[i % len(_OTHER_CUSTOMER_EMAILS)]
        subject = _NOISE_INTERCOM_SUBJECTS[i % len(_NOISE_INTERCOM_SUBJECTS)]
        # Some bodies mention "cancel" - but for unrelated customers.
        body = (
            "We want to cancel our trial." if "Cancel" in subject
            else f"Hi team, just a quick question about {subject.lower()}."
        )
        out.append({
            "id": f"ic_{base_id + i:05d}",
            "contact_email": email,
            "subject": subject,
            "body": body,
            "status": "open" if i % 3 == 0 else "closed",
            "created_at": f"2026-{(i % 5) + 1:02d}-{(i % 27) + 1:02d}T{(i % 23):02d}:00:00",
        })
    return out


def _noise_zendesk(n: int, base_id: int = 5000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(n):
        out.append({
            "id": f"zd_{base_id + i:05d}",
            "requester_email": _OTHER_CUSTOMER_EMAILS[i % len(_OTHER_CUSTOMER_EMAILS)],
            "subject": _NOISE_TICKET_SUBJECTS[i % len(_NOISE_TICKET_SUBJECTS)],
            "status": ["open", "pending", "solved", "closed"][i % 4],
            "updated_at": f"2026-{(i % 5) + 1:02d}-{(i % 27) + 1:02d}T{(i % 23):02d}:00:00",
        })
    return out


def _noise_slack(n: int, base_id: int = 10000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    channels = ["cs-escalations", "ar", "engineering", "general", "growth"]
    users = ["amelia", "priya", "jordan", "rohan", "sarah", "gina", "marcus"]
    for i in range(n):
        out.append({
            "ts": f"2026-{(i % 5) + 1:02d}-{(i % 27) + 1:02d}T{(i % 23):02d}:{(i % 59):02d}:00",
            "channel": channels[i % len(channels)],
            "user": users[i % len(users)],
            "text": _NOISE_SLACK_TEXTS[i % len(_NOISE_SLACK_TEXTS)],
        })
    return out


# ──────────────────────────────────────────────────────────────────────
# S01-BRUTAL - Acme friendly fraud, real volume + noise
# ──────────────────────────────────────────────────────────────────────
#
# Ground truth (unchanged from flat S01):
#   - Customer claims they cancelled an annual renewal ($4,200)
#   - In reality: no formal cancel request anywhere
#   - One 2-month-old Intercom convo says "we're evaluating whether to
#     continue" - informal, not formal
#   - Subscription still active, no cancel_at_period_end set
#   - Customer was active 5 days before the dispute (Posthog)
#   - Refunds SOP says FIGHT when no formal cancel + recent usage
#   - DECISION: fight
#
# Brutal twists:
#   - Intercom: 60 conversations total, 5 from this customer, 55 noise.
#     Two of the 55 noise rows have "cancel" in body or subject (from
#     OTHER customers).
#   - Zendesk: 40 tickets, 2 from this customer (neither cancel-related);
#     several noise tickets mention "cancel" or "refund" from others.
#   - Slack: 80 messages from cs-escalations + others. Two mention "Acme"
#     - one for Acme Genomics (this customer), one for Acme Logistics
#     (a different customer entirely).
#   - Notion: 8 pages, only refunds-2026-sop is the right policy. There's
#     a 2024 deprecated one, a customer-facing FAQ, a quarterly notes
#     doc, etc.
#   - Stripe: customer has 4 historical subscriptions, only 1 active.
#   - Posthog: 30+ event records, agent must aggregate to find last
#     active timestamp.
#   - Sentry: 6 issues, 1 is the red herring legacy-reporting-v1 incident
#     from 60 days ago on a product area this customer doesn't use.

_THIS_EMAIL = "ops@acme-genomics.example"
_THIS_CUSTOMER_ID = "cus_AcmeGn"


_S01_BRUTAL_WORLD: dict[str, dict[str, list[dict[str, Any]]]] = {
    # ─────────── stripe ───────────
    "stripe": {
        "disputes": [
            # THE TARGET
            {
                "id": "dp_3MqAcmeRen",
                "customer": _THIS_CUSTOMER_ID,
                "customer_email": _THIS_EMAIL,
                "charge": "ch_3MqAcmeRen",
                "amount_minor": 420000,
                "currency": "usd",
                "reason": "subscription_canceled",
                "status": "needs_response",
                "created": "2026-05-09T11:02:00",
                "evidence_due_by": "2026-06-12T00:00:00",
            },
            # Noise - other customers' disputes from different periods
            {"id": "dp_001", "customer": "cus_Joe01", "customer_email": "joe@joescoffee-pdx.example", "charge": "ch_001", "amount_minor": 4200, "currency": "usd", "reason": "fraudulent", "status": "lost", "created": "2026-04-04T11:00:00", "evidence_due_by": "2026-05-20T00:00:00"},
            {"id": "dp_002", "customer": "cus_AcmeLog", "customer_email": "admin@acme-logistics.example", "charge": "ch_002", "amount_minor": 31200, "currency": "usd", "reason": "duplicate", "status": "won", "created": "2026-02-12T14:21:00", "evidence_due_by": "2026-03-15T00:00:00"},
            {"id": "dp_003", "customer": "cus_Helio", "customer_email": "team@helio-energy.example", "charge": "ch_003", "amount_minor": 89400, "currency": "usd", "reason": "credit_not_processed", "status": "won", "created": "2025-12-19T10:00:00", "evidence_due_by": "2026-01-10T00:00:00"},
            {"id": "dp_004", "customer": "cus_Vertex", "customer_email": "ops@vertex-mining.example", "charge": "ch_004", "amount_minor": 24000, "currency": "usd", "reason": "subscription_canceled", "status": "lost", "created": "2026-03-22T09:15:00", "evidence_due_by": "2026-04-20T00:00:00"},
            {"id": "dp_005", "customer": "cus_Globex", "customer_email": "billing@globex.example", "charge": "ch_005", "amount_minor": 820000, "currency": "usd", "reason": "incorrect_amount", "status": "open", "created": "2026-05-01T16:00:00", "evidence_due_by": "2026-06-15T00:00:00"},
            {"id": "dp_006", "customer": "cus_QSynth", "customer_email": "support@quantum-synth.io", "charge": "ch_006", "amount_minor": 5000000, "currency": "usd", "reason": "fraudulent", "status": "open", "created": "2026-06-13T15:30:00", "evidence_due_by": "2026-07-15T00:00:00"},
            {"id": "dp_007", "customer": "cus_NorthW", "customer_email": "ar@northwind-logi.example", "charge": "ch_007", "amount_minor": 225000, "currency": "usd", "reason": "sla_breach", "status": "open", "created": "2026-05-20T10:00:00", "evidence_due_by": "2026-06-30T00:00:00"},
        ],
        "charges": [
            # This case
            {"id": "ch_3MqAcmeRen", "customer": _THIS_CUSTOMER_ID, "amount_minor": 420000, "status": "succeeded", "payment_method": "card_visa_4242", "created": "2026-05-09T11:02:00"},
            # Acme prior charges (history)
            {"id": "ch_AcmeY24", "customer": _THIS_CUSTOMER_ID, "amount_minor": 420000, "status": "succeeded", "payment_method": "card_visa_4242", "created": "2025-05-09T11:02:00"},
            {"id": "ch_AcmeY23", "customer": _THIS_CUSTOMER_ID, "amount_minor": 360000, "status": "succeeded", "payment_method": "card_visa_4242", "created": "2024-05-09T11:02:00"},
            # Noise charges from other customers
            {"id": "ch_001", "customer": "cus_Joe01", "amount_minor": 4200, "status": "succeeded", "payment_method": "card_mc_8021", "created": "2026-04-04T11:00:00"},
            {"id": "ch_002", "customer": "cus_AcmeLog", "amount_minor": 31200, "status": "succeeded", "payment_method": "card_visa_1122", "created": "2026-02-12T14:21:00"},
            {"id": "ch_003", "customer": "cus_Helio", "amount_minor": 89400, "status": "succeeded", "payment_method": "ach", "created": "2025-12-19T10:00:00"},
            {"id": "ch_004", "customer": "cus_Vertex", "amount_minor": 24000, "status": "refunded", "payment_method": "card_visa_3344", "created": "2026-03-22T09:15:00"},
            {"id": "ch_005", "customer": "cus_Globex", "amount_minor": 820000, "status": "succeeded", "payment_method": "ach", "created": "2026-05-01T16:00:00"},
        ],
        "subscriptions": [
            # THE ACTIVE ONE for Acme
            {
                "id": "sub_AcmeGn_curr",
                "customer": _THIS_CUSTOMER_ID,
                "status": "active",
                "plan": "Pro Annual",
                "cancel_at_period_end": False,
                "canceled_at": None,
                "current_period_start": "2026-05-09T00:00:00",
                "current_period_end": "2027-05-09T00:00:00",
                "created": "2024-05-09T11:02:00",
                "collection_method": "charge_automatically",
            },
            # Acme historical (older, ended naturally)
            {"id": "sub_AcmeGn_2024", "customer": _THIS_CUSTOMER_ID, "status": "ended", "plan": "Pro Annual", "cancel_at_period_end": False, "canceled_at": "2024-05-09T00:00:00", "current_period_start": "2023-05-09T00:00:00", "current_period_end": "2024-05-09T00:00:00", "created": "2023-05-09T11:02:00", "collection_method": "charge_automatically"},
            {"id": "sub_AcmeGn_trial", "customer": _THIS_CUSTOMER_ID, "status": "canceled", "plan": "Trial", "cancel_at_period_end": False, "canceled_at": "2023-04-30T11:02:00", "current_period_start": "2023-04-15T00:00:00", "current_period_end": "2023-04-30T00:00:00", "created": "2023-04-15T11:02:00", "collection_method": "send_invoice"},
            # Noise from other customers - including ones that DID cancel (to test if agent picks the right sub)
            {"id": "sub_QSynth", "customer": "cus_QSynth", "status": "trialing", "plan": "Pro Annual", "cancel_at_period_end": False, "canceled_at": None, "current_period_start": "2026-05-22T00:00:00", "current_period_end": "2027-05-22T00:00:00", "created": "2026-05-22T09:00:00", "collection_method": "send_invoice"},
            {"id": "sub_Vertex", "customer": "cus_Vertex", "status": "canceled", "plan": "Pro Monthly", "cancel_at_period_end": False, "canceled_at": "2026-03-21T00:00:00", "current_period_start": "2026-02-22T00:00:00", "current_period_end": "2026-03-22T00:00:00", "created": "2025-08-22T09:00:00", "collection_method": "charge_automatically"},
            {"id": "sub_Saga_new", "customer": "cus_newSaga", "status": "active", "plan": "Pro Annual", "cancel_at_period_end": False, "canceled_at": None, "current_period_start": "2026-03-12T00:00:00", "current_period_end": "2027-03-12T00:00:00", "created": "2026-03-12T11:00:00", "collection_method": "charge_automatically"},
            {"id": "sub_Saga_old", "customer": "cus_oldSaga", "status": "active", "plan": "Pro Annual", "cancel_at_period_end": True, "canceled_at": None, "current_period_start": "2026-06-04T00:00:00", "current_period_end": "2027-06-04T00:00:00", "created": "2024-03-12T11:00:00", "collection_method": "charge_automatically"},
        ],
        "refunds": [
            {"id": "rf_001", "customer": "cus_AcmeLog", "amount_minor": 31200, "reason": "duplicate_charge", "created": "2026-02-14T11:00:00"},
            {"id": "rf_002", "customer": "cus_Bottega", "amount_minor": 90000, "reason": "tax_error", "created": "2026-05-25T11:00:00"},
        ],
        "customers": [
            {"id": _THIS_CUSTOMER_ID, "email": _THIS_EMAIL, "name": "Acme Genomics", "created": "2023-04-15T11:02:00", "metadata_account_external_id": "001AcmeGn"},
            {"id": "cus_AcmeLog", "email": "admin@acme-logistics.example", "name": "Acme Logistics", "created": "2024-09-01T11:02:00", "metadata_account_external_id": "001AcmeLog"},
            {"id": "cus_Joe01", "email": "joe@joescoffee-pdx.example", "name": "Joe's Coffee", "created": "2026-04-04T10:00:00", "metadata_account_external_id": None},
            {"id": "cus_QSynth", "email": "support@quantum-synth.io", "name": "Quantum Synth", "created": "2026-05-22T09:00:00", "metadata_account_external_id": "001QSynth"},
            {"id": "cus_Globex", "email": "billing@globex.example", "name": "Globex Software", "created": "2023-01-01T10:00:00", "metadata_account_external_id": "001Globex"},
        ],
    },
    # ─────────── salesforce ───────────
    "salesforce": {
        "accounts": [
            {
                "id": "001AcmeGn",
                "name": "Acme Genomics",
                "email": _THIS_EMAIL,
                "plan": "Pro Annual",
                "arr_minor": 420000,
                "health": "yellow",
                "nps_last": 6,
                "csm_owner": "priya@us",
                "renewal_date": "2027-05-09",
                "account_owner_notes": "Asked about data export in early March. Priya noted possible churn risk but no formal action requested. Renewed normally in May.",
                "industry": "genomics",
                "strategic_flag": False,
            },
            {"id": "001AcmeLog", "name": "Acme Logistics", "email": "admin@acme-logistics.example", "plan": "Standard Monthly", "arr_minor": 24000, "health": "red", "nps_last": 3, "csm_owner": "marcus@us", "renewal_date": "2026-09-01", "account_owner_notes": "Churn risk - actively shopping competitors.", "industry": "logistics", "strategic_flag": False},
            {"id": "001Globex", "name": "Globex Software", "email": "billing@globex.example", "plan": "Pro Annual", "arr_minor": 4000000, "health": "green", "nps_last": 9, "csm_owner": "mark@us", "renewal_date": "2026-12-31", "account_owner_notes": "Expansion expected Q4.", "industry": "software", "strategic_flag": True},
            {"id": "001NorthW", "name": "Northwind Logistics", "email": "ar@northwind-logi.example", "plan": "Enterprise Annual", "arr_minor": 10800000, "health": "green", "nps_last": 8, "csm_owner": "rohan@us", "renewal_date": "2026-11-01", "account_owner_notes": "Stable.", "industry": "logistics", "strategic_flag": True},
            {"id": "001Helix", "name": "Helix Bio", "email": "ap@helix-bio.example", "plan": "Enterprise Annual", "arr_minor": 13400000, "health": "red", "nps_last": 4, "csm_owner": "sarah@us", "renewal_date": "2026-08-15", "account_owner_notes": "AR escalation in progress.", "industry": "biotech", "strategic_flag": False},
        ],
        "opportunities": [
            {"id": "opp_AcmeGn_2024", "account_id": "001AcmeGn", "stage": "Closed Won", "amount_minor": 360000, "close_date": "2024-05-09", "type": "New"},
            {"id": "opp_AcmeGn_2025", "account_id": "001AcmeGn", "stage": "Closed Won", "amount_minor": 420000, "close_date": "2025-05-09", "type": "Renewal"},
            {"id": "opp_AcmeGn_2026", "account_id": "001AcmeGn", "stage": "Closed Won", "amount_minor": 420000, "close_date": "2026-05-09", "type": "Renewal"},
            {"id": "opp_Globex_2026", "account_id": "001Globex", "stage": "Closed Won", "amount_minor": 4000000, "close_date": "2026-01-15", "type": "New"},
            {"id": "opp_NorthW_2025", "account_id": "001NorthW", "stage": "Closed Won", "amount_minor": 10800000, "close_date": "2025-11-01", "type": "Renewal"},
        ],
    },
    # ─────────── intercom - 60 rows total, 5 ours, 55 noise ───────────
    "intercom": {
        "conversations": [
            # ours - 5 rows for ops@acme-genomics.example
            {
                "id": "ic_acme_001",
                "contact_email": _THIS_EMAIL,
                "subject": "Data export options",
                "body": (
                    "Hi team - we're evaluating whether to continue with you for another year "
                    "and need to understand what our data export options look like. Could you "
                    "walk us through the formats? We are not planning to cancel right now, just "
                    "want to know what's available in case our review comes back negative. - Ops, Acme"
                ),
                "status": "closed",
                "created_at": "2026-03-08T14:00:00",
            },
            {
                "id": "ic_acme_002",
                "contact_email": _THIS_EMAIL,
                "subject": "Re: Data export options",
                "body": (
                    "Thanks for the walkthrough - that's helpful. Looping our analytics lead "
                    "in. We'll come back to you if we need anything else. No action needed "
                    "for now."
                ),
                "status": "closed",
                "created_at": "2026-03-09T10:22:00",
            },
            {
                "id": "ic_acme_003",
                "contact_email": _THIS_EMAIL,
                "subject": "Q1 check-in: pricing flexibility",
                "body": (
                    "Could we get a quick call to review our pricing tier? We're growing the "
                    "genomics team and may want to add seats in Q3. Not urgent."
                ),
                "status": "closed",
                "created_at": "2026-03-12T16:00:00",
            },
            {
                "id": "ic_acme_004",
                "contact_email": _THIS_EMAIL,
                "subject": "API rate limit question",
                "body": "We hit 429s during a large nightly ingest. Can you bump our rate limit to 200rps?",
                "status": "closed",
                "created_at": "2026-04-22T11:00:00",
            },
            {
                "id": "ic_acme_005",
                "contact_email": _THIS_EMAIL,
                "subject": "Re: API rate limit question",
                "body": "Thanks - confirmed 200rps. All good now.",
                "status": "closed",
                "created_at": "2026-04-23T09:30:00",
            },
            # noise - 55 conversations from other customers
            *_noise_intercom(55, base_id=1000),
        ],
    },
    # ─────────── zendesk - 40 rows, 2 ours, 38 noise ───────────
    "zendesk": {
        "tickets": [
            # ours - non-cancel topics
            {"id": "zd_acme_001", "requester_email": _THIS_EMAIL, "subject": "Add new viewer-role user", "status": "solved", "updated_at": "2026-02-04T09:00:00"},
            {"id": "zd_acme_002", "requester_email": _THIS_EMAIL, "subject": "Webhook delivery question", "status": "solved", "updated_at": "2026-04-30T15:00:00"},
            # noise - 38 tickets from other customers
            *_noise_zendesk(38, base_id=5000),
        ],
    },
    # ─────────── slack - 80 messages, 2 mention "Acme" (one is wrong Acme) ───────────
    "slack": {
        "messages": [
            # THIS customer escalation chatter
            {
                "ts": "2026-03-09T10:15:00",
                "channel": "cs-escalations",
                "user": "priya",
                "text": "Acme Genomics flagged yellow - data-export question, not a cancel. Will monitor. ops@acme-genomics.example",
            },
            # WRONG Acme - Acme Logistics
            {
                "ts": "2026-02-13T14:00:00",
                "channel": "cs-escalations",
                "user": "marcus",
                "text": "Acme Logistics churn risk flagged - shopping competitors. admin@acme-logistics.example. Won the dispute though.",
            },
            # 78 noise messages
            *_noise_slack(78, base_id=10000),
        ],
    },
    # ─────────── notion - 8 pages with similar titles ───────────
    "notion": {
        "pages": [
            # THE ACTUAL POLICY
            {
                "id": "n_refunds_2026",
                "title": "Refunds & Disputes - 2026 SOP (CURRENT)",
                "body": (
                    "OFFICIAL CURRENT POLICY. For subscription_canceled chargebacks: FIGHT when "
                    "(a) no formal cancellation request exists across Intercom/Zendesk/Gmail, AND "
                    "(b) documented product usage exists within 14 days before the dispute. An "
                    "informal mention of considering cancellation (e.g. 'we're evaluating', 'might "
                    "downgrade') is NOT a cancellation request. Only an explicit 'please cancel "
                    "our subscription effective <date>' counts as formal. Cite this policy by id "
                    "n_refunds_2026 in your finding."
                ),
                "status": "current",
                "updated_at": "2026-02-10T09:00:00",
                "tags": "refunds,sop,policy,authoritative",
            },
            *_DEPRECATED_NOTION_PAGES,
            {
                "id": "n_engineering_oncall",
                "title": "Engineering on-call runbook",
                "body": "How to handle pager alerts. Unrelated to billing.",
                "status": "current",
                "updated_at": "2026-04-01T00:00:00",
                "tags": "engineering",
            },
            {
                "id": "n_sales_objections",
                "title": "Sales objections handbook - when prospects say they're cancelling",
                "body": "Sales-stage objection handling. Not for active customers.",
                "status": "current",
                "updated_at": "2025-11-20T00:00:00",
                "tags": "sales,objections",
            },
            {
                "id": "n_csm_playbook",
                "title": "CSM cancel-save playbook",
                "body": "For when an active customer asks to cancel - offer retention discount tier, escalate to CS lead. NOT a disputes policy.",
                "status": "current",
                "updated_at": "2026-03-15T00:00:00",
                "tags": "csm,retention",
            },
        ],
    },
    # ─────────── posthog - 30+ event rows the agent must aggregate ───────────
    "posthog": {
        "events": [
            # Acme Genomics events (last 30 days, multiple users)
            *[
                {
                    "id": f"ev_acme_{i:03d}",
                    "distinct_id": _THIS_EMAIL,
                    "event": ["pageview", "report_generated", "data_exported", "api_call", "login"][i % 5],
                    "timestamp": f"2026-{['04','05'][i % 2]}-{(i % 27) + 1:02d}T{(i % 23):02d}:00:00",
                    "properties": '{"product_area": "v3-reporting"}',
                }
                for i in range(18)
            ],
            # Most recent (5 days before dispute)
            {"id": "ev_acme_last", "distinct_id": _THIS_EMAIL, "event": "login", "timestamp": "2026-05-04T22:01:00", "properties": '{"product_area": "v3-reporting"}'},
            # Noise - events from other customers
            *[
                {
                    "id": f"ev_noise_{i:03d}",
                    "distinct_id": _OTHER_CUSTOMER_EMAILS[i % len(_OTHER_CUSTOMER_EMAILS)],
                    "event": ["pageview", "login", "report_generated"][i % 3],
                    "timestamp": f"2026-{(i % 5) + 1:02d}-{(i % 27) + 1:02d}T{(i % 23):02d}:00:00",
                    "properties": '{"product_area": "v3-reporting"}',
                }
                for i in range(40)
            ],
        ],
        "person_summary": [
            {"distinct_id": _THIS_EMAIL, "first_seen": "2023-05-09T11:02:00", "last_seen": "2026-05-04T22:01:00", "total_events_30d": 19, "distinct_users_active_30d": 4, "critical_actions_14d": 12, "product_areas": "v3-reporting,v3-export"},
            {"distinct_id": "support@quantum-synth.io", "first_seen": "2026-05-22T09:00:00", "last_seen": "2026-05-26T11:00:00", "total_events_30d": 3, "distinct_users_active_30d": 2, "critical_actions_14d": 0, "product_areas": "trial-only"},
            {"distinct_id": "billing@globex.example", "first_seen": "2023-01-01T10:00:00", "last_seen": "2026-06-02T16:00:00", "total_events_30d": 412, "distinct_users_active_30d": 215, "critical_actions_14d": 280, "product_areas": "v3-reporting,v3-seats"},
        ],
    },
    # ─────────── gmail - 30 threads, 1 ours ───────────
    "gmail": {
        "threads": [
            {"id": "gm_acme_001", "participants": _THIS_EMAIL, "subject": "Acme Genomics - Q1 check-in", "snippet": "Discussed renewal expectations, no objections raised.", "last_message_at": "2026-03-12T16:00:00"},
            {"id": "gm_noise_001", "participants": "admin@acme-logistics.example", "subject": "Acme Logistics - please cancel", "snippet": "We are formally requesting cancellation effective end of Feb.", "last_message_at": "2026-02-10T10:00:00"},
            {"id": "gm_noise_002", "participants": "ap@helix-bio.example", "subject": "Helix Bio AR follow-up", "snippet": "47 days past due, please confirm payment.", "last_message_at": "2026-06-04T14:00:00"},
            {"id": "gm_noise_003", "participants": "billing@globex.example", "subject": "Re: Q3 seat planning", "snippet": "We can flex you up to 220 seats at no extra charge through end of Q3.", "last_message_at": "2026-03-18T14:22:00"},
            {"id": "gm_noise_004", "participants": "joe@joescoffee-pdx.example", "subject": "Welcome to the platform", "snippet": "Self-serve signup welcome email.", "last_message_at": "2026-04-04T10:00:00"},
        ],
    },
    # ─────────── sentry - red-herring legacy v1 incident ───────────
    "sentry": {
        "issues": [
            {"id": "snt_001", "title": "legacy-reporting-v1: NullPointerException in /v1/reports/quarterly", "product_area": "legacy-reporting-v1", "first_seen": "2026-03-22T08:14:00", "affected_accounts_csv": "001NorthW,001Helix", "status": "ignored"},
            {"id": "snt_002", "title": "v3-reporting: occasional 502 on export endpoint", "product_area": "v3-reporting", "first_seen": "2026-04-01T12:00:00", "affected_accounts_csv": "001Globex,001NorthW,001AcmeGn", "status": "in_progress"},
            {"id": "snt_003", "title": "auth-svc: rate-limiter false positives", "product_area": "auth", "first_seen": "2026-05-15T03:00:00", "affected_accounts_csv": "001AcmeGn", "status": "resolved"},
            {"id": "snt_004", "title": "billing-platform: orphan subscription migration bug", "product_area": "billing", "first_seen": "2026-03-12T00:00:00", "affected_accounts_csv": "001SagaR", "status": "in_progress"},
            {"id": "snt_005", "title": "v3-export: timeout on large datasets", "product_area": "v3-export", "first_seen": "2026-02-01T00:00:00", "affected_accounts_csv": "001AcmeGn,001Helix", "status": "resolved"},
            {"id": "snt_006", "title": "ui-shell: dark-mode contrast bug", "product_area": "ui", "first_seen": "2026-04-12T00:00:00", "affected_accounts_csv": "001Globex", "status": "resolved"},
        ],
    },
}


S01_BRUTAL = Scenario(
    case_id="S01B-acme-brutal",
    pattern_name="friendly_fraud_brutal",
    trigger_text=(
        "Slack DM from @priya (CSM):\n"
        "\"Hey can you take dp_3MqAcmeRen? Acme Genomics is fighting the $4,200 annual "
        "renewal. They keep insisting they tried to cancel earlier this year - I poked "
        "around Intercom and there's something from a couple months back but it didn't "
        "feel like a formal cancel request to me. They're using the product. Brief "
        "please by EOD Thu (evidence due Fri).\"\n\n"
        "Customer: Acme Genomics (cus_AcmeGn, ops@acme-genomics.example)\n"
        "Dispute: dp_3MqAcmeRen · $4,200 USD · reason: subscription_canceled\n"
        "Charge: ch_3MqAcmeRen · 09 May 2026\n"
        "Evidence deadline: 12 June 2026\n"
    ),
    dispute_header={},  # unused in DuckDB path
    duckdb_world=_S01_BRUTAL_WORLD,
    distractor_sources=["sentry"],
    catalog=[],  # derived from DB live
    expected_decision="fight",
    expected_min_confidence=0.80,
    expected_findings_keywords=[
        "no formal cancel",
        "data export",  # the informal mention
        "usage",
        "policy",
    ],
    must_not_findings_keywords=[
        "acme logistics",  # different company!
        "legacy-reporting",
        "nullpointer",
        "2024",  # the deprecated policy doc
        "faq",  # the customer-facing FAQ
    ],
    notes=(
        "Real volume + noise. The agent must filter intercom.conversations by "
        "contact_email = 'ops@acme-genomics.example' (NOT just LIKE %acme%, "
        "which catches Acme Logistics). Must pick refunds-2026-sop NOT the "
        "deprecated 2024 one or the customer-facing FAQ. Must NOT cite the "
        "Sentry legacy-reporting-v1 incident (Acme is on v3). Must aggregate "
        "posthog events to find last_active, not rely on a pre-extracted field."
    ),
)


SCENARIOS_BRUTAL: list[Scenario] = [S01_BRUTAL]
