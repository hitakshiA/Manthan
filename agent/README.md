# `agent/` — the Manthan investigation loop

This directory is the brain. Everything else in Manthan (the FastAPI
in `manthan-api/`, the React surface in `manthan-ui/`, the three
worker processes) exists to deliver cases to this loop and to act on
what it decides. The loop itself is a few hundred lines of Python.
No agent framework. No orchestrator. Just an async generator that
yields typed `Event` objects until the case is resolved.

If you are reading the codebase for the first time, start here.

## The thirty-second mental model

A case arrives. The loop opens it, sends a system prompt + the case
text + the running event log to an LLM, and then dispatches whatever
tool the model wants to call next. The dispatch lives in
`tools.py`. Most tool calls are `coral_sql` (read every connected
source through the Coral MCP server); a few are write-side tools the
loop itself implements (`record_finding`, `amend_brief`,
`conclude`). The result of every call becomes another event in the
log. The next LLM turn sees the whole log. We do this until the
model emits `conclude`, at which point the loop yields a `Brief` and
returns.

Every fact the loop asserts is cited back to a source row. The agent
never holds write credentials. The actual mutations (Stripe refunds,
HubSpot notes, Slack posts, emails) are queued as `DraftedAction`s
in the brief and executed by a separate process after a human (or a
policy rule) approves them.

## The files

| File | What lives there |
|---|---|
| `loop.py` | The async generator. `run_case(trigger, cfg)` yields `Event`s. Reads patterns from Claude Code's loop and OpenAI Agents SDK's typed `NextStep` dispatch. |
| `types.py` | `CaseTrigger`, `Evidence`, `Finding`, `Decision`, `DraftedAction`, `Brief`, `Event`, `NextStep` union. The locked vocabulary. Read this file second. |
| `tools.py` | `ToolExecutor` + every tool the agent can call. Coral tools (`coral_sql`, `coral_list_catalog`, `coral_describe_table`) dispatch through an MCP stdio session; non-Coral tools (`record_finding`, `amend_brief`, `conclude`, `ask_human`, `reply`) are handled inline. |
| `coral_session.py` | The MCP stdio session to the Coral binary. Bound per-run via `set_active_coral_session()` so tool calls dispatch through the live session without threading the handle through every signature. |
| `state.py` | `EventStore` (in-memory append-only log) and the function that converts `Event`s to OpenAI chat messages for the next turn. |
| `pacer.py` | Pre-round and pre-conclude judges. Bounded LLM calls that decide whether the agent has enough to conclude or should run another round. Keeps the loop from spinning. |
| `prompts.py` | `SYSTEM` and `REFLEXION` prompts. Editable as plain text; no templating magic. |
| `llm.py` | Thin wrapper over the OpenAI SDK pointed at OpenRouter. One function: `chat(cfg, messages, temperature, tools)`. |
| `config.py` | `Config` dataclass plus `load()` from environment. Read once at process start. |

## How a case actually runs

```text
investigate worker (manthan-api/workers/investigate.py)
       │
       │  picks up a `cases` row from a PG LISTEN/NOTIFY signal
       ▼
   builds a CaseTrigger
       │
       │  async for evt in run_case(trigger, cfg):
       ▼                       │
   ┌───────────────┐            │
   │   agent loop  │   yields:  │
   │   (loop.py)   │   case_opened
   │               │   tool_call
   │   each turn:  │   tool_result
   │   1. judge    │   finding_recorded
   │      pre-round│   reflexion
   │   2. LLM call │   decision_recorded
   │   3. dispatch │   draft_action_added
   │      tools    │   brief_drafted     ← terminal
   │   4. append   │   case_closed
   │      events   │
   │   5. reflexion│
   │      every 3  │
   │      turns    │
   └───────────────┘
       │
   investigate worker
       │
       │  persists each event to PG events table,
       │  projects findings → findings table,
       │  projects drafted_actions → actions table
       ▼
   actor worker  (after human or policy approval)
       │
       │  drains the actions queue, calls Stripe / Resend /
       │  HubSpot / Slack adapters, marks each succeeded/failed.
       ▼
   case status → resolved
```

