"""Sources - list connected data sources + their live state.

The 11 sources powering Manthan's cross-source investigation. Connection
status comes from whether the relevant env credentials are present;
last-query stats come from the events table (tool_call events whose
SQL references that source).

In v1 these creds live in env vars (single-tenant). When we wire OAuth
onboarding, this will instead read from the `sources` table per org.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api", tags=["sources"])
logger = logging.getLogger("manthan_api.sources")


# Source registry - id, display name, category, env vars that gate it.
# When ALL listed env vars are present, the source is "configured".
SOURCE_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "stripe", "name": "Stripe", "category": "billing",
        "description": "Disputes, charges, customers, refunds.",
        "envs": ["STRIPE_API_KEY"],
        "capabilities": ["read", "write", "trigger"],
        "oauth": True,
    },
    {
        "id": "salesforce", "name": "Salesforce", "category": "crm",
        "description": "Accounts, opportunities, contacts, ARR.",
        "envs": ["SALESFORCE_ACCESS_TOKEN", "SALESFORCE_API_URL"],
        "capabilities": ["read"], "oauth": True,
    },
    {
        "id": "hubspot", "name": "HubSpot", "category": "crm",
        "description": "Companies, contacts, deals, engagements.",
        "envs": ["HUBSPOT_ACCESS_TOKEN"],
        "capabilities": ["read", "write"], "oauth": True,
    },
    {
        "id": "intercom", "name": "Intercom", "category": "support",
        "description": "Customer chats, conversations, contacts.",
        "envs": ["INTERCOM_ACCESS_TOKEN"],
        "capabilities": ["read", "trigger"], "oauth": True,
    },
    {
        "id": "zendesk", "name": "Zendesk", "category": "support",
        "description": "Tickets, users, organizations.",
        "envs": ["ZENDESK_API_TOKEN", "ZENDESK_SUBDOMAIN"],
        "capabilities": ["read", "write", "trigger"], "oauth": False,
    },
    {
        "id": "slack", "name": "Slack", "category": "comms",
        "description": "Channels, mentions, internal team threads.",
        "envs": ["SLACK_TOKEN"],
        "capabilities": ["read", "write", "trigger"], "oauth": True,
    },
    {
        "id": "notion", "name": "Notion", "category": "knowledge",
        "description": "Policy docs, decision runbooks, ops repo.",
        "envs": ["NOTION_API_KEY"],
        "capabilities": ["read", "write"], "oauth": True,
    },
    {
        "id": "posthog", "name": "PostHog", "category": "analytics",
        "description": "Product usage events, distinct active users.",
        "envs": ["POSTHOG_API_KEY"],
        "capabilities": ["read"], "oauth": False,
    },
    {
        "id": "sentry", "name": "Sentry", "category": "ops",
        "description": "Errors, exception groups, regressions.",
        "envs": ["SENTRY_TOKEN", "SENTRY_ORG"],
        "capabilities": ["read"], "oauth": True,
    },
    {
        "id": "datadog", "name": "Datadog", "category": "ops",
        "description": "Infra metrics, APM, synthetic monitors.",
        "envs": ["DD_API_KEY", "DD_APPLICATION_KEY"],
        "capabilities": ["read"], "oauth": False,
    },
    {
        "id": "pagerduty", "name": "PagerDuty", "category": "ops",
        "description": "Incidents, services, on-call schedules.",
        "envs": ["PAGERDUTY_API_TOKEN"],
        "capabilities": ["read"], "oauth": False,
    },
]


_SOURCE_REF_RE = re.compile(r"\b([a-z_][a-z0-9_]+)\s*\.\s*[a-z_][a-z0-9_]+\b")


@router.get("/sources")
async def list_sources(ctx: TenantCtx = Depends(get_ctx)) -> dict[str, Any]:
    """Per-source: configured y/n, last query time, query count from events."""
    # Aggregate tool_call usage from the events table. For each event with
    # name=coral_sql, scan the SQL string for `<source>.<table>` refs and
    # increment per-source counters.
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT data->'arguments'->>'query' AS sql, created_at
            FROM events
            WHERE org_id = $1
              AND type = 'tool_call'
              AND data->>'name' = 'coral_sql'
              AND data->'arguments'->>'query' IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 2000
            """,
            ctx.org_id,
        )

    known_sources = {s["id"] for s in SOURCE_REGISTRY}
    last_query_by_src: dict[str, datetime] = {}
    count_by_src: dict[str, int] = {s: 0 for s in known_sources}

    for row in rows:
        sql = str(row["sql"]).lower()
        seen_in_row: set[str] = set()
        for m in _SOURCE_REF_RE.finditer(sql):
            src = m.group(1)
            if src in known_sources and src not in seen_in_row:
                seen_in_row.add(src)
                count_by_src[src] = count_by_src.get(src, 0) + 1
                ts = row["created_at"]
                if isinstance(ts, datetime) and (
                    src not in last_query_by_src or ts > last_query_by_src[src]
                ):
                    last_query_by_src[src] = ts

    out: list[dict[str, Any]] = []
    for s in SOURCE_REGISTRY:
        configured = all(os.environ.get(e) for e in s["envs"])
        last_q = last_query_by_src.get(s["id"])
        status = "connected" if configured else "available"
        out.append({
            "id": s["id"],
            "name": s["name"],
            "category": s["category"],
            "description": s["description"],
            "capabilities": s["capabilities"],
            "oauth": s["oauth"],
            "status": status,
            "last_query_at": last_q.isoformat() if last_q else None,
            "queries_total": count_by_src.get(s["id"], 0),
        })

    return {
        "sources": out,
        "totals": {
            "configured": sum(1 for s in out if s["status"] == "connected"),
            "available": sum(1 for s in out if s["status"] == "available"),
            "total": len(out),
        },
    }


