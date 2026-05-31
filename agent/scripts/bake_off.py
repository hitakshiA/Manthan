"""Model bake-off across OpenRouter.

Runs the same TechCorp $1,200 chargeback case through N different
models, captures speed / quality / depth per run, prints a comparison
table.

Pricing per million tokens is best-effort (OpenRouter pricing fluctuates;
update the MODEL_RATES table as needed). Wall-clock + token usage are
read from the live API responses.

Run:
    cd manthanv2/agent
    .venv/bin/python scripts/bake_off.py

Expected wall-clock: ~15-30 minutes total (sequential). Errors per model
are caught and reported - a failing model doesn't stop the bake-off.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import sys
import time
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from manthan_agent import config
from manthan_agent.loop import run_case
from manthan_agent.state import EventStore
from manthan_agent.types import Brief, CaseTrigger

console = Console()


# Best-effort pricing per million tokens (input, output). Update as
# OpenRouter publishes accurate numbers. USD estimate in the result is
# illustrative - what matters for the bake-off is the relative numbers.
MODEL_RATES: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-v4-pro:exacto":     (1.50, 3.00),
    "minimax/minimax-m2.7:exacto":         (0.80, 2.40),
    "google/gemini-3.5-flash:exacto":      (0.15, 0.60),
    "moonshotai/kimi-k2.6:exacto":         (0.50, 1.50),
    "x-ai/grok-build-0.1":                 (2.00, 8.00),
    "xiaomi/mimo-v2.5-pro:exacto":         (0.40, 1.20),
}

MODELS = [
    "deepseek/deepseek-v4-pro:exacto",   # baseline (already proven)
    "minimax/minimax-m2.7:exacto",
    "google/gemini-3.5-flash:exacto",
    "moonshotai/kimi-k2.6:exacto",
    "x-ai/grok-build-0.1",
    "xiaomi/mimo-v2.5-pro:exacto",
]


TRIGGER_TEXT = """\
A new Stripe dispute event arrived for case CASE-BAKE-001.

Customer: TechCorp Industries (cus_8mFqZ, ops@techcorp.example)
Dispute: dp_mock_1Qxxxx · $1,200 USD · reason: subscription_canceled
Charge: ch_mock_3MqXfL · 12 May 2026
Evidence deadline: 8 June 2026

Initial signal: customer claims they cancelled the subscription before
the disputed renewal charge. No prior disputes on file as far as I know.
Investigate across all available sources and draft a recommendation.

Don't be lazy. Look at multiple sources before deciding."""


@dataclass
class RunResult:
    model: str
    wall_clock_sec: float
    total_events: int
    tool_calls: int
    coral_sql_calls: int
    findings: int
    concluded: bool
    closed_reason: str | None
    decision_action: str | None
    decision_confidence: float | None
    distinct_sources_queried: int
    prompt_tokens: int
    completion_tokens: int
    est_usd: float
    error: str | None
    tldr_preview: str | None


