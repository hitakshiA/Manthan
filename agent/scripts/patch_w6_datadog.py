"""Patch Datadog with W6 signal - cascade-cloud auth-svc outage.

Creates:
  * Monitor: "auth-service token issuance error rate elevated"
    tagged workflow:W6-cascade-auth, incident:INC-2026-05-08-authkms,
    service:auth-service, customer_id:cus_UankGYRlc7WiW1.
  * Event: "Deploy auth-service v4.1.0 - rotated KMS signing key from
    auth-prod-2026q2 to auth-prod-2026q2-replacement"
    posted ~5 days ago, tagged service:auth-service +
    workflow:W6-cascade-auth.

Reuses auth + client + monitor pattern (w2_webhook_monitor) from
seed_datadog.py.

Run:
    .venv/bin/python scripts/patch_w6_datadog.py
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from seed_datadog import (  # noqa: E402
    HEADERS,
    REQ_SLEEP,
    SITE,
    TIMEOUT,
    EventSpec,
    MonitorSpec,
    _common_options,
    _epoch,
    _hours_ago,
    _request,
    post_event,
    upsert_monitor,
)


# ──────────────────────────────────────────────────────────────────────
# W6 config
# ──────────────────────────────────────────────────────────────────────

W6_CUSTOMER_ID = "cus_UankGYRlc7WiW1"          # Stripe id for Cascade Cloud
W6_CUSTOMER_DOMAIN = "cascade-cloud.test"

# Narrative outage timeline - baked into title/text/message because
# Datadog rejects ``date_happened`` more than ~18h in the past.
W6_OUTAGE_START_NARRATIVE = datetime(2026, 5, 8, 9, 0, 0, tzinfo=timezone.utc)
W6_OUTAGE_END_NARRATIVE = datetime(2026, 5, 22, 16, 0, 0, tzinfo=timezone.utc)
W6_DEPLOY_NARRATIVE = datetime(2026, 5, 22, 14, 30, 0, tzinfo=timezone.utc)

# Posted timestamp - Datadog rejects ``date_happened`` > ~18h in the
# past (see seed_datadog.py note). The *narrative* deploy time is 5
# days ago and is baked into the event title + text; the posted
# date_happened is recent so the event is accepted.
_DEPLOY_HOURS_AGO = 4


# ──────────────────────────────────────────────────────────────────────
# Monitor spec
# ──────────────────────────────────────────────────────────────────────


def w6_auth_monitor() -> MonitorSpec:
    """W6 monitor - auth-service token issuance error rate elevated."""
    start_iso = W6_OUTAGE_START_NARRATIVE.isoformat()
    end_iso = W6_OUTAGE_END_NARRATIVE.isoformat()
    deploy_iso = W6_DEPLOY_NARRATIVE.isoformat()
    msg = (
        "auth-service token issuance error rate elevated. Intermittent "
        f"outage between {start_iso} and {end_iso} (~15 days, "
        "intermittent throughout). Root cause: KMS rejected the active "
        "signing key `auth-prod-2026q2` whenever the worker picked the "
        "version that the rotation policy had disabled before the "
        "replacement was promoted to primary.\n\n"
        f"Primary impact: customer {W6_CUSTOMER_ID} "
        f"({W6_CUSTOMER_DOMAIN}, Cascade Cloud, Pro Annual). Their SSO "
        "+ M2M clients hit 3-7% error rates in 5-40 minute bursts. "
        "Other tenants saw smaller fractions of the same errors.\n\n"
        f"Resolved at {deploy_iso} by deploy of auth-service v4.1.0 "
        "(see related Datadog event: 'Deploy auth-service v4.1.0 - "
        "rotated KMS signing key from auth-prod-2026q2 to "
        "auth-prod-2026q2-replacement'). Linked PagerDuty incident "
        "and Sentry issue (TokenIssuanceError) carry the same "
        "workflow + incident tags.\n\n"
        "Page @platform-oncall on re-trigger."
    )
    return MonitorSpec(
        name="auth-service token issuance error rate elevated",
        type="query alert",
        query=(
            "avg(last_15m):sum:auth.token.issue.errors"
            "{service:auth-service,env:prod} > 30"
        ),
        message=msg,
        tags=[
            "env:prod",
            "team:platform",
            "service:auth-service",
            "sev:1",
            "workflow:W6-cascade-auth",
            "incident:INC-2026-05-08-authkms",
            f"customer_id:{W6_CUSTOMER_ID}",
            f"customer_domain:{W6_CUSTOMER_DOMAIN}",
            "kms_key:auth-prod-2026q2",
            "status:resolved",
            "narrative_window:2026-05-08_2026-05-22",
        ],
        options=_common_options(
            {"critical": 30, "warning": 10},
            notify_no_data=True,
            renotify_interval=15,
        ),
        note_state="Alert (resolved)",
    )


def w6_deploy_event() -> EventSpec:
    """W6 deploy event - KMS signing key rotation hotfix."""
    return EventSpec(
        title=(
            "Deploy auth-service v4.1.0 - rotated KMS signing key from "
            "auth-prod-2026q2 to auth-prod-2026q2-replacement"
        ),
        text=(
            f"Hotfix deployed at {W6_DEPLOY_NARRATIVE.isoformat()} by "
            "@platform-oncall. Rotates the active KMS signing key in "
            "auth-service from `auth-prod-2026q2` (which had been "
            "disabled by the rotation policy whenever the worker "
            "happened to pick that key version) to "
            "`auth-prod-2026q2-replacement` which is now primary.\n\n"
            f"Resolves the intermittent token issuance error spike "
            f"running from {W6_OUTAGE_START_NARRATIVE.isoformat()} "
            f"through {W6_OUTAGE_END_NARRATIVE.isoformat()} "
            f"(~15 days). Primary impact: customer {W6_CUSTOMER_ID} "
            f"({W6_CUSTOMER_DOMAIN} - Cascade Cloud, Pro Annual). "
            "Their SSO + M2M clients hit intermittent 401s/503s during "
            "the affected window.\n\n"
            "Linked monitor: 'auth-service token issuance error rate "
            "elevated' (workflow:W6-cascade-auth, "
            "incident:INC-2026-05-08-authkms). Linked Sentry issue: "
            "TokenIssuanceError on project auth-svc. Linked PagerDuty "
            "incident: auth-service KMS-rejected signing key.\n\n"
            "Rotation runbook updated to require 24h overlap before "
            "disabling the previous key version.\n\n"
            "[Note: Datadog rejects backdated events more than ~18h "
            "in the past, so this event's posted timestamp differs "
            "from the narrative deploy time above. The narrative "
            "timestamp is authoritative.]"
        ),
        date_happened=_epoch(_hours_ago(_DEPLOY_HOURS_AGO)),
        tags=[
            "service:auth-service",
            "deploy",
            "env:prod",
            "team:platform",
            "sev:1-recovery",
            "workflow:W6-cascade-auth",
            "incident:INC-2026-05-08-authkms",
            "version:v4.1.0",
            f"customer_id:{W6_CUSTOMER_ID}",
            f"customer_domain:{W6_CUSTOMER_DOMAIN}",
            "kms_key_from:auth-prod-2026q2",
            "kms_key_to:auth-prod-2026q2-replacement",
            "narrative_date:2026-05-22",
        ],
        alert_type="success",
    )


# ──────────────────────────────────────────────────────────────────────
# Verification - query back via the public API
# ──────────────────────────────────────────────────────────────────────


def verify_monitor_by_tag(
    client: httpx.Client, tag: str
) -> tuple[int, list[dict]]:
    """List monitors filtered by tag - confirm the W6 one is queryable.

    Returns (count, raw_items).
    """
    r = _request(
        client, "GET", "/api/v1/monitor",
        params={"monitor_tags": tag, "page": 0, "page_size": 50},
    )
    if r.status_code != 200:
        return 0, []
    items = r.json()
    return len(items), items


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    print("== Datadog W6 patch - cascade-cloud auth-svc outage ==")
    print(f"  site             : {SITE}")
    print(f"  customer_id      : {W6_CUSTOMER_ID}")
    print(f"  customer_domain  : {W6_CUSTOMER_DOMAIN}")
    print(
        f"  narrative outage : {W6_OUTAGE_START_NARRATIVE.isoformat()} → "
        f"{W6_OUTAGE_END_NARRATIVE.isoformat()}"
    )
    print(f"  deploy narrative : {W6_DEPLOY_NARRATIVE.isoformat()}")
    print()

    mon_spec = w6_auth_monitor()
    evt_spec = w6_deploy_event()

    monitor_id: int | None = None
    event_id: int | None = None

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # ── 1. Monitor ──
        print("[1] Upserting monitor…")
        mid, action = upsert_monitor(client, mon_spec)
        monitor_id = mid
        print(f"  [{action}] monitor id={mid}  name={mon_spec.name}")
        time.sleep(REQ_SLEEP)

        # ── 2. Event ──
        print("\n[2] Posting deploy event…")
        eid, action = post_event(client, evt_spec)
        event_id = eid
        print(f"  [{action}] event id={eid}  title={evt_spec.title[:80]}")
        time.sleep(REQ_SLEEP)

        # ── 3. Verify via tag query ──
        print("\n[3] Verifying monitor via tag query workflow:W6-cascade-auth")
        count, items = verify_monitor_by_tag(client, "workflow:W6-cascade-auth")
        print(f"  found {count} monitors with workflow:W6-cascade-auth")
        for m in items:
            print(f"    id={m.get('id')} name={m.get('name')}")

        # Also verify by direct GET
        if monitor_id:
            r = _request(client, "GET", f"/api/v1/monitor/{monitor_id}")
            if r.status_code == 200:
                m = r.json()
                tags = m.get("tags") or []
                workflow_ok = "workflow:W6-cascade-auth" in tags
                incident_ok = "incident:INC-2026-05-08-authkms" in tags
                service_ok = "service:auth-service" in tags
                print(
                    f"  direct GET monitor: workflow_ok={workflow_ok} "
                    f"incident_ok={incident_ok} service_ok={service_ok}"
                )

    print("\n" + "=" * 60)
    print("W6 DATADOG SUMMARY")
    print("=" * 60)
    print(f"Monitor id:  {monitor_id}")
    print(f"Monitor:     {mon_spec.name}")
    print(f"Event id:    {event_id}")
    print(f"Event title: {evt_spec.title[:80]}…")
    print(f"Tag verify:  {count} monitor(s) for workflow:W6-cascade-auth")
    print("=" * 60)

    return 0 if (monitor_id and event_id and count > 0) else 1


if __name__ == "__main__":
    sys.exit(main())
