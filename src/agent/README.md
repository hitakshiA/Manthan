# agent/ — Layer 2: Autonomous Agent Harness

The agent is a single `while` loop that calls an AI model, executes tool calls, observes results, and iterates until the model produces a final text response.

## Architecture

```
ManthanAgent.run_stream()
  Phase 0: session_start event
  Phase 1: Auto-discover tables (SHOW TABLES → inject into prompt)
  Phase 2: Assemble system prompt (base + schema + tables + memory)
  Phase 3: Check cross-session memory
  Phase 4: While loop
    → Call model with messages + TOOL_DEFINITIONS
    → If tool_calls: execute each, emit SSE events
    → If no tool_calls: load render_spec, emit done event, return
```

## Files

| File | What it does |
|------|-------------|
| `loop.py` | `ManthanAgent` class — the agent while-loop with SSE streaming |
| `tools.py` | 8 tool definitions (OpenAI function format) + `ToolRouter` dispatcher |
| `prompt.py` | System prompt assembly: 3 decision gates, chart rules, tool patterns |
| `events.py` | 22 SSE event types: lifecycle, discovery, thinking, tools, HITL, plans |
| `config.py` | Agent-specific settings (model, max_turns, temperature, timeout) |

## Decision gates (from prompt.py)

1. **Clarification** — If 2+ interpretations exist → `ask_user` with options, blocks until answered
2. **Planning** — If 3+ tool calls needed → `create_plan` with steps/citations, waits for approval
3. **Complexity** — Decides output mode early: Simple (KPI + chart) / Moderate (dashboard) / Complex (report)

## Tools

| Tool | Timeout | Behavior |
|------|---------|----------|
| `get_schema` | — | Reads semantic layer (columns, roles, verified queries) |
| `get_context` | — | Full DCD as YAML, optionally query-pruned |
| `run_sql` | 30s | Read-only SQL, supports temp tables and DESCRIBE |
| `run_python` | 60s | Stateful sandbox — variables persist across calls |
| `ask_user` | 30s | Blocks for user input; auto-proceeds on timeout |
| `create_plan` | 30s | Approval gate; auto-approves on timeout |
| `save_memory` | — | Persists to SQLite (scope: dataset/user/global/session) |
| `recall_memory` | — | Searches prior conclusions by query |
