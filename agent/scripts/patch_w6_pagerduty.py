"""Patch PagerDuty with W6 signal - cascade-cloud auth-svc outage.

Creates a single resolved high-urgency incident on the auth-service
service:
  auth-service: KMS-rejected signing key causing intermittent token
  issuance failures - partial degradation

The narrative is a 15-day partial degradation, opened ~19 days ago,
resolved ~5 days ago. PagerDuty stamps created_at itself; we bake the
narrative timestamps into the title/body + an explicit resolution log
entry so the agent has reference points it can match against Sentry
and Datadog.

Reuses auth + base client + helpers from seed_pagerduty.py.

Run:
    .venv/bin/python scripts/patch_w6_pagerduty.py
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from seed_pagerduty import (  # noqa: E402
    HEADERS,
    REQ_SLEEP,
    REQUESTER_EMAIL,
    TIMEOUT,
    _incident_key,
    _request,
    create_incident,
    fetch_all_incident_keys,
    find_service_id_by_name,
    first_escalation_policy_id,
    update_incident_status,
    upsert_service,
)

# ──────────────────────────────────────────────────────────────────────
# W6 config
# ──────────────────────────────────────────────────────────────────────

W6_SERVICE = "auth-service"
W6_SERVICE_DESC = (
    "Authentication / authorization - token issuance, session "
    "validation, OAuth callback handlers."
)

W6_CUSTOMER_ID = "cus_UankGYRlc7WiW1"          # Stripe id for Cascade Cloud
W6_CUSTOMER_DOMAIN = "cascade-cloud.test"

W6_TITLE = (
    "auth-service: KMS-rejected signing key causing intermittent token "
    "issuance failures - partial degradation"
)
W6_URGENCY = "high"

# Narrative dates - PagerDuty cannot backdate created_at via REST API,
# so the chronology is captured in the body + a resolution log-entry note.
_NOW = datetime.now(timezone.utc)
W6_CREATED_NARRATIVE = _NOW - timedelta(days=19)
W6_RESOLVED_NARRATIVE = _NOW - timedelta(days=5)
W6_DURATION_DAYS = (W6_RESOLVED_NARRATIVE - W6_CREATED_NARRATIVE).days  # 14d

W6_BODY = (
    f"Partial degradation of auth-service token issuance.\n\n"
    f"Narrative timeline (authoritative - PagerDuty timestamps reflect "
    f"seed time, not the actual outage):\n"
    f"  - Declared (created_at narrative): "
    f"{W6_CREATED_NARRATIVE.isoformat()}  ({W6_CREATED_NARRATIVE.date()})\n"
    f"  - Resolved (resolved_at narrative): "
    f"{W6_RESOLVED_NARRATIVE.isoformat()}  ({W6_RESOLVED_NARRATIVE.date()})\n"
    f"  - Duration: ~{W6_DURATION_DAYS} days (intermittent throughout)\n\n"
    f"Symptoms: POST /v1/oauth/token returning 503 for ~3-7% of requests "
    f"in spurts of 5-40 minutes. Affected primarily customer "
    f"{W6_CUSTOMER_ID} ({W6_CUSTOMER_DOMAIN}, ARR $78k, Pro Annual) - "
    f"their SSO + machine-to-machine clients hit elevated 401s/503s and "
    f"degraded login UX for end users in the cascade-cloud.test tenant.\n\n"
    f"Root cause: KMS rejected the active signing key "
    f"`auth-prod-2026q2`. The rotation policy disabled the older key "
    f"version before the replacement (`auth-prod-2026q2-replacement`) "
    f"was promoted to primary. Whenever auth-service worker picked the "
    f"disabled key version under load, the KMS Sign() call returned "
    f"AccessDeniedException → bubbled as TokenIssuanceError → 503 to "
    f"the client. Sentry issue: TokenIssuanceError on project "
    f"auth-svc. Datadog monitor: 'auth-service token issuance error "
    f"rate elevated' (workflow:W6-cascade-auth, "
    f"incident:INC-2026-05-08-authkms).\n\n"
    f"Remediation: deploy rolled forward to new signing key version "
    f"(`auth-prod-2026q2-replacement`); rotation runbook updated to "
    f"require 24h overlap before disabling the previous version.\n\n"
    f"Customer comms: Cascade Cloud (billing@cascade-cloud.test) "
    f"raised a billing dispute citing degraded service during the "
    f"affected billing period. Refer to billing-ops workflow "
    f"W6-cascade-auth for the dispute investigation."
)

W6_RESOLUTION_NOTE = (
    "deploy rolled forward to new signing key version"
)


# ──────────────────────────────────────────────────────────────────────
# Log entry / resolution note helpers
# ──────────────────────────────────────────────────────────────────────


def add_incident_note(
    client: httpx.Client, incident_id: str, content: str
) -> bool:
    """Attach a note to an incident - surfaces in the incident's log."""
    body = {"note": {"content": content}}
    r = _request(
        client,
        "POST",
        f"/incidents/{incident_id}/notes",
        json=body,
        extra_headers={"From": REQUESTER_EMAIL},
    )
    if r.status_code in (200, 201):
        return True
    print(
        f"  note add fail [{incident_id}]: "
        f"{r.status_code} {r.text[:200]}"
    )
    return False


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    print("== PagerDuty W6 patch - cascade-cloud auth-svc outage ==")
    print(f"  customer_id    : {W6_CUSTOMER_ID}")
    print(f"  customer_domain: {W6_CUSTOMER_DOMAIN}")
    print(f"  service        : {W6_SERVICE}")
    print(f"  created (narr) : {W6_CREATED_NARRATIVE.isoformat()}")
    print(f"  resolved (narr): {W6_RESOLVED_NARRATIVE.isoformat()}")
    print(f"  duration       : ~{W6_DURATION_DAYS} days")
    print()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # ── 1. Get an escalation policy.
        ep_id = None
        sid, ep_id_existing = find_service_id_by_name(client, W6_SERVICE)
        if ep_id_existing:
            ep_id = ep_id_existing
        if not ep_id:
            r = _request(client, "GET", "/services", params={"limit": 25})
            if r.status_code == 200:
                for s in r.json().get("services", []):
                    if s.get("escalation_policy", {}).get("id"):
                        ep_id = s["escalation_policy"]["id"]
                        break
        if not ep_id:
            ep_id = first_escalation_policy_id(client)
        if not ep_id:
            sys.exit(
                "ERROR: no escalation policy found. Create one in the "
                "PagerDuty UI first."
            )
        print(f"[1] Escalation policy id: {ep_id}")

        # ── 2. Service - create if missing.
        print(f"\n[2] Ensuring service {W6_SERVICE!r}")
        sid, action = upsert_service(client, W6_SERVICE, W6_SERVICE_DESC, ep_id)
        if not sid:
            sys.exit(f"ERROR: could not upsert service {W6_SERVICE}")
        print(f"  [{action}] {W6_SERVICE} → {sid}")
        time.sleep(REQ_SLEEP)

        # ── 3. Check for existing W6 incident (idempotency).
        print("\n[3] Checking for existing W6 incident…")
        w6_key = _incident_key(W6_SERVICE, W6_TITLE, salt="W6")
        existing_keys = fetch_all_incident_keys(client)
        existing = w6_key in existing_keys
        if existing:
            print(f"  W6 already seeded (key={w6_key}); resolving lookup…")
            r = _request(
                client, "GET", "/incidents", params={"incident_key": w6_key}
            )
            inc_id = None
            inc_num = None
            if r.status_code == 200:
                incs = r.json().get("incidents", [])
                if incs:
                    inc_id = incs[0].get("id")
                    inc_num = incs[0].get("incident_number")
        else:
            print(f"  no existing W6 incident; creating (key={w6_key})")
            inc_id, inc_num = create_incident(
                client, sid, W6_TITLE, W6_URGENCY, W6_BODY, w6_key
            )
            if not inc_id:
                sys.exit("ERROR: failed to create W6 incident")
            time.sleep(REQ_SLEEP)

        print(f"  W6 incident: id={inc_id} number={inc_num}")

        # ── 4. Add resolution note as a log entry.
        print("\n[4] Adding resolution note to incident log…")
        if inc_id:
            ok = add_incident_note(client, inc_id, W6_RESOLUTION_NOTE)
            print(f"  note added: {ok}")
            time.sleep(REQ_SLEEP)

        # ── 5. Resolve.
        print("\n[5] Resolving incident (status=resolved)…")
        if inc_id:
            # Always issue the resolve PUT - idempotent if already resolved.
            ok = update_incident_status(client, inc_id, "resolved")
            print(f"  resolved: {ok}")
            time.sleep(REQ_SLEEP)

        # ── 6. Verify via GET service + GET incident.
        print("\n[6] Verifying via PagerDuty API…")
        # 6a. service has the incident
        r = _request(
            client,
            "GET",
            "/incidents",
            params={"service_ids[]": sid, "incident_key": w6_key,
                    "statuses[]": "resolved"},
        )
        found = False
        verify_status = None
        if r.status_code == 200:
            for inc in r.json().get("incidents", []):
                if inc.get("incident_key") == w6_key:
                    found = True
                    verify_status = inc.get("status")
                    break
        print(f"  GET service incidents → found={found} status={verify_status}")

    print("\n" + "=" * 60)
    print("W6 PAGERDUTY SUMMARY")
    print("=" * 60)
    print(f"Service:        {W6_SERVICE} (id={sid})")
    print(f"Incident id:    {inc_id}")
    print(f"Incident num:   {inc_num}")
    print(f"Title:          {W6_TITLE[:80]}")
    print(f"Status:         resolved")
    print(f"Urgency:        {W6_URGENCY}")
    print(f"Customer id:    {W6_CUSTOMER_ID}")
    print(f"Verify:         found={found} status={verify_status}")
    print("=" * 60)

    return 0 if inc_id and found else 1


if __name__ == "__main__":
    sys.exit(main())
