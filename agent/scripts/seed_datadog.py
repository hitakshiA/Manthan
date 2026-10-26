"""Seed Datadog (us5.datadoghq.com) for the Manthan billing-dispute agent.

Creates a realistic blend of monitors, events, and dashboards across many
services + teams. The W2 signal is baked into:

  * a monitor named "billing-webhook-handler error rate elevated" that
    captures the 2026-05-12 10:00-11:30 UTC error spike (currently OK,
    but the message + tags + alert-history note tell the story);
  * an event "Deploy billing-webhook v3.2.1 - hotfix for unhandled
    TypeError" dated 2026-05-12 11:45 UTC that resolves the crash.

The agent investigating Northwind's ghost-paid dispute should be able to
correlate the Stripe charge timestamp with the Datadog monitor's alert
window and the recovery deploy event - vendor failure, not friendly
fraud.

The script is idempotent: it searches Datadog by name/title before
creating each resource. Re-runs are cheap and safe.

Run:
    .venv/bin/python scripts/seed_datadog.py
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Make seed_world importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from seed_world import WORKFLOWS  # noqa: E402

# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

SITE = os.getenv("DD_SITE", "us5.datadoghq.com")
API_KEY = os.getenv("DD_API_KEY")
APP_KEY = os.getenv("DD_APPLICATION_KEY")

if not API_KEY or not APP_KEY:
    sys.exit("ERROR: DD_API_KEY and DD_APPLICATION_KEY must be set in .env")

BASE = f"https://api.{SITE}"
HEADERS = {
    "DD-API-KEY": API_KEY,
    "DD-APPLICATION-KEY": APP_KEY,
    "Content-Type": "application/json",
}

# Free-tier rate limit guard. Datadog returns 429 with Retry-After if we
# punch through it. We pace at ~10/sec which is well under the limit.
REQ_SLEEP = 0.10

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


# ──────────────────────────────────────────────────────────────────────
# W2 timing - the webhook crash window.
#
# The narrative date for the W2 crash is **2026-05-12** (matches the
# Stripe seeder's simulated_created_at and the seed_world fixtures).
# Datadog rejects events whose date_happened is more than ~18h in the
# past, so we cannot stamp ``date_happened`` to the literal 2026-05-12.
# Instead we follow the same pattern the Stripe seeder uses for
# Charge.created (test mode is "now"): bake the narrative date into
# the event title + text. The agent reads those, not date_happened.
# ──────────────────────────────────────────────────────────────────────

# Narrative dates - what the events SAY happened
W2_CRASH_START_NARRATIVE = datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc)
W2_CRASH_END_NARRATIVE = datetime(2026, 5, 12, 11, 30, 0, tzinfo=timezone.utc)
W2_DEPLOY_TIME_NARRATIVE = datetime(2026, 5, 12, 11, 45, 0, tzinfo=timezone.utc)
W2_CHARGE_TIME_NARRATIVE = datetime(2026, 5, 12, 10, 23, 0, tzinfo=timezone.utc)

# Posted timestamps - anchored to "now", clustered so the relative order
# (pre-crash deploy → incident open → hotfix deploy → incident resolved)
# is preserved. Each event's narrative date is in its title/text.
_NOW = datetime.now(timezone.utc)


def _hours_ago(hours: float) -> datetime:
    return _NOW - timedelta(hours=hours)


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


# ──────────────────────────────────────────────────────────────────────
# HTTP wrapper with retry on 429 / 5xx
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
    url = path if path.startswith("http") else f"{BASE}{path}"
    last = None
    for attempt in range(retries):
        r = client.request(method, url, json=json, params=params)
        last = r
        if r.status_code == 429:
            wait = float(r.headers.get("X-RateLimit-Reset", "")
                         or r.headers.get("Retry-After", "")
                         or "1.0")
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        time.sleep(REQ_SLEEP)
        return r
    return last  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────
# Monitor catalog
#
# Each entry becomes a Datadog monitor. ``status`` is a hint for the
# message field - we cannot directly set the runtime alert state via the
# create API (Datadog evaluates the query). Instead we write the
# narrative state into the message so search/list returns it, and we tag
# the monitor with status:<x> so filtering by tag works.
# ──────────────────────────────────────────────────────────────────────


@dataclass
class MonitorSpec:
    name: str
    type: str
    query: str
    message: str
    tags: list[str]
    options: dict
    note_state: str  # narrative - "Alert" / "Warn" / "OK"


def _common_options(thresholds: dict, **extra) -> dict:
    """Build a typical monitor options dict."""
    opts = {
        "thresholds": thresholds,
        "notify_audit": False,
        "include_tags": True,
        "new_host_delay": 300,
        "no_data_timeframe": 10,
        "notify_no_data": False,
        "renotify_interval": 0,
        "evaluation_delay": 60,
        "timeout_h": 0,
        "require_full_window": False,
        "silenced": {},
    }
    opts.update(extra)
    return opts


def w2_webhook_monitor() -> MonitorSpec:
    """THE W2 signal monitor - webhook handler 5xx error rate spike."""
    crash_start_iso = W2_CRASH_START_NARRATIVE.isoformat()
    crash_end_iso = W2_CRASH_END_NARRATIVE.isoformat()
    deploy_iso = W2_DEPLOY_TIME_NARRATIVE.isoformat()
    msg = (
        "Webhook handler error rate spiked above threshold "
        f"around {crash_start_iso} through {crash_end_iso} "
        "(approx 90 minutes). Caused by unhandled `TypeError: "
        "Cannot read properties of undefined (reading 'tier')` "
        "in invoice.payment_succeeded handler when the customer "
        "object did not include the optional `entitlement_hint` "
        "field. Impact: invoice.payment_succeeded events for "
        "customers paying during this window were ACK'd to Stripe "
        "but the internal entitlement table was never updated - "
        "customers stayed on their previous tier despite a "
        "successful charge.\n\n"
        f"Resolved at {deploy_iso} by deploy of "
        "billing-webhook v3.2.1 (see related event 'Deploy "
        "billing-webhook v3.2.1 - hotfix for unhandled "
        "TypeError'). Backfill of affected entitlements is "
        "manual - see runbook 'WEBHOOK-CRASH-BACKFILL'.\n\n"
        "Page @platform-oncall on re-trigger."
    )
    return MonitorSpec(
        name="billing-webhook-handler error rate elevated",
        type="query alert",
        query=(
            "avg(last_15m):sum:billing.webhook.errors.5xx"
            "{service:billing-webhook-handler} > 50"
        ),
        message=msg,
        tags=[
            "env:prod",
            "team:platform",
            "service:billing-webhook-handler",
            "sev:1",
            "workflow:W2-northwind-webhook-ghost",
            "status:resolved",
            "incident:INC-2026-05-12-webhook",
        ],
        options=_common_options(
            {"critical": 50, "warning": 20},
            notify_no_data=True,
            renotify_interval=15,
        ),
        note_state="Alert (resolved)",
    )


def all_monitors() -> list[MonitorSpec]:
    """The full monitor catalog. ~32 entries spanning many services."""
    out: list[MonitorSpec] = []

    # W2 signal - first so it's prominent.
    out.append(w2_webhook_monitor())

    # API gateway latency (Warn now). Datadog requires critical
    # threshold to equal the comparator in the query.
    out.append(MonitorSpec(
        name="api-gateway p95 latency above target",
        type="query alert",
        query=(
            "avg(last_5m):p95:trace.http.request.duration"
            "{service:api-gateway,env:prod} > 0.8"
        ),
        message=(
            "API gateway p95 latency above 800ms target for >5 min. "
            "Check upstream service health and load-balancer queue "
            "depth. Page @platform-oncall if persists >15 min."
        ),
        tags=["env:prod", "team:platform", "service:api-gateway",
              "sev:2", "status:warn"],
        options=_common_options({"critical": 0.8, "warning": 0.5}),
        note_state="Warn",
    ))

    # Database connection pool (OK)
    out.append(MonitorSpec(
        name="postgres-billing connection pool near exhaustion",
        type="query alert",
        query=(
            "avg(last_10m):avg:postgresql.connections.active"
            "{db:billing,env:prod} / avg:postgresql.connections.max"
            "{db:billing,env:prod} > 0.85"
        ),
        message=(
            "Billing database connection pool at >85% utilization. "
            "Investigate long-running transactions and connection "
            "leaks. Notify @db-oncall."
        ),
        tags=["env:prod", "team:platform", "service:postgres-billing",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 0.85, "warning": 0.7}),
        note_state="OK",
    ))

    # Cache hit rate (Warn)
    out.append(MonitorSpec(
        name="redis-session cache hit rate below floor",
        type="query alert",
        query=(
            "avg(last_15m):avg:redis.cache.hit_rate"
            "{service:redis-session,env:prod} < 0.7"
        ),
        message=(
            "Session cache hit rate below 70%. Likely cause: TTL "
            "tuned too aggressively after the last config change, "
            "or upstream invalidations spiked."
        ),
        tags=["env:prod", "team:platform", "service:redis-session",
              "sev:3", "status:warn"],
        options=_common_options({"critical": 0.7, "warning": 0.8}),
        note_state="Warn",
    ))

    # CDN error rate (OK)
    out.append(MonitorSpec(
        name="fastly-edge 5xx error rate",
        type="query alert",
        query=(
            "avg(last_10m):sum:fastly.requests{status:5xx,env:prod}"
            ".as_rate() > 5"
        ),
        message=(
            "Fastly edge 5xx error rate >5/sec. Often origin-side; "
            "check upstream health before assuming CDN issue."
        ),
        tags=["env:prod", "team:platform", "service:fastly-cdn",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 5, "warning": 2}),
        note_state="OK",
    ))

    # Auth service token issuance latency (OK)
    out.append(MonitorSpec(
        name="auth-service token issuance p99 latency",
        type="query alert",
        query=(
            "avg(last_5m):p99:auth.token.issue.duration"
            "{service:auth-service,env:prod} > 1.5"
        ),
        message=(
            "Token issuance p99 above 1.5s. Investigate JWT signing "
            "queue and key-rotation tasks. Notify @auth-oncall."
        ),
        tags=["env:prod", "team:auth", "service:auth-service",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 1.5, "warning": 1.0}),
        note_state="OK",
    ))

    # Worker queue depth (Alert)
    out.append(MonitorSpec(
        name="celery-default queue depth growing",
        type="query alert",
        query=(
            "avg(last_10m):max:celery.queue.depth"
            "{queue:default,env:prod} > 1000"
        ),
        message=(
            "Default Celery queue depth above 1000 for >10 min. "
            "Workers may be stuck or scaling lag. Check worker pool "
            "size and recent deploys to background-worker."
        ),
        tags=["env:prod", "team:platform", "service:background-worker",
              "sev:1", "status:alert"],
        options=_common_options({"critical": 1000, "warning": 500},
                                renotify_interval=30),
        note_state="Alert",
    ))

    # Disk fill - current utilization (forecast needs longer than
    # we have data for in test-seed, so use the current-value form).
    out.append(MonitorSpec(
        name="disk.utilization root partition",
        type="query alert",
        query=(
            "avg(last_30m):avg:system.disk.in_use"
            "{device:/,env:prod} > 0.85"
        ),
        message=(
            "Root partition utilization above 85% for 30 min. "
            "Expand or rotate logs before it crosses 90%."
        ),
        tags=["env:prod", "team:infra", "service:hostagent",
              "sev:2", "status:warn"],
        options=_common_options({"critical": 0.85, "warning": 0.75}),
        note_state="Warn",
    ))

    # Memory pressure (OK)
    out.append(MonitorSpec(
        name="container.memory pressure (billing-webhook-handler)",
        type="query alert",
        query=(
            "avg(last_5m):avg:container.memory.usage"
            "{service:billing-webhook-handler,env:prod} "
            "/ avg:container.memory.limit"
            "{service:billing-webhook-handler,env:prod} > 0.85"
        ),
        message=(
            "Webhook handler containers running hot on memory. "
            "Likely tied to a slow leak introduced in v3.2.0; "
            "monitor pre-deploy of v3.2.1."
        ),
        tags=["env:prod", "team:platform", "service:billing-webhook-handler",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 0.85, "warning": 0.7}),
        note_state="OK",
    ))

    # Background job completion (OK)
    out.append(MonitorSpec(
        name="invoice.reconcile job success rate",
        type="query alert",
        query=(
            "avg(last_1h):sum:job.invoice_reconcile.success"
            "{env:prod} / sum:job.invoice_reconcile.total"
            "{env:prod} < 0.98"
        ),
        message=(
            "Nightly invoice reconciliation success rate dipped "
            "below 98%. Check job logs and downstream Stripe API "
            "rate limits."
        ),
        tags=["env:prod", "team:billing", "service:billing-jobs",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 0.98, "warning": 0.99}),
        note_state="OK",
    ))

    # Email delivery failure (Warn)
    out.append(MonitorSpec(
        name="sendgrid email bounce rate above floor",
        type="query alert",
        query=(
            "avg(last_30m):sum:sendgrid.email.bounce"
            "{env:prod} / sum:sendgrid.email.delivered"
            "{env:prod} > 0.02"
        ),
        message=(
            "Email bounce rate above 2%. Likely transient SES/"
            "Sendgrid issue or a bad list. @growth check before "
            "re-running campaigns."
        ),
        tags=["env:prod", "team:growth", "service:sendgrid",
              "sev:3", "status:warn"],
        options=_common_options({"critical": 0.02, "warning": 0.01}),
        note_state="Warn",
    ))

    # Search indexer freshness (OK)
    out.append(MonitorSpec(
        name="elasticsearch indexer lag",
        type="query alert",
        query=(
            "avg(last_10m):max:elasticsearch.indexer.lag_seconds"
            "{service:search-indexer,env:prod} > 300"
        ),
        message=(
            "Search indexer falling behind by >5 min. Check Kafka "
            "consumer lag and Elasticsearch cluster health."
        ),
        tags=["env:prod", "team:data", "service:search-indexer",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 300, "warning": 120}),
        note_state="OK",
    ))

    # API rate limit hit count (Warn)
    out.append(MonitorSpec(
        name="public-api 429 rate-limit hits",
        type="query alert",
        query=(
            "sum(last_15m):sum:public_api.rate_limit.hit"
            "{env:prod}.as_count() > 500"
        ),
        message=(
            "Public API rate-limit rejections >500 in 15min. Might "
            "indicate a misbehaving customer integration; check "
            "tag api_key:* for top offenders."
        ),
        tags=["env:prod", "team:api", "service:public-api",
              "sev:3", "status:warn"],
        options=_common_options({"critical": 500, "warning": 200}),
        note_state="Warn",
    ))

    # Webhook delivery success rate (general - not the W2 monitor) (OK)
    out.append(MonitorSpec(
        name="outbound webhook delivery success rate",
        type="query alert",
        query=(
            "avg(last_30m):sum:webhook.outbound.delivered"
            "{env:prod} / sum:webhook.outbound.attempted"
            "{env:prod} < 0.95"
        ),
        message=(
            "Outbound webhook delivery success rate below 95%. "
            "Customers may see missed events. Check the retry "
            "queue and dead-letter dashboard."
        ),
        tags=["env:prod", "team:platform", "service:webhook-dispatcher",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 0.95, "warning": 0.98}),
        note_state="OK",
    ))

    # Stripe API client latency (OK)
    out.append(MonitorSpec(
        name="stripe-api-client p95 latency",
        type="query alert",
        query=(
            "avg(last_10m):p95:stripe.api.call.duration"
            "{env:prod} > 2.5"
        ),
        message=(
            "Stripe API client p95 over 2.5s. Could be upstream; "
            "check status.stripe.com before paging."
        ),
        tags=["env:prod", "team:billing", "service:billing-core",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 2.5, "warning": 1.5}),
        note_state="OK",
    ))

    # Security - failed-login burst (Track Logs is paywalled on this
    # org, so we use a metric alert on a counter the auth service
    # emits directly).
    out.append(MonitorSpec(
        name="auth-service repeated failed-login burst",
        type="query alert",
        query=(
            "sum(last_5m):sum:auth.login.failed"
            "{service:auth-service,env:prod}.as_count() > 100"
        ),
        message=(
            "More than 100 failed logins in 5 minutes against "
            "auth-service. Possible credential stuffing. @security "
            "review source IPs (tag @usr.ip in Datadog logs) and "
            "block at the WAF if confirmed."
        ),
        tags=["env:prod", "team:security", "service:auth-service",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 100, "warning": 30}),
        note_state="OK",
    ))

    # Disputes / chargebacks - metric form (same paywall reason).
    out.append(MonitorSpec(
        name="stripe webhook dispute.created burst",
        type="query alert",
        query=(
            "sum(last_1h):sum:stripe.webhook.event"
            "{event:charge.dispute.created,env:prod}.as_count() > 5"
        ),
        message=(
            "Chargeback bursts can indicate either a real bug, "
            "card-testing, or a refund-policy regression. Review "
            "/billing-disputes-dashboard before paging."
        ),
        tags=["env:prod", "team:billing", "service:stripe-webhook-receiver",
              "sev:3", "status:warn"],
        options=_common_options({"critical": 5, "warning": 2}),
        note_state="Warn",
    ))

    # Service check - host agent up (OK). Host monitors require
    # notify_no_data=True per Datadog policy.
    out.append(MonitorSpec(
        name="datadog.agent up",
        type="service check",
        query=(
            "\"datadog.agent.up\".over(\"env:prod\").by(\"host\")"
            ".last(2).count_by_status()"
        ),
        message=(
            "Datadog agent reporting down on at least one prod "
            "host. Check the host directly."
        ),
        tags=["env:prod", "team:infra", "service:datadog-agent",
              "sev:3", "status:ok"],
        options=_common_options(
            {"critical": 1, "warning": 1, "ok": 1},
            notify_no_data=True,
            no_data_timeframe=60,
        ),
        note_state="OK",
    ))

    # Frontend Core Web Vitals (Warn)
    out.append(MonitorSpec(
        name="frontend LCP p75 above 2.5s",
        type="query alert",
        query=(
            "avg(last_15m):p75:rum.largest_contentful_paint"
            "{service:web-app,env:prod} > 2.5"
        ),
        message=(
            "p75 LCP above the 2.5s 'good' Web Vitals threshold. "
            "Possible regression from the recent bundle change."
        ),
        tags=["env:prod", "team:frontend", "service:web-app",
              "sev:3", "status:warn"],
        options=_common_options({"critical": 2.5, "warning": 1.8}),
        note_state="Warn",
    ))

    # SSL cert expiry (OK)
    out.append(MonitorSpec(
        name="ssl certificate days remaining",
        type="query alert",
        query=(
            "avg(last_1h):min:ssl.certificate.days_remaining"
            "{env:prod} < 14"
        ),
        message=(
            "Production cert has <14 days remaining. Renew before "
            "expiry. Owned by @infra."
        ),
        tags=["env:prod", "team:infra", "service:edge-tls",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 14, "warning": 30}),
        note_state="OK",
    ))

    # Kafka consumer lag (OK)
    out.append(MonitorSpec(
        name="kafka consumer lag (billing.events)",
        type="query alert",
        query=(
            "avg(last_10m):max:kafka.consumer.lag"
            "{topic:billing.events,env:prod} > 50000"
        ),
        message=(
            "Consumer lag on billing.events topic exceeds 50k "
            "messages. Check consumer group health."
        ),
        tags=["env:prod", "team:billing", "service:kafka",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 50000, "warning": 10000}),
        note_state="OK",
    ))

    # Background entitlement reconciliation success (Alert) - supports W2
    out.append(MonitorSpec(
        name="entitlement reconciler drift detected",
        type="query alert",
        query=(
            "sum(last_24h):sum:billing.entitlement.drift_detected"
            "{env:prod}.as_count() > 0"
        ),
        message=(
            "The hourly entitlement reconciler found accounts whose "
            "active Stripe subscription tier does not match the "
            "internal entitlement table. Each drift event includes "
            "customer_id in tags. Cross-reference with "
            "billing-webhook-handler error rate; drift events "
            "during webhook outages usually indicate ack'd-but-"
            "unprocessed payment events. See runbook "
            "WEBHOOK-CRASH-BACKFILL."
        ),
        tags=["env:prod", "team:billing", "service:billing-reconciler",
              "sev:2", "status:alert",
              "workflow:W2-northwind-webhook-ghost"],
        options=_common_options({"critical": 0},
                                renotify_interval=60),
        note_state="Alert",
    ))

    # Notifications service (OK)
    out.append(MonitorSpec(
        name="notifications fanout retry-queue depth",
        type="query alert",
        query=(
            "avg(last_15m):max:notifications.retry_queue.depth"
            "{env:prod} > 5000"
        ),
        message=(
            "Push/email/SMS retry queue depth >5000 messages. "
            "Investigate downstream provider failures."
        ),
        tags=["env:prod", "team:platform", "service:notifications",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 5000, "warning": 1000}),
        note_state="OK",
    ))

    # Search service p95 (OK)
    out.append(MonitorSpec(
        name="search-service p95 latency",
        type="query alert",
        query=(
            "avg(last_5m):p95:search.query.duration"
            "{service:search-service,env:prod} > 0.4"
        ),
        message=(
            "Search p95 above 400ms. Check shard balance and "
            "recent index changes."
        ),
        tags=["env:prod", "team:data", "service:search-service",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 0.4, "warning": 0.25}),
        note_state="OK",
    ))

    # CI/CD deploy failure (OK)
    out.append(MonitorSpec(
        name="ci-pipeline failure rate (main)",
        type="query alert",
        query=(
            "sum(last_1h):sum:ci.pipeline.failed"
            "{branch:main,env:prod}.as_count() > 3"
        ),
        message=(
            "More than 3 main-branch pipeline failures in the last "
            "hour. Possible bad merge - check #eng-builds."
        ),
        tags=["env:ci", "team:devex", "service:ci-pipeline",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 3, "warning": 1}),
        note_state="OK",
    ))

    # K8s pod restarts (Warn)
    out.append(MonitorSpec(
        name="kubernetes.pod restart loop",
        type="query alert",
        query=(
            "sum(last_30m):sum:kubernetes.containers.restarts"
            "{env:prod}.as_count() > 20"
        ),
        message=(
            "Excessive pod restarts in prod cluster. Investigate "
            "ImagePullBackOff and CrashLoopBackOff pods."
        ),
        tags=["env:prod", "team:infra", "service:k8s-prod",
              "sev:2", "status:warn"],
        options=_common_options({"critical": 20, "warning": 10}),
        note_state="Warn",
    ))

    # NAT gateway throughput (OK)
    out.append(MonitorSpec(
        name="aws nat-gateway bytes-out approaching limit",
        type="query alert",
        query=(
            "avg(last_10m):avg:aws.natgateway.bytes_out_to_destination"
            "{env:prod} > 4000000000"
        ),
        message=(
            "NAT gateway throughput approaching the 5GB/s soft "
            "ceiling. Consider scaling out or adding a parallel "
            "NAT in another AZ."
        ),
        tags=["env:prod", "team:infra", "service:aws-network",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 4000000000,
                                 "warning": 3000000000}),
        note_state="OK",
    ))

    # Stripe webhook signature failures (Warn) - adjacent to W2
    out.append(MonitorSpec(
        name="stripe-webhook-receiver signature verification failures",
        type="query alert",
        query=(
            "sum(last_15m):sum:stripe_webhook.signature.invalid"
            "{env:prod}.as_count() > 5"
        ),
        message=(
            "Multiple Stripe webhook signature verification "
            "failures. Either signing-secret rotation skew, "
            "replay attempt, or upstream malformed payloads."
        ),
        tags=["env:prod", "team:billing", "service:stripe-webhook-receiver",
              "sev:3", "status:warn"],
        options=_common_options({"critical": 5, "warning": 2}),
        note_state="Warn",
    ))

    # Mobile crash rate (OK)
    out.append(MonitorSpec(
        name="mobile crash-free sessions",
        type="query alert",
        query=(
            "avg(last_1h):avg:rum.crash_free_sessions_rate"
            "{service:mobile-ios,env:prod} < 0.995"
        ),
        message=(
            "iOS crash-free session rate below 99.5%. Check the "
            "latest Sentry release."
        ),
        tags=["env:prod", "team:mobile", "service:mobile-ios",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 0.995, "warning": 0.998}),
        note_state="OK",
    ))

    # Customer-facing 5xx (Warn)
    out.append(MonitorSpec(
        name="customer-facing 5xx error rate",
        type="query alert",
        query=(
            "avg(last_10m):sum:http.requests"
            "{status:5xx,env:prod,team:platform}.as_rate() > 1"
        ),
        message=(
            "Customer-facing 5xx error rate above 1/sec. Often a "
            "leading indicator for SLA breach."
        ),
        tags=["env:prod", "team:platform", "service:edge-router",
              "sev:2", "status:warn"],
        options=_common_options({"critical": 1, "warning": 0.5}),
        note_state="Warn",
    ))

    # Background data export job (OK)
    out.append(MonitorSpec(
        name="data-export job duration (Acme-class large customers)",
        type="query alert",
        query=(
            "avg(last_2h):max:job.data_export.duration_seconds"
            "{env:prod} > 3600"
        ),
        message=(
            "Data export jobs running longer than 1h. Large "
            "customers (e.g. Acme Genomics) request these - slow "
            "exports cause CSM escalations."
        ),
        tags=["env:prod", "team:data", "service:data-export",
              "sev:3", "status:ok"],
        options=_common_options({"critical": 3600, "warning": 1800}),
        note_state="OK",
    ))

    # SLO burn rate (OK)
    out.append(MonitorSpec(
        name="api-gateway SLO burn rate (1h+6h)",
        type="query alert",
        query=(
            "avg(last_1h):avg:slo.burn_rate"
            "{slo:api-gateway-availability,env:prod} > 14.4"
        ),
        message=(
            "Multi-window multi-burn-rate alert on the API gateway "
            "availability SLO. 1h burn at >14.4x = budget gone in "
            "~2 days at current rate."
        ),
        tags=["env:prod", "team:platform", "service:api-gateway",
              "sev:2", "status:ok"],
        options=_common_options({"critical": 14.4, "warning": 6.0}),
        note_state="OK",
    ))

    return out


# ──────────────────────────────────────────────────────────────────────
# Event catalog
# ──────────────────────────────────────────────────────────────────────


@dataclass
class EventSpec:
    title: str
    text: str
    date_happened: int
    tags: list[str]
    alert_type: str  # info | warning | error | success


def w2_deploy_event() -> EventSpec:
    return EventSpec(
        title="Deploy billing-webhook v3.2.1 - hotfix for unhandled TypeError",
        text=(
            f"Hotfix deployed at {W2_DEPLOY_TIME_NARRATIVE.isoformat()} by "
            "@platform-oncall. Resolves the error spike from "
            f"{W2_CRASH_START_NARRATIVE.isoformat()} through "
            f"{W2_CRASH_END_NARRATIVE.isoformat()} where the "
            "invoice.payment_succeeded handler threw `TypeError: "
            "Cannot read properties of undefined (reading 'tier')` "
            "on customer objects that did not include the optional "
            "`entitlement_hint` field.\n\n"
            "Impact during the outage: Stripe charge succeeded but "
            "internal entitlement table never updated. Customers "
            "stayed on their previous tier despite a successful "
            "charge. Backfill is manual via the runbook "
            "WEBHOOK-CRASH-BACKFILL.\n\n"
            "Linked monitor: 'billing-webhook-handler error rate "
            "elevated'. Linked workflow: W2-northwind-webhook-"
            "ghost. Affected customers include Northwind Logistics "
            "(charge succeeded ~10:23 UTC, entitlement never "
            "flipped).\n\n"
            "[Note: Datadog rejects backdated events more than ~18h "
            "in the past, so this event's posted timestamp differs "
            "from the narrative date above. The narrative date is "
            "the authoritative one.]"
        ),
        date_happened=_epoch(_hours_ago(4)),
        tags=[
            "service:billing-webhook-handler",
            "deploy",
            "env:prod",
            "team:platform",
            "sev:1-recovery",
            "workflow:W2-northwind-webhook-ghost",
            "version:v3.2.1",
            "narrative_date:2026-05-12",
        ],
        alert_type="success",
    )


def all_events() -> list[EventSpec]:
    """Build the event catalog.

    Datadog rejects ``date_happened`` more than ~18h in the past, so
    each event is posted relative to "now" but its **narrative date**
    (the date the event purports to describe) is baked into the title
    and text - exactly the pattern the Stripe seeder uses for
    ``metadata.simulated_created_at``.

    Hour-offsets below place the W2 sequence in a coherent local order:
        pre-crash deploy (v3.2.0)  → ~17h ago
        incident declared          → ~16h ago
        hotfix deploy (v3.2.1)     → ~4h ago
        incident resolved          → ~3h ago
    Noise events fill in around them.
    """
    out: list[EventSpec] = []
    nd = "narrative_date"  # tag-key shorthand

    # ── W2 narrative cluster ───────────────────────────────────────

    # 1. Pre-crash deploy that introduced the bug.
    out.append(EventSpec(
        title="Deploy billing-webhook v3.2.0",
        text=(
            "Routine deploy at 2026-05-10T17:00:00+00:00 (narrative "
            "date - actual Datadog timestamp is recent due to "
            "ingest-window limits). Adds optional "
            "`entitlement_hint` field handling to "
            "invoice.payment_succeeded. No incidents reported at "
            "deploy time. NOTE in hindsight: this is the change "
            "that introduced the unhandled TypeError fixed in "
            "v3.2.1."
        ),
        date_happened=_epoch(_hours_ago(17)),
        tags=["service:billing-webhook-handler", "deploy", "env:prod",
              "team:platform", "version:v3.2.0",
              f"{nd}:2026-05-10"],
        alert_type="info",
    ))

    # 2. W2 deploy (hotfix). This is the critical recovery signal.
    out.append(w2_deploy_event())

    # 3. Incident declaration during the W2 crash window.
    out.append(EventSpec(
        title="INC-2026-05-12-webhook declared (sev1)",
        text=(
            "Incident declared at 2026-05-12T10:24:00+00:00 "
            "(narrative). Monitor 'billing-webhook-handler error "
            "rate elevated' tripped at 50 errors/15min. IC: "
            "@platform-oncall. Customer impact: "
            "invoice.payment_succeeded handler ack'ing but failing "
            "to update entitlements. Slack channel: "
            "#inc-webhook-2026-05-12."
        ),
        date_happened=_epoch(_hours_ago(16)),
        tags=["service:billing-webhook-handler", "incident", "env:prod",
              "team:platform", "sev:1",
              "incident:INC-2026-05-12-webhook",
              "workflow:W2-northwind-webhook-ghost",
              f"{nd}:2026-05-12"],
        alert_type="error",
    ))

    # 4. Incident resolution.
    out.append(EventSpec(
        title="INC-2026-05-12-webhook resolved",
        text=(
            "Resolved at 2026-05-12T12:05:00+00:00 (narrative) "
            "following v3.2.1 hotfix deploy. Total impact window "
            "~90 minutes. Post-mortem scheduled. Action items: "
            "(1) backfill affected customer entitlements via "
            "runbook WEBHOOK-CRASH-BACKFILL, (2) add explicit "
            "schema validation on customer payloads, (3) raise "
            "entitlement drift monitor threshold sensitivity."
        ),
        date_happened=_epoch(_hours_ago(3)),
        tags=["service:billing-webhook-handler", "incident", "env:prod",
              "team:platform", "sev:1-recovery",
              "incident:INC-2026-05-12-webhook",
              "workflow:W2-northwind-webhook-ghost",
              f"{nd}:2026-05-12"],
        alert_type="success",
    ))

    # ── Other deploys (narrative dates spread Apr-May 2026) ───────

    deploys = [
        ("Deploy api-gateway v1.18.0",
         "Adds per-tenant rate limiting. Soak test green. "
         "Narrative date: 2026-04-28T14:30:00+00:00.",
         "api-gateway", "platform", "v1.18.0", "2026-04-28", 15.5),
        ("Deploy auth-service v2.7.3",
         "Token refresh latency improvement. Rolled to 100%. "
         "Narrative date: 2026-05-04T16:00:00+00:00.",
         "auth-service", "auth", "v2.7.3", "2026-05-04", 14.0),
        ("Deploy billing-core v4.11.2",
         "Adds proration handling for mid-cycle plan changes. "
         "Narrative date: 2026-05-06T09:00:00+00:00.",
         "billing-core", "billing", "v4.11.2", "2026-05-06", 13.5),
        ("Deploy notifications v0.9.4",
         "Switches SMS provider for India routes. "
         "Narrative date: 2026-05-08T11:00:00+00:00.",
         "notifications", "platform", "v0.9.4", "2026-05-08", 13.0),
        ("Deploy search-service v3.0.1",
         "Shard rebalance + minor query parser fix. "
         "Narrative date: 2026-05-09T10:00:00+00:00.",
         "search-service", "data", "v3.0.1", "2026-05-09", 12.5),
        ("Deploy web-app v6.42.0",
         "Bundle size reduction; LCP regression watch. "
         "Narrative date: 2026-05-14T15:00:00+00:00.",
         "web-app", "frontend", "v6.42.0", "2026-05-14", 8.0),
        ("Deploy billing-reconciler v1.4.0",
         "Doubles run cadence to hourly. Helps detect entitlement "
         "drift earlier (see WEBHOOK-CRASH-BACKFILL). "
         "Narrative date: 2026-05-18T13:00:00+00:00.",
         "billing-reconciler", "billing", "v1.4.0", "2026-05-18", 7.0),
        ("Deploy stripe-webhook-receiver v2.3.0",
         "Bumps Stripe API version to 2026-04-30. No customer "
         "impact expected. Narrative date: "
         "2026-05-21T18:30:00+00:00.",
         "stripe-webhook-receiver", "billing", "v2.3.0", "2026-05-21",
         6.0),
        ("Deploy mobile-ios v7.1.0",
         "Adds biometric re-auth. Crash-free rate stable. "
         "Narrative date: 2026-05-24T10:00:00+00:00.",
         "mobile-ios", "mobile", "v7.1.0", "2026-05-24", 5.0),
    ]
    for title, text, service, team, version, narr, hrs in deploys:
        out.append(EventSpec(
            title=title,
            text=text,
            date_happened=_epoch(_hours_ago(hrs)),
            tags=[f"service:{service}", "deploy", "env:prod",
                  f"team:{team}", f"version:{version}",
                  f"{nd}:{narr}"],
            alert_type="info",
        ))

    # ── Other incidents - unrelated noise ─────────────────────────

    out.append(EventSpec(
        title="INC-2026-04-30-search declared",
        text=(
            "Narrative date: 2026-04-30T19:00:00+00:00. Search "
            "latency spike during the daily reindex. Caused by a "
            "noisy-neighbor on the elasticsearch cluster. "
            "Mitigated by moving the noisy job to off-peak."
        ),
        date_happened=_epoch(_hours_ago(15.2)),
        tags=["service:search-service", "incident", "env:prod",
              "team:data", "sev:3", f"{nd}:2026-04-30"],
        alert_type="warning",
    ))
    out.append(EventSpec(
        title="INC-2026-05-02-auth declared",
        text=(
            "Narrative date: 2026-05-02T08:12:00+00:00. Brief "
            "token issuance latency spike from a Redis failover. "
            "Auto-recovered in <2 minutes."
        ),
        date_happened=_epoch(_hours_ago(14.5)),
        tags=["service:auth-service", "incident", "env:prod",
              "team:auth", "sev:3", f"{nd}:2026-05-02"],
        alert_type="warning",
    ))
    out.append(EventSpec(
        title="INC-2026-05-02-auth resolved",
        text=(
            "Narrative date: 2026-05-02T08:14:00+00:00. Resolved "
            "at 08:14 UTC. No customer-reported impact."
        ),
        date_happened=_epoch(_hours_ago(14.45)),
        tags=["service:auth-service", "incident", "env:prod",
              "team:auth", "sev:3-recovery", f"{nd}:2026-05-02"],
        alert_type="success",
    ))
    out.append(EventSpec(
        title="INC-2026-05-20-mobile push outage declared",
        text=(
            "Narrative date: 2026-05-20T06:30:00+00:00. FCM "
            "delivery failure rate >40% for ~30 min after Google "
            "Cloud regional issue."
        ),
        date_happened=_epoch(_hours_ago(6.5)),
        tags=["service:notifications", "incident", "env:prod",
              "team:platform", "sev:2", f"{nd}:2026-05-20"],
        alert_type="error",
    ))

    # ── Capacity adjustments ──────────────────────────────────────

    out.append(EventSpec(
        title="Scale-out: api-gateway desired pods 12 -> 18",
        text=(
            "Narrative date: 2026-05-11T22:00:00+00:00. Manual "
            "scale ahead of expected traffic spike from a "
            "marketing campaign launch."
        ),
        date_happened=_epoch(_hours_ago(11.0)),
        tags=["service:api-gateway", "capacity", "env:prod",
              "team:platform", f"{nd}:2026-05-11"],
        alert_type="info",
    ))
    out.append(EventSpec(
        title="Scale-out: background-worker desired pods 8 -> 16",
        text=(
            "Narrative date: 2026-05-15T16:30:00+00:00. Queue "
            "depth on default queue stayed >500 for over an hour. "
            "Auto-scaler limits raised."
        ),
        date_happened=_epoch(_hours_ago(8.5)),
        tags=["service:background-worker", "capacity", "env:prod",
              "team:platform", f"{nd}:2026-05-15"],
        alert_type="info",
    ))
    out.append(EventSpec(
        title="Postgres-billing storage extended +500GB",
        text=(
            "Narrative date: 2026-05-17T04:00:00+00:00. Routine "
            "storage extension to keep utilization under 70%. No "
            "downtime."
        ),
        date_happened=_epoch(_hours_ago(7.5)),
        tags=["service:postgres-billing", "capacity", "env:prod",
              "team:platform", f"{nd}:2026-05-17"],
        alert_type="info",
    ))

    # ── Security / config events ──────────────────────────────────

    out.append(EventSpec(
        title="Stripe webhook signing secret rotated",
        text=(
            "Narrative date: 2026-05-05T17:00:00+00:00. Routine "
            "rotation of the Stripe webhook signing secret for "
            "stripe-webhook-receiver. Old secret retired after "
            "24h grace window."
        ),
        date_happened=_epoch(_hours_ago(13.7)),
        tags=["service:stripe-webhook-receiver", "config", "env:prod",
              "team:billing", "security", f"{nd}:2026-05-05"],
        alert_type="info",
    ))
    out.append(EventSpec(
        title="JWT signing key rotation completed",
        text=(
            "Narrative date: 2026-05-16T12:00:00+00:00. Quarterly "
            "JWT signing key rotation. All issued tokens from the "
            "previous key honored until natural expiry."
        ),
        date_happened=_epoch(_hours_ago(7.7)),
        tags=["service:auth-service", "config", "env:prod",
              "team:auth", "security", f"{nd}:2026-05-16"],
        alert_type="info",
    ))

    # ── Maintenance ───────────────────────────────────────────────

    out.append(EventSpec(
        title="Scheduled maintenance: search-service reindex",
        text=(
            "Narrative date: 2026-05-25T03:00:00+00:00. Full "
            "reindex of the primary corpus. Expected "
            "search-degradation window 03:00-04:30 UTC."
        ),
        date_happened=_epoch(_hours_ago(4.5)),
        tags=["service:search-service", "maintenance", "env:prod",
              "team:data", f"{nd}:2026-05-25"],
        alert_type="info",
    ))

    # ── Operational notes that the agent should surface ──────────

    out.append(EventSpec(
        title="Runbook updated: WEBHOOK-CRASH-BACKFILL",
        text=(
            "Narrative date: 2026-05-13T09:00:00+00:00. Updated "
            "post-mortem actions following "
            "INC-2026-05-12-webhook. Adds explicit guidance: when "
            "an invoice.payment_succeeded webhook fails during a "
            "service outage, customers whose Stripe charge "
            "succeeded but entitlement did not update should be "
            "FULL-REFUNDED + manually upgraded + sent the "
            "vendor-failure apology template. DO NOT contest a "
            "chargeback in this scenario - it is a vendor failure, "
            "not friendly fraud."
        ),
        date_happened=_epoch(_hours_ago(2.5)),
        tags=["service:billing-webhook-handler", "runbook", "env:prod",
              "team:billing", "workflow:W2-northwind-webhook-ghost",
              f"{nd}:2026-05-13"],
        alert_type="info",
    ))

    out.append(EventSpec(
        title="Feature flag: entitlement_strict_mode rolled to 100%",
        text=(
            "Narrative date: 2026-05-19T14:00:00+00:00. "
            "Strict-mode entitlement validation on every API "
            "request. Catches drift earlier - would have surfaced "
            "the 2026-05-12 webhook outage at first impacted "
            "request rather than at next reconciler tick."
        ),
        date_happened=_epoch(_hours_ago(6.8)),
        tags=["service:billing-core", "feature-flag", "env:prod",
              "team:billing", f"{nd}:2026-05-19"],
        alert_type="info",
    ))

    out.append(EventSpec(
        title="On-call rotation: @platform-oncall transitioned",
        text=(
            "Narrative date: 2026-05-11T17:00:00+00:00. Weekly "
            "handoff. New primary: @joel. Secondary: @ananya."
        ),
        date_happened=_epoch(_hours_ago(11.5)),
        tags=["team:platform", "on-call", "env:prod",
              f"{nd}:2026-05-11"],
        alert_type="info",
    ))

    return out


# ──────────────────────────────────────────────────────────────────────
# Dashboard catalog
# ──────────────────────────────────────────────────────────────────────


def _timeseries(title: str, query: str) -> dict:
    return {
        "definition": {
            "type": "timeseries",
            "requests": [
                {
                    "q": query,
                    "display_type": "line",
                    "style": {"palette": "dog_classic",
                              "line_type": "solid", "line_width": "normal"},
                }
            ],
            "title": title,
            "show_legend": True,
        }
    }


def _query_value(title: str, query: str, precision: int = 2) -> dict:
    return {
        "definition": {
            "type": "query_value",
            "requests": [{"q": query, "aggregator": "avg"}],
            "title": title,
            "precision": precision,
            "autoscale": True,
        }
    }


def _note(content: str) -> dict:
    return {
        "definition": {
            "type": "note",
            "content": content,
            "background_color": "yellow",
            "font_size": "14",
            "text_align": "left",
            "show_tick": False,
            "tick_pos": "50%",
            "tick_edge": "left",
        }
    }


def all_dashboards() -> list[dict]:
    """Each dashboard is a full create-payload dict."""
    out: list[dict] = []

    # 1. Engineering - Reliability Overview
    out.append({
        "title": "Engineering - Reliability Overview",
        "description": (
            "Cross-service reliability snapshot: 5xx rate, p95 "
            "latency, deploy frequency, and outstanding incidents. "
            "Owned by @platform."
        ),
        "layout_type": "ordered",
        "widgets": [
            _note(
                "**Reliability overview.** Watch the 5xx rate "
                "first - it's the leading indicator. p95 latency "
                "and queue depth are second."
            ),
            _timeseries(
                "Customer-facing 5xx rate",
                "sum:http.requests{status:5xx,env:prod}.as_rate()"),
            _timeseries(
                "API gateway p95 latency",
                "p95:trace.http.request.duration"
                "{service:api-gateway,env:prod}"),
            _query_value(
                "Active incidents (last 24h)",
                "sum:incident.active{env:prod}.as_count()"),
            _timeseries(
                "Background worker queue depth",
                "max:celery.queue.depth{env:prod}"),
        ],
        "tags": ["team:platform"],
    })

    # 2. Billing - Webhook health (THE W2 dashboard)
    out.append({
        "title": "Billing - Webhook health",
        "description": (
            "Health of inbound and outbound webhook handlers. "
            "Cross-references entitlement drift and Stripe charge "
            "success. If 5xx rate and drift events spike together, "
            "you have a vendor-failure / ghost-paid situation - "
            "see runbook WEBHOOK-CRASH-BACKFILL. Workflow: "
            "W2-northwind-webhook-ghost."
        ),
        "layout_type": "ordered",
        "widgets": [
            _note(
                "**Webhook health.** Correlate 5xx with "
                "entitlement drift. Drift during a 5xx spike = "
                "customers were charged but never upgraded."
            ),
            _timeseries(
                "billing-webhook-handler 5xx rate",
                "sum:billing.webhook.errors.5xx"
                "{service:billing-webhook-handler,env:prod}.as_rate()"),
            _timeseries(
                "invoice.payment_succeeded ack vs processed",
                "sum:billing.webhook.acked{event:invoice.payment_succeeded,env:prod}.as_rate(),"
                "sum:billing.webhook.processed{event:invoice.payment_succeeded,env:prod}.as_rate()"),
            _timeseries(
                "Entitlement drift events detected",
                "sum:billing.entitlement.drift_detected{env:prod}.as_count()"),
            _query_value(
                "Webhook handler current error rate (req/sec)",
                "sum:billing.webhook.errors.5xx"
                "{service:billing-webhook-handler,env:prod}.as_rate()"),
        ],
        "tags": ["team:billing"],
    })

    # 3. Platform - Latency
    out.append({
        "title": "Platform - Latency",
        "description": (
            "End-to-end latency budget by service. Stripe API "
            "calls, Postgres queries, Redis hits. Trace-derived."
        ),
        "layout_type": "ordered",
        "widgets": [
            _timeseries(
                "api-gateway p95 / p99",
                "p95:trace.http.request.duration{service:api-gateway,env:prod},"
                "p99:trace.http.request.duration{service:api-gateway,env:prod}"),
            _timeseries(
                "billing-core Stripe API p95",
                "p95:stripe.api.call.duration{env:prod}"),
            _timeseries(
                "postgres-billing query p95",
                "p95:postgresql.query.duration{db:billing,env:prod}"),
            _timeseries(
                "redis-session p99",
                "p99:redis.command.duration{service:redis-session,env:prod}"),
        ],
        "tags": ["team:platform"],
    })

    # 4. Security - Auth health
    out.append({
        "title": "Security - Auth health",
        "description": (
            "Authentication and authorization health. Failed "
            "logins, token issuance latency, key rotation events."
        ),
        "layout_type": "ordered",
        "widgets": [
            _timeseries(
                "Failed logins / sec",
                "sum:auth.login.failed{env:prod}.as_rate()"),
            _timeseries(
                "Token issuance p99",
                "p99:auth.token.issue.duration{service:auth-service,env:prod}"),
            _query_value(
                "Active sessions",
                "avg:auth.sessions.active{env:prod}"),
            _timeseries(
                "JWT verifications / sec",
                "sum:auth.jwt.verified{env:prod}.as_rate()"),
        ],
        "tags": ["team:auth", "team:security"],
    })

    # 5. Billing - Disputes & Reconciliation
    out.append({
        "title": "Billing - Disputes & Reconciliation",
        "description": (
            "Stripe disputes received, reconciler drift events, "
            "and refund volume. Useful for billing-ops triage."
        ),
        "layout_type": "ordered",
        "widgets": [
            _timeseries(
                "Disputes received (Stripe webhook)",
                "sum:stripe.dispute.created{env:prod}.as_count()"),
            _timeseries(
                "Refunds issued",
                "sum:stripe.refund.created{env:prod}.as_count()"),
            _timeseries(
                "Entitlement reconciler drift detected",
                "sum:billing.entitlement.drift_detected{env:prod}.as_count()"),
            _query_value(
                "Disputes open right now",
                "sum:stripe.dispute.open{env:prod}"),
        ],
        "tags": ["team:billing"],
    })

    return out


# ──────────────────────────────────────────────────────────────────────
# Lookups (for idempotency)
# ──────────────────────────────────────────────────────────────────────


_MONITOR_INDEX: dict[str, int] = {}
_MONITOR_INDEX_LOADED = False


def _load_monitor_index(client: httpx.Client) -> None:
    """List all monitors once and index by name. Datadog's
    /monitor/search endpoint doesn't accept the `name:"..."` filter on
    this org tier, so we list and filter client-side."""
    global _MONITOR_INDEX_LOADED
    if _MONITOR_INDEX_LOADED:
        return
    page = 0
    while True:
        r = _request(
            client, "GET", "/api/v1/monitor",
            params={"page": page, "page_size": 100}
        )
        if r.status_code != 200:
            print(f"  monitor index load failed page={page}: "
                  f"{r.status_code}")
            break
        items = r.json()
        if not items:
            break
        for m in items:
            name = m.get("name")
            mid = m.get("id")
            if name and mid is not None:
                _MONITOR_INDEX[name] = mid
        if len(items) < 100:
            break
        page += 1
    _MONITOR_INDEX_LOADED = True


def find_monitor_by_name(client: httpx.Client, name: str) -> int | None:
    _load_monitor_index(client)
    return _MONITOR_INDEX.get(name)


def find_event_by_title(
    client: httpx.Client, title: str, when_epoch: int
) -> int | None:
    """Look up an existing event by exact title within a wide window
    around when_epoch. Returns the event id, or None if not found."""
    start = when_epoch - 86400
    end = when_epoch + 86400
    r = _request(
        client, "GET", "/api/v1/events",
        params={"start": start, "end": end}
    )
    if r.status_code != 200:
        return None
    events = r.json().get("events", [])
    for e in events:
        if e.get("title") == title:
            return e.get("id")
    return None


def find_dashboard_by_title(client: httpx.Client, title: str) -> str | None:
    r = _request(client, "GET", "/api/v1/dashboard")
    if r.status_code != 200:
        return None
    for d in r.json().get("dashboards", []):
        if d.get("title") == title:
            return d.get("id")
    return None


# ──────────────────────────────────────────────────────────────────────
# Creators
# ──────────────────────────────────────────────────────────────────────


def upsert_monitor(
    client: httpx.Client, spec: MonitorSpec
) -> tuple[int | None, str]:
    """Returns (id, 'created' | 'updated' | 'error')."""
    existing_id = find_monitor_by_name(client, spec.name)
    body = {
        "name": spec.name,
        "type": spec.type,
        "query": spec.query,
        "message": spec.message,
        "tags": spec.tags,
        "options": spec.options,
        "priority": 1 if "sev:1" in spec.tags else (
            2 if "sev:2" in spec.tags else 3),
    }
    if existing_id:
        r = _request(client, "PUT", f"/api/v1/monitor/{existing_id}",
                     json=body)
        if r.status_code in (200, 201):
            return existing_id, "updated"
        print(f"  update failed for {spec.name!r}: "
              f"{r.status_code} {r.text[:200]}")
        return existing_id, "error"
    r = _request(client, "POST", "/api/v1/monitor", json=body)
    if r.status_code in (200, 201):
        mid = r.json().get("id")
        if mid is not None:
            _MONITOR_INDEX[spec.name] = mid
        return mid, "created"
    print(f"  create failed for {spec.name!r}: "
          f"{r.status_code} {r.text[:200]}")
    return None, "error"


def post_event(
    client: httpx.Client, spec: EventSpec
) -> tuple[int | None, str]:
    existing_id = find_event_by_title(client, spec.title, spec.date_happened)
    if existing_id:
        return existing_id, "exists"
    body = {
        "title": spec.title,
        "text": spec.text,
        "date_happened": spec.date_happened,
        "tags": spec.tags,
        "alert_type": spec.alert_type,
        "source_type_name": "my apps",
    }
    r = _request(client, "POST", "/api/v1/events", json=body)
    if r.status_code in (200, 201, 202):
        ev = r.json().get("event") or {}
        return ev.get("id"), "created"
    print(f"  event create failed for {spec.title!r}: "
          f"{r.status_code} {r.text[:200]}")
    return None, "error"


def upsert_dashboard(
    client: httpx.Client, payload: dict
) -> tuple[str | None, str]:
    title = payload["title"]
    existing_id = find_dashboard_by_title(client, title)
    if existing_id:
        r = _request(
            client, "PUT", f"/api/v1/dashboard/{existing_id}", json=payload
        )
        if r.status_code in (200, 201):
            return existing_id, "updated"
        print(f"  dashboard update failed for {title!r}: "
              f"{r.status_code} {r.text[:200]}")
        return existing_id, "error"
    r = _request(client, "POST", "/api/v1/dashboard", json=payload)
    if r.status_code in (200, 201):
        return r.json().get("id"), "created"
    print(f"  dashboard create failed for {title!r}: "
          f"{r.status_code} {r.text[:200]}")
    return None, "error"


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    print(f"Datadog site: {SITE}")
    print(f"W2 workflow target: {WORKFLOWS['W2'].case_id}")
    print()

    monitor_specs = all_monitors()
    event_specs = all_events()
    dashboard_payloads = all_dashboards()

    print(f"Seeding {len(monitor_specs)} monitors, "
          f"{len(event_specs)} events, "
          f"{len(dashboard_payloads)} dashboards…")
    print()

    counts = {
        "monitor_created": 0, "monitor_updated": 0, "monitor_error": 0,
        "event_created": 0, "event_exists": 0, "event_error": 0,
        "dash_created": 0, "dash_updated": 0, "dash_error": 0,
    }
    errors: list[str] = []
    w2_monitor_id: int | None = None
    w2_event_id: int | None = None

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # ── Monitors ──
        print("── Monitors ──")
        for spec in monitor_specs:
            mid, action = upsert_monitor(client, spec)
            counts[f"monitor_{action}"] = counts.get(
                f"monitor_{action}", 0) + 1
            tag_summary = ",".join(
                t for t in spec.tags
                if t.startswith(("team:", "service:", "sev:", "status:"))
            )
            mid_disp = mid if mid is not None else "-"
            print(f"  [{action:7s}] id={mid_disp!s:>8s}  "
                  f"{spec.name}  [{tag_summary}]  ({spec.note_state})")
            if (spec.name == "billing-webhook-handler error rate elevated"
                    and mid):
                w2_monitor_id = mid
            if action == "error":
                errors.append(f"monitor:{spec.name}")

        # ── Events ──
        print("\n── Events ──")
        for spec in event_specs:
            eid, action = post_event(client, spec)
            counts[f"event_{action}"] = counts.get(
                f"event_{action}", 0) + 1
            tag_summary = ",".join(
                t for t in spec.tags
                if t.startswith(("service:", "team:", "deploy",
                                 "incident", "workflow:"))
            )[:90]
            eid_disp = eid if eid is not None else "-"
            print(f"  [{action:7s}] id={eid_disp!s:>14s}  "
                  f"{spec.title[:60]}  [{tag_summary}]")
            if (spec.title.startswith(
                    "Deploy billing-webhook v3.2.1")
                    and eid):
                w2_event_id = eid
            if action == "error":
                errors.append(f"event:{spec.title}")

        # ── Dashboards ──
        print("\n── Dashboards ──")
        for payload in dashboard_payloads:
            did, action = upsert_dashboard(client, payload)
            counts[f"dash_{action}"] = counts.get(
                f"dash_{action}", 0) + 1
            did_disp = did if did is not None else "-"
            print(f"  [{action:7s}] id={did_disp!s:>12s}  "
                  f"{payload['title']}")
            if action == "error":
                errors.append(f"dashboard:{payload['title']}")

    # ── Summary ──
    print("\n" + "═" * 70)
    print("SUMMARY")
    print("═" * 70)
    print(
        f"Monitors  : created={counts['monitor_created']:2d}  "
        f"updated={counts['monitor_updated']:2d}  "
        f"errors={counts['monitor_error']:2d}"
    )
    print(
        f"Events    : created={counts['event_created']:2d}  "
        f"exists={counts['event_exists']:2d}  "
        f"errors={counts['event_error']:2d}"
    )
    print(
        f"Dashboards: created={counts['dash_created']:2d}  "
        f"updated={counts['dash_updated']:2d}  "
        f"errors={counts['dash_error']:2d}"
    )

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  …and {len(errors) - 20} more")

    print("\nW2 workflow signal verification:")
    print(f"  W2 monitor id: {w2_monitor_id}")
    print("    name        : billing-webhook-handler error rate elevated")
    print("    crash window: "
          f"{W2_CRASH_START_NARRATIVE.isoformat()} → "
          f"{W2_CRASH_END_NARRATIVE.isoformat()}")
    print(f"  W2 deploy event id: {w2_event_id}")
    print("    title       : Deploy billing-webhook v3.2.1 - "
          "hotfix for unhandled TypeError")
    print(f"    narrative time: {W2_DEPLOY_TIME_NARRATIVE.isoformat()}")
    print()

    # Verify the W2 signal monitor exists and is queryable
    if w2_monitor_id:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
            r = _request(client, "GET",
                         f"/api/v1/monitor/{w2_monitor_id}")
            if r.status_code == 200:
                m = r.json()
                tags_ok = "workflow:W2-northwind-webhook-ghost" in (
                    m.get("tags") or [])
                msg_ok = (
                    "Cannot read properties of undefined" in (
                        m.get("message") or "")
                    or "TypeError" in (m.get("message") or "")
                )
                print(f"  W2 monitor verified: tags_ok={tags_ok} "
                      f"msg_ok={msg_ok} status={m.get('overall_state')}")
            else:
                print(f"  W2 monitor verify failed: {r.status_code}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
