"""Seed PagerDuty with 8 services + ~150 incidents.

Drives the Manthan billing-dispute investigation agent. Bakes in the W2
workflow signal (failed Stripe webhook → Northwind ghost-paid) as a
resolved high-urgency incident on the billing-webhook-handler service.

Idempotent - re-runs:
  * Services: looked up by name via GET /services?query=<name>; the
    "Default Service" that ships with a fresh PagerDuty account is
    renamed to core-platform-prod on first run.
  * Incidents: every seed incident has a deterministic incident_key
    (sha1 of service + title). At start we fetch all existing incidents
    once and skip any whose incident_key is already present.

PagerDuty stamps every incident with its real created_at; the API does
not let us backdate. So all timestamps will be "today" - that's accepted
per the seed spec.

Run:
    .venv/bin/python scripts/seed_pagerduty.py
"""

from __future__ import annotations

import hashlib
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

TOKEN = os.getenv("PAGERDUTY_API_TOKEN")
if not TOKEN:
    sys.exit("ERROR: PAGERDUTY_API_TOKEN missing from .env")

REQUESTER_EMAIL = "akash@miny-labs.com"

BASE = "https://api.pagerduty.com"
HEADERS = {
    "Authorization": f"Token token={TOKEN}",
    "Accept": "application/vnd.pagerduty+json;version=2",
    "Content-Type": "application/json",
    "From": REQUESTER_EMAIL,
}

# Rate limit: 720 req/min ≈ 12 req/s. Sleep ~0.1s between requests to
# stay comfortably under the cap. We don't batch - PagerDuty's REST
# API has no bulk-incident-create endpoint.
REQ_SLEEP = 0.10

TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Deterministic seed so re-runs produce the same incident_keys.
random.seed(0xBEEF)


# ──────────────────────────────────────────────────────────────────────
# HTTP wrapper with backoff
# ──────────────────────────────────────────────────────────────────────


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | list | None = None,
    extra_headers: dict | None = None,
    retries: int = 4,
) -> httpx.Response:
    url = path if path.startswith("http") else f"{BASE}{path}"
    last_resp = None
    for attempt in range(retries):
        r = client.request(
            method, url, json=json, params=params, headers=extra_headers
        )
        last_resp = r
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", "1.0"))
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        return r
    return last_resp  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────
# Service catalog
# ──────────────────────────────────────────────────────────────────────


SERVICE_CATALOG: list[tuple[str, str]] = [
    (
        "core-platform-prod",
        "Core platform services - APIs, background jobs, internal tooling.",
    ),
    (
        "billing-webhook-handler",
        "Handles stripe webhook deliveries (invoice.payment_succeeded, "
        "customer.subscription.updated, etc.) → entitlement updates. "
        "Owner: payments team.",
    ),
    (
        "auth-service",
        "Authentication / authorization - token issuance, session "
        "validation, OAuth callback handlers.",
    ),
    (
        "api-gateway",
        "Public-facing HTTPS edge → routes to upstream services. Handles "
        "rate limiting, request signing, mTLS termination.",
    ),
    (
        "ingest-pipeline",
        "Streaming ingest workers - Kafka consumers feeding the data "
        "warehouse and analytics jobs.",
    ),
    (
        "database-primary",
        "Primary Postgres cluster (writer) + replication health. "
        "Connection pooling, slow-query monitoring.",
    ),
    (
        "cdn-edge",
        "CDN edge fleet - static asset delivery, image transformations, "
        "cache invalidation pipeline.",
    ),
    (
        "monitoring",
        "Observability stack - Prometheus, Grafana, alertmanager, "
        "incident routing.",
    ),
]


# ──────────────────────────────────────────────────────────────────────
# Incident templates per service
# ──────────────────────────────────────────────────────────────────────
#
# Each entry is (title, urgency, body).  Urgency: "high" or "low".
# We'll sample these per service to reach the volume target. The
# billing-webhook-handler list includes the W2-specific incident at
# the front; everything else is fleshed out with realistic SRE-flavored
# titles.

