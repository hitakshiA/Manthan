"""Seed Sentry for the Manthan billing-dispute investigation agent.

Creates a realistic Sentry footprint for the `miny-labs` org on the US
shard (https://us.sentry.io). The W2 workflow - Northwind Logistics
ghost-paid for an Enterprise upgrade because our webhook handler choked -
relies on a crash being visible in Sentry around the May 12 charge time,
so this seeder bakes that signal in.

What gets created:

  * Teams (idempotent - reuses existing teams)
      - miny-labs   (auto-created with the org; reused as-is)
      - platform    (Platform Eng - created if missing)

  * Projects (5; all under the platform team - Python except frontend-web)
      - billing-webhook-svc   ← W2 lives here
      - api-gateway
      - ingest-pipeline
      - frontend-web          (javascript)
      - auth-svc

  * Issues (~180 unique fingerprints, ~2500 total events)
      Each unique (exception type, message) tuple becomes one Sentry
      issue. We send N events per pattern so issue counts vary across
      a realistic distribution. Sentry's `last_seen` for new captures is
      always "now" - we accept that limitation per the spec.

  * W2 signal
      A dominating issue on billing-webhook-svc:
        TypeError: 'NoneType' object has no attribute 'payment_method'
      raised from stripe_webhook_handler.process_invoice_payment_succeeded.
      ~30 events, several tagged with customer_id=cus_test_northwind_logi
      and webhook_payload context referencing the invoice. Mentions of the
      2026-05-12 10:00 window are included in the message text so the
      agent finds it when grep'ing the recent issue list around the
      charge time.

Auth: SENTRY_TOKEN (User Auth Token, `sntryu_...`) in agent/.env
Region: US shard - `https://us.sentry.io/api/0/`

Run:
    .venv/bin/python scripts/seed_sentry.py
"""

from __future__ import annotations

import os
import random
import sys
import time
import warnings
from pathlib import Path

# sentry-sdk 2.x deprecates `push_scope` and `Hub.current` but both still
# work and are concise for our purposes (one-shot seed script). Silence
# the warnings so the run output stays readable.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="sentry_sdk")
warnings.filterwarnings(
    "ignore",
    message=".*sentry_sdk\\.Hub.*",
)
warnings.filterwarnings(
    "ignore",
    message=".*sentry_sdk\\.push_scope.*",
)

import httpx  # noqa: E402
import sentry_sdk  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

ENV_PATH = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_PATH)

TOKEN = os.getenv("SENTRY_TOKEN")
ORG = os.getenv("SENTRY_ORG", "miny-labs")
if not TOKEN:
    sys.exit("ERROR: SENTRY_TOKEN missing from .env")

# IMPORTANT - this org lives on the US shard. The plain `sentry.io` host
# is the routing/control plane; data + most endpoints live behind the
# regional host. Use `us.sentry.io` for everything here.
API_BASE = "https://us.sentry.io/api/0"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Sentry's per-project free-tier event ingest is ~5 req/s. We stay well
# under that with explicit sleeps between captures.
INGEST_SLEEP = 0.05  # 20 req/s ceiling - Sentry buffers this fine

# Where in the May 2026 window the W2 charge landed.
W2_CHARGE_WINDOW = "2026-05-12T10:00"
W2_CUSTOMER_ID = "cus_test_northwind_logi"
W2_INVOICE_ID = "in_1OqM8Z2eZvKYlo2C9Pq3xT4w"

TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Deterministic but interesting variation.
random.seed(2026_05_27)


# ──────────────────────────────────────────────────────────────────────
# HTTP helpers (control-plane: teams, projects, keys)
# ──────────────────────────────────────────────────────────────────────


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    retries: int = 3,
) -> httpx.Response:
    """HTTP with backoff on 429 / 5xx."""
    url = path if path.startswith("http") else f"{API_BASE}{path}"
    last: httpx.Response | None = None
    for attempt in range(retries):
        r = client.request(method, url, json=json)
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


def ping_org(client: httpx.Client) -> None:
    """Sanity-check auth + region before doing anything else."""
    r = _request(client, "GET", f"/organizations/{ORG}/")
    if r.status_code != 200:
        sys.exit(
            f"ERROR: Sentry org ping failed: {r.status_code} {r.text[:200]}\n"
            "Check SENTRY_TOKEN scope and that you're hitting us.sentry.io."
        )
    name = r.json().get("name", "?")
    print(f"  connected to Sentry org: {name} ({ORG})")


# ──────────────────────────────────────────────────────────────────────
# Teams
# ──────────────────────────────────────────────────────────────────────


def list_teams(client: httpx.Client) -> list[dict]:
    r = _request(client, "GET", f"/organizations/{ORG}/teams/")
    r.raise_for_status()
    return r.json()


