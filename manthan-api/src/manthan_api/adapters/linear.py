"""Linear adapter - create a follow-up issue."""

from __future__ import annotations

import os
from typing import Any

import httpx

from . import AdapterError, ExecutionResult


def create_issue(payload: dict[str, Any], idempotency_key: str) -> ExecutionResult:
    """Create a Linear issue via GraphQL.

    Required payload keys:
      team_id: Linear team UUID  (or team_key like 'BIL')
      title: str
      description: str (markdown)
      priority: 0-4 (optional)
    """
    token = os.environ.get("LINEAR_API_KEY")
    demo_mode = os.environ.get("MANTHAN_DEMO_MODE")
    title = payload.get("title") or payload.get("description") or "Manthan follow-up"

    # Demo-mode shortcut: when no Linear key is configured AND we're
    # running a demo, return a synthetic-success ExecutionResult so the
    # case can finalize cleanly. Production deployments configure
    # LINEAR_API_KEY and this branch never fires.
    if not token:
        if demo_mode:
            ref = f"DEMO-LIN-{idempotency_key[:8].upper()}"
            return ExecutionResult(
                external_ref=ref,
                summary=f"Linear ticket queued (demo): {title[:80]}",
                raw={
                    "identifier": ref,
                    "url": None,
                    "demo": True,
                    "reason": "LINEAR_API_KEY not configured; demo-mode placeholder",
                },
            )
        raise AdapterError("LINEAR_API_KEY missing - add to .env to enable Linear writes")

    team_id = payload.get("team_id")
    description = payload.get("description", "")
    if not team_id or not title:
        # Demo-mode: still succeed gracefully so the case finalizes.
        if demo_mode:
            ref = f"DEMO-LIN-{idempotency_key[:8].upper()}"
            return ExecutionResult(
                external_ref=ref,
                summary=f"Linear ticket queued (demo): {title[:80]}",
                raw={
                    "identifier": ref,
                    "url": None,
                    "demo": True,
                    "reason": "incomplete payload (missing team_id/title); demo-mode placeholder",
                },
            )
        raise AdapterError("linear.create_issue payload requires team_id + title")

    query = (
        "mutation IssueCreate($input: IssueCreateInput!) {\n"
        "  issueCreate(input: $input) {\n"
        "    success\n"
        "    issue { id identifier url }\n"
        "  }\n"
        "}\n"
    )
    variables = {
        "input": {
            "teamId": team_id,
            "title": title,
            "description": description + f"\n\n_Manthan idempotency_key: {idempotency_key}_",
        }
    }
    if "priority" in payload:
        variables["input"]["priority"] = int(payload["priority"])

    with httpx.Client(timeout=30.0) as c:
        try:
            r = c.post(
                "https://api.linear.app/graphql",
                headers={"Authorization": token, "Content-Type": "application/json"},
                json={"query": query, "variables": variables},
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            raise AdapterError(f"linear create failed: {e.response.status_code}")

    issue = (data.get("data") or {}).get("issueCreate", {}).get("issue")
    if not issue:
        raise AdapterError(f"linear create returned no issue: {data}")
    return ExecutionResult(
        external_ref=str(issue.get("identifier") or issue.get("id")),
        summary=f"Linear issue {issue.get('identifier')} created",
        raw={"identifier": issue.get("identifier"), "url": issue.get("url")},
    )