INCIDENT_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "core-platform-prod": [
        (
            "core-platform-prod: pod restart loop on payments-worker deployment",
            "high",
            "payments-worker pods entered CrashLoopBackOff after the 14:22 "
            "rollout. Liveness probe failing intermittently - suspect "
            "config map drift. Rolling back to previous revision.",
        ),
        (
            "core-platform-prod: latency p99 spike on /v1/customers endpoint",
            "high",
            "p99 latency on GET /v1/customers jumped from 180ms to 2.4s "
            "starting 09:15 UTC. Correlated with a connection pool "
            "saturation event downstream in database-primary.",
        ),
        (
            "core-platform-prod: memory pressure on api-worker nodes",
            "low",
            "Heap usage trending up over 72h on api-worker-1 through -4. "
            "No OOMs yet but expect rollover by EOW unless we cut a "
            "patch. Likely leak in the new audit-log serializer.",
        ),
        (
            "core-platform-prod: feature flag service returned 503 during deploy",
            "low",
            "LaunchDarkly client got 503s for ~90s during their planned "
            "maintenance. Fallback cache served stale flags - no user "
            "impact, but worth tightening the fallback TTL.",
        ),
        (
            "core-platform-prod: scheduled job 'nightly-rollup' missed window",
            "low",
            "The 02:00 UTC nightly-rollup didn't fire. Cron entry was "
            "removed during last week's Helm chart refactor. Re-added and "
            "manually backfilled today's batch.",
        ),
        (
            "core-platform-prod: graceful shutdown timeout on canary pods",
            "low",
            "Canary pods took 45s to shut down during the v2.14.0 rollout "
            "- breaches the 30s SLO for graceful shutdown. Investigating "
            "long-running goroutines in the metrics flusher.",
        ),
    ],
    "billing-webhook-handler": [
        # W2 signal incident is created separately with explicit body.
        (
            "billing-webhook-handler: Stripe signature verification failures elevated",
            "high",
            "Webhook signature verification error rate jumped from 0.01% "
            "to 3.2% over a 15-minute window. Suspect Stripe rotated the "
            "endpoint secret without our knowing - pulling fresh secret "
            "from dashboard.",
        ),
        (
            "billing-webhook-handler: invoice.payment_failed events queued, not processed",
            "high",
            "Dead-letter queue depth on invoice.payment_failed grew to "
            "1,200 in 30 minutes. Worker pool was paused after the last "
            "deploy and never resumed. Resumed manually; queue drained.",
        ),
        (
            "billing-webhook-handler: duplicate entitlement upgrades from replayed webhooks",
            "low",
            "Customers received duplicate upgrade confirmation emails when "
            "Stripe retried delivery of customer.subscription.updated. "
            "Idempotency key collision - fixed by including the event_id "
            "in the dedupe key.",
        ),
        (
            "billing-webhook-handler: customer.subscription.deleted not propagating to entitlements",
            "high",
            "Cancelled subscriptions stayed active in the entitlement "
            "table for 6 customers. Root cause: handler swallowed an "
            "exception in the downstream RPC. Patch deployed; manual "
            "fix-up script run for the 6 affected.",
        ),
        (
            "billing-webhook-handler: handler latency > 5s causing Stripe retries",
            "low",
            "Stripe deems webhooks failed after 5s. Our handler median "
            "creeping up due to a synchronous call to the analytics "
            "service. Moved that to an async fanout.",
        ),
        (
            "billing-webhook-handler: replay storm after Stripe outage backlog drain",
            "high",
            "Stripe delivered ~40k queued webhook events at once when "
            "their delivery system came back up. Our worker pool "
            "auto-scaled but the entitlement service DB locked up "
            "for ~3 minutes during the surge.",
        ),
        (
            "billing-webhook-handler: missing handler for new event type 'invoice.upcoming'",
            "low",
            "We're logging 'unhandled event type' warnings for "
            "invoice.upcoming. Not currently used downstream - adding "
            "a no-op handler to silence the noise.",
        ),
    ],
    "auth-service": [
        (
            "auth-service: token issuance latency degraded",
            "high",
            "POST /v1/oauth/token p95 jumped from 80ms to 1.2s. Redis "
            "session store showed elevated CPU; capacity headroom thin "
            "since last week's user growth spike.",
        ),
        (
            "auth-service: refresh token pre-emptive refresh failing for ~2% of sessions",
            "low",
            "A subset of clients on the older SDK (<v3.2) are failing "
            "their background refresh and hitting the login screen "
            "every ~30 minutes. SDK bug - upgrading customers off the "
            "old version.",
        ),
        (
            "auth-service: rate limiter false-positives on /v1/login",
            "low",
            "Corporate NAT'd customers from <10 IPs are tripping the "
            "/v1/login rate limit. Raised the per-IP cap and added an "
            "enterprise allowlist.",
        ),
        (
            "auth-service: OAuth callback 500 errors from one IdP",
            "high",
            "OneLogin callbacks returning 500 for ~12% of requests. "
            "Their IdP cert chain changed; we needed to trust an "
            "intermediate. Hot-patched the truststore.",
        ),
        (
            "auth-service: SAML metadata refresh job stuck",
            "low",
            "Background job that refreshes IdP SAML metadata hasn't "
            "completed in 18 hours. Stuck on a single tenant whose "
            "metadata URL now returns 404. Skipped that tenant; "
            "filed a ticket with their admin.",
        ),
        (
            "auth-service: brute-force attempts on /v1/login from one ASN",
            "high",
            "Spike in failed login attempts from ASN 12389 over 45 "
            "minutes. WAF blocking the offending IPs; no successful "
            "compromises observed.",
        ),
    ],
    "api-gateway": [
        (
            "api-gateway: 5xx error rate elevated above SLO",
            "high",
            "5xx rate on /v1/* climbed to 1.8% over a 10-minute window "
            "(SLO: 0.1%). Upstream timeouts to billing-webhook-handler. "
            "Page acknowledged; root cause linked to handler restart.",
        ),
        (
            "api-gateway: TLS cert renewal failed on edge-3",
            "high",
            "cert-manager renewal CronJob errored on edge-3 - Route 53 "
            "DNS challenge timed out. Manually rotated; investigating "
            "the DNS plugin retry behaviour.",
        ),
        (
            "api-gateway: WAF rule update accidentally blocked /v1/health",
            "low",
            "New WAF rule against SQLi pattern false-positived our own "
            "health probe path. LB marked instances unhealthy for ~4 "
            "minutes. Rule narrowed.",
        ),
        (
            "api-gateway: connection pool exhausted to upstream auth-service",
            "high",
            "Outbound conn pool to auth-service hit max-out for 6 "
            "minutes. Caused cascading 503s on /v1/login. Bumped pool "
            "size; auth-service was running hot at the same time.",
        ),
        (
            "api-gateway: edge node 'edge-7' draining slowly during deploy",
            "low",
            "edge-7 took 12 minutes to drain connections during the "
            "rolling restart. Long-lived websocket connections from "
            "the realtime product. Added a hard timeout.",
        ),
        (
            "api-gateway: spurious 401s during JWT key rotation",
            "low",
            "During the planned signing-key rotation, ~30 seconds of "
            "401s as old/new key sets propagated. Customer impact "
            "minimal; document the rotation runbook to include a "
            "30s grace overlap.",
        ),
    ],
    "ingest-pipeline": [
        (
            "ingest-pipeline: Kafka consumer lag above 100k on topic 'events.raw'",
            "high",
            "Consumer lag on events.raw climbed to 142k. One worker pod "
            "OOMed and never restarted. Pod re-rolled; lag draining at "
            "expected rate.",
        ),
        (
            "ingest-pipeline: worker queue depth above threshold",
            "low",
            "queue depth on the 'transform' stage breached the warning "
            "threshold (>5k) for 20 minutes. Scaled out by 2 replicas.",
        ),
        (
            "ingest-pipeline: schema validation failures spiking from one tenant",
            "low",
            "Tenant T-918 started sending events with an unknown field. "
            "Schema registry rejected ~12% of their events. Reached out; "
            "they pushed a fix.",
        ),
        (
            "ingest-pipeline: warehouse load job failed (Snowflake stage error)",
            "high",
            "COPY INTO from S3 stage failed with 'file format error' on "
            "the 04:00 batch. Corrupt Parquet file from one ingest "
            "worker. Skipped that file; replayed the rest.",
        ),
        (
            "ingest-pipeline: dead-letter topic growing - 'events.dlq'",
            "low",
            "DLQ topic up to ~3k messages, all from a single mis-configured "
            "tenant. Routed their traffic to the quarantine pipeline "
            "until they fix their producer.",
        ),
        (
            "ingest-pipeline: cross-AZ replication lag elevated",
            "high",
            "Replication lag on the events.raw topic between us-east-1a "
            "and us-east-1b climbed past 30s. AWS reported a transient "
            "network event in 1b; recovered after 8 minutes.",
        ),
    ],
    "database-primary": [
        (
            "database-primary: connection pool exhausted on primary writer",
            "high",
            "pgbouncer reported zero available connections on the primary "
            "for ~90 seconds. Slow query holding row locks. Killed the "
            "session; added an index suggested by EXPLAIN ANALYZE.",
        ),
        (
            "database-primary: replication lag on standby exceeding 60s",
            "high",
            "Standby replica db-replica-2 lagging the primary by 87s. "
            "Vacuum job on a large table is the suspect. Coordinating "
            "with the DBA for a controlled VACUUM FULL window.",
        ),
        (
            "database-primary: CPU > 85% on primary for 30 minutes",
            "low",
            "Primary CPU sustained > 85% during the analytics batch "
            "window. Worked as designed but headroom is thin. Planning "
            "a vertical scale-up next maintenance window.",
        ),
        (
            "database-primary: disk space on /var/lib/postgresql at 78%",
            "low",
            "Disk usage trending up faster than expected after the new "
            "audit-log table came online. Archival policy adjusted; "
            "old partitions detached and dropped.",
        ),
        (
            "database-primary: long-running query detected - > 10 min",
            "low",
            "A reporting query from the BI tool ran for 18 minutes on "
            "the primary instead of the read replica. BI tool config "
            "fixed to route reporting to the replica.",
        ),
        (
            "database-primary: failed pg_dump nightly backup",
            "high",
            "Nightly pg_dump exited non-zero - disk full on the backup "
            "bucket prefix due to retention misconfig. Extended the "
            "lifecycle rule; backup re-run successfully.",
        ),
    ],
    "cdn-edge": [
        (
            "cdn-edge: cache hit rate dropped below 92%",
            "low",
            "Cache hit rate fell from 98.4% to 89.1% after the asset "
            "pipeline changed its hashing scheme - invalidated more "
            "URLs than expected. Warming cache; expected to recover.",
        ),
        (
            "cdn-edge: origin shield 5xx rate elevated",
            "high",
            "Origin shield in us-east returning 5xx for ~2% of requests "
            "for 8 minutes. Coincided with an S3 partial outage. "
            "Recovered without action; tracking AWS status.",
        ),
        (
            "cdn-edge: image transform worker timeouts",
            "low",
            "/transform/* endpoint p95 jumped from 120ms to 1.8s on "
            "very large images uploaded by one tenant. Added a max "
            "input size guard.",
        ),
        (
            "cdn-edge: WAF false-positive on signed asset URLs",
            "high",
            "Signed URLs with long query strings tripped a WAF rule "
            "and got 403s for ~6 minutes. Whitelisted the signing "
            "param prefix.",
        ),
        (
            "cdn-edge: purge API latency exceeded SLO during release",
            "low",
            "Manual purge call took 47s during the v4.2 release purge "
            "of ~120k URLs. CDN provider acknowledged the slowness; "
            "they're tuning their queue.",
        ),
    ],
    "monitoring": [
        (
            "monitoring: alertmanager silenced an active page during maintenance",
            "high",
            "An over-broad silence put in place for the auth-service "
            "maintenance also silenced an unrelated database-primary "
            "page. Page was missed for ~12 minutes. Runbook updated to "
            "scope silences by alertname, not just service.",
        ),
        (
            "monitoring: Prometheus tsdb disk usage at 88%",
            "low",
            "Prom retention bumped from 15d to 30d last sprint and we "
            "didn't size up the volume. Extending the EBS volume; no "
            "outage.",
        ),
        (
            "monitoring: Grafana dashboard rendering errors on /d/billing",
            "low",
            "Billing dashboard panels showing 'query timeout' for "
            "anything > 7d range. Underlying datasource ran out of "
            "concurrent query slots; raised the cap.",
        ),
        (
            "monitoring: alert flapping on auth-service token issuance latency",
            "low",
            "Threshold too tight - alert fired and resolved 14 times "
            "in 90 minutes. Hysteresis added; threshold relaxed by 10%.",
        ),
        (
            "monitoring: scrape target failures on ingest-pipeline pods",
            "high",
            "Service-monitor lost its label selector match after the "
            "ingest-pipeline Helm chart upgrade. Half the pods went "
            "unscraped for 23 minutes. Selector restored.",
        ),
    ],
}