# ──────────────────────────────────────────────────────────────────────
# Coral connection detail - per source: env vars (censored) + the
# qualified table names that Coral exposes for the agent's SQL queries.
# ──────────────────────────────────────────────────────────────────────


# Stable per-source table catalog. Mirrors what the duckdb world / Coral
# binary actually expose at query time. Kept here instead of querying
# Coral live because (a) it's a fixed schema per source, (b) avoids
# spinning a duckdb subprocess on every page load, (c) gives the UI a
# stable surface to render even when Coral itself is unreachable.
SOURCE_TABLES: dict[str, list[str]] = {
    "stripe": [
        "stripe.charges",
        "stripe.disputes",
        "stripe.refunds",
        "stripe.customers",
        "stripe.invoices",
        "stripe.payment_intents",
        "stripe.subscriptions",
    ],
    "salesforce": [
        "salesforce.accounts",
        "salesforce.opportunities",
        "salesforce.contacts",
        "salesforce.cases",
    ],
    "hubspot": [
        "hubspot.companies",
        "hubspot.contacts",
        "hubspot.deals",
        "hubspot.engagements",
    ],
    "zendesk": [
        "zendesk.tickets",
        "zendesk.users",
        "zendesk.organizations",
    ],
    "intercom": [
        "intercom.conversations",
        "intercom.contacts",
        "intercom.companies",
    ],
    "slack": [
        "slack.messages",
        "slack.channels",
        "slack.users",
    ],
    "notion": [
        "notion.pages",
        "notion.databases",
    ],
    "posthog": [
        "posthog.events",
        "posthog.persons",
    ],
    "sentry": [
        "sentry.issues",
        "sentry.events",
    ],
    "datadog": [
        "datadog.incidents",
        "datadog.monitors",
        "datadog.metrics",
    ],
    "pagerduty": [
        "pagerduty.incidents",
        "pagerduty.services",
    ],
    "resend": [
        "resend.emails",
        "resend.contacts",
    ],
    "linear": [
        "linear.issues",
        "linear.projects",
    ],
}


def _censor(value: str) -> str:
    """Mask a credential string for display. Keeps the prefix (so you
    can still tell whether it's a test key, what kind of token it is)
    and the last 4 chars (for fingerprinting), masks the middle."""
    if not value:
        return ""
    if len(value) <= 12:
        return value[:2] + "…" + value[-2:]
    # Keep the prefix up to the second separator, e.g. "sk_test_" or "xoxb-…-".
    prefix_match = re.match(r"^(sk_test_|sk_live_|pk_test_|pk_live_|xoxb-|xoxp-|pat-na2-|re_|du_|ch_)", value)
    prefix = prefix_match.group(1) if prefix_match else value[:4]
    return f"{prefix}{'•' * 24}{value[-4:]}"


@router.get("/sources/{source_id}/coral")
async def get_source_coral_detail(
    source_id: str,
    ctx: TenantCtx = Depends(get_ctx),  # noqa: ARG001 (auth gate only)
) -> dict[str, Any]:
    """Per-source Coral connection detail: env vars (censored) + the
    qualified table names Coral exposes for the agent's SQL queries.
    Powers the Source-tile click-through inspector in the UI."""
    src = next((s for s in SOURCE_REGISTRY if s["id"] == source_id), None)
    if src is None:
        return {"error": f"unknown source: {source_id}"}

    env_vars: list[dict[str, Any]] = []
    for env_name in src["envs"]:
        raw = os.environ.get(env_name)
        env_vars.append({
            "name": env_name,
            "present": bool(raw),
            "value_preview": _censor(raw) if raw else None,
        })

    tables = SOURCE_TABLES.get(source_id, [])

    return {
        "id": src["id"],
        "name": src["name"],
        "category": src["category"],
        "description": src["description"],
        "status": "connected" if all(os.environ.get(e) for e in src["envs"]) else "available",
        "env_vars": env_vars,
        "tables": tables,
        # Coral itself - what's powering this connection.
        "coral": {
            "binary": "coral mcp-stdio",
            "transport": "MCP over stdio",
            "tools": ["coral_sql", "coral_list_catalog", "coral_describe_table"],
        },
    }