The agent itself does not know any of the persistence happened. It
only sees the event log it is yielding into.

## Why no framework

We tried LangGraph and the OpenAI Agents SDK early. Both forced us
to learn their state model before we could express the things we
actually wanted: a typed event log as the single source of truth,
deterministic dispatch by tool name, a pacer LLM that judges the
agent loop from the outside, and zero hidden retries. The whole
loop fits in one file you can read top-to-bottom in ten minutes.
That trade is worth it.

The patterns we *did* steal verbatim are called out in `loop.py`'s
docstring: Claude Code's async-generator signature, OpenAI Agents
SDK's typed `NextStep` union for terminal vs. non-terminal turns,
and 12-Factor Agents items #3 (own your context window) and #8 (own
your control flow).

## Tool surface (what the LLM can actually call)

Read tools (parallel-safe, dispatched through Coral MCP):

- `coral_list_catalog` — list every connected source + their tables.
- `coral_describe_table` — column types for one qualified table.
- `coral_sql` — execute a SELECT across any connected source.

Write tools (handled inside the loop, no external side effects):

- `record_finding(text, citations[idx], confidence)` — assert a
  cited claim. Joins the running findings list. The brief is built
  from these.
- `amend_brief(reason, decision_*?, regenerate_actions?)` — used by
  the chat-followup phase to revise a drafted brief after new
  evidence.
- `ask_human(question, recommendation, options[], confidence)` —
  terminates the loop with a `NextStepInterruption`. The case sits
  in `awaiting_approval` until a human responds.
- `conclude(tldr, decision, drafted_actions[])` — terminates the
  loop with a `NextStepFinalOutput`. The brief is yielded as
  `brief_drafted` and the worker drains drafted_actions into the
  PG actions table.

## Running it standalone

The agent runs inside the `manthan-investigate` worker in
production, but you can drive it from a script for debugging.

```bash
cd agent
uv venv && uv pip install -e .

# Point at OpenRouter + the Coral binary.
cp .env.example .env
$EDITOR .env   # set OPENROUTER_API_KEY; CORAL_BINARY defaults to `coral` on PATH

# Run a single case end-to-end against a local Coral.
uv run python -m manthan_agent.smoke aperture
```

The smoke script lives in `scripts/`. There are also `seed_*.py`
scripts in `scripts/` that populate the Coral test database with
the customers, charges, disputes, and CRM records that the demo
scenarios reference. Run them once after standing up a fresh
Coral instance.

## What's NOT in this directory

- **The actor that fires actions.** That lives in
  `manthan-api/workers/actor.py`. The agent never holds write
  credentials.
- **The HTTP surface.** That lives in `manthan-api/`. The agent
  doesn't speak HTTP at all; it speaks events.
- **Per-tenant config.** The agent only knows about the case it was
  handed. Org resolution, member auth, and policy matching all
  happen upstream.
- **Coral itself.** Coral is a separate Rust binary the agent talks
  to over MCP stdio. The agent has no idea what's behind that
  socket — could be the production Coral pointed at fifteen real
  sources, could be a local Coral pointed at a SQLite test database.

## Editing notes

- Adding a tool: define the args as a Pydantic model in `tools.py`,
  add a dispatch arm in the executor, and append the
  `openai_schema` entry. The loop picks it up on the next round.
  No registration step.
- Changing the system prompt: edit `prompts.py`. There is no
  templating. The trigger text is appended verbatim by `loop.py`.
- Changing the model: `MANTHAN_MODEL=...` in the env. Default is
  `deepseek/deepseek-v4-pro:exacto` (cheap, smart enough). Any
  OpenRouter model with function-calling support works.
- Changing the budget: `Budget` in `loop.py`. Max prompt tokens,
  max steps, max wall-clock.

## Reading order if you have ten minutes

1. `types.py` — the vocabulary.
2. `loop.py` — the main generator. Read top to bottom.
3. `tools.py` — what the LLM can call.
4. `prompts.py` — what the LLM is told to do.

Skip `pacer.py`, `state.py`, `llm.py`, `coral_session.py`,
`config.py` until you need them. They are mechanical.