# ──────────────────────────────────────────────────────────────────────
# W2 signal - the canonical billing-webhook-handler crash
# ──────────────────────────────────────────────────────────────────────


W2_SERVICE = "billing-webhook-handler"
W2_TITLE = (
    "billing-webhook-handler: unhandled TypeError processing "
    "invoice.payment_succeeded - entitlement updates failing"
)
W2_BODY = (
    "Webhook handler crashed with uncaught TypeError around 2026-05-12 "
    "10:00-11:30 UTC. Customer payments succeeded in Stripe but "
    "downstream entitlement service never received the upgrade webhook. "
    "Affected customers may need manual entitlement promotion. SEV-1.\n\n"
    "Root cause: a recently-added field on the line_items array was "
    "expected to be a string but Stripe started returning null for one "
    "promo SKU. The handler did `.toLowerCase()` on it, throwing "
    "TypeError, and PM2 restarted the worker faster than alertmanager "
    "could route the page. Webhook deliveries returned 500 and Stripe's "
    "retry logic eventually gave up after ~3 hours.\n\n"
    "Remediation: null-guard added; entitlement promotion script run "
    "for the 14 customers identified in the dropped-delivery window. "
    "Customer success following up with each one individually."
)
W2_URGENCY = "high"


# ──────────────────────────────────────────────────────────────────────
# Services: find or create
# ──────────────────────────────────────────────────────────────────────