def ensure_team(client: httpx.Client, name: str, slug: str) -> dict:
    """Create the team if it doesn't already exist. Idempotent."""
    existing = {t["slug"]: t for t in list_teams(client)}
    if slug in existing:
        print(f"  team {slug!r} already exists")
        return existing[slug]
    r = _request(
        client,
        "POST",
        f"/organizations/{ORG}/teams/",
        json={"name": name, "slug": slug},
    )
    if r.status_code in (200, 201):
        print(f"  created team {slug!r}")
        return r.json()
    # 409 / 400 with "already exists" - refetch.
    if r.status_code in (400, 409):
        existing = {t["slug"]: t for t in list_teams(client)}
        if slug in existing:
            return existing[slug]
    sys.exit(f"ERROR creating team {slug}: {r.status_code} {r.text[:300]}")


# ──────────────────────────────────────────────────────────────────────
# Projects
# ──────────────────────────────────────────────────────────────────────


def list_projects(client: httpx.Client) -> list[dict]:
    r = _request(client, "GET", f"/organizations/{ORG}/projects/")
    r.raise_for_status()
    return r.json()


def ensure_project(
    client: httpx.Client,
    team_slug: str,
    name: str,
    slug: str,
    platform: str,
) -> dict:
    """Create the project if missing. Idempotent."""
    existing = {p["slug"]: p for p in list_projects(client)}
    if slug in existing:
        print(f"  project {slug!r} already exists")
        return existing[slug]
    r = _request(
        client,
        "POST",
        f"/teams/{ORG}/{team_slug}/projects/",
        json={"name": name, "slug": slug, "platform": platform},
    )
    if r.status_code in (200, 201):
        print(f"  created project {slug!r} (platform={platform})")
        return r.json()
    if r.status_code in (400, 409):
        existing = {p["slug"]: p for p in list_projects(client)}
        if slug in existing:
            return existing[slug]
    sys.exit(f"ERROR creating project {slug}: {r.status_code} {r.text[:300]}")


def get_project_dsn(client: httpx.Client, project_slug: str) -> str:
    """Fetch the public DSN for a project."""
    r = _request(client, "GET", f"/projects/{ORG}/{project_slug}/keys/")
    r.raise_for_status()
    keys = r.json()
    if not keys:
        sys.exit(f"ERROR: project {project_slug} has no client keys")
    # First key is the default ("Default"); use its public DSN.
    dsn = keys[0]["dsn"]["public"]
    return dsn


# ──────────────────────────────────────────────────────────────────────
# Issue patterns
#
# Each entry: (exc_type, message, level, weight)
#   weight is the relative event count this fingerprint should get.
#   We sample event counts around `weight` to produce a realistic
#   long-tail distribution (lots of low-count noise, a few loud ones).
# ──────────────────────────────────────────────────────────────────────

# Severity weights for variety - Sentry treats these as event "level".
LEVELS_COMMON = ["error", "error", "error", "warning", "info"]


