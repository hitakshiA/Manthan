"""Tool definitions + execution router for the agent loop.

Each tool maps to a Layer 1 HTTP endpoint. Tool descriptions encode
behavioral rules — the LLM reads them at every decision point.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from src.agent.config import AgentConfig

# OpenAI-format function definitions for the LLM
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": (
                "Get compact schema: table names, column roles, summary "
                "tables, verified queries. Call FIRST before any SQL/Python. "
                "Cheap and fast."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                },
                "required": ["dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_context",
            "description": (
                "Full DCD with column descriptions, aggregation rules, "
                "quality metadata, agent instructions. Optionally prune "
                "to columns relevant to a query. Use when you need "
                "detailed semantics beyond get_schema."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                    "query": {
                        "type": "string",
                        "description": "Natural language query to prune columns",
                    },
                },
                "required": ["dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": (
                "Execute read-only SQL against the dataset's DuckDB. "
                "Available: gold table, summary tables, temp tables from "
                "prior calls. Verify names via get_schema first. Include "
                "LIMIT 100 on exploratory queries. Supports SELECT, WITH, "
                "DESCRIBE, SHOW TABLES, CREATE TEMP TABLE, DROP TEMP. "
                "NOTE: temp tables here are NOT visible in run_python. "
                "If a NAMED business metric covers your question "
                "(revenue, AOV, margin, churn, retention — anything "
                "listed in the Entity's 'Governed metrics' section), "
                "PREFER compute_metric so the declared filter and "
                "aggregation semantics are applied deterministically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                    "sql": {"type": "string"},
                    "max_rows": {"type": "integer", "default": 1000},
                },
                "required": ["dataset_id", "sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_metric",
            "description": (
                "Governed happy-path for named business metrics. Use this "
                "whenever the question names a metric declared in the "
                "Entity's 'Governed metrics' block (revenue, AOV, margin, "
                "etc.). Manthan composes SQL from the metric's declared "
                "expression + baked-in filter, so the answer respects the "
                "business definition without you having to remember it. "
                "Specify 'entity' as the entity slug, 'metric' as the "
                "metric slug, optional 'dimensions' to GROUP BY, 'filters' "
                "as additional predicates (scalar, list, or {gte,lte,eq} "
                "range), and 'grain' for time rollup. The response carries "
                "the composed SQL for audit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "Entity slug, e.g. 'orders'.",
                    },
                    "metric": {
                        "type": "string",
                        "description": "Metric slug, e.g. 'revenue'.",
                    },
                    "dimensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Columns to GROUP BY (optional).",
                    },
                    "filters": {
                        "type": "object",
                        "description": (
                            "Extra filters ANDed with the metric's declared "
                            "filter. Values may be scalar, list (IN), or "
                            "{gte, lte, gt, lt, eq} for ranges."
                        ),
                    },
                    "grain": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"],
                        "description": (
                            "Time grain for a time-series slice. Requires "
                            "the entity to have a temporal column."
                        ),
                    },
                    "limit": {"type": "integer", "default": 500},
                },
                "required": ["entity", "metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Execute Python in a persistent sandbox. Pre-loaded: "
                "df (pandas DataFrame), con (DuckDB with 'dataset' view "
                "for primary table + named views for all gold parquets), "
                "OUTPUT_DIR (writable), DATA_DIR (read-only). Variables "
                "persist across calls with same session_id. Write outputs "
                "to OUTPUT_DIR (parquet files). "
                "NOTE: con here is SEPARATE from run_sql's connection."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                    "code": {"type": "string"},
                    "session_id": {
                        "type": "string",
                        "description": "Reuse to keep state across calls",
                    },
                    "timeout_seconds": {"type": "integer", "default": 60},
                },
                "required": ["dataset_id", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Check with the exec in propose-first style. Only call when "
                "two credible interpretation paths would materially diverge "
                "in what you investigate (EVPI stop rule). Questions with "
                "adjectives of judgment ('best', 'struggling', 'good') "
                "usually need this; specific column references usually "
                "don't. ALWAYS populate proposed_interpretation (your "
                "working read, one sentence, exec language) and "
                "why_this_matters (what flips downstream). The UI renders "
                "these prominently as an analyst's note, not a form."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "prompt": {
                        "type": "string",
                        "description": "Plain-English question (short — the UI shows interpretation/why separately)",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-3 alternative interpretations in exec language",
                    },
                    "proposed_interpretation": {
                        "type": "string",
                        "description": "Your working interpretation in one sentence, exec language. Shown prominently in the UI.",
                    },
                    "why_this_matters": {
                        "type": "string",
                        "description": "One sentence: why the clarification matters — what flips downstream.",
                    },
                    "ambiguity_type": {
                        "type": "string",
                        "enum": [
                            "intent",
                            "vague_goal",
                            "parameter",
                            "value",
                            "contextual",
                        ],
                        "description": "MAC-taxonomy classification of the ambiguity (see prompt for definitions).",
                    },
                },
                "required": ["session_id", "prompt", "options"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_plan",
            "description": (
                "Submit a structured analysis plan for user approval. "
                "Use when 3+ tool calls expected OR after resolving "
                "ambiguity via ask_user. Include interpretation grounded "
                "in DCD citations. Wait for approval before executing. "
                "Skip for simple single-number questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "dataset_id": {"type": "string"},
                    "user_question": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string"},
                                "identifier": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                        },
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "tool": {"type": "string"},
                                "description": {"type": "string"},
                                "depends_on": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "expected_cost": {"type": "object"},
                    "risks": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "session_id",
                    "dataset_id",
                    "user_question",
                    "interpretation",
                    "steps",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Persist conclusions to cross-session storage. Write at "
                "END of complex analyses. Key convention: {topic}_{dataset}. "
                "Write CONCLUSIONS not raw data. Use scope_type=dataset "
                "for durable findings, session for subagent bridging."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scope_type": {
                        "type": "string",
                        "enum": ["dataset", "user", "global", "session"],
                    },
                    "scope_id": {"type": "string"},
                    "key": {"type": "string"},
                    "value": {},
                    "category": {
                        "type": "string",
                        "enum": ["preference", "definition", "caveat", "fact", "note"],
                    },
                    "description": {"type": "string"},
                },
                "required": ["scope_type", "scope_id", "key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": (
                "Search for prior conclusions. Call at START of every "
                "conversation to check for existing analysis. If found, "
                "surface to user: 'I found prior analysis. Continue?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scope_type": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emit_visual",
            "description": (
                "Show an inline visual in the conversation — a small HTML "
                "snippet (NOT a full document) rendered directly in the chat. "
                "Use for quick visuals during exploration. Types:\n"
                "- stat_card: Single KPI (value + label + delta)\n"
                "- stat_strip: Row of 3-5 KPI cards\n"
                "- mini_chart: Small Chart.js chart (~200px tall)\n"
                "- chart_insight: Chart + narrative callout above\n"
                "- comparison: Side-by-side before/after cards\n"
                "- heatmap: Color-coded grid (cohort, correlation)\n"
                "- callout: Highlighted insight/warning/tip card\n"
                "- progress: Horizontal progress/funnel steps\n\n"
                "The HTML is a FRAGMENT (no <html>/<head>/<body>). "
                "It will be wrapped in a container with these fonts/colors "
                "pre-loaded: Inter for body, Instrument Serif for values, "
                "palette: #6e56cf (accent), #3b8263 (success), #bd9e14 "
                "(warning), #c92f31 (error). Background: transparent. "
                "Cards: white (#fff) with 1px solid #e8e8e7 border, "
                "border-radius:12px. Use inline styles only.\n\n"
                "For Chart.js: include a <canvas> + <script> that creates "
                "the chart. Chart.js 4.5 is pre-loaded in the container.\n\n"
                "Keep HTML under 3000 chars. For complex outputs, use "
                "create_artifact instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "visual_type": {
                        "type": "string",
                        "enum": [
                            "stat_card",
                            "stat_strip",
                            "mini_chart",
                            "chart_insight",
                            "comparison",
                            "heatmap",
                            "callout",
                            "progress",
                        ],
                        "description": "Type of inline visual",
                    },
                    "html": {
                        "type": "string",
                        "description": "HTML fragment with inline styles",
                    },
                    "height": {
                        "type": "integer",
                        "description": "Height in px (default 200)",
                    },
                },
                "required": ["visual_type", "html"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_artifact",
            "description": (
                "Create a self-contained HTML dashboard/report/tool rendered "
                "live in the artifact panel. Use the Manthan Artifact Design "
                "System from the system prompt (fonts, colors, card styles, "
                "Chart.js palette). Must be a single complete HTML file with "
                "Chart.js 4.5 CDN, inline CSS matching the design system, "
                "embedded pre-aggregated data, and a Dashboard class with "
                "applyFilters() that updates all charts + KPIs + tables. "
                "Background: #f6f6f5 (warm gray). Cards: white with 1px "
                "border. Headings: Instrument Serif. Body: Inter. "
                "NEVER use dark backgrounds for the dashboard body."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Artifact title shown in panel header",
                    },
                    "html": {
                        "type": "string",
                        "description": (
                            "Complete self-contained HTML document with "
                            "inline styles, Chart.js CDN, embedded data, "
                            "and dashboard logic"
                        ),
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename like 'revenue_dashboard.html'",
                    },
                },
                "required": ["title", "html"],
            },
        },
    },
]


class ToolRouter:
    """Maps tool calls to Layer 1 HTTP endpoints."""

    def __init__(self, config: AgentConfig) -> None:
        self.client = httpx.AsyncClient(
            base_url=config.layer1_url,
            timeout=float(config.timeout_seconds),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def execute(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool call against Layer 1. Returns JSON string."""
        try:
            result = await self._dispatch(name, args)
            return self._truncate(result)
        except httpx.HTTPStatusError as exc:
            return json.dumps(
                {
                    "error": f"HTTP {exc.response.status_code}",
                    "detail": exc.response.text[:500],
                }
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)[:500]})

    async def _dispatch(self, name: str, args: dict[str, Any]) -> str:
        if name == "get_schema":
            r = await self.client.get(f"/datasets/{args['dataset_id']}/schema")
            r.raise_for_status()
            return r.text
        if name == "get_context":
            params = {}
            if args.get("query"):
                params["query"] = args["query"]
            r = await self.client.get(
                f"/datasets/{args['dataset_id']}/context",
                params=params,
            )
            r.raise_for_status()
            return r.text
        if name == "run_sql":
            r = await self.client.post(
                "/tools/sql",
                json={
                    "dataset_id": args["dataset_id"],
                    "sql": args["sql"],
                    "max_rows": args.get("max_rows", 1000),
                },
            )
            r.raise_for_status()
            return r.text
        if name == "compute_metric":
            body = {
                "entity": args["entity"],
                "metric": args["metric"],
                "dimensions": args.get("dimensions", []),
                "filters": args.get("filters", {}),
                "limit": args.get("limit", 500),
            }
            if args.get("grain"):
                body["grain"] = args["grain"]
            r = await self.client.post("/tools/metric", json=body)
            r.raise_for_status()
            return r.text
        if name == "run_python":
            body: dict[str, Any] = {
                "dataset_id": args["dataset_id"],
                "code": args["code"],
                "timeout_seconds": args.get("timeout_seconds", 60),
            }
            if args.get("session_id"):
                body["session_id"] = args["session_id"]
            r = await self.client.post("/tools/python", json=body)
            r.raise_for_status()
            return r.text
        if name == "ask_user":
            body: dict[str, Any] = {
                "session_id": args["session_id"],
                "prompt": args["prompt"],
                "options": args.get("options", []),
                "allow_free_text": True,
            }
            # Propose-first extensions (all optional, backward compatible)
            if args.get("proposed_interpretation"):
                body["proposed_interpretation"] = args["proposed_interpretation"]
            if args.get("why_this_matters"):
                body["why_this_matters"] = args["why_this_matters"]
            if args.get("ambiguity_type"):
                body["ambiguity_type"] = args["ambiguity_type"]
            r = await self.client.post("/ask_user", json=body)
            r.raise_for_status()
            q = r.json()
            # Wait up to 30s — if no answer, return timeout so the
            # agent proceeds with its best judgment
            r2 = await self.client.post(
                f"/ask_user/{q['id']}/wait",
                params={"timeout_seconds": 30},
            )
            r2.raise_for_status()
            result = r2.json()
            if result.get("timed_out"):
                return json.dumps(
                    {
                        "status": "timed_out",
                        "note": "User did not respond within 30s. "
                        "Proceed with your best interpretation.",
                    }
                )
            return r2.text
        if name == "create_plan":
            r = await self.client.post("/plans", json=args)
            r.raise_for_status()
            plan = r.json()
            plan_id = plan["id"]
            await self.client.post(f"/plans/{plan_id}/submit")
            r3 = await self.client.post(
                f"/plans/{plan_id}/wait",
                params={"timeout_seconds": 30},
            )
            r3.raise_for_status()
            result = r3.json()
            if result.get("timed_out"):
                # Auto-approve if user doesn't respond
                await self.client.post(
                    f"/plans/{plan_id}/approve",
                    json={"actor": "auto_timeout"},
                )
                return json.dumps(
                    {
                        "status": "auto_approved",
                        "plan_id": plan_id,
                        "note": "Plan auto-approved after 30s timeout.",
                    }
                )
            return r3.text
        if name == "save_memory":
            r = await self.client.post(
                "/memory",
                json={
                    "scope_type": args["scope_type"],
                    "scope_id": args["scope_id"],
                    "key": args["key"],
                    "value": args["value"],
                    "category": args.get("category", "note"),
                    "description": args.get("description"),
                },
            )
            r.raise_for_status()
            return r.text
        if name == "recall_memory":
            params: dict[str, str] = {"query": args["query"]}
            if args.get("scope_type"):
                params["scope_type"] = args["scope_type"]
            r = await self.client.get("/memory/search/", params=params)
            r.raise_for_status()
            return r.text

        return json.dumps({"error": f"Unknown tool: {name}"})

    def _truncate(self, text: str, max_chars: int = 16000) -> str:
        """Truncate large results to stay within context budget."""
        if len(text) <= max_chars:
            return text
        # Try to truncate JSON rows intelligently
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "rows" in data:
                rows = data["rows"]
                if len(rows) > 50:
                    data["rows"] = rows[:50]
                    data["truncated"] = True
                    data["_note"] = f"Showing 50 of {len(rows)} rows"
                    return json.dumps(data)
        except (json.JSONDecodeError, TypeError):
            pass
        return text[:max_chars] + "\n[TRUNCATED]"
