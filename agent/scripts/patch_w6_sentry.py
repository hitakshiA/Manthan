"""Patch Sentry with W6 signal - cascade-cloud auth-svc outage.

Adds a new dominating issue on the existing `auth-svc` project:
  TokenIssuanceError: signing key 'auth-prod-2026q2' rejected by KMS -
  auth-service login flow degraded

Bakes ~40-60 events tagged customer_id=cus_UankGYRlc7WiW1 (cascade-cloud)
and customer_domain=cascade-cloud.test, plus a handful of noise events
tagged with unrelated customer_ids so the agent has to filter.

Reuses the auth + base client + ingestion pattern from seed_sentry.py.

Run:
    .venv/bin/python scripts/patch_w6_sentry.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import httpx
import sentry_sdk

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Reuse everything from seed_sentry - auth, HTTP client config, helpers.
from seed_sentry import (  # noqa: E402
    API_BASE,
    HEADERS,
    INGEST_SLEEP,
    ORG,
    TIMEOUT,
    _init_for_project,
    _request,
    ensure_project,
    ensure_team,
    get_project_dsn,
    list_projects,
    list_teams,
    ping_org,
)


# ──────────────────────────────────────────────────────────────────────
# W6 config - cascade-cloud auth-svc outage
# ──────────────────────────────────────────────────────────────────────

W6_CUSTOMER_ID = "cus_UankGYRlc7WiW1"          # Stripe id for Cascade Cloud
W6_CUSTOMER_DOMAIN = "cascade-cloud.test"

W6_PROJECT_SLUG = "auth-svc"
W6_PROJECT_NAME = "Auth Service"
W6_TEAM_SLUG = "platform"

W6_EXC_TYPE = "TokenIssuanceError"
W6_TITLE = (
    "TokenIssuanceError: signing key 'auth-prod-2026q2' rejected by KMS - "
    "auth-service login flow degraded"
)

# Outage window - 15 days, 2026-05-08 → 2026-05-22 (intermittent).
W6_WINDOW_START = "2026-05-08"
W6_WINDOW_END = "2026-05-22"

# Noise customer ids - totally unrelated tenants. Agent must filter these
# out when scoping to cascade-cloud.
W6_NOISE_CUSTOMER_IDS = [
    "cus_test_aurora_health",
    "cus_test_meridian_partners",
    "cus_test_horizon_genomics",
]

# Total events for the W6 fingerprint. Bulk go to cascade-cloud; a few
# noise events are sprinkled in for filter-difficulty.
W6_TOTAL_EVENTS = 52  # within the 40-60 ask
W6_NOISE_EVENT_COUNT = 3
W6_CASCADE_EVENT_COUNT = W6_TOTAL_EVENTS - W6_NOISE_EVENT_COUNT

random.seed(2026_05_27 ^ 0xCA5CADE)


# ──────────────────────────────────────────────────────────────────────
# Exception class - preserves type name in the issue title
# ──────────────────────────────────────────────────────────────────────


class TokenIssuanceError(Exception):
    """Raised by auth-service when KMS rejects the active signing key."""


# ──────────────────────────────────────────────────────────────────────
# Ingest the W6 signal
# ──────────────────────────────────────────────────────────────────────


# Distribute the cascade events across the 15-day window so the date
# spread is visible in event messages (Sentry will stamp ingestion time
# itself; we embed the narrative date in the message text).
def _narrative_date_for(i: int, total: int) -> str:
    """Pick a date inside the W6 window for event index i."""
    # Spread events across 15 days, weighted slightly to the middle.
    day = int((i / max(total - 1, 1)) * 14)  # 0..14
    return f"2026-05-{8 + day:02d}"


def _narrative_hhmm(i: int) -> str:
    """Random-ish HH:MM within business hours, deterministic per index."""
    rng = random.Random(0xC4 ^ (i * 7919))
    hh = rng.randint(8, 22)
    mm = rng.randint(0, 59)
    return f"{hh:02d}:{mm:02d}"


def ingest_w6_signal(dsn: str) -> int:
    """Ingest the W6 outage events into auth-svc.

    Returns total events ingested.
    """
    _init_for_project(dsn)

    cascade_events = 0
    noise_events = 0

    # Spread cascade events across the 15-day window. A few of them will
    # carry richer webhook/login-flow context.
    cascade_idxs_rich_context = {0, 7, 15, 24, 33, 41, 48}

    for i in range(W6_CASCADE_EVENT_COUNT):
        narrative_date = _narrative_date_for(i, W6_CASCADE_EVENT_COUNT)
        narrative_time = _narrative_hhmm(i)
        is_rich = i in cascade_idxs_rich_context

        try:
            raise TokenIssuanceError(
                f"signing key 'auth-prod-2026q2' rejected by KMS - "
                f"token issuance failed for customer {W6_CUSTOMER_ID} "
                f"(domain={W6_CUSTOMER_DOMAIN}) around "
                f"{narrative_date}T{narrative_time}Z. KMS error: "
                f"AccessDeniedException - key version disabled."
            )
        except TokenIssuanceError:
            with sentry_sdk.push_scope() as scope:
                scope.level = "error"  # type: ignore[assignment]
                # Pin fingerprint so all events group into a single issue.
                scope.fingerprint = [W6_EXC_TYPE, W6_TITLE]
                # Filterable tags - these are how the agent should
                # discover the W6/cascade-cloud link.
                scope.set_tag("service", "auth-service")
                scope.set_tag("env", "production")
                scope.set_tag("customer_id", W6_CUSTOMER_ID)
                scope.set_tag("customer_domain", W6_CUSTOMER_DOMAIN)
                scope.set_tag("kms_key_id", "auth-prod-2026q2")
                scope.set_tag("workflow", "W6-cascade-auth")
                scope.set_tag("incident", "INC-2026-05-08-authkms")
                scope.set_tag("narrative_date", narrative_date)

                if is_rich:
                    scope.set_context(
                        "login_flow",
                        {
                            "customer_id": W6_CUSTOMER_ID,
                            "customer_domain": W6_CUSTOMER_DOMAIN,
                            "endpoint": "POST /v1/oauth/token",
                            "kms_key_id": "auth-prod-2026q2",
                            "kms_error": "AccessDeniedException",
                            "narrative_window_start": W6_WINDOW_START,
                            "narrative_window_end": W6_WINDOW_END,
                            "outage_kind": "intermittent",
                        },
                    )
                    scope.set_context(
                        "kms",
                        {
                            "key_arn": (
                                "arn:aws:kms:us-east-1:000000000000:"
                                "key/auth-prod-2026q2"
                            ),
                            "operation": "Sign",
                            "rejection_reason": (
                                "key version disabled by rotation policy "
                                "- replacement key not yet promoted"
                            ),
                        },
                    )
                sentry_sdk.capture_exception()
        cascade_events += 1
        time.sleep(INGEST_SLEEP)

    # Noise events - same fingerprint so they all roll up into the same
    # issue, but tagged with unrelated customer_ids. Agent must filter by
    # customer_id=cus_UankGYRlc7WiW1 to scope correctly.
    for i in range(W6_NOISE_EVENT_COUNT):
        noise_cust = W6_NOISE_CUSTOMER_IDS[i % len(W6_NOISE_CUSTOMER_IDS)]
        narrative_date = _narrative_date_for(
            i * (W6_CASCADE_EVENT_COUNT // max(W6_NOISE_EVENT_COUNT, 1)),
            W6_CASCADE_EVENT_COUNT,
        )
        try:
            raise TokenIssuanceError(
                f"signing key 'auth-prod-2026q2' rejected by KMS - "
                f"token issuance failed for customer {noise_cust} "
                f"around {narrative_date}T{_narrative_hhmm(i * 31)}Z. "
                "(noise - unrelated tenant during same outage)"
            )
        except TokenIssuanceError:
            with sentry_sdk.push_scope() as scope:
                scope.level = "error"  # type: ignore[assignment]
                scope.fingerprint = [W6_EXC_TYPE, W6_TITLE]
                scope.set_tag("service", "auth-service")
                scope.set_tag("env", "production")
                scope.set_tag("customer_id", noise_cust)
                scope.set_tag("kms_key_id", "auth-prod-2026q2")
                scope.set_tag("workflow", "W6-cascade-auth")
                scope.set_tag("incident", "INC-2026-05-08-authkms")
                scope.set_tag("narrative_date", narrative_date)
                sentry_sdk.capture_exception()
        noise_events += 1
        time.sleep(INGEST_SLEEP)

    # Extra correlated breadcrumb messages so free-text searches for
    # the customer id or domain surface the issue.
    for breadcrumb in (
        f"auth-service token issuance failures impacting "
        f"{W6_CUSTOMER_DOMAIN} (customer {W6_CUSTOMER_ID}) - intermittent "
        f"between {W6_WINDOW_START} and {W6_WINDOW_END}",
        f"KMS Sign() rejecting auth-prod-2026q2 - degrading "
        f"login flow for {W6_CUSTOMER_ID}",
    ):
        with sentry_sdk.push_scope() as scope:
            scope.level = "error"  # type: ignore[assignment]
            scope.fingerprint = [W6_EXC_TYPE, W6_TITLE]
            scope.set_tag("service", "auth-service")
            scope.set_tag("customer_id", W6_CUSTOMER_ID)
            scope.set_tag("customer_domain", W6_CUSTOMER_DOMAIN)
            scope.set_tag("workflow", "W6-cascade-auth")
            scope.set_tag("incident", "INC-2026-05-08-authkms")
            sentry_sdk.capture_message(breadcrumb, level="error")
        time.sleep(INGEST_SLEEP)

    sentry_sdk.flush(timeout=20.0)
    return cascade_events + noise_events + 2  # +2 breadcrumb messages


# ──────────────────────────────────────────────────────────────────────
# Verification - find the W6 issue back via the API
# ──────────────────────────────────────────────────────────────────────


def verify_w6_issue(
    client: httpx.Client, *, max_wait_s: float = 90.0
) -> dict | None:
    """Poll for the W6 fingerprint to appear in the auth-svc issue list."""
    deadline = time.time() + max_wait_s
    last_count = 0
    while time.time() < deadline:
        r = _request(
            client,
            "GET",
            f"/projects/{ORG}/{W6_PROJECT_SLUG}/issues/"
            f"?query=TokenIssuanceError&limit=10",
        )
        if r.status_code == 200:
            items = r.json()
            last_count = len(items)
            for it in items:
                title = (
                    it.get("title", "")
                    + " "
                    + it.get("metadata", {}).get("value", "")
                )
                if "TokenIssuanceError" in title and "auth-prod-2026q2" in title:
                    return it
        time.sleep(3.0)
    print(f"  (verify: polled until timeout; last list had {last_count} issues)")
    return None


def count_w6_events_with_customer_tag(
    client: httpx.Client, issue_id: str
) -> int:
    """Best-effort count of W6 events tagged with the cascade customer id."""
    r = _request(
        client,
        "GET",
        f"/organizations/{ORG}/issues/{issue_id}/tags/customer_id/values/",
    )
    if r.status_code != 200:
        return -1
    for v in r.json():
        if v.get("value") == W6_CUSTOMER_ID:
            return v.get("count", 0)
    return 0


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    print("== Sentry W6 patch - cascade-cloud auth-svc outage ==")
    print(f"  customer_id    : {W6_CUSTOMER_ID}")
    print(f"  customer_domain: {W6_CUSTOMER_DOMAIN}")
    print(f"  project        : {W6_PROJECT_SLUG}")
    print(f"  window         : {W6_WINDOW_START} → {W6_WINDOW_END}")
    print()

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # 0. Sanity
        print("[0] Pinging org…")
        ping_org(client)

        # 1. Ensure team + project exist (idempotent).
        print("\n[1] Ensuring team + project")
        existing_teams = {t["slug"]: t for t in list_teams(client)}
        if W6_TEAM_SLUG not in existing_teams:
            ensure_team(client, "Platform Eng", W6_TEAM_SLUG)
        else:
            print(f"  team {W6_TEAM_SLUG!r} exists")

        existing_projects = {p["slug"]: p for p in list_projects(client)}
        if W6_PROJECT_SLUG not in existing_projects:
            ensure_project(
                client, W6_TEAM_SLUG, W6_PROJECT_NAME, W6_PROJECT_SLUG, "python"
            )
        else:
            print(f"  project {W6_PROJECT_SLUG!r} exists")

        # 2. Get DSN
        print("\n[2] Fetching DSN")
        dsn = get_project_dsn(client, W6_PROJECT_SLUG)
        print(f"  {W6_PROJECT_SLUG}: dsn ok")

        # 3. Ingest W6 events
        print(
            f"\n[3] Ingesting W6 events (~{W6_TOTAL_EVENTS} total, "
            f"{W6_NOISE_EVENT_COUNT} noise)"
        )
        n_events = ingest_w6_signal(dsn)
        print(f"  ingested {n_events} events for fingerprint {W6_EXC_TYPE}")

        # 4. Verify
        print("\n[4] Verifying issue is queryable…")
        issue = verify_w6_issue(client)

    print("\n" + "=" * 60)
    print("W6 SENTRY SUMMARY")
    print("=" * 60)
    print(f"Project:         {W6_PROJECT_SLUG}")
    print(f"Cascade events:  {W6_CASCADE_EVENT_COUNT}")
    print(f"Noise events:    {W6_NOISE_EVENT_COUNT}")
    print(f"Breadcrumbs:     2")
    print(f"Total events:    {n_events}")
    print(f"Customer id:     {W6_CUSTOMER_ID}")
    print(f"Customer domain: {W6_CUSTOMER_DOMAIN}")
    if issue:
        print()
        print(f"Sentry issue id:  {issue.get('id')}")
        print(f"Sentry short id:  {issue.get('shortId')}")
        print(f"Sentry count:     {issue.get('count')}")
        print(f"Title:            {issue.get('title', '')[:100]}")
        print(f"Permalink:        {issue.get('permalink')}")
    else:
        print()
        print("Issue not yet indexed via search; events were accepted.")
    print("=" * 60)

    return 0 if issue else 1


if __name__ == "__main__":
    sys.exit(main())
