"""Chat→re-investigate loop.

When the operator follows up on a case in chat ("go check X again", "what
about Y?", "I disagree, refund full amount"), the agent that wrote the
brief picks up the same thread with the same tool surface and can:

  1. Run additional Coral SQL against the same source mesh.
  2. Record new findings that join the original ones.
  3. Amend the brief's decision (action / amount / rationale / confidence)
     and regenerate drafted actions when the decision changes.
  4. Reply directly to the operator - terminal step.

It's the same ReAct/Reflexion loop as the initial investigation, just
with `amend_brief` + `reply` instead of `conclude` + `ask_human`. The
operator is talking to the agent that produced the brief, not a generic
chatbot - full case context + Coral access + write authority.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from uuid import UUID

from manthan_agent import config as agent_config
from manthan_agent.coral_session import (
    clear_active_coral_session,
    coral_mcp_session,
    set_active_coral_session,
)
from manthan_agent.llm import chat as llm_chat
from manthan_agent.tools import (
    CoralSqlArgs,
    CoralListCatalogArgs,
    CoralDescribeTableArgs,
    RecordFindingArgs,
    ToolExecutor,
    _enforce_strict,
)
from manthan_agent.types import ToolCall

from manthan_api.config import get_settings
from manthan_api.db import get_pool

logger = logging.getLogger("worker.chat")


# ──────────────────────────────────────────────────────────────────────
# Chat tool schema (subset of agent tools + chat-specific tools).
# We hand-build the OpenAI shape rather than reusing `openai_schema()`
# from the agent because the chat path needs different terminals.
# ──────────────────────────────────────────────────────────────────────


def _strict_schema(args_model: type) -> dict[str, Any]:
    """Render a Pydantic model as an OpenAI strict-mode JSON Schema."""
    schema = args_model.model_json_schema()
    _enforce_strict(schema)
    return schema


def chat_tools_schema() -> list[dict[str, Any]]:
    """Tools available to the chat agent in a single response.

    Read tools (coral_*) run in parallel. Write tools (record_finding,
    amend_brief, reply) run serially. `reply` is terminal - calling it
    ends the loop and posts the text as an agent_reply event.
    """
    tools: list[dict[str, Any]] = []

    tools.append({
        "type": "function",
        "function": {
            "name": "coral_sql",
            "description": (
                "Execute SQL against the company's connected data sources "
                "(Stripe, HubSpot, Salesforce, Intercom, Zendesk, Slack, "
                "Notion, etc.) through Coral. Use this to re-check facts, "
                "pull updated state, or investigate something the original "
                "brief didn't cover."
            ),
            "parameters": _strict_schema(CoralSqlArgs),
            "strict": True,
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "coral_list_catalog",
            "description": "List schemas/tables visible to Coral. Use when you don't know which source has the data.",
            "parameters": _strict_schema(CoralListCatalogArgs),
            "strict": True,
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "coral_describe_table",
            "description": "Show columns for a specific Coral table.",
            "parameters": _strict_schema(CoralDescribeTableArgs),
            "strict": True,
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "record_finding",
            "description": (
                "Add a new finding to the case. Use when your follow-up "
                "investigation surfaces a fact the original brief missed. "
                "Findings join the existing ones in the case record."
            ),
            "parameters": _strict_schema(RecordFindingArgs),
            "strict": True,
        },
    })

    amend_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why you're amending (1-2 sentences for audit trail).",
            },
            "decision_action": {
                "type": ["string", "null"],
                "enum": ["fight", "refund", "accept", "escalate", None],
                "description": "New action, or null to leave unchanged.",
            },
            "decision_amount_minor": {
                "type": ["integer", "null"],
                "description": "New amount in minor units (cents), or null to leave unchanged.",
            },
            "decision_rationale": {
                "type": ["string", "null"],
                "description": "Updated rationale, or null to leave unchanged.",
            },
            "decision_confidence": {
                "type": ["number", "null"],
                "description": "Updated confidence 0-1, or null to leave unchanged.",
            },
            "regenerate_actions": {
                "type": "boolean",
                "description": "If true, throw away drafted actions and regenerate from the new decision.",
            },
        },
        "required": [
            "reason", "decision_action", "decision_amount_minor",
            "decision_rationale", "decision_confidence", "regenerate_actions",
        ],
    }
    tools.append({
        "type": "function",
        "function": {
            "name": "amend_brief",
            "description": (
                "Update the case decision after follow-up investigation. "
                "Use when the operator's feedback or new evidence changes "
                "the action, amount, rationale, or confidence. Regenerates "
                "drafted actions if you set regenerate_actions=true."
            ),
            "parameters": amend_schema,
            "strict": True,
        },
    })

    reply_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "text": {
                "type": "string",
                "description": (
                    "Your reply to the operator. 2-6 sentences. Reference "
                    "finding numbers like [1] when citing evidence. If you "
                    "amended the brief, summarize what changed and why."
                ),
            },
        },
        "required": ["text"],
    }
    tools.append({
        "type": "function",
        "function": {
            "name": "reply",
            "description": (
                "End the follow-up by sending your reply to the operator. "
                "Always call this last. Without it the operator sees nothing."
            ),
            "parameters": reply_schema,
            "strict": True,
        },
    })

    return tools


CHAT_SYSTEM_PROMPT = """\
You are Manthan, a billing-ops investigator. You already drafted a case brief earlier in this thread. The operator (a Director of Revenue Accounting or similar) is following up - pushing back on the decision, asking you to re-check a specific source, or requesting a change to the action.