def _patterns_for(project_slug: str) -> list[tuple[str, str, str, int]]:
    """Return a per-project list of (exc_type, message, level, weight).

    Patterns are flavored to the service so the agent sees plausible
    error signatures when it grep's a project's recent issues. The
    fingerprints are unique by (exc_type, message) - that's how Sentry
    groups events into issues.
    """
    if project_slug == "billing-webhook-svc":
        return [
            # - These are noise the agent will scroll past -
            ("KeyError", "Missing 'amount_received' in invoice.payment_failed payload", "error", 18),
            ("ValueError", "Stripe signature header missing on /webhook/stripe POST", "warning", 12),
            ("requests.exceptions.ConnectionError", "Connection reset by stripe.com:443 during signature verify", "error", 9),
            ("TimeoutError", "Webhook handler exceeded 30s budget on subscription.updated", "error", 14),
            ("KeyError", "Missing 'period' field in invoice.created webhook", "warning", 7),
            ("AssertionError", "Idempotency key collision in webhook_dispatch", "error", 5),
            ("json.JSONDecodeError", "Expecting value: line 1 column 1 (char 0) - empty webhook body", "warning", 11),
            ("psycopg2.errors.DeadlockDetected", "Deadlock detected upserting customer_entitlement", "error", 4),
            ("ValueError", "Unknown event type 'invoice.payment_pending' - no handler registered", "info", 16),
            ("AttributeError", "'WebhookEvent' object has no attribute 'livemode'", "warning", 6),
            ("KeyError", "Missing 'subscription' on charge.refunded event", "error", 8),
            ("ConnectionResetError", "[Errno 54] Connection reset by peer talking to entitlement-svc", "error", 13),
            ("requests.exceptions.HTTPError", "503 Service Unavailable from entitlement-svc /v1/grant", "error", 10),
            ("TypeError", "unsupported operand type(s) for +: 'int' and 'NoneType' in usage_aggregator", "warning", 5),
            ("ValueError", "Negative quantity on metered_usage record id=mu_9f3a", "error", 3),
            ("OperationalError", "could not connect to server: Connection refused (entitlements_db)", "error", 7),
            ("KeyError", "Missing 'tier' in plan_to_tier_map for plan_pro_2024_v3", "warning", 4),
            ("ValueError", "Refusing to process webhook with livemode=true while WEBHOOK_LIVEMODE_OK=false", "warning", 6),
            ("RuntimeError", "Outbox publisher lag > 60s on topic billing.entitlement.changed", "warning", 9),
            ("KeyError", "Missing 'invoice' on charge.dispute.created event payload", "error", 5),
            ("ValueError", "Webhook signature timestamp drift > 300s - rejecting", "warning", 8),
            ("psycopg2.errors.UniqueViolation", "duplicate key (event_id) on stripe_webhook_events insert", "warning", 12),
            ("AttributeError", "'Subscription' object has no attribute 'pause_collection'", "error", 4),
            ("TimeoutError", "Lock acquisition on subscription_state row timed out after 5s", "warning", 7),
            ("KeyError", "Missing 'previous_attributes' in customer.subscription.updated", "info", 14),
            ("ValueError", "Refund amount exceeds original charge for ch_3OqM... - rejecting", "error", 3),
            ("RuntimeError", "Dead letter queue overflow on stripe.webhook.retry topic", "error", 4),
            ("KeyError", "Missing 'metadata' on payment_intent.succeeded - cannot route to tenant", "warning", 9),
            ("ValueError", "Webhook event id 'evt_legacy_3iU' format unrecognized (pre-2024)", "info", 8),
            ("AttributeError", "'Charge' object has no attribute 'application_fee_amount' in v23 API", "warning", 5),
            ("TimeoutError", "Async entitlement update queued > 60s - retrying", "warning", 11),
        ]
    if project_slug == "api-gateway":
        return [
            ("TimeoutError", "Upstream timeout calling billing-webhook-svc /v1/dispatch", "error", 22),
            ("ConnectionResetError", "Connection reset on upstream auth-svc:8443", "error", 18),
            ("ValueError", "Invalid JWT signature on Authorization header - kid not in JWKS", "warning", 30),
            ("KeyError", "Missing 'X-Tenant-Id' header on /v2/reports request", "warning", 14),
            ("HTTPException", "429 Too Many Requests - burst limit on /v1/charges/search", "warning", 25),
            ("RuntimeError", "Circuit breaker open for service=ingest-pipeline", "error", 8),
            ("TypeError", "Cannot serialize datetime in response body for /v1/reports", "error", 11),
            ("OSError", "[Errno 24] Too many open files in gunicorn worker pid=4711", "error", 4),
            ("ValueError", "Rate limit token bucket negative for customer cus_x9q2", "warning", 7),
            ("AssertionError", "Trace context missing parent span in upstream request", "info", 13),
            ("LookupError", "No route registered for /v3/insights/export - 404 returned", "warning", 19),
            ("BrokenPipeError", "Broken pipe writing 200 OK to client behind LB", "warning", 9),
            ("UnicodeDecodeError", "'utf-8' codec can't decode byte 0xff in request body", "error", 3),
            ("ConnectionError", "Failed to resolve upstream host frontend-web.internal", "error", 6),
            ("ValueError", "Tenant suspended - refusing /v1/reports for tenant_id=tnt_72a", "info", 17),
            ("RuntimeError", "Hedged request budget exceeded on /v1/disputes/list", "warning", 5),
            ("PermissionError", "Forbidden - caller lacks scope 'billing:read' on /v1/charges", "warning", 11),
            ("TimeoutError", "Downstream entitlement-svc /v1/check exceeded 1500ms p99", "error", 14),
            ("ValueError", "Malformed cursor parameter in /v1/audit_logs pagination", "warning", 4),
            ("KeyError", "Missing 'aud' claim in JWT for /admin/* route", "error", 8),
            ("ConnectionError", "TLS handshake failed with downstream auth-svc - cert expired", "error", 3),
            ("RuntimeError", "Gunicorn worker exceeded 1GB RSS - sigterm sent", "warning", 6),
            ("ValueError", "CSRF token mismatch on POST /v1/billing/dispute_response", "warning", 10),
            ("TimeoutError", "Health check probe timing out - pod readiness flapping", "info", 9),
            ("LookupError", "Unknown feature flag 'disputes.v2.fastpath' - defaulting to off", "info", 7),
            ("ValueError", "Request body exceeded 8MB ceiling on POST /v1/uploads/presign", "warning", 5),
            ("RuntimeError", "Retry budget exhausted on /v1/audit/log - dropping", "warning", 4),
            ("KeyError", "Missing 'X-Request-Id' header - synthesised from ulid", "info", 12),
            ("TimeoutError", "Connection pool starvation talking to db-replica-2", "error", 6),
            ("PermissionError", "Banned IP 203.0.113.55 attempted /v1/auth/login", "warning", 8),
        ]
    if project_slug == "ingest-pipeline":
        return [
            ("MemoryError", "OutOfMemory in batch worker processing 2.4GB shard", "error", 11),
            ("TimeoutError", "Kafka consumer poll timeout on topic=stripe.charges", "error", 16),
            ("ValueError", "Schema mismatch: expected 14 cols, got 12 in s3://ingest/2026-05-12/", "error", 8),
            ("KeyError", "Missing partition key 'customer_id' in event id=ev_8a3f", "warning", 22),
            ("psycopg2.errors.UniqueViolation", "duplicate key value violates unique constraint stripe_charges_pkey", "warning", 13),
            ("BotocoreClientError", "An error occurred (Throttling) when calling PutObject", "warning", 9),
            ("AssertionError", "Watermark went backward on partition p_03 - refusing commit", "error", 4),
            ("TypeError", "argument of type 'NoneType' is not iterable in normalize_address()", "error", 7),
            ("OSError", "[Errno 28] No space left on device - /tmp/spill_47", "error", 3),
            ("ValueError", "Cannot parse ISO timestamp '2026-15-03T...' from upstream", "error", 14),
            ("BotocoreClientError", "NoSuchKey: key 's3://ingest/late/2026-05-11/00.parquet'", "warning", 18),
            ("KafkaError", "Offset out of range for group=ingest-prod partition=11", "error", 5),
            ("RuntimeError", "Hung worker in stage=dedup for >900s - killing", "error", 6),
            ("ValueError", "Decimal overflow on usage_count > 2^63 for customer cus_b1", "warning", 4),
            ("AttributeError", "'NoneType' object has no attribute 'split' in shred_user_agent", "warning", 12),
            ("TimeoutError", "Snowflake COPY INTO hung for 45 minutes on STAGE @raw", "error", 5),
            ("ValueError", "Late-arriving event for closed window 2026-05-12 - dropped", "warning", 10),
            ("KeyError", "Missing 'event_type' tag in CDC payload from postgres replication", "error", 7),
            ("RuntimeError", "Backpressure: kafka producer in-flight > 50k - pausing reader", "warning", 8),
            ("psycopg2.errors.SerializationFailure", "could not serialize access due to concurrent update", "warning", 6),
            ("ValueError", "Geo lookup failed for IP 0.0.0.0 - default region applied", "info", 15),
            ("TypeError", "Cannot concatenate 'str' and 'NoneType' in build_session_key()", "error", 4),
            ("AssertionError", "Schema registry returned compatibility=NONE for v17 → v18", "error", 3),
            ("BotocoreClientError", "AccessDenied calling GetObject on s3://archive/2024/...", "warning", 5),
            ("TimeoutError", "DuckDB query exceeded 30s budget on aggregate_usage", "warning", 9),
            ("ValueError", "Negative duration_ms in session event sess_b88b - clamped to 0", "info", 11),
            ("KeyError", "Missing 'tenant_id' on usage event - falling back to org lookup", "warning", 7),
            ("RuntimeError", "Reservoir sample full - older events being evicted unexpectedly", "warning", 4),
            ("TimeoutError", "Compaction on partition p_07 stuck > 1h - manual intervention", "error", 3),
            ("ValueError", "Encoding 'cp1252' detected - re-running with permissive decoder", "info", 14),
            ("AttributeError", "'NoneType' object has no attribute 'lower' in normalize_email", "warning", 8),
        ]
    if project_slug == "frontend-web":
        return [
            ("TypeError", "Cannot read properties of undefined (reading 'subscription') in BillingPage", "error", 28),
            ("ReferenceError", "posthog is not defined in PaywallModal.tsx:142", "warning", 11),
            ("ChunkLoadError", "Loading chunk 47 failed - likely stale deploy", "warning", 24),
            ("NetworkError", "Failed to fetch /api/v1/me after 3 retries", "error", 19),
            ("TypeError", "stripe.confirmCardPayment is not a function in CheckoutForm", "error", 8),
            ("SyntaxError", "Unexpected token < in JSON at position 0 (got HTML error page)", "warning", 15),
            ("RangeError", "Maximum call stack size exceeded in useDeepEqual()", "error", 4),
            ("TypeError", "Cannot read properties of null (reading 'tier') in SidebarBadge", "warning", 13),
            ("DOMException", "Failed to execute 'postMessage' on 'DOMWindow' (CORS) for iframe", "warning", 6),
            ("AbortError", "User aborted upload in InvoiceImporter component", "info", 17),
            ("TypeError", "Cannot set property 'innerHTML' of null in legacy_dashboard.js", "error", 5),
            ("Error", "Hydration failed because the initial UI does not match server-rendered", "warning", 22),
            ("URIError", "URI malformed in router.push() for path /billing/disputes/", "warning", 3),
            ("TypeError", "Cannot read properties of undefined (reading 'amount') in DisputeRow", "error", 9),
            ("NetworkError", "Failed to fetch /api/v1/billing/disputes - HTTP 502", "warning", 13),
            ("ReferenceError", "Stripe is not defined - third-party script blocked by extension", "warning", 7),
            ("TypeError", "props.user.entitlements.map is not a function in TierGate", "error", 6),
            ("DOMException", "QuotaExceededError writing to localStorage in PersistedSettings", "info", 11),
            ("Error", "ResizeObserver loop completed with undelivered notifications", "info", 18),
            ("TypeError", "Cannot read properties of undefined (reading 'features') in FeatureFlagProvider", "warning", 4),
            ("ChunkLoadError", "Loading chunk 12 failed - net::ERR_INTERNET_DISCONNECTED", "warning", 14),
            ("Error", "Uncaught (in promise) AbortError: BodyStreamBuffer was aborted", "warning", 8),
            ("TypeError", "intl.formatNumber is not a function in InvoiceTotal - i18n bundle missing", "error", 3),
            ("NetworkError", "Failed to fetch /api/v1/me/preferences - CORS preflight rejected", "warning", 6),
            ("TypeError", "Cannot read properties of undefined (reading 'createPaymentMethod')", "error", 5),
            ("DOMException", "InvalidStateError: AudioContext was not allowed to start (autoplay)", "info", 7),
            ("Error", "Sentry self-report: Replay session dropped - rrweb buffer overflow", "warning", 4),
            ("TypeError", "history.replaceState is not a function in IE-mode iframe", "warning", 3),
            ("NetworkError", "Failed to fetch /api/v1/billing/dispute/dp_3OqM... after retries", "error", 11),
        ]
    if project_slug == "auth-svc":
        return [
            ("ValueError", "Refresh token reuse detected for session sess_8a2b", "error", 14),
            ("TimeoutError", "LDAP bind timed out talking to ldap-prd.internal", "error", 7),
            ("KeyError", "Missing 'sub' claim in incoming OIDC ID token", "warning", 11),
            ("RuntimeError", "JWKS rotation in progress - refusing new sessions for 12s", "warning", 5),
            ("ConnectionError", "Cannot reach Okta /oauth2/v1/token (DNS failure)", "error", 9),
            ("ValueError", "Password hash format unrecognized for user_id=u_2017_001 (legacy bcrypt$2a)", "warning", 4),
            ("AssertionError", "MFA challenge_id reused - replay attempt blocked", "error", 6),
            ("TypeError", "'NoneType' object is not subscriptable in tenant_for_user()", "error", 8),
            ("PermissionError", "User u_71f3 lacks scope 'billing:dispute:write' for /v1/disputes/decide", "warning", 18),
            ("ValueError", "Invalid SAML response - signature mismatch from idp_acme_okta", "error", 3),
            ("TimeoutError", "Session store (redis) PING > 5s - failing over", "warning", 10),
            ("RuntimeError", "Account lockout threshold reached for user_id=u_b9c (5 failures/2m)", "info", 21),
            ("ValueError", "JWT iat in the future (clock skew > 60s) - rejecting", "warning", 7),
            ("PermissionError", "Tenant tnt_acme_logi lacks feature 'sso.scim' - request rejected", "info", 13),
            ("ValueError", "Email verification token expired (>24h) for user_id=u_5b1c", "warning", 9),
            ("ConnectionError", "Cannot reach Auth0 /userinfo - read timeout after 5s", "error", 5),
            ("AssertionError", "Device fingerprint mismatch on session resume for user_id=u_d72", "error", 4),
            ("TimeoutError", "MFA SMS provider (Twilio) latency > 8s - falling back to TOTP", "warning", 8),
            ("ValueError", "Password rotation overdue (>180d) for service account svc_billing_ro", "info", 16),
            ("RuntimeError", "Rate limit exceeded on /v1/login for IP 198.51.100.42 (15/min)", "warning", 12),
            ("KeyError", "Missing 'org_id' on session token - refusing /v1/me/billing", "warning", 6),
            ("PermissionError", "User u_2031 attempted privilege escalation to role:owner - blocked", "error", 3),
            ("TimeoutError", "Argon2id verify > 800ms p99 - params too aggressive?", "warning", 5),
            ("ValueError", "API key prefix 'sk_live_' rejected on staging endpoint", "warning", 8),
            ("RuntimeError", "Encryption key rotation in progress - read-only mode for 30s", "info", 6),
            ("KeyError", "Missing 'scope' claim on machine-to-machine token", "warning", 4),
            ("ConnectionError", "Cannot reach Cognito /oauth2/userInfo - proxy timeout", "error", 5),
            ("ValueError", "Email change requires reauth - refusing /v1/users/email PATCH", "info", 11),
        ]
    return []


