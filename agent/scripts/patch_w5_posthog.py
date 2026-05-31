"""Patch PostHog with heavy-usage events for summit-payments (W5).

W5 = summit-payments usage-fraud REFUTE workflow. The agent's job is to
look up product analytics and see that Summit Payments is, in fact,
actively using the platform - not a fraudulent/idle account. To support
that conclusion we seed 40-50 product events scattered across the last
60 days for 3 finance personas at Summit Payments.

Reuses the auth / HTTP plumbing from seed_posthog.py.

Run:
    .venv/bin/python scripts/patch_w5_posthog.py
"""

from __future__ import annotations

import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make seed_posthog importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from seed_posthog import (  # noqa: E402
    BASE,
    PROJECT_ID,
    H_MGMT,
    TIMEOUT,
    _request,
    fetch_project_api_key,
    ingest_events,
)

import httpx  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

COMPANY_SLUG = "summit-payments"
COMPANY_NAME = "Summit Payments"
COMPANY_PLAN = "growth"
COMPANY_ARR = 84000
COMPANY_INDUSTRY = "fintech"
COMPANY_EMAIL_DOMAIN = "summit-payments.test"
COMPANY_APP_HOST = "app.summit-payments.com"

# 3 finance personas - deterministic distinct_ids so re-runs identify
# the same persons (not new ones every time).
PERSONAS = [
    {
        "distinct_id": "summit-payments-finance-1",
        "role": "analyst",
        "email": f"analyst@{COMPANY_EMAIL_DOMAIN}",
        "name": "Priya Analyst",
    },
    {
        "distinct_id": "summit-payments-finance-2",
        "role": "controller",
        "email": f"controller@{COMPANY_EMAIL_DOMAIN}",
        "name": "Marcus Controller",
    },
    {
        "distinct_id": "summit-payments-finance-3",
        "role": "ar-lead",
        "email": f"ar-lead@{COMPANY_EMAIL_DOMAIN}",
        "name": "Tomas AR Lead",
    },
]

# Event mix biased toward the kinds of events a finance team uses.
EVENT_NAMES = [
    "$pageview",
    "$pageview",
    "$pageview",  # weight $pageview heavier
    "dashboard_viewed",
    "dashboard_viewed",
    "report_exported",
    "payment_recorded",
    "payment_recorded",
    "reconciliation_completed",
    "api_key_rotated",
    "team_member_invited",
]

# Plausible app pages the finance team would hit.
APP_PAGES = [
    "/dashboard",
    "/dashboard/revenue",
    "/payments",
    "/payments/recent",
    "/reconciliation",
    "/reports",
    "/reports/monthly",
    "/settings/api-keys",
    "/settings/team",
    "/invoices",
]

random.seed(442171_05)  # deterministic-ish per re-run


# ──────────────────────────────────────────────────────────────────────
# Person construction
# ──────────────────────────────────────────────────────────────────────


def _person_set_props(persona: dict) -> dict:
    """The $set block PostHog uses to identify/update the Person."""
    return {
        "$set": {
            "email": persona["email"],
            "name": persona["name"],
            "company": COMPANY_NAME,
            "company_slug": COMPANY_SLUG,
            "plan": COMPANY_PLAN,
            "arr_usd": COMPANY_ARR,
            "industry": COMPANY_INDUSTRY,
            "country": "USA",
            "role": persona["role"],
            "team": "finance",
            # Marker so we can identify W5-seeded persons later.
            "seeded_by": "patch_w5_posthog",
        },
        "$set_once": {
            "first_seen": "2024-04-10T09:00:00Z",
            "signup_year": 2024,
        },
    }


def build_identify_events() -> list[dict]:
    """One $identify per persona - creates / updates the Person row."""
    # Anchor 60 days back so $identify timestamp predates the activity.
    anchor = datetime.now(timezone.utc) - timedelta(days=60, hours=1)
    out: list[dict] = []
    for p in PERSONAS:
        out.append({
            "event": "$identify",
            "distinct_id": p["distinct_id"],
            "properties": {
                **_person_set_props(p),
                "$lib": "manthan-w5-patch",
            },
            "timestamp": anchor.isoformat(),
        })
    return out


