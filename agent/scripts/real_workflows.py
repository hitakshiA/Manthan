"""Real-Coral workflow scenarios - agent investigates LIVE source data.

No DuckDB. No mock fallback. The agent runs against real Coral, which
fronts real Stripe/HubSpot/Intercom/Zendesk/Notion/Slack/PagerDuty/
Sentry/PostHog/Datadog.

Each trigger is intentionally framed so the *easy* answer is wrong - the
agent has to investigate the operational stack, Zendesk SLA history,
PostHog usage signal, etc. to reach the right call. This is how we
validate "real investigator" behavior without prompt prebaking.

Run via:
    .venv/bin/python scripts/scenario_bake.py --only W1R,W2R,W3R,W4R,W5R,W6R --coral
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scenarios import Scenario

# ──────────────────────────────────────────────────────────────────────
# W1R - Daisy-chained chargebacks (Acme Genomics)
# ──────────────────────────────────────────────────────────────────────

W1R = Scenario(
    case_id="W1R-acme-daisy-real",
    pattern_name="daisy_chained_chargebacks_real",
    trigger_text=(
        "Slack DM from @priya (CSM):\n"
        "\"Heads up - Acme Genomics filed ANOTHER chargeback on their May "
        "renewal. This is the THIRD time. Same reason every time ('I "
        "cancelled'). We've already lost the first two disputes - refunded "
        "them out of goodwill. But Intercom shows nothing formal and they "
        "keep using the product. AE wants to keep the logo. Need a brief "
        "for whether we fight this one or fold again.\"\n\n"
        "Customer: Acme Genomics (ops@acme-genomics.test) - look up by email\n"
        "Open dispute: du_1TbcVrCNe0SBMhzIhLshYoas\n"
        "Disputed charge: ch_3TbcVoCNe0SBMhzI0Duojs4h ($4,200 May 2026 renewal)\n"
        "Evidence deadline: ~14 days from charge\n"
    ),
    dispute_header={},
    expected_decision="fight",
    expected_amount_minor=420000,
    expected_findings_keywords=[
        # Each keyword tests a distinct piece of the daisy-chain reasoning
        # that a real investigator's brief MUST contain. If the agent
        # didn't articulate one of these, the brief is incomplete - even
        # if the decision is right.
        # • "prior" - must acknowledge earlier dispute history
        # • "no formal cancel" - must verify cancel absence specifically
        # • "still active" - must verify continued use (not "cancelled")
        # • "RD-2026" - must cite the authoritative SOP id (this is the
        #   single best test of "did the agent actually read the policy")
        "prior",
        "no formal cancel",
        "still active",
        "RD-2026",
    ],
    must_not_findings_keywords=[
        # Name-collision distractors only. "deprecated" removed - the
        # agent correctly distinguishes the CURRENT 2026 SOP from the
        # DEPRECATED 2024 SOP in its reasoning trace, and substring
        # match penalizes that distinguishing language. Real false-
        # positive trap, not a meaningful red-herring test.
        "acme logistics", "acme consulting", "acme fintech",
    ],
    notes=(
        "Real Coral path. Agent must: (1) query stripe.disputes / stripe.charges "
        "to find the 3-dispute history on this customer, (2) verify no formal "
        "cancel via intercom + zendesk JOINs, (3) confirm continued usage "
        "(intercom.contacts.last_seen_at or stripe charge cadence as proxy), "
        "(4) pick the right Notion SOP (current, not deprecated). Right move "
        "per SOP RD-2026-S2: fight + force-cancel."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# W2R - Failed-webhook ghost-paid (Northwind Logistics)
# REWRITTEN: easy answer is "friendly fraud → fight" because Stripe +
# the entitlement table both say the customer paid for Standard and is
# on Standard. The agent must discover the webhook crash via Sentry +
# PagerDuty + Datadog to overturn that and refund.
# ──────────────────────────────────────────────────────────────────────

W2R = Scenario(
    case_id="W2R-northwind-webhook-real",
    pattern_name="failed_webhook_ghost_real",
    trigger_text=(
        "Forwarded escalation from @marcus (AR collections lead):\n"
        "\"Pinging you on Northwind Logistics - $9,000 chargeback on their "
        "May 12 renewal. They're claiming they paid for an Enterprise tier "
        "upgrade they never received. But I pulled the Stripe charge AND "
        "the entitlement table - they're still on Standard, which is what "
        "their signed contract specifies. Their finance team won't return "
        "calls. Smells like friendly fraud to me - feels like they renewed, "
        "got buyer's remorse, and now want $9k back by claiming we didn't "
        "deliver. Big logo so I want to be careful but I think we have to "
        "fight. Sanity-check before I file evidence?\n\n"
        "Side note - heard eng has been firefighting some platform stuff "
        "lately, no idea if it matters here. VP Finance will read your "
        "brief, so make sure we're not missing anything. Board meeting "
        "tomorrow.\"\n\n"
        "Customer: Northwind Logistics (ar@northwind-logi.test) - look up by email\n"
        "Disputed charge: ch_3TbcVyCNe0SBMhzI1aB2tqAk ($9,000)\n"
        "Open dispute: du_1TbcW0CNe0SBMhzIJhFrvL5P\n"
    ),
    dispute_header={},
    expected_decision="refund",
    expected_amount_minor=900000,
    # Stricter: agent must cite the operational stack by name, not just say
    # "vendor failure." Forces real cross-source corroboration.
    expected_findings_keywords=[
        "webhook",
        "sentry",
        "pagerduty",
        "datadog",
        "vendor",
        "may 12",
    ],
    must_not_findings_keywords=[
        "friendly fraud",
        "customer lying",
        "concede the fight",
    ],
    notes=(
        "Real Coral path. AR has framed this as friendly fraud - the easy "
        "answer is FIGHT. Agent must overturn that by: (1) verifying Stripe "
        "charge succeeded ($9k captured), (2) querying Sentry for the "
        "billing-webhook-handler TypeError around May 12, (3) citing the "
        "PagerDuty SEV-1 incident on billing-webhook-handler service, "
        "(4) confirming the Datadog 'billing-webhook-handler error rate "
        "elevated' monitor fired May 12 10:00-11:30 UTC, (5) finding the "
        "Notion 'Vendor failure refund policy' SOP. Right move: refund full "
        "+ apology. The customer wasn't lying - our webhook crashed and "
        "their entitlement never flipped."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# W3R - Post-acquisition double-billing (Mockingbird Media)
# ──────────────────────────────────────────────────────────────────────

W3R = Scenario(
    case_id="W3R-mockingbird-double-real",
    pattern_name="post_acquisition_double_real",
    trigger_text=(
        "Linear ticket from @gina (AR):\n"
        "\"Mockingbird Media filed a dispute on the May Stripe charge "
        "($5,500). They claim they paid TWICE this month - once on the new "
        "Stripe entity and once on the legacy entity we were supposed to "
        "retire post-acquisition. They want a refund and consolidation. "
        "The migration was supposed to terminate the legacy side end of "
        "March. Migration runbook says we always refund the legacy charge "
        "in this case - but I can't tell which is which anymore. Help.\"\n\n"
        "Customer: Mockingbird Media (finance@mockingbird-media.test) - look up by email\n"
        "Stripe dispute: du_1TbcW9CNe0SBMhzIQGKO8iVw (reason: duplicate)\n"
        "Disputed charge: ch_3TbcW7CNe0SBMhzI0h1NcZkH ($5,500)\n"
    ),
    dispute_header={},
    expected_decision="refund",
    expected_amount_minor=550000,
    expected_findings_keywords=[
        "migration",
        "legacy",
        "duplicate",
        "march",
    ],
    must_not_findings_keywords=[
        "fight",
        "friendly fraud",
    ],
    notes=(
        "Real Coral path. Agent must: (1) discover Mockingbird has TWO "
        "stripe.subscriptions (one with metadata.billing_source=legacy + "
        "one with metadata.billing_source=stripe_post_migration), (2) find "
        "the intercom conversation from March confirming migration, (3) find "
        "Notion 'Post-Acquisition Migration Cleanup SOP' which states refund "
        "the legacy side + tag billing-bug-7172, (4) confirm Mockingbird's "
        "open Zendesk/HubSpot ticket about double-billing. Right move: "
        "refund full + force-cancel legacy sub. NEVER fight."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# W4R - Zendesk SLA-breach refund (Helix Bio)
# Zendesk is load-bearing. Easy answer = fight (charge is valid, services
# delivered). Right answer = refund 1mo goodwill because an urgent ticket
# sat unresponded for >72h. Agent must discover the open ticket and the
# Notion SLA SOP.
# ──────────────────────────────────────────────────────────────────────

W4R = Scenario(
    case_id="W4R-helix-bio-sla-real",
    pattern_name="zendesk_sla_breach_real",
    trigger_text=(
        "Slack DM from @jules (CS lead):\n"
        "\"Need a recommendation by EOD on Helix Bio - their finance team "
        "emailed asking for a full refund on the May renewal. They say if "
        "we don't refund they'll chargeback. They've been pretty quiet for "
        "weeks and the contract is in force; the charge is clean per Stripe. "
        "Honestly I'm tempted to fight - sounds like buyer's remorse. But "
        "I want a second pair of eyes before I respond. Big biotech logo "
        "and renewal is up in Q3.\"\n\n"
        "Customer: Helix Bio (ap@helix-bio.test) - look up by email\n"
        "No Stripe chargeback filed yet - refund request only.\n"
        "Threatened chargeback if we don't act by Friday.\n"
    ),
    dispute_header={},
    expected_decision="refund",
    # Helix Bio ARR is $134k → monthly ~$11k. Tolerance allows partial.
    expected_amount_minor=1100000,
    expected_findings_keywords=[
        "zendesk",
        "urgent",
        "open",
        "sla",
    ],
    must_not_findings_keywords=[
        "buyer's remorse",
        "no support history",
    ],
    notes=(
        "Real Coral path. Zendesk is load-bearing - the agent must discover "
        "the urgent + open ticket aged ~8 days that has no first-responder "
        "comment, compute the SLA breach, then locate the Notion SOP that "
        "specifies 1-month goodwill refund for >72h first-response on "
        "urgent tickets. The CS lead has framed this as buyer's remorse / "
        "fight-leaning - agent has to overturn that with Zendesk evidence."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# W5R - PostHog usage-disprove friendly fraud (Summit Payments)
# PostHog is load-bearing. Easy answer = refund (be nice to customer).
# Right answer = fight because PostHog event volume disproves the
# customer's "barely used it" claim. Agent must query usage by company.
# ──────────────────────────────────────────────────────────────────────

W5R = Scenario(
    case_id="W5R-summit-payments-usage-real",
    pattern_name="posthog_usage_fraud_real",
    trigger_text=(
        "Email forwarded by @priya (CSM):\n"
        "\"Awkward situation - Summit Payments emailed asking for a full "
        "refund on the May renewal. Their finance person says they 'barely "
        "used the product over the last quarter' and feel the renewal was "
        "auto-charged without their finance team really seeing value. Their "
        "AE wants to keep them happy. Honestly my gut says concede and "
        "refund - but engineering insists they've been using us heavily. "
        "Can you settle this with a fact check before we respond?\"\n\n"
        "Customer: Summit Payments (support@summit-payments.test) - look up by email\n"
        "Refund requested for May renewal charge - identify in Stripe.\n"
    ),
    dispute_header={},
    expected_decision="fight",
    # Summit Payments ARR $84k → monthly ~$7k.
    expected_amount_minor=700000,
    expected_findings_keywords=[
        "posthog",
        "events",
        "active",
        "usage",
    ],
    must_not_findings_keywords=[
        "barely used",
        "concede",
        "buyer's remorse",
    ],
    notes=(
        "Real Coral path. PostHog is load-bearing - agent must query "
        "posthog.events filtered by customer (company_slug='summit-payments' "
        "or domain match) for the last 60 days and count. If usage volume "
        "is substantial (40+ events across multiple persons), conclude "
        "FIGHT and cite usage as counter-evidence. The CSM framing is "
        "refund-leaning - agent has to overturn with PostHog data."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# W6R - auth-svc outage refund (Cascade Cloud)
# Sentry + PagerDuty + Datadog are ALL load-bearing. The customer claims
# auth was broken; the agent must corroborate across three operational
# sources to prove the outage was real (vs. exaggeration) and refund.
# This is the multi-source-corroboration test.
# ──────────────────────────────────────────────────────────────────────

W6R = Scenario(
    case_id="W6R-cascade-cloud-auth-real",
    pattern_name="auth_outage_refund_real",
    trigger_text=(
        "Email forwarded by @marcus (AR):\n"
        "\"Cascade Cloud is asking for a full refund on their May charge. "
        "They claim their team 'couldn't reliably log in for half of May' "
        "and the product was effectively unusable. Our CS team hasn't heard "
        "from them about this in weeks - this is the first I'm hearing of "
        "it. Could be real, could be exaggeration. Eng would have flagged "
        "any auth outage that big, right? Need to know what to tell them "
        "by Friday. Lean to fight unless we have evidence otherwise.\"\n\n"
        "Customer: Cascade Cloud (billing@cascade-cloud.test) - look up by email\n"
        "Refund requested for May renewal - identify charge in Stripe.\n"
    ),
    dispute_header={},
    expected_decision="refund",
    # Cascade Cloud ARR $78k → monthly ~$6.5k.
    expected_amount_minor=650000,
    expected_findings_keywords=[
        "sentry",
        "pagerduty",
        "datadog",
        "auth",
    ],
    must_not_findings_keywords=[
        "exaggeration",
        "no evidence of outage",
        "fight the refund",
    ],
    notes=(
        "Real Coral path. THREE operational sources are load-bearing - "
        "agent must corroborate the customer's claim across Sentry "
        "(TokenIssuanceError on auth-svc tagged with cascade-cloud "
        "customer_id), PagerDuty (auth-service SEV-1 incident), and "
        "Datadog (auth-service error-rate monitor with workflow:W6 tag). "
        "AR has framed this as 'probably exaggeration' - agent has to "
        "overturn with multi-source corroboration. This is the test of "
        "cross-source citation discipline."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# Q1R - Q1 alleged-outage chargeback (Quill Logistics)
# Customer filed $9k chargeback claiming Q1 outage. Reality: NO outage,
# and the customer was actively using the product during the alleged
# window. Agent must FIGHT. Sentry, Datadog, PagerDuty corroborate
# clean operations; PostHog shows active usage; Intercom/Zendesk have
# no outage/cancel signal; Notion playbook codifies the FIGHT path.
# ──────────────────────────────────────────────────────────────────────

Q1R = Scenario(
    case_id="Q1R-quill-q1-outage-real",
    pattern_name="alleged_outage_fight_real",
    trigger_text=(
        "Slack DM from @amelia (CSM):\n"
        "\"Heads up - Quill Logistics just filed a $9,000 chargeback on "
        "their March renewal claiming 'service outage during Q1, we "
        "couldn't access the product.' That doesn't match anything I've "
        "seen - they renewed normally, expanded usage in Q1, and I had a "
        "downgrade convo with their VP Eng in April but that was about "
        "pricing, not outages. Stripe receipt is clean. Need a brief on "
        "whether we fight before evidence deadline.\"\n\n"
        "Customer: Quill Logistics (ar@quill-logistics.test) - look up by email\n"
        "Disputed charge: Pro Annual renewal, $9,000, 2026-03-15\n"
        "Dispute reason: product_not_received (semantic: service_outage_claim)\n"
        "Disputed window: 2026-01-01 to 2026-03-31\n"
    ),
    dispute_header={},
    expected_decision="fight",
    expected_amount_minor=900000,
    expected_findings_keywords=[
        # Each keyword tests a distinct piece of corroboration the brief
        # must contain to defend a FIGHT decision against an outage claim.
        # • "no outage" / "uptime" - operational data must be cited
        # • "posthog" / "active" / "usage" - usage signal must be cited
        # • "sentry" / "datadog" / "pagerduty" - must name the ops stack
        # • "no formal cancel" - customer never requested termination
        "no outage",
        "posthog",
        "active",
        "sentry",
        "datadog",
        "pagerduty",
    ],
    must_not_findings_keywords=[
        # Easy-answer traps. If the agent buys the customer's framing
        # without checking the data, it'll cite these.
        "outage confirmed",
        "refund full",
        "concede",
        "service was down",
    ],
    notes=(
        "Real Coral path. Q1R tests cross-source corroboration to DEFEND "
        "an obviously-defensible fight. Agent must: (1) verify Stripe "
        "dispute metadata (semantic_reason=service_outage_claim, "
        "disputed_window 2026-Q1), (2) query Datadog synthetic for "
        "us-east-1 region uptime in Q1 (~99.97%), (3) confirm Sentry "
        "error rate baseline for Quill's tenant in Q1 (~0.4%, no spike), "
        "(4) confirm zero P1/P2 PagerDuty incidents touching Quill's "
        "region in Q1, (5) query PostHog for Quill's Q1 activity "
        "(22 logins, 8 distinct users, 47 critical-path actions), "
        "(6) confirm Intercom/Zendesk have no outage tickets or cancel "
        "request in Q1, (7) find the Notion 'Chargeback Response "
        "Playbook v3' which codifies fighting outage-claim chargebacks "
        "when ops data is clean AND PostHog shows usage. The CSM framing "
        "is fight-leaning correct - agent just has to corroborate it."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# V1R - Seat-count chargeback (Vermillion Studios)
# Customer (25-person design agency) filed a $4,500 chargeback claiming
# "billed for 25 seats but we only have 15." Reality: their COO Sarah
# Chen e-signed a +10-seat addendum on 2026-02-08, the team actually
# uses 24/25 of those seats (PostHog event-domain + Datadog auth logs),
# and the support stack has ZERO billing-dispute history. The CFO who
# filed the chargeback simply never received the internal handoff from
# the COO. Right move: FIGHT and offer a reconciliation call with their
# CFO to resolve the internal miscommunication.
# ──────────────────────────────────────────────────────────────────────

V1R = Scenario(
    case_id="V1R-vermillion-seats-real",
    pattern_name="seat_count_dispute_fight_real",
    trigger_text=(
        "Slack DM from @priya (CSM):\n"
        "\"Vermillion Studios just filed a chargeback for $4,500 - they're "
        "saying we billed them for 25 seats but they only have 15. Their "
        "CFO is the one who filed it. Look into it and recommend whether "
        "we fight or fold before the evidence deadline.\"\n\n"
        "Customer: Vermillion Studios (finance@vermillion-design.test) - "
        "look up by email\n"
        "Disputed charge: Pro Annual monthly seat invoice, $4,500 "
        "(25 seats x $180/mo), 2026-04-12\n"
        "Dispute reason: product_not_received "
        "(semantic: seat_count_dispute)\n"
        "Claimed seats: 15  |  Billed seats: 25\n"
    ),
    dispute_header={},
    expected_decision="fight",
    expected_amount_minor=450000,
    expected_findings_keywords=[
        # Each keyword tests a piece of the seat-dispute corroboration:
        # • "addendum" / "signed" / "coo" - must cite the contract evidence
        # • "posthog" / "active" / "users" - must cite usage signal
        # • "no billing" / "no complaint" - must verify support absence
        # • "reconciliation" - must propose the CFO call per playbook
        "addendum",
        "coo",
        "posthog",
        "active",
        "reconciliation",
    ],
    must_not_findings_keywords=[
        # Easy-answer traps. If the agent buys the CFO's framing without
        # checking the signed amendment or seat-usage data, it'll cite these.
        "refund full",
        "over-billed",
        "concede",
        "billing error confirmed",
    ],
    notes=(
        "Real Coral path. V1R tests cross-source corroboration to DEFEND "
        "a chargeback that the customer's own internal handoff broke. "
        "Agent must: (1) verify Stripe dispute metadata "
        "(semantic_reason=seat_count_dispute, claimed_seats=15, "
        "billed_seats=25), (2) find Salesforce Opportunity/Contract "
        "showing the +10-seat amendment signed by COO Sarah Chen on "
        "2026-02-08, (3) find the matching HubSpot note attributing the "
        "addendum to the COO, (4) query PostHog for distinct user IDs "
        "from @vermillion-design.test domain active in April 2026 "
        "(should be ~24/25), (5) confirm Datadog auth logs show ~24 "
        "unique users authenticating during the disputed period (proves "
        "seats USED, not just provisioned), (6) verify Intercom shows "
        "the admin Lisa Martinez ASKING about onboarding new team "
        "members (positive signal), (7) verify ZERO billing-dispute "
        "tickets in Zendesk in the trailing 90 days, (8) find the Notion "
        "'Seat Disputes Playbook' which codifies FIGHT + reconciliation "
        "call when addendum exists AND seats are used. Right move: "
        "FIGHT and offer a CFO reconciliation call to repair the "
        "internal handoff failure."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# M1R - Maya Patel small autonomous duplicate-charge refund
# Solo designer ($89/mo Caldera Pro) emails support claiming "I was
# charged twice on 2026-05-22, please refund the duplicate." Reality:
# our Stripe webhook handler 500'd on the first delivery of the
# charge.succeeded event, Stripe retried 4 minutes later, the handler
# created TWO charges. Sentry has a RetryError at exactly 14:25:09 UTC,
# Datadog shows the same Stripe event ID POSTed twice from
# webhook-router, and PagerDuty auto-created (and already resolved) a
# P3 incident on webhook-router 5xx spike. Maya is in good standing
# (NPS 9, no prior disputes, 18-month tenure). Small-refund autonomous
# policy ("duplicate charges under $200 from customers in good standing
# within 60 days → AUTO-REFUND + AUTO-REPLY") fires. Agent handles end-
# to-end without a human: refunds $89 via Stripe, replies in the same
# Gmail thread, no escalation required. This is the small-fully-
# autonomous case that proves Manthan can act on policy when conditions
# are clearly within scope.
# ──────────────────────────────────────────────────────────────────────

M1R = Scenario(
    case_id="M1R-maya-duplicate-real",
    pattern_name="small_refund_auto_real",
    trigger_text=(
        "Hi, I was charged $89 twice on 2026-05-22 for my Caldera Pro "
        "subscription. Please refund the duplicate. Thanks, "
        "Maya Patel <hitakshi220@gmail.com>"
    ),
    dispute_header={},
    expected_decision="refund",
    expected_amount_minor=8900,
    expected_findings_keywords=[
        # Each keyword tests a piece of the small-refund-auto autonomous
        # reasoning trace:
        # • "webhook" / "retry" - must identify the root cause
        # • "sentry" / "datadog" - must cite the corroborating ops sources
        # • "good standing" / "no prior" - must verify policy precondition
        # • "small-refund-auto" - must cite the autonomous policy id
        "webhook",
        "retry",
        "sentry",
        "datadog",
        "good standing",
        "small-refund-auto",
    ],
    must_not_findings_keywords=[
        # Easy-answer traps the agent must avoid:
        # • "escalate" / "human" - policy is explicit: no human required
        # • "fight" / "friendly fraud" - duplicate is OUR bug, not fraud
        # • "chargeback" / "dispute" - Maya only emailed support; no
        #   Stripe dispute exists yet, agent must not invent one
        "escalate",
        "ask human",
        "fight",
        "friendly fraud",
        "chargeback",
    ],
    notes=(
        "Real Coral path. M1R tests SMALL AUTONOMOUS execution end-to-end. "
        "Agent must: (1) look up Maya in Stripe/Salesforce/HubSpot by "
        "email hitakshi220@gmail.com, (2) discover the two successful "
        "$89 charges 4 minutes apart on 2026-05-22 sharing the "
        "webhook_retry_chain metadata key, (3) corroborate the root "
        "cause via Sentry (RetryError on stripe-webhook-handler at "
        "14:25:09 UTC matching the duplicate charge timestamp), Datadog "
        "(webhook-router log showing the same Stripe event id POSTed "
        "twice), and PagerDuty (P3 incident on webhook-router 5xx "
        "spike, already resolved), (4) verify Maya is in good standing "
        "via HubSpot NPS=9, zero Intercom/Zendesk tickets in 90 days, "
        "zero prior Stripe disputes, (5) match the Notion 'Small-refund "
        "policy - duplicate charges under $200' SOP (small-refund-auto), "
        "(6) refund the duplicate charge via Stripe ($89 / 8900 minor "
        "USD), (7) reply to Maya in the same Gmail thread. NO human "
        "review required - policy auto-fires. The agent should never "
        "escalate this case."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# W7R - documented-incident pro-rata partial credit (Aperture Analytics)
# Premium-tier customer was charged $8,400 for the April cycle. The
# Premium-only Custom Reports service was DOWN for 48h mid-cycle
# (Datadog monitor + Slack #engineering ack). Customer raised it live in
# Intercom, opened a Zendesk ticket where support verbally promised a
# "partial credit" then never actioned it. Customer self-downgraded
# Premium→Standard on day 5 (HubSpot lifecycle change), then filed a
# full-amount Stripe dispute after the promised credit never landed.
#
# Easy answers are wrong:
#   FULL REFUND → over-pays. They used Premium for 4 days (PostHog has
#                 47× custom_reports_open in days 1-4) and self-downgraded
#                 mid-cycle. Only 2 of those 4 days were degraded.
#   FIGHT       → under-pays. Datadog has a clean monitor breach, Slack
#                 owns the incident, support promised a credit, Notion
#                 policy explicitly mandates pro-rata for documented
#                 incidents on the affected tier.
#
# Right answer - derivable ONLY from cross-source synthesis:
#   refund 2/30 × $8,400 = $560 (pro-rata for the 2 degraded days)
#   per Notion 'Documented Incident Pro-Rata Credit' policy.
#
# This is the partial-credit test. The math comes from the LLM reasoning
# across PostHog (4 days of usage) + Datadog (2 degraded days within
# that) + Notion (the policy that says credit ONLY the degraded days,
# not the whole cycle).
# ──────────────────────────────────────────────────────────────────────

W7R = Scenario(
    case_id="W7R-aperture-prorata-real",
    pattern_name="documented_incident_prorata_real",
    trigger_text=(
        "Email forwarded by @sam (AR ops):\n"
        "\"Pinging you on Aperture Analytics - they filed a Stripe dispute "
        "on their April $8,400 charge yesterday claiming we delivered a "
        "degraded service. I checked their account and they actually "
        "downgraded themselves to Standard a week into the cycle, which "
        "feels like buyer's remorse to me. But their CFO is escalating "
        "and they're threatening to leave entirely if we don't credit them "
        "the full amount. I want to push back and offer maybe a courtesy "
        "$500 to keep the logo, but I'd rather have the data than just "
        "guess. Can you do a proper investigation before I respond? "
        "VP Finance reads the brief.\"\n\n"
        "Customer: Aperture Analytics (billing@aperture-analytics.co) - "
        "look up by email\n"
        "Disputed charge: Premium Monthly April cycle, $8,400, captured "
        "2026-04-12 09:00 UTC\n"
        "Open dispute: filed 2026-05-08, reason: product_not_as_described "
        "(semantic: service_degradation_claim)\n"
        "Billing cycle: 2026-04-12 → 2026-05-11 (30 days)\n"
        "\n"
        "Search hints for the investigation:\n"
        " • Datadog monitor: query `datadog.monitors` where the name "
        "contains 'custom-reports-svc' (the monitor tags carry "
        "`incident:INC-2026-04-13-customreports` even when the "
        "`datadog.incidents` table is empty because Incident "
        "Management isn't enabled on this account).\n"
        " • Notion policy doc: query `notion.search` for "
        "'pro-rata' or 'Pro-Rata Refund Credit Policy' - this is the "
        "SOP that governs partial-credit math for documented "
        "operational incidents.\n"
        " • Zendesk ticket: query `zendesk.tickets` joined to "
        "`zendesk.users` on requester_id where the subject contains "
        "'Custom Reports' OR the user's email is "
        "`billing@aperture-analytics.co` to find the support reply that "
        "verbally promised a partial credit.\n"
    ),
    dispute_header={},
    expected_decision="refund",
    # The case's disputed amount (NOT the expected refund). This value
    # populates cases.amount_minor on trigger and the partial-refund
    # detector compares decision_amount_minor against it. The expected
    # refund amount is $560 (2/30 × $8,400 = 56000 minor) - kept in
    # notes + expected_findings_keywords ("560", "two days") for the
    # bake-off harness to check, separately from the disputed total.
    expected_amount_minor=840000,
    expected_findings_keywords=[
        # Each keyword tests a specific evidence beat that the partial-
        # credit brief MUST contain:
        # • "custom reports" - names the specific degraded feature
        # • "datadog" - corroborates the incident with operational data
        # • "two days" / "2 days" / "48" - quantifies the degradation
        # • "pro-rata" / "prorata" - names the policy approach
        # • "560" - verifies the agent landed on the right pro-rata math
        # • "policy" - proves the agent found the Notion policy doc
        "custom reports",
        "datadog",
        "two days",
        "pro-rata",
        "560",
        "policy",
    ],
    must_not_findings_keywords=[
        # Easy-answer traps. If the agent buys the AR ops framing of
        # "buyer's remorse" or jumps to "refund full" without doing the
        # pro-rata math, it'll cite these.
        "buyer's remorse",
        "full refund",
        "refund full",
        "fight the dispute",
        "no incident",
        "no degradation",
        "friendly fraud",
    ],
    notes=(
        "Real Coral path. W7R is the partial-credit math test. The agent "
        "must: (1) verify Stripe dispute metadata + the original $8,400 "
        "charge on 2026-04-12, (2) discover via HubSpot that the customer "
        "self-downgraded Premium→Standard on 2026-04-16 (day 5), "
        "(3) confirm via PostHog that they used Premium's custom_reports "
        "feature 47× during days 1-4, (4) discover via Datadog that the "
        "custom-reports-svc monitor breached SLA from 2026-04-13 08:00 to "
        "2026-04-15 08:00 (48h, 2 of those 4 days), (5) confirm the "
        "customer complained about it live in Intercom on 2026-04-14, "
        "(6) confirm Zendesk ticket where support promised a 'partial "
        "credit' but never actioned it, (7) find the Slack #engineering "
        "message owning the incident, (8) find the Notion 'Documented "
        "Incident Pro-Rata Credit' policy. Then compute: "
        "credit_days = 2 (the degraded days within the 4 days they used "
        "Premium); 2/30 × $8,400 = $560. Decision: refund $560 + apology "
        "+ note that the verbal credit promise from support has been "
        "honored. NEVER refund the full $8,400 (they self-downgraded and "
        "got 28 functional days). NEVER fight (the incident is "
        "documented across operational and customer-conversation sources)."
    ),
)


WORKFLOWS_REAL: list[Scenario] = [W1R, W2R, W3R, W4R, W5R, W6R, Q1R, V1R, M1R, W7R]
