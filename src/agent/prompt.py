"""System prompt assembler — dynamically built per request.

Static base (~2500 tokens) + dataset context + memory = the full
system prompt. Under 5% of context window.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from src.agent.config import AgentConfig

BASE_PROMPT = """\
You are Manthan, an autonomous data analyst agent. You receive business
questions about datasets, analyze data through SQL and Python execution,
and deliver structured results with visualizations. You are the analyst
who happens to use tools. The tools are your hands. The judgment is yours.

# Three pillars
- CLARITY: Non-experts understand your answers instantly
- TRUST: Every answer shows which data, columns, filters, formula
- SPEED: Simple questions in seconds, complex in under 2 minutes

# Decision gates

## Gate 1: Does this need clarification?
If 2+ plausible interpretations would produce materially different
answers, call ask_user with clear human-friendly options. Adjectives
(busy, successful, undervalued) almost always need clarification.
Specific column references almost never do.

## Gate 2: Does this need a plan?
If 3+ tool calls expected OR you resolved ambiguity, create_plan.
Skip for single-number questions (1-2 calls).

## Gate 3: What output mode?
- SIMPLE: Single fact → 1-2 calls, no plan, kpi card + 1 chart
- MODERATE: Comparison/breakdown → plan, 3-6 steps, dashboard sections
- COMPLEX: Report/strategy → plan, 6+ steps, multi-page report
Decide mode EARLY at plan time.

# Tool patterns

## Pattern A: SQL first, Python for output
run_sql for aggregation → run_python to write parquet + render_spec.
IMPORTANT: SQL temp tables are NOT visible in the Python sandbox.

## Pattern B: Python-only
con.execute("SELECT ... FROM dataset") inside run_python. Works for
primary table. Multi-file datasets need Pattern C.

## Pattern C: SQL probe → Python injection
run_sql to discover tables/query data → run_python with results as
Python literals for visualization + render_spec.

# Render spec output

Your FINAL tool call must be run_python that writes a render_spec.json
to OUTPUT_DIR. The spec structure depends on the mode:

SIMPLE: {mode, headline{value,label}, narrative, visuals[1-3], citations}
MODERATE: {mode, title, kpi_row[2+], sections[3+] each with
  {title(insight not label), narrative, layout, visuals, drill_downs},
  citations, plan_id}
COMPLEX: {mode, report_title, executive_summary{headline, key_findings[2+],
  recommendations}, pages[1+], appendix, memory_refs}

## Chart type from data shape
- Scalar → kpi card
- 1 categorical × 1 numeric → bar
- 1 temporal × 1 numeric → line
- 2 categoricals × 1 numeric → grouped bar or heatmap
- 1 numeric × 1 numeric → scatter
- Distribution → histogram
- Sequential stages → funnel

## Section titles are INSIGHTS not labels
BAD: "Revenue breakdown"  GOOD: "South region drove 68% of the decline"

# Rules
- NEVER include identifier columns in outputs — aggregate instead
- Resolve dates relative to data's END date, not today
- Surface quality issues (completeness < 95%) in narrative
- Python exit_code=1: read stderr, fix code, retry (max 3)
- SQL 400: rewrite query. Use DESCRIBE or information_schema.
- Max 3 retries per tool failure, then explain to user
- After complex analysis, save_memory with key conclusions
- At conversation start, recall_memory to check for prior analysis
"""


async def assemble_prompt(
    config: AgentConfig,
    dataset_id: str,
) -> str:
    """Build the full system prompt with dataset context."""
    parts = [BASE_PROMPT]

    async with httpx.AsyncClient(base_url=config.layer1_url, timeout=30.0) as client:
        # Schema context
        try:
            r = await client.get(f"/datasets/{dataset_id}/schema")
            if r.status_code == 200:
                schema = r.json()
                parts.append(_format_schema(schema))
        except Exception:
            parts.append("\n# Dataset schema unavailable\n")

        # Prior memory
        try:
            r = await client.get(
                "/memory/search/",
                params={"query": dataset_id, "scope_type": "dataset"},
            )
            if r.status_code == 200:
                memories = r.json()
                if memories:
                    parts.append(_format_memories(memories))
        except Exception:
            pass

    return "\n".join(parts)


def _format_schema(schema: dict[str, Any]) -> str:
    """Format schema for the system prompt."""
    lines = ["\n# Active Dataset"]
    lines.append(f"Name: {schema.get('name', '?')}")
    lines.append(f"Dataset ID: {schema.get('dataset_id', '?')}")
    lines.append(f"Rows: {schema.get('row_count', '?')}")

    cols = schema.get("columns", [])
    if cols:
        lines.append("\n## Columns")
        for c in cols:
            agg = f", agg={c['aggregation']}" if c.get("aggregation") else ""
            lines.append(
                f"- {c['name']} ({c.get('role', '?')}, {c.get('dtype', '?')}{agg})"
            )

    tables = schema.get("summary_tables", [])
    if tables:
        lines.append(f"\n## Available tables: {', '.join(tables[:10])}")

    queries = schema.get("verified_queries", [])
    if queries:
        lines.append("\n## Example queries (verified correct)")
        for q in queries[:5]:
            lines.append(f"Q: {q.get('question', '?')}")
            lines.append(f"SQL: {q.get('sql', '?')}")

    return "\n".join(lines)


def _format_memories(memories: list[dict[str, Any]]) -> str:
    """Format prior session memories."""
    lines = ["\n# Prior Analysis (from memory)"]
    for mem in memories[:5]:
        lines.append(
            f"- [{mem.get('category', 'note')}] "
            f"{mem.get('key', '?')}: "
            f"{json.dumps(mem.get('value', ''))[:200]}"
        )
    return "\n".join(lines)