def find_service_id_by_name(
    client: httpx.Client, name: str
) -> tuple[str | None, str | None]:
    """Return (service_id, escalation_policy_id) or (None, None)."""
    r = _request(
        client, "GET", "/services", params={"query": name, "limit": 25}
    )
    if r.status_code != 200:
        return None, None
    for s in r.json().get("services", []):
        if s.get("name") == name:
            ep = s.get("escalation_policy", {})
            return s.get("id"), ep.get("id")
    return None, None


def first_escalation_policy_id(client: httpx.Client) -> str | None:
    r = _request(
        client, "GET", "/escalation_policies", params={"limit": 1}
    )
    if r.status_code != 200:
        return None
    pols = r.json().get("escalation_policies", [])
    if not pols:
        return None
    return pols[0].get("id")


def upsert_service(
    client: httpx.Client,
    name: str,
    description: str,
    fallback_ep_id: str,
) -> tuple[str | None, str]:
    """Create the service if missing; otherwise update its description.

    Returns (service_id, "created" | "updated" | "error").
    """
    sid, _ep = find_service_id_by_name(client, name)
    if sid:
        # Update description so re-runs converge to our canonical text.
        r = _request(
            client,
            "PUT",
            f"/services/{sid}",
            json={"service": {"description": description}},
        )
        if r.status_code in (200, 201):
            return sid, "updated"
        return sid, "error"

    # On a fresh account, the only existing service is "Default Service".
    # If the caller wants the very first service in our catalog
    # (core-platform-prod) and Default Service still exists, rename it
    # instead of creating a new one - keeps the EP attached and avoids
    # leaving "Default Service" cluttering the directory.
    if name == "core-platform-prod":
        default_sid, _ = find_service_id_by_name(client, "Default Service")
        if default_sid:
            r = _request(
                client,
                "PUT",
                f"/services/{default_sid}",
                json={
                    "service": {"name": name, "description": description}
                },
            )
            if r.status_code in (200, 201):
                return default_sid, "renamed-from-default"
            # If rename failed, fall through to create.

    body = {
        "service": {
            "name": name,
            "description": description,
            "escalation_policy": {
                "id": fallback_ep_id,
                "type": "escalation_policy_reference",
            },
            "alert_creation": "create_alerts_and_incidents",
        }
    }
    r = _request(client, "POST", "/services", json=body)
    if r.status_code in (200, 201):
        return r.json().get("service", {}).get("id"), "created"
    print(f"  service create fail {name}: {r.status_code} {r.text[:200]}")
    return None, "error"


