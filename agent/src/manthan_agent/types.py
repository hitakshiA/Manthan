"""Core types for the Manthan investigator.

These flow through every stage of the agent loop. Pydantic enforces the
contract at each boundary - the LLM's structured output is parsed into
a typed object, and the next iteration only sees the typed object.

This is the locked vocabulary. Every other module operates on these
types. Read this file first.

Design notes:
- NO Pattern enum. The agent reasons about each case from first
  principles - it doesn't classify into a fixed taxonomy. Patterns
  exist for evals and docs, not control flow.
- The Event log is the single source of truth. State is derived.
- Tool results carry full provenance via Evidence.
- HITL gates are deterministic, computed outside the model.
- NextStep is a typed Union - no string-based intent parsing.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────────────
# Trigger - what starts a case
# ──────────────────────────────────────────────────────────────────────


class CaseTrigger(BaseModel):
    """The opening event for a case.

    Free-form text plus optional structured payload. The agent reads
    this and reasons about what kind of work it is - no classifier
    stage.
    """

    case_id: str
    text: str = Field(description="Free-form description of the case")
    structured: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional structured event (e.g. Stripe webhook payload). "
            "Agent reads this alongside text."
        ),
    )
    source_surface: Literal[
        "stripe_webhook",
        "intercom_ticket",
        "manual_web",
        "manual_slack",
        "slack_mention",
        "slack_dm",
        "inbound_email",
        "cron_proactive",
        "api",
    ] = "manual_web"


# ──────────────────────────────────────────────────────────────────────
# Evidence - one row from any source, full provenance
# ──────────────────────────────────────────────────────────────────────


class Evidence(BaseModel):
    """One row retrieved from a source. Every Finding cites by index.

    Provenance fields are populated by the tool executor, not the LLM.
    The LLM never sees the raw row - it sees the Evidence wrapper with
    `source.table.record_id` so citation is structural.
    """

    source: str = Field(description="e.g. 'stripe', 'salesforce'")
    table: str = Field(description="e.g. 'disputes', 'accounts'")
    record_id: str = Field(description="Primary key in the source system")
    fields: dict[str, Any] = Field(description="The row payload")
    query: str = Field(description="The SQL or tool call that produced it")
    retrieved_at: datetime


# ──────────────────────────────────────────────────────────────────────
# Finding - a typed, cited claim
# ──────────────────────────────────────────────────────────────────────


class Finding(BaseModel):
    """A factual assertion the agent is willing to make.

    Every Finding cites at least one Evidence index. Type-system rejects
    findings without citations. The brief is rendered from a list of
    Findings - no free-form prose lives outside this structure.
    """

    text: str = Field(description="1-2 sentences, present-tense, factual")
    citations: list[int] = Field(
        min_length=1,
        description="Indices into the case's Evidence list",
    )
    confidence: float = Field(ge=0, le=1)


# ──────────────────────────────────────────────────────────────────────
# Decision - the agent's recommendation
# ──────────────────────────────────────────────────────────────────────


class HitlGate(StrEnum):
    """Where the case lands in the approval flow.

    Computed deterministically by the orchestrator after the agent
    proposes a Decision. The LLM does NOT pick the gate - policy does.

    Locked thresholds (from marketing site):
      AUTO        amount_minor < 5000  (i.e. < $50)
      ONE_CLICK   5000 <= amount_minor < 50000 (i.e. $50-$500)
      TWO_PERSON  amount_minor >= 50000 (i.e. >= $500)
      Always TWO_PERSON for any account with ARR > $50,000.
    """

    AUTO = "auto"
    ONE_CLICK = "one-click"
    TWO_PERSON = "two-person"


class Decision(BaseModel):
    """What the agent thinks should happen."""

    action: Literal["fight", "refund", "accept", "escalate"]
    amount_minor: int | None = Field(
        default=None, description="In cents/paise; None for non-monetary actions"
    )
    currency: str | None = Field(default=None, description="ISO 4217, e.g. 'usd'")
    rationale: str = Field(
        description="2-4 sentences referencing finding indices [1][3] etc"
    )
    confidence: float = Field(ge=0, le=1)


# ──────────────────────────────────────────────────────────────────────
# Drafted actions - the writes the agent proposes (gated by HITL)
# ──────────────────────────────────────────────────────────────────────


class DraftedAction(BaseModel):
    """One action ready for human approval.

    `payload` is action-specific. The Action Executor (separate process,
    write-scoped credentials) consumes this only after HITL approval.
    The LLM never holds write keys.
    """

    kind: Literal[
        "stripe_refund",
        "stripe_dispute_response",
        "customer_email",
        "hubspot_note",
        "slack_brief",
    ]
    payload: dict[str, Any]
    description: str = Field(description="One-line summary for the approve page")
    reversibility: Literal["reversible", "partial", "irreversible"] = "reversible"


# ──────────────────────────────────────────────────────────────────────
# Brief - the approve-page artifact
# ──────────────────────────────────────────────────────────────────────


class Brief(BaseModel):
    """The final case artifact. What humans approve, edit, or chat with.

    Renders to the structure shown on the marketing site (Case 4821):
        TL;DR
        Drafted actions
        Findings (with citations)
        Evidence (numbered, citable)
        HITL question (decision-quality, not 'approve?')

    Every field traces back to a typed source. No prose lives outside
    typed structures.
    """

    case_id: str
    tldr: str = Field(description="2-3 sentences for a busy controller")
    findings: list[Finding]
    evidence: list[Evidence]
    decision: Decision
    drafted_actions: list[DraftedAction]
    hitl_question: str = Field(
        description=(
            "Decision-quality question for the human. Names the tradeoff, "
            "the alternatives, the precedent risk. Not 'approve?'"
        )
    )
    generated_at: datetime


# ──────────────────────────────────────────────────────────────────────
# Tool plumbing
# ──────────────────────────────────────────────────────────────────────


class ToolCall(BaseModel):
    """One tool the LLM wants to invoke this turn."""

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """Envelope every tool returns. Saves ~60% on retry-driven loops.

    The LLM sees `status`, `data`, `next_action_hint` - never raw
    exceptions. Categorized errors so the LLM can decide whether to
    retry, change inputs, or escalate.
    """

    tool_call_id: str
    status: Literal["ok", "no_results", "error", "rate_limited", "permission_denied"]
    data: dict[str, Any] | None = None
    is_complete: bool = True
    total_matches: int | None = None
    error_type: str | None = None
    retryable: bool = False
    retry_after_ms: int | None = None
    next_action_hint: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# NextStep - the typed dispatch (OpenAI Agents SDK pattern)
# ──────────────────────────────────────────────────────────────────────


class NextStepRunAgain(BaseModel):
    """Continue the loop. New events have been appended."""

    kind: Literal["run_again"] = "run_again"
    new_events: list[Event] = Field(default_factory=list)


class NextStepInterruption(BaseModel):
    """Pause for HITL. Caller persists state and surfaces a UI."""

    kind: Literal["interruption"] = "interruption"
    reason: Literal["hitl_gate", "ask_human", "budget", "stuck"]
    question: str | None = None
    recommendation: str | None = None
    options: list[str] = Field(default_factory=list)
    confidence: float | None = None


class NextStepFinalOutput(BaseModel):
    """Investigation complete. Brief is ready."""

    kind: Literal["final_output"] = "final_output"
    brief: Brief


NextStep = Annotated[
    NextStepRunAgain | NextStepInterruption | NextStepFinalOutput,
    Field(discriminator="kind"),
]


# ──────────────────────────────────────────────────────────────────────
# Event - the single source of truth
# ──────────────────────────────────────────────────────────────────────


class Event(BaseModel):
    """One entry in the case event log. Append-only.

    The entire case state is derivable from the event log. State is not
    stored separately. This is the 12-Factor Agents pattern (#3 + #5):
    own the context window, unify execution and business state.
    """

    case_id: str
    seq: int
    kind: Literal[
        "case_opened",          # initial trigger
        "agent_thought",        # LLM reasoning (non-tool turn)
        "tool_call",            # LLM wants to call a tool
        "tool_result",          # tool returned (carries Evidence)
        "finding_recorded",     # agent asserted a typed Finding
        "decision_recorded",    # agent picked an action
        "draft_action_added",   # agent staged a write
        "reflexion",            # every-3-steps self-check
        "hitl_pause",           # waiting for human
        "human_response",       # human approve/edit/reject/chat
        "agent_reply",          # agent's reply to a human chat message
        "brief_drafted",        # final brief ready
        "action_fired",         # write committed by Action Executor
        "case_closed",
        "error",
    ]
    actor: str = Field(description="system | agent | human:<user_id> | external:<source>")
    data: dict[str, Any]
    ts: datetime
    trace_id: str | None = None
    span_id: str | None = None


# Resolve forward references for NextStepRunAgain.new_events
NextStepRunAgain.model_rebuild()