def _expand_patterns(
    patterns: list[tuple[str, str, str, int]],
) -> list[tuple[str, str, str, int]]:
    """Sample an event count per pattern based on weight.

    Distribution: count ~ weight * U(0.6, 1.8), clipped to [5, 50].
    Long tail with occasional spikes is what production data looks
    like.
    """
    out: list[tuple[str, str, str, int]] = []
    for exc_type, msg, level, weight in patterns:
        count = int(max(5, min(50, weight * random.uniform(0.6, 1.8))))
        out.append((exc_type, msg, level, count))
    return out


# ──────────────────────────────────────────────────────────────────────
# Event ingestion - sentry_sdk
# ──────────────────────────────────────────────────────────────────────


def _init_for_project(dsn: str) -> None:
    """(Re-)initialise the sentry_sdk with a project-specific DSN.

    We swap DSNs between projects by closing the prior client and calling
    `init` again. Each project gets a clean client so event routing stays
    correct.
    """
    client = sentry_sdk.Hub.current.client
    if client is not None:
        client.close(timeout=2.0)
    sentry_sdk.init(
        dsn=dsn,
        environment="production",
        release="seed-2026.05.27",
        # Disable performance / profiling - we just want errors.
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        # Don't auto-attach default integrations that hook signal handlers.
        default_integrations=False,
        # Add an extra second of grace before drop.
        shutdown_timeout=10.0,
    )