# ──────────────────────────────────────────────────────────────────────
# Incidents: bulk fetch existing → skip if seen
# ──────────────────────────────────────────────────────────────────────


def _incident_key(service_name: str, title: str, salt: str = "") -> str:
    """Deterministic dedupe key for a seed incident."""
    payload = f"{service_name}|{title}|{salt}".encode()
    return f"seed-pd-{hashlib.sha1(payload).hexdigest()[:16]}"


def fetch_all_incident_keys(client: httpx.Client) -> set[str]:
    """Page through every incident on the account and collect their
    incident_key values. Used to avoid duplicate creates."""
    seen: set[str] = set()
    offset = 0
    limit = 100
    while True:
        params: list[tuple[str, str]] = [
            ("limit", str(limit)),
            ("offset", str(offset)),
            ("statuses[]", "triggered"),
            ("statuses[]", "acknowledged"),
            ("statuses[]", "resolved"),
        ]
        r = _request(client, "GET", "/incidents", params=params)
        if r.status_code != 200:
            print(f"  incident fetch fail: {r.status_code} {r.text[:200]}")
            break
        data = r.json()
        for inc in data.get("incidents", []):
            ik = inc.get("incident_key")
            if ik:
                seen.add(ik)
        if not data.get("more"):
            break
        offset += limit
        time.sleep(REQ_SLEEP)
    return seen


