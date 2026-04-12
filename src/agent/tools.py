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
                "NOTE: temp tables here are NOT visible in run_python."
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
            "name": "run_python",
            "description": (
                "Execute Python in a persistent sandbox. Pre-loaded: "
                "df (pandas DataFrame), con (DuckDB with 'dataset' view "
                "for primary table + named views for all gold parquets), "
                "OUTPUT_DIR (writable), DATA_DIR (read-only). Variables "
                "persist across calls with same session_id. Write outputs "
                "to OUTPUT_DIR (parquet files, render_spec.json). "
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
                "Ask a clarifying question and block until answered. Use "
                "when 2+ plausible interpretations would produce materially "
                "different answers. Questions with adjectives (busy, "
                "successful, undervalued) almost always need clarification. "
                "Specific column references almost never do. Provide clear "
                "human-friendly options the user can click."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "prompt": {
                        "type": "string",
                        "description": "Plain-English question",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Clickable option labels",
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
            # Create question
            r = await self.client.post(
                "/ask_user",
                json={
                    "session_id": args["session_id"],
                    "prompt": args["prompt"],
                    "options": args.get("options", []),
                    "allow_free_text": True,
                },
            )
            r.raise_for_status()
            q = r.json()
            # Block until answered
            r2 = await self.client.post(
                f"/ask_user/{q['id']}/wait",
                params={"timeout_seconds": 300},
            )
            r2.raise_for_status()
            return r2.text
        if name == "create_plan":
            # Create + submit + wait for approval
            r = await self.client.post("/plans", json=args)
            r.raise_for_status()
            plan = r.json()
            plan_id = plan["id"]
            await self.client.post(f"/plans/{plan_id}/submit")
            r3 = await self.client.post(
                f"/plans/{plan_id}/wait",
                params={"timeout_seconds": 600},
            )
            r3.raise_for_status()
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