def _capture_exception(exc_type: str, msg: str, level: str) -> None:
    """Synthesise + capture a fingerprinted exception."""
    try:
        # Build the right exception class. Some patterns name third-party
        # exception types we don't have imported - fall back to a generic
        # `Exception` while keeping the type *name* preserved in the
        # message so the issue title still reads correctly.
        cls = _EXC_MAP.get(exc_type, type(exc_type, (Exception,), {}))
        raise cls(msg)
    except Exception:
        with sentry_sdk.push_scope() as scope:
            scope.level = level  # type: ignore[assignment]
            # Pin the fingerprint so identical (exc_type, msg) pairs
            # always group into a single issue regardless of stack noise.
            scope.fingerprint = [exc_type, msg]
            sentry_sdk.capture_exception()


# Map pattern exception names to real Python classes where it matters.
# Anything unmapped becomes a dynamically-created Exception subclass.
_EXC_MAP: dict[str, type] = {
    "TypeError": TypeError,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "AssertionError": AssertionError,
    "TimeoutError": TimeoutError,
    "ConnectionError": ConnectionError,
    "ConnectionResetError": ConnectionResetError,
    "BrokenPipeError": BrokenPipeError,
    "LookupError": LookupError,
    "MemoryError": MemoryError,
    "PermissionError": PermissionError,
    "OSError": OSError,
    "UnicodeDecodeError": UnicodeDecodeError,
    "RangeError": Exception,
    "ReferenceError": Exception,
    "URIError": Exception,
    "DOMException": Exception,
    "NetworkError": Exception,
    "AbortError": Exception,
    "ChunkLoadError": Exception,
    "Error": Exception,
    "HTTPException": Exception,
    "SyntaxError": SyntaxError,
}


