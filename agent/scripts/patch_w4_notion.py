"""Patch W4 - Notion anchor page for the Helix Bio Zendesk SLA-breach
refund workflow.

Creates a SINGLE policy SOP page under the ManthanOps parent that
documents the Support SLA & first-response refund policy. This is the
authoritative reference Manthan v2 should cite when investigating
billing disputes that intersect with support-SLA breaches (W4).

Idempotency: before creating, we list child pages of the parent and
skip if a page with this exact title already exists. Re-running is
safe.

Reuses seed_notion's auth, HTTP wrapper, page-builder, and parent
lookup so we stay in lock-step with the original seeder's behaviour.

Run:
    .venv/bin/python scripts/patch_w4_notion.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

# Reuse seed_notion's HTTP + page-builder helpers.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from seed_notion import (  # noqa: E402
    HEADERS,
    REQ_SLEEP,
    TIMEOUT,
    NotionPage,
    _page_payload,
    _request,
    find_parent_page,
    list_existing_children,
)


# ──────────────────────────────────────────────────────────────────────
# W4 spec - Support SLA & first-response refund policy
# ──────────────────────────────────────────────────────────────────────

W4_PAGE = NotionPage(
    title="Support SLA & first-response refund policy",
    category="Policy & SOP",
    signal_id="W4",
    paragraphs=[
        "Owner: CS lead (jules@miny-labs.com). Status: CURRENT - "
        "authoritative. Last reviewed 2026-04-22.",

        "Scope: this policy covers support ticket SLA breaches and "
        "the goodwill refund offered to customers when our "
        "first-response targets are missed on urgent tickets. Does "
        "NOT cover platform uptime SLA credits - see 'SLA credit "
        "calculation runbook'.",

        "First-response SLA targets (measured from ticket creation "
        "to first non-automated human reply): Urgent priority - 4 "
        "business hours. High priority - 1 business day. Normal - 2 "
        "business days.",

        "If first-response SLA is breached by >72 hours on an Urgent "
        "ticket, the customer is eligible for a one-month goodwill "
        "credit applied as a refund to the most recent invoice. "
        "Apply automatically, do not wait for the customer to ask.",

        "If the customer has already raised a refund request OR a "
        "Stripe dispute citing 'no support' / 'unresponsive' / "
        "'never heard back' style language AND there is an Urgent "
        "ticket aged >72h with no first-responder reply, the right "
        "move is to refund the most recent month + apologize. NEVER "
        "fight - the SLA breach is on us.",

        "Calculation: refund = (annual ARR / 12) for customers on "
        "annual plans; OR the most recent monthly charge for "
        "customers on monthly plans. Round to nearest dollar.",

        "Cite this policy in the resolution note: policy id "
        "SLA-2026-04. Tag the case `support-sla-breach` in HubSpot.",

        "Reference: internal URL "
        "https://miny-labs.notion.site/sla-support-2026 . Approved "
        "by: cs-leads + revops. Next review: 2026-10-01.",
    ],
)


def main() -> None:
    print("=" * 70)
    print("Manthan patch_w4_notion - W4 SLA-breach policy SOP")
    print("=" * 70)

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # 1. Find parent page (same parent as the other policy SOPs).
        parent_id, parent_title = find_parent_page(client)
        print(f"\nParent page: {parent_title} ({parent_id})")
        time.sleep(REQ_SLEEP)

        # 2. Idempotency: bail if a page with this exact title is
        # already a child of the parent.
        print("Listing existing children for idempotency...")
        existing = list_existing_children(client, parent_id)
        print(f"  found {len(existing)} existing child pages")

        if W4_PAGE.title in existing:
            page_id = existing[W4_PAGE.title]
            print(
                f"\nSKIP: page already exists - title={W4_PAGE.title!r} "
                f"page_id={page_id}"
            )
            _print_summary(page_id)
            return

        # 3. Create the page.
        payload = _page_payload(parent_id, W4_PAGE)
        r = _request(client, "POST", "/pages", json=payload)
        if r.status_code not in (200, 201):
            sys.exit(
                f"ERROR creating W4 page: {r.status_code} {r.text[:500]}"
            )
        body = r.json()
        page_id = body.get("id", "")
        url = body.get("url", "")
        print(f"\nCREATED: {W4_PAGE.title}")
        print(f"  page_id: {page_id}")
        print(f"  url    : {url}")


def _print_summary(page_id: str) -> None:
    # Reconstruct the canonical Notion URL from the page id.
    pid = page_id.replace("-", "")
    title_slug = W4_PAGE.title.replace(" ", "-").replace("&", "and")
    print(f"  page_id: {page_id}")
    print(f"  url    : https://www.notion.so/{title_slug}-{pid}")


if __name__ == "__main__":
    main()