def build_activity_events(target_count: int = 45) -> list[dict]:
    """Scatter ~45 events across personas + the last 60 days."""
    now = datetime.now(timezone.utc)
    events: list[dict] = []

    # Pre-compute 45 timestamps spread across the 60-day window.
    # Use a sampling that avoids clustering by ensuring each event lands
    # in a distinct ~1.3-day-wide bucket, then jittered.
    buckets = target_count
    bucket_width_hours = (60 * 24) / buckets
    for i in range(target_count):
        # Bucket center, then jitter +/- half a bucket.
        center_hours_ago = (i + 0.5) * bucket_width_hours
        jitter = random.uniform(
            -bucket_width_hours / 2, bucket_width_hours / 2
        )
        hours_ago = max(0.5, center_hours_ago + jitter)
        ts = now - timedelta(hours=hours_ago)

        persona = random.choice(PERSONAS)
        event_name = random.choice(EVENT_NAMES)
        page = random.choice(APP_PAGES)

        props: dict = {
            "company_slug": COMPANY_SLUG,
            "company": COMPANY_NAME,
            "plan": COMPANY_PLAN,
            "$lib": "manthan-w5-patch",
            "seed_batch": "w5_summit_payments",
        }

        if event_name == "$pageview":
            props["$current_url"] = f"https://{COMPANY_APP_HOST}{page}"
            props["$host"] = COMPANY_APP_HOST
            props["$pathname"] = page
        elif event_name == "dashboard_viewed":
            props["dashboard_name"] = random.choice(
                ["Revenue Overview", "Payments Today", "AR Aging"]
            )
        elif event_name == "report_exported":
            props["report_type"] = random.choice(
                ["monthly_revenue", "transaction_log", "reconciliation"]
            )
            props["format"] = random.choice(["csv", "xlsx", "pdf"])
        elif event_name == "payment_recorded":
            props["amount_usd"] = round(random.uniform(120, 9800), 2)
            props["payment_method"] = random.choice(
                ["ach", "wire", "card"]
            )
        elif event_name == "reconciliation_completed":
            props["records_matched"] = random.randint(40, 480)
            props["records_unmatched"] = random.randint(0, 5)
        elif event_name == "api_key_rotated":
            props["key_label"] = random.choice(
                ["production", "staging", "webhook-signing"]
            )
        elif event_name == "team_member_invited":
            props["invitee_role"] = random.choice(
                ["analyst", "viewer", "ops"]
            )

        events.append({
            "event": event_name,
            "distinct_id": persona["distinct_id"],
            "properties": props,
            "timestamp": ts.isoformat(),
        })

    return events


# ──────────────────────────────────────────────────────────────────────
# Verification via PostHog query API
# ──────────────────────────────────────────────────────────────────────


