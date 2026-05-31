"""Smoke test 3: end-to-end agent loop against MOCK Coral.

Wires together every primitive built in step 1:
  - Config (loads OpenRouter key from .env)
  - LLM client (DeepSeek V4 Pro Exacto via OpenRouter, strict-mode headers)
  - Event store (in-memory)
  - Tool registry (5 tools: coral_sql, coral_list_catalog,
    coral_describe_table, record_finding, ask_human, conclude)
  - Tool executor (mock Coral handlers return canned evidence)
  - The async-generator main loop

Run with:
    cd manthanv2/agent
    .venv/bin/python scripts/smoke_agent.py

Exit codes:
    0 - agent loop ran end-to-end (concluded or asked human)
    1 - OPENROUTER_API_KEY missing, or loop errored

What "green" looks like:
    case opened → agent calls coral_list_catalog or coral_sql
                → tool result returns mock evidence
                → agent calls record_finding (one or more)
                → agent calls conclude (or ask_human)
                → Terminal is reason=concluded with a Brief

The Brief includes a TL;DR, drafted actions, evidence list, and the
decision-quality HITL question. We print it at the end.
"""

from __future__ import annotations

import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from manthan_agent import config
from manthan_agent.loop import run_case
from manthan_agent.state import EventStore
from manthan_agent.types import Brief, CaseTrigger

console = Console()


# A real-feeling TechCorp $1,200 chargeback case - the canonical
# Case 4821 from the marketing site. The mock Coral returns one row
# matching this; the agent should investigate, record findings, draft
# a refund decision, and conclude.
TRIGGER_TEXT = """\
A new Stripe dispute event arrived for case CASE-SMK-001.

Customer: TechCorp Industries (cus_8mFqZ, ops@techcorp.example)
Dispute: dp_mock_1Qxxxx · $1,200 USD · reason: subscription_canceled
Charge: ch_mock_3MqXfL · 12 May 2026
Evidence deadline: 8 June 2026

Initial signal: customer claims they cancelled the subscription before
the disputed renewal charge. No prior disputes on file as far as I know.
Investigate and draft a recommendation."""


