"""Tool discovery endpoint — ``GET /tools/list``.

A hand-crafted static manifest of every agent-facing tool in Layer 1.
We keep it static (rather than scraping the FastAPI OpenAPI schema)
because (a) it lets us curate the agent-level description separately
from the HTTP-level parameters, and (b) the tool count is small
enough that auto-generation isn't worth the complexity.

When a new tool is added to Layer 1, add it to ``_TOOL_MANIFEST``
below so Layer 2 can discover it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["tools"])


_TOOL_MANIFEST: list[dict[str, Any]] = [
    {
        "name": "run_sql",
        "endpoint": "POST /tools/sql",
        "description": (
            "Execute a read-only SQL query against the dataset's Gold table. "
            "Supports SELECT, WITH, CREATE TEMP TABLE/VIEW (scratchpad across "
            "turns), and DROP TABLE/VIEW on temp objects only. 30-second "
            "timeout. Use temp tables to build up multi-step analyses."
        ),
        "input": {
            "dataset_id": "str (required)",
            "sql": (
                "str (required) — SELECT / WITH / "
                "CREATE TEMP TABLE / DROP TABLE (temp only)"
            ),
            "max_rows": "int (default 1000)",
        },
        "output": (
            "SqlResult with columns, rows, row_count, truncated, "
            "execution_time_ms, statement_kind, affected"
        ),
    },
    {
        "name": "run_python",
        "endpoint": "POST /tools/python",
        "description": (
            "Execute Python code in a stateful sandboxed session. "
            "Variables, imports, and DataFrames persist across calls "
            "when the same session_id is passed. Pre-loaded globals: "
            "df (pandas DataFrame of the primary Gold table), "
            "con (DuckDB connection with all Gold parquets attached "
            "as views — the primary table is named 'dataset', "
            "additional tables from multi-file uploads are named by "
            "their parquet stem e.g. 'gold_teams_xxx'), "
            "OUTPUT_DIR (writable path for parquet outputs), "
            "DATA_DIR (read-only path to the dataset's parquet "
            "files). Libraries: pandas, numpy, scipy, sklearn, "
            "plotly, matplotlib, duckdb, pyarrow."
        ),
        "input": {
            "dataset_id": "str (required)",
            "code": "str (required)",
            "session_id": (
                "str (optional — generated if omitted, reuse to keep state)"
            ),
            "timeout_seconds": "int (default 60)",
        },
        "output": (
            "stdout, stderr, exit_code, execution_time_ms, repr, "
            "files_created, session_id"
        ),
    },
    {
        "name": "get_context",
        "endpoint": "GET /datasets/{dataset_id}/context?query=...",
        "description": (
            "Return the Data Context Document as YAML. Pass a natural-language "
            "query to prune the DCD to the columns relevant to that query "
            "(saves tokens). Call this first on every user question."
        ),
        "input": {
            "dataset_id": "str (required)",
            "query": "str (optional)",
        },
        "output": "YAML text of the full or pruned DCD",
    },
    {
        "name": "get_schema",
        "endpoint": "GET /datasets/{dataset_id}/schema",
        "description": (
            "Compact JSON schema summary: columns with roles, descriptions, "
            "synonyms, hierarchies, confidence, classification_reasoning; "
            "plus summary_tables list and verified_queries."
        ),
        "input": {"dataset_id": "str (required)"},
        "output": "SchemaSummary JSON",
    },
    {
        "name": "ask_user",
        "endpoint": "POST /ask_user + POST /ask_user/{id}/wait",
        "description": (
            "Human-in-the-loop clarification. Post a question with optional "
            "options, then long-poll the wait endpoint to block until the user "
            "answers or the timeout fires. Use when the agent hits ambiguity "
            "mid-task and can't safely guess (e.g. 'last month' could mean "
            "calendar month or trailing 30 days)."
        ),
        "input": {
            "session_id": "str",
            "prompt": "str",
            "options": "list[str] (optional)",
            "allow_free_text": "bool (default true)",
            "context": "str (optional)",
        },
        "output": "QuestionResponse with status, answer, timed_out",
    },
    {
        "name": "plan",
        "endpoint": "POST /plans + /submit + /wait + /approve|reject|amend",
        "description": (
            "Propose a structured plan and wait for user approval before "
            "executing. Plan includes: user_question, agent's interpretation, "
            "DCD citations backing the interpretation, concrete tool-call "
            "steps, expected cost, and risks. User can approve, reject with "
            "feedback, or amend specific steps. Use for expensive or "
            "consequential multi-step investigations."
        ),
        "input": {
            "session_id": "str",
            "dataset_id": "str (optional)",
            "user_question": "str",
            "interpretation": "str",
            "citations": "list[{kind, identifier, reason}]",
            "steps": "list[{tool, description, arguments, depends_on}]",
            "expected_cost": "dict[str, int]",
            "risks": "list[str]",
        },
        "output": (
            "Plan object with status machine; wait returns on approve/reject/amend"
        ),
    },
    {
        "name": "tasks",
        "endpoint": "POST /tasks + /tasks/{id}/update + GET /tasks?session_id=",
        "description": (
            "Per-session agent todo list. Create tasks at plan time, mark "
            "in_progress when starting each, completed when done. Supports "
            "depends_on edges for sequential plans. Scoped to a session_id "
            "so a master agent and its subagents each track their own work."
        ),
        "input": {
            "session_id": "str",
            "title": "str",
            "description": "str",
            "depends_on": "list[str]",
        },
        "output": "TaskResponse with id, status, result, timestamps",
    },
    {
        "name": "memory",
        "endpoint": "POST /memory + GET /memory/{scope}/{scope_id}/{key}",
        "description": (
            "Cross-session persistent key-value memory. Scopes: dataset, user, "
            "global, session. Categories: preference, definition, caveat, "
            "fact, note. Survives server restarts (SQLite-backed). Use to "
            "remember user-corrected metric definitions, business-specific "
            "terminology, known data caveats."
        ),
        "input": {
            "scope_type": "dataset | user | global | session",
            "scope_id": "str",
            "key": "str",
            "value": "any JSON",
            "category": "preference | definition | caveat | fact | note",
            "description": "str (optional)",
        },
        "output": "MemoryEntry with timestamps",
    },
    {
        "name": "subagents",
        "endpoint": "POST /subagents/spawn + /complete + /fail",
        "description": (
            "Isolated subagent workspaces for multi-agent analysis. Spawning "
            "creates a new session_id with its own Python kernel, task list, "
            "and memory scope — so a master agent can delegate exploratory "
            "work without polluting its own context window. Completion can "
            "optionally write the subagent's result back to the parent "
            "session's memory for the master to pick up."
        ),
        "input": {
            "parent_session_id": "str (optional)",
            "dataset_id": "str (optional)",
            "task": "str",
            "context_hint": "str (optional)",
        },
        "output": "Subagent with session_id, status, result",
    },
    {
        "name": "clarification",
        "endpoint": "GET /clarification/{dataset_id}",
        "description": (
            "Pending profiling-time clarification questions — questions the "
            "Silver stage emitted about low-confidence column classifications "
            "on this dataset. Answer them via POST /clarification/{id} to "
            "refine the DCD before running expensive analyses."
        ),
        "input": {"dataset_id": "str"},
        "output": "list[ClarificationQuestion]",
    },
    {
        "name": "upload",
        "endpoint": "POST /datasets/upload (single) + /upload-multi (related files)",
        "description": (
            "Upload one or more files to trigger the Bronze → Silver → Gold "
            "pipeline. Multi-file upload detects foreign keys across tables "
            "automatically."
        ),
        "input": {"file": "UploadFile (multi: files: list[UploadFile])"},
        "output": "DatasetSummary with dataset_id, status=gold",
    },
    {
        "name": "connect_database",
        "endpoint": "POST /datasets/connect",
        "description": (
            "Connect to a Postgres / MySQL / SQLite source and pull a table "
            "through the full pipeline. Connection string is used once and "
            "never persisted."
        ),
        "input": {
            "source_type": "postgres | mysql | sqlite",
            "connection_string": "str (secret)",
            "source_table": "str",
            "destination_table": "str",
        },
        "output": "DatasetSummary",
    },
    {
        "name": "edit_context",
        "endpoint": "PUT /datasets/{dataset_id}/context",
        "description": (
            "Apply user corrections to a generated DCD. Edits are validated "
            "against the live DuckDB catalog so you can't reference columns "
            "that don't exist."
        ),
        "input": {
            "dataset_name": "str (optional)",
            "dataset_description": "str (optional)",
            "columns": "list[{name, role, description, aggregation}]",
            "agent_instructions": "list[str] (optional)",
            "known_limitations": "list[str] (optional)",
        },
        "output": "DatasetSummary",
    },
]


@router.get("/tools/list")
def list_tools() -> dict[str, Any]:
    """Return the full agent tool inventory for Layer 2 discovery."""
    return {
        "version": "1.0",
        "tool_count": len(_TOOL_MANIFEST),
        "tools": _TOOL_MANIFEST,
    }
