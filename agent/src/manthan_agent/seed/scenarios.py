"""Five fully-specified scenarios from research/billing_ops_cases.md.

Distribution covers the five main billing-ops case categories:
  - chargeback:      friendly-fraud-saas-annual-non-refundable (case #1)
  - failed_payment:  expired-card-on-high-ARR-renewal           (case #5)
  - refund_dispute:  refund-after-policy-window                 (case #9)
  - dunning:         high-mrr-30-days-past-due-no-csm           (case #12)
  - renewal_risk:    champion-left-no-replacement               (case #15)

Each scenario:
- Maps 1:1 to a case in research/billing_ops_cases.md (grounded in public
  sources cited there).
- Specifies which sources its seeder must populate.
- Provides per-source `seed_hints` that the individual seeders consume.
- Names the expected agent action + the cross-source citations the
  agent must produce to be graded "passed."

Companies named below all use the .example TLD (RFC 2606) so no seeded
record can hit a real inbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .identity import CompanyIdentity

# ────────────────────────────────────────────────────────────────────────
# Canonical companies - one per scenario. Re-usable if a scenario expands.
# ────────────────────────────────────────────────────────────────────────

NORTHSTAR = CompanyIdentity(
    slug="northstar-logistics",
    name="Northstar Logistics",
    domain="northstar-logistics.example",
    industry="Last-mile delivery",
    size="smb",
    arr_usd=2_400,
    signup_date="2025-01-15",
    primary_billing_name="Maya Patel",
    csm_email="",  # CSM-less - the point of this case
)

TINDARELL = CompanyIdentity(
    slug="tindarell-corp",
    name="Tindarell Corp",
    domain="tindarell.example",
    industry="HR tech",
    size="mid-market",
    arr_usd=48_000,
    signup_date="2024-09-04",
    primary_billing_name="Lucia Marchetti",
    csm_email="akash@miny-labs.com",
)

VAUXLEY = CompanyIdentity(
    slug="vauxley-analytics",
    name="Vauxley Analytics",
    domain="vauxley.example",
    industry="Marketing analytics",
    size="mid-market",
    arr_usd=84_000,
    signup_date="2024-07-22",
    primary_billing_name="Marcus Reed",
    csm_email="hitakshi@miny-labs.com",
)

BRILLION = CompanyIdentity(
    slug="brillion-studios",
    name="Brillion Studios",
    domain="brillion.example",
    industry="Design agency",
    size="smb",
    arr_usd=4_800,
    signup_date="2026-01-05",
    primary_billing_name="Anwar Khalid",
    csm_email="",
)

GOLDENROD = CompanyIdentity(
    slug="goldenrod-group",
    name="Goldenrod Group",
    domain="goldenrod.example",
    industry="Insurance broker",
    size="enterprise",
    arr_usd=108_000,
    signup_date="2024-03-01",
    primary_billing_name="Daniela Costa",
    csm_email="akash@miny-labs.com",
)


# ────────────────────────────────────────────────────────────────────────
# Scenario shape
# ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scenario:
    """One billing-ops case to investigate.

    Read by:
      - seed/<source>.py - for the source's slice in `seed_hints`
      - eval/runner.py   - to fire the trigger at the agent and grade
                           the response against `expected_action`
                           and `must_cite_sources`.
    """

    id: str                                # research kebab-tag, primary key
    title: str
    category: str                          # see module docstring
    company: CompanyIdentity
    sources_touched: frozenset[str]        # which seeders must run
    trigger: dict[str, Any]                # event the agent reacts to
    expected_action: str                   # agent's correct next move
    must_cite_sources: frozenset[str]      # citations required to pass
    narrative: str                         # 2-3 sentence summary
    research_case_id: str                  # e.g. "case-1"
    seed_hints: dict[str, dict[str, Any]] = field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────────
# The five scenarios
# ────────────────────────────────────────────────────────────────────────

SCENARIOS: list[Scenario] = [
    # 1 ──────────────────────────────────────────────────────────────────
    Scenario(
        id="friendly-fraud-saas-annual-non-refundable",
        title="Friendly fraud - annual SaaS, Visa 13.2 cancelled_recurring",
        category="chargeback",
        research_case_id="case-1",
        company=NORTHSTAR,
        sources_touched=frozenset(
            {"stripe", "hubspot", "intercom", "slack", "posthog"}
        ),
        trigger={
            "source": "stripe",
            "event": "dispute.created",
            "reason_code": "cancelled_recurring",  # Visa 13.2
            "amount_minor": 240_000,               # cents
            "currency": "usd",
            "filed_at": "2026-02-08",
            "evidence_due_at": "2026-02-15",
        },
        expected_action="respond_with_evidence",
        must_cite_sources=frozenset(
            {
                "stripe.disputes",
                "stripe.charges",
                "intercom.conversations",
                "posthog.events",
                "hubspot.companies",
            }
        ),
        narrative=(
            "Northstar Logistics renewed Jan 15 2026 at $2,400/yr. Used the "
            "product for 90 days (~40 logins, 3 exports). Filed Visa 13.2 "
            "on Feb 8 2026 claiming they 'never agreed to the annual "
            "renewal.' No CSM relationship - only a TOS checkbox 13 months "
            "earlier in the signup record."
        ),
        seed_hints={
            "stripe": {
                "subscription": {
                    "amount_minor": 240_000,
                    "interval": "year",
                    "started_on": "2025-01-15",
                    "renewed_on": "2026-01-15",
                },
                "create_dispute": True,
                "dispute_reason": "subscription_canceled",
            },
            "hubspot": {
                "lifecycle_stage": "customer",
                "deal_amount": 2_400,
            },
            "intercom": {
                "renewal_reminder": {
                    "subject": "Your Manthan annual renewal is coming up",
                    "sent_offset_days": -29,  # 29 days before dispute
                    "opened": True,
                    "clicked": False,
                },
            },
            "slack": {
                "messages": [
                    {
                        "text": (
                            "FYI Northstar's annual renewed today $2,400. "
                            "Solo signup, no CSM assigned. flagging."
                        ),
                        "ts_offset_days": -24,
                    },
                ],
            },
            "posthog": {
                "logins": 40,
                "exports": 3,
                "last_login_offset_days": -3,
            },
        },
    ),
    # 2 ──────────────────────────────────────────────────────────────────
    Scenario(
        id="expired-card-on-high-ARR-renewal",
        title="Expired card on $48K annual renewal - ABU sync failing",
        category="failed_payment",
        research_case_id="case-5",
        company=TINDARELL,
        sources_touched=frozenset(
            {"stripe", "hubspot", "salesforce", "slack", "sentry"}
        ),
        trigger={
            "source": "stripe",
            "event": "invoice.payment_failed",
            "failure_code": "expired_card",
            "amount_minor": 4_800_000,
            "currency": "usd",
            "failed_at": "2026-01-12",
        },
        expected_action="escalate_to_csm",
        must_cite_sources=frozenset(
            {
                "stripe.invoices",
                "stripe.payment_intents",
                "sentry.issues",
                "salesforce.accounts",
                "slack.messages",
            }
        ),
        narrative=(
            "Tindarell ($48K annual, billed upfront) renewal charge failed "
            "Jan 12 - card expired Dec 31. Visa Account Updater pushed "
            "the new card Jan 4 but the merchant's ABU sync silently "
            "failed (Sentry error). CFO is on PTO; auto-reply going "
            "nowhere. CSM relationship exists but they don't know."
        ),
        seed_hints={
            "stripe": {
                "subscription": {
                    "amount_minor": 4_800_000,
                    "interval": "year",
                    "started_on": "2024-09-04",
                    "renewed_on": "2026-01-12",
                },
                "force_payment_failure": "expired_card",
            },
            "sentry": {
                "issue": {
                    "title": "ABUSyncError: hash mismatch (CRLF vs LF)",
                    "level": "error",
                    "frequency_per_day": 2,
                    "first_seen_offset_days": -45,
                },
            },
            "salesforce": {
                "account_type": "Customer - Direct",
                "renewal_date": "2026-09-04",
            },
            "slack": {
                "messages": [
                    {
                        "text": (
                            "Lucia (Tindarell CFO) is OOO until Jan 22. "
                            "Auto-reply confirms it. Backup is Riley in AP."
                        ),
                        "ts_offset_days": -5,
                    },
                ],
            },
        },
    ),
    # 3 ──────────────────────────────────────────────────────────────────
    Scenario(
        id="refund-after-policy-window",
        title="Refund request 73 days after 30-day money-back window",
        category="refund_dispute",
        research_case_id="case-9",
        company=BRILLION,
        sources_touched=frozenset(
            {"stripe", "hubspot", "intercom", "notion", "posthog"}
        ),
        trigger={
            "source": "intercom",
            "event": "conversation.opened",
            "subject": "Full refund request - we never really used it",
            "received_at": "2026-04-18",
            "intent": "refund_request",
        },
        expected_action="propose_decision_with_tradeoffs",
        must_cite_sources=frozenset(
            {
                "stripe.charges",
                "stripe.refunds",
                "notion.search",                # the refund-policy runbook
                "posthog.events",               # actual usage
                "intercom.conversations",
                "hubspot.companies",
            }
        ),
        narrative=(
            "Brillion Studios paid $4,800 annual on Jan 5 2026. Requested "
            "full refund Apr 18 (day 103). Refund policy says 30-day "
            "money-back, then nothing. Actual usage: 47 logins, 12 "
            "projects, 3 invites - light but not zero. Customer hints at "
            "chargeback if denied. Judgment call - no obvious right "
            "answer."
        ),
        seed_hints={
            "stripe": {
                "charge": {
                    "amount_minor": 480_000,
                    "currency": "usd",
                    "captured_on": "2026-01-05",
                },
            },
            "intercom": {
                "conversation_body": (
                    "Hi team, we paid for the annual plan back in January "
                    "but honestly we never really used it. We'd like a "
                    "full refund please. If not, we'll have to dispute "
                    "this through our bank."
                ),
            },
            "notion": {
                "create_runbook_page": True,
                "runbook_title": "Refund policy - annual plans",
                "runbook_body_excerpt": (
                    "30-day money-back guarantee from the date of charge. "
                    "After 30 days, no refunds except for service-credit "
                    "scenarios documented in the SLA."
                ),
            },
            "posthog": {
                "logins": 47,
                "projects_created": 12,
                "invites_sent": 3,
                "last_login_offset_days": -8,
            },
        },
    ),
    # 4 ──────────────────────────────────────────────────────────────────
    Scenario(
        id="high-mrr-30-days-past-due-no-csm",
        title="$108K ARR account 30 days past due - AR emailing shared inbox",
        category="dunning",
        research_case_id="case-12",
        company=GOLDENROD,
        sources_touched=frozenset(
            {"stripe", "salesforce", "intercom", "slack", "linear"}
        ),
        trigger={
            "source": "stripe",
            "event": "invoice.overdue",
            "days_overdue": 30,
            "amount_minor": 900_000,         # $9,000 of $108K ARR
            "currency": "usd",
            "due_date": "2026-04-01",
            "today": "2026-05-01",
        },
        expected_action="route_to_csm_block_suspension",
        must_cite_sources=frozenset(
            {
                "stripe.invoices",
                "salesforce.accounts",
                "salesforce.opportunities",
                "linear.issues",
                "slack.messages",
            }
        ),
        narrative=(
            "Goldenrod Group ($108K ARR enterprise, Net 30). Invoice due "
            "Apr 1 still unpaid. AR has been emailing ap@goldenrod.example "
            "(shared inbox), no reply. Default rule would suspend at day "
            "30 - but Goldenrod has an active product integration that "
            "their downstream insureds depend on. Suspension causes "
            "contagion. CSM doesn't know AR is escalating."
        ),
        seed_hints={
            "stripe": {
                "invoice": {
                    "amount_minor": 900_000,
                    "currency": "usd",
                    "due_offset_days": -30,
                    "status": "open",
                },
            },
            "salesforce": {
                "account_arr": 108_000,
                "renewal_date": "2026-09-01",
                "owner_email": "akash@miny-labs.com",
                "integration_criticality": "high",
            },
            "linear": {
                "issue": {
                    "title": "Goldenrod Group - past-due, contains critical integration",
                    "priority": "Urgent",
                    "state": "open",
                },
            },
            "slack": {
                "messages": [
                    {
                        "text": (
                            "Goldenrod payment hasn't landed. ap@ inbox is "
                            "silent. Daniela was their primary AR contact - "
                            "is she still there?"
                        ),
                        "ts_offset_days": -3,
                    },
                ],
            },
        },
    ),
    # 5 ──────────────────────────────────────────────────────────────────
    Scenario(
        id="champion-left-no-replacement",
        title="Champion departed - 22% usage drop, renewal in 90 days",
        category="renewal_risk",
        research_case_id="case-15",
        company=VAUXLEY,
        sources_touched=frozenset(
            {"stripe", "hubspot", "posthog", "slack", "intercom"}
        ),
        trigger={
            "source": "posthog",
            "event": "renewal_risk.signal",
            "renewal_in_days": 90,
            "usage_drop_pct": 22,
            "champion_user_inactive_for_days": 28,
        },
        expected_action="open_save_play",
        must_cite_sources=frozenset(
            {
                "posthog.events",
                "hubspot.companies",
                "hubspot.contacts",
                "intercom.conversations",
                "slack.messages",
            }
        ),
        narrative=(
            "Vauxley Analytics ($84K ARR, 18 months tenure). VP-Marketing "
            "Marcus Reed - the original champion - stopped logging in 28 "
            "days ago. Usage on his account dropped to zero; org-wide "
            "usage dropped 22%. CSM only noticed during QBR prep. "
            "Renewal Jul 22 - 90 days away. ChurnZero data says 51% "
            "churn risk; 33% renewal lift if acted on within 48 hours."
        ),
        seed_hints={
            "stripe": {
                "subscription": {
                    "amount_minor": 700_000,    # ~$7K/mo
                    "interval": "month",
                    "started_on": "2024-07-22",
                },
            },
            "hubspot": {
                "primary_contact_inactive": True,
                "company_health_score": "yellow",
                "renewal_owner": "hitakshi@miny-labs.com",
            },
            "posthog": {
                "primary_user_last_login_offset_days": -28,
                "org_usage_drop_pct": 22,
                "outcome_events_in_30d": 4,    # vs cohort median 22
            },
            "intercom": {
                "last_inbound_conversation_offset_days": -45,
            },
            "slack": {
                "messages": [
                    {
                        "text": (
                            "Did anyone hear back from Marcus at Vauxley? "
                            "His LinkedIn went quiet. Their team_lead "
                            "might be transitioning."
                        ),
                        "ts_offset_days": -8,
                    },
                ],
            },
        },
    ),
]

# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────


def scenarios_for_source(source: str) -> list[Scenario]:
    """Return every scenario whose seed_hints include the given source."""
    return [s for s in SCENARIOS if source in s.sources_touched]


def scenario_by_id(scenario_id: str) -> Scenario:
    """Lookup. Raises KeyError if not found."""
    for s in SCENARIOS:
        if s.id == scenario_id:
            return s
    raise KeyError(scenario_id)
