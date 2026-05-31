"""Hard scenario battery for Manthan investigator.

Each scenario is a realistic billing-ops case with:
  - Messy trigger text (how a human would actually forward/describe the case)
  - Rich source bundles ("world") - some relevant, some red herrings
  - Ground truth: expected decision, optional amount, keywords that
    should appear in findings, keywords that should NOT (red-herring
    citations the agent must avoid)

Use scripts/scenario_bake.py to run them against any OpenRouter model.

Design constraints we honored:
  - Triggers are HUMAN-WRITTEN, not pristine. Some have typos, partial
    info, opinions, internal politics. The agent has to find truth in
    the data, not in the trigger.
  - Every scenario surfaces at least one red-herring source - an
    incident/ticket/escalation that LOOKS related but isn't.
  - Decisions span: fight, refund (full), refund (partial), accept,
    escalate (ask_human).
  - Source mix varies: SLA cases need pagerduty/statusgator; compliance
    needs notion policy + vertex tax data; fraud needs stripe-radar
    signal + domain-age signal; political-dunning needs slack chatter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Scenario:
    case_id: str
    pattern_name: str
    trigger_text: str
    dispute_header: dict[str, Any]
    # Legacy flat path: source → pre-curated field bundle. The mock unions
    # these into a single returned row. Easy mode - answers are pre-extracted.
    world: dict[str, dict[str, Any]] = field(default_factory=dict)
    distractor_sources: list[str] = field(default_factory=list)
    catalog: list[dict[str, Any]] = field(default_factory=list)
    expected_decision: str = "fight"
    expected_amount_minor: int | None = None
    expected_min_confidence: float = 0.70
    expected_findings_keywords: list[str] = field(default_factory=list)
    must_not_findings_keywords: list[str] = field(default_factory=list)
    notes: str = ""
    # Brutal-data path: source → table → list of row-dicts. Loaded into
    # an in-memory DuckDB; the agent runs real SQL against it. When this
    # is set, it takes precedence over `world` (the flat path is ignored).
    duckdb_world: dict[str, dict[str, list[dict[str, Any]]]] | None = None


# The unified catalog every scenario advertises. We give the agent a
# broad surface so a scenario with no PagerDuty data still LOOKS like
# PagerDuty exists - the agent might JOIN into it and get nothing back,
# which is itself a finding ("no incidents on file"). That mirrors real
# Coral behavior.
_FULL_CATALOG: list[dict[str, Any]] = [
    {"name": "stripe",      "tables": ["disputes", "charges", "customers", "invoices", "subscriptions", "refunds", "radar_reviews"]},
    {"name": "salesforce",  "tables": ["accounts", "opportunities", "contacts"]},
    {"name": "hubspot",     "tables": ["companies", "contacts", "deals", "notes"]},
    {"name": "intercom",    "tables": ["conversations", "contacts"]},
    {"name": "zendesk",     "tables": ["tickets", "users"]},
    {"name": "slack",       "tables": ["channels", "messages"]},
    {"name": "notion",      "tables": ["pages", "blocks"]},
    {"name": "posthog",     "tables": ["events", "person_summary"]},
    {"name": "gmail",       "tables": ["threads", "messages"]},
    {"name": "pagerduty",   "tables": ["incidents", "alerts"]},
    {"name": "statusgator", "tables": ["status_events"]},
    {"name": "datadog",     "tables": ["alerts", "metrics"]},
    {"name": "sentry",      "tables": ["issues", "events"]},
    {"name": "linear",      "tables": ["issues"]},
    {"name": "vertex_tax",  "tables": ["computations", "exemptions"]},
]


# ──────────────────────────────────────────────────────────────────────
# S01 - Friendly fraud with a legit-feeling complaint in the rear-view
# ──────────────────────────────────────────────────────────────────────

_S01 = Scenario(
    case_id="S01-acme-friendly-fraud",
    pattern_name="friendly_fraud_complex",
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
        "Evidence deadline: 12 June 2026"
    ),
    dispute_header={
        "dispute_id": "dp_3MqAcmeRen",
        "dispute_amount_minor": 420000,
        "dispute_currency": "usd",
        "dispute_reason": "subscription_canceled",
        "dispute_status": "needs_response",
        "dispute_evidence_due_by": "2026-06-12T00:00:00Z",
        "customer_email": "ops@acme-genomics.example",
        "stripe_customer_id": "cus_AcmeGn",
    },
    world={
        "stripe": {
            "charge_id": "ch_3MqAcmeRen",
            "charge_amount_minor": 420000,
            "charge_created": "2026-05-09T11:02:00Z",
            "charge_status": "succeeded",
            "subscription_id": "sub_AcmeGn",
            "subscription_status": "active",
            "subscription_cancel_at_period_end": False,
            "subscription_canceled_at": None,
            "subscription_current_period_start": "2026-05-09T00:00:00Z",
            "subscription_current_period_end": "2027-05-09T00:00:00Z",
            "prior_disputes_14mo": 0,
            "prior_refunds_24mo": 0,
        },
        "salesforce": {
            "sf_account_name": "Acme Genomics",
            "sf_plan": "Pro Annual",
            "sf_arr_minor": 420000,
            "sf_health": "yellow",
            "sf_nps_last": 6,
            "sf_csm_owner": "priya@us",
            "sf_renewal_date": "2027-05-09",
            "sf_account_owner_notes": "Customer asked about data export 60d ago. CSM noted possible churn risk but no action requested.",
        },
        "intercom": {
            "ic_conversations_90d": 2,
            "ic_last_subject": "Data export options",
            "ic_last_body_snippet": (
                "We're evaluating whether to continue with you for another year and need to "
                "understand what data export looks like. Could you walk us through it?"
            ),
            "ic_last_at": "2026-03-08T14:00:00Z",
            "ic_cancel_intent_mentions_90d": 1,
            "ic_formal_cancel_requests_90d": 0,
        },
        "zendesk": {
            "zd_open_tickets": 0,
            "zd_tickets_90d": 0,
            "zd_last_subject": None,
            "zd_cancel_tickets_90d": 0,
        },
        "gmail": {
            "gmail_threads_90d": 1,
            "gmail_last_subject": "Acme Genomics - Q1 check-in",
            "gmail_last_at": "2026-03-12T16:00:00Z",
            "gmail_cancel_requests_90d": 0,
        },
        "slack": {
            "slack_cs_escalations_90d": 1,
            "slack_last_text_snippet": "Priya flagged Acme as yellow - data-export question, not a cancel.",
            "slack_last_ts": "2026-03-09T10:15:00Z",
        },
        "notion": {
            "notion_refunds_title": "Refunds & Disputes - 2026 SOP",
            "notion_refunds_body": (
                "For subscription_canceled chargebacks: FIGHT when (a) no formal "
                "cancellation request exists across Intercom/Zendesk/Gmail, AND (b) "
                "documented product usage exists within 14 days before the dispute. "
                "An informal mention of considering cancellation is NOT a cancellation."
            ),
        },
        "posthog": {
            "ph_last_active_at": "2026-05-04T22:01:00Z",  # 5d before dispute
            "ph_logins_30d": 9,
            "ph_distinct_users_active_30d": 4,
            "ph_critical_actions_14d": 12,
        },
        # RED HERRING - old sentry incident on a different product line
        "sentry": {
            "sentry_recent_incidents_90d": 1,
            "sentry_last_issue_title": "legacy-reporting-v1: NullPointerException in /v1/reports/quarterly",
            "sentry_last_issue_at": "2026-03-22T08:14:00Z",
            "sentry_last_issue_product_area": "legacy-reporting-v1",
            "sentry_affected_customers": "Acme is on v3 reporting (not v1). No impact.",
        },
    },
    distractor_sources=["sentry"],
    catalog=_FULL_CATALOG,
    expected_decision="fight",
    expected_min_confidence=0.80,
    expected_findings_keywords=[
        "no formal cancel",
        "data export",
        "usage",
        "policy",
    ],
    must_not_findings_keywords=[
        "sentry",
        "legacy-reporting",
        "nullpointer",
    ],
    notes=(
        "Hard because the customer DID have a real-feeling 'maybe we'll cancel' "
        "interaction. The agent must distinguish informal mention from formal "
        "request, and must NOT cite the unrelated v1 Sentry incident."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S02 - SLA short-pay with conflicting sources, correct answer is PARTIAL
# ──────────────────────────────────────────────────────────────────────

_S02 = Scenario(
    case_id="S02-northwind-sla-partial",
    pattern_name="sla_partial_credit",
    trigger_text=(
        "Forwarded email from @marcus (AR):\n"
        "\"FYI - Northwind Logistics short-paid INV-9821 by 25% ($2,250 on a $9k invoice). "
        "Their cite reason is 'SLA breach during May 14-15 outage.' I checked our status "
        "page (StatusGator snapshot) and it said operational the whole time so I don't "
        "think we owe them anything but plz double-check. AE is asking we don't ding the "
        "renewal over this.\"\n\n"
        "Customer: Northwind Logistics (acct 001Nwnd, ar@northwind-logi.example)\n"
        "Invoice INV-9821 · $9,000 USD · paid $6,750 (short $2,250)\n"
        "Cited SLA breach window: 2026-05-14 09:00 to 2026-05-15 14:00"
    ),
    dispute_header={
        "dispute_id": "INV-9821-shortpay",
        "dispute_amount_minor": 225000,
        "dispute_currency": "usd",
        "dispute_reason": "sla_breach_short_pay",
        "dispute_status": "needs_response",
        "dispute_evidence_due_by": "2026-06-30T00:00:00Z",
        "customer_email": "ar@northwind-logi.example",
        "stripe_customer_id": "cus_Nwnd",
        "invoice_id": "INV-9821",
        "invoice_total_minor": 900000,
        "invoice_paid_minor": 675000,
        "invoice_short_minor": 225000,
    },
    world={
        "stripe": {
            "invoice_status": "open",
            "invoice_due": "2026-05-30T00:00:00Z",
            "invoice_collection_method": "send_invoice",
            "prior_short_pays_24mo": 0,
            "subscription_status": "active",
            "subscription_plan": "Enterprise Annual",
        },
        "salesforce": {
            "sf_account_name": "Northwind Logistics",
            "sf_plan": "Enterprise Annual",
            "sf_arr_minor": 10800000,  # $108k ARR
            "sf_sla_tier": "99.95",
            "sf_health": "green",
            "sf_csm_owner": "rohan@us",
        },
        "pagerduty": {
            "pd_incidents_window": 1,
            "pd_last_incident_id": "PD-INC-44219",
            "pd_last_incident_severity": "SEV-2",
            "pd_last_incident_started_at": "2026-05-14T09:15:00Z",
            "pd_last_incident_resolved_at": "2026-05-14T13:42:00Z",
            "pd_last_incident_duration_minutes": 267,  # 4hr 27min
            "pd_last_incident_root_cause": "Degraded latency in EU region: routing config rollout",
        },
        "statusgator": {
            # Customer-facing status - note that we DIDN'T post an update.
            # A naive agent will read this as "no outage"; the right read
            # is "operational error - we failed to communicate, but the
            # internal incident is the ground truth."
            "sg_status_during_window": "operational",
            "sg_status_updates_in_window": 0,
            "sg_note_internal": (
                "No customer-facing update was posted for PD-INC-44219. Comms gap, "
                "flagged in retro doc 'outage-comms-may-2026'."
            ),
        },
        "datadog": {
            "dd_alerts_window": 6,
            "dd_p95_latency_baseline_ms": 220,
            "dd_p95_latency_during_ms": 1840,
            "dd_error_rate_baseline_pct": 0.2,
            "dd_error_rate_during_pct": 4.1,
            "dd_note": "Latency + error spike confirmed for the PagerDuty window.",
        },
        "notion": {
            "notion_msa_title": "Northwind Logistics MSA - SLA Addendum",
            "notion_msa_body": (
                "Per Northwind MSA Section 7.4: SLA credit = "
                "(downtime_hours / total_hours_in_month) * monthly_fee * multiplier. "
                "multiplier = 2 for SEV-2, 4 for SEV-1. Credits cap at one month's fee. "
                "Customer must claim credits within 30 days of incident. Customers may "
                "NOT unilaterally short-pay invoices - credits issue as billing adjustments."
            ),
            "notion_msa_updated_at": "2025-11-02T00:00:00Z",
            "notion_calc_note": (
                "Worked example: 4.45 downtime hours / 720 monthly hours * $9,000 * 2 = "
                "approx $111. Customer short-pay of $2,250 vastly exceeds owed credit."
            ),
        },
        "intercom": {
            "ic_conversations_90d": 1,
            "ic_last_subject": "Outage May 14 - credit request",
            "ic_last_body_snippet": (
                "Saw degraded performance May 14 morning. We had a customer-facing impact. "
                "Reducing our renewal payment by 25%."
            ),
            "ic_last_at": "2026-05-20T10:00:00Z",
        },
        # RED HERRING - an OLD SLA breach from a year ago that does NOT apply
        "sentry": {
            "sentry_recent_incidents_90d": 0,
            "sentry_old_incidents_note": (
                "Unrelated: a P3 issue from 2025-08 is still open on the staging environment. "
                "No customer impact, no production effect."
            ),
        },
    },
    distractor_sources=["sentry", "statusgator"],
    catalog=_FULL_CATALOG,
    expected_decision="refund",  # PARTIAL - small credit, not full short-pay
    expected_amount_minor=11100,  # ~$111 credit
    expected_min_confidence=0.75,
    expected_findings_keywords=[
        "pagerduty",
        "sev-2",
        "4",  # 4 hours / 4.45 hours
        "msa",
        "credit",
    ],
    must_not_findings_keywords=[
        "no outage",  # wrong - there WAS an outage, statusgator was the wrong source
        "sentry",
        "2,250",  # don't agree to the full short-pay
    ],
    notes=(
        "Two-source contradiction: StatusGator says operational (red herring - we "
        "didn't post a status update); PagerDuty + Datadog confirm SEV-2 outage. "
        "Customer is RIGHT that there was an outage, WRONG about the credit math. "
        "Correct answer: issue $111 credit, document the comms gap, do NOT accept "
        "the $2,250 short-pay."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S03 - AE made an off-contract verbal promise via Gmail; honor it
# ──────────────────────────────────────────────────────────────────────

_S03 = Scenario(
    case_id="S03-globex-ae-promise",
    pattern_name="ae_promise_off_contract",
    trigger_text=(
        "Linear ticket from @ops-billing:\n"
        "\"Customer disputing $8,200 expansion invoice. They claim AE Mark promised seat "
        "flex up to 220 at no extra charge in a Gmail thread. Salesforce opp shows the "
        "original 200-seat contract. We auto-billed based on contract. Who's right?\"\n\n"
        "Customer: Globex Software (cus_Globex, accounting@globex.example)\n"
        "Invoice INV-7732 · $8,200 USD · Q3 seat overage\n"
        "Customer paid the base $40k contract; disputing the overage only."
    ),
    dispute_header={
        "dispute_id": "INV-7732-overage",
        "dispute_amount_minor": 820000,
        "dispute_currency": "usd",
        "dispute_reason": "incorrect_amount",
        "dispute_status": "open",
        "dispute_evidence_due_by": "2026-06-25T00:00:00Z",
        "customer_email": "accounting@globex.example",
        "stripe_customer_id": "cus_Globex",
        "invoice_id": "INV-7732",
    },
    world={
        "stripe": {
            "invoice_total_minor": 820000,
            "invoice_line_item_description": "Q3 seat overage: 15 seats above contracted 200",
            "invoice_billing_rate_minor": 20000,  # $200/seat/month
            "subscription_status": "active",
        },
        "salesforce": {
            "sf_account_name": "Globex Software",
            "sf_plan": "Pro Annual",
            "sf_contracted_seats": 200,
            "sf_contract_rate_per_seat_year_minor": 20000,
            "sf_arr_minor": 4000000,  # $40k
            "sf_account_owner": "mark@us",  # AE Mark
            "sf_renewal_date": "2026-12-31",
            "sf_health": "green",
        },
        "gmail": {
            "gmail_threads_90d": 3,
            "gmail_promise_thread_subject": "Re: Q3 seat planning",
            "gmail_promise_thread_from": "mark@us (AE)",
            "gmail_promise_thread_to": "accounting@globex.example",
            "gmail_promise_thread_at": "2026-03-18T14:22:00Z",
            "gmail_promise_thread_quote": (
                "Hey Sarah - we can flex you up to 220 seats at no extra charge through "
                "end of Q3 as we'd talked about. Just keep me in the loop on hiring."
            ),
            "gmail_promise_thread_attachments": 0,
        },
        "posthog": {
            "ph_seats_provisioned": 215,
            "ph_seats_active_30d": 215,
            "ph_seats_active_14d": 213,
            "ph_last_active_at": "2026-06-02T16:00:00Z",
        },
        "notion": {
            "notion_msa_title": "Globex MSA - Seat Billing Terms",
            "notion_msa_body": (
                "Seat overage billed at contract rate * overage_count, prorated monthly. "
                "Side letters or AE-issued promises must be reflected as opportunity "
                "amendments in Salesforce before being honored by billing automation."
            ),
            "notion_runbook_title": "Off-contract AE promises - 2026 RevOps SOP",
            "notion_runbook_body": (
                "If a Gmail/Slack AE promise exists but no SF amendment was filed, the "
                "promise still binds the company (good-faith reliance). Refund or credit "
                "the affected invoice, then file the missing amendment retroactively."
            ),
        },
        "intercom": {
            "ic_conversations_90d": 0,
        },
        "zendesk": {
            "zd_tickets_90d": 1,
            "zd_last_subject": "Question about seat pricing - closed Jan",
            "zd_last_status": "solved",
            "zd_last_at": "2026-01-08T11:00:00Z",
            "zd_cancel_tickets_90d": 0,
        },
        # RED HERRING - a Slack message about a DIFFERENT customer's seat dispute
        "slack": {
            "slack_cs_escalations_90d": 0,
            "slack_last_text_snippet": (
                "Globex Polymers (different account!) had a seat dispute in Feb - "
                "that one was resolved by adjusting their billing cycle. Unrelated to "
                "Globex Software."
            ),
            "slack_last_ts": "2026-02-04T11:00:00Z",
        },
    },
    distractor_sources=["slack"],
    catalog=_FULL_CATALOG,
    expected_decision="refund",
    expected_amount_minor=820000,  # full $8,200 - AE promised up to 220, they used 215
    expected_min_confidence=0.75,
    expected_findings_keywords=[
        "gmail",
        "ae",
        "215",
        "220",
        "promise",
    ],
    must_not_findings_keywords=[
        "globex polymers",  # different company
        "polymers",
    ],
    notes=(
        "AE made an off-contract verbal-ish promise via email; customer used 215 "
        "seats (under the promised 220). The MSA says SF amendment required, but "
        "the RevOps SOP says good-faith reliance binds the company. Refund full "
        "$8,200, file retroactive amendment. Slack red herring is a different "
        "company (Globex Polymers vs Globex Software)."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S04 - VAT misconfig: customer is right but only partially
# ──────────────────────────────────────────────────────────────────────

_S04 = Scenario(
    case_id="S04-bottega-vat-partial",
    pattern_name="compliance_vat_misconfig",
    trigger_text=(
        "Stripe webhook + slack note from @finance:\n"
        "\"Italian customer is disputing INV-4521 ($5,400 total) - they say they shouldn't "
        "have been charged VAT because they're a business with a valid IT VAT ID. Avalara "
        "computed VAT anyway. I think they have a point but the disputed amount is "
        "$5,400 which is the WHOLE invoice and that can't be right either.\"\n\n"
        "Customer: Bottega Romano S.r.l. (cus_Bottega, contab@bottega-romano.example)\n"
        "Invoice INV-4521 · $5,400 USD ($4,500 product + $900 VAT @ 20%)"
    ),
    dispute_header={
        "dispute_id": "INV-4521-vat",
        "dispute_amount_minor": 540000,
        "dispute_currency": "usd",
        "dispute_reason": "incorrect_tax",
        "dispute_status": "open",
        "dispute_evidence_due_by": "2026-06-30T00:00:00Z",
        "customer_email": "contab@bottega-romano.example",
        "stripe_customer_id": "cus_Bottega",
    },
    world={
        "stripe": {
            "invoice_total_minor": 540000,
            "invoice_product_minor": 450000,
            "invoice_tax_minor": 90000,
            "invoice_tax_rate_pct": 20,
            "subscription_status": "active",
        },
        "salesforce": {
            "sf_account_name": "Bottega Romano S.r.l.",
            "sf_business_type": "B2B",
            "sf_country": "IT",
            "sf_vat_id": "IT12345678901",
            "sf_vat_id_verified": True,
            "sf_vat_id_verified_via": "VIES on 2025-09-12",
            "sf_health": "green",
        },
        "vertex_tax": {
            "tax_engine": "Avalara",
            "tax_customer_record_tax_exempt": False,  # the bug
            "tax_engine_computed_correctly_for_inputs": True,
            "tax_note": (
                "Customer is configured tax_exempt=false despite valid EU VAT ID on file. "
                "Avalara correctly applied 20% IT VAT given that input. Bug is at the "
                "customer-record level (tax_exempt flag not set), not at the engine level."
            ),
        },
        "notion": {
            "notion_policy_title": "EU B2B Tax Handling - RevOps SOP v4",
            "notion_policy_body": (
                "EU B2B customers with a VIES-verified VAT ID are subject to reverse-charge "
                "VAT - we do NOT charge VAT on their invoices. They self-report VAT in their "
                "own jurisdiction. Configure tax_exempt=true in the billing platform once VAT "
                "ID is VIES-verified. If a customer is incorrectly charged VAT, refund the "
                "VAT portion only (product portion is owed and used)."
            ),
            "notion_policy_updated_at": "2025-10-01T00:00:00Z",
        },
        "intercom": {
            "ic_conversations_90d": 2,
            "ic_last_subject": "VAT question - EU business customer",
            "ic_last_body_snippet": (
                "Hi, we're an Italian business. Are we supposed to pay VAT to you, or does "
                "the reverse-charge mechanism apply? Our accountant is asking."
            ),
            "ic_last_at": "2026-05-02T09:00:00Z",
            "ic_last_response_snippet": (
                "Hi! Our Avalara integration handles VAT automatically, so whatever's on "
                "the invoice is correct. - Riya (CS)"
            ),
            "ic_last_response_at": "2026-05-02T11:30:00Z",
        },
        "posthog": {
            "ph_last_active_at": "2026-06-04T13:00:00Z",
            "ph_logins_30d": 22,
            "ph_distinct_users_active_30d": 18,
        },
        # RED HERRING - an unrelated Notion page about EU labor law
        "linear": {
            "linear_open_issues_90d": 1,
            "linear_last_issue_title": "EU GDPR right-to-deletion task - unrelated infra cleanup",
            "linear_last_issue_status": "in_progress",
        },
    },
    distractor_sources=["linear"],
    catalog=_FULL_CATALOG,
    expected_decision="refund",
    expected_amount_minor=90000,  # $900 VAT only, NOT $5,400
    expected_min_confidence=0.75,
    expected_findings_keywords=[
        "reverse",  # reverse-charge
        "vat id",
        "tax_exempt",
        "vies",
    ],
    must_not_findings_keywords=[
        "labor",
        "gdpr",
        "5,400",  # don't refund the full invoice
        "$5400",
    ],
    notes=(
        "Customer is RIGHT that VAT shouldn't have applied - but only the $900 VAT "
        "portion, not the full $5,400 invoice. The bug is the tax_exempt flag in "
        "the billing platform, not the engine. The CS response in Intercom was "
        "unhelpfully wrong. Linear GDPR ticket is a red herring."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S05 - Dunning escalation: agent MUST ask_human, runbook conflict
# ──────────────────────────────────────────────────────────────────────

_S05 = Scenario(
    case_id="S05-helix-dunning-escalate",
    pattern_name="dunning_political_escalate",
    trigger_text=(
        "Linear ticket from @gina (AR):\n"
        "\"Helix Bio is 47 days past due on $11,200 invoice. Standard runbook says "
        "suspend at 30. AE Sarah is in my DMs saying don't suspend, her CTO contact "
        "promised payment this week. CFO assistant pinged me twice asking why "
        "they're still active. I don't want to make this call solo - please advise.\"\n\n"
        "Customer: Helix Bio (cus_HelixB, ap@helix-bio.example)\n"
        "Invoice INV-3344 · $11,200 USD · 47 days past due\n"
        "Last collection attempt: day 30 (failed, no retry since)"
    ),
    dispute_header={
        "dispute_id": "INV-3344-dunning",
        "dispute_amount_minor": 1120000,
        "dispute_currency": "usd",
        "dispute_reason": "past_due_escalation",
        "dispute_status": "needs_response",
        "dispute_evidence_due_by": "2026-07-01T00:00:00Z",
        "customer_email": "ap@helix-bio.example",
        "stripe_customer_id": "cus_HelixB",
    },
    world={
        "stripe": {
            "invoice_total_minor": 1120000,
            "invoice_status": "past_due",
            "invoice_days_past_due": 47,
            "invoice_last_collection_attempt_at": "2026-04-30T00:00:00Z",
            "invoice_last_collection_status": "failed",
            "subscription_status": "active",  # not yet suspended
            "subscription_plan": "Enterprise Annual",
        },
        "salesforce": {
            "sf_account_name": "Helix Bio",
            "sf_plan": "Enterprise Annual",
            "sf_arr_minor": 13400000,  # $134k ARR
            "sf_health": "red",
            "sf_account_owner": "sarah@us",  # AE
            "sf_renewal_date": "2026-08-15",
            "sf_strategic_flag": False,  # NOT flagged
            "sf_override_on_file": None,  # NO override
        },
        "slack": {
            "slack_cs_escalations_90d": 3,
            "slack_ae_message_snippet": (
                "(AE Sarah, 3d ago, #cs-execs): 'Their CTO promised payment this week - "
                "don't suspend, please. I'll lose this renewal if we cut them off.'"
            ),
            "slack_ae_message_at": "2026-06-13T09:14:00Z",
            "slack_cfo_message_snippet": (
                "(CFO assistant, 1d ago, #ar): 'Why is Helix still active at 47 days past "
                "due? Our policy is 30.'"
            ),
            "slack_cfo_message_at": "2026-06-15T10:30:00Z",
        },
        "intercom": {
            "ic_conversations_90d": 1,
            "ic_last_subject": "Re: Invoice INV-3344 - payment reminder",
            "ic_last_body_snippet": (
                "Sorry, our AP team is backed up. We'll process this week. - Helix AP"
            ),
            "ic_last_at": "2026-06-04T14:00:00Z",
            "ic_follow_up_response_count": 0,  # No further response after 12d
        },
        "posthog": {
            "ph_last_active_at": "2026-06-15T22:00:00Z",
            "ph_logins_30d": 124,
            "ph_distinct_users_active_30d": 35,
            "ph_critical_actions_14d": 280,
        },
        "notion": {
            "notion_runbook_title": "Dunning & Suspension SOP v6",
            "notion_runbook_body": (
                "Suspend customer at 30 days past due unless: (a) account is flagged "
                "'strategic' in Salesforce, OR (b) a written override exists from the "
                "Director of Revenue. No exceptions for AE pleas alone. If an AE wants "
                "to delay suspension without an override, ESCALATE to Director."
            ),
            "notion_runbook_updated_at": "2026-04-10T00:00:00Z",
        },
        # RED HERRING - a 6-month-old issue
        "sentry": {
            "sentry_recent_incidents_90d": 0,
            "sentry_note": "An old 2025-12 incident affected Helix briefly but resolved within hours. Unrelated.",
        },
    },
    distractor_sources=["sentry"],
    catalog=_FULL_CATALOG,
    expected_decision="escalate",  # ask_human path acceptable
    expected_min_confidence=0.55,  # low conviction expected
    expected_findings_keywords=[
        "no override",
        "no strategic",
        "47",  # days past due
        "runbook",
    ],
    must_not_findings_keywords=[
        "sentry",
        "approve",  # agent should NOT autonomously decide
    ],
    notes=(
        "Genuine human-judgment call: customer is using product daily, AE has a "
        "verbal CTO promise, no override on file. Suspending follows runbook but "
        "tanks the renewal. Not suspending violates the SOP and ignores CFO. The "
        "agent should call ask_human OR conclude with decision_action='escalate', "
        "naming the tradeoff cleanly. Either is acceptable; an autonomous "
        "approve/suspend decision is wrong."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S06 - Failed payment with subtle new-account-fraud red flags
# ──────────────────────────────────────────────────────────────────────

_S06 = Scenario(
    case_id="S06-quantum-fraud-flags",
    pattern_name="fraud_red_flags",
    trigger_text=(
        "Stripe webhook + ops comment from @evan:\n"
        "\"Failed payment on $50k invoice for Quantum Synth, INV-7732. Customer wants us "
        "to retry the charge. Deal was just closed 3 weeks ago by Jordan (new AE). Just "
        "want to make sure we're not getting hosed before I queue another attempt - feels "
        "off but I can't put my finger on why.\"\n\n"
        "Customer: Quantum Synth (cus_QSynth, support@quantum-synth.io)\n"
        "Invoice INV-7732 · $50,000 USD · charge failed 'insufficient_funds' on 2026-06-13"
    ),
    dispute_header={
        "dispute_id": "INV-7732-fraud-suspect",
        "dispute_amount_minor": 5000000,
        "dispute_currency": "usd",
        "dispute_reason": "failed_payment",
        "dispute_status": "open",
        "dispute_evidence_due_by": "2026-07-15T00:00:00Z",
        "customer_email": "support@quantum-synth.io",
        "stripe_customer_id": "cus_QSynth",
    },
    world={
        "stripe": {
            "invoice_total_minor": 5000000,
            "invoice_status": "open",
            "charge_last_attempted_at": "2026-06-13T15:30:00Z",
            "charge_last_failure_reason": "insufficient_funds",
            "subscription_status": "trialing",  # never paid
            "subscription_age_days": 35,
            "stripe_radar_risk_score": 68,
            "stripe_radar_rules_triggered": [
                "high_charge_first_attempt",
                "young_customer_domain",
            ],
            "prior_disputes_14mo": 0,
            "prior_refunds_24mo": 0,
        },
        "salesforce": {
            "sf_account_name": "Quantum Synth",
            "sf_deal_closed_at": "2026-05-24T00:00:00Z",
            "sf_deal_amount_minor": 5000000,
            "sf_account_owner": "jordan@us",
            "sf_account_owner_tenure_days": 62,  # new AE
            "sf_account_owner_prior_deals_closed": 1,
            "sf_health": "unknown",
        },
        "hubspot": {
            "hs_company_id": "99119",
            "hs_company_industry": "AI / fintech (self-reported)",
            "hs_company_website_age_days": 78,  # very new
            "hs_company_linkedin_present": False,
            "hs_company_employee_count_estimated": "unknown / not listed",
            "hs_company_domain_whois_registered": "2026-03-21",
        },
        "intercom": {
            "ic_conversations_90d": 0,
            "ic_formal_cancel_requests_90d": 0,
        },
        "zendesk": {
            "zd_tickets_90d": 0,
        },
        "posthog": {
            "ph_last_active_at": "2026-05-26T11:00:00Z",
            "ph_logins_30d": 3,
            "ph_distinct_users_active_30d": 2,
            "ph_critical_actions_14d": 0,
            "ph_signup_at": "2026-05-22T09:00:00Z",
        },
        "notion": {
            "notion_runbook_title": "Anti-Fraud SOP - 2026",
            "notion_runbook_body": (
                "BEFORE retrying ANY charge >$25k where (a) customer-domain age <90 days "
                "AND (b) product-usage <10 critical events AND (c) the account-owning AE "
                "has <90 days tenure, the dispute must be escalated to the Fraud Review "
                "Committee. Do NOT auto-retry. Do NOT auto-refund (refund signals legitimacy). "
                "Tag the case 'fraud-review'."
            ),
            "notion_runbook_updated_at": "2026-01-15T00:00:00Z",
        },
        # RED HERRING - a different "Quantum Synth Corp" (legitimate)
        "hubspot_dup_check": {
            "hs_dup_company_note": (
                "Separate company 'Quantum Synth Corp' (industrial sensors, 200 employees, "
                "10y old domain). DIFFERENT entity. Don't conflate."
            ),
        },
    },
    distractor_sources=["hubspot_dup_check"],
    catalog=[*_FULL_CATALOG, {"name": "hubspot_dup_check", "tables": ["lookups"]}],
    expected_decision="escalate",
    expected_min_confidence=0.75,
    expected_findings_keywords=[
        "domain age",
        "fraud",
        "radar",
        "new ae",
    ],
    must_not_findings_keywords=[
        "industrial sensors",
        "quantum synth corp",  # different entity
        "retry",  # do NOT recommend retrying
    ],
    notes=(
        "Three fraud signals stack: new domain (78d), new AE (62d), almost no usage "
        "(0 critical actions). Notion runbook is explicit - escalate to Fraud Review. "
        "The HubSpot dup-check is a red herring (different entity); the agent must "
        "not be fooled by the legitimate company sharing the name."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S07 - Tiny dispute, auto-accept policy. Agent must NOT over-investigate
# ──────────────────────────────────────────────────────────────────────

_S07 = Scenario(
    case_id="S07-joescoffee-auto-accept",
    pattern_name="thin_low_value_auto_accept",
    trigger_text=(
        "Forwarded Stripe email:\n"
        "\"Small chargeback came in - $42 on dp_3MqJoeCo, customer says didn't recognize "
        "the charge. We get these constantly with self-serve accounts.\"\n\n"
        "Customer: joe@joescoffee-pdx.example (self-serve, no account record)\n"
        "Charge ch_3MqJoeCo · $42 USD · 2026-04-04\n"
        "Dispute reason: fraudulent"
    ),
    dispute_header={
        "dispute_id": "dp_3MqJoeCo",
        "dispute_amount_minor": 4200,
        "dispute_currency": "usd",
        "dispute_reason": "fraudulent",
        "dispute_status": "needs_response",
        "dispute_evidence_due_by": "2026-06-20T00:00:00Z",
        "customer_email": "joe@joescoffee-pdx.example",
        "stripe_customer_id": "cus_JoeCo",
    },
    world={
        "stripe": {
            "charge_id": "ch_3MqJoeCo",
            "charge_amount_minor": 4200,
            "charge_created": "2026-04-04T11:00:00Z",
            "subscription_status": "canceled",
            "subscription_canceled_at": "2026-04-05T00:00:00Z",
            "prior_disputes_14mo": 0,
            "prior_refunds_24mo": 0,
            "lifetime_revenue_minor": 4200,
            "lifetime_charges": 1,
        },
        "salesforce": {
            "sf_note": "No account record. Self-serve only.",
        },
        "hubspot": {
            "hs_note": "No company record on file.",
        },
        "intercom": {
            "ic_conversations_90d": 0,
        },
        "zendesk": {
            "zd_tickets_90d": 0,
        },
        "posthog": {
            "ph_last_active_at": "2026-04-04T11:30:00Z",
            "ph_logins_30d": 1,
            "ph_signup_at": "2026-04-04T10:00:00Z",
            "ph_critical_actions_lifetime": 1,
        },
        "notion": {
            "notion_policy_title": "Self-Serve Chargeback Policy - 2026",
            "notion_policy_body": (
                "Auto-accept ANY dispute under $100 from self-serve accounts with no CRM "
                "record, lifetime revenue <$200, and <5 critical actions. Operational cost "
                "to fight exceeds amount recovered. Issue refund, close case in under 5 minutes."
            ),
        },
    },
    distractor_sources=[],  # this scenario is anti-trap - no red herrings, just don't overthink
    catalog=_FULL_CATALOG,
    expected_decision="accept",
    expected_amount_minor=4200,
    expected_min_confidence=0.80,
    expected_findings_keywords=[
        "auto-accept",
        "self-serve",
        "policy",
    ],
    must_not_findings_keywords=[],
    notes=(
        "Anti-over-investigation test. The right answer is a 30-second clean accept. "
        "Bad agents will waste tools probing CRM/support, find nothing, and still "
        "conclude - wasting wall-clock. Score this on efficiency too: <3 findings is OK, "
        "<2 coral_sql calls is great."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S08 - Multi-customer migration: charge happened on the orphan
# ──────────────────────────────────────────────────────────────────────

_S08 = Scenario(
    case_id="S08-saga-migration-orphan",
    pattern_name="multi_customer_migration",
    trigger_text=(
        "Stripe webhook + slack:\n"
        "\"Saga Robotics is disputing $3,600 on cus_oldSaga. They say they cancelled "
        "back in March when we migrated them to cus_newSaga. They've been paying on "
        "cus_newSaga for 3 months and now we randomly charged the OLD customer? Why "
        "did that even happen?\"\n\n"
        "Customer: Saga Robotics - TWO stripe records:\n"
        "  cus_oldSaga (the disputed charge)\n"
        "  cus_newSaga (their active sub since March)\n"
        "Dispute dp_3MqSagaOrph · $3,600 USD · reason: subscription_canceled"
    ),
    dispute_header={
        "dispute_id": "dp_3MqSagaOrph",
        "dispute_amount_minor": 360000,
        "dispute_currency": "usd",
        "dispute_reason": "subscription_canceled",
        "dispute_status": "needs_response",
        "dispute_evidence_due_by": "2026-06-25T00:00:00Z",
        "customer_email": "ar@saga-robotics.example",
        "stripe_customer_id": "cus_oldSaga",
    },
    world={
        "stripe": {
            # Orphan customer (the disputed one)
            "orphan_customer_id": "cus_oldSaga",
            "orphan_subscription_id": "sub_oldSaga",
            "orphan_subscription_status": "active",  # SHOULD BE canceled - this is the bug
            "orphan_subscription_cancel_at_period_end": True,  # was set
            "orphan_subscription_cancel_intended_at": "2026-03-12T00:00:00Z",
            "orphan_last_charge_id": "ch_3MqSagaOrph",
            "orphan_last_charge_at": "2026-06-04T08:00:00Z",
            "orphan_last_charge_amount_minor": 360000,
            # The legitimate active customer
            "active_customer_id": "cus_newSaga",
            "active_subscription_id": "sub_newSaga",
            "active_subscription_status": "active",
            "active_subscription_paid_through": "2026-08-15T00:00:00Z",
            "active_paid_invoices_since_march": 3,
        },
        "salesforce": {
            "sf_account_name": "Saga Robotics",
            "sf_account_external_ids": ["cus_oldSaga", "cus_newSaga"],  # both mapped
            "sf_arr_minor": 4320000,  # $43.2k
            "sf_health": "green",
        },
        "intercom": {
            "ic_conversations_90d": 1,
            "ic_migration_thread_at": "2026-03-10T00:00:00Z",
            "ic_migration_thread_subject": "Confirming migration to new billing entity",
            "ic_migration_thread_body": (
                "Hi Saga - we've migrated your billing to cus_newSaga effective Mar 12. "
                "Your old subscription will cancel at period end. New invoices will go "
                "to the same AP contact. - Billing Ops"
            ),
        },
        "posthog": {
            "ph_last_active_at": "2026-06-15T17:00:00Z",
            "ph_logins_30d": 28,
            "ph_distinct_users_active_30d": 12,
            "ph_active_under_customer": "cus_newSaga",
        },
        "notion": {
            "notion_runbook_title": "Duplicate Customer / Migration Cleanup SOP",
            "notion_runbook_body": (
                "When an orphan customer charge occurs after a migration: ALWAYS (a) refund "
                "the orphan charge in full, (b) force-cancel the orphan subscription, (c) "
                "file an engineering ticket against billing-bug-7172 (the known migration "
                "cleanup defect). Do NOT fight - the charge is operationally invalid."
            ),
        },
        "linear": {
            "linear_open_issues_billing_bug_7172": 1,
            "linear_issue_title": "Migration cleanup: orphan subs occasionally re-bill (billing-bug-7172)",
            "linear_issue_status": "in_progress",
            "linear_issue_assigned_to": "platform-billing-team",
        },
        # RED HERRING - an unrelated finance ticket from the same period
        "zendesk": {
            "zd_tickets_90d": 1,
            "zd_last_subject": "Finance question for Saga Foods (different customer!)",
            "zd_last_status": "solved",
            "zd_last_at": "2026-03-20T00:00:00Z",
            "zd_unrelated_company_note": (
                "Saga Foods (different company) had a billing question in March - totally "
                "unrelated to Saga Robotics. Don't conflate."
            ),
        },
    },
    distractor_sources=["zendesk"],
    catalog=_FULL_CATALOG,
    expected_decision="refund",
    expected_amount_minor=360000,
    expected_min_confidence=0.85,
    expected_findings_keywords=[
        "migration",
        "orphan",
        "cus_oldsaga",  # cite the orphan
        "billing-bug-7172",  # cite the engineering ticket
    ],
    must_not_findings_keywords=[
        "saga foods",
        "fight",  # do NOT recommend fighting
    ],
    notes=(
        "The customer is 100% right; this is an internal billing bug. Refund full "
        "$3,600, force-cancel orphan sub, escalate the bug to engineering. The "
        "Zendesk red herring is a totally unrelated 'Saga Foods' ticket."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# Battery
# ──────────────────────────────────────────────────────────────────────

SCENARIOS: list[Scenario] = [_S01, _S02, _S03, _S04, _S05, _S06, _S07, _S08]


def by_id(case_id: str) -> Scenario | None:
    for s in SCENARIOS:
        if s.case_id == case_id:
            return s
    return None
