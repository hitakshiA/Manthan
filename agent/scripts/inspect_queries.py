"""Dump every coral_sql query the agent emits.

Answers: is the agent calling multiple sources in ONE query (the JOIN
promise) or N single-source queries (the default trap)?

Runs ONE model end-to-end and prints every full SQL query with a
source-count annotation.

Run:
    cd manthanv2/agent
    .venv/bin/python scripts/inspect_queries.py [model]

Default model: x-ai/grok-build-0.1 (the only one that concluded in
the bake-off).
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from manthan_agent import config
from manthan_agent.loop import run_case
from manthan_agent.state import EventStore
from manthan_agent.types import CaseTrigger

console = Console()

KNOWN_SOURCES = {
    "stripe", "chargebee", "razorpay", "hubspot", "salesforce", "intercom",
    "zendesk", "slack", "notion", "confluence", "gmail", "postmark", "resend",
    "mailchimp", "loops", "twilio", "clerk", "cal", "mixpanel", "posthog",
    "sentry", "datadog", "grafana", "pagerduty", "statusgator", "launchdarkly",
    "github", "linear", "google_drive", "k8s",
}


def sources_in_query(q: str) -> set[str]:
    """Find every <source>.<table> reference in a SQL string."""
    # Match identifiers like 'stripe.disputes' (but not inside string literals).
    # Simple regex; good enough for spotting cross-source JOINs.
    found: set[str] = set()
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*", q.lower()):
        candidate = m.group(1)
        if candidate in KNOWN_SOURCES:
            found.add(candidate)
    return found


TRIGGER_TEXT = """\
A new Stripe dispute event arrived for case CASE-INSP-001.

Customer: TechCorp Industries (cus_8mFqZ, ops@techcorp.example)
Dispute: dp_mock_1Qxxxx · $1,200 USD · reason: subscription_canceled
Charge: ch_mock_3MqXfL · 12 May 2026
Evidence deadline: 8 June 2026

Initial signal: customer claims they cancelled the subscription before
the disputed renewal charge. No prior disputes on file as far as I know.
Investigate across all available sources and draft a recommendation.

Don't be lazy. Look at multiple sources before deciding."""


async def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "x-ai/grok-build-0.1"
    cfg = dataclasses.replace(config.load(), model=model)

    if not cfg.openrouter_api_key:
        console.print(Panel("OPENROUTER_API_KEY not set", border_style="red"))
        return 1

    console.print(
        Panel(
            f"model: {model}\ncase: TechCorp $1,200 chargeback",
            title="Query inspector",
            border_style="cyan",
        )
    )

    trigger = CaseTrigger(
        case_id="CASE-INSP-001",
        text=TRIGGER_TEXT,
        source_surface="stripe_webhook",
    )
    store = EventStore()

    queries: list[str] = []
    findings_count = 0
    column_counts: list[int] = []  # how wide each returned row was
    decision_action: str | None = None
    decision_confidence: float | None = None
    closed_reason: str | None = None

    t0 = time.monotonic()
    async for event in run_case(trigger, cfg, store):
        if event.kind == "tool_call" and event.data.get("name") == "coral_sql":
            q = (event.data.get("arguments") or {}).get("query", "")
            queries.append(q)
        elif event.kind == "tool_result":
            r = event.data.get("result") or {}
            data = r.get("data") or {}
            if "column_count" in data:
                column_counts.append(int(data["column_count"]))
        elif event.kind == "finding_recorded":
            findings_count += 1
        elif event.kind == "brief_drafted":
            decision = event.data.get("decision") or {}
            decision_action = decision.get("action")
            decision_confidence = decision.get("confidence")
        elif event.kind == "case_closed":
            closed_reason = event.data.get("reason")
    wall_clock = time.monotonic() - t0

    # Report
    cross_source = 0
    single_source = 0
    zero_source = 0  # weird case, no FROM clause found
    by_count: dict[int, int] = {}

    console.print(f"\n[bold]{len(queries)} coral_sql queries emitted:[/bold]\n")
    for i, q in enumerate(queries, start=1):
        srcs = sources_in_query(q)
        if len(srcs) == 0:
            zero_source += 1
            tag = "[red]NO-SOURCE[/red]"
        elif len(srcs) == 1:
            single_source += 1
            tag = f"[yellow]SINGLE  ({next(iter(srcs))})[/yellow]"
        else:
            cross_source += 1
            tag = f"[green]CROSS   ({sorted(srcs)})[/green]"
        by_count[len(srcs)] = by_count.get(len(srcs), 0) + 1
        # Print compact: tag + first 200 chars of query
        oneliner = q.replace("\n", " ").strip()
        if len(oneliner) > 220:
            oneliner = oneliner[:217] + "..."
        console.print(f"  #{i:02d} {tag}")
        console.print(f"      {oneliner}")
        console.print()

    console.print("[bold]Query shape[/bold]")
    console.print(f"  cross-source (>1 source): {cross_source} / {len(queries)}")
    console.print(f"  single-source (1 source): {single_source} / {len(queries)}")
    if zero_source:
        console.print(f"  no source detected:       {zero_source} / {len(queries)}")
    if column_counts:
        avg_cols = sum(column_counts) / len(column_counts)
        console.print(
            f"  columns returned (per row): min={min(column_counts)} "
            f"avg={avg_cols:.1f} max={max(column_counts)}"
        )
    console.print()

    # Depth + decision summary - the part we actually care about
    summary = Table(title="Outcome", show_header=False, border_style="cyan")
    summary.add_row("[bold]closed_reason[/bold]", closed_reason or "(no case_closed)")
    summary.add_row("[bold]decision[/bold]", decision_action or "(no brief)")
    conf_str = f"{decision_confidence:.2f}" if decision_confidence is not None else "-"
    summary.add_row("[bold]confidence[/bold]", conf_str)
    summary.add_row("[bold]findings recorded[/bold]", str(findings_count))
    summary.add_row("[bold]coral_sql calls[/bold]", str(len(queries)))
    summary.add_row(
        "[bold]cross-source ratio[/bold]",
        f"{cross_source}/{len(queries)}" if queries else "0/0",
    )
    summary.add_row("[bold]wall clock[/bold]", f"{wall_clock:.1f}s")
    console.print(summary)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