async def main() -> int:
    cfg = config.load()

    if not cfg.openrouter_api_key:
        console.print(
            Panel(
                "[yellow]OPENROUTER_API_KEY not set.[/yellow]\n\n"
                "Add it to manthanv2/agent/.env and re-run.",
                title="Smoke 3 - skipped",
                border_style="yellow",
            )
        )
        return 0

    console.print(
        Panel(
            f"[bold]model[/bold]  {cfg.model}\n"
            "[bold]coral[/bold]  MOCK (step 1; step 3 wires real MCP)\n"
            "[bold]case[/bold]   CASE-SMK-001 · TechCorp $1,200 chargeback",
            title="Manthan smoke - agent end-to-end",
            border_style="cyan",
        )
    )

    trigger = CaseTrigger(
        case_id="CASE-SMK-001",
        text=TRIGGER_TEXT,
        source_surface="stripe_webhook",
    )

    store = EventStore()

    # Drive the agent. The async generator yields Event objects.
    # Python disallows return-value on async generators (PEP 525), so the
    # final event is always kind="case_closed" - its data tells us why.
    event_count = 0
    final_brief: Brief | None = None
    closed_reason: str | None = None
    closed_detail: str | None = None
    async for event in run_case(trigger, cfg, store):
        event_count += 1
        glyph = {
            "case_opened": ":file_folder:",
            "agent_thought": ":thought_balloon:",
            "tool_call": ":wrench:",
            "tool_result": ":white_check_mark:",
            "finding_recorded": ":pushpin:",
            "reflexion": ":mag:",
            "hitl_pause": ":pause_button:",
            "brief_drafted": ":scroll:",
            "case_closed": ":checkered_flag:",
            "error": ":x:",
        }.get(event.kind, ":memo:")
        summary = _summarize(event)
        console.print(
            f"  {glyph} [dim]#{event.seq:02d}[/dim] [cyan]{event.kind:<18}[/cyan] {summary}"
        )

        if event.kind == "brief_drafted":
            final_brief = Brief.model_validate(event.data)
        if event.kind == "case_closed":
            closed_reason = event.data.get("reason")
            closed_detail = event.data.get("detail")

    console.print()

    if closed_reason is None:
        console.print("[red]Loop exited without a case_closed event - this is a bug.[/red]")
        return 1

    # Report the outcome
    if closed_reason == "concluded" and final_brief is not None:
        brief = final_brief
        tbl = Table(title=f"Brief - {brief.case_id}", show_header=False)
        tbl.add_row("[bold]TL;DR[/bold]", brief.tldr or "(empty)")
        tbl.add_row(
            "[bold]Decision[/bold]",
            f"{brief.decision.action} "
            f"{brief.decision.amount_minor or ''} "
            f"({brief.decision.currency or ''}) · "
            f"conf {brief.decision.confidence:.2f}",
        )
        tbl.add_row("[bold]Rationale[/bold]", brief.decision.rationale or "(empty)")
        tbl.add_row(
            "[bold]Findings[/bold]",
            "\n".join(
                f"[{i}] {f.text} (cites {f.citations}, conf {f.confidence:.2f})"
                for i, f in enumerate(brief.findings)
            )
            or "(none)",
        )
        tbl.add_row(
            "[bold]Evidence[/bold]",
            "\n".join(
                f"[{i}] {e.source}.{e.table}.{e.record_id}"
                for i, e in enumerate(brief.evidence)
            )
            or "(none)",
        )
        tbl.add_row(
            "[bold]Drafted actions[/bold]",
            "\n".join(f"{a.kind} - {a.description}" for a in brief.drafted_actions)
            or "(none)",
        )
        tbl.add_row("[bold]HITL question[/bold]", brief.hitl_question or "(empty)")
        console.print(tbl)
        console.print(
            f"\n[green]:white_check_mark: Smoke green.[/green] "
            f"{event_count} events. Loop concluded with a Brief."
        )
        return 0

    if closed_reason == "ask_human":
        console.print(
            Panel(
                f"[bold]Question:[/bold] {closed_detail or '(see hitl_pause event above)'}\n\n"
                "(Agent paused for HITL. Loop ended cleanly - this is the\n"
                "ask_human happy path. Step 3 wires the resume flow.)",
                title="Agent asked for human help",
                border_style="yellow",
            )
        )
        return 0

    console.print(
        Panel(
            f"reason: {closed_reason}\ndetail: {closed_detail}",
            title="Case closed - non-success",
            border_style="red",
        )
    )
    return 1


def _summarize(event) -> str:
    """One-line description of an event for the trace output."""
    d = event.data
    if event.kind == "tool_call":
        return f"[bold]{d.get('name')}[/bold]({_short_args(d.get('arguments', {}))})"
    if event.kind == "tool_result":
        r = d.get("result", {})
        return f"status={r.get('status')} rows={r.get('total_matches', '-')} +{d.get('evidence_added', 0)} evidence"
    if event.kind == "finding_recorded":
        return f"[{d.get('idx')}] conf {d.get('confidence'):.2f} - {(d.get('text') or '')[:60]}"
    if event.kind == "agent_thought":
        t = (d.get("text") or "").replace("\n", " ")
        return t[:80] + ("…" if len(t) > 80 else "")
    if event.kind == "hitl_pause":
        return f"reason={d.get('reason')} · {(d.get('question') or '')[:60]}"
    if event.kind == "brief_drafted":
        return f"action={d.get('decision', {}).get('action')} · findings={len(d.get('findings', []))}"
    if event.kind == "case_opened":
        return f"surface={d.get('source_surface')}"
    if event.kind == "error":
        return f"{d.get('reason')}: {(d.get('detail') or '')[:60]}"
    return ""


def _short_args(args: dict) -> str:
    """Compact tool-call argument preview."""
    s = ", ".join(f"{k}={_short_val(v)}" for k, v in args.items())
    if len(s) > 100:
        s = s[:97] + "..."
    return s


def _short_val(v) -> str:
    if isinstance(v, str):
        return repr(v[:40] + "…") if len(v) > 40 else repr(v)
    if isinstance(v, (list, dict)):
        return f"<{type(v).__name__} len={len(v)}>"
    return repr(v)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
