"""Pydantic models - request/response schemas for the API.

Mirror the DB schema where useful but stay separate so the API surface can
evolve independently of the storage layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────────────
# Org / Member
# ──────────────────────────────────────────────────────────────────────


class Org(BaseModel):
    id: UUID
    slug: str
    name: str
    plan: str
    created_at: datetime


class Member(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    name: str | None = None
    role: Literal["admin", "approver", "viewer"]
    approval_limit_minor: int
    created_at: datetime


# ──────────────────────────────────────────────────────────────────────
# Case + Findings
# ──────────────────────────────────────────────────────────────────────

CaseStatus = Literal[
    "investigating",
    "awaiting_approval",
    "acting",
    "resolved",
    "errored",
    "escalated",
]

TriggerSurface = Literal[
    "stripe_webhook",
    "inbound_email",
    "slack_mention",
    "slack_dm",
    "cron",
    "web_new",
    "api",
]

CaseType = Literal[
    "chargeback",
    "refund_request",
    "sla_credit",
    "failed_renewal",
    "invoice_dispute",
    # Slack-originated cases that didn't hit the demo-v3 graft path
    # (channel mismatch, non-member sender, etc.) get this generic type
    # so the agent still investigates without us pretending it's a
    # chargeback.
    "slack_request",
    "other",
]

DecisionAction = Literal["refund", "fight", "partial_credit", "escalate", "accept"]


class Citation(BaseModel):
    source: str          # "stripe" | "salesforce" | ...
    table: str           # "disputes" | "opportunities" | ...
    ref: str             # row identifier
    field: str | None = None
    url: str | None = None  # deep-link to source record (filled by citation_links service)


class Finding(BaseModel):
    id: UUID
    seq: int
    text: str
    confidence: float | None = None
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class Case(BaseModel):
    id: UUID
    org_id: UUID
    short_id: str
    status: CaseStatus
    trigger_surface: TriggerSurface
    case_type: CaseType | None = None
    customer_ref: str | None = None
    amount_minor: int | None = None
    # Real-world cases (esp. non-monetary Slack/email triggers) may have
    # no currency yet - the agent fills it in once it identifies the
    # charge. Was strict-str → 500 on the inbox endpoint whenever a case
    # row had currency=NULL.
    currency: str | None = None
    decision_action: DecisionAction | None = None
    decision_amount_minor: int | None = None
    decision_confidence: float | None = None
    assigned_member_id: UUID | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    # Optional joined data (populated by specific endpoints)
    findings: list[Finding] | None = None
    # brief + policy_match are denormalised onto the case detail endpoint
    # so the UI doesn't need a second fetch to show the decision rationale
    # and which policy rule matched.
    brief: "BriefSummary | None" = None
    policy_match: "PolicyMatchSummary | None" = None
    # One-line summary written by the prettifier (Gemini Flash Lite). Used
    # by the inbox cards; populated by the list endpoint, null elsewhere.
    card_summary: str | None = None

    # True when this case was opened via the demo-v2 guided flow and the
    # webhook grafted seeded Stripe/HubSpot IDs onto trigger_payload. The
    # UI reads this to show a small "demo" annotation above the brief
    # explaining why the case references Maya Patel Design / hitakshi220
    # even though the operator is logged in with their own email.
    # Kept for backwards-compat with older clients; new code reads
    # `demo_mode` which carries the specific demo flavour.
    is_demo_v2: bool = False
    # Which guided demo grafted seeded data onto this case:
    #   "v2" - inbound-email demo, Maya Patel scenario IDs attached
    #   "v3" - Slack-mention demo, Vermillion Studios scenario IDs attached
    #   None - real case, no seeded graft
    demo_mode: str | None = None


class BriefSummary(BaseModel):
    """The latest `brief_drafted` event's important fields."""

    tldr: str | None = None
    decision_rationale: str | None = None
    decision_action: str | None = None
    decision_amount_minor: int | None = None
    decision_confidence: float | None = None
    hitl_question: str | None = None
    generated_at: datetime | None = None


class PolicyMatchSummary(BaseModel):
    """The latest policy match on this case (if any)."""

    rule_name: str
    mode: str  # auto | suggest | escalate
    matched_at: datetime


class CaseList(BaseModel):
    cases: list[Case]
    total: int


class CreateCaseRequest(BaseModel):
    """For the web `+ New case` button or API trigger."""

    trigger_text: str
    case_type: CaseType = "other"
    customer_ref: str | None = None
    amount_minor: int | None = None
    currency: str = "usd"
    metadata: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# Action
# ──────────────────────────────────────────────────────────────────────

ActionStatus = Literal[
    "drafted",
    "awaiting_approval",
    "approved",
    "executing",
    "succeeded",
    "failed",
    "drift",
]


class Action(BaseModel):
    id: UUID
    org_id: UUID
    case_id: UUID
    seq: int
    type: str             # e.g. "stripe.refund"
    payload: dict[str, Any]
    status: ActionStatus
    external_ref: str | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    verified_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime


# ──────────────────────────────────────────────────────────────────────
# Event
# ──────────────────────────────────────────────────────────────────────


class Event(BaseModel):
    id: int
    org_id: UUID
    thread_id: UUID
    seq: int
    type: str
    actor: str
    data: dict[str, Any]
    signed_at: datetime | None = None
    signature: str | None = None
    created_at: datetime


# ──────────────────────────────────────────────────────────────────────
# HITL
# ──────────────────────────────────────────────────────────────────────


class HitlPending(BaseModel):
    id: UUID
    case_id: UUID
    decision_required: str
    assigned_to: UUID | None = None
    deadline: datetime | None = None
    created_at: datetime