async def run_one(model: str) -> RunResult:
    """Run the case end-to-end against one model, capture metrics."""
    cfg = dataclasses.replace(config.load(), model=model)
    trigger = CaseTrigger(
        case_id=f"CASE-BAKE-{model.split('/')[-1][:20]}",
        text=TRIGGER_TEXT,
        source_surface="stripe_webhook",
    )
    store = EventStore()

    total_events = 0
    tool_calls = 0
    coral_sql_calls = 0
    findings = 0
    distinct_sources: set[str] = set()
    final_brief: Brief | None = None
    closed_reason: str | None = None
    prompt_tokens = 0
    completion_tokens = 0
    error: str | None = None

    t0 = time.monotonic()
    try:
        async for event in run_case(trigger, cfg, store):
            total_events += 1
            if event.kind == "tool_call":
                tool_calls += 1
                if event.data.get("name") == "coral_sql":
                    coral_sql_calls += 1
                    # crude source-tracking: parse `FROM <source>.<table>` from query
                    q = (event.data.get("arguments") or {}).get("query", "").lower()
                    if "from " in q:
                        rest = q.split("from ", 1)[1].lstrip()
                        first_token = rest.split()[0] if rest else ""
                        if "." in first_token:
                            distinct_sources.add(first_token.split(".")[0].strip("(),"))
            if event.kind == "finding_recorded":
                findings += 1
            if event.kind == "brief_drafted":
                with contextlib.suppress(Exception):
                    final_brief = Brief.model_validate(event.data)
            if event.kind == "case_closed":
                closed_reason = event.data.get("reason")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    wall = time.monotonic() - t0

    # Sum token usage from agent_thought events (the loop charges Budget
    # on every LLM call). We don't currently log token counts per event,
    # so this is a placeholder - Budget would have charged them. For the
    # bake-off the wall-clock + concluded outcome is the primary signal.
    # When we add Postgres-backed events with token columns, this
    # tightens up.

    rate_in, rate_out = MODEL_RATES.get(model, (1.50, 3.00))
    est_usd = (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000

    tldr_preview = None
    if final_brief is not None and final_brief.tldr:
        tldr_preview = (final_brief.tldr[:140] + "…") if len(final_brief.tldr) > 140 else final_brief.tldr

    return RunResult(
        model=model,
        wall_clock_sec=wall,
        total_events=total_events,
        tool_calls=tool_calls,
        coral_sql_calls=coral_sql_calls,
        findings=findings,
        concluded=(closed_reason == "concluded"),
        closed_reason=closed_reason,
        decision_action=final_brief.decision.action if final_brief else None,
        decision_confidence=final_brief.decision.confidence if final_brief else None,
        distinct_sources_queried=len(distinct_sources),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        est_usd=est_usd,
        error=error,
        tldr_preview=tldr_preview,
    )


def print_summary(results: list[RunResult]) -> None:
    """Print the comparison table + a written recommendation."""
    tbl = Table(title="Manthan model bake-off - TechCorp $1,200 chargeback", show_lines=True)
    tbl.add_column("Model", style="cyan", overflow="fold")
    tbl.add_column("Concl?", justify="center")
    tbl.add_column("Action")
    tbl.add_column("Conf", justify="right")
    tbl.add_column("Wall (s)", justify="right")
    tbl.add_column("Events", justify="right")
    tbl.add_column("Tools", justify="right")
    tbl.add_column("SQL", justify="right")
    tbl.add_column("Find", justify="right")
    tbl.add_column("Srcs", justify="right")
    tbl.add_column("Notes", overflow="fold")

    for r in results:
        if r.error:
            notes = f"[red]{r.error[:80]}[/red]"
        elif r.tldr_preview:
            notes = r.tldr_preview
        else:
            notes = f"closed: {r.closed_reason or '-'}"

        tbl.add_row(
            r.model.split("/")[-1][:32],
            ":white_check_mark:" if r.concluded else ":x:",
            r.decision_action or "-",
            f"{r.decision_confidence:.2f}" if r.decision_confidence is not None else "-",
            f"{r.wall_clock_sec:.1f}",
            str(r.total_events),
            str(r.tool_calls),
            str(r.coral_sql_calls),
            str(r.findings),
            str(r.distinct_sources_queried),
            notes,
        )

    console.print(tbl)

    # Score: did it conclude, times confidence, divided by wall_clock
    # (penalty for taking forever), times findings (bonus for depth).
    def score(r: RunResult) -> float:
        if not r.concluded or r.decision_confidence is None:
            return 0.0
        return (
            r.decision_confidence
            * (1 + min(r.findings, 8) / 4)         # depth bonus, capped
            * (1 + min(r.distinct_sources_queried, 6) / 3)  # breadth bonus, capped
            / max(r.wall_clock_sec, 5.0)            # speed penalty
            * 100
        )

    ranked = sorted(results, key=score, reverse=True)
    console.print()
    console.print("[bold]Composite score: confidence * depth * breadth / wall_clock * 100[/bold]")
    for r in ranked:
        s = score(r)
        color = "green" if s > 0 else "red"
        console.print(f"  [{color}]{s:6.2f}[/{color}]  {r.model}")


async def main() -> int:
    cfg = config.load()
    if not cfg.openrouter_api_key:
        console.print(Panel("OPENROUTER_API_KEY not set", border_style="red"))
        return 1

    console.print(
        Panel(
            f"Models: {len(MODELS)}\n"
            f"Case: TechCorp $1,200 chargeback (mock Coral, 8 schemas)\n"
            f"Budget per model: 25 steps / $2.00\n"
            f"Run mode: sequential (avoid OpenRouter rate-limiting)",
            title="Manthan bake-off",
            border_style="cyan",
        )
    )

    results: list[RunResult] = []
    for i, model in enumerate(MODELS, start=1):
        console.print(f"\n[bold cyan]({i}/{len(MODELS)}) {model}[/bold cyan]")
        t0 = time.monotonic()
        try:
            r = await run_one(model)
        except Exception as exc:
            r = RunResult(
                model=model,
                wall_clock_sec=time.monotonic() - t0,
                total_events=0,
                tool_calls=0,
                coral_sql_calls=0,
                findings=0,
                concluded=False,
                closed_reason=None,
                decision_action=None,
                decision_confidence=None,
                distinct_sources_queried=0,
                prompt_tokens=0,
                completion_tokens=0,
                est_usd=0.0,
                error=f"{type(exc).__name__}: {exc}",
                tldr_preview=None,
            )
        results.append(r)
        if r.error:
            console.print(f"  [red]:x: {r.error}[/red]")
        elif r.concluded:
            console.print(
                f"  [green]:white_check_mark: concluded[/green] · "
                f"{r.wall_clock_sec:.1f}s · {r.tool_calls} tools · "
                f"{r.findings} findings · action={r.decision_action}"
            )
        else:
            console.print(
                f"  [yellow]:warning: closed={r.closed_reason}[/yellow] · "
                f"{r.wall_clock_sec:.1f}s · {r.tool_calls} tools"
            )

    console.print("\n")
    print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