def ingest_project_noise(
    dsn: str,
    project_slug: str,
    patterns: list[tuple[str, str, str, int]],
) -> tuple[int, int]:
    """Ingest the noise issues for a project.

    Returns (issue_count, event_count).
    """
    _init_for_project(dsn)
    issues = 0
    events = 0
    for exc_type, msg, level, count in patterns:
        for i in range(count):
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("service", project_slug)
                scope.set_tag("env", "production")
                if i == 0:
                    # First event in each pattern gets richer context so
                    # the issue's "latest event" view has something
                    # interesting to read.
                    scope.set_context(
                        "runtime",
                        {"worker_id": f"w-{random.randint(1, 64)}",
                         "shard": random.choice(["us-east-1a", "us-east-1b", "us-west-2a"])},
                    )
            _capture_exception(exc_type, msg, level)
            events += 1
            time.sleep(INGEST_SLEEP)
        issues += 1
    sentry_sdk.flush(timeout=15.0)
    return issues, events


# ──────────────────────────────────────────────────────────────────────
# W2 - the load-bearing signal
# ──────────────────────────────────────────────────────────────────────


W2_EXC_TYPE = "TypeError"
W2_MESSAGE = (
    "'NoneType' object has no attribute 'payment_method' in "
    "stripe_webhook_handler.process_invoice_payment_succeeded"
)


