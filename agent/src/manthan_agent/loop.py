"""The async-generator main loop.

Reference patterns adopted verbatim:
  - Claude Code's async-generator loop signature
  - OpenAI Agents SDK's typed NextStep dispatch
  - 12-Factor Agents #3 (own your context window) + #8 (own your control flow)

The loop yields Event objects as they happen. Caller iterates with
`async for event in run(case_id)`. Termination is a typed Terminal
value returned from the generator (via StopAsyncIteration.value).

Step 1 scope: investigate-then-conclude. No Postgres yet (in-memory
EventStore). No real Coral yet (mock tool handlers). The architecture
is complete; the integrations swap in steps 2 and 3.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime

from .config import Config
from .llm import chat
from .prompts import REFLEXION, SYSTEM
from .state import EventStore, events_to_messages
from .tools import ToolExecutor, openai_schema, tool_by_name
from .types import (
    Brief,
    CaseTrigger,
    Decision,
    DraftedAction,
    Event,
    Finding,
    ToolCall,
)

# DraftedAction is imported because Brief.drafted_actions uses it; the
# linter sees it as unused inside loop.py itself. Keep the import.
_ = DraftedAction

# ──────────────────────────────────────────────────────────────────────
# Budget + termination
# ──────────────────────────────────────────────────────────────────────


@dataclass
class Budget:
    """Telemetry only - caps removed at user request.

    The agent self-terminates on confidence or saturation. Steps and
    USD are tracked for visibility but never trigger termination.
    Re-introduce caps before any unattended production deploy.
    """

    steps: int = 0
    usd_spent: float = 0.0

    def charge(self, prompt_tokens: int, completion_tokens: int) -> None:
        # DeepSeek V4 Pro on OpenRouter: ~$1.50/MTok input, $3.00/MTok output
        # (use conservative numbers; refine when we have live billing data).
        self.usd_spent += prompt_tokens * 1.5e-6 + completion_tokens * 3.0e-6
        self.steps += 1

    def exhausted(self) -> bool:
        # Caps disabled. Agent runs until it concludes, asks for human,
        # or hits an unrecoverable error.
        return False


@dataclass
class Terminal:
    reason: str  # "concluded" | "ask_human" | "budget" | "error"
    brief: Brief | None = None
    question: str | None = None
    detail: str | None = None


# ──────────────────────────────────────────────────────────────────────
# The main loop
# ──────────────────────────────────────────────────────────────────────


async def run_case(
    trigger: CaseTrigger,
    cfg: Config,
    store: EventStore | None = None,
    *,
    budget: Budget | None = None,
) -> AsyncGenerator[Event, Terminal]:
    """Investigate a case. Yields Event as it happens. Returns Terminal.

    Caller pattern:
        async for event in run_case(trigger, cfg):
            print(event.kind, event.data)
    """
    store = store or EventStore()
    budget = budget or Budget()
    executor = ToolExecutor()

    # Findings accumulate via record_finding tool calls.
    # Drafted actions are emitted only at conclude() time, packed inside
    # the Brief - they don't accumulate during the loop.
    findings: list[Finding] = []

    # Open the case
    yield store.append(
        trigger.case_id,
        kind="case_opened",
        actor="system",
        data={
            "case_id": trigger.case_id,
            "text": trigger.text,
            "structured": trigger.structured,
            "source_surface": trigger.source_surface,
        },
    )

    tools_schema = openai_schema()

    # The ReAct + Reflexion inner loop
    while True:
        if budget.exhausted():
            yield store.append(
                trigger.case_id,
                kind="error",
                actor="system",
                data={
                    "reason": "budget_exhausted",
                    "steps": budget.steps,
                    "usd_spent": round(budget.usd_spent, 4),
                },
            )
            yield store.append(
                trigger.case_id,
                kind="case_closed",
                actor="system",
                data={"reason": "budget", "detail": "safety rail hit"},
            )
            return

        # 1. Compose messages from the event log
        messages = [{"role": "system", "content": SYSTEM}]
        messages.extend(events_to_messages(store.list_for_case(trigger.case_id)))

        # 2. Call the LLM
        t0 = time.monotonic()
        try:
            response = chat(
                cfg,
                messages,
                tools=tools_schema,
                temperature=0.2,
            )
        except Exception as exc:
            yield store.append(
                trigger.case_id,
                kind="error",
                actor="system",
                data={"reason": "llm_call_failed", "detail": f"{type(exc).__name__}: {exc}"},
            )
            yield store.append(
                trigger.case_id,
                kind="case_closed",
                actor="system",
                data={"reason": "error", "detail": f"{type(exc).__name__}: {exc}"},
            )
            return
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        usage = getattr(response, "usage", None)
        if usage is not None:
            budget.charge(usage.prompt_tokens, usage.completion_tokens)

        msg = response.choices[0].message

        # 3a. The model emitted free-form thought (no tool calls).
        if msg.content and not msg.tool_calls:
            yield store.append(
                trigger.case_id,
                kind="agent_thought",
                actor="agent",
                data={"text": msg.content, "elapsed_ms": elapsed_ms},
            )
            # No tool calls means the model didn't pick conclude/ask_human.
            # We force it to wrap up next turn by injecting a nudge.
            store.append(
                trigger.case_id,
                kind="agent_thought",
                actor="system",
                data={
                    "text": (
                        "[orchestrator nudge] You did not emit a tool call. "
                        "Either call coral_sql to gather more evidence, "
                        "record_finding to assert a claim, ask_human, or "
                        "conclude."
                    )
                },
            )
            continue

        # 3b. The model emitted tool calls. Parse + dispatch.
        if not msg.tool_calls:
            yield store.append(
                trigger.case_id,
                kind="error",
                actor="system",
                data={
                    "reason": "empty_response",
                    "finish_reason": response.choices[0].finish_reason,
                },
            )
            yield store.append(
                trigger.case_id,
                kind="case_closed",
                actor="system",
                data={"reason": "error", "detail": "empty response from model"},
            )
            return

        # Defensive parse of tool_calls. Some models (observed in
        # MiniMax) return a list with None entries or missing function
        # objects. We skip those rather than crash.
        tool_calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            if tc is None or tc.function is None:
                continue
            try:
                args_dict = json.loads(tc.function.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                args_dict = {}
            tool_calls.append(
                ToolCall(
                    id=tc.id or f"missing-{len(tool_calls)}",
                    name=tc.function.name or "_unknown",
                    arguments=args_dict,
                )
            )

        # If the model returned tool_calls metadata but every entry was
        # malformed, treat as an empty response.
        if not tool_calls:
            yield store.append(
                trigger.case_id,
                kind="error",
                actor="system",
                data={
                    "reason": "all_tool_calls_malformed",
                    "raw_count": len(msg.tool_calls or []),
                },
            )
            yield store.append(
                trigger.case_id,
                kind="case_closed",
                actor="system",
                data={"reason": "error", "detail": "all tool_calls malformed"},
            )
            return

        # Log each tool call as an event before dispatch
        for tc in tool_calls:
            yield store.append(
                trigger.case_id,
                kind="tool_call",
                actor="agent",
                data={"id": tc.id, "name": tc.name, "arguments": tc.arguments},
            )

        # Check for terminal tools (ask_human / conclude) FIRST. These
        # don't go through the executor - the loop handles them directly.
        for tc in tool_calls:
            tool = tool_by_name(tc.name)
            if tool is None:
                continue

            if tc.name == "ask_human":
                args = tc.arguments
                yield store.append(
                    trigger.case_id,
                    kind="hitl_pause",
                    actor="agent",
                    data={
                        "reason": "ask_human",
                        "question": args.get("question", ""),
                        "recommendation": args.get("recommendation", ""),
                        "confidence": args.get("confidence"),
                        "options": args.get("options", []),
                    },
                )
                yield store.append(
                    trigger.case_id,
                    kind="case_closed",
                    actor="system",
                    data={
                        "reason": "ask_human",
                        "question": args.get("question", ""),
                    },
                )
                return

            if tc.name == "conclude":
                args = tc.arguments

                # Defensive: clamp decision fields. Some models (observed
                # in DeepSeek + Xiaomi MiMo) emit invalid action strings
                # or out-of-range confidences. We coerce rather than raise.
                raw_action = args.get("decision_action", "escalate")
                if not (
                    isinstance(raw_action, str)
                    and raw_action in ("fight", "refund", "accept", "escalate")
                ):
                    raw_action = "escalate"
                try:
                    confidence = max(0.0, min(1.0, float(args.get("decision_confidence", 0.5))))
                except (TypeError, ValueError):
                    confidence = 0.5

                # Defensive: skip malformed drafted_actions instead of
                # crashing the whole brief on a missing kind/payload.
                raw_actions = args.get("drafted_actions", []) or []
                safe_actions: list[DraftedAction] = []
                dropped_actions = 0
                dropped_details: list[dict[str, Any]] = []
                for raw in raw_actions:
                    if not isinstance(raw, dict):
                        dropped_actions += 1
                        dropped_details.append({
                            "reason": "not_a_dict",
                            "raw_type": type(raw).__name__,
                        })
                        continue
                    try:
                        safe_actions.append(DraftedAction(**raw))
                    except Exception as e:  # noqa: BLE001
                        dropped_actions += 1
                        dropped_details.append({
                            "reason": "validation_failed",
                            "kind": raw.get("kind"),
                            "description": raw.get("description"),
                            "error": f"{type(e).__name__}: {e}",
                        })

                # Surface dropped actions as a warning event so the
                # operator (and any retry logic) can see WHY an action
                # didn't make it into the brief. Action-Executor side
                # also runs an enrichment pass for missing structured
                # fields; this catches the cases where the agent's
                # output couldn't even be parsed into a DraftedAction.
                if dropped_actions:
                    yield store.append(
                        trigger.case_id,
                        kind="error",
                        actor="system",
                        data={
                            "reason": "action_validation_warning",
                            "dropped_count": dropped_actions,
                            "kept_count": len(safe_actions),
                            "details": dropped_details,
                        },
                    )

                brief = Brief(
                    case_id=trigger.case_id,
                    tldr=args.get("tldr", ""),
                    findings=findings,
                    evidence=list(executor.evidence),
                    decision=Decision(
                        action=raw_action,  # type: ignore[arg-type]
                        amount_minor=args.get("decision_amount_minor"),
                        currency=args.get("decision_currency"),
                        rationale=args.get("decision_rationale", ""),
                        confidence=confidence,
                    ),
                    drafted_actions=safe_actions,
                    hitl_question=args.get("hitl_question", ""),
                    generated_at=datetime.utcnow(),
                )
                yield store.append(
                    trigger.case_id,
                    kind="brief_drafted",
                    actor="agent",
                    data=brief.model_dump(mode="json"),
                )
                yield store.append(
                    trigger.case_id,
                    kind="case_closed",
                    actor="system",
                    data={"reason": "concluded", "brief_seq": store.list_for_case(trigger.case_id)[-1].seq - 1},
                )
                return

        # Non-terminal tool calls: dispatch through the executor.
        results = await executor.dispatch(tool_calls)
        for r in results:
            # Side-effect: record_finding mutates the agent's Findings list.
            if r.tool_call_id:
                originating = next((tc for tc in tool_calls if tc.id == r.tool_call_id), None)
                if originating and originating.name == "record_finding":
                    findings.append(
                        Finding(
                            text=originating.arguments["text"],
                            citations=originating.arguments["citations"],
                            confidence=originating.arguments["confidence"],
                        )
                    )
                    yield store.append(
                        trigger.case_id,
                        kind="finding_recorded",
                        actor="agent",
                        data={
                            "idx": len(findings) - 1,
                            "text": originating.arguments["text"],
                            "citations": originating.arguments["citations"],
                            "confidence": originating.arguments["confidence"],
                        },
                    )
            yield store.append(
                trigger.case_id,
                kind="tool_result",
                actor="system",
                data={
                    "tool_call_id": r.tool_call_id,
                    "result": r.model_dump(mode="json", exclude={"evidence"}),
                    "evidence_added": len(r.evidence),
                },
            )

        # 4. Reflexion every 3 steps (Anthropic Reflexion pattern, 2-3 reps optimal)
        if budget.steps > 0 and budget.steps % 3 == 0:
            messages_for_reflexion = [
                {"role": "system", "content": REFLEXION},
                *events_to_messages(store.list_for_case(trigger.case_id)),
            ]
            try:
                ref_resp = chat(cfg, messages_for_reflexion, temperature=0.0)
                ref_text = ref_resp.choices[0].message.content or ""
                ref_usage = getattr(ref_resp, "usage", None)
                if ref_usage:
                    budget.charge(ref_usage.prompt_tokens, ref_usage.completion_tokens)
                yield store.append(
                    trigger.case_id,
                    kind="reflexion",
                    actor="agent",
                    data={"verdict_text": ref_text},
                )
            except Exception as exc:
                # Reflexion failure is non-fatal; loop continues.
                yield store.append(
                    trigger.case_id,
                    kind="error",
                    actor="system",
                    data={"reason": "reflexion_failed", "detail": str(exc)},
                )
