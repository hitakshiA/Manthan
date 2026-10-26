"""Citation deep-link resolver - turn (source, table, ref) into a clickable URL.

The agent records citations as `{source, table, ref, field}`. The UI lights
the citation as a chip; ideally the operator clicks the chip and lands in
the actual source record (Stripe charge, Notion page, HubSpot contact, etc.).

This module is the single map. Adding a source is one entry. Source-specific
quirks (HubSpot portal IDs, Salesforce instance URLs, Notion page UUID
formatting) live here and nowhere else.

When the URL can't be resolved (missing env, unknown source, malformed ref),
we return None and the UI renders a non-clickable chip - never a broken link.
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote


# ──────────────────────────────────────────────────────────────────────
# Per-source URL builders
# ──────────────────────────────────────────────────────────────────────


def _stripe_url(table: str, ref: str) -> str | None:
    """Stripe Dashboard deep-links. We assume test mode for the demo."""
    table_path = {
        "charges": "payments",
        "charge": "payments",
        "disputes": "disputes",
        "dispute": "disputes",
        "customers": "customers",
        "customer": "customers",
        "invoices": "invoices",
        "invoice": "invoices",
        "refunds": "refunds",
        "refund": "refunds",
        "subscriptions": "subscriptions",
        "subscription": "subscriptions",
        "payment_intents": "payments",
        "products": "products",
        "events": "events",
    }
    # Sniff from ref prefix if table is unhelpful.
    prefix_map = {
        "ch_": "payments", "pi_": "payments",
        "du_": "disputes",
        "cus_": "customers",
        "in_": "invoices",
        "re_": "refunds",
        "sub_": "subscriptions",
        "prod_": "products",
        "evt_": "events",
    }
    path = table_path.get(table.lower())
    if not path:
        for pfx, p in prefix_map.items():
            if ref.startswith(pfx):
                path = p
                break
    if not path:
        return None
    return f"https://dashboard.stripe.com/test/{path}/{quote(ref, safe='')}"


def _notion_url(table: str, ref: str) -> str | None:
    """Notion pages - strip dashes from UUID (Notion's URL convention)."""
    if not ref:
        return None
    clean = ref.replace("-", "")
    # Notion URLs work as notion.so/{page_id_no_dashes} (redirects to canonical).
    return f"https://www.notion.so/{quote(clean, safe='')}"


def _hubspot_url(table: str, ref: str) -> str | None:
    portal = os.environ.get("HUBSPOT_PORTAL_ID")
    if not portal or not ref:
        return None
    kind_map = {
        "companies": "company",
        "company": "company",
        "contacts": "contact",
        "contact": "contact",
        "deals": "deal",
        "deal": "deal",
        "notes": "note",
        "engagements": "engagement",
    }
    kind = kind_map.get(table.lower())
    if not kind:
        return None
    return f"https://app.hubspot.com/contacts/{portal}/{kind}/{quote(ref, safe='')}"


def _salesforce_url(table: str, ref: str) -> str | None:
    """Salesforce Lightning record URLs.

    Instance URL pattern from SALESFORCE_API_URL env (e.g.
    'https://orgfarm-7d06b472d9-dev-ed.develop.my.salesforce.com').
    """
    instance = os.environ.get("SALESFORCE_API_URL", "").rstrip("/")
    if not instance or not ref:
        return None
    # Strip the my.salesforce.com → lightning.force.com (Salesforce's UI host).
    lightning = instance.replace(".my.salesforce.com", ".lightning.force.com")
    object_map = {
        "accounts": "Account",
        "account": "Account",
        "opportunities": "Opportunity",
        "opportunity": "Opportunity",
        "contacts": "Contact",
        "contact": "Contact",
        "leads": "Lead",
        "lead": "Lead",
        "cases": "Case",
    }
    obj = object_map.get(table.lower())
    if not obj:
        return None
    return f"{lightning}/lightning/r/{obj}/{quote(ref, safe='')}/view"


def _intercom_url(table: str, ref: str) -> str | None:
    workspace = os.environ.get("INTERCOM_WORKSPACE_ID")
    if not workspace or not ref:
        return None
    if table.lower() in ("conversations", "conversation"):
        return f"https://app.intercom.com/a/inbox/{workspace}/conversations/{quote(ref, safe='')}"
    if table.lower() in ("contacts", "contact", "users", "user"):
        return f"https://app.intercom.com/a/apps/{workspace}/users/{quote(ref, safe='')}"
    return None


def _zendesk_url(table: str, ref: str) -> str | None:
    sub = os.environ.get("ZENDESK_SUBDOMAIN")
    if not sub or not ref:
        return None
    if table.lower() in ("tickets", "ticket"):
        return f"https://{sub}.zendesk.com/agent/tickets/{quote(ref, safe='')}"
    if table.lower() in ("users", "user"):
        return f"https://{sub}.zendesk.com/agent/users/{quote(ref, safe='')}/identities"
    return None


def _slack_url(table: str, ref: str) -> str | None:
    """Slack message deep-link. ref expected as 'channel_id:ts' or just 'ts'."""
    workspace = os.environ.get("SLACK_WORKSPACE_HANDLE", "")
    if not ref:
        return None
    # Permalink form: https://{workspace}.slack.com/archives/{channel}/p{ts}
    if ":" in ref:
        channel, ts = ref.split(":", 1)
        ts_clean = ts.replace(".", "")
        host = f"{workspace}.slack.com" if workspace else "app.slack.com"
        return f"https://{host}/archives/{quote(channel, safe='')}/p{ts_clean}"
    # Channel-only fallback
    host = f"{workspace}.slack.com" if workspace else "app.slack.com"
    return f"https://{host}/archives/{quote(ref, safe='')}"


def _posthog_url(table: str, ref: str) -> str | None:
    project = os.environ.get("POSTHOG_PROJECT_ID")
    base = os.environ.get("POSTHOG_API_BASE", "https://us.posthog.com").rstrip("/")
    # Strip the /api/projects/... suffix if present
    base = re.sub(r"/api/.*$", "", base)
    if not project or not ref:
        return None
    if table.lower() in ("events", "event"):
        return f"{base}/project/{project}/events/{quote(ref, safe='')}"
    if table.lower() in ("persons", "person"):
        return f"{base}/project/{project}/persons/{quote(ref, safe='')}"
    if table.lower() in ("insights", "insight"):
        return f"{base}/project/{project}/insights/{quote(ref, safe='')}"
    return None


def _sentry_url(table: str, ref: str) -> str | None:
    org = os.environ.get("SENTRY_ORG")
    if not org or not ref:
        return None
    if table.lower() in ("issues", "issue", "events", "event"):
        return f"https://sentry.io/organizations/{quote(org, safe='')}/issues/{quote(ref, safe='')}/"
    return None


def _datadog_url(table: str, ref: str) -> str | None:
    site = os.environ.get("DD_SITE", "datadoghq.com")
    if not ref:
        return None
    if table.lower() in ("events", "event"):
        return f"https://app.{site}/event/event?id={quote(ref, safe='')}"
    if table.lower() in ("monitors", "monitor"):
        return f"https://app.{site}/monitors/{quote(ref, safe='')}"
    if table.lower() in ("logs", "log"):
        return f"https://app.{site}/logs?query={quote(ref, safe='')}"
    return None


def _pagerduty_url(table: str, ref: str) -> str | None:
    sub = os.environ.get("PAGERDUTY_SUBDOMAIN")
    if not sub or not ref:
        return None
    if table.lower() in ("incidents", "incident"):
        return f"https://{sub}.pagerduty.com/incidents/{quote(ref, safe='')}"
    if table.lower() in ("services", "service"):
        return f"https://{sub}.pagerduty.com/service-directory/{quote(ref, safe='')}"
    return None


def _linear_url(table: str, ref: str) -> str | None:
    """Linear issue / project / cycle URLs.

    Linear's UI is keyed on the issue identifier (ENG-123). When the ref
    matches that pattern we deep-link to the issue page. Otherwise we
    fall back to a workspace-wide search.
    """
    if not ref:
        return None
    org = os.environ.get("LINEAR_WORKSPACE_SLUG", "miny")
    t = table.lower()
    # Issue identifier (ENG-123 etc.)
    if re.match(r"^[A-Z]{2,}-\d+$", ref):
        return f"https://linear.app/{org}/issue/{ref}"
    if t in ("issues", "issue"):
        return f"https://linear.app/{org}/issue/{quote(ref, safe='')}"
    if t in ("projects", "project"):
        return f"https://linear.app/{org}/project/{quote(ref, safe='')}"
    return None


def _github_url(table: str, ref: str) -> str | None:
    """GitHub deep-links - issue/PR/commit. Repo comes from env."""
    repo = os.environ.get("GITHUB_REPO")  # owner/name
    if not repo or not ref:
        return None
    t = table.lower()
    if t in ("issues", "issue"):
        return f"https://github.com/{repo}/issues/{quote(ref, safe='')}"
    if t in ("pulls", "pull", "pull_requests"):
        return f"https://github.com/{repo}/pull/{quote(ref, safe='')}"
    if t in ("commits", "commit"):
        return f"https://github.com/{repo}/commit/{quote(ref, safe='')}"
    return None


# ──────────────────────────────────────────────────────────────────────
# Search fallback - if we can't build a record-specific URL, send the
# operator to the source's search/inbox so they at least land in the
# right product. Better than a dead chip.
# ──────────────────────────────────────────────────────────────────────


def _search_fallback(source: str, ref: str) -> str | None:
    """When the (source, table, ref) tuple doesn't resolve, drop the
    operator into the source's main UI with `ref` as a search query.
    The user can then locate the record themselves - still one click
    instead of zero."""
    if not ref:
        return None
    q = quote(ref, safe="")
    if source == "stripe":
        return f"https://dashboard.stripe.com/test/search?query={q}"
    if source == "notion":
        return f"https://www.notion.so/search?query={q}"
    if source == "hubspot":
        portal = os.environ.get("HUBSPOT_PORTAL_ID")
        if portal:
            return f"https://app.hubspot.com/contacts/{portal}/objects/0-1/search?query={q}"
    if source == "salesforce":
        inst = os.environ.get("SALESFORCE_API_URL", "").rstrip("/")
        if inst:
            light = inst.replace(".my.salesforce.com", ".lightning.force.com")
            return f"{light}/one/one.app#/sObject/Search/{q}"
    if source == "intercom":
        ws = os.environ.get("INTERCOM_WORKSPACE_ID")
        if ws:
            return f"https://app.intercom.com/a/inbox/{ws}/inbox/search/all?term={q}"
    if source == "zendesk":
        sub = os.environ.get("ZENDESK_SUBDOMAIN")
        if sub:
            return f"https://{sub}.zendesk.com/agent/search/1?query={q}"
    if source == "slack":
        ws = os.environ.get("SLACK_WORKSPACE_HANDLE")
        host = f"{ws}.slack.com" if ws else "app.slack.com"
        return f"https://{host}/search?q={q}"
    if source == "posthog":
        project = os.environ.get("POSTHOG_PROJECT_ID")
        base = os.environ.get("POSTHOG_API_BASE", "https://us.posthog.com")
        base = re.sub(r"/api/.*$", "", base).rstrip("/")
        if project:
            return f"{base}/project/{project}/events?q={q}"
    if source == "sentry":
        org = os.environ.get("SENTRY_ORG")
        if org:
            return f"https://sentry.io/organizations/{quote(org, safe='')}/issues/?query={q}"
    if source == "datadog":
        site = os.environ.get("DD_SITE", "datadoghq.com")
        return f"https://app.{site}/logs?query={q}"
    if source == "pagerduty":
        sub = os.environ.get("PAGERDUTY_SUBDOMAIN")
        if sub:
            return f"https://{sub}.pagerduty.com/search?keywords={q}"
    if source == "linear":
        org = os.environ.get("LINEAR_WORKSPACE_SLUG", "miny")
        return f"https://linear.app/{org}/search?q={q}"
    if source == "github":
        repo = os.environ.get("GITHUB_REPO")
        if repo:
            return f"https://github.com/{repo}/search?q={q}"
    return None


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


_RESOLVERS = {
    "stripe": _stripe_url,
    "notion": _notion_url,
    "hubspot": _hubspot_url,
    "salesforce": _salesforce_url,
    "intercom": _intercom_url,
    "zendesk": _zendesk_url,
    "slack": _slack_url,
    "posthog": _posthog_url,
    "sentry": _sentry_url,
    "datadog": _datadog_url,
    "pagerduty": _pagerduty_url,
    "linear": _linear_url,
    "github": _github_url,
}


def resolve_url(source: str | None, table: str | None, ref: str | None) -> str | None:
    """Turn a (source, table, ref) citation into a clickable URL.

    Resolution order:
      1. Source-specific table-aware builder (the precise record URL).
      2. Search fallback (drops the operator into the source's search UI
         with `ref` as the query) - better than a dead chip.
      3. None - UI renders a non-clickable chip.
    """
    if not source or not ref:
        return None
    # Handle joined sources like "stripe+notion" (record_id from a join):
    # use the first one as the primary.
    s = source.lower().split("+", 1)[0].split("_", 1)[0]
    fn = _RESOLVERS.get(s)
    direct = None
    if fn is not None:
        try:
            direct = fn((table or "").lower(), ref)
        except Exception:
            direct = None
    if direct:
        return direct
    # Fallback: search URL on that source.
    try:
        return _search_fallback(s, ref)
    except Exception:
        return None


def enrich_citation(citation: dict) -> dict:
    """Return a shallow copy of the citation with a `url` field added (or null)."""
    url = resolve_url(citation.get("source"), citation.get("table"), citation.get("ref"))
    return {**citation, "url": url}


def enrich_citations(citations: list[dict]) -> list[dict]:
    return [enrich_citation(c) for c in citations]