def ingest_w2_signal(dsn: str) -> tuple[str, int]:
    """Bake the Northwind webhook crash into billing-webhook-svc.

    Captures ~32 events. Several of them carry the Northwind customer
    id and invoice id as tags + context + message text so the agent
    finds the link when it filters by tag or grep's recent issues
    around the 2026-05-12 charge window.

    Returns (fingerprint_key, event_count).
    """
    _init_for_project(dsn)
    total = 32
    # Which event indices get the Northwind-flavored context - a small
    # but easy-to-find subset. Put them late in the burst so they're at
    # the top of the issue's event list (Sentry orders newest first).
    northwind_idxs = {3, 7, 11, 19, 24, 28, 30, 31}

    for i in range(total):
        is_northwind = i in northwind_idxs

        with sentry_sdk.push_scope() as scope:
            scope.level = "error"  # type: ignore[assignment]
            scope.fingerprint = [W2_EXC_TYPE, W2_MESSAGE]
            scope.set_tag("service", "billing-webhook-svc")
            scope.set_tag("env", "production")
            scope.set_tag("handler", "process_invoice_payment_succeeded")
            scope.set_tag("event_type", "invoice.payment_succeeded")

            if is_northwind:
                # Tag + context that the agent can filter by directly.
                scope.set_tag("customer_id", W2_CUSTOMER_ID)
                scope.set_tag("livemode", "false")
                scope.set_context(
                    "webhook_payload",
                    {
                        "customer": W2_CUSTOMER_ID,
                        "invoice_id": W2_INVOICE_ID,
                        "amount_paid": 900000,
                        "currency": "usd",
                        "subscription": "sub_test_northwind_enterprise_q2",
                        "event_id": f"evt_{W2_INVOICE_ID[3:]}",
                        "received_at": W2_CHARGE_WINDOW + ":17Z",
                    },
                )
                scope.set_context(
                    "stripe",
                    {
                        "event_type": "invoice.payment_succeeded",
                        "charge_succeeded": True,
                        "entitlement_grant_attempted": True,
                        "entitlement_grant_succeeded": False,
                    },
                )

        try:
            if is_northwind:
                # Embed the customer id + window in the message so it's
                # findable by free-text search inside the issue's event
                # list. Sentry indexes message bodies.
                raise TypeError(
                    f"{W2_MESSAGE} - failed for customer {W2_CUSTOMER_ID} "
                    f"on invoice {W2_INVOICE_ID} around {W2_CHARGE_WINDOW}Z"
                )
            else:
                raise TypeError(W2_MESSAGE)
        except TypeError:
            with sentry_sdk.push_scope() as scope:
                scope.level = "error"  # type: ignore[assignment]
                scope.fingerprint = [W2_EXC_TYPE, W2_MESSAGE]
                if is_northwind:
                    scope.set_tag("customer_id", W2_CUSTOMER_ID)
                sentry_sdk.capture_exception()
        time.sleep(INGEST_SLEEP)

    # Drop a couple of correlated breadcrumb-style messages so a free-text
    # search for "northwind" or the customer id surfaces the issue too.
    for tag_extra in (
        f"Unhandled TypeError processing invoice.payment_succeeded "
        f"for {W2_CUSTOMER_ID} (invoice {W2_INVOICE_ID})",
        f"Entitlement upgrade aborted: webhook crash for "
        f"{W2_CUSTOMER_ID} at {W2_CHARGE_WINDOW}Z",
    ):
        with sentry_sdk.push_scope() as scope:
            scope.level = "error"  # type: ignore[assignment]
            scope.fingerprint = [W2_EXC_TYPE, W2_MESSAGE]
            scope.set_tag("customer_id", W2_CUSTOMER_ID)
            scope.set_tag("service", "billing-webhook-svc")
            scope.set_context(
                "webhook_payload",
                {"customer": W2_CUSTOMER_ID, "invoice_id": W2_INVOICE_ID},
            )
            sentry_sdk.capture_message(tag_extra, level="error")
        time.sleep(INGEST_SLEEP)

    sentry_sdk.flush(timeout=20.0)
    return f"{W2_EXC_TYPE}::{W2_MESSAGE[:60]}", total + 2


# ──────────────────────────────────────────────────────────────────────
# Verification - find the W2 issue back via the API
# ──────────────────────────────────────────────────────────────────────


def verify_w2_issue(
    client: httpx.Client,
    project_slug: str,
    *,
    max_wait_s: float = 90.0,
) -> dict | None:
    """Poll the project's issues list for the W2 fingerprint.

    Sentry indexes new events asynchronously - wait up to max_wait_s for
    the issue to materialise.
    """
    deadline = time.time() + max_wait_s
    last_count = 0
    while time.time() < deadline:
        r = _request(
            client,
            "GET",
            f"/projects/{ORG}/{project_slug}/issues/?query=is:unresolved+payment_method&limit=10",
        )
        if r.status_code == 200:
            items = r.json()
            last_count = len(items)
            for it in items:
                title = it.get("title", "") + " " + it.get("metadata", {}).get("value", "")
                if "payment_method" in title and "process_invoice_payment_succeeded" in title:
                    return it
        time.sleep(3.0)
    print(f"  (verify: polled until timeout; last list had {last_count} issues)")
    return None


