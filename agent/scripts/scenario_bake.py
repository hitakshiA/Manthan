"""Run the hard-scenario battery against any OpenRouter model.

For each scenario in scripts/scenarios.py:
  - Bind the scenario's world (header + facts + catalog) into the mock
    via contextvars
  - Drive the Manthan loop end-to-end against the model
  - Capture: queries, cross-source ratio, findings, decision, confidence,
    wall-clock
  - Score against ground truth: decision_match, amount_match (if any),
    keyword recall (did findings cite the right facts), keyword precision
    (did findings avoid the red herrings), confidence calibration

Aggregate report at the end.

Run:
    cd manthanv2/agent
    .venv/bin/python scripts/scenario_bake.py
    .venv/bin/python scripts/scenario_bake.py --model deepseek/deepseek-v4-pro:exacto
    .venv/bin/python scripts/scenario_bake.py --only S01,S05

Exit 0 if all scenarios completed (regardless of pass/fail); 1 on hard
errors (missing key, crash). Use the aggregate table to decide if Grok
is ready for step 5 (real Coral) or needs more prompt work.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# scripts/ isn't a package - bolt it onto sys.path so we can import scenarios.py
sys.path.insert(0, str(Path(__file__).parent))

from brutal_scenarios import SCENARIOS_BRUTAL
from coral_scenarios_data import SCENARIOS_CORAL
from real_workflows import WORKFLOWS_REAL
from scenarios import SCENARIOS, Scenario

from manthan_agent import config
from manthan_agent.coral_session import (
    clear_active_coral_session,
    coral_mcp_session,
    set_active_coral_session,
)
from manthan_agent.duckdb_world import build_world
from manthan_agent.loop import run_case
from manthan_agent.state import EventStore
from manthan_agent.tools import (
    clear_scenario_world,
    set_scenario_world,
)
from manthan_agent.types import CaseTrigger

console = Console()


# ──────────────────────────────────────────────────────────────────────
# Result + scoring
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ScenarioResult:
    scenario: Scenario
    closed_reason: str | None = None
    decision_action: str | None = None
    decision_confidence: float | None = None
    decision_amount_minor: int | None = None
    findings: list[str] = field(default_factory=list)
    finding_confidences: list[float] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    cross_source_count: int = 0
    wall_clock_s: float = 0.0
    error: str | None = None

    # Scoring
    decision_match: bool = False
    amount_match: bool = False
    confidence_ok: bool = False
    keyword_recall: float = 0.0
    keyword_precision: float = 1.0
    composite: float = 0.0


def _decision_matches(expected: str, result: ScenarioResult) -> bool:
    """Match logic that accepts ask_human as a valid form of escalate."""
    if expected == "escalate":
        return result.closed_reason == "ask_human" or result.decision_action == "escalate"
    return (result.decision_action or "").lower() == expected.lower()


def _amount_matches(expected: int | None, actual: int | None) -> bool:
    if expected is None:
        return True  # not scored
    if actual is None:
        return False
    # 25% tolerance for partial-refund math
    tolerance = max(int(expected * 0.25), 5000)  # at least $50 wiggle room
    return abs(actual - expected) <= tolerance


def _score(result: ScenarioResult) -> None:
    s = result.scenario
    result.decision_match = _decision_matches(s.expected_decision, result)
    result.amount_match = _amount_matches(
        s.expected_amount_minor, result.decision_amount_minor
    )
    if result.decision_confidence is not None:
        result.confidence_ok = result.decision_confidence >= s.expected_min_confidence
    else:
        # For ask_human path there's no Brief; treat min-confidence as
        # automatically satisfied (escalation is a low-conviction signal).
        result.confidence_ok = s.expected_decision == "escalate"

    blob = " ".join(result.findings).lower()
    # Recall: how many expected keywords appear (substring, case-insensitive)
    if s.expected_findings_keywords:
        hits = sum(1 for kw in s.expected_findings_keywords if kw.lower() in blob)
        result.keyword_recall = hits / len(s.expected_findings_keywords)
    else:
        result.keyword_recall = 1.0

    # Precision: penalty for citing must-not (red-herring) keywords
    if s.must_not_findings_keywords:
        misses = sum(1 for kw in s.must_not_findings_keywords if kw.lower() in blob)
        result.keyword_precision = 1.0 - (misses / len(s.must_not_findings_keywords))
    else:
        result.keyword_precision = 1.0

    # Composite: decision is the headline; recall/precision/conf are texture.
    result.composite = (
        0.50 * (1.0 if result.decision_match else 0.0)
        + 0.15 * (1.0 if result.amount_match else 0.0)
        + 0.15 * result.keyword_recall
        + 0.10 * result.keyword_precision
        + 0.10 * (1.0 if result.confidence_ok else 0.0)
    )


# ──────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────


async def run_one(scenario: Scenario, cfg) -> ScenarioResult:
    result = ScenarioResult(scenario=scenario)
    duck_con = None
    if scenario.duckdb_world is not None:
        # Brutal-data path - build the per-scenario in-memory DB.
        duck_con = build_world(scenario.duckdb_world)
        tokens = set_scenario_world(duckdb_con=duck_con)
    else:
        # Flat-bundle path - legacy
        tokens = set_scenario_world(
            header=scenario.dispute_header,
            facts=scenario.world,
            catalog=scenario.catalog or None,
        )
    try:
        trigger = CaseTrigger(
            case_id=scenario.case_id,
            text=scenario.trigger_text,
            source_surface="manual_web",
        )
        store = EventStore()
        t0 = time.monotonic()
        try:
            async for event in run_case(trigger, cfg, store):
                if event.kind == "tool_call" and event.data.get("name") == "coral_sql":
                    q = (event.data.get("arguments") or {}).get("query", "")
                    result.queries.append(q)
                    if _is_cross_source(q):
                        result.cross_source_count += 1
                elif event.kind == "finding_recorded":
                    result.findings.append(event.data.get("text", ""))
                    fc = event.data.get("confidence")
                    if isinstance(fc, (int, float)):
                        result.finding_confidences.append(float(fc))
                elif event.kind == "brief_drafted":
                    decision = event.data.get("decision") or {}
                    result.decision_action = decision.get("action")
                    result.decision_confidence = decision.get("confidence")
                    result.decision_amount_minor = decision.get("amount_minor")
                elif event.kind == "case_closed":
                    result.closed_reason = event.data.get("reason")
                elif event.kind == "error":
                    result.error = event.data.get("detail") or event.data.get("reason")
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
        result.wall_clock_s = time.monotonic() - t0
    finally:
        clear_scenario_world(tokens)
        if duck_con is not None:
            duck_con.close()
    _score(result)
    return result


def _is_cross_source(query: str) -> bool:
    # Lazy - count distinct <source>.<table> refs known to Coral
    known = {
        "stripe", "salesforce", "hubspot", "intercom", "zendesk", "slack",
        "notion", "posthog", "gmail", "pagerduty", "statusgator", "datadog",
        "sentry", "linear", "vertex_tax", "chargebee", "razorpay",
    }
    found: set[str] = set()
    import re

    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*", query.lower()):
        if m.group(1) in known:
            found.add(m.group(1))
    return len(found) > 1


# ──────────────────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────────────────


def _format_decision(r: ScenarioResult) -> str:
    if r.closed_reason == "ask_human":
        return "ask_human"
    if r.decision_action:
        amt = (
            f" ${r.decision_amount_minor / 100:.0f}"
            if r.decision_amount_minor
            else ""
        )
        return f"{r.decision_action}{amt}"
    if r.error:
        return "[red]ERR[/red]"
    return "[dim]-[/dim]"


def _format_match(ok: bool) -> str:
    return "[green]OK[/green]" if ok else "[red]X[/red]"


def report(results: list[ScenarioResult]) -> None:
    tbl = Table(title="Scenario Battery Results", border_style="cyan")
    tbl.add_column("Case", no_wrap=True)
    tbl.add_column("Pattern", no_wrap=True)
    tbl.add_column("Decision (got)", no_wrap=True)
    tbl.add_column("Expected", no_wrap=True)
    tbl.add_column("Match", justify="center")
    tbl.add_column("$Match", justify="center")
    tbl.add_column("Conf", justify="right")
    tbl.add_column("Recall", justify="right")
    tbl.add_column("Prec", justify="right")
    tbl.add_column("Findings", justify="right")
    tbl.add_column("Queries", justify="right")
    tbl.add_column("XSrc", justify="right")
    tbl.add_column("Wall(s)", justify="right")
    tbl.add_column("Composite", justify="right")

    for r in results:
        s = r.scenario
        tbl.add_row(
            s.case_id[:24],
            s.pattern_name[:22],
            _format_decision(r),
            s.expected_decision[:9],
            _format_match(r.decision_match),
            _format_match(r.amount_match) if s.expected_amount_minor else "[dim]-[/dim]",
            f"{r.decision_confidence:.2f}" if r.decision_confidence is not None else "-",
            f"{r.keyword_recall:.0%}",
            f"{r.keyword_precision:.0%}",
            str(len(r.findings)),
            str(len(r.queries)),
            f"{r.cross_source_count}/{len(r.queries)}" if r.queries else "0/0",
            f"{r.wall_clock_s:.0f}",
            f"{r.composite:.2f}",
        )
    console.print(tbl)

    # Aggregate
    n = len(results)
    if n == 0:
        return
    n_decision = sum(1 for r in results if r.decision_match)
    n_amount = sum(1 for r in results if r.amount_match and r.scenario.expected_amount_minor)
    amount_total = sum(1 for r in results if r.scenario.expected_amount_minor)
    avg_recall = sum(r.keyword_recall for r in results) / n
    avg_precision = sum(r.keyword_precision for r in results) / n
    avg_composite = sum(r.composite for r in results) / n
    total_wall = sum(r.wall_clock_s for r in results)
    avg_queries = sum(len(r.queries) for r in results) / n
    n_errors = sum(1 for r in results if r.error)

    summary = Table(title="Aggregate", show_header=False, border_style="cyan")
    summary.add_row("Decisions correct", f"{n_decision} / {n}  ({n_decision/n:.0%})")
    if amount_total:
        summary.add_row(
            "Amounts within tolerance",
            f"{n_amount} / {amount_total}  ({n_amount/amount_total:.0%})",
        )
    summary.add_row("Avg keyword recall", f"{avg_recall:.0%}")
    summary.add_row("Avg keyword precision (red-herring resistance)", f"{avg_precision:.0%}")
    summary.add_row("Avg coral_sql calls per case", f"{avg_queries:.1f}")
    summary.add_row("Total wall-clock", f"{total_wall:.0f}s  ({total_wall/60:.1f}min)")
    summary.add_row("Errors (crash / no conclude)", str(n_errors))
    summary.add_row("Average composite", f"{avg_composite:.2f}")
    console.print(summary)


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model",
        default="x-ai/grok-build-0.1",
        help="OpenRouter model id (default: x-ai/grok-build-0.1)",
    )
    p.add_argument(
        "--only",
        default=None,
        help="Comma-separated case-id prefixes to run (e.g. S01,S05,S01B). Default: all.",
    )
    p.add_argument(
        "--brutal",
        action="store_true",
        help="Run only brutal-data (DuckDB-backed) scenarios.",
    )
    p.add_argument(
        "--include-brutal",
        action="store_true",
        help="Include brutal-data scenarios alongside flat scenarios.",
    )
    p.add_argument(
        "--coral",
        action="store_true",
        help=(
            "Route coral_sql/coral_list_catalog/coral_describe_table through "
            "the real Coral MCP binary (cfg.coral_binary). Requires that the "
            "scenario's data has been registered with Coral; for brutal "
            "scenarios, run setup_coral_bridge.py first."
        ),
    )
    p.add_argument(
        "--quiet-findings",
        action="store_true",
        help="Don't print findings dump per case",
    )
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    cfg = dataclasses.replace(config.load(), model=args.model)
    if not cfg.openrouter_api_key:
        console.print(Panel("OPENROUTER_API_KEY not set", border_style="red"))
        return 1

    if args.brutal:
        pool: list[Scenario] = SCENARIOS_BRUTAL
    elif args.include_brutal:
        pool = [*SCENARIOS, *SCENARIOS_BRUTAL]
    else:
        pool = SCENARIOS

    selected: list[Scenario] = pool
    if args.only:
        wanted = [p.strip() for p in args.only.split(",") if p.strip()]
        # Search across ALL pools when --only is used so users can pick any
        # scenario without remembering which pool it's in.
        full_pool = [*SCENARIOS, *SCENARIOS_BRUTAL, *SCENARIOS_CORAL, *WORKFLOWS_REAL]
        selected = [s for s in full_pool if any(s.case_id.startswith(w) for w in wanted)]
        if not selected:
            console.print(Panel(f"No scenarios matched --only={args.only}", border_style="red"))
            return 1

    coral_label = (
        f"REAL Coral binary ({cfg.coral_binary})"
        if args.coral
        else "MOCK (per-scenario world via contextvar)"
    )
    console.print(
        Panel(
            f"[bold]model[/bold]      {args.model}\n"
            f"[bold]scenarios[/bold]  {len(selected)} / {len(SCENARIOS)}\n"
            f"[bold]coral[/bold]      {coral_label}",
            title="Scenario battery",
            border_style="cyan",
        )
    )

    # In --coral mode we keep ONE persistent Coral MCP session for the
    # whole batch. The session is bound to the contextvar inside run_one
    # so each scenario sees a fresh contextvar set/clear.
    if args.coral:
        async with coral_mcp_session(cfg.coral_binary) as session:
            results = await _run_battery(selected, cfg, args, coral_session=session)
    else:
        results = await _run_battery(selected, cfg, args, coral_session=None)

    console.print()
    report(results)
    return 0


async def _run_battery(
    scenarios: list[Scenario],
    cfg: Any,
    args: Any,
    coral_session: Any | None,
) -> list[ScenarioResult]:
    """Run each scenario in turn, optionally with a persistent Coral session."""
    results: list[ScenarioResult] = []
    for i, scenario in enumerate(scenarios, start=1):
        console.print(
            f"\n[dim]({i}/{len(scenarios)})[/dim] [bold cyan]{scenario.case_id}[/bold cyan]  "
            f"[dim]({scenario.pattern_name})[/dim]"
        )

        # Bind Coral session to contextvar IFF we're in --coral mode.
        coral_token = None
        if coral_session is not None:
            coral_token = set_active_coral_session(coral_session)
        try:
            r = await run_one(scenario, cfg)
        finally:
            if coral_token is not None:
                clear_active_coral_session(coral_token)
        results.append(r)

        if r.error:
            console.print(f"  [red]ERROR:[/red] {r.error}")
        else:
            console.print(
                f"  → {_format_decision(r)}  "
                f"(conf {r.decision_confidence or 0:.2f}, "
                f"{len(r.findings)} findings, "
                f"{len(r.queries)} queries, "
                f"{r.wall_clock_s:.0f}s)"
            )
            if not args.quiet_findings and r.findings:
                for j, f in enumerate(r.findings[:6]):
                    snippet = f[:130] + ("..." if len(f) > 130 else "")
                    console.print(f"    [dim]F{j + 1}.[/dim] {snippet}")
                # Dump full findings (untruncated) so we can tune keywords
                # to actual agent phrasing on the next iteration.
                findings_path = (
                    Path(".manthan/runs")
                    / f"{scenario.case_id}_findings.txt"
                )
                findings_path.parent.mkdir(parents=True, exist_ok=True)
                with findings_path.open("w") as f:
                    f.write(f"# {scenario.case_id} - findings dump\n")
                    f.write(f"# decision: {r.decision_action} "
                            f"amount: {r.decision_amount_minor} "
                            f"conf: {r.decision_confidence}\n\n")
                    for j, finding in enumerate(r.findings):
                        f.write(f"--- F{j + 1} ---\n{finding}\n\n")
                console.print(f"    [dim]→ full findings dumped to {findings_path}[/dim]")
            if not args.quiet_findings and r.queries:
                for j, q in enumerate(r.queries):
                    oneliner = " ".join(q.split())
                    if len(oneliner) > 160:
                        oneliner = oneliner[:157] + "..."
                    console.print(f"    [dim]Q{j + 1}.[/dim] {oneliner}")
                # Dump full SQL (untruncated) to a per-case log file so we
                # can analyze cross-source JOIN patterns after the run.
                log_path = (
                    Path(".manthan/runs")
                    / f"{scenario.case_id}_queries.sql"
                )
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("w") as f:
                    for j, q in enumerate(r.queries):
                        f.write(f"-- Q{j + 1}\n{q.strip()};\n\n")
                console.print(f"    [dim]→ full SQL dumped to {log_path}[/dim]")
        mark = "[green]OK[/green]" if r.decision_match else "[red]MISS[/red]"
        console.print(
            f"  decision: {mark}  composite: [bold]{r.composite:.2f}[/bold]"
        )
    return results


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
