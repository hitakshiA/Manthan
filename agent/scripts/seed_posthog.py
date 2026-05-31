"""Seed PostHog (project 442171, us.posthog.com) for the Manthan agent.

Coral's PostHog source exposes analytics METADATA (insights, dashboards,
feature flags, cohorts, surveys) - not raw events. So this script focuses
on management-API artifacts first, and ingests events as a "future use"
bonus when the project API key is available.

Workflow signals baked into the analytics layer:

  W1 - Acme daisy disputes
       Cohort "Customers with multiple disputes" containing Acme
       Insight "Refund rate by company - Acme outlier"

  W2 - Northwind webhook crash
       Feature flag `enterprise_dashboard_v2` (enabled, rollout 100%)
         - Northwind's stuck-on-Standard issue is this flag's eval failing
       Insight "Webhook delivery failures by hour" - May 2026 spike
       Dashboard "Engineering - Webhook Reliability" pointing at the above

  W3 - Mockingbird legacy billing migration
       Feature flag `legacy_billing_entity_deprecated` (50% rollout)
       Insight "Customers on dual billing entities" - points at Mockingbird

Idempotent: searches by name/key before creating each artifact.

Run:
    .venv/bin/python scripts/seed_posthog.py
"""

from __future__ import annotations

import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Make seed_world importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from seed_world import COMPANIES, WORKFLOWS, Company  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

PERSONAL_KEY = os.getenv("POSTHOG_API_KEY")
BASE = os.getenv("POSTHOG_API_BASE", "https://us.posthog.com").rstrip("/")
PROJECT_ID = 442171

if not PERSONAL_KEY:
    sys.exit("ERROR: POSTHOG_API_KEY missing from .env")

# Personal key - for management API (Bearer header).
H_MGMT: dict[str, str] = {
    "Authorization": f"Bearer {PERSONAL_KEY}",
    "Content-Type": "application/json",
}

# PostHog has generous rate limits but we still throttle a bit to be safe.
REQ_SLEEP = 0.08
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Reproducible randomness.
random.seed(442171)


# ──────────────────────────────────────────────────────────────────────
# HTTP wrapper with auto-throttling + retry
# ──────────────────────────────────────────────────────────────────────


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: Any | None = None,
    params: dict | None = None,
    retries: int = 3,
) -> httpx.Response:
    url = path if path.startswith("http") else f"{BASE}{path}"
    last: httpx.Response | None = None
    for attempt in range(retries):
        r = client.request(method, url, json=json, params=params)
        last = r
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", "1.0"))
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        return r
    assert last is not None
    return last


# ──────────────────────────────────────────────────────────────────────
# List-all helper (pagination)
# ──────────────────────────────────────────────────────────────────────