You are NOT a chatbot. You are the same agent that wrote the brief, with the same tools (Coral SQL access across Stripe/HubSpot/Salesforce/Intercom/Zendesk/Slack/Notion/etc.). When the operator asks you to verify something, USE THE TOOLS - don't just claim you can't or guess from memory.

How to handle a follow-up:

1. Re-read the case context (trigger, findings, decision) carried in the user message.
2. If the operator asks "are you sure?", "double-check X", or "look at Y" - actually call coral_sql to re-verify. Don't say "I already checked" without re-running the query.
3. If new evidence changes your answer, call record_finding to capture it, then call amend_brief with the updated decision.
4. If the operator disagrees but provides no new evidence, defend your call with the specific findings (cite them as [1], [2]) - don't fold without reason.
5. Always end your turn by calling `reply` with 2-6 sentences for the operator.

Use forbidden engineering vocabulary sparingly when explaining to the operator - they understand customers, charges, refunds, support tickets, not schemas/tables/queries.

Budget: do at most 4 tool round-trips before replying. If you can answer from existing findings, reply directly.
"""


# ──────────────────────────────────────────────────────────────────────
# The chat loop
# ──────────────────────────────────────────────────────────────────────


MAX_CHAT_ROUNDS = 6


async def run_chat_followup(
    org_id: UUID,
    thread_id: UUID,
    case_id: UUID,
    user_message: str,
    append_event: Any,  # callable(org_id, thread_id, type_, actor, data) -> coroutine
    append_finding: Any,  # callable(org_id, case_id, text, confidence, citations) -> coroutine
    synthesize_actions: Any,  # callable(org_id, thread_id, case_id, decision_action, amount_minor) -> coroutine
) -> None:
    """Run the toolful follow-up loop.

    Reuses the agent's Coral session + ToolExecutor for read tools.
    Handles record_finding/amend_brief/reply itself (those are chat-mode
    terminals, not part of the main agent's vocabulary).
    """
    log = logger.getChild(str(thread_id)[:8] + ".chat")

    cfg = agent_config.load()

    # Pull case context for the system prompt.
    context_block = await _build_context_block(org_id, thread_id, case_id)
    chat_history = await _build_chat_history(org_id, thread_id)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": context_block},
        *chat_history,
        {"role": "user", "content": user_message},
    ]

    tools_schema = chat_tools_schema()

    coral_binary = get_settings().coral_binary
    executor = ToolExecutor()

    rounds = 0
    replied = False

    try:
        async with coral_mcp_session(coral_binary) as session:
            token = set_active_coral_session(session)
            try:
                while rounds < MAX_CHAT_ROUNDS and not replied:
                    rounds += 1
                    t0 = time.monotonic()
                    try:
                        response = llm_chat(
                            cfg,
                            messages,
                            tools=tools_schema,
                            temperature=0.2,
                        )
                    except Exception as e:  # noqa: BLE001
                        log.exception("chat LLM call failed: %s", e)
                        await append_event(
                            org_id, thread_id, "error", "system",
                            {"reason": "chat_llm_failed", "detail": f"{type(e).__name__}: {e}"},
                        )
                        await append_event(
                            org_id, thread_id, "agent_reply", "agent",
                            {
                                "text": "I hit an internal error trying to think through that. "
                                        "Try rephrasing, or check the activity log for details.",
                                "in_reply_to": "human_followup",
                            },
                        )
                        return
                    elapsed_ms = int((time.monotonic() - t0) * 1000)

                    msg = response.choices[0].message

                    # Free-form text without tool_calls: treat as the reply
                    # (gentle fallback for models that forget to call reply).
                    if msg.content and not msg.tool_calls:
                        await append_event(
                            org_id, thread_id, "agent_reply", "agent",
                            {
                                "text": msg.content,
                                "in_reply_to": "human_followup",
                                "elapsed_ms": elapsed_ms,
                            },
                        )
                        replied = True
                        break

                    if not msg.tool_calls:
                        log.warning("chat round %d: no content + no tool_calls", rounds)
                        continue

                    # Append the assistant message (with tool_calls) to history
                    # so the next round sees the right context.
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                            if tc.function is not None
                        ],
                    })

                    # Parse + dispatch.
                    parsed_calls: list[ToolCall] = []
                    for tc in msg.tool_calls:
                        if tc is None or tc.function is None:
                            continue
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                        parsed_calls.append(ToolCall(
                            id=tc.id or f"missing-{len(parsed_calls)}",
                            name=tc.function.name or "_unknown",
                            arguments=args,
                        ))

                    # Emit tool_call events for visibility in the trace.
                    for tc in parsed_calls:
                        await append_event(
                            org_id, thread_id, "tool_call", "agent",
                            {"id": tc.id, "name": tc.name, "arguments": tc.arguments,
                             "phase": "chat_followup"},
                        )

                    # Handle each tool call.
                    for tc in parsed_calls:
                        result_payload: dict[str, Any]

                        if tc.name in ("coral_sql", "coral_list_catalog", "coral_describe_table"):
                            # Dispatch through the agent's executor (uses real Coral).
                            results = await executor.dispatch([tc])
                            tr = results[0] if results else None
                            if tr is None:
                                result_payload = {"status": "error", "error": "no result"}
                            else:
                                result_payload = tr.model_dump(mode="json", exclude={"evidence"})

                            await append_event(
                                org_id, thread_id, "tool_result", "system",
                                {
                                    "tool_call_id": tc.id,
                                    "result": result_payload,
                                    "evidence_added": len(tr.evidence) if tr else 0,
                                    "phase": "chat_followup",
                                },
                            )

                        elif tc.name == "record_finding":
                            args = tc.arguments or {}
                            text = str(args.get("text") or "")
                            citations = args.get("citations") or []
                            try:
                                conf = float(args.get("confidence", 0.5))
                            except (TypeError, ValueError):
                                conf = 0.5
                            # citations are indices into the executor's evidence;
                            # we don't have a fresh evidence list shared between
                            # chat and initial run, so we just record citations
                            # as opaque ints and let the UI handle.
                            await append_finding(
                                org_id, case_id, text, conf,
                                [
                                    {
                                        "source": "chat_followup",
                                        "table": "",
                                        "ref": f"evidence#{c}",
                                        "field": None,
                                    }
                                    for c in citations
                                    if isinstance(c, int)
                                ],
                            )
                            await append_event(
                                org_id, thread_id, "finding_recorded", "agent",
                                {
                                    "text": text,
                                    "citations": citations,
                                    "confidence": conf,
                                    "phase": "chat_followup",
                                },
                            )
                            result_payload = {"recorded": True, "text": text}

                        elif tc.name == "amend_brief":
                            args = tc.arguments or {}
                            patch = {
                                k: args.get(k)
                                for k in (
                                    "decision_action", "decision_amount_minor",
                                    "decision_rationale", "decision_confidence",
                                )
                                if args.get(k) is not None
                            }
                            regenerate = bool(args.get("regenerate_actions"))
                            await _apply_amend(
                                org_id, case_id, patch,
                                regenerate=regenerate,
                                thread_id=thread_id,
                                synthesize_actions=synthesize_actions,
                            )
                            await append_event(
                                org_id, thread_id, "brief_amended", "agent",
                                {
                                    "reason": args.get("reason", ""),
                                    "patch": patch,
                                    "regenerated_actions": regenerate,
                                    "phase": "chat_followup",
                                },
                            )
                            result_payload = {
                                "amended": True,
                                "fields_changed": list(patch.keys()),
                                "regenerated_actions": regenerate,
                            }

                        elif tc.name == "reply":
                            text = str((tc.arguments or {}).get("text") or "")
                            await append_event(
                                org_id, thread_id, "agent_reply", "agent",
                                {
                                    "text": text,
                                    "in_reply_to": "human_followup",
                                    "rounds": rounds,
                                    "elapsed_ms": elapsed_ms,
                                },
                            )
                            # Mirror to Slack thread if case was opened there.
                            try:
                                from manthan_api.services.slack_notifier import maybe_notify
                                await maybe_notify(
                                    org_id=org_id,
                                    thread_id=thread_id,
                                    case_id=case_id,
                                    event_type="agent_reply",
                                    event_data={"text": text},
                                )
                            except Exception:  # noqa: BLE001
                                pass
                            result_payload = {"sent": True}
                            replied = True

                        else:
                            result_payload = {"status": "error", "error": f"unknown tool {tc.name}"}

                        # Feed result back into the message history so the
                        # model sees it on the next round.
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result_payload, default=str)[:8000],
                        })

                if not replied:
                    # Out of rounds - synth a fallback so the operator isn't
                    # left hanging.
                    log.warning("chat hit MAX_CHAT_ROUNDS without reply - emitting fallback")
                    await append_event(
                        org_id, thread_id, "agent_reply", "agent",
                        {
                            "text": (
                                "I dug into this but couldn't wrap up cleanly. "
                                "Check the activity log above for what I found. "
                                "Want me to take another angle?"
                            ),
                            "in_reply_to": "human_followup",
                            "fallback": True,
                        },
                    )
            finally:
                clear_active_coral_session(token)
    except Exception as e:  # noqa: BLE001
        log.exception("chat loop crashed: %s", e)
        await append_event(
            org_id, thread_id, "error", "system",
            {"reason": "chat_loop_crashed", "detail": f"{type(e).__name__}: {e}"},
        )
        await append_event(
            org_id, thread_id, "agent_reply", "agent",
            {
                "text": "Something broke on my side mid-investigation. Try again, "
                        "or rephrase the question - and check the activity log.",
                "in_reply_to": "human_followup",
                "fallback": True,
            },
        )


# ──────────────────────────────────────────────────────────────────────
# Helpers (context, history, apply)
# ──────────────────────────────────────────────────────────────────────


async def _build_context_block(
    org_id: UUID,
    thread_id: UUID,
    case_id: UUID,
) -> str:
    """Pack the case state (trigger, findings, decision) into a single
    user message that primes the chat agent before history."""
    async with get_pool().acquire() as conn:
        case_row = await conn.fetchrow(
            """
            SELECT short_id, customer_ref, amount_minor, currency,
                   decision_action, decision_amount_minor, decision_confidence
            FROM cases WHERE id=$1
            """,
            case_id,
        )
        opened = await conn.fetchrow(
            """
            SELECT data FROM events
            WHERE org_id=$1 AND thread_id=$2 AND type='case_opened'
            ORDER BY seq ASC LIMIT 1
            """,
            org_id, thread_id,
        )
        findings = await conn.fetch(
            """
            SELECT seq, text, confidence FROM findings
            WHERE org_id=$1 AND case_id=$2 ORDER BY seq ASC
            """,
            org_id, case_id,
        )
        brief_row = await conn.fetchrow(
            """
            SELECT data FROM events
            WHERE org_id=$1 AND thread_id=$2 AND type='brief_drafted'
            ORDER BY seq DESC LIMIT 1
            """,
            org_id, thread_id,
        )
        actions = await conn.fetch(
            """
            SELECT type, status, payload FROM actions
            WHERE org_id=$1 AND case_id=$2 ORDER BY seq ASC
            """,
            org_id, case_id,
        )

    short_id = case_row["short_id"] if case_row else "?"
    customer = (case_row["customer_ref"] if case_row else None) or "(unknown)"
    amount = case_row["amount_minor"] if case_row else None
    currency = (case_row["currency"] if case_row else "usd") or "usd"
    decision_action = case_row["decision_action"] if case_row else None
    decision_amount = case_row["decision_amount_minor"] if case_row else None
    decision_conf = case_row["decision_confidence"] if case_row else None

    opened_data = (opened["data"] if isinstance(opened["data"], dict) else json.loads(opened["data"])) if opened else {}
    trigger_text = str(opened_data.get("trigger_text", ""))

    findings_block = "\n".join(
        f"[{r['seq']}] (conf {(r['confidence'] or 0):.2f}) {r['text']}"
        for r in findings
    ) or "(no findings recorded)"

    brief_block = ""
    if brief_row:
        bdata = brief_row["data"] if isinstance(brief_row["data"], dict) else json.loads(brief_row["data"])
        brief_block = (bdata.get("tldr") or "")[:600]

    actions_block = "\n".join(
        f"- {r['type']} ({r['status']}): {json.dumps(r['payload'], default=str)[:160]}"
        for r in actions
    ) or "(no actions drafted)"

    return f"""\
=== CASE CONTEXT (do not respond - this is your memory) ===

Case: {short_id}  Customer: {customer}  Amount: ${(amount or 0) / 100:,.2f} {currency.upper()}

TRIGGER:
{trigger_text[:1500]}

FINDINGS:
{findings_block}

DRAFTED BRIEF TL;DR:
{brief_block}

CURRENT DECISION: {decision_action} for ${(decision_amount or 0) / 100:,.2f} (conf {decision_conf})

DRAFTED ACTIONS:
{actions_block}

=== END CONTEXT ===

The operator's question follows. Use coral_sql to re-verify if asked. End with reply().
"""


async def _build_chat_history(org_id: UUID, thread_id: UUID) -> list[dict[str, Any]]:
    """Recent chat turns (human_followup ↔ agent_reply pairs) - limited to last 6 for context."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT type, data FROM events
            WHERE org_id=$1 AND thread_id=$2
              AND type IN ('human_followup', 'agent_reply')
            ORDER BY seq ASC
            """,
            org_id, thread_id,
        )
    # Exclude the very last human_followup - it's the message we're about
    # to act on, passed separately.
    if rows and rows[-1]["type"] == "human_followup":
        rows = rows[:-1]
    # Cap to last 6 turns.
    rows = rows[-6:]
    msgs: list[dict[str, Any]] = []
    for r in rows:
        data = r["data"] if isinstance(r["data"], dict) else {}
        if r["type"] == "human_followup":
            msgs.append({"role": "user", "content": str(data.get("message", ""))})
        elif r["type"] == "agent_reply":
            msgs.append({"role": "assistant", "content": str(data.get("text", ""))})
    return msgs


async def _apply_amend(
    org_id: UUID,
    case_id: UUID,
    patch: dict[str, Any],
    *,
    regenerate: bool,
    thread_id: UUID,
    synthesize_actions: Any,
) -> None:
    """Apply a decision patch to the case row + optionally regenerate actions."""
    if not patch and not regenerate:
        return

    sets: list[str] = []
    params: list[Any] = []
    for col, val in patch.items():
        if col == "decision_action":
            sets.append(f"decision_action = ${len(params) + 1}")
            params.append(val)
        elif col == "decision_amount_minor":
            sets.append(f"decision_amount_minor = ${len(params) + 1}")
            params.append(val)
        elif col == "decision_confidence":
            sets.append(f"decision_confidence = ${len(params) + 1}")
            params.append(val)
        # decision_rationale lives in events, not cases - UI reads brief

    if sets:
        params.append(case_id)
        async with get_pool().acquire() as conn:
            await conn.execute(
                f"UPDATE cases SET {', '.join(sets)} WHERE id = ${len(params)}",
                *params,
            )

    if regenerate:
        # Pull latest decision so we synthesize from the updated state.
        async with get_pool().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT decision_action, decision_amount_minor FROM cases WHERE id=$1",
                case_id,
            )
        if row is None:
            return
        # Wipe drafted actions (preserve approved/executed - those are
        # historic). New synth happens below.
        async with get_pool().acquire() as conn:
            await conn.execute(
                "DELETE FROM actions WHERE case_id=$1 AND status='drafted'",
                case_id,
            )

        from manthan_api.workers.actor import make_idempotency_key

        new_actions = await synthesize_actions(
            org_id, thread_id, case_id,
            row["decision_action"], row["decision_amount_minor"],
        )
        for i, da in enumerate(new_actions or []):
            if not isinstance(da, dict):
                continue
            kind = da.get("kind")
            payload = da.get("payload") or {}
            if not kind:
                continue
            idem = make_idempotency_key(case_id, kind, payload)
            async with get_pool().acquire() as conn:
                try:
                    await conn.execute(
                        """
                        INSERT INTO actions (
                            org_id, case_id, seq, type, payload,
                            idempotency_key, status
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, 'drafted')
                        ON CONFLICT (org_id, idempotency_key) DO NOTHING
                        """,
                        org_id, case_id, i + 1, kind, payload, idem,
                    )
                except Exception:  # noqa: BLE001
                    pass