def create_incident(
    client: httpx.Client,
    service_id: str,
    title: str,
    urgency: str,
    body_details: str,
    incident_key: str,
) -> tuple[str | None, int | None]:
    """Returns (incident_id, incident_number)."""
    body = {
        "incident": {
            "type": "incident",
            "title": title,
            "service": {"id": service_id, "type": "service_reference"},
            "urgency": urgency,
            "body": {"type": "incident_body", "details": body_details},
            "incident_key": incident_key,
        }
    }
    r = _request(client, "POST", "/incidents", json=body)
    if r.status_code in (200, 201):
        inc = r.json().get("incident", {})
        return inc.get("id"), inc.get("incident_number")
    # If the open-incident-with-same-key check trips, treat as exists.
    if r.status_code == 400 and "matching dedup key" in r.text:
        return None, None
    print(
        f"  incident create fail [{title[:60]}]: "
        f"{r.status_code} {r.text[:200]}"
    )
    return None, None


def update_incident_status(
    client: httpx.Client, incident_id: str, status: str
) -> bool:
    body = {
        "incident": {"type": "incident_reference", "status": status},
    }
    r = _request(client, "PUT", f"/incidents/{incident_id}", json=body)
    if r.status_code in (200, 201):
        return True
    print(
        f"  status update {status} fail [{incident_id}]: "
        f"{r.status_code} {r.text[:200]}"
    )
    return False


# ──────────────────────────────────────────────────────────────────────
# Plan: how many incidents per service and what status mix
# ──────────────────────────────────────────────────────────────────────
#
# Volume target: ~150 incidents total.
# Roughly proportional to "ops attention", with billing-webhook-handler
# getting a healthy slice so its incident history reads "noisy service".

INCIDENTS_PER_SERVICE: dict[str, int] = {
    "core-platform-prod": 26,
    "billing-webhook-handler": 24,  # excludes the W2 signal incident
    "auth-service": 22,
    "api-gateway": 22,
    "ingest-pipeline": 18,
    "database-primary": 18,
    "cdn-edge": 12,
    "monitoring": 10,
}

# Status mix targets per service (must sum to incidents-per-service).
# Heavy on resolved (noise from the past), some open / acknowledged
# for present-tense variety.
STATUS_MIX = {
    "resolved": 0.85,
    "acknowledged": 0.08,
    "triggered": 0.07,
}