def list_all(
    client: httpx.Client, path: str, *, limit_per_page: int = 200
) -> list[dict]:
    """Page through a PostHog list endpoint and return all results."""
    out: list[dict] = []
    next_url: str | None = (
        f"{BASE}{path}"
        if not path.startswith("http")
        else path
    )
    if next_url and "?" not in next_url:
        next_url = f"{next_url}?limit={limit_per_page}"
    while next_url:
        r = _request(client, "GET", next_url)
        if r.status_code != 200:
            print(f"  list_all failed {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        out.extend(data.get("results", []))
        next_url = data.get("next")
        # PostHog returns absolute URLs in 'next' - pass through.
    return out


# ──────────────────────────────────────────────────────────────────────
# Project API key (for event ingestion)
# ──────────────────────────────────────────────────────────────────────


def fetch_project_api_key(client: httpx.Client) -> str | None:
    """Return the project's API token (phc_...) for event ingestion."""
    r = _request(client, "GET", f"/api/projects/{PROJECT_ID}/")
    if r.status_code != 200:
        return None
    return r.json().get("api_token")


# ──────────────────────────────────────────────────────────────────────
# Insights
# ──────────────────────────────────────────────────────────────────────

# Helpful wrappers around the modern PostHog "query" format. Coral
# reads the metadata (name/description/query.kind/series), so any valid
# query that round-trips through the API is fine - we don't need the
# numbers to render to anything specific.


def _trends(events: list[dict], interval: str = "day") -> dict:
    return {
        "kind": "InsightVizNode",
        "source": {
            "kind": "TrendsQuery",
            "series": events,
            "interval": interval,
        },
    }


def _funnel(events: list[dict]) -> dict:
    return {
        "kind": "InsightVizNode",
        "source": {
            "kind": "FunnelsQuery",
            "series": events,
            "interval": "day",
        },
    }


def _events(*names: str) -> list[dict]:
    return [{"kind": "EventsNode", "event": n, "name": n} for n in names]


# Full list of insights we seed. Order matters - workflow-signal
# insights are at the start so they appear high in any UI listing.
INSIGHT_SPECS: list[dict] = [
    # ── Workflow-signal insights (must succeed) ──
    {
        "name": "Refund rate by company - Acme outlier",  # W1
        "description": (
            "Tracks per-company refund rate. Acme Genomics shows 3x the "
            "median over the last 8 months - flagged for pattern review "
            "(daisy-chained chargebacks)."
        ),
        "query": _trends(_events("refund_issued"), interval="month"),
        "tags": ["billing", "disputes", "w1", "acme-genomics"],
    },
    {
        "name": "Disputes filed per customer (rolling 12 months)",  # W1
        "description": (
            "Rolling 12-month dispute count grouped by customer. "
            "Customers with 2+ in the window are candidates for the "
            "'multiple disputes' cohort."
        ),
        "query": _trends(_events("dispute_filed"), interval="month"),
        "tags": ["billing", "disputes", "w1"],
    },
    {
        "name": "Webhook delivery failures by hour",  # W2
        "description": (
            "invoice.payment_succeeded webhook handler exceptions. "
            "Major spike on 2026-05-08 around 14:00 UTC - handler "
            "crashed on enterprise tier evaluation, leaving customers "
            "paid-but-not-entitled (Northwind impact)."
        ),
        "query": _trends(
            _events("webhook_delivery_failed"), interval="hour"
        ),
        "tags": ["engineering", "webhooks", "w2", "northwind"],
    },
    {
        "name": "Entitlement mismatch: paid vs tier",  # W2
        "description": (
            "Customers where stripe.customer.subscription.plan != "
            "entitlement_table.tier. Northwind shows up here as "
            "'Paid Enterprise, Granted Standard' since the May 8 "
            "webhook crash."
        ),
        "query": _trends(
            _events("entitlement_mismatch_detected"), interval="day"
        ),
        "tags": ["engineering", "billing", "w2", "northwind"],
    },
    {
        "name": "Customers on dual billing entities",  # W3
        "description": (
            "Customers with active subscriptions in BOTH the legacy "
            "billing system and Stripe. Should be 0 after the March 2026 "
            "migration cutover - Mockingbird Media is the outlier."
        ),
        "query": _trends(
            _events("dual_billing_detected"), interval="week"
        ),
        "tags": ["billing", "migration", "w3", "mockingbird"],
    },
    {
        "name": "Legacy billing entity - active subscriptions",  # W3
        "description": (
            "Subscriptions still active on the legacy billing entity "
            "that was supposed to be deprecated at end-of-March 2026. "
            "Trend should be flat-zero; spikes indicate migration "
            "regressions."
        ),
        "query": _trends(
            _events("legacy_subscription_charged"), interval="day"
        ),
        "tags": ["billing", "migration", "w3"],
    },
    # ── Realistic spread (engineering + product + finance) ──
    {
        "name": "Daily Active Users",
        "description": "DAU across all plans, last 30 days.",
        "query": _trends(_events("$pageview")),
        "tags": ["product", "growth"],
    },
    {
        "name": "Daily Active Users by Plan",
        "description": (
            "DAU broken out by subscription plan. Trial users tracked "
            "separately."
        ),
        "query": _trends(_events("$pageview")),
        "tags": ["product", "growth"],
    },
    {
        "name": "Weekly Active Users by Plan",
        "description": "WAU by plan tier - Standard / Pro / Enterprise.",
        "query": _trends(_events("$pageview"), interval="week"),
        "tags": ["product"],
    },
    {
        "name": "Monthly Active Users",
        "description": "MAU rolling.",
        "query": _trends(_events("$pageview"), interval="month"),
        "tags": ["product"],
    },
    {
        "name": "Funnel: Signup → Activation",
        "description": (
            "New user funnel: signup_completed → first_dashboard_view → "
            "first_export."
        ),
        "query": _funnel(
            _events(
                "signup_completed",
                "first_dashboard_view",
                "first_export",
            )
        ),
        "tags": ["product", "activation"],
    },
    {
        "name": "Funnel: Trial → Paid Conversion",
        "description": (
            "Trial-to-paid conversion: trial_started → plan_selected → "
            "checkout_completed."
        ),
        "query": _funnel(
            _events(
                "trial_started",
                "plan_selected",
                "checkout_completed",
            )
        ),
        "tags": ["finance", "growth"],
    },
    {
        "name": "Stripe checkout conversion",
        "description": (
            "Conversion through the Stripe Checkout flow: opened → "
            "succeeded."
        ),
        "query": _funnel(
            _events(
                "stripe_checkout_opened",
                "stripe_checkout_succeeded",
            )
        ),
        "tags": ["finance", "billing"],
    },
    {
        "name": "Feature Adoption: Enterprise Dashboard",
        "description": (
            "How many Enterprise customers have opened the new "
            "dashboard at least once."
        ),
        "query": _trends(_events("enterprise_dashboard_viewed")),
        "tags": ["product", "enterprise"],
    },
    {
        "name": "Feature Adoption: Pro Export Formats",
        "description": (
            "Adoption of Pro-tier export formats (xlsx, parquet)."
        ),
        "query": _trends(_events("export_completed")),
        "tags": ["product", "pro"],
    },
    {
        "name": "Retention by signup cohort",
        "description": "Weekly retention curve segmented by signup month.",
        "query": _trends(_events("$pageview"), interval="week"),
        "tags": ["product", "retention"],
    },
    {
        "name": "Webhook delivery success rate",
        "description": (
            "Overall webhook health: successful deliveries / total. "
            "Should be > 99.5%."
        ),
        "query": _trends(_events("webhook_delivered")),
        "tags": ["engineering", "webhooks"],
    },
    {
        "name": "API request volume by endpoint",
        "description": "Daily request count broken out by route.",
        "query": _trends(_events("api_request"), interval="day"),
        "tags": ["engineering"],
    },
    {
        "name": "Error rate by service",
        "description": "5xx + uncaught exceptions per service per hour.",
        "query": _trends(_events("server_error"), interval="hour"),
        "tags": ["engineering"],
    },
    {
        "name": "Churn signals - last login age",
        "description": (
            "Customers whose last_login is > 30 days. Pre-churn signal."
        ),
        "query": _trends(_events("$pageview"), interval="week"),
        "tags": ["customer-success"],
    },
    {
        "name": "MRR by plan",
        "description": "Monthly recurring revenue split by plan tier.",
        "query": _trends(_events("subscription_renewed"), interval="month"),
        "tags": ["finance"],
    },
    {
        "name": "Dispute volume by month",
        "description": (
            "Total disputes filed per month across all customers."
        ),
        "query": _trends(_events("dispute_filed"), interval="month"),
        "tags": ["finance", "disputes"],
    },
    {
        "name": "Time-to-resolution: Support tickets",
        "description": (
            "Median + p90 minutes from ticket_opened to ticket_resolved."
        ),
        "query": _trends(_events("ticket_resolved")),
        "tags": ["support"],
    },
]


def _slugify_name(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_")


def upsert_insight(
    client: httpx.Client,
    spec: dict,
    existing_by_name: dict[str, int],
) -> tuple[int | None, str]:
    name = spec["name"]
    payload = {
        "name": name,
        "description": spec.get("description", ""),
        "query": spec["query"],
        "tags": spec.get("tags", []),
        "saved": True,
    }
    if name in existing_by_name:
        iid = existing_by_name[name]
        r = _request(
            client, "PATCH",
            f"/api/projects/{PROJECT_ID}/insights/{iid}/",
            json=payload,
        )
        if r.status_code in (200, 201):
            return iid, "updated"
        return iid, f"error-update-{r.status_code}: {r.text[:200]}"
    r = _request(
        client, "POST",
        f"/api/projects/{PROJECT_ID}/insights/",
        json=payload,
    )
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    return None, f"error-create-{r.status_code}: {r.text[:200]}"


# ──────────────────────────────────────────────────────────────────────
# Feature flags
# ──────────────────────────────────────────────────────────────────────

# A flag specification. `active` controls "Active" toggle.
# `rollout` is the rollout percentage for the default everyone-group.
FLAG_SPECS: list[dict] = [
    # ── Workflow-signal flags ──
    {
        "key": "enterprise_dashboard_v2",
        "name": "Enterprise Dashboard v2",
        "description": (
            "Gate for the new Enterprise dashboard. Northwind Logistics "
            "is supposed to be receiving it after upgrading; the May 8 "
            "webhook crash broke the flag-evaluation path for their "
            "tenant. Related to W2."
        ),
        "active": True,
        "rollout": 100,
        "tags": ["enterprise", "w2", "northwind"],
    },
    {
        "key": "legacy_billing_entity_deprecated",
        "name": "Legacy billing entity deprecated",
        "description": (
            "When ON, charges are routed exclusively through Stripe; the "
            "legacy entity should not bill. Rollout still in progress - "
            "Mockingbird Media is in the non-deprecated bucket due to a "
            "migration miss. Related to W3."
        ),
        "active": True,
        "rollout": 50,
        "tags": ["billing", "migration", "w3", "mockingbird"],
    },
    {
        "key": "webhook_handler_v2",
        "name": "Webhook handler v2",
        "description": (
            "Switches invoice.payment_succeeded handler to the new "
            "retry-aware implementation. Was rolled back after the May 8 "
            "crash. Related to W2."
        ),
        "active": False,
        "rollout": 0,
        "tags": ["engineering", "webhooks", "w2"],
    },
    # ── Realistic noise flags ──
    {
        "key": "pro_export_formats",
        "name": "Pro export formats (xlsx, parquet)",
        "description": "Enables xlsx + parquet exports for Pro plan customers.",
        "active": True,
        "rollout": 100,
        "tags": ["pro", "exports"],
    },
    {
        "key": "multi_tenant_billing",
        "name": "Multi-tenant billing",
        "description": (
            "Lets a single organization manage billing for multiple "
            "workspaces. Beta rollout."
        ),
        "active": True,
        "rollout": 25,
        "tags": ["billing", "enterprise"],
    },
    {
        "key": "new_dispute_resolution_ui",
        "name": "New dispute resolution UI",
        "description": (
            "Internal UI for AR team to triage disputes faster."
        ),
        "active": True,
        "rollout": 100,
        "tags": ["internal", "disputes"],
    },
    {
        "key": "sso_saml",
        "name": "SSO SAML support",
        "description": "SAML SSO availability for Enterprise customers.",
        "active": True,
        "rollout": 100,
        "tags": ["enterprise", "security"],
    },
    {
        "key": "audit_log_retention_365d",
        "name": "Audit log retention - 365 days",
        "description": (
            "Extends audit log retention to 365 days for Enterprise."
        ),
        "active": True,
        "rollout": 100,
        "tags": ["enterprise", "compliance"],
    },
    {
        "key": "ai_summary_beta",
        "name": "AI summary (beta)",
        "description": "Auto-generated summaries on dashboards.",
        "active": True,
        "rollout": 10,
        "tags": ["ai", "beta"],
    },
    {
        "key": "stripe_link_payments",
        "name": "Stripe Link payments",
        "description": "Faster checkout via Stripe Link.",
        "active": True,
        "rollout": 80,
        "tags": ["billing"],
    },
    {
        "key": "intercom_v2_chat",
        "name": "Intercom v2 chat widget",
        "description": "New chat widget - A/B against the old one.",
        "active": False,
        "rollout": 0,
        "tags": ["support"],
    },
    {
        "key": "background_jobs_v3",
        "name": "Background jobs v3 (Sidekiq → Temporal)",
        "description": "Migrate background workers from Sidekiq to Temporal.",
        "active": True,
        "rollout": 20,
        "tags": ["engineering"],
    },
    {
        "key": "csv_streaming_export",
        "name": "Streaming CSV export",
        "description": "Stream CSV export for large datasets.",
        "active": True,
        "rollout": 100,
        "tags": ["exports"],
    },
]


def upsert_flag(
    client: httpx.Client,
    spec: dict,
    existing_by_key: dict[str, int],
) -> tuple[int | None, str]:
    payload = {
        "key": spec["key"],
        "name": spec["name"],
        "active": spec["active"],
        "filters": {
            "groups": [
                {
                    "properties": [],
                    "rollout_percentage": spec["rollout"],
                }
            ]
        },
        "tags": spec.get("tags", []),
    }
    desc = spec.get("description", "")
    if desc:
        # PostHog feature flag model doesn't have description on create,
        # but it does accept it on PATCH. We send it both ways anyway.
        payload["description"] = desc

    key = spec["key"]
    if key in existing_by_key:
        fid = existing_by_key[key]
        r = _request(
            client, "PATCH",
            f"/api/projects/{PROJECT_ID}/feature_flags/{fid}/",
            json=payload,
        )
        if r.status_code in (200, 201):
            return fid, "updated"
        return fid, f"error-update-{r.status_code}: {r.text[:200]}"
    r = _request(
        client, "POST",
        f"/api/projects/{PROJECT_ID}/feature_flags/",
        json=payload,
    )
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    return None, f"error-create-{r.status_code}: {r.text[:200]}"


# ──────────────────────────────────────────────────────────────────────
# Dashboards
# ──────────────────────────────────────────────────────────────────────

DASHBOARD_SPECS: list[dict] = [
    {
        "name": "Engineering - Webhook Reliability",  # W2
        "description": (
            "Webhook delivery health, retry queue depth, and exception "
            "rate. Surfaced the May 2026 invoice.payment_succeeded "
            "crash that left Northwind Logistics stuck on Standard."
        ),
        "tags": ["engineering", "w2"],
        # Names of insights to attach as tiles (must already exist).
        "tile_insight_names": [
            "Webhook delivery failures by hour",
            "Webhook delivery success rate",
            "Entitlement mismatch: paid vs tier",
            "Error rate by service",
        ],
    },
    {
        "name": "Finance - Conversion",
        "description": (
            "Trial → paid funnel, checkout conversion, MRR, dispute "
            "volume."
        ),
        "tags": ["finance"],
        "tile_insight_names": [
            "Funnel: Trial → Paid Conversion",
            "Stripe checkout conversion",
            "MRR by plan",
            "Dispute volume by month",
        ],
    },
    {
        "name": "Product - Activation",
        "description": (
            "Activation funnel + feature adoption for new signups."
        ),
        "tags": ["product"],
        "tile_insight_names": [
            "Funnel: Signup → Activation",
            "Feature Adoption: Enterprise Dashboard",
            "Feature Adoption: Pro Export Formats",
            "Daily Active Users",
            "Retention by signup cohort",
        ],
    },
    {
        "name": "Customer Health",
        "description": (
            "Per-customer churn risk + dispute pattern. Acme Genomics "
            "outlier surfaces here (W1 signal)."
        ),
        "tags": ["customer-success", "w1"],
        "tile_insight_names": [
            "Churn signals - last login age",
            "Refund rate by company - Acme outlier",
            "Disputes filed per customer (rolling 12 months)",
            "Time-to-resolution: Support tickets",
        ],
    },
    {
        "name": "Billing - Migration Tracking",  # W3
        "description": (
            "Tracks the legacy billing → Stripe migration that finished "
            "March 2026. Surfaces dual-billing regressions like the "
            "Mockingbird Media case."
        ),
        "tags": ["billing", "w3"],
        "tile_insight_names": [
            "Customers on dual billing entities",
            "Legacy billing entity - active subscriptions",
            "MRR by plan",
        ],
    },
]


def upsert_dashboard(
    client: httpx.Client,
    spec: dict,
    existing_by_name: dict[str, int],
) -> tuple[int | None, str]:
    payload = {
        "name": spec["name"],
        "description": spec.get("description", ""),
        "tags": spec.get("tags", []),
    }
    name = spec["name"]
    if name in existing_by_name:
        did = existing_by_name[name]
        r = _request(
            client, "PATCH",
            f"/api/projects/{PROJECT_ID}/dashboards/{did}/",
            json=payload,
        )
        if r.status_code in (200, 201):
            return did, "updated"
        return did, f"error-update-{r.status_code}: {r.text[:200]}"
    r = _request(
        client, "POST",
        f"/api/projects/{PROJECT_ID}/dashboards/",
        json=payload,
    )
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    return None, f"error-create-{r.status_code}: {r.text[:200]}"


def attach_insights_to_dashboard(
    client: httpx.Client,
    dashboard_id: int,
    insight_ids: list[int],
) -> int:
    """Add each insight to a dashboard via PATCH on the insight.

    The cleanest way to wire an insight to a dashboard via the
    management API is to PATCH the insight with `dashboards: [id, ...]`.
    Returns the number of insights successfully attached.
    """
    attached = 0
    for iid in insight_ids:
        # Fetch existing dashboards on the insight so we don't drop other
        # associations on update.
        r = _request(
            client, "GET",
            f"/api/projects/{PROJECT_ID}/insights/{iid}/",
        )
        if r.status_code != 200:
            continue
        cur = r.json().get("dashboards") or []
        if dashboard_id in cur:
            attached += 1
            continue
        cur = list(set(cur + [dashboard_id]))
        r2 = _request(
            client, "PATCH",
            f"/api/projects/{PROJECT_ID}/insights/{iid}/",
            json={"dashboards": cur},
        )
        if r2.status_code in (200, 201):
            attached += 1
    return attached


# ──────────────────────────────────────────────────────────────────────
# Cohorts
# ──────────────────────────────────────────────────────────────────────

# Static cohort approach: build by static distinct_id list. PostHog
# accepts `is_static: true` cohorts; we then POST distinct_ids to
# /cohorts/{id}/persons/ to populate them (or skip population if events
# aren't ingested).
#
# Dynamic cohorts use `filters` with property predicates. We use dynamic
# for filters that should "live" (e.g. "Active customers Q2 2026").
COHORT_SPECS: list[dict] = [
    {
        "name": "Customers with multiple disputes",  # W1
        "description": (
            "Customers who have filed 2+ disputes in the rolling "
            "12-month window. Acme Genomics is the headline outlier."
        ),
        "is_static": False,
        "filters": {
            "properties": {
                "type": "AND",
                "values": [
                    {
                        "type": "AND",
                        "values": [
                            {
                                "key": "dispute_count_12mo",
                                "type": "person",
                                "value": "2",
                                "operator": "gte",
                            }
                        ],
                    }
                ],
            }
        },
        "tags": ["disputes", "w1"],
    },
    {
        "name": "Customers stuck on wrong plan",  # W2
        "description": (
            "Customers whose paid Stripe plan disagrees with their "
            "entitlement_table tier. Northwind Logistics is here due to "
            "the May 8 webhook crash."
        ),
        "is_static": False,
        "filters": {
            "properties": {
                "type": "AND",
                "values": [
                    {
                        "type": "AND",
                        "values": [
                            {
                                "key": "entitlement_mismatch",
                                "type": "person",
                                "value": ["true"],
                                "operator": "exact",
                            }
                        ],
                    }
                ],
            }
        },
        "tags": ["entitlement", "w2"],
    },
    {
        "name": "Customers on dual billing entities",  # W3
        "description": (
            "Customers still being charged by both Stripe and the "
            "legacy billing entity after the March 2026 migration. "
            "Mockingbird Media is the canonical case."
        ),
        "is_static": False,
        "filters": {
            "properties": {
                "type": "AND",
                "values": [
                    {
                        "type": "AND",
                        "values": [
                            {
                                "key": "has_legacy_subscription",
                                "type": "person",
                                "value": ["true"],
                                "operator": "exact",
                            },
                            {
                                "key": "has_stripe_subscription",
                                "type": "person",
                                "value": ["true"],
                                "operator": "exact",
                            },
                        ],
                    }
                ],
            }
        },
        "tags": ["billing", "migration", "w3"],
    },
    # ── Realistic noise cohorts ──
    {
        "name": "Active customers Q2 2026",
        "description": "Customers active in Q2 2026 (April–June).",
        "is_static": False,
        "filters": {
            "properties": {
                "type": "AND",
                "values": [
                    {
                        "type": "AND",
                        "values": [
                            {
                                "key": "plan",
                                "type": "person",
                                "value": [
                                    "Pro Annual",
                                    "Enterprise Annual",
                                    "Standard Monthly",
                                ],
                                "operator": "exact",
                            }
                        ],
                    }
                ],
            }
        },
        "tags": ["customer-success"],
    },
    {
        "name": "Trial users",
        "description": "Currently on a trial plan, no paid conversion yet.",
        "is_static": False,
        "filters": {
            "properties": {
                "type": "AND",
                "values": [
                    {
                        "type": "AND",
                        "values": [
                            {
                                "key": "plan",
                                "type": "person",
                                "value": ["Trial"],
                                "operator": "exact",
                            }
                        ],
                    }
                ],
            }
        },
        "tags": ["growth"],
    },
    {
        "name": "Enterprise customers",
        "description": "Active Enterprise-tier subscriptions.",
        "is_static": False,
        "filters": {
            "properties": {
                "type": "AND",
                "values": [
                    {
                        "type": "AND",
                        "values": [
                            {
                                "key": "plan",
                                "type": "person",
                                "value": ["Enterprise Annual"],
                                "operator": "exact",
                            }
                        ],
                    }
                ],
            }
        },
        "tags": ["enterprise"],
    },
    {
        "name": "Yellow / Red health customers",
        "description": (
            "Customers flagged yellow or red by the CSM team. Watch "
            "list for renewal risk."
        ),
        "is_static": False,
        "filters": {
            "properties": {
                "type": "AND",
                "values": [
                    {
                        "type": "AND",
                        "values": [
                            {
                                "key": "health",
                                "type": "person",
                                "value": ["yellow", "red"],
                                "operator": "exact",
                            }
                        ],
                    }
                ],
            }
        },
        "tags": ["customer-success"],
    },
    {
        "name": "Churning - Q2 2026",
        "description": "Customers with cancel-intent signals in Q2 2026.",
        "is_static": False,
        "filters": {
            "properties": {
                "type": "AND",
                "values": [
                    {
                        "type": "AND",
                        "values": [
                            {
                                "key": "cancel_intent",
                                "type": "person",
                                "value": ["true"],
                                "operator": "exact",
                            }
                        ],
                    }
                ],
            }
        },
        "tags": ["customer-success", "churn"],
    },
]


def upsert_cohort(
    client: httpx.Client,
    spec: dict,
    existing_by_name: dict[str, int],
) -> tuple[int | None, str]:
    payload = {
        "name": spec["name"],
        "description": spec.get("description", ""),
        "is_static": spec.get("is_static", False),
        "filters": spec.get("filters", {}),
        "tags": spec.get("tags", []),
    }
    name = spec["name"]
    if name in existing_by_name:
        cid = existing_by_name[name]
        r = _request(
            client, "PATCH",
            f"/api/projects/{PROJECT_ID}/cohorts/{cid}/",
            json=payload,
        )
        if r.status_code in (200, 201):
            return cid, "updated"
        return cid, f"error-update-{r.status_code}: {r.text[:200]}"
    r = _request(
        client, "POST",
        f"/api/projects/{PROJECT_ID}/cohorts/",
        json=payload,
    )
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    return None, f"error-create-{r.status_code}: {r.text[:200]}"


# ──────────────────────────────────────────────────────────────────────
# Surveys
# ──────────────────────────────────────────────────────────────────────

SURVEY_SPECS: list[dict] = [
    {
        "name": "NPS Q2 2026",
        "description": (
            "Quarterly Net Promoter Score survey. Sampled across all "
            "active customers."
        ),
        "type": "popover",
        "questions": [
            {
                "type": "rating",
                "question": (
                    "How likely are you to recommend us to a "
                    "colleague?"
                ),
                "display": "number",
                "scale": 10,
            },
            {
                "type": "open",
                "question": "What's the main reason for your score?",
            },
        ],
    },
    {
        "name": "Why are you cancelling?",
        "description": (
            "Lifecycle survey shown to customers who initiate cancel. "
            "Drives churn reason categorization."
        ),
        "type": "popover",
        "questions": [
            {
                "type": "single_choice",
                "question": "Which best describes why you're leaving?",
                "choices": [
                    "Too expensive",
                    "Missing features",
                    "Found an alternative",
                    "Don't need it anymore",
                    "Bugs / reliability",
                    "Billing issues",
                    "Other",
                ],
            },
            {
                "type": "open",
                "question": "Anything we could have done differently?",
            },
        ],
    },
    {
        "name": "Onboarding feedback (week 1)",
        "description": (
            "Sent to new accounts 7 days after signup_completed."
        ),
        "type": "popover",
        "questions": [
            {
                "type": "rating",
                "question": "How was getting started?",
                "display": "emoji",
                "scale": 5,
            },
            {
                "type": "open",
                "question": "What was the biggest hurdle?",
            },
        ],
    },
    {
        "name": "Enterprise dashboard - feature request",
        "description": (
            "Surfaced inside the Enterprise dashboard to collect "
            "feature requests. Linked to enterprise_dashboard_v2 flag."
        ),
        "type": "popover",
        "questions": [
            {
                "type": "open",
                "question": (
                    "What's the one thing we could add to make this "
                    "dashboard more useful?"
                ),
            },
        ],
    },
    {
        "name": "Billing experience - disputes",
        "description": (
            "Targeted at customers who recently went through a dispute "
            "or refund flow. Captures whether the resolution felt fair."
        ),
        "type": "popover",
        "questions": [
            {
                "type": "rating",
                "question": (
                    "How fair did our handling of your recent billing "
                    "issue feel?"
                ),
                "display": "number",
                "scale": 5,
            },
            {
                "type": "open",
                "question": "What would have made it better?",
            },
        ],
    },
]


def upsert_survey(
    client: httpx.Client,
    spec: dict,
    existing_by_name: dict[str, str],
) -> tuple[str | None, str]:
    payload = {
        "name": spec["name"],
        "description": spec.get("description", ""),
        "type": spec.get("type", "popover"),
        "questions": spec["questions"],
    }
    name = spec["name"]
    if name in existing_by_name:
        sid = existing_by_name[name]
        r = _request(
            client, "PATCH",
            f"/api/projects/{PROJECT_ID}/surveys/{sid}/",
            json=payload,
        )
        if r.status_code in (200, 201):
            return sid, "updated"
        return sid, f"error-update-{r.status_code}: {r.text[:200]}"
    r = _request(
        client, "POST",
        f"/api/projects/{PROJECT_ID}/surveys/",
        json=payload,
    )
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    return None, f"error-create-{r.status_code}: {r.text[:200]}"


# ──────────────────────────────────────────────────────────────────────
# Event ingestion (bonus - needs project API key)
# ──────────────────────────────────────────────────────────────────────


def _distinct_id_for_user(company: Company, suffix: str = "") -> str:
    """Deterministic distinct_id for a user inside a company."""
    base = f"user_{company.slug.replace('-', '_')}"
    return f"{base}_{suffix}" if suffix else base


def _person_properties(company: Company, role: str) -> dict:
    """Build $set properties to identify the person."""
    name_parts = company.email.split("@")[0]
    return {
        "$set": {
            "email": f"{role}@{company.email.split('@', 1)[1]}",
            "company": company.name,
            "company_slug": company.slug,
            "country": company.country,
            "plan": company.plan,
            "health": company.health,
            "industry": company.industry,
            "arr_usd": company.arr_usd,
            "role": role,
            # Per-workflow markers.
            "dispute_count_12mo": (
                3 if company.slug == "acme-genomics" else 0
            ),
            "entitlement_mismatch": (
                True if company.slug == "northwind-logi" else False
            ),
            "has_legacy_subscription": (
                True if company.slug == "mockingbird-media" else False
            ),
            "has_stripe_subscription": True,
            "cancel_intent": company.health == "red",
            "name": f"{role.title()} at {company.name}",
        },
        "$set_once": {
            "signup_year": company.signup_year,
            "first_seen": f"{company.signup_year}-01-15T10:00:00Z",
        },
    }


def build_persons() -> list[tuple[str, dict, str]]:
    """Return (distinct_id, $set properties, company_slug) tuples.

    ~3-5 users per company × 35 companies → 100-150 distinct identities.
    """
    out: list[tuple[str, dict, str]] = []
    roles_by_arr = {
        # Small accounts get fewer users.
        "small": ["admin", "ops"],  # 2
        "mid": ["admin", "ops", "billing"],  # 3
        "large": ["admin", "ops", "billing", "csm", "exec"],  # 5
    }
    for c in COMPANIES:
        if c.arr_usd >= 100_000:
            roles = roles_by_arr["large"]
        elif c.arr_usd >= 30_000:
            roles = roles_by_arr["mid"]
        else:
            roles = roles_by_arr["small"]
        for role in roles:
            did = _distinct_id_for_user(c, role)
            out.append((did, _person_properties(c, role), c.slug))
    return out


def build_events(
    persons: list[tuple[str, dict, str]],
    project_key: str,
) -> list[dict]:
    """Build a realistic spread of events.

    Each person gets:
      - $pageview events spread over 90 days
      - $identify (via the persons step)
      - 5-20 product events
    Plus workflow-target persons get the diagnostic events that the
    insights point at.
    """
    events: list[dict] = []
    # Anchor "now" at 2026-05-26 (close to current date) so the insight
    # date ranges line up.
    now = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)

    company_by_slug = {c.slug: c for c in COMPANIES}

    PRODUCT_EVENTS = [
        "$pageview",
        "dashboard_viewed",
        "report_generated",
        "export_completed",
        "api_request",
        "ticket_resolved",
        "subscription_renewed",
        "stripe_checkout_opened",
        "stripe_checkout_succeeded",
    ]

    for did, props, slug in persons:
        c = company_by_slug[slug]
        # 1) $identify-style event ($set persists the props).
        events.append({
            "event": "$identify",
            "distinct_id": did,
            "properties": {
                **props,
                "$lib": "manthan-seed",
            },
            "timestamp": (now - timedelta(days=90)).isoformat(),
        })

        # 2) 5-20 random product events over 90 days.
        n = random.randint(5, 20)
        for _ in range(n):
            days_ago = random.randint(0, 90)
            hours_ago = random.randint(0, 23)
            ts = now - timedelta(days=days_ago, hours=hours_ago)
            ev = random.choice(PRODUCT_EVENTS)
            events.append({
                "event": ev,
                "distinct_id": did,
                "properties": {
                    "plan": c.plan,
                    "company_slug": c.slug,
                    "$lib": "manthan-seed",
                },
                "timestamp": ts.isoformat(),
            })

    # ── Workflow-specific events ──
    # W1: Acme Genomics - 3 dispute_filed events, 2 refund_issued.
    acme_admin = _distinct_id_for_user(
        company_by_slug["acme-genomics"], "admin"
    )
    for i, days_ago in enumerate([240, 150, 12]):
        events.append({
            "event": "dispute_filed",
            "distinct_id": acme_admin,
            "properties": {
                "reason": "subscription_canceled",
                "amount_usd": 4200,
                "company_slug": "acme-genomics",
                "dispute_number": i + 1,
                "$lib": "manthan-seed",
            },
            "timestamp": (now - timedelta(days=days_ago)).isoformat(),
        })
    for days_ago in [238, 148]:
        events.append({
            "event": "refund_issued",
            "distinct_id": acme_admin,
            "properties": {
                "amount_usd": 4200,
                "company_slug": "acme-genomics",
                "$lib": "manthan-seed",
            },
            "timestamp": (now - timedelta(days=days_ago)).isoformat(),
        })

    # W2: Northwind - webhook_delivery_failed cluster on 2026-05-08.
    northwind_admin = _distinct_id_for_user(
        company_by_slug["northwind-logi"], "admin"
    )
    crash_day = datetime(2026, 5, 8, 14, 7, 0, tzinfo=timezone.utc)
    for i in range(8):
        events.append({
            "event": "webhook_delivery_failed",
            "distinct_id": f"system_webhook_handler_{i}",
            "properties": {
                "webhook_type": "invoice.payment_succeeded",
                "company_slug": "northwind-logi",
                "error": "TypeError: NoneType has no attribute 'tier'",
                "$lib": "manthan-seed",
            },
            "timestamp": (
                crash_day + timedelta(minutes=i * 3)
            ).isoformat(),
        })
    events.append({
        "event": "entitlement_mismatch_detected",
        "distinct_id": northwind_admin,
        "properties": {
            "paid_tier": "Enterprise",
            "granted_tier": "Standard",
            "company_slug": "northwind-logi",
            "$lib": "manthan-seed",
        },
        "timestamp": (now - timedelta(days=14)).isoformat(),
    })

    # W3: Mockingbird - dual_billing_detected + legacy_subscription_charged.
    mb_admin = _distinct_id_for_user(
        company_by_slug["mockingbird-media"], "admin"
    )
    for days_ago in [55, 25, 8]:
        events.append({
            "event": "dual_billing_detected",
            "distinct_id": mb_admin,
            "properties": {
                "stripe_amount_usd": 5500,
                "legacy_amount_usd": 5500,
                "company_slug": "mockingbird-media",
                "$lib": "manthan-seed",
            },
            "timestamp": (now - timedelta(days=days_ago)).isoformat(),
        })
        events.append({
            "event": "legacy_subscription_charged",
            "distinct_id": mb_admin,
            "properties": {
                "amount_usd": 5500,
                "company_slug": "mockingbird-media",
                "$lib": "manthan-seed",
            },
            "timestamp": (
                now - timedelta(days=days_ago - 1)
            ).isoformat(),
        })

    return events


def ingest_events(
    client: httpx.Client,
    events: list[dict],
    project_key: str,
    batch_size: int = 100,
) -> tuple[int, int]:
    """POST events in batches to /batch/. Returns (sent, errors)."""
    sent = 0
    errors = 0
    for i in range(0, len(events), batch_size):
        chunk = events[i : i + batch_size]
        body = {"api_key": project_key, "batch": chunk}
        r = _request(
            client, "POST", f"{BASE}/batch/", json=body
        )
        if r.status_code == 200:
            sent += len(chunk)
        else:
            errors += len(chunk)
            print(
                f"  batch {i // batch_size}: "
                f"{r.status_code} {r.text[:200]}"
            )
        time.sleep(REQ_SLEEP)
    return sent, errors


# ──────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────


def verify_workflows(
    client: httpx.Client,
    insight_ids: dict[str, int],
    flag_ids: dict[str, int],
    cohort_ids: dict[str, int],
    dashboard_ids: dict[str, int],
) -> dict[str, bool]:
    """Confirm W1/W2/W3 signals exist in PostHog."""
    results: dict[str, bool] = {}

    # W1 - Acme outlier insight + multiple-disputes cohort exist.
    w1 = (
        "Refund rate by company - Acme outlier" in insight_ids
        and "Disputes filed per customer (rolling 12 months)"
        in insight_ids
        and "Customers with multiple disputes" in cohort_ids
    )
    results["W1"] = w1
    print(
        f"W1 acme-daisy-chargebacks  "
        f"insights={'yes' if w1 else 'NO'}"
    )

    # W2 - Webhook reliability dashboard, webhook insight, flag exist.
    w2 = (
        "Webhook delivery failures by hour" in insight_ids
        and "Entitlement mismatch: paid vs tier" in insight_ids
        and "enterprise_dashboard_v2" in flag_ids
        and "Engineering - Webhook Reliability" in dashboard_ids
        and "Customers stuck on wrong plan" in cohort_ids
    )
    results["W2"] = w2
    print(
        f"W2 northwind-webhook-ghost insights+flag+dashboard="
        f"{'yes' if w2 else 'NO'}"
    )

    # W3 - Legacy migration flag + dual-billing insight + cohort.
    w3 = (
        "Customers on dual billing entities" in insight_ids
        and "Legacy billing entity - active subscriptions"
        in insight_ids
        and "legacy_billing_entity_deprecated" in flag_ids
        and "Customers on dual billing entities" in cohort_ids
        and "Billing - Migration Tracking" in dashboard_ids
    )
    results["W3"] = w3
    print(
        f"W3 mockingbird-double      "
        f"insights+flag+cohort={'yes' if w3 else 'NO'}"
    )

    return results


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    counts: dict[str, int] = {
        "insights_created": 0, "insights_updated": 0, "insights_error": 0,
        "flags_created": 0, "flags_updated": 0, "flags_error": 0,
        "dashboards_created": 0, "dashboards_updated": 0,
        "dashboards_error": 0,
        "cohorts_created": 0, "cohorts_updated": 0, "cohorts_error": 0,
        "surveys_created": 0, "surveys_updated": 0, "surveys_error": 0,
        "tiles_attached": 0,
        "persons_attempted": 0, "events_sent": 0, "events_error": 0,
    }
    errors: list[str] = []
    insight_ids: dict[str, int] = {}
    flag_ids: dict[str, int] = {}
    dashboard_ids: dict[str, int] = {}
    cohort_ids: dict[str, int] = {}
    survey_ids: dict[str, str] = {}

    with httpx.Client(headers=H_MGMT, timeout=TIMEOUT) as client:
        # ── 0. Fetch project API key for ingestion ─────────────────
        project_key = fetch_project_api_key(client)
        print(
            f"Project: {PROJECT_ID} on {BASE}  "
            f"phc_key_available={bool(project_key)}"
        )

        # ── 1. Insights ────────────────────────────────────────────
        print("\nFetching existing insights…")
        existing_insights = list_all(
            client, f"/api/projects/{PROJECT_ID}/insights/"
        )
        ex_ins_by_name: dict[str, int] = {
            i.get("name"): i.get("id")
            for i in existing_insights
            if i.get("name")
        }
        print(f"  existing: {len(existing_insights)}")

        print(f"\nSeeding {len(INSIGHT_SPECS)} insights…")
        for spec in INSIGHT_SPECS:
            iid, action = upsert_insight(client, spec, ex_ins_by_name)
            if iid:
                insight_ids[spec["name"]] = iid
                # Refresh existing map so a repeat name hits the update
                # branch instead of creating duplicates.
                ex_ins_by_name[spec["name"]] = iid
            if action == "created":
                counts["insights_created"] += 1
            elif action == "updated":
                counts["insights_updated"] += 1
            else:
                counts["insights_error"] += 1
                errors.append(f"insight {spec['name']}: {action}")
            print(f"  [{action:>30}] {spec['name'][:50]:50s} → {iid}")
            time.sleep(REQ_SLEEP)

        # ── 2. Feature flags ───────────────────────────────────────
        print("\nFetching existing feature flags…")
        existing_flags = list_all(
            client, f"/api/projects/{PROJECT_ID}/feature_flags/"
        )
        ex_flag_by_key: dict[str, int] = {
            f.get("key"): f.get("id")
            for f in existing_flags
            if f.get("key")
        }
        print(f"  existing: {len(existing_flags)}")

        print(f"\nSeeding {len(FLAG_SPECS)} feature flags…")
        for spec in FLAG_SPECS:
            fid, action = upsert_flag(client, spec, ex_flag_by_key)
            if fid:
                flag_ids[spec["key"]] = fid
                ex_flag_by_key[spec["key"]] = fid
            if action == "created":
                counts["flags_created"] += 1
            elif action == "updated":
                counts["flags_updated"] += 1
            else:
                counts["flags_error"] += 1
                errors.append(f"flag {spec['key']}: {action}")
            print(f"  [{action:>30}] {spec['key']:35s} → {fid}")
            time.sleep(REQ_SLEEP)

        # ── 3. Dashboards ──────────────────────────────────────────
        print("\nFetching existing dashboards…")
        existing_dashboards = list_all(
            client, f"/api/projects/{PROJECT_ID}/dashboards/"
        )
        ex_dash_by_name: dict[str, int] = {
            d.get("name"): d.get("id")
            for d in existing_dashboards
            if d.get("name")
        }
        print(f"  existing: {len(existing_dashboards)}")

        print(f"\nSeeding {len(DASHBOARD_SPECS)} dashboards…")
        for spec in DASHBOARD_SPECS:
            did, action = upsert_dashboard(client, spec, ex_dash_by_name)
            if did:
                dashboard_ids[spec["name"]] = did
                ex_dash_by_name[spec["name"]] = did
            if action == "created":
                counts["dashboards_created"] += 1
            elif action == "updated":
                counts["dashboards_updated"] += 1
            else:
                counts["dashboards_error"] += 1
                errors.append(f"dashboard {spec['name']}: {action}")
            print(f"  [{action:>30}] {spec['name'][:50]:50s} → {did}")
            time.sleep(REQ_SLEEP)

            # Attach insight tiles.
            tile_ids = [
                insight_ids[n]
                for n in spec.get("tile_insight_names", [])
                if n in insight_ids
            ]
            if did and tile_ids:
                attached = attach_insights_to_dashboard(
                    client, did, tile_ids
                )
                counts["tiles_attached"] += attached
                print(
                    f"    └─ attached {attached}/{len(tile_ids)} "
                    f"insight tiles"
                )

        # ── 4. Cohorts ─────────────────────────────────────────────
        print("\nFetching existing cohorts…")
        existing_cohorts = list_all(
            client, f"/api/projects/{PROJECT_ID}/cohorts/"
        )
        ex_co_by_name: dict[str, int] = {
            c.get("name"): c.get("id")
            for c in existing_cohorts
            if c.get("name")
        }
        print(f"  existing: {len(existing_cohorts)}")

        print(f"\nSeeding {len(COHORT_SPECS)} cohorts…")
        for spec in COHORT_SPECS:
            cid, action = upsert_cohort(client, spec, ex_co_by_name)
            if cid:
                cohort_ids[spec["name"]] = cid
                ex_co_by_name[spec["name"]] = cid
            if action == "created":
                counts["cohorts_created"] += 1
            elif action == "updated":
                counts["cohorts_updated"] += 1
            else:
                counts["cohorts_error"] += 1
                errors.append(f"cohort {spec['name']}: {action}")
            print(f"  [{action:>30}] {spec['name'][:50]:50s} → {cid}")
            time.sleep(REQ_SLEEP)

        # ── 5. Surveys ─────────────────────────────────────────────
        print("\nFetching existing surveys…")
        existing_surveys = list_all(
            client, f"/api/projects/{PROJECT_ID}/surveys/"
        )
        # Surveys filter: ignore the probe survey by name match for
        # idempotency; it stays in PostHog but we don't conflict.
        ex_sv_by_name: dict[str, str] = {
            s.get("name"): s.get("id")
            for s in existing_surveys
            if s.get("name") and not s.get("name", "").startswith("__PROBE")
        }
        print(f"  existing: {len(existing_surveys)}")

        print(f"\nSeeding {len(SURVEY_SPECS)} surveys…")
        for spec in SURVEY_SPECS:
            sid, action = upsert_survey(client, spec, ex_sv_by_name)
            if sid:
                survey_ids[spec["name"]] = sid
                ex_sv_by_name[spec["name"]] = sid
            if action == "created":
                counts["surveys_created"] += 1
            elif action == "updated":
                counts["surveys_updated"] += 1
            else:
                counts["surveys_error"] += 1
                errors.append(f"survey {spec['name']}: {action}")
            print(f"  [{action:>30}] {spec['name'][:50]:50s} → {sid}")
            time.sleep(REQ_SLEEP)

        # ── 6. Event ingestion (uses phc_ key) ─────────────────────
        if project_key:
            print(
                "\nIngesting events (uses project api_token, "
                "not personal key)…"
            )
            persons = build_persons()
            counts["persons_attempted"] = len(persons)
            events = build_events(persons, project_key)
            print(
                f"  persons={len(persons)}  events={len(events)}  "
                f"batching by 100"
            )
            sent, errs = ingest_events(client, events, project_key)
            counts["events_sent"] = sent
            counts["events_error"] = errs
            print(f"  ingested: {sent}  errors: {errs}")
        else:
            print(
                "\nSkipping event ingestion: no project api_token "
                "available."
            )

        # ── 7. W1/W2/W3 verification ───────────────────────────────
        print("\n" + "─" * 70)
        print("Workflow signal verification")
        print("─" * 70)
        verify_workflows(
            client, insight_ids, flag_ids, cohort_ids, dashboard_ids
        )

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("SUMMARY")
    print("═" * 70)
    print(
        f"Insights   : created={counts['insights_created']:2d}  "
        f"updated={counts['insights_updated']:2d}  "
        f"errors={counts['insights_error']:2d}"
    )
    print(
        f"Flags      : created={counts['flags_created']:2d}  "
        f"updated={counts['flags_updated']:2d}  "
        f"errors={counts['flags_error']:2d}"
    )
    print(
        f"Dashboards : created={counts['dashboards_created']:2d}  "
        f"updated={counts['dashboards_updated']:2d}  "
        f"errors={counts['dashboards_error']:2d}  "
        f"tiles_attached={counts['tiles_attached']}"
    )
    print(
        f"Cohorts    : created={counts['cohorts_created']:2d}  "
        f"updated={counts['cohorts_updated']:2d}  "
        f"errors={counts['cohorts_error']:2d}"
    )
    print(
        f"Surveys    : created={counts['surveys_created']:2d}  "
        f"updated={counts['surveys_updated']:2d}  "
        f"errors={counts['surveys_error']:2d}"
    )
    print(
        f"Events     : persons_attempted={counts['persons_attempted']}  "
        f"events_sent={counts['events_sent']}  "
        f"errors={counts['events_error']}"
    )

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  …and {len(errors) - 20} more")

    print("\nWorkflow IDs:")
    print(
        f"  W1 cohort 'Customers with multiple disputes' → "
        f"{cohort_ids.get('Customers with multiple disputes', '(missing)')}"
    )
    print(
        f"  W2 flag 'enterprise_dashboard_v2' → "
        f"{flag_ids.get('enterprise_dashboard_v2', '(missing)')}"
    )
    print(
        f"  W2 dashboard 'Engineering - Webhook Reliability' → "
        f"{dashboard_ids.get('Engineering - Webhook Reliability', '(missing)')}"
    )
    print(
        f"  W3 flag 'legacy_billing_entity_deprecated' → "
        f"{flag_ids.get('legacy_billing_entity_deprecated', '(missing)')}"
    )
    print(
        f"  W3 insight 'Customers on dual billing entities' → "
        f"{insight_ids.get('Customers on dual billing entities', '(missing)')}"
    )

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
