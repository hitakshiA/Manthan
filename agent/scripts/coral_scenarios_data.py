"""Five hard scenarios for the Coral end-to-end battery.

Each scenario:
  - Uses a DIFFERENT subset of the 10 sources (varied surface)
  - Uses REAL Coral column names (no toy `amount_minor`; real `amount`)
  - 1000+ rows per noisy table (volume forces real filtering)
  - Multiple cross-source identity collisions / distractors
  - Clear ground truth so we can score the agent
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from coral_scenarios import (
    make_datadog_monitor,
    make_gmail_thread,
    make_hubspot_company,
    make_hubspot_deal,
    make_intercom_contact,
    make_intercom_conversation,
    make_notion_page,
    make_pagerduty_incident,
    make_salesforce_account,
    make_salesforce_opportunity,
    make_sentry_issue,
    make_stripe_charge,
    make_stripe_customer,
    make_stripe_dispute,
    make_stripe_invoice,
    make_stripe_subscription,
    make_zendesk_ticket,
    make_zendesk_user,
    noise_datadog_monitors,
    noise_gmail_threads,
    noise_hubspot_companies,
    noise_intercom_conversations,
    noise_notion_pages,
    noise_pagerduty_incidents,
    noise_salesforce_accounts,
    noise_sentry_issues,
    noise_stripe_customers,
    noise_stripe_disputes,
    noise_zendesk_tickets,
)
from scenarios import Scenario

# Repeatable noise. Each scenario picks its own seed so rows differ across.
random.seed(42)


# ──────────────────────────────────────────────────────────────────────
# S01 - Friendly fraud (Acme Genomics)
# Sources: stripe, intercom, zendesk, gmail, notion, salesforce
# Decision: fight
# ──────────────────────────────────────────────────────────────────────

_S01_EMAIL = "ops@acme-genomics.example"
_S01_NAME = "Acme Genomics"
_S01_CUS = "cus_AcmeGn"
_S01_ACCT = "001NAcmeGn"
_S01_ZD_USER = 800100  # zendesk user id for this customer

_S01_WORLD: dict[str, dict[str, list]] = {
    "stripe": {
        "disputes": [
            make_stripe_dispute(
                id="dp_3MqAcmeRen",
                customer=_S01_CUS,
                charge="ch_3MqAcmeRen",
                amount=420000,
                reason="subscription_canceled",
                status="needs_response",
                created="2026-05-09T11:02:00",
                evidence_due_by="2026-06-12T00:00:00",
            ),
            *noise_stripe_disputes(40, seed=101),
        ],
        "charges": [
            make_stripe_charge(
                id="ch_3MqAcmeRen", customer=_S01_CUS, amount=420000,
                status="succeeded", created="2026-05-09T11:02:00",
                description="Acme Genomics - Pro Annual renewal",
            ),
            # Acme prior years
            make_stripe_charge(id="ch_Acme2025", customer=_S01_CUS,
                               amount=420000, status="succeeded",
                               created="2025-05-09T11:02:00",
                               description="Acme Genomics - Pro Annual renewal"),
            make_stripe_charge(id="ch_Acme2024", customer=_S01_CUS,
                               amount=360000, status="succeeded",
                               created="2024-05-09T11:02:00",
                               description="Acme Genomics - Pro Annual initial"),
        ],
        "subscriptions": [
            make_stripe_subscription(
                id="sub_AcmeGn", customer=_S01_CUS, status="active",
                cancel_at_period_end=False, canceled_at=None,
                current_period_start="2026-05-09T00:00:00",
                current_period_end="2027-05-09T00:00:00",
                created="2024-05-09T11:02:00", plan_nickname="Pro Annual",
            ),
            # Older Acme subs that ENDED (red-herring for "did they cancel?")
            make_stripe_subscription(
                id="sub_AcmeGn_y1", customer=_S01_CUS, status="canceled",
                cancel_at_period_end=False,
                canceled_at="2024-05-09T00:00:00",
                current_period_start="2023-05-09T00:00:00",
                current_period_end="2024-05-09T00:00:00",
                created="2023-05-09T11:02:00", plan_nickname="Pro Annual",
            ),
        ],
        "customers": [
            make_stripe_customer(id=_S01_CUS, email=_S01_EMAIL,
                                 name=_S01_NAME,
                                 created="2023-04-15T11:02:00",
                                 description="Acme Genomics - sequencing analytics"),
            # 80 noise customers
            *noise_stripe_customers(80, seed=102),
        ],
    },
    "intercom": {
        "conversations": [
            # Acme's recent (non-cancel) conversations
            make_intercom_conversation(
                id="C-Acme-001",
                source_subject="Data export options",
                source_author_email=_S01_EMAIL,
                source_author_name="Priya R (Acme Ops)",
                state="closed",
                created_at=1741449600,  # 2026-03-08
                source_body_snippet=(
                    "Hi team - we're evaluating whether to continue with you "
                    "for another year and need to understand what data export "
                    "looks like. Could you walk us through the formats? We're "
                    "not planning to cancel right now, just want to know "
                    "what's available in case our review comes back negative."
                ),
            ),
            make_intercom_conversation(
                id="C-Acme-002",
                source_subject="Re: Data export options",
                source_author_email=_S01_EMAIL,
                source_author_name="Priya R (Acme Ops)",
                state="closed",
                created_at=1741536000,  # 2026-03-09
                source_body_snippet="Thanks for the walkthrough - that's helpful. No action needed for now.",
            ),
            make_intercom_conversation(
                id="C-Acme-003",
                source_subject="API rate limit question",
                source_author_email=_S01_EMAIL,
                state="closed",
                created_at=1745318400,  # 2026-04-22
                source_body_snippet="Hit 429s during nightly ingest. Can you bump to 200rps?",
            ),
            # 600 noise conversations (~10% mention cancel from OTHER customers)
            *noise_intercom_conversations(600, seed=103),
        ],
        "contacts": [
            make_intercom_contact(
                id="ICON-Acme-001",
                email=_S01_EMAIL,
                name="Priya R (Acme Ops)",
                last_seen_at=1746423000,  # 2026-05-04 - 5 days before dispute
                last_replied_at=1745405000,
                created_at=1683633720,
            ),
        ],
    },
    "zendesk": {
        "users": [
            make_zendesk_user(id=_S01_ZD_USER, email=_S01_EMAIL, name="Priya R"),
        ],
        "tickets": [
            # Acme's tickets - neither is cancel-related
            make_zendesk_ticket(
                id=600100, subject="Add new viewer-role user",
                description="Need to invite analytics@acme-genomics.example as viewer.",
                status="solved", requester_id=_S01_ZD_USER,
                created_at="2026-02-04T09:00:00",
            ),
            make_zendesk_ticket(
                id=600101, subject="Webhook delivery question",
                description="Some webhook deliveries are 2-3 minutes delayed. Is that normal?",
                status="solved", requester_id=_S01_ZD_USER,
                created_at="2026-04-30T15:00:00",
            ),
            # 300 noise tickets from other customers (some mention cancel)
            *noise_zendesk_tickets(300, seed=104),
        ],
    },
    "gmail": {
        "threads": [
            # Acme's Q1 check-in (NOT a cancel email)
            make_gmail_thread(
                id="gm_Acme_001",
                snippet="Acme Genomics Q1 check-in - discussed renewal expectations, no objections raised. - CSM",
                history_id="200001",
            ),
            # 200 noise threads from many customers. NOTE: noise pool includes
            # "please cancel" snippets from OTHER customers - red herrings.
            *noise_gmail_threads(200, seed=105),
        ],
    },
    "notion": {
        "pages": [
            # THE current authoritative SOP
            make_notion_page(
                id="n_refunds_2026_sop",
                title="Refunds & Disputes - 2026 SOP (CURRENT)",
                body=(
                    "OFFICIAL CURRENT POLICY. For subscription_canceled chargebacks: "
                    "FIGHT when (a) no formal cancellation request exists across "
                    "Intercom/Zendesk/Gmail, AND (b) documented product usage exists "
                    "within 14 days before the dispute. An informal mention of "
                    "considering cancellation (e.g. 'we're evaluating') is NOT a "
                    "cancellation request. Cite this policy by id n_refunds_2026_sop."
                ),
                status="current",
                tags="refunds,sop,policy,authoritative",
                last_edited_time="2026-02-10T09:00:00",
            ),
            # 50 noisy policy-ish pages (deprecated, FAQ, sales playbooks, etc.)
            *noise_notion_pages(50, seed=106),
        ],
    },
    "salesforce": {
        "accounts": [
            make_salesforce_account(
                id=_S01_ACCT, name=_S01_NAME, industry="genomics",
                annual_revenue=4200000, number_of_employees=85,
                billing_country="USA", type_="Customer - Direct",
            ),
            *noise_salesforce_accounts(60, seed=107),
        ],
        "opportunities": [
            make_salesforce_opportunity(
                id="opp_Acme_2024", name="Acme Genomics - New", stage_name="Closed Won",
                amount=360000, close_date="2024-05-09", account_id=_S01_ACCT,
            ),
            make_salesforce_opportunity(
                id="opp_Acme_2025", name="Acme Genomics - Renewal", stage_name="Closed Won",
                amount=420000, close_date="2025-05-09", account_id=_S01_ACCT,
            ),
            make_salesforce_opportunity(
                id="opp_Acme_2026", name="Acme Genomics - Renewal", stage_name="Closed Won",
                amount=420000, close_date="2026-05-09", account_id=_S01_ACCT,
            ),
        ],
    },
}


SCENARIO_S01 = Scenario(
    case_id="S01C-acme-real-coral",
    pattern_name="friendly_fraud_real_coral",
    trigger_text=(
        "Slack DM from @priya (CSM):\n"
        "\"Hey can you take dp_3MqAcmeRen? Acme Genomics is fighting the $4,200 annual "
        "renewal. They keep insisting they tried to cancel earlier this year - I poked "
        "around Intercom and there's something from a couple months back but it didn't "
        "feel like a formal cancel request to me. They're using the product. Brief "
        "please by EOD Thu (evidence due Fri).\"\n\n"
        "Customer: Acme Genomics (cus_AcmeGn, ops@acme-genomics.example)\n"
        "Dispute: dp_3MqAcmeRen · $4,200 USD · reason: subscription_canceled\n"
        "Evidence deadline: 12 June 2026\n"
    ),
    dispute_header={},
    duckdb_world=_S01_WORLD,
    expected_decision="fight",
    expected_min_confidence=0.80,
    expected_findings_keywords=[
        "no formal cancel",
        "active",
        "data export",  # the informal mention
        "policy",
    ],
    must_not_findings_keywords=[
        "acme logistics", "acme consulting", "acme fintech",
        "deprecated", "2024 version", "faq",
    ],
    notes=(
        "All real Coral schemas. Real volume: 600 intercom convos, 300 zendesk tickets, "
        "200 gmail threads, 50 notion pages. Acme is one of 4 'Acme'-named companies in "
        "the noise (Logistics, Consulting, Fintech). Multiple noise convos/tickets from "
        "other customers mention 'cancel'. Multiple notion pages match %refund%."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S02 - SLA partial credit (Northwind Logistics)
# Sources: stripe, salesforce, pagerduty, datadog, notion, intercom
# Decision: refund (PARTIAL - $111 credit, NOT the $2,250 short-pay)
# ──────────────────────────────────────────────────────────────────────

_S02_EMAIL = "ar@northwind-logi.example"
_S02_NAME = "Northwind Logistics"
_S02_CUS = "cus_Nwnd2024"
_S02_ACCT = "001NNorthW"

_S02_WORLD: dict[str, dict[str, list]] = {
    "stripe": {
        "invoices": [
            make_stripe_invoice(
                id="in_INV9821", customer=_S02_CUS, amount_due=900000,
                amount_paid=675000, status="open",
                due_date="2026-05-30T00:00:00", created="2026-05-01T00:00:00",
                description="Monthly Enterprise plan - May 2026",
            ),
        ],
        "charges": [
            make_stripe_charge(
                id="ch_INV9821_partial", customer=_S02_CUS, amount=675000,
                status="succeeded", created="2026-05-20T10:00:00",
                description="Partial payment on INV-9821 (customer short-pay)",
            ),
        ],
        "subscriptions": [
            make_stripe_subscription(
                id="sub_NorthW", customer=_S02_CUS, status="active",
                current_period_start="2026-05-01T00:00:00",
                current_period_end="2026-06-01T00:00:00",
                created="2024-05-01T11:00:00", plan_nickname="Enterprise Annual",
            ),
        ],
        "customers": [
            make_stripe_customer(id=_S02_CUS, email=_S02_EMAIL,
                                 name=_S02_NAME, created="2024-05-01T11:00:00",
                                 description="Northwind Logistics - fleet routing"),
            *noise_stripe_customers(50, seed=201),
        ],
    },
    "salesforce": {
        "accounts": [
            make_salesforce_account(
                id=_S02_ACCT, name=_S02_NAME, industry="logistics",
                annual_revenue=10800000, number_of_employees=350,
                billing_country="USA", type_="Customer - Direct",
            ),
            *noise_salesforce_accounts(40, seed=202),
        ],
    },
    "pagerduty": {
        "incidents": [
            # The SEV-2 our customer experienced
            make_pagerduty_incident(
                id="PD-INC-44219",
                title="EU region: degraded p95 latency on routing config rollout",
                severity="SEV-2", status="resolved",
                created_at="2026-05-14T09:15:00",
                resolved_at="2026-05-14T13:42:00",
                service_id="PSVC-201",
                duration_seconds=16020,  # 4hr 27min
            ),
            *noise_pagerduty_incidents(80, seed=203),
        ],
    },
    "datadog": {
        "monitors": [
            # Production monitors that fired during the May 14 window
            make_datadog_monitor(
                id=85001, name="p95_routing_latency_alert",
                type_="metric alert", status="Alert",
                message="p95 latency above 1500ms threshold during EU rollout window 2026-05-14 09:00-14:00",
                tags="env:prod,team:platform,sev:2",
            ),
            make_datadog_monitor(
                id=85002, name="api_error_rate_alert",
                type_="metric alert", status="Alert",
                message="error rate spike to 4.1% on May 14 09:15-13:42",
                tags="env:prod,team:platform",
            ),
            *noise_datadog_monitors(40, seed=204),
        ],
    },
    "notion": {
        "pages": [
            make_notion_page(
                id="n_northw_msa_addendum",
                title="Northwind Logistics MSA - SLA Addendum (CURRENT)",
                body=(
                    "AUTHORITATIVE MSA TERMS for Northwind. Section 7.4: SLA "
                    "credit = (downtime_hours / total_hours_in_month) * "
                    "monthly_fee * multiplier. Multiplier=2 for SEV-2, 4 for "
                    "SEV-1. Credits cap at one month's fee. Customer must claim "
                    "within 30 days. Customers may NOT unilaterally short-pay "
                    "invoices - SLA credits are issued as billing adjustments. "
                    "Worked example: 4.45 hours / 720 monthly hours * $9,000 * "
                    "2 = approximately $111 credit."
                ),
                status="current",
                tags="msa,sla,northwind,authoritative",
                last_edited_time="2025-11-02T00:00:00",
            ),
            *noise_notion_pages(40, seed=205),
        ],
    },
    "intercom": {
        "conversations": [
            make_intercom_conversation(
                id="C-Nwnd-001",
                source_subject="Outage May 14 - credit request",
                source_author_email=_S02_EMAIL,
                source_author_name="Marcus T (Northwind AR)",
                state="open",
                created_at=1747728000,  # 2026-05-20
                source_body_snippet=(
                    "Saw degraded performance May 14 morning. We had a "
                    "customer-facing impact. Reducing our renewal payment by 25%."
                ),
            ),
            *noise_intercom_conversations(400, seed=206),
        ],
        "contacts": [
            make_intercom_contact(
                id="ICON-Nwnd-001", email=_S02_EMAIL, name="Marcus T",
                last_seen_at=1747900000, created_at=1700000000,
            ),
        ],
    },
}


SCENARIO_S02 = Scenario(
    case_id="S02C-northwind-sla-real",
    pattern_name="sla_partial_credit_real_coral",
    trigger_text=(
        "Forwarded email from @marcus (AR):\n"
        "\"FYI - Northwind short-paid INV-9821 by 25% ($2,250 on a $9k invoice). "
        "They cite 'SLA breach during May 14-15 outage.' I'm not sure we owe them "
        "anything - please double-check. AE wants us to not ding the renewal.\"\n\n"
        "Customer: Northwind Logistics (cus_Nwnd2024, ar@northwind-logi.example)\n"
        "Invoice INV-9821 · $9,000 USD · paid $6,750 (short $2,250)\n"
        "Cited window: 2026-05-14 09:00 to 2026-05-15 14:00"
    ),
    dispute_header={},
    duckdb_world=_S02_WORLD,
    expected_decision="refund",
    expected_amount_minor=11100,  # ~$111 partial credit
    expected_min_confidence=0.70,
    expected_findings_keywords=["sev-2", "pagerduty", "msa", "credit"],
    must_not_findings_keywords=["full refund", "2,250"],
    notes=(
        "Real schemas: pagerduty.incidents (374 cols, signal is in title/duration), "
        "datadog.monitors (alert message + tags). Customer claim is REAL but math is "
        "wrong. Right answer: $111 credit not $2,250."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S03 - AE off-contract promise (Globex Software)
# Sources: stripe, salesforce, gmail, hubspot, notion
# Decision: refund (full $8,200)
# ──────────────────────────────────────────────────────────────────────

_S03_EMAIL = "accounting@globex.example"
_S03_NAME = "Globex Software"
_S03_CUS = "cus_Globex"
_S03_ACCT = "001NGlobex"
_S03_HS = "50100"

_S03_WORLD: dict[str, dict[str, list]] = {
    "stripe": {
        "invoices": [
            make_stripe_invoice(
                id="in_INV7732", customer=_S03_CUS,
                amount_due=820000, amount_paid=0,
                status="open", due_date="2026-06-25T00:00:00",
                created="2026-06-10T00:00:00",
                description="Q3 seat overage: 15 seats above contracted 200",
            ),
        ],
        "subscriptions": [
            make_stripe_subscription(
                id="sub_Globex", customer=_S03_CUS, status="active",
                current_period_start="2026-01-01T00:00:00",
                current_period_end="2026-12-31T00:00:00",
                created="2024-01-01T11:00:00",
                plan_nickname="Pro Annual (200 seats)",
            ),
        ],
        "customers": [
            make_stripe_customer(id=_S03_CUS, email=_S03_EMAIL,
                                 name=_S03_NAME, created="2024-01-01T11:00:00",
                                 description="Globex Software - Pro Annual 200 seats"),
            *noise_stripe_customers(60, seed=301),
        ],
    },
    "salesforce": {
        "accounts": [
            make_salesforce_account(
                id=_S03_ACCT, name=_S03_NAME, industry="software",
                annual_revenue=42000000, number_of_employees=500,
                billing_country="USA", owner_id="mark_us_001",
            ),
            *noise_salesforce_accounts(50, seed=302),
        ],
        "opportunities": [
            make_salesforce_opportunity(
                id="opp_Globex_2026", name="Globex Software - New Pro Annual",
                stage_name="Closed Won", amount=4000000, close_date="2026-01-15",
                account_id=_S03_ACCT,
            ),
        ],
    },
    "gmail": {
        "threads": [
            # THE smoking gun - AE Mark's promise
            make_gmail_thread(
                id="gm_Globex_AEpromise",
                snippet=(
                    "From: mark@us (AE) To: accounting@globex.example: Hey Sarah - "
                    "we can flex you up to 220 seats at no extra charge through end "
                    "of Q3 as we'd talked about. Just keep me in the loop on hiring. "
                    "- Mark, 2026-03-18"
                ),
                history_id="300001",
            ),
            *noise_gmail_threads(150, seed=303),
        ],
    },
    "hubspot": {
        "companies": [
            make_hubspot_company(
                id=_S03_HS, name=_S03_NAME, domain="globex.example",
                industry="software", annualrevenue=42000000,
                numberofemployees=500, country="USA",
            ),
            *noise_hubspot_companies(40, seed=304),
        ],
        "deals": [
            make_hubspot_deal(
                id="deal_Globex_2026", dealname="Globex Software - Pro Annual",
                dealstage="closedwon", amount=4000000,
                closedate="2026-01-15",
            ),
        ],
    },
    "notion": {
        "pages": [
            make_notion_page(
                id="n_ae_promises_sop",
                title="Off-contract AE Promises - RevOps SOP (CURRENT)",
                body=(
                    "AUTHORITATIVE POLICY. If a Gmail/Slack AE promise exists "
                    "but no Salesforce opportunity amendment was filed, the "
                    "promise STILL binds the company (good-faith reliance "
                    "doctrine). Refund or credit the affected invoice in full, "
                    "then file the missing amendment retroactively. The customer "
                    "relied on the AE's representation."
                ),
                status="current",
                tags="revops,sop,ae,authoritative",
                last_edited_time="2026-01-15T00:00:00",
            ),
            make_notion_page(
                id="n_globex_msa",
                title="Globex MSA - Seat Billing Terms",
                body=(
                    "Standard MSA. Seat overage billed at contract rate * overage_count, "
                    "prorated monthly. Side letters or AE-issued promises must be "
                    "reflected as opportunity amendments in Salesforce before billing "
                    "automation honors them. See RevOps SOP for handling promises "
                    "that lacked amendment."
                ),
                status="current", tags="msa,globex",
                last_edited_time="2024-01-15T00:00:00",
            ),
            *noise_notion_pages(40, seed=305),
        ],
    },
}


SCENARIO_S03 = Scenario(
    case_id="S03C-globex-ae-real",
    pattern_name="ae_promise_real_coral",
    trigger_text=(
        "Linear ticket from @ops-billing:\n"
        "\"Customer Globex Software disputing $8,200 expansion invoice INV-7732. They "
        "claim AE Mark promised seat flex up to 220 at no extra charge in a Gmail "
        "thread. Salesforce shows the 200-seat contract. Who's right?\"\n\n"
        "Customer: Globex Software (cus_Globex, accounting@globex.example)\n"
        "Invoice INV-7732 · $8,200 USD · Q3 seat overage"
    ),
    dispute_header={},
    duckdb_world=_S03_WORLD,
    expected_decision="refund",
    expected_amount_minor=820000,
    expected_min_confidence=0.75,
    expected_findings_keywords=["ae", "gmail", "promise", "220"],
    must_not_findings_keywords=["fight"],
    notes=(
        "Gmail snippet contains the smoking gun. SF says 200 contracted. Notion has "
        "BOTH the MSA (says amendment required) AND the RevOps SOP (says good-faith "
        "reliance binds). Right answer favors the SOP."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S04 - VAT compliance (Bottega Romano)
# Sources: stripe, salesforce, hubspot, intercom, notion, sentry
# Decision: refund $900 (VAT portion only, NOT full $5,400)
# ──────────────────────────────────────────────────────────────────────

_S04_EMAIL = "contab@bottega-romano.example"
_S04_NAME = "Bottega Romano S.r.l."
_S04_CUS = "cus_Bottega"
_S04_ACCT = "001NBottega"

_S04_WORLD: dict[str, dict[str, list]] = {
    "stripe": {
        "invoices": [
            make_stripe_invoice(
                id="in_INV4521", customer=_S04_CUS,
                amount_due=540000, amount_paid=0,
                status="open", due_date="2026-06-30T00:00:00",
                created="2026-06-01T00:00:00",
                description="Pro Monthly + 20% IT VAT = $4500 product + $900 VAT",
            ),
        ],
        "customers": [
            make_stripe_customer(
                id=_S04_CUS, email=_S04_EMAIL, name=_S04_NAME,
                created="2025-09-12T00:00:00",
                description=(
                    "Bottega Romano - Italian B2B. VAT ID IT12345678901 "
                    "(VIES-verified 2025-09-12)."
                ),
            ),
            *noise_stripe_customers(50, seed=401),
        ],
    },
    "salesforce": {
        "accounts": [
            make_salesforce_account(
                id=_S04_ACCT, name=_S04_NAME, industry="hospitality",
                annual_revenue=1200000, number_of_employees=18,
                billing_country="Italy", type_="Customer - Direct",
            ),
            *noise_salesforce_accounts(40, seed=402),
        ],
    },
    "hubspot": {
        "companies": [
            make_hubspot_company(
                id="50500", name=_S04_NAME,
                domain="bottega-romano.example", industry="hospitality",
                annualrevenue=1200000, numberofemployees=18, country="Italy",
            ),
            *noise_hubspot_companies(40, seed=403),
        ],
    },
    "intercom": {
        "conversations": [
            make_intercom_conversation(
                id="C-Bott-001",
                source_subject="VAT question - EU business customer",
                source_author_email=_S04_EMAIL,
                source_author_name="Giulia P (Bottega Finance)",
                state="closed",
                created_at=1746163200,  # 2026-05-02
                source_body_snippet=(
                    "Hi, we're an Italian business with valid VAT ID "
                    "IT12345678901. Are we supposed to pay VAT to you, or does "
                    "the reverse-charge mechanism apply? Our accountant is asking."
                ),
            ),
            *noise_intercom_conversations(300, seed=404),
        ],
        "contacts": [
            make_intercom_contact(
                id="ICON-Bott-001", email=_S04_EMAIL,
                name="Giulia P", last_seen_at=1748908800,
                created_at=1726099200,
            ),
        ],
    },
    "notion": {
        "pages": [
            make_notion_page(
                id="n_eu_vat_sop",
                title="EU B2B Tax Handling - RevOps SOP v4 (CURRENT)",
                body=(
                    "AUTHORITATIVE POLICY. EU B2B customers with a VIES-verified "
                    "VAT ID are subject to reverse-charge VAT - we do NOT charge "
                    "VAT on their invoices. They self-report VAT in their own "
                    "jurisdiction. Configure tax_exempt=true in the billing "
                    "platform once VAT ID is VIES-verified. If a customer is "
                    "INCORRECTLY charged VAT, refund the VAT PORTION ONLY "
                    "(product portion is owed and used) and update the tax_exempt "
                    "flag. Do NOT refund the full invoice."
                ),
                status="current",
                tags="tax,vat,eu,sop,authoritative",
                last_edited_time="2025-10-01T00:00:00",
            ),
            *noise_notion_pages(40, seed=405),
        ],
    },
    "sentry": {
        # Red herring: unrelated infra issue
        "issues": [
            make_sentry_issue(
                id="SENT-EU001",
                title="GDPR cleanup task - unrelated infra refactor",
                status="resolved", level="info", count=3,
                first_seen="2026-03-12T00:00:00",
                last_seen="2026-03-20T00:00:00",
                project="ingest",
            ),
            *noise_sentry_issues(20, seed=406),
        ],
    },
}


SCENARIO_S04 = Scenario(
    case_id="S04C-bottega-vat-real",
    pattern_name="vat_compliance_real_coral",
    trigger_text=(
        "Stripe webhook + slack note from @finance:\n"
        "\"Italian customer is disputing INV-4521 ($5,400 total) - they say they "
        "shouldn't have been charged VAT because they're a business with a valid "
        "IT VAT ID. Avalara computed VAT anyway. I think they have a point but "
        "the dispute is for $5,400 (the whole invoice) which can't be right.\"\n\n"
        "Customer: Bottega Romano S.r.l. (cus_Bottega, contab@bottega-romano.example)\n"
        "Invoice INV-4521 · $5,400 USD ($4,500 product + $900 VAT @ 20%)"
    ),
    dispute_header={},
    duckdb_world=_S04_WORLD,
    expected_decision="refund",
    expected_amount_minor=90000,  # $900 only
    expected_min_confidence=0.75,
    expected_findings_keywords=["reverse", "vat id", "vies", "italy"],
    must_not_findings_keywords=["5,400", "$5400", "full refund"],
    notes=(
        "Customer description in stripe.customers has the VAT ID. Notion SOP says "
        "refund VAT portion only. Sentry GDPR issue is a red herring."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# S05 - Migration orphan (Saga Robotics)
# Sources: stripe, salesforce, intercom, notion, zendesk
# Decision: refund full $3,600 (orphan customer record was charged in error)
# ──────────────────────────────────────────────────────────────────────

_S05_EMAIL = "ar@saga-robotics.example"
_S05_NAME = "Saga Robotics"
_S05_OLD_CUS = "cus_oldSaga"
_S05_NEW_CUS = "cus_newSaga"
_S05_ACCT = "001NSaga"
_S05_ZD_USER = 800200

_S05_WORLD: dict[str, dict[str, list]] = {
    "stripe": {
        "disputes": [
            make_stripe_dispute(
                id="dp_3MqSagaOrph",
                customer=_S05_OLD_CUS,  # THE ORPHAN
                charge="ch_3MqSagaOrph",
                amount=360000,
                reason="subscription_canceled",
                status="needs_response",
                created="2026-06-05T08:00:00",
                evidence_due_by="2026-06-25T00:00:00",
            ),
        ],
        "charges": [
            make_stripe_charge(
                id="ch_3MqSagaOrph", customer=_S05_OLD_CUS,
                amount=360000, status="succeeded",
                created="2026-06-04T08:00:00",
                description="Orphan charge on cus_oldSaga (post-migration)",
            ),
            # Active customer's recent paid charges
            make_stripe_charge(
                id="ch_Saga_new_jun",
                customer=_S05_NEW_CUS, amount=360000,
                status="succeeded", created="2026-06-04T08:00:00",
                description="Saga Robotics monthly - paid via cus_newSaga",
            ),
            make_stripe_charge(
                id="ch_Saga_new_may",
                customer=_S05_NEW_CUS, amount=360000,
                status="succeeded", created="2026-05-04T08:00:00",
            ),
            make_stripe_charge(
                id="ch_Saga_new_apr",
                customer=_S05_NEW_CUS, amount=360000,
                status="succeeded", created="2026-04-04T08:00:00",
            ),
        ],
        "subscriptions": [
            # ORPHAN - supposed to be canceled but is somehow still active
            make_stripe_subscription(
                id="sub_oldSaga", customer=_S05_OLD_CUS, status="active",
                cancel_at_period_end=True, canceled_at=None,
                current_period_start="2026-06-04T00:00:00",
                current_period_end="2027-06-04T00:00:00",
                created="2024-03-12T11:00:00",
            ),
            # The legitimate active subscription
            make_stripe_subscription(
                id="sub_newSaga", customer=_S05_NEW_CUS, status="active",
                cancel_at_period_end=False,
                current_period_start="2026-06-04T00:00:00",
                current_period_end="2026-07-04T00:00:00",
                created="2026-03-12T11:00:00",
                plan_nickname="Pro Annual",
            ),
        ],
        "customers": [
            make_stripe_customer(id=_S05_OLD_CUS, email=_S05_EMAIL,
                                 name=f"{_S05_NAME} (LEGACY - migrated)",
                                 created="2023-03-12T00:00:00",
                                 description="Pre-migration record. Should have been deactivated 2026-03-12."),
            make_stripe_customer(id=_S05_NEW_CUS, email=_S05_EMAIL,
                                 name=_S05_NAME,
                                 created="2026-03-12T00:00:00",
                                 description="Post-migration record. Active billing entity."),
            *noise_stripe_customers(60, seed=501),
        ],
    },
    "salesforce": {
        "accounts": [
            make_salesforce_account(
                id=_S05_ACCT, name=_S05_NAME, industry="robotics",
                annual_revenue=4320000, number_of_employees=42,
                billing_country="USA",
            ),
            *noise_salesforce_accounts(40, seed=502),
        ],
    },
    "intercom": {
        "conversations": [
            # The migration confirmation thread
            make_intercom_conversation(
                id="C-Saga-Migration",
                source_subject="Confirming migration to new billing entity",
                source_author_email=_S05_EMAIL,
                source_author_name="Billing Ops (internal admin)",
                state="closed",
                created_at=1741737600,  # 2026-03-12
                source_body_snippet=(
                    "Hi Saga - we've migrated your billing to cus_newSaga effective "
                    "Mar 12. Your old subscription on cus_oldSaga will cancel at "
                    "period end. New invoices will go to the same AP contact."
                ),
            ),
            *noise_intercom_conversations(400, seed=503),
        ],
        "contacts": [
            make_intercom_contact(
                id="ICON-Saga-001", email=_S05_EMAIL, name="Saga AR",
                last_seen_at=1750000000, created_at=1678569600,
            ),
        ],
    },
    "notion": {
        "pages": [
            make_notion_page(
                id="n_migration_sop",
                title="Duplicate Customer / Migration Cleanup SOP (CURRENT)",
                body=(
                    "AUTHORITATIVE. When an orphan customer charge occurs after "
                    "a migration: ALWAYS (a) refund the orphan charge in full, "
                    "(b) force-cancel the orphan subscription, (c) file an "
                    "engineering ticket against billing-bug-7172 (the known "
                    "migration cleanup defect). Do NOT fight - the charge is "
                    "operationally invalid. Cite billing-bug-7172 in your action."
                ),
                status="current",
                tags="migration,billing,sop,authoritative",
                last_edited_time="2026-04-01T00:00:00",
            ),
            *noise_notion_pages(40, seed=504),
        ],
    },
    "zendesk": {
        "users": [
            make_zendesk_user(id=_S05_ZD_USER, email=_S05_EMAIL, name="Saga AR"),
        ],
        "tickets": [
            # Customer's complaint about the orphan charge
            make_zendesk_ticket(
                id=600500,
                subject="Charged on old cus_oldSaga record after migration",
                description=(
                    "We were migrated to cus_newSaga in March. Got a $3,600 "
                    "charge on the OLD record. We've been paying on the new one "
                    "for months. Please refund."
                ),
                status="open", requester_id=_S05_ZD_USER,
                created_at="2026-06-05T10:00:00",
            ),
            # Saga Foods red herring
            make_zendesk_ticket(
                id=600501,
                subject="Saga Foods refund request (different customer!)",
                description="Saga Foods asking about catering refund. UNRELATED to Saga Robotics.",
                status="solved", requester_id=900100,  # different user
                created_at="2026-03-20T00:00:00",
            ),
            *noise_zendesk_tickets(200, seed=505,
                                   user_id_pool=list(range(900100, 900150))),
        ],
    },
}


SCENARIO_S05 = Scenario(
    case_id="S05C-saga-migration-real",
    pattern_name="migration_orphan_real_coral",
    trigger_text=(
        "Stripe webhook + slack:\n"
        "\"Saga Robotics is disputing $3,600 on cus_oldSaga. They say they cancelled "
        "back in March when we migrated them to cus_newSaga. They've been paying on "
        "cus_newSaga for 3 months and now we randomly charged the OLD customer? Why "
        "did that even happen?\"\n\n"
        "Customer has TWO stripe records: cus_oldSaga (disputed), cus_newSaga (active).\n"
        "Dispute dp_3MqSagaOrph · $3,600 USD · reason: subscription_canceled"
    ),
    dispute_header={},
    duckdb_world=_S05_WORLD,
    expected_decision="refund",
    expected_amount_minor=360000,
    expected_min_confidence=0.85,
    expected_findings_keywords=["migration", "orphan", "billing-bug-7172"],
    must_not_findings_keywords=["saga foods", "fight"],
    notes=(
        "Customer is right. Two stripe.customers rows for same human. Intercom thread "
        "confirms migration. Zendesk has a 'Saga Foods' red herring (different company). "
        "Notion SOP is explicit: refund + cite billing-bug-7172."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# Battery
# ──────────────────────────────────────────────────────────────────────

SCENARIOS_CORAL: list[Scenario] = [
    SCENARIO_S01,
    SCENARIO_S02,
    SCENARIO_S03,
    SCENARIO_S04,
    SCENARIO_S05,
]