def status_for_index(idx: int, total: int) -> str:
    """Deterministic status assignment per service."""
    r_cut = int(total * STATUS_MIX["resolved"])
    a_cut = r_cut + int(total * STATUS_MIX["acknowledged"])
    if idx < r_cut:
        return "resolved"
    if idx < a_cut:
        return "acknowledged"
    return "triggered"


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    print("Seeding PagerDuty…")
    counts = {
        "services_created": 0,
        "services_updated": 0,
        "services_renamed": 0,
        "services_error": 0,
        "incidents_created": 0,
        "incidents_skipped_exists": 0,
        "incidents_error": 0,
        "incidents_resolved": 0,
        "incidents_acknowledged": 0,
        "incidents_triggered": 0,
    }
    by_service: Counter[str] = Counter()
    by_urgency: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    errors: list[str] = []
    w2_incident_id: str | None = None
    w2_incident_number: int | None = None

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # ── 0. Find the escalation policy we'll attach new services to.
        # Prefer the EP attached to whatever service currently exists.
        _existing_sid, ep_id = find_service_id_by_name(client, "Default Service")
        if not ep_id:
            # If Default Service was already renamed in a prior run,
            # try the first service we can find that has an EP.
            r = _request(client, "GET", "/services", params={"limit": 25})
            if r.status_code == 200:
                for s in r.json().get("services", []):
                    ep = s.get("escalation_policy", {}).get("id")
                    if ep:
                        ep_id = ep
                        break
        if not ep_id:
            ep_id = first_escalation_policy_id(client)
        if not ep_id:
            sys.exit(
                "ERROR: could not find any escalation policy to attach "
                "new services to. Create one in the PagerDuty UI first."
            )
        print(f"  Using escalation policy id: {ep_id}")

        # ── 1. Services ───────────────────────────────────────────────
        print(f"\nSeeding {len(SERVICE_CATALOG)} services…")
        service_ids: dict[str, str] = {}
        for name, desc in SERVICE_CATALOG:
            sid, action = upsert_service(client, name, desc, ep_id)
            if sid:
                service_ids[name] = sid
            if action == "created":
                counts["services_created"] += 1
            elif action == "renamed-from-default":
                counts["services_renamed"] += 1
            elif action == "updated":
                counts["services_updated"] += 1
            else:
                counts["services_error"] += 1
                errors.append(f"service {name}: {action}")
            print(f"  [{action:>22}] {name:30s} → {sid}")
            time.sleep(REQ_SLEEP)

        if "billing-webhook-handler" not in service_ids:
            sys.exit(
                "ERROR: billing-webhook-handler service was not created - "
                "cannot seed W2 signal. Aborting."
            )

        # ── 2. Fetch existing incidents so we can skip duplicates.
        print("\nFetching existing incidents (for idempotency)…")
        existing_keys = fetch_all_incident_keys(client)
        print(f"  found {len(existing_keys)} existing incident_keys")

        # ── 3. W2 signal incident on billing-webhook-handler ──────────
        print("\nSeeding W2 signal incident on billing-webhook-handler…")
        w2_key = _incident_key(W2_SERVICE, W2_TITLE, salt="W2")
        if w2_key in existing_keys:
            print(f"  W2 already seeded (key={w2_key}); resolving lookup…")
            # Find its id so we can report it.
            r = _request(
                client,
                "GET",
                "/incidents",
                params={"incident_key": w2_key},
            )
            if r.status_code == 200:
                incs = r.json().get("incidents", [])
                if incs:
                    w2_incident_id = incs[0].get("id")
                    w2_incident_number = incs[0].get("incident_number")
            counts["incidents_skipped_exists"] += 1
        else:
            w2_id, w2_num = create_incident(
                client,
                service_ids["billing-webhook-handler"],
                W2_TITLE,
                W2_URGENCY,
                W2_BODY,
                w2_key,
            )
            if w2_id:
                counts["incidents_created"] += 1
                by_service["billing-webhook-handler"] += 1
                by_urgency[W2_URGENCY] += 1
                w2_incident_id = w2_id
                w2_incident_number = w2_num
                # Resolve immediately - the past-incident-already-fixed
                # narrative is what the agent should see.
                time.sleep(REQ_SLEEP)
                if update_incident_status(client, w2_id, "resolved"):
                    counts["incidents_resolved"] += 1
                    by_status["resolved"] += 1
                else:
                    by_status["triggered"] += 1
            else:
                counts["incidents_error"] += 1
                errors.append("W2 signal incident failed to create")
            time.sleep(REQ_SLEEP)

        if w2_incident_id:
            print(f"  W2 incident: id={w2_incident_id} number={w2_incident_number}")
        else:
            print("  W2 incident: !! NOT CREATED !!")

        # ── 4. Bulk incidents per service ─────────────────────────────
        print("\nSeeding incidents per service…")
        for svc_name, target_n in INCIDENTS_PER_SERVICE.items():
            templates = INCIDENT_TEMPLATES.get(svc_name, [])
            if not templates:
                print(f"  no templates for {svc_name}, skipping")
                continue
            sid = service_ids.get(svc_name)
            if not sid:
                errors.append(f"no service_id for {svc_name}")
                continue
            print(f"\n  {svc_name}  target={target_n}")

            for i in range(target_n):
                tmpl = templates[i % len(templates)]
                base_title, urgency, body_text = tmpl

                # Add a variation tag so 26 incidents on the same service
                # aren't all identical-looking titles.
                if target_n > len(templates):
                    suffix = f" [#{i + 1:02d}]"
                else:
                    suffix = ""
                title = base_title + suffix

                ikey = _incident_key(svc_name, title, salt=f"v{i:03d}")
                if ikey in existing_keys:
                    counts["incidents_skipped_exists"] += 1
                    continue

                inc_id, inc_num = create_incident(
                    client, sid, title, urgency, body_text, ikey
                )
                if not inc_id:
                    counts["incidents_error"] += 1
                    errors.append(f"incident create fail: {title[:50]}")
                    time.sleep(REQ_SLEEP)
                    continue

                counts["incidents_created"] += 1
                by_service[svc_name] += 1
                by_urgency[urgency] += 1

                # Walk the status mix deterministically.
                target_status = status_for_index(i, target_n)
                time.sleep(REQ_SLEEP)

                if target_status == "acknowledged":
                    if update_incident_status(
                        client, inc_id, "acknowledged"
                    ):
                        counts["incidents_acknowledged"] += 1
                        by_status["acknowledged"] += 1
                    else:
                        by_status["triggered"] += 1
                elif target_status == "resolved":
                    if update_incident_status(client, inc_id, "resolved"):
                        counts["incidents_resolved"] += 1
                        by_status["resolved"] += 1
                    else:
                        by_status["triggered"] += 1
                else:
                    # leave as triggered
                    counts["incidents_triggered"] += 1
                    by_status["triggered"] += 1

                if (i + 1) % 5 == 0:
                    print(
                        f"    {i + 1:>3}/{target_n} created - "
                        f"latest #{inc_num} [{target_status}]"
                    )
                time.sleep(REQ_SLEEP)

    # ── 5. Final report ───────────────────────────────────────────────
    print("\n" + "=" * 62)
    print("SEED SUMMARY - PagerDuty")
    print("=" * 62)
    print(f"  Services: {len(SERVICE_CATALOG)} total")
    print(f"    created : {counts['services_created']}")
    print(f"    renamed : {counts['services_renamed']}")
    print(f"    updated : {counts['services_updated']}")
    print(f"    errors  : {counts['services_error']}")
    print()
    print(
        f"  Incidents: "
        f"{counts['incidents_created']} created, "
        f"{counts['incidents_skipped_exists']} already existed, "
        f"{counts['incidents_error']} errors"
    )
    print("    by service:")
    for s, n in sorted(by_service.items(), key=lambda x: -x[1]):
        print(f"      {n:>3}  {s}")
    print("    by urgency:")
    for u, n in by_urgency.items():
        print(f"      {n:>3}  {u}")
    print("    by status (this run):")
    for s, n in by_status.items():
        print(f"      {n:>3}  {s}")
    print()
    print("  W2 SIGNAL - webhook crash → Northwind ghost-paid:")
    if w2_incident_id:
        print(f"    incident id      : {w2_incident_id}")
        print(f"    incident number  : {w2_incident_number}")
        print(f"    service          : billing-webhook-handler")
        print(f"    title            : {W2_TITLE[:80]}")
        print(f"    status           : resolved")
    else:
        print(f"    !!! NOT CREATED !!!  see errors above")
    print()
    if errors:
        print(f"  Errors ({len(errors)}):")
        for e in errors[:20]:
            print(f"    - {e}")
        if len(errors) > 20:
            print(f"    … and {len(errors) - 20} more")

    return 0 if not counts["services_error"] and w2_incident_id else 1


if __name__ == "__main__":
    sys.exit(main())
