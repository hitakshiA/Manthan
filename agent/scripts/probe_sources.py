"""Probe every configured source key with one minimal authenticated call.

For each source we know how to talk to, hit a cheap "who am I / list one"
endpoint, report:
  - OK + a 1-line identity (e.g. "Stripe acct_xxx, livemode=false")
  - ERR + the specific error (HTTP status + body snippet)

Never echoes the key itself to console - only the response.

Run:
    cd manthanv2/agent
    .venv/bin/python scripts/probe_sources.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

console = Console()


def _short(s: str, n: int = 80) -> str:
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 3] + "..."


def probe_stripe() -> tuple[bool, str]:
    key = os.getenv("STRIPE_API_KEY")
    if not key:
        return False, "STRIPE_API_KEY missing"
    r = httpx.get(
        "https://api.stripe.com/v1/account",
        headers={"Authorization": f"Bearer {key}"},
        timeout=10.0,
    )
    if r.status_code == 200:
        d = r.json()
        return True, f"acct={d.get('id')} livemode={d.get('charges_enabled')}"
    return False, f"{r.status_code} {_short(r.text)}"


def probe_hubspot() -> tuple[bool, str]:
    # Private App tokens auth via Authorization: Bearer. The oauth/v1/access-tokens
    # introspection endpoint is for OAuth user-tokens only and returns 400 here.
    tok = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not tok:
        return False, "HUBSPOT_ACCESS_TOKEN missing"
    r = httpx.get(
        "https://api.hubapi.com/crm/v3/objects/companies?limit=1",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10.0,
    )
    if r.status_code == 200:
        d = r.json()
        return True, f"companies endpoint OK, {len(d.get('results', []))} row(s)"
    return False, f"{r.status_code} {_short(r.text)}"


def probe_intercom() -> tuple[bool, str]:
    tok = os.getenv("INTERCOM_ACCESS_TOKEN")
    if not tok:
        return False, "INTERCOM_ACCESS_TOKEN missing"
    r = httpx.get(
        "https://api.intercom.io/me",
        headers={
            "Authorization": f"Bearer {tok}",
            "Intercom-Version": "2.11",
            "Accept": "application/json",
        },
        timeout=10.0,
    )
    if r.status_code == 200:
        d = r.json()
        app = (d.get("app") or {}).get("name")
        return True, f"app={app!r} id_code={(d.get('app') or {}).get('id_code')}"
    return False, f"{r.status_code} {_short(r.text)}"


def probe_zendesk() -> tuple[bool, str]:
    sub = os.getenv("ZENDESK_SUBDOMAIN")
    email_tok = os.getenv("ZENDESK_USER_EMAIL_WITH_TOKEN")
    api_tok = os.getenv("ZENDESK_API_TOKEN")
    if not (sub and email_tok and api_tok):
        return False, "ZENDESK_* (3 vars) missing"
    r = httpx.get(
        f"https://{sub}.zendesk.com/api/v2/users/me.json",
        auth=(email_tok, api_tok),
        timeout=10.0,
    )
    if r.status_code == 200:
        u = r.json().get("user") or {}
        return True, f"user={u.get('email')} role={u.get('role')}"
    return False, f"{r.status_code} {_short(r.text)}"


def probe_slack() -> tuple[bool, str]:
    tok = os.getenv("SLACK_TOKEN")
    if not tok:
        return False, "SLACK_TOKEN missing"
    r = httpx.post(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10.0,
    )
    d = r.json() if r.status_code == 200 else {}
    if d.get("ok"):
        return True, f"team={d.get('team')!r} bot={d.get('user')!r}"
    return False, f"{r.status_code} ok={d.get('ok')} err={d.get('error') or _short(r.text)}"


def probe_notion() -> tuple[bool, str]:
    tok = os.getenv("NOTION_API_KEY")
    if not tok:
        return False, "NOTION_API_KEY missing"
    r = httpx.get(
        "https://api.notion.com/v1/users/me",
        headers={
            "Authorization": f"Bearer {tok}",
            "Notion-Version": "2022-06-28",
        },
        timeout=10.0,
    )
    if r.status_code == 200:
        d = r.json()
        bot = d.get("bot") or {}
        ws = bot.get("workspace_name") or "?"
        return True, f"bot={d.get('name')!r} workspace={ws!r}"
    return False, f"{r.status_code} {_short(r.text)}"


def probe_pagerduty() -> tuple[bool, str]:
    tok = os.getenv("PAGERDUTY_API_TOKEN")
    if not tok:
        return False, "PAGERDUTY_API_TOKEN missing"
    r = httpx.get(
        "https://api.pagerduty.com/users/me",
        headers={
            "Authorization": f"Token token={tok}",
            "Accept": "application/vnd.pagerduty+json;version=2",
        },
        timeout=10.0,
    )
    if r.status_code == 200:
        u = r.json().get("user") or {}
        return True, f"user={u.get('email')} role={u.get('role')}"
    return False, f"{r.status_code} {_short(r.text)}"


def probe_sentry() -> tuple[bool, str]:
    tok = os.getenv("SENTRY_TOKEN")
    org = os.getenv("SENTRY_ORG")
    if not (tok and org):
        return False, "SENTRY_TOKEN/ORG missing"
    # Decode the sntrys_ token payload to find which region shard hosts
    # this org. New SaaS orgs are on us.sentry.io or eu.sentry.io -
    # calling the bare sentry.io endpoint returns 403 from the wrong shard.
    import base64
    import json as _json

    api_root = "https://sentry.io"
    if tok.startswith("sntrys_"):
        try:
            payload = tok.split("_", 2)[1]
            payload += "=" * (-len(payload) % 4)
            decoded = _json.loads(base64.urlsafe_b64decode(payload))
            api_root = decoded.get("region_url") or api_root
        except Exception:
            pass
    r = httpx.get(
        f"{api_root}/api/0/projects/",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10.0,
    )
    if r.status_code == 200:
        projects = r.json()
        names = [p.get("slug") for p in projects[:3]]
        return True, f"region={api_root} projects={len(projects)} sample={names}"
    return False, f"{r.status_code} {_short(r.text)}"


def probe_posthog() -> tuple[bool, str]:
    tok = os.getenv("POSTHOG_API_KEY")
    base = os.getenv("POSTHOG_API_BASE") or "https://us.posthog.com"
    if not tok:
        return False, "POSTHOG_API_KEY missing"
    # /api/projects/@current works with project-scoped tokens; /api/users/@me
    # needs broader "User access" which personal keys often don't have.
    r = httpx.get(
        f"{base.rstrip('/')}/api/projects/@current",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10.0,
    )
    if r.status_code == 200:
        d = r.json()
        return True, f"project={d.get('name')!r} id={d.get('id')}"
    return False, f"{r.status_code} {_short(r.text)}"


def probe_datadog() -> tuple[bool, str]:
    site = os.getenv("DD_SITE") or "datadoghq.com"
    api_key = os.getenv("DD_API_KEY")
    app_key = os.getenv("DD_APPLICATION_KEY")
    if not (api_key and app_key):
        return False, "DD_API_KEY / DD_APPLICATION_KEY missing"
    # validate api key
    r1 = httpx.get(
        f"https://api.{site}/api/v1/validate",
        headers={"DD-API-KEY": api_key},
        timeout=10.0,
    )
    if r1.status_code != 200:
        return False, f"api-key {r1.status_code} {_short(r1.text)}"
    # check application key via /api/v2/current_user (the modern endpoint)
    r2 = httpx.get(
        f"https://api.{site}/api/v2/current_user",
        headers={"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key},
        timeout=10.0,
    )
    if r2.status_code == 200:
        d = r2.json().get("data") or {}
        attrs = d.get("attributes") or {}
        return True, f"user={attrs.get('email')} site={site}"
    return False, f"app-key {r2.status_code} {_short(r2.text)}"


def probe_salesforce() -> tuple[bool, str]:
    url = os.getenv("SALESFORCE_API_URL")
    tok = os.getenv("SALESFORCE_ACCESS_TOKEN")
    if not (url and tok):
        return False, "SALESFORCE_API_URL / SALESFORCE_ACCESS_TOKEN missing"
    r = httpx.get(
        f"{url}/services/data/v59.0/query",
        params={"q": "SELECT Id FROM Account LIMIT 1"},
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
        timeout=10.0,
    )
    if r.status_code == 200:
        n = r.json().get("totalSize", 0)
        # Identify org by hitting /services/data/v59.0/sobjects (cheap)
        return True, f"instance={url.split('//')[1].split('.')[0]} sample_accounts={n}"
    if r.status_code == 401:
        return False, (
            "401 - access token expired. Refresh with: "
            ".venv/bin/python scripts/refresh_salesforce_token.py"
        )
    return False, f"{r.status_code} {_short(r.text)}"


PROBES: list[tuple[str, Any]] = [
    ("stripe", probe_stripe),
    ("notion", probe_notion),
    ("intercom", probe_intercom),
    ("hubspot", probe_hubspot),
    ("slack", probe_slack),
    ("pagerduty", probe_pagerduty),
    ("sentry", probe_sentry),
    ("posthog", probe_posthog),
    ("zendesk", probe_zendesk),
    ("datadog", probe_datadog),
    ("salesforce", probe_salesforce),
]


def main() -> int:
    tbl = Table(title="Source probe", border_style="cyan")
    tbl.add_column("Source", style="bold")
    tbl.add_column("Status", justify="center")
    tbl.add_column("Detail", overflow="fold")

    n_ok = 0
    for name, fn in PROBES:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"EXCEPTION {type(e).__name__}: {e}"
        if ok:
            n_ok += 1
            tbl.add_row(name, "[green]OK[/green]", detail)
        else:
            tbl.add_row(name, "[red]ERR[/red]", detail)
    console.print(tbl)
    console.print(f"\n{n_ok}/{len(PROBES)} sources responding cleanly")
    return 0 if n_ok == len(PROBES) else 1


if __name__ == "__main__":
    sys.exit(main())
