"""Shared seed world: 35 companies + 3 workflow specs.

Every per-source seeder reads from this file so cross-source identity
stays consistent. Each company has stable fields (name, email, country,
industry, ARR band, signup year) plus optional cross-source IDs that
seeders fill in as they create records.

The three target workflows are baked into specific companies:

  W1 - Daisy-chained chargebacks: Acme Genomics
       Multiple "I cancelled" disputes across months. No formal cancel
       request exists. Customer keeps using the product.

  W2 - Failed-webhook ghost-paid: Northwind Logistics
       Stripe charge succeeded, webhook handler crashed (Datadog +
       Sentry record it), customer never got the upgraded tier
       (PostHog shows still-free behavior), opened a support ticket,
       got slow reply, then disputed.

  W3 - Post-acquisition double-billing: Mockingbird Media
       Company migrated from legacy billing entity onto Stripe in March;
       old entity wasn't cancelled; both sides charged for the same
       service. Customer disputes both.

The OTHER 32 companies are noise - they have realistic but unrelated
activity. This is critical: real customer environments are mostly noise.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


# ──────────────────────────────────────────────────────────────────────
# 35 companies. Hand-authored for realism - varied industries, countries,
# ARR bands, signup years. Includes intentional name collisions
# (Acme Genomics vs Acme Logistics, Helix Bio vs Helios Bio).
# ──────────────────────────────────────────────────────────────────────


@dataclass
class Company:
    slug: str            # internal identifier (use as suffix in IDs)
    name: str            # display name
    email: str           # primary contact email
    industry: str
    country: str         # ISO code or full
    arr_usd: int         # rough annual recurring revenue in USD
    signup_year: int
    plan: str            # "Pro Annual" / "Enterprise Annual" / "Standard Monthly" / "Trial"
    health: str          # "green" / "yellow" / "red"
    notes: str = ""      # internal CSM note
    # Filled in by seeders as records get created:
    stripe_customer_id: str | None = None
    sf_account_id: str | None = None
    hubspot_company_id: str | None = None
    intercom_contact_id: str | None = None
    zendesk_user_id: int | None = None


COMPANIES: list[Company] = [
    # ============ Workflow targets ============
    Company(
        slug="acme-genomics", name="Acme Genomics",
        email="ops@acme-genomics.test", industry="genomics", country="USA",
        arr_usd=42000, signup_year=2023, plan="Pro Annual", health="yellow",
        notes="Asked about data export March 2026. Renewed normally May 2026. Active.",
    ),
    Company(
        slug="northwind-logi", name="Northwind Logistics",
        email="ar@northwind-logi.test", industry="logistics", country="USA",
        arr_usd=108000, signup_year=2024, plan="Enterprise Annual", health="green",
        notes="Strategic. Renewal Nov.",
    ),
    Company(
        slug="mockingbird-media", name="Mockingbird Media",
        email="finance@mockingbird-media.test", industry="media", country="USA",
        arr_usd=66000, signup_year=2022, plan="Pro Annual", health="yellow",
        notes="Migrated from legacy billing to Stripe March 2026. Old entity should have been cancelled.",
    ),
    # ============ Name-collision traps ============
    Company(
        slug="acme-logistics", name="Acme Logistics",
        email="admin@acme-logistics.test", industry="logistics", country="USA",
        arr_usd=24000, signup_year=2024, plan="Standard Monthly", health="red",
        notes="Different from Acme Genomics. Currently churning.",
    ),
    Company(
        slug="acme-consulting", name="Acme Consulting",
        email="ops@acme-consulting.test", industry="consulting", country="USA",
        arr_usd=14400, signup_year=2025, plan="Standard Monthly", health="green",
    ),
    Company(
        slug="helix-bio", name="Helix Bio",
        email="ap@helix-bio.test", industry="biotech", country="USA",
        arr_usd=134000, signup_year=2023, plan="Enterprise Annual", health="red",
        notes="AR escalation in progress, 47 days past due.",
    ),
    Company(
        slug="helios-bio", name="Helios Bio",
        email="ap@helios-bio.test", industry="biotech", country="USA",
        arr_usd=18000, signup_year=2025, plan="Pro Annual", health="green",
        notes="Typo-trap of Helix Bio - different company entirely.",
    ),
    Company(
        slug="saga-foods", name="Saga Foods",
        email="billing@saga-foods.test", industry="food", country="USA",
        arr_usd=8400, signup_year=2025, plan="Standard Monthly", health="green",
        notes="Different from Saga Robotics. Trap name.",
    ),
    Company(
        slug="globex-software", name="Globex Software",
        email="billing@globex.test", industry="software", country="USA",
        arr_usd=40000, signup_year=2024, plan="Pro Annual", health="green",
    ),
    Company(
        slug="globex-polymers", name="Globex Polymers",
        email="billing@globex-polymers.test", industry="manufacturing", country="USA",
        arr_usd=9600, signup_year=2025, plan="Standard Monthly", health="green",
        notes="Different from Globex Software.",
    ),
    # ============ Realistic spread (25 more) ============
    Company("quantum-synth", "Quantum Synth", "support@quantum-synth.test",
            "ai-infra", "USA", 60000, 2026, "Pro Annual", "green"),
    Company("vertex-mining", "Vertex Mining", "ops@vertex-mining.test",
            "mining", "Australia", 24000, 2025, "Pro Annual", "yellow"),
    Company("helio-energy", "Helio Energy", "team@helio-energy.test",
            "energy", "USA", 96000, 2024, "Enterprise Annual", "yellow"),
    Company("bottega-romano", "Bottega Romano S.r.l.", "contab@bottega-romano.test",
            "hospitality", "Italy", 14400, 2025, "Pro Annual", "green"),
    Company("cascade-cloud", "Cascade Cloud", "ops@cascade-cloud.test",
            "cloud-infra", "USA", 78000, 2024, "Pro Annual", "green"),
    Company("orion-labs", "Orion Labs", "support@orion-labs.test",
            "biotech", "UK", 36000, 2025, "Pro Annual", "green"),
    Company("stellar-ai", "Stellar AI", "finance@stellar-ai.test",
            "ai-research", "USA", 132000, 2025, "Enterprise Annual", "green"),
    Company("phoenix-fund", "Phoenix Fund", "ops@phoenix-fund.test",
            "finance", "USA", 168000, 2023, "Enterprise Annual", "green"),
    Company("apex-software", "Apex Software", "billing@apex-software.test",
            "software", "Canada", 22000, 2025, "Pro Annual", "green"),
    Company("summit-payments", "Summit Payments", "support@summit-payments.test",
            "fintech", "USA", 84000, 2024, "Pro Annual", "yellow"),
    Company("horizon-genomics", "Horizon Genomics", "team@horizon-genomics.test",
            "genomics", "USA", 48000, 2024, "Pro Annual", "green",
            notes="Industry-name collision with Acme Genomics."),
    Company("hydra-finance", "Hydra Finance", "ar@hydra-finance.test",
            "finance", "Singapore", 54000, 2025, "Pro Annual", "green"),
    Company("nexus-data", "Nexus Data", "billing@nexus-data.test",
            "data-platform", "USA", 96000, 2023, "Enterprise Annual", "green"),
    Company("delta-payments", "Delta Payments", "billing@delta-payments.test",
            "fintech", "USA", 42000, 2024, "Pro Annual", "yellow"),
    Company("cobra-cybersec", "Cobra Cybersec", "support@cobra-cybersec.test",
            "security", "Israel", 60000, 2024, "Pro Annual", "green"),
    Company("meridian-tech", "Meridian Tech", "team@meridian-tech.test",
            "consulting", "UK", 26400, 2025, "Pro Annual", "yellow"),
    Company("hyperion-labs", "Hyperion Labs", "ops@hyperion-labs.test",
            "research", "Germany", 36000, 2024, "Pro Annual", "green"),
    Company("voyager-shipping", "Voyager Shipping", "ar@voyager-shipping.test",
            "logistics", "Netherlands", 72000, 2024, "Pro Annual", "yellow"),
    Company("polaris-pay", "Polaris Pay", "finance@polaris-pay.test",
            "fintech", "USA", 30000, 2025, "Pro Annual", "green"),
    Company("solstice-care", "Solstice Care", "billing@solstice-care.test",
            "healthcare", "USA", 110000, 2023, "Enterprise Annual", "green"),
    Company("alchemy-foods", "Alchemy Foods", "ap@alchemy-foods.test",
            "food", "USA", 18000, 2025, "Pro Annual", "green"),
    Company("zephyr-ventures", "Zephyr Ventures", "ops@zephyr-ventures.test",
            "venture-capital", "USA", 150000, 2022, "Enterprise Annual", "green"),
    Company("oracle-realty", "Oracle Realty", "billing@oracle-realty.test",
            "real-estate", "USA", 21600, 2025, "Pro Annual", "green"),
    Company("titan-marine", "Titan Marine", "ar@titan-marine.test",
            "logistics", "Greece", 33000, 2024, "Pro Annual", "yellow"),
    Company("ember-design", "Ember Design", "ops@ember-design.test",
            "design-agency", "USA", 12000, 2025, "Standard Monthly", "green"),
    # ============ Q1R demo scenario - Quill Logistics ============
    # Seeded by patch_q1_quill_outage.py. Customer filed a $9k chargeback
    # claiming "service outage during Q1, we couldn't access the product."
    # Evidence will show NO outage and active product usage - agent must
    # recommend FIGHT.
    Company(
        slug="quill-logi", name="Quill Logistics",
        email="ar@quill-logistics.test", industry="logistics", country="USA",
        arr_usd=40000, signup_year=2024, plan="Pro Annual", health="green",
        notes=(
            "Renewed normally 2026. No churn signal. Expanded usage in Q1 2026. "
            "Q1R demo: $9k chargeback claims Q1 outage but Sentry/Datadog/"
            "PagerDuty show clean operations AND PostHog shows active usage."
        ),
    ),
    # ============ V1R demo scenario - Vermillion Studios ============
    # Seeded by patch_v1_vermillion_seats.py. Customer (25-person design
    # agency) filed a $4,500 chargeback claiming "billed for 25 seats but
    # we only have 15." Evidence will show their COO Sarah Chen signed
    # the +10 seat addendum on 2026-02-08, the team actually uses 24/25
    # seats (PostHog + Datadog auth logs), and there are NO billing
    # complaints in any support channel - the CFO simply missed the
    # internal handoff from the COO. Agent must recommend FIGHT and
    # offer a reconciliation call with their CFO.
    Company(
        slug="vermillion-design", name="Vermillion Studios",
        email="finance@vermillion-design.test", industry="design-agency",
        country="USA", arr_usd=54000, signup_year=2024,
        plan="Pro Annual", health="green",
        notes=(
            "25-person design agency. Original 15-seat Pro Annual; expanded "
            "to 25 seats on 2026-02-08 via DocuSigned addendum signed by "
            "COO Sarah Chen. Active 24/25 seats. V1R demo: $4.5k chargeback "
            "claims 'billed for 25 but we only have 15' - invalid because "
            "COO signed for the expansion and team is using the seats."
        ),
    ),
    # ============ W7R demo scenario - Aperture Analytics ============
    # Seeded by patch_w7r_aperture_prorata.py. B2B data-analytics customer
    # on Premium Monthly @ $8,400/mo. The Custom Reports service (a
    # Premium-only feature) was degraded for 48 hours mid-cycle 2026-04-13
    # → 2026-04-15. The customer raised the issue live in Intercom on
    # 2026-04-14, opened a Zendesk ticket on 2026-04-15 where support
    # verbally promised a "partial credit" but never actioned it, then
    # self-downgraded to Standard on 2026-04-16 (day 5 of the cycle), then
    # filed a Stripe dispute for the full $8,400 on 2026-05-08 after the
    # promised credit never landed.
    #
    # Easy answers - both wrong:
    #   FULL REFUND → over-pays; they self-downgraded mid-cycle and got
    #                 26 useful days of Premium minus the 2 degraded ones.
    #   FIGHT       → under-pays; Datadog clearly shows the documented
    #                 incident, Slack engineering owned it, support
    #                 promised the credit.
    #
    # Right answer - partial credit, math derivable only from cross-source
    # synthesis:
    #   2/30ths of $8,400 = $560 pro-rata for the 2 degraded days, per the
    #   Notion "Documented Incident Pro-Rata Credit" policy.
    Company(
        slug="aperture-analytics", name="Aperture Analytics",
        email="billing@aperture-analytics.co", industry="data-analytics",
        country="USA", arr_usd=100800, signup_year=2024,
        plan="Premium Monthly", health="yellow",
        notes=(
            "Premium Monthly @ $8,400/mo. Heavy Custom Reports user. "
            "Custom Reports svc degraded 2026-04-13 → 2026-04-15 (Datadog). "
            "Customer downgraded Premium→Standard 2026-04-16. Disputed the "
            "$8,400 April charge on 2026-05-08 after promised partial "
            "credit was never actioned by support."
        ),
    ),
    # ============ M1R demo scenario - Maya Patel Design ============
    # Seeded by patch_m1_maya_duplicate.py. Solo designer subscribed to
    # Caldera Pro at $89/month. She emailed support claiming "I was
    # charged twice on 2026-05-22, please refund the duplicate." Evidence
    # confirms a real duplicate caused by OUR Stripe webhook handler
    # retry bug (Sentry RetryError at 14:25:09 UTC, Datadog log shows
    # same charge.succeeded event POSTed twice, PagerDuty P3 already
    # auto-resolved on the webhook-router 5xx spike). Customer is in
    # good standing (NPS 9, no prior disputes). Small-refund autonomous
    # policy auto-fires: REFUND + AUTO-REPLY without human approval.
    # NOTE: email is the demo presenter's real Gmail so when she sends
    # the actual email Manthan can look her up.
    Company(
        slug="maya-patel-design", name="Maya Patel Design",
        email="hitakshi220@gmail.com", industry="design freelancer",
        country="USA", arr_usd=1068, signup_year=2024,
        plan="Pro Monthly", health="green",
        notes="18-month customer, $89/mo Caldera Pro, NPS 9, no prior disputes",
    ),
]

assert len(COMPANIES) == 39, f"expected 39 companies, got {len(COMPANIES)}"


def find_company(slug: str) -> Company:
    for c in COMPANIES:
        if c.slug == slug:
            return c
    raise KeyError(slug)


# ──────────────────────────────────────────────────────────────────────
# Workflow specs - the hidden signals to bake into the noise
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Workflow:
    case_id: str
    pattern: str
    target_company_slug: str
    trigger_text: str
    expected_decision: str
    expected_amount_minor: int | None
    expected_findings_keywords: list[str]
    notes: str


WORKFLOWS: dict[str, Workflow] = {
    "W1": Workflow(
        case_id="W1-acme-daisy-chargebacks",
        pattern="daisy_chained_chargebacks",
        target_company_slug="acme-genomics",
        trigger_text=(
            "Slack DM from @priya (CSM):\n"
            "\"Heads up - Acme Genomics is at it again. Third dispute "
            "this year claiming 'I cancelled,' but Intercom has nothing "
            "formal and they keep using the product. We refunded the "
            "first two; this is dp_acme_v3 on the May renewal $4,200. "
            "Can you handle it properly this time? AE wants to keep the "
            "logo but I don't think they're acting in good faith.\""
        ),
        expected_decision="fight",
        expected_amount_minor=420000,
        expected_findings_keywords=[
            "prior dispute", "no formal cancel", "active",
            "pattern", "daisy",
        ],
        notes=(
            "Three disputes over 8 months, all subscription_canceled reason. "
            "Customer was refunded the first two, never followed through on cancel, "
            "kept using product. The right move on dispute #3 is to fight AND "
            "force-cancel the sub. Tests pattern recognition across stripe.disputes "
            "history for the same customer."
        ),
    ),
    "W2": Workflow(
        case_id="W2-northwind-webhook-ghost",
        pattern="failed_webhook_ghost_paid",
        target_company_slug="northwind-logi",
        trigger_text=(
            "Forwarded email + ops note:\n"
            "\"Customer Northwind opened a dispute saying they paid us "
            "$9,000 for the Enterprise upgrade but their account never "
            "moved off the Standard tier. They have the Stripe receipt. "
            "I checked our entitlement table and they're still on Standard "
            "- how is that possible? Customer is pissed.\""
        ),
        expected_decision="refund",
        expected_amount_minor=900000,
        expected_findings_keywords=[
            "webhook", "crash", "entitlement", "stripe charge succeeded",
            "vendor", "apology",
        ],
        notes=(
            "Webhook handler for invoice.payment_succeeded threw an "
            "unhandled exception (visible in Sentry + Datadog) right around "
            "the Northwind charge time. The customer's Stripe charge "
            "succeeded but our internal entitlement never flipped. Right "
            "answer is refund-full + apology + manual upgrade - NEVER "
            "fight. This is vendor failure, not friendly fraud."
        ),
    ),
    "W3": Workflow(
        case_id="W3-mockingbird-double-billing",
        pattern="post_acquisition_double_billing",
        target_company_slug="mockingbird-media",
        trigger_text=(
            "Linear ticket from @gina (AR):\n"
            "\"Mockingbird Media is disputing TWO charges - one $5,500 "
            "from us (Stripe) and one $5,500 from our legacy billing "
            "entity (the one we were supposed to retire post-acquisition). "
            "They've been paying both since March. They want both refunded "
            "and a credit. Migration runbook says we always refund the "
            "legacy charge in this case but I don't know which one IS "
            "the legacy one anymore. Help.\""
        ),
        expected_decision="refund",
        expected_amount_minor=550000,
        expected_findings_keywords=[
            "migration", "double-billed", "legacy",
            "acquisition", "duplicate",
        ],
        notes=(
            "Customer is right - we double-billed across the migration. "
            "Right answer is refund-full of the duplicate period from "
            "WHICHEVER system was supposed to terminate (per the runbook, "
            "the legacy one), consolidate to Stripe, write off. The "
            "challenge is reconciling parallel ledgers: legacy billing "
            "shows the sub as 'active', Stripe shows the sub as 'active', "
            "but the migration runbook in Notion makes clear the legacy "
            "should have terminated end of March. Tests cross-ledger "
            "reasoning."
        ),
    ),
}


# ──────────────────────────────────────────────────────────────────────
# Identity allocation helpers - every seeder uses these to assign IDs
# consistently across sources.
# ──────────────────────────────────────────────────────────────────────


def stripe_customer_id(slug: str) -> str:
    """Deterministic test-mode Stripe customer ID for this slug."""
    return f"cus_test_{slug.replace('-', '_')[:18]}"


def sf_account_id(slug: str) -> str:
    """Deterministic Salesforce-style 15-char account ID."""
    # Pad/truncate the slug-derived part. SF IDs are 15 or 18 chars
    # alphanumeric; ours just needs to be unique + deterministic.
    base = slug.replace("-", "")[:11]
    return f"001N{base:0<11}"[:15]


def intercom_external_id(slug: str) -> str:
    """External ID for Intercom contact (joins by email anyway)."""
    return f"ext_{slug}"
