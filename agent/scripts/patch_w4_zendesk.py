"""Patch W4 - Helix Bio SLA-breach refund workflow anchor.

Creates a single urgent open Zendesk ticket on the helix-bio org, for the
Manthan v2 billing-dispute investigation agent.

Idempotent: re-running detects the existing helix-bio org, the
`w4-helix-billing` user (external_id), and the W4 ticket (tracked in the
shared `.manthan/zendesk_seed_state.json` under `w4_helix_ticket`) and
skips writes accordingly.

Run:
    .venv/bin/python scripts/patch_w4_zendesk.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

# Reuse the seed_zendesk module - same auth, helpers, state file.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from seed_zendesk import (  # noqa: E402
    AUTH,
    BASE,
    SUBDOMAIN,
    TIMEOUT,
    TrialCapHit,
    _isoformat,
    _request,
    import_ticket,
    load_state,
    save_state,
    upsert_organization,
    upsert_user,
)
from seed_world import COMPANIES  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# W4 spec - Helix Bio
# ──────────────────────────────────────────────────────────────────────

W4_SLUG = "helix-bio"
W4_USER_EMAIL = "billing@helix-bio.test"
W4_USER_NAME = "Helix Bio billing"
W4_USER_EXTERNAL_ID = "ext_helix-bio_w4_billing"

W4_SUBJECT = "Urgent - May invoice clarification needed before EOQ"
W4_BODY = (
    "We need clarification on the $X May renewal invoice before our "
    "end-of-quarter close on Friday. Please respond ASAP - we have "
    "leadership reviewing this on Thursday. We've also been concerned "
    "about value delivered vs. price over the last cycle."
)
W4_PRIORITY = "urgent"
W4_STATUS = "open"
W4_TYPE = "question"
W4_DAYS_AGO = 8


def _helix_company():
    for co in COMPANIES:
        if co.slug == W4_SLUG:
            return co
    sys.exit(f"ERROR: {W4_SLUG} not found in seed_world.COMPANIES")


def main() -> None:
    state = load_state()
    state.setdefault("organizations", {})
    state.setdefault("users", {})

    helix = _helix_company()

    with httpx.Client(auth=AUTH, timeout=TIMEOUT) as client:
        # ── 1. Org: lookup or create ──────────────────────────────────
        org_id = state["organizations"].get(W4_SLUG)
        if org_id:
            print(f"helix-bio org: reusing cached id {org_id}")
        else:
            org_id, action = upsert_organization(client, helix)
            if not org_id:
                sys.exit("ERROR: failed to upsert helix-bio org")
            state["organizations"][W4_SLUG] = org_id
            save_state(state)
            print(f"helix-bio org: {action} id={org_id}")

        # ── 2. Requester user: lookup or create ───────────────────────
        user_id = state["users"].get(W4_USER_EXTERNAL_ID)
        if user_id:
            print(f"requester user: reusing cached id {user_id} ({W4_USER_EMAIL})")
        else:
            user_id, action = upsert_user(
                client,
                email=W4_USER_EMAIL,
                name=W4_USER_NAME,
                role="end-user",
                organization_id=org_id,
                external_id=W4_USER_EXTERNAL_ID,
            )
            if not user_id:
                sys.exit(f"ERROR: failed to upsert {W4_USER_EMAIL}")
            state["users"][W4_USER_EXTERNAL_ID] = user_id
            save_state(state)
            print(f"requester user: {action} id={user_id} ({W4_USER_EMAIL})")

        # ── 3. W4 ticket: skip if already created ─────────────────────
        existing_tid = state.get("w4_helix_ticket")
        if existing_tid:
            # Verify it still exists on the live API.
            r = _request(client, "GET", f"/tickets/{existing_tid}.json")
            if r.status_code == 200:
                t = r.json().get("ticket", {})
                print(
                    f"W4 ticket: already exists id={existing_tid} "
                    f"(status={t.get('status')}, priority={t.get('priority')})"
                )
                _print_summary(existing_tid)
                return
            else:
                print(
                    f"W4 ticket: cached id {existing_tid} not found "
                    f"({r.status_code}) - recreating"
                )

        # Backdate created_at by 8 days. The /imports/tickets.json endpoint
        # used by import_ticket() respects created_at (that's its purpose).
        created_at = datetime.now(timezone.utc) - timedelta(days=W4_DAYS_AGO)
        updated_at = created_at + timedelta(hours=2)
        spec = {
            "subject": W4_SUBJECT,
            "body": W4_BODY,
            "priority": W4_PRIORITY,
            "status": W4_STATUS,
            "type": W4_TYPE,
            "created_at": _isoformat(created_at),
            "updated_at": _isoformat(updated_at),
            "requester_id": user_id,
            "requester_email": W4_USER_EMAIL,
        }

        try:
            tid = import_ticket(client, spec)
        except TrialCapHit:
            sys.exit("ERROR: Zendesk trial cap hit - cannot create W4 ticket")
        if not tid:
            sys.exit("ERROR: failed to create W4 ticket")

        state["w4_helix_ticket"] = tid
        save_state(state)
        print(f"W4 ticket: created id={tid}")
        _print_summary(tid)


def _print_summary(tid: int) -> None:
    url = f"https://{SUBDOMAIN}.zendesk.com/agent/tickets/{tid}"
    print(f"  ticket id : {tid}")
    print(f"  url       : {url}")
    print(f"  api       : {BASE}/tickets/{tid}.json")


if __name__ == "__main__":
    main()