# ──────────────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────────────


PROJECTS_SPEC = [
    # (name, slug, platform)
    ("Billing Webhook Service", "billing-webhook-svc", "python"),
    ("API Gateway", "api-gateway", "python"),
    ("Ingest Pipeline", "ingest-pipeline", "python"),
    ("Frontend Web", "frontend-web", "javascript"),
    ("Auth Service", "auth-svc", "python"),
]


def main() -> None:
    print("== Sentry seed for miny-labs (US shard) ==")
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        # 0. Sanity
        print("\n[0] Pinging org…")
        ping_org(client)

        # 1. Teams - reuse default `miny-labs` team, add `platform`.
        print("\n[1] Teams")
        existing_teams = {t["slug"]: t for t in list_teams(client)}
        team_slugs: list[str] = []
        # Default team that ships with the org - keep it.
        if "miny-labs" in existing_teams:
            print("  team 'miny-labs' already exists (org-default)")
            team_slugs.append("miny-labs")
        # Our Platform Eng team - primary owner of these services.
        platform = ensure_team(client, "Platform Eng", "platform")
        team_slugs.append(platform["slug"])

        # 2. Projects - all owned by `platform`.
        print("\n[2] Projects (owner: platform)")
        projects: list[dict] = []
        for name, slug, platform_kind in PROJECTS_SPEC:
            p = ensure_project(client, "platform", name, slug, platform_kind)
            projects.append(p)

        # 3. DSNs
        print("\n[3] Fetching DSNs")
        dsns: dict[str, str] = {}
        for p in projects:
            dsn = get_project_dsn(client, p["slug"])
            dsns[p["slug"]] = dsn
            # Print just the public-key portion so the log isn't noisy.
            print(f"  {p['slug']}: dsn ok")

        # 4. Ingest issues per project
        print("\n[4] Ingesting issues + events")
        total_issues = 0
        total_events = 0
        per_project_stats: list[tuple[str, int, int]] = []
        for p in projects:
            slug = p["slug"]
            patterns = _expand_patterns(_patterns_for(slug))
            if not patterns:
                continue
            n_iss, n_evt = ingest_project_noise(dsns[slug], slug, patterns)
            per_project_stats.append((slug, n_iss, n_evt))
            total_issues += n_iss
            total_events += n_evt
            print(f"  {slug}: {n_iss} issues / {n_evt} events ingested")

        # 5. W2 - the dominating signal
        print("\n[5] W2 - Northwind webhook crash")
        w2_dsn = dsns["billing-webhook-svc"]
        fp, w2_events = ingest_w2_signal(w2_dsn)
        total_issues += 1  # one new fingerprint
        total_events += w2_events
        print(f"  W2 fingerprint: {fp}")
        print(f"  W2 events ingested: {w2_events}")

        # Update billing-webhook-svc stat row.
        for i, (s, ni, ne) in enumerate(per_project_stats):
            if s == "billing-webhook-svc":
                per_project_stats[i] = (s, ni + 1, ne + w2_events)
                break

        # 6. Verify W2 is searchable
        print("\n[6] Verifying W2 issue appears in API…")
        w2_issue = verify_w2_issue(client, "billing-webhook-svc")
        if w2_issue:
            print(
                f"  W2 issue found: id={w2_issue.get('id')} "
                f"short_id={w2_issue.get('shortId')} "
                f"count={w2_issue.get('count')}"
            )
        else:
            print(
                "  W2 issue not yet indexed via search (may still be "
                "processing). Events were accepted by ingest - Sentry's "
                "search index typically catches up within a few minutes."
            )

    # 7. Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Teams:           {len(team_slugs)}  ({', '.join(team_slugs)})")
    print(f"Projects:        {len(projects)}  ({', '.join(p['slug'] for p in projects)})")
    print(f"Issues:          {total_issues}")
    print(f"Total events:    {total_events}")
    print()
    print("Per-project:")
    for s, ni, ne in per_project_stats:
        print(f"  {s:<22} {ni:>3} issues / {ne:>4} events")
    print()
    print("W2 verification:")
    if w2_issue:
        print(f"  short_id:  {w2_issue.get('shortId')}")
        print(f"  id:        {w2_issue.get('id')}")
        print(f"  title:     {w2_issue.get('title', '')[:90]}")
        print(f"  count:     {w2_issue.get('count')}")
        print(f"  permalink: {w2_issue.get('permalink')}")
    else:
        print(f"  fingerprint: {fp}")
        print("  (Issue exists but search index hadn't caught up at verify time.)")
    print("=" * 60)


if __name__ == "__main__":
    main()