def verify_count(client: httpx.Client) -> int | None:
    """Verify ingestion. Tries HogQL → /events/ → /persons/ fallback.

    The personal key in this env only has `persons:read` scope (not
    `query:read`), so HogQL & /events/ both return 403. We fall back to
    confirming the personas exist and that their `last_seen_at` /
    `created_at` lie within our 60-day window - which only happens if
    events landed (PostHog updates last_seen_at off event timestamps).
    """
    # Path 1: HogQL.
    hogql = (
        "SELECT count() FROM events "
        f"WHERE properties.company_slug = '{COMPANY_SLUG}' "
        "AND timestamp > now() - INTERVAL 60 DAY"
    )
    payload = {"query": {"kind": "HogQLQuery", "query": hogql}}
    r = _request(
        client, "POST",
        f"/api/projects/{PROJECT_ID}/query/",
        json=payload,
    )
    if r.status_code == 200:
        data = r.json()
        results = data.get("results") or data.get("result") or []
        if results and isinstance(results, list) and results[0]:
            first = results[0]
            if isinstance(first, (list, tuple)) and first:
                return int(first[0])
            if isinstance(first, (int, float)):
                return int(first)
        print(f"  unexpected query shape: {str(data)[:300]}")
        return None
    print(
        f"  HogQL query unavailable ({r.status_code}); "
        "falling back to /persons/ verification (query:read scope missing)"
    )

    # Path 2: confirm persons + their last_seen_at proves event landing.
    r = _request(
        client, "GET",
        f"/api/projects/{PROJECT_ID}/persons/",
        params={"search": COMPANY_SLUG},
    )
    if r.status_code != 200:
        print(f"  /persons/ failed: {r.status_code} {r.text[:200]}")
        return None
    persons = [
        p for p in r.json().get("results", [])
        if p.get("properties", {}).get("seeded_by") == "patch_w5_posthog"
    ]
    if not persons:
        print("  no W5-seeded persons found yet")
        return None
    print(f"  W5 persons present: {len(persons)}")
    for p in persons:
        dids = p.get("distinct_ids", [])
        ls = p.get("last_seen_at")
        props = p.get("properties", {})
        print(
            f"    {dids[0]}  last_seen={ls}  "
            f"plan={props.get('plan')}  arr={props.get('arr_usd')}"
        )
    # We can't get the exact count without query scope; return None and
    # let the caller treat "persons present + ingest success" as proof.
    return None


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print("═" * 70)
    print(f"W5 PostHog patch - {COMPANY_SLUG}")
    print("═" * 70)

    with httpx.Client(headers=H_MGMT, timeout=TIMEOUT) as client:
        # 1. Get project API token (phc_…) for the /batch/ endpoint.
        project_key = fetch_project_api_key(client)
        if not project_key:
            sys.exit(
                "ERROR: could not fetch project api_token from "
                f"/api/projects/{PROJECT_ID}/ - check POSTHOG_API_KEY scopes"
            )
        print(f"project key: {project_key[:8]}…")

        # 2. Build events.
        identify_events = build_identify_events()
        activity_events = build_activity_events(target_count=45)
        all_events = identify_events + activity_events
        print(
            f"persons: {len(PERSONAS)}  "
            f"identify_events: {len(identify_events)}  "
            f"activity_events: {len(activity_events)}  "
            f"total: {len(all_events)}"
        )

        # 3. Distribute across the 60-day window - sanity print.
        days = sorted({
            datetime.fromisoformat(e["timestamp"]).date()
            for e in activity_events
        })
        print(
            f"activity spans {len(days)} distinct calendar days "
            f"({days[0]} … {days[-1]})"
        )

        # 4. Send.
        print("\nIngesting…")
        sent, errs = ingest_events(client, all_events, project_key)
        print(f"  sent: {sent}  errors: {errs}")

        # 5. Verify (after a short sleep - ingestion is async).
        print("\nWaiting 12s for PostHog ingestion pipeline…")
        time.sleep(12)
        count = verify_count(client)
        if count is None:
            print("  verify: UNAVAILABLE (query failed)")
        else:
            print(f"  verify: {count} events for company_slug='{COMPANY_SLUG}' in last 60d")

        # 6. Final report.
        print("\n" + "═" * 70)
        print("SUMMARY")
        print("═" * 70)
        print(f"Company       : {COMPANY_NAME} ({COMPANY_SLUG})")
        print(f"Personas      : {len(PERSONAS)}")
        for p in PERSONAS:
            print(f"  - {p['distinct_id']}  <{p['email']}>")
        print(f"Events sent   : {sent}")
        print(f"Errors        : {errs}")
        if count is not None:
            ok = "OK" if count >= 40 else "BELOW THRESHOLD"
            print(f"Queryable now : {count}  [{ok} >= 40]")
        else:
            print("Queryable now : <unknown - verify failed>")

        # Sample
        sample = [e["distinct_id"] for e in activity_events[:5]]
        print(f"Sample d_ids  : {sample}")


if __name__ == "__main__":
    main()
