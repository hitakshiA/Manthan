"""Seed Notion (`Manthan Ops` parent page) with ~95 child pages for the
Manthan billing-dispute agent.

Pages span MANY categories (policies & SOPs, customer accounts,
all-hands, engineering docs, HR/company/brand, customer-facing drafts).
The three workflow targets get specific authoritative policy docs +
account-history pages baked in:

  W1 - "Refunds & Disputes - 2026 SOP (CURRENT)" : daisy-chained
       chargebacks. Repeat-disputer pattern → fight + force-cancel.
       Account page for Acme Genomics documents the 2 prior
       won-by-customer disputes.

  W2 - "Vendor failure refund policy (CURRENT)" : when webhook /
       internal system caused the issue, refund full + apology.
       Account page for Northwind Logistics documents the
       Enterprise upgrade that never activated.

  W3 - "Post-Acquisition Migration Cleanup SOP (CURRENT)" : when
       customers are billed on BOTH legacy entity and Stripe, refund
       legacy side, force-cancel legacy, consolidate to Stripe.
       Account page for Mockingbird Media documents the March cutover.

Notion rate-limits at ~3 req/s. We sleep ~340ms between writes.

Idempotency: before creating, we search by exact title and skip if a
child page with that title already exists under the parent. Re-running
is safe.

Run:
    .venv/bin/python scripts/seed_notion.py
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Make seed_world importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from seed_world import COMPANIES, WORKFLOWS  # noqa: E402,F401


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

TOKEN = os.getenv("NOTION_API_KEY")
if not TOKEN:
    sys.exit("ERROR: NOTION_API_KEY missing from .env")

BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# Notion rate-limits at ~3 req/s. Sleep ~340ms between writes to stay
# safely under the limit; on 429 we honor Retry-After.
REQ_SLEEP = 0.36
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


# ──────────────────────────────────────────────────────────────────────
# Page model
# ──────────────────────────────────────────────────────────────────────


@dataclass
class NotionPage:
    title: str
    category: str
    # Body is a list of paragraph strings. Empty lines = paragraph break.
    paragraphs: list[str] = field(default_factory=list)
    # Optional heading blocks before paragraphs (level 2/3).
    headings: list[tuple[int, str]] = field(default_factory=list)
    # Identifier used in signal verification (filled by the W1/W2/W3 docs).
    signal_id: str | None = None


# ──────────────────────────────────────────────────────────────────────
# Page authoring helpers
# ──────────────────────────────────────────────────────────────────────


def _paragraphs_to_blocks(paragraphs: list[str]) -> list[dict]:
    """Convert paragraph strings into Notion paragraph blocks.

    Each string > 1900 chars is chunked into multiple rich_text spans
    (Notion has a 2000-char limit per rich_text element). We chunk on
    sentence boundaries when possible.
    """
    blocks: list[dict] = []
    for para in paragraphs:
        if not para.strip():
            # Spacer paragraph.
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": []},
            })
            continue
        # Split into <=1900-char chunks on sentence boundaries.
        rich_text: list[dict] = []
        remaining = para
        while remaining:
            if len(remaining) <= 1900:
                rich_text.append({
                    "type": "text",
                    "text": {"content": remaining},
                })
                break
            # Find the last sentence boundary before 1900.
            cut = remaining.rfind(". ", 0, 1900)
            if cut == -1:
                cut = 1900
            else:
                cut += 1  # keep the period
            rich_text.append({
                "type": "text",
                "text": {"content": remaining[:cut]},
            })
            remaining = remaining[cut:].lstrip()
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": rich_text},
        })
    return blocks


def _heading_block(level: int, text: str) -> dict:
    """Build a heading_2 or heading_3 block."""
    htype = f"heading_{level}"
    return {
        "object": "block", "type": htype,
        htype: {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _page_payload(parent_id: str, page: NotionPage) -> dict:
    """Build the POST /v1/pages payload for a NotionPage."""
    children = []
    # Category badge at the top.
    children.append({
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Category: {page.category}"},
            }],
            "icon": {"type": "emoji", "emoji": "📄"},
        },
    })
    for level, text in page.headings:
        children.append(_heading_block(level, text))
    children.extend(_paragraphs_to_blocks(page.paragraphs))
    return {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": page.title}}],
            },
        },
        "children": children,
    }


# ──────────────────────────────────────────────────────────────────────
# HTTP wrapper with auto-throttling on 429 / 5xx
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
    """HTTP request with retry/backoff on 429 + 5xx."""
    url = path if path.startswith("http") else f"{BASE}{path}"
    for attempt in range(retries):
        r = client.request(method, url, json=json, params=params)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", "1.5"))
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        return r
    return r


# ──────────────────────────────────────────────────────────────────────
# Parent page lookup
# ──────────────────────────────────────────────────────────────────────


def find_parent_page(client: httpx.Client) -> tuple[str, str]:
    """Find the ManthanOps parent page. Returns (page_id, title).

    Bails if the integration isn't connected to it.
    """
    r = _request(client, "POST", "/search", json={
        "query": "ManthanOps",
        "filter": {"property": "object", "value": "page"},
    })
    if r.status_code != 200:
        sys.exit(f"ERROR: search failed {r.status_code}: {r.text[:300]}")
    results = r.json().get("results", [])
    # Allow either "ManthanOps" or "Manthan Ops" - user may have either.
    candidates = []
    for x in results:
        title_parts = x.get("properties", {}).get("title", {}).get("title", [])
        title_text = "".join(t.get("plain_text", "") for t in title_parts).strip()
        if title_text.lower().replace(" ", "") == "manthanops":
            candidates.append((x["id"], title_text))
    if not candidates:
        sys.exit(
            "ERROR: No page named 'ManthanOps' (or 'Manthan Ops') is shared "
            "with this integration. Open Notion → ManthanOps page → ··· → "
            "Connections → add the integration, then re-run."
        )
    return candidates[0]


# ──────────────────────────────────────────────────────────────────────
# Existing-child lookup for idempotency
# ──────────────────────────────────────────────────────────────────────


def list_existing_children(
    client: httpx.Client, parent_id: str
) -> dict[str, str]:
    """Return {title: page_id} for existing child_page blocks under parent."""
    existing: dict[str, str] = {}
    cursor: str | None = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        r = _request(
            client, "GET", f"/blocks/{parent_id}/children", params=params,
        )
        if r.status_code != 200:
            print(
                f"  warning: list children failed {r.status_code}: "
                f"{r.text[:200]}"
            )
            return existing
        data = r.json()
        for block in data.get("results", []):
            if block.get("type") == "child_page":
                title = block.get("child_page", {}).get("title", "")
                existing[title] = block["id"]
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(REQ_SLEEP)
    return existing


# ──────────────────────────────────────────────────────────────────────
# Page catalog - author the ~95 pages here
# ──────────────────────────────────────────────────────────────────────


def _pages_policies_sops() -> list[NotionPage]:
    """Policies & SOPs (~18 pages). Includes the 3 authoritative workflow
    SOPs as CURRENT versions + various unrelated SOPs as noise."""
    pages: list[NotionPage] = []

    # ── W1: THE authoritative refunds & disputes SOP (CURRENT, latest) ──
    pages.append(NotionPage(
        title="Refunds & Disputes - 2026 SOP (CURRENT)",
        category="Policy & SOP",
        signal_id="W1",
        headings=[(2, "Refunds & Disputes - 2026 SOP")],
        paragraphs=[
            "Owner: RevOps (priya@miny-labs.com). Doc version 2026.05. "
            "Status: CURRENT - authoritative. Last reviewed 2026-05-18. "
            "Supersedes: 'Refunds policy - DEPRECATED 2024 version'. "
            "Internal - do not share externally; see 'Refunds customer-"
            "facing FAQ' for the public-safe version.",

            "Scope: this SOP covers chargebacks, voluntary refunds, "
            "billing-bug refunds, and disputes raised through Stripe, "
            "PayPal, or our legacy billing entity. It does NOT cover "
            "SLA credits - see 'SLA credit calculation runbook'.",

            "",
            "Section 1 - Standard subscription_canceled chargebacks.",
            "When a customer disputes a charge with reason "
            "'subscription_canceled', the default position is to FIGHT "
            "if and only if (a) there is no formal cancel request on "
            "file across any channel (Intercom, Zendesk, email, in-app) "
            "in the 60 days prior to the dispute, AND (b) Stripe shows "
            "the subscription still active at the time of the disputed "
            "charge, AND (c) PostHog shows active product usage in the "
            "billing period covered by the charge. If all three hold, "
            "submit evidence and fight. Cite this section in the "
            "dispute submission notes.",

            "An informal message like 'we're evaluating other vendors' "
            "or 'considering downgrade' is NOT a formal cancel. A "
            "formal cancel is an explicit, written request to terminate "
            "the subscription, with a date - anything ambiguous goes to "
            "RevOps for review, not auto-canceled.",

            "",
            "Section 2 - REPEAT-DISPUTER pattern (daisy-chained "
            "chargebacks).",
            "If the SAME customer (matched by Stripe customer ID OR by "
            "primary contact email) has one or more prior disputes that "
            "were won-by-customer within the trailing 14 months, AND "
            "still has no formal cancel on file across any channel, "
            "this is a daisy-chained-disputes pattern. The economics "
            "are: each individual dispute looks small, but the customer "
            "is exploiting the refund-on-dispute default to use the "
            "product for free.",

            "Action on dispute #2 of the pattern: refund as usual but "
            "open a flag in HubSpot, document the pattern in this "
            "customer's account page in Notion, and warn the AE. "
            "Action on dispute #3 and beyond: FIGHT this dispute AND "
            "force-cancel the subscription with a prorated refund of "
            "any unused period. Use Stripe `cancellation_details."
            "comment = 'daisy_chain_chargeback'` and cite policy "
            "id RD-2026-S2 in the dispute submission.",

            "This is the right answer even when sales pushes back to "
            "preserve the logo - bad-faith customers cost more than "
            "they're worth and they prime other AEs to learn the same "
            "bad pattern.",

            "",
            "Section 3 - Vendor-failure refunds.",
            "If our internal systems (webhook handlers, entitlement "
            "service, billing platform, identity service, etc.) caused "
            "the customer to be billed without receiving the value "
            "they paid for, ALWAYS refund the full amount, apologize, "
            "and manually fix the entitlement. NEVER fight. See "
            "'Vendor failure refund policy' for the full procedure and "
            "evidence-collection checklist.",

            "",
            "Section 4 - Post-acquisition double-billing.",
            "Customers migrated from a legacy billing entity onto "
            "Stripe in the 2025-2026 cleanup project are at risk of "
            "being billed on both sides. See 'Post-Acquisition "
            "Migration Cleanup SOP' for the full procedure.",

            "",
            "Section 5 - Escalation matrix.",
            "Disputes >$10,000: route to VP Finance. "
            "Disputes from accounts on the strategic list: notify the "
            "AE owner in Slack before submitting evidence. "
            "Disputes with regulator involvement (CFPB, FCA, ASIC): "
            "escalate to Legal immediately, do not respond directly.",

            "Reference: internal URL "
            "https://miny-labs.notion.site/sop-refunds-2026 . "
            "Approved by: ops-leads. Next review: 2026-08-01.",
        ],
    ))

    # ── DEPRECATED 2024 version ──
    pages.append(NotionPage(
        title="Refunds policy - DEPRECATED 2024 version",
        category="Policy & SOP",
        paragraphs=[
            "Status: ARCHIVED 2026-01-12. Do not follow this doc. "
            "Superseded by 'Refunds & Disputes - 2026 SOP (CURRENT)'.",
            "",
            "Original 2024 policy: refund any dispute under $500 "
            "without investigation. Fight anything above $500 if there "
            "is no formal cancel. (This was the previous default and "
            "led to the daisy-chain abuse pattern we corrected in the "
            "2026 SOP.)",
            "Author (2024): former-RevOps. Archived by priya@miny-labs.com.",
        ],
    ))

    # ── Public-facing FAQ ──
    pages.append(NotionPage(
        title="Refunds customer-facing FAQ",
        category="Customer-facing draft",
        paragraphs=[
            "Public, customer-safe version. Sanitised - do NOT cite "
            "internal policy IDs here.",
            "",
            "Q: How do I request a refund?",
            "A: Email billing@miny-labs.com within 14 days of the "
            "charge with your invoice number and the reason. We respond "
            "within two business days.",
            "",
            "Q: Will you refund a cancelled subscription mid-period?",
            "A: We prorate refunds for cancelled annual plans on a "
            "case-by-case basis. Monthly plans are non-refundable once "
            "the period has started.",
            "",
            "Q: I was charged twice - what do I do?",
            "A: Send us both charge IDs and we'll investigate the "
            "duplicate and refund the extra charge within five business "
            "days.",
        ],
    ))

    # ── Engineering on-call runbook ──
    pages.append(NotionPage(
        title="Engineering on-call runbook",
        category="Policy & SOP",
        paragraphs=[
            "Owner: Platform Engineering. Last updated 2026-04-22.",
            "On-call rotation: weekly, PagerDuty schedule "
            "'platform-primary'. Backup: 'platform-secondary'.",
            "SEV-1: customer-facing outage, regulated-data exposure, "
            "or revenue-impacting bug. Page primary immediately, file "
            "incident in Statuspage within 15 minutes, write a "
            "post-mortem within 5 business days.",
            "SEV-2: degraded experience, internal-only impact. "
            "Open a Linear ticket and acknowledge in #platform-alerts "
            "within 30 minutes.",
            "Common runbook entries: webhook handler restart, "
            "entitlement re-sync, Stripe webhook replay (see "
            "'Webhook reliability project - post-mortems').",
        ],
    ))

    # ── Dunning & Suspension SOP ──
    pages.append(NotionPage(
        title="Dunning & Suspension SOP",
        category="Policy & SOP",
        paragraphs=[
            "Owner: RevOps. Status: CURRENT. Last updated 2026-03-14.",
            "Dunning emails: send on days 1, 4, 8, 14 after failed "
            "charge. Suspend feature access on day 21. Hard-close on "
            "day 60. Exceptions for strategic accounts require AE + "
            "RevOps sign-off in HubSpot deal notes.",
            "Suspend = read-only access. Hard-close = entitlement "
            "revoked, data retained for 90 days per retention policy.",
            "Edge cases: do not suspend an account that has an open "
            "billing dispute. Do not suspend an account during an "
            "active SEV-1 platform incident.",
        ],
    ))

    # ── W2: Vendor failure refund policy (CURRENT) ──
    pages.append(NotionPage(
        title="Vendor failure refund policy",
        category="Policy & SOP",
        signal_id="W2",
        headings=[(2, "Vendor-Failure Refund Policy")],
        paragraphs=[
            "Owner: Engineering + RevOps jointly. Status: CURRENT - "
            "authoritative. Doc version 2026.04. Last reviewed "
            "2026-05-09. Referenced from 'Refunds & Disputes - 2026 "
            "SOP (CURRENT)' Section 3.",

            "Scope: any case where the customer was charged but did "
            "not receive the value they paid for BECAUSE OF a failure "
            "in our own systems. Examples: webhook handler crashed, "
            "entitlement service down, identity sync broken, billing "
            "platform issued a duplicate charge, feature flag rollout "
            "regressed a paid feature.",

            "",
            "Rule: in every vendor-failure case, the default action is "
            "REFUND FULL + APOLOGY + manual entitlement repair. We do "
            "NOT fight these disputes, even when the customer's "
            "framing of the issue is technically wrong. The customer "
            "was billed by us, did not get the product, and it was "
            "our fault - we owe them their money back regardless of "
            "what they wrote in the dispute reason.",

            "",
            "Evidence checklist when classifying a dispute as "
            "vendor-failure: (1) Stripe charge succeeded around the "
            "time of the alleged issue; (2) Sentry shows an unhandled "
            "exception in `billing_engineering` or "
            "`entitlement_service` within +/- 15 minutes of the "
            "charge; (3) Datadog shows a corresponding alert for the "
            "same window; (4) PostHog shows the customer's account did "
            "NOT receive the entitlement (e.g. still on the free "
            "tier, or feature flags still off). If three of four "
            "hold, classify as vendor-failure.",

            "Specifically look for: invoice.payment_succeeded webhook "
            "handler crashes (the most common cause), entitlement "
            "service 5xx spikes, and Stripe `invoice.paid` events "
            "where our internal `subscription_tier` field did not "
            "change.",

            "",
            "Action procedure:",
            "1. Refund the full disputed amount via Stripe Dashboard "
            "with `reason = duplicate` (this avoids a fight outcome "
            "and the resulting dispute fee).",
            "2. Issue a manual entitlement upgrade in the admin tool "
            "to match what the customer paid for.",
            "3. Send the customer an apology email from "
            "billing@miny-labs.com - template VFR-2026 in the "
            "templates folder. CC the AE owner.",
            "4. Open a Linear ticket in the `billing_engineering` "
            "project linking the Sentry issue, the Datadog alert, "
            "and the Stripe charge ID, tagged with label "
            "`vendor-failure-refund`.",
            "5. Note the refund in this customer's Notion account "
            "page so the AE can reference it on the next QBR.",

            "",
            "Forbidden: never fight a vendor-failure dispute. Never "
            "reply to the customer with anything other than 'we are "
            "investigating; refund issued' until the entitlement is "
            "fixed. Never close the Linear ticket until the "
            "post-mortem is written.",

            "Reference: policy id VFR-2026. "
            "Internal URL https://miny-labs.notion.site/sop-vendor-"
            "failure-refunds-2026 . Approved by ops-leads + "
            "platform-leads. Next review: 2026-09-01.",
        ],
    ))

    # ── W3: Post-Acquisition Migration Cleanup SOP (CURRENT) ──
    pages.append(NotionPage(
        title="Post-Acquisition Migration Cleanup SOP",
        category="Policy & SOP",
        signal_id="W3",
        headings=[(2, "Post-Acquisition Migration Cleanup SOP")],
        paragraphs=[
            "Owner: Billing Engineering + RevOps. Status: CURRENT - "
            "authoritative. Doc version 2026.03. Last reviewed "
            "2026-05-20. Referenced from 'Refunds & Disputes - 2026 "
            "SOP (CURRENT)' Section 4 and the 'Billing platform "
            "migration - runbook & timeline' project doc.",

            "Background: in Q4 2025 we acquired a smaller competitor "
            "and inherited their Chargebee-based legacy billing "
            "entity. Migration plan: move all legacy subscriptions "
            "onto our Stripe entity by end-of-March 2026, terminating "
            "the legacy sub at period-end. Several customers were "
            "left billed on both sides because the legacy "
            "subscription was not actually terminated at cutover. "
            "This SOP covers cleanup.",

            "",
            "Detection: a customer is double-billed if both (a) the "
            "Stripe entity has an active subscription with at least "
            "one paid invoice dated after their migration cutover "
            "date, AND (b) the legacy Chargebee entity also has an "
            "active subscription with at least one paid invoice "
            "dated after the same cutover date, for the same product "
            "tier. The migration log in 'Billing platform migration "
            "- runbook & timeline' is authoritative for cutover "
            "dates.",

            "",
            "Action: when double-billing is detected (whether "
            "reported by the customer or caught by the monthly "
            "reconciliation job):",
            "1. Always refund the LEGACY-side charges in full for "
            "the duplicate period - never the Stripe charges. "
            "Stripe is our source-of-truth post-migration; the "
            "legacy entity should not be charging anyone past "
            "their cutover date.",
            "2. Force-cancel the legacy Chargebee subscription "
            "effective at the cutover date (back-dated). Note the "
            "cancellation reason as `post_acquisition_cleanup`.",
            "3. Consolidate all future billing onto the Stripe "
            "entity - verify the Stripe sub is on the correct plan "
            "for what the customer was paying on the legacy side.",
            "4. Issue a credit memo for the duplicate-period amount "
            "as a customer-trust gesture. Apply to the next Stripe "
            "invoice.",
            "5. Tag the Linear ticket with `billing-bug-7172` (the "
            "umbrella issue tracking this migration cleanup) and "
            "link both the legacy invoice and the Stripe invoice "
            "for reconciliation.",

            "",
            "Communication: email the customer's finance contact "
            "from billing@miny-labs.com with the refund confirmation "
            "and credit memo. Template PAM-2026 in the templates "
            "folder. Apologise for the duplicate billing and confirm "
            "the legacy sub is now terminated.",

            "",
            "Reconciliation: the parallel-ledger reconciliation "
            "job runs nightly and dumps a Linear ticket per detected "
            "double-billing into `billing_engineering`. RevOps "
            "reviews these weekly; any aging >14 days gets "
            "escalated to the VP Finance.",

            "Reference: policy id PAM-2026. Umbrella issue: "
            "billing-bug-7172. Internal URL "
            "https://miny-labs.notion.site/sop-post-acquisition-"
            "migration-cleanup-2026 . Approved by ops-leads + "
            "platform-leads + VP Finance. Next review: 2026-07-15.",
        ],
    ))

    # ── AE off-contract promises ──
    pages.append(NotionPage(
        title="AE off-contract promises - RevOps SOP",
        category="Policy & SOP",
        paragraphs=[
            "Owner: RevOps. Status: CURRENT. Last updated 2026-02-10.",
            "Account Executives may not promise discounts, refunds, "
            "or feature roadmap items that are not reflected in a "
            "signed order form. Any off-contract promise discovered "
            "after the fact (whether by the customer raising it in "
            "support or by us catching it in a QBR) is the AE's "
            "responsibility to escalate to RevOps for write-off or "
            "ratification before the next renewal.",
            "Do NOT honour off-contract promises silently - that "
            "creates inconsistent customer experience and rewards "
            "the AE's mistake.",
        ],
    ))

    # ── SLA credit calculation ──
    pages.append(NotionPage(
        title="SLA credit calculation runbook",
        category="Policy & SOP",
        paragraphs=[
            "Owner: Customer Success. Status: CURRENT. "
            "Last updated 2026-01-30.",
            "Standard SLA: 99.9% monthly uptime measured on the "
            "control-plane API. Credit schedule: <99.9% → 5% of "
            "monthly fee; <99.0% → 15%; <97.0% → 30%; <95.0% → 50%.",
            "Credits are applied to the next invoice as a discount, "
            "never refunded in cash. Customers on Standard Monthly "
            "plans get pro-rated credits.",
            "Eligibility: customer must request the credit within 30 "
            "days of the affected billing period. Outages caused by "
            "scheduled maintenance windows (posted ≥48h in advance) "
            "do not count toward SLA.",
        ],
    ))

    # ── Tax exemption (EU/VAT) policy ──
    pages.append(NotionPage(
        title="Tax exemption (EU/VAT) policy",
        category="Policy & SOP",
        paragraphs=[
            "Owner: Finance. Status: CURRENT. Last updated 2026-02-22.",
            "EU customers with a valid VIES-verified VAT ID may be "
            "billed reverse-charge (no VAT collected by us). "
            "Bottega Romano S.r.l. and other EU-based customers must "
            "submit their VAT ID via the billing portal; we verify "
            "against the VIES API before applying reverse charge.",
            "Italy-specific: SDI invoicing required for all B2B "
            "customers. Codice destinatario must be on file.",
            "Tax exemption for US 501(c)(3) customers: collect the "
            "exemption certificate, store in the customer's HubSpot "
            "company record, apply tax-exempt flag in Stripe.",
        ],
    ))

    # ── Anti-fraud screening ──
    pages.append(NotionPage(
        title="Anti-fraud screening procedure",
        category="Policy & SOP",
        paragraphs=[
            "Owner: Trust & Safety. Status: CURRENT. "
            "Last updated 2026-04-05.",
            "All new sign-ups are run through Stripe Radar with our "
            "custom rules. High-risk signals: disposable email domain, "
            "IP geolocation mismatch with billing address, card BIN on "
            "the high-risk list, name on the OFAC list.",
            "High-risk accounts are placed in manual review queue and "
            "their first month is held in escrow. Reviewer rubric is "
            "in the Trust & Safety Linear project under doc TS-2026-01.",
        ],
    ))

    # ── Unrelated noise SOPs ──
    pages.append(NotionPage(
        title="HR - PTO policy 2026",
        category="HR / company",
        paragraphs=[
            "Owner: People Ops. Status: CURRENT. Effective 2026-01-01.",
            "Unlimited PTO with a 15-day minimum encouraged. Holidays: "
            "US federal calendar + 2 floating days. Sabbatical: 4 weeks "
            "after 4 years tenure.",
            "Request through Rippling at least 5 business days in "
            "advance for stretches longer than 2 days. Manager approval "
            "required, no other gatekeeping.",
        ],
    ))

    pages.append(NotionPage(
        title="Security incident response policy",
        category="Policy & SOP",
        paragraphs=[
            "Owner: Security. Status: CURRENT. Last updated 2026-03-18.",
            "Classification: SEC-1 (data exposure, active intrusion), "
            "SEC-2 (suspicious access, malware), SEC-3 (policy "
            "violation, phishing attempt).",
            "SEC-1 response: page CISO immediately, contain within 1 "
            "hour, notify Legal + DPO, prepare regulator notification "
            "draft within 24 hours per GDPR Article 33.",
            "Tabletop exercises quarterly. Last exercise: 2026-04-11 - "
            "see post-exercise notes in the Security Linear project.",
        ],
    ))

    pages.append(NotionPage(
        title="Brand voice & style guide",
        category="HR / company",
        paragraphs=[
            "Owner: Marketing. Last updated 2026-02-28.",
            "Voice: direct, technical, warm. Avoid: jargon for its own "
            "sake, exclamation points, em dashes used like commas, "
            "passive voice in customer-facing copy.",
            "Capitalisation: 'Miny Labs' always two words, both "
            "capitalised. Product names are lowercase in body copy "
            "except at the start of a sentence.",
        ],
    ))

    pages.append(NotionPage(
        title="Hiring rubric - Senior Software Engineer",
        category="HR / company",
        paragraphs=[
            "Owner: Engineering hiring committee. Updated 2026-03-02.",
            "Loop: phone screen (45min, hiring manager), take-home "
            "coding (3h, evaluated by peer), virtual onsite (4 "
            "sessions: system design, deep technical, behavioural, "
            "team fit). Decision meeting within 5 business days of "
            "onsite.",
            "Bar: top 30% of candidates we onsite. Promotion-ready "
            "from senior to staff in 18-24 months at average cadence.",
        ],
    ))

    pages.append(NotionPage(
        title="Expense reimbursement policy",
        category="HR / company",
        paragraphs=[
            "Owner: Finance. Last updated 2025-12-08.",
            "Use the Ramp card for all reimbursable expenses. "
            "Out-of-pocket expenses: submit via Ramp within 30 days, "
            "attach receipt + business justification.",
            "Per-diem: $80 domestic, $120 international. Hotel: book "
            "via the travel portal; exceptions need manager approval "
            "in advance.",
        ],
    ))

    pages.append(NotionPage(
        title="Customer health scoring methodology",
        category="Policy & SOP",
        paragraphs=[
            "Owner: Customer Success. Status: CURRENT. "
            "Last updated 2026-03-30.",
            "Health scores roll up signals from product usage (PostHog), "
            "support volume (Zendesk + Intercom), invoice payment "
            "behaviour (Stripe), and CSM-supplied qualitative input.",
            "Green: trending toward expansion. Yellow: stable but "
            "missing engagement signal. Red: actively at risk - "
            "weekly CSM check-in required.",
        ],
    ))

    pages.append(NotionPage(
        title="Data retention & deletion policy",
        category="Policy & SOP",
        paragraphs=[
            "Owner: Legal + DPO. Status: CURRENT. Last updated 2026-01-15.",
            "Customer data is retained for the duration of the active "
            "subscription + 90 days post-termination. After 90 days, "
            "data is purged from production and archived for one year "
            "in cold storage before final deletion.",
            "Deletion requests under GDPR Article 17 are processed "
            "within 30 days via the privacy portal.",
        ],
    ))

    return pages


def _pages_customer_accounts() -> list[NotionPage]:
    """Customer account health-notes pages (~17 pages). The three workflow
    targets get specific detailed account histories that bake in signals."""
    pages: list[NotionPage] = []

    # ── W1: Acme Genomics - daisy-chain history ──
    pages.append(NotionPage(
        title="Account: Acme Genomics - health notes",
        category="Customer account",
        signal_id="W1",
        headings=[(2, "Acme Genomics - account health & dispute history")],
        paragraphs=[
            "Customer: Acme Genomics. Stripe customer "
            "cus_test_acme_genomics. Plan: Pro Annual, $42,000 ARR. "
            "Signup: 2023. Industry: genomics. Country: USA. CSM: "
            "Priya. AE: David. Health: YELLOW (downgraded from green "
            "after dispute history pattern).",

            "Last formal customer contact: data export inquiry in "
            "March 2026 - see Intercom thread. NOT a cancel request. "
            "Renewal completed normally on May 12, 2026 at the "
            "$42,000 list price (May renewal invoice "
            "in_acme_2026_05).",

            "",
            "Dispute history (this is the important section - see "
            "'Refunds & Disputes - 2026 SOP (CURRENT)' Section 2 for "
            "the policy that applies):",

            "Dispute #1: filed 2025-08-22. Stripe dispute id "
            "dp_acme_v1. Reason: subscription_canceled. Amount: "
            "$4,200 (one month of the prior Pro Annual cycle). "
            "Outcome: WON BY CUSTOMER. We refunded. No formal cancel "
            "request was on file - customer claimed in the dispute "
            "narrative that they had 'asked to cancel' but Intercom "
            "and Zendesk have no such thread.",

            "Dispute #2: filed 2026-01-09. Stripe dispute id "
            "dp_acme_v2. Reason: subscription_canceled. Amount: "
            "$4,200. Outcome: WON BY CUSTOMER. We refunded. Same "
            "pattern: no formal cancel on file, customer kept using "
            "the product through the disputed period (PostHog shows "
            "daily DAU on Acme's tenant).",

            "Pattern: Acme has filed 2 prior subscription_canceled "
            "disputes within a 14-month window (2025-08 and 2026-01), "
            "BOTH won by customer, BOTH refunded by us. Customer never "
            "actually followed through on the supposed cancel - they "
            "kept using the product, kept paying the next invoice, "
            "kept generating active-user signal. Per the RevOps SOP "
            "(policy id RD-2026-S2) this is a textbook daisy-chained-"
            "chargebacks pattern.",

            "",
            "Standing instruction (Priya, 2026-05-01): on dispute #3 "
            "we fight + force-cancel. Per policy. AE wants to keep the "
            "logo but Priya and VP Finance are aligned: bad-faith "
            "customers cost more than they're worth.",

            "Expansion / renewal: AE notes opportunity for an "
            "Enterprise upgrade at next renewal if relationship can be "
            "stabilised. Blocked on the dispute pattern.",

            "Risks: net-new dispute likely on the May 2026 invoice. "
            "If filed, route per RD-2026-S2.",

            "Last updated: 2026-05-15 by priya@miny-labs.com.",
        ],
    ))

    # ── W2: Northwind Logistics - webhook ghost-paid ──
    pages.append(NotionPage(
        title="Account: Northwind Logistics - Q2 2026 enterprise upgrade",
        category="Customer account",
        signal_id="W2",
        headings=[(2, "Northwind Logistics - Q2 2026 enterprise upgrade")],
        paragraphs=[
            "Customer: Northwind Logistics. Stripe customer "
            "cus_test_northwind_logi. Plan: previously Standard, "
            "upgraded to Enterprise Annual May 2026. ARR pre-upgrade "
            "$108,000; post-upgrade $117,000 ($9,000 upgrade fee for "
            "the remaining year). Industry: logistics. Country: USA. "
            "CSM: Wei. AE: Marcus. Health: GREEN (strategic).",

            "Renewal cycle: November. Strategic account - see brand-"
            "name list in the Sales playbook.",

            "",
            "Q2 2026 upgrade incident (active issue):",
            "Northwind purchased the Enterprise upgrade on 2026-05-12 "
            "for $9,000 (Stripe invoice in_northwind_2026_05_upgrade, "
            "payment_intent pi_northwind_2026_05_upgrade). Customer "
            "reports the upgrade never activated on their tenant - "
            "they are still on Standard-tier feature flags, no "
            "Enterprise-only features visible, and their analytics "
            "behaviour in PostHog confirms the entitlement did NOT "
            "flip.",

            "Engineering investigation in progress in the "
            "billing_engineering Linear project. Initial finding from "
            "Wei's check of Datadog: a SEV-1 incident occurred in the "
            "webhook handler around 2026-05-12 14:00-15:30 UTC - "
            "PagerDuty page id pd_alert_2026_05_12. The "
            "invoice.payment_succeeded handler crashed with an "
            "unhandled exception in the entitlement-flip path. Sentry "
            "issue BILL-2451 captures the stack trace.",

            "This matches the vendor-failure pattern documented in "
            "'Vendor failure refund policy' (policy id VFR-2026) "
            "exactly: Stripe charge succeeded, our internal "
            "entitlement never flipped, customer paid for value they "
            "did not receive.",

            "",
            "Standing instruction (Wei, 2026-05-13): if Northwind "
            "files a dispute, classify as vendor-failure per VFR-2026. "
            "Refund full + apology + manual entitlement upgrade. NEVER "
            "fight. CC marcus@miny-labs.com on the apology email.",

            "Risk: strategic logo, renewal Nov. Mishandling this "
            "incident is an existential threat to renewal.",

            "Last updated: 2026-05-20 by wei@miny-labs.com.",
        ],
    ))

    # ── W3: Mockingbird Media - migration cutover ──
    pages.append(NotionPage(
        title="Account: Mockingbird Media - Migration cutover March 2026",
        category="Customer account",
        signal_id="W3",
        headings=[
            (2, "Mockingbird Media - billing-entity migration"),
        ],
        paragraphs=[
            "Customer: Mockingbird Media. Stripe customer "
            "cus_test_mockingbird_med. Plan: Pro Annual, $66,000 ARR. "
            "Signup: 2022 (legacy entity). Industry: media. Country: "
            "USA. CSM: Wei. AE: Sara. Health: YELLOW (downgraded due "
            "to migration friction).",

            "",
            "Migration history:",
            "Mockingbird migrated from our legacy billing entity "
            "(Chargebee) onto our Stripe entity on 2026-03-12 as part "
            "of the post-acquisition cleanup project (see 'Billing "
            "platform migration - runbook & timeline'). Per the "
            "migration runbook, their legacy Chargebee subscription "
            "was supposed to terminate at end-of-March cutover "
            "(2026-03-31 23:59 UTC).",

            "However: the legacy subscription was NOT actually "
            "terminated at cutover. Mockingbird has been billed on "
            "both sides since April - Stripe invoice "
            "in_mockingbird_2026_04 for $5,500, and legacy Chargebee "
            "invoice cb_inv_mockingbird_2026_04 also for $5,500. "
            "Same for May (in_mockingbird_2026_05 + "
            "cb_inv_mockingbird_2026_05).",

            "This matches the post-acquisition double-billing pattern "
            "documented in 'Post-Acquisition Migration Cleanup SOP' "
            "(policy id PAM-2026) exactly. Per the runbook: refund "
            "the LEGACY-side charges (the Chargebee invoices), "
            "force-cancel the legacy Chargebee sub back-dated to "
            "2026-03-31, consolidate to Stripe, issue credit memo. "
            "Tag billing-bug-7172.",

            "",
            "Standing instruction (Wei, 2026-05-18): if Mockingbird "
            "files a dispute on either side, classify as post-"
            "acquisition double-billing per PAM-2026. Refund the "
            "Chargebee-side duplicate-period charges in full. "
            "Force-cancel the Chargebee sub. Issue a credit memo for "
            "the duplicate period as a customer-trust gesture.",

            "Risk: customer is frustrated with the migration. Sara "
            "(AE) has been managing the relationship. Renewal cycle "
            "originally April; renewal extended 60 days to allow "
            "cleanup. New renewal date: 2026-06-12.",

            "Last updated: 2026-05-22 by wei@miny-labs.com.",
        ],
    ))

    # ── Other (noise) customer account pages ──
    noise_accounts = [
        ("acme-logistics", "Different from Acme Genomics. Currently churning - high support volume, low DAU. Probably non-renew at next cycle. AE: Marcus.", "RED"),
        ("helix-bio", "AR escalation in progress. 47 days past due on the Q1 invoice. Finance is working with their AP team. Strategic logo despite the AR pain.", "RED"),
        ("globex-software", "Healthy expansion candidate. Two new seats added in March. CSM-led upsell motion for the team plan.", "GREEN"),
        ("stellar-ai", "Top 10 ARR account. Quarterly business review scheduled for June. Renewal cycle November. AE: David.", "GREEN"),
        ("phoenix-fund", "Top 5 ARR account. CRO sponsors the relationship directly. Renewal cycle March 2027.", "GREEN"),
        ("cascade-cloud", "Heavy API user. Reliability sensitive - any SEV-1 affecting them is a relationship risk. Renewal cycle August.", "GREEN"),
        ("hydra-finance", "Singapore-based fintech. KYC documentation completed Feb 2026. Renewal cycle May 2027.", "GREEN"),
        ("nexus-data", "Embedded with our data platform team - joint roadmap discussion ongoing. Expansion likely Q3.", "GREEN"),
        ("voyager-shipping", "Netherlands-based. EU VAT exemption applied. Mid-cycle expansion attempt failed in March - customer paused.", "YELLOW"),
        ("solstice-care", "Healthcare. HIPAA BAA on file. Strategic vertical. CSM: Wei. Renewal August 2027.", "GREEN"),
        ("orion-labs", "UK research lab. Renewal cycle Sept. Recently flagged in Intercom about pricing sensitivity - CSM follow-up scheduled.", "YELLOW"),
        ("summit-payments", "Fintech with seasonal usage spikes. SLA-sensitive. Renewal cycle Feb 2027.", "YELLOW"),
        ("delta-payments", "Fintech, smaller than Summit. Currently in retention play after a downgrade attempt. CSM weekly check-ins.", "YELLOW"),
        ("vertex-mining", "Australia-based. Bandwidth-sensitive - they have intermittent connectivity issues in remote sites. CS-led adoption coaching.", "YELLOW"),
    ]

    for slug, summary, health in noise_accounts:
        # Find display name
        from seed_world import find_company as fc
        try:
            c = fc(slug)
            display_name = c.name
        except KeyError:
            display_name = slug.replace("-", " ").title()
        pages.append(NotionPage(
            title=f"Account: {display_name} - health notes",
            category="Customer account",
            paragraphs=[
                f"Customer: {display_name}. Health: {health}.",
                summary,
                "Last updated by CSM team during the 2026-Q2 portfolio review.",
            ],
        ))

    return pages


def _pages_meetings() -> list[NotionPage]:
    """All-hands & meeting notes (~12 pages). Mostly noise. Some red
    herrings that mention refunds in passing."""
    return [
        NotionPage(
            title="Q1 2026 all-hands notes",
            category="Meeting notes",
            paragraphs=[
                "Q1 2026 all-hands. Date: 2026-04-04. Attendance: full company.",
                "Key updates: Q1 revenue beat plan by 6%. Two strategic logo "
                "wins (Stellar AI expansion, Phoenix Fund renewal at "
                "+18% ARR). Engineering shipped the new entitlement service "
                "(GA in February).",
                "Q&A: someone asked about the increase in disputes in Q1 - "
                "Priya (RevOps) noted it correlates with the inbound surge "
                "and that the new SOP is reducing the refund-on-default "
                "behaviour from the old policy. Not a system-wide issue.",
                "Q2 priorities: post-acquisition migration cleanup "
                "(see runbook), webhook reliability project (Sev tracking), "
                "and the new pricing experiment.",
            ],
        ),
        NotionPage(
            title="Sales kickoff 2026",
            category="Meeting notes",
            paragraphs=[
                "Sales kickoff 2026. Date: 2026-01-15. Attendance: GTM org.",
                "FY26 plan: $14M new ARR, $4M expansion, 92% gross retention.",
                "Territory changes: Marcus picks up Northwind from outgoing "
                "AE. Sara picks up Mockingbird (post-acquisition migration).",
                "New playbooks: vertical-specific plays for healthcare and "
                "logistics. See the Sales Linear project.",
            ],
        ),
        NotionPage(
            title="Engineering planning Q2 2026",
            category="Meeting notes",
            paragraphs=[
                "Engineering planning meeting. Date: 2026-03-28.",
                "Priority projects: (1) webhook reliability project - "
                "see post-mortems doc; (2) post-acquisition billing "
                "migration cleanup; (3) entitlement service v2 "
                "(idempotency + replay).",
                "Capacity: 14 engineers across platform, data, and "
                "frontend. Q2 stretch: ship webhook idempotency by EOQ.",
            ],
        ),
        NotionPage(
            title="Board meeting notes Feb 2026",
            category="Meeting notes",
            paragraphs=[
                "Board meeting. Date: 2026-02-19. Attendance: board + "
                "exec team.",
                "Highlights: Q4 revenue beat plan by 9%. Net retention "
                "118%. Logo retention 94%. Two-quarter trailing dispute "
                "rate trending DOWN after the 2026 SOP rollout.",
                "Lowlights: post-acquisition migration is delayed by "
                "two months - billing engineering capacity-constrained.",
                "Next board: May 2026.",
            ],
        ),
        NotionPage(
            title="RevOps weekly - 2026-05-15",
            category="Meeting notes",
            paragraphs=[
                "RevOps weekly. Attendance: Priya, Wei, Marcus, Sara, "
                "David, VP Finance.",
                "Open disputes:",
                "- Acme Genomics: history of two prior won-by-customer "
                "disputes; per RD-2026-S2 we fight + force-cancel on "
                "next dispute (Priya owns).",
                "- Northwind: vendor-failure case from the May upgrade "
                "incident; per VFR-2026 we refund full if/when disputed "
                "(Wei owns).",
                "- Mockingbird: double-billing per PAM-2026, awaiting "
                "AR cleanup (Wei + AR own).",
                "Next steps: AE training session on the 2026 SOP next week.",
            ],
        ),
        NotionPage(
            title="Customer Success weekly - 2026-05-08",
            category="Meeting notes",
            paragraphs=[
                "CS weekly. Attendance: CS team + Wei (CSM lead).",
                "Portfolio health: 4 yellow accounts moved back to green "
                "this week. 1 new red (Acme Logistics - confirmed churn "
                "at next renewal). QBRs scheduled with top-10 ARR.",
                "Action items: refresh health-score model with the new "
                "PostHog feature-usage cohorts.",
            ],
        ),
        NotionPage(
            title="Product roadmap review Q2 2026",
            category="Meeting notes",
            paragraphs=[
                "Roadmap review. Date: 2026-04-15. Attendance: Product, "
                "Engineering, Design leads.",
                "Q2 commits: entitlement service v2, audit log GA, "
                "advanced filters in the dashboard, SSO improvements.",
                "Cuts: the AI-assist feature is being deprioritised to Q3 "
                "due to engineering capacity.",
            ],
        ),
        NotionPage(
            title="AE off-site notes - March 2026",
            category="Meeting notes",
            paragraphs=[
                "AE off-site. Date: 2026-03-21 to 2026-03-23.",
                "Theme: 'sell the value, not the discount'. Workshops on "
                "discovery, technical evaluation, mutual action plans.",
                "Output: new AE certification framework rolling out in "
                "Q2. RevOps reviews the cert quarterly.",
            ],
        ),
        NotionPage(
            title="Town hall - March 2026",
            category="Meeting notes",
            paragraphs=[
                "Monthly town hall. Date: 2026-03-31.",
                "CEO update: closed the Series B extension. Hiring plan "
                "for 2026 expanded.",
                "Eng update: webhook reliability post-mortem from "
                "January reviewed. New idempotency framework rolling "
                "out Q2.",
            ],
        ),
        NotionPage(
            title="Engineering planning Q3 2026 - draft",
            category="Meeting notes",
            paragraphs=[
                "Draft. Date: 2026-05-22. Not yet finalised.",
                "Likely Q3 priorities: entitlement service v2 cleanup, "
                "billing platform consolidation finish-line, new "
                "metering for the consumption pricing experiment.",
            ],
        ),
        NotionPage(
            title="Marketing kickoff 2026",
            category="Meeting notes",
            paragraphs=[
                "Marketing kickoff. Date: 2026-01-22.",
                "Brand refresh in Q2. Three new vertical campaigns "
                "(logistics, healthcare, fintech). New customer story "
                "library: top targets are Stellar AI and Phoenix Fund.",
            ],
        ),
        NotionPage(
            title="Compliance review - SOC2 2026",
            category="Meeting notes",
            paragraphs=[
                "Compliance review meeting. Date: 2026-02-12.",
                "SOC2 Type II audit window: April-October 2026. "
                "Auditor: redacted. Open issues: encrypt-at-rest in the "
                "legacy billing-entity database (closes during the "
                "migration), MFA enforcement for all admin tools "
                "(closed Q1).",
            ],
        ),
    ]


def _pages_engineering() -> list[NotionPage]:
    """Project & engineering docs (~18 pages)."""
    return [
        # The webhook-reliability project - explicit W2 corroboration
        NotionPage(
            title="Webhook reliability project - post-mortems",
            category="Engineering doc",
            signal_id="W2",
            paragraphs=[
                "Owner: Platform Engineering. Status: active. "
                "Last updated 2026-05-21.",
                "Background: throughout late 2025 and early 2026 we "
                "have had recurring incidents in the webhook handler "
                "stack - specifically the invoice.payment_succeeded "
                "handler that owns flipping internal entitlements. "
                "Each crash leaves customers in a ghost-paid state.",

                "",
                "Post-mortem: 2026-01-04. Trigger: malformed metadata "
                "in a customer's invoice caused KeyError in the "
                "entitlement-flip path. Impact: ~12 customers affected "
                "over a 4-hour window. Resolution: manual "
                "entitlement repair, Stripe webhook replay. Action "
                "items: input validation, default-value handling.",

                "Post-mortem: 2026-03-08. Trigger: a slow database "
                "query in the entitlement service timed out the "
                "webhook handler. Impact: ~3 customers affected. "
                "Resolution: index added, query optimised. Action "
                "items: timeout budget alerting.",

                "Post-mortem: 2026-05-12 (SEV-1). Trigger: unhandled "
                "exception in the entitlement-flip path during a "
                "feature-flag rollout. PagerDuty page "
                "pd_alert_2026_05_12. Customers affected: Northwind "
                "Logistics (Enterprise upgrade $9,000) - confirmed "
                "ghost-paid. Possibly 1-2 others not yet identified. "
                "Sentry issue BILL-2451. Datadog dashboard "
                "wh_2026_05_12. Resolution: feature flag rolled back, "
                "code path fixed in PR billing/2451, deployed "
                "2026-05-13. Manual entitlement repair for Northwind "
                "in progress. Action items: webhook idempotency "
                "framework (Q2 priority).",

                "",
                "Reference: project Linear ID WHR-2026. "
                "Internal URL https://miny-labs.notion.site/eng-"
                "webhook-reliability . Next milestone: webhook "
                "idempotency v1 by 2026-06-30.",
            ],
        ),
        # The migration project doc - explicit W3 corroboration
        NotionPage(
            title="Billing platform migration - runbook & timeline",
            category="Engineering doc",
            signal_id="W3",
            paragraphs=[
                "Owner: Billing Engineering + Finance. Status: "
                "winding-down. Last updated 2026-05-19.",

                "Background: in Q4 2025 we acquired a smaller "
                "competitor and inherited their Chargebee-based "
                "billing entity. Migration plan: move all legacy "
                "subscriptions onto our Stripe entity by end-of-March "
                "2026, terminating the legacy sub at period-end. See "
                "'Post-Acquisition Migration Cleanup SOP' for the "
                "policy that governs cleanup.",

                "",
                "Cutover schedule:",
                "- 2026-02-15: Wave 1 customers migrated (small "
                "accounts, low risk). Legacy subs terminated "
                "successfully.",
                "- 2026-03-12: Wave 2 customers migrated (Mockingbird "
                "Media + 6 others). Cutover date for these accounts "
                "is end-of-March (2026-03-31 23:59 UTC).",
                "- 2026-03-25: Wave 3 customers migrated (largest "
                "legacy accounts). Cutover end-of-April.",

                "",
                "Known issue: at the end-of-March cutover, the legacy "
                "Chargebee subscriptions for Wave 2 customers were "
                "NOT all terminated as planned. A bug in the "
                "termination script ("
                "see billing-bug-7172 in Linear) left ~6 customers "
                "still being billed on both sides. Mockingbird Media "
                "is the most affected (highest ARR in the cohort).",

                "Cleanup procedure: per the SOP, refund the LEGACY-"
                "side duplicate-period charges, back-date-cancel the "
                "legacy sub to 2026-03-31, consolidate to Stripe, "
                "issue credit memo.",

                "Status of the 6 affected customers (as of 2026-05-19):",
                "- Mockingbird Media: cleanup pending - awaiting "
                "dispute resolution.",
                "- 5 other accounts: cleanup completed by AR team in "
                "April-May. Reconciliation confirmed.",

                "Reference: project Linear ID BMI-2025. Umbrella issue "
                "billing-bug-7172. Internal URL "
                "https://miny-labs.notion.site/eng-billing-platform-"
                "migration .",
            ],
        ),
        NotionPage(
            title="Entitlement service v2 - design doc",
            category="Engineering doc",
            paragraphs=[
                "Owner: Platform Engineering. Status: in design.",
                "Goals: idempotent entitlement flips, replay-safe, "
                "audit-log first-class. Replaces v1 which has been "
                "the source of multiple webhook-related ghost-paid "
                "incidents.",
                "Design: append-only event log, materialised views "
                "for current entitlement state, replay tool for "
                "manual repair.",
            ],
        ),
        NotionPage(
            title="Database migration plans - Q3 2026",
            category="Engineering doc",
            paragraphs=[
                "Owner: Data Platform. Status: planning.",
                "Migrate the events table from Postgres to "
                "ClickHouse. Expected wall time: 6 weeks. "
                "Dependencies: dual-write infrastructure, "
                "shadow-read validation.",
            ],
        ),
        NotionPage(
            title="OAuth refactor proposal",
            category="Engineering doc",
            paragraphs=[
                "Owner: Identity team. Status: RFC.",
                "Replace our legacy session-cookie auth with OAuth "
                "2.1 + PKCE for first-party clients. Migration "
                "strategy: dual-stack for 6 months, then sunset "
                "the legacy cookie path.",
            ],
        ),
        NotionPage(
            title="API rate limiting design",
            category="Engineering doc",
            paragraphs=[
                "Owner: Platform Engineering. Status: implementation.",
                "Token-bucket per API key, sliding window for burst "
                "protection. Different limits per plan tier. "
                "Enforcement at the edge (Envoy filter).",
            ],
        ),
        NotionPage(
            title="Onboarding flow redesign",
            category="Engineering doc",
            paragraphs=[
                "Owner: Frontend + Product. Status: A/B testing.",
                "New onboarding emphasises time-to-first-value. "
                "Removes the wizard pattern in favour of guided "
                "discovery. Hypothesis: 20% activation lift.",
            ],
        ),
        NotionPage(
            title="Observability stack overview",
            category="Engineering doc",
            paragraphs=[
                "Owner: Platform. Last updated 2026-04-10.",
                "Datadog for metrics + APM. Sentry for application "
                "errors. PagerDuty for paging. PostHog for product "
                "analytics. Honeycomb deprecated end-of-Q2.",
            ],
        ),
        NotionPage(
            title="Feature flag governance",
            category="Engineering doc",
            paragraphs=[
                "Owner: Platform. Status: CURRENT.",
                "All flags must have an owner, an expiry, and a "
                "kill switch. Quarterly cleanup of stale flags. "
                "Flags blocking entitlement changes require a "
                "post-mortem if they cause a ghost-paid incident.",
            ],
        ),
        NotionPage(
            title="CI/CD pipeline overview",
            category="Engineering doc",
            paragraphs=[
                "Owner: DevEx. Last updated 2026-03-18.",
                "GitHub Actions → Buildkite → Argo CD. Median PR-to-"
                "production: 23 minutes. Rollback via Argo CD revert.",
            ],
        ),
        NotionPage(
            title="Audit log design doc",
            category="Engineering doc",
            paragraphs=[
                "Owner: Platform. Status: GA in Q2.",
                "Append-only audit log for all sensitive actions: "
                "entitlement changes, refund issuance, role changes, "
                "data export. Backed by Postgres + S3 archive.",
            ],
        ),
        NotionPage(
            title="SSO integrations - supported IdPs",
            category="Engineering doc",
            paragraphs=[
                "Owner: Identity. Last updated 2026-04-30.",
                "Supported: Okta, Azure AD (Entra), Google "
                "Workspace, OneLogin, JumpCloud. SCIM provisioning "
                "available on Enterprise plan only.",
            ],
        ),
        NotionPage(
            title="Frontend architecture overview",
            category="Engineering doc",
            paragraphs=[
                "Owner: Frontend. Last updated 2026-02-05.",
                "Next.js 14, React Server Components, Tailwind, "
                "shadcn. Component library in the design-system "
                "monorepo package.",
            ],
        ),
        NotionPage(
            title="Mobile app strategy",
            category="Engineering doc",
            paragraphs=[
                "Owner: Product + Mobile. Last updated 2026-03-22.",
                "iOS-first, Android Q4. Native (Swift) for iOS, "
                "Kotlin for Android. Read-only at launch - focus on "
                "alerts and approvals.",
            ],
        ),
        NotionPage(
            title="ML feature store proposal",
            category="Engineering doc",
            paragraphs=[
                "Owner: Data Science. Status: RFC.",
                "Feast-based feature store for our churn-prediction "
                "and product-recommendation models. Online + offline "
                "feature parity required.",
            ],
        ),
        NotionPage(
            title="Stripe webhook handler - architecture",
            category="Engineering doc",
            paragraphs=[
                "Owner: Billing Engineering. Last updated 2026-04-25.",
                "Inbound webhooks → Cloudflare worker → SQS queue → "
                "Lambda consumer → entitlement service. Idempotency "
                "currently weak - see 'Entitlement service v2 - "
                "design doc' for the v2 replacement.",
            ],
        ),
        NotionPage(
            title="Background job framework migration",
            category="Engineering doc",
            paragraphs=[
                "Owner: Platform. Status: complete.",
                "Migrated from Sidekiq-style worker pools to Temporal "
                "for durable workflows. Adoption: billing, "
                "entitlements, dunning. Q3: migrate the email-"
                "sending pipeline.",
            ],
        ),
        NotionPage(
            title="Data warehouse modelling guidelines",
            category="Engineering doc",
            paragraphs=[
                "Owner: Data Platform. Last updated 2026-01-22.",
                "Snowflake + dbt. Three layers: bronze (raw), "
                "silver (cleaned), gold (mart). Naming conventions "
                "in the dbt repo CONTRIBUTING.md.",
            ],
        ),
        NotionPage(
            title="Incident retrospective template",
            category="Engineering doc",
            paragraphs=[
                "Owner: Platform Engineering. Use this template for "
                "every SEV-1 and SEV-2 incident.",
                "Sections: timeline, contributing factors (not 'root "
                "cause'), customer impact, what went well, what we "
                "want to change, action items with owners and due "
                "dates. Action-item DRI must be a named person - "
                "never a team.",
            ],
        ),
        NotionPage(
            title="Cost optimisation review - 2026 Q1",
            category="Engineering doc",
            paragraphs=[
                "Owner: Platform + Finance. Quarterly cost review.",
                "Q1 spend: down 8% vs. Q4 driven by S3 lifecycle "
                "rules and reserved-instance commitments. Q2 watch "
                "items: ClickHouse migration (Q3 - expect spend "
                "increase before consolidation savings).",
            ],
        ),
    ]


def _pages_hr_company() -> list[NotionPage]:
    """HR / company / brand pages (~9 pages, noise)."""
    return [
        NotionPage(
            title="Security training - 2026 annual refresh",
            category="HR / company",
            paragraphs=[
                "Owner: Security + People Ops. Required for all "
                "employees annually.",
                "Modules: phishing awareness (with simulation), "
                "secrets management, device hygiene, social "
                "engineering, compliance basics. Completion deadline: "
                "2026-06-30.",
            ],
        ),
        NotionPage(
            title="Equity refresh - 2026 grants",
            category="HR / company",
            paragraphs=[
                "Owner: People Ops + Finance. Annual refresh "
                "cycle complete.",
                "Refresh grants vest over 4 years, 1-year cliff. "
                "Top performers received accelerated cliff. "
                "Communication: managers deliver one-on-one with "
                "the personalised grant letter.",
            ],
        ),
        NotionPage(
            title="Remote work guidelines",
            category="HR / company",
            paragraphs=[
                "Owner: People Ops. Last updated 2026-01-08.",
                "We are remote-first with hub offices in SF and "
                "NYC. Required overlap: 4 hours with the rest of "
                "your team. Annual all-hands in person.",
            ],
        ),
        NotionPage(
            title="Code of conduct",
            category="HR / company",
            paragraphs=[
                "Owner: People Ops. Last reviewed 2025-12-01.",
                "Respect, candour, ownership, customer-obsession. "
                "Zero tolerance for harassment. Reporting channels: "
                "manager, skip-level, People Ops, anonymous hotline.",
            ],
        ),
        NotionPage(
            title="Engineering levelling guide",
            category="HR / company",
            paragraphs=[
                "Owner: Engineering leadership. Last updated "
                "2026-02-14.",
                "Levels: E2 (associate) through E7 (distinguished). "
                "Each level has scope, complexity, impact, and "
                "leadership criteria. Promo cycles twice a year.",
            ],
        ),
        NotionPage(
            title="Performance review process",
            category="HR / company",
            paragraphs=[
                "Owner: People Ops. Last updated 2026-01-12.",
                "Semi-annual cycle. 360 input collected through Lattice. "
                "Calibration meetings at the org level. Compensation "
                "changes follow review by 30 days.",
            ],
        ),
        NotionPage(
            title="Internal mobility policy",
            category="HR / company",
            paragraphs=[
                "Owner: People Ops. Effective 2026-01-01.",
                "Employees can apply for internal transfers after 12 "
                "months in role with manager approval. The job board "
                "is updated weekly.",
            ],
        ),
        NotionPage(
            title="Brand assets library",
            category="HR / company",
            paragraphs=[
                "Owner: Marketing. Last updated 2026-04-02.",
                "Logos, fonts, colour palette, slide templates. "
                "External use requires Marketing approval. Internal "
                "use: free-for-all from the assets repo.",
            ],
        ),
        NotionPage(
            title="Holiday calendar 2026",
            category="HR / company",
            paragraphs=[
                "US federal holidays + 2 company floating days "
                "(Memorial Day weekend extended Friday, Day after "
                "Thanksgiving).",
                "Office closures: SF and NYC offices closed during "
                "the holiday weeks at end-of-December.",
            ],
        ),
        NotionPage(
            title="Onboarding playbook - first 30 days",
            category="HR / company",
            paragraphs=[
                "Owner: People Ops. Last updated 2026-02-20.",
                "Week 1: laptop setup, access provisioning, intro "
                "meetings with manager + skip-level + peers. Week 2: "
                "team-specific onboarding. Week 3-4: shadowing + "
                "first independent task. Day 30: check-in with "
                "manager and People Ops.",
            ],
        ),
        NotionPage(
            title="Anti-corruption & gifts policy",
            category="HR / company",
            paragraphs=[
                "Owner: Legal. Status: CURRENT. Last updated "
                "2025-11-30.",
                "No gifts to/from customers or vendors exceeding "
                "$100 in value. No payments to government officials. "
                "All vendor relationships go through Procurement.",
            ],
        ),
        NotionPage(
            title="Employee referral programme",
            category="HR / company",
            paragraphs=[
                "Owner: Talent. Effective 2026-01-01.",
                "$5,000 referral bonus for engineering hires, "
                "$3,000 for non-engineering. Payable 6 months after "
                "the referred hire's start date. Open to all "
                "employees except direct managers of the role.",
            ],
        ),
        NotionPage(
            title="Office facilities & access policy",
            category="HR / company",
            paragraphs=[
                "Owner: Facilities. Last updated 2026-03-10.",
                "Hub offices in SF and NYC. Badge access 24/7 for "
                "employees. Guest sign-in via the lobby tablet. "
                "Hot-desk reservations through the workspace app.",
            ],
        ),
    ]


def _pages_customer_facing() -> list[NotionPage]:
    """Customer-facing drafts (~5 pages). Red herrings - they mention
    refunds in marketing terms."""
    return [
        NotionPage(
            title="Blog post draft - 'Why we changed our refund policy in 2026'",
            category="Customer-facing draft",
            paragraphs=[
                "DRAFT - do not publish without Comms approval. "
                "Author: Marketing.",
                "Lede: 'Earlier this year we updated our refunds and "
                "disputes policy to better balance fairness for "
                "customers with fairness for our team.' (Soft "
                "framing - internal policy details NOT in this post.)",
                "The post is meant as a transparency gesture and "
                "should NOT reference internal SOP identifiers, dispute "
                "patterns, or specific customers.",
                "Status: pending Comms review. Target publish: Q3 2026.",
            ],
        ),
        NotionPage(
            title="Help center article - 'Understanding your invoice'",
            category="Customer-facing draft",
            paragraphs=[
                "Public help-center article. Last updated 2026-03-15.",
                "Walks the customer through the invoice fields: "
                "line items, taxes, period, payment method. Links "
                "to the refunds FAQ.",
                "Status: PUBLISHED. URL: "
                "https://help.miny-labs.com/billing/understanding-"
                "your-invoice.",
            ],
        ),
        NotionPage(
            title="Sales deck - Q2 2026 enterprise pitch",
            category="Customer-facing draft",
            paragraphs=[
                "Owner: Marketing + Sales. Refresh cycle quarterly.",
                "Top 10 slides: cover, problem, solution, customer "
                "stories (Stellar AI, Phoenix Fund, Northwind), ROI "
                "calc, security, integration map, pricing tiers, "
                "next steps.",
                "Note for AEs: customer story slides require "
                "permission from the named customer - keep the "
                "approved list updated.",
            ],
        ),
        NotionPage(
            title="Customer story - Northwind Logistics (draft)",
            category="Customer-facing draft",
            paragraphs=[
                "DRAFT - pending Northwind approval.",
                "Hero: Northwind reduced their logistics "
                "reconciliation time by 60% using our platform.",
                "Hold until the Q2 upgrade incident is fully "
                "resolved - Marcus (AE) flagged the timing.",
                "Last updated: 2026-05-19 by marketing@miny-labs.com.",
            ],
        ),
        NotionPage(
            title="Pricing page - refresh notes",
            category="Customer-facing draft",
            paragraphs=[
                "Owner: Product + Marketing. Refresh cycle every "
                "6 months.",
                "Current refresh: simpler tier names, clearer "
                "feature comparison table. Tested in March, "
                "rolling out in June.",
                "Hypothesis: 15% reduction in pricing-related "
                "support tickets.",
            ],
        ),
    ]


def all_pages() -> list[NotionPage]:
    pages: list[NotionPage] = []
    pages.extend(_pages_policies_sops())
    pages.extend(_pages_customer_accounts())
    pages.extend(_pages_meetings())
    pages.extend(_pages_engineering())
    pages.extend(_pages_hr_company())
    pages.extend(_pages_customer_facing())
    return pages


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("Manthan seed_notion - Notion seeder")
    print("=" * 70)

    pages = all_pages()
    print(f"Planned pages: {len(pages)}")

    # Category breakdown.
    from collections import Counter
    cat_counts = Counter(p.category for p in pages)
    print("Category breakdown:")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {n}")

    # Sort so that the W1/W2/W3 authoritative SOPs are created LAST.
    # The CURRENT SOP for each workflow should have the latest
    # last_edited_time so an "ORDER BY last_edited_time DESC LIMIT 1"
    # query lands on it. Notion sets last_edited_time = creation time
    # for a freshly-created page, so creating the authoritative SOPs
    # last achieves that.
    signal_titles_last = {
        "Refunds & Disputes - 2026 SOP (CURRENT)",
        "Vendor failure refund policy",
        "Post-Acquisition Migration Cleanup SOP",
    }
    ordered = (
        [p for p in pages if p.title not in signal_titles_last]
        + [p for p in pages if p.title in signal_titles_last]
    )

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # 1. Find parent page
        parent_id, parent_title = find_parent_page(client)
        print(f"\nParent page: {parent_title} ({parent_id})")
        time.sleep(REQ_SLEEP)

        # 2. List existing children for idempotency
        print("Listing existing children for idempotency...")
        existing = list_existing_children(client, parent_id)
        print(f"  found {len(existing)} existing child pages")

        # 3. Create missing pages
        created = 0
        skipped = 0
        signal_ids: dict[str, str] = {}  # signal_id -> page_id

        for page in ordered:
            if page.title in existing:
                skipped += 1
                if page.signal_id:
                    signal_ids[page.signal_id + ":" + page.title] = (
                        existing[page.title]
                    )
                print(f"  skip (exists): {page.title}")
                continue

            payload = _page_payload(parent_id, page)
            r = _request(client, "POST", "/pages", json=payload)
            if r.status_code in (200, 201):
                created += 1
                page_id = r.json().get("id", "")
                if page.signal_id:
                    signal_ids[page.signal_id + ":" + page.title] = page_id
                print(f"  created: {page.title} ({page_id[:8]}...)")
            else:
                print(
                    f"  ERROR creating '{page.title}': "
                    f"{r.status_code} {r.text[:300]}"
                )
            time.sleep(REQ_SLEEP)

    # Summary
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Pages planned: {len(pages)}")
    print(f"Pages created: {created}")
    print(f"Pages skipped (already existed): {skipped}")
    print("Category breakdown:")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {n}")

    print()
    print("Signal verification - authoritative SOPs:")
    for workflow_id in ("W1", "W2", "W3"):
        matches = {k: v for k, v in signal_ids.items() if k.startswith(f"{workflow_id}:")}
        if matches:
            for k, v in matches.items():
                title = k.split(":", 1)[1]
                print(f"  {workflow_id} - {title}")
                print(f"        page_id={v}")
        else:
            print(f"  {workflow_id} - MISSING (signal not produced)")


if __name__ == "__main__":
    main()
