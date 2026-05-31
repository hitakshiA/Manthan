"""Tool registry + executor.

The agent gets a fixed toolkit. Each tool has a Pydantic-schemad input
type and a `read_only` flag that determines dispatch behavior:

  read_only = True   → run in parallel (asyncio.gather)
  read_only = False  → run serially through an idempotency queue

For step 1 (this file), the Coral tools are MOCK - they return canned
evidence. Step 3 swaps them for real MCP calls against the Coral binary.
The agent code doesn't change.
"""

from __future__ import annotations

import asyncio
import contextvars
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from . import duckdb_world
from .coral_session import get_active_coral_session
from .types import DraftedAction, Evidence, ToolCall, ToolResult

# ──────────────────────────────────────────────────────────────────────
# Tool argument schemas (each becomes a JSON Schema for the LLM)
# ──────────────────────────────────────────────────────────────────────


class CoralSqlArgs(BaseModel):
    query: str = Field(description="SQL to execute against Coral's catalog")


class CoralListCatalogArgs(BaseModel):
    pass


class CoralDescribeTableArgs(BaseModel):
    qualified_name: str = Field(description="e.g. 'stripe.disputes'")


class RecordFindingArgs(BaseModel):
    text: str = Field(description="1-2 sentences, present-tense, factual")
    citations: list[int] = Field(
        min_length=1, description="Indices into the case's Evidence list"
    )
    confidence: float = Field(ge=0, le=1)


class AskHumanArgs(BaseModel):
    question: str = Field(
        description="Decision-quality question, not 'approve?'"
    )
    recommendation: str = Field(description="What you think the right action is")
    confidence: float = Field(ge=0, le=1)
    options: list[str] = Field(
        default_factory=list,
        description="Named alternatives the human can pick",
    )


class ConcludeArgs(BaseModel):
    tldr: str = Field(description="2-3 sentences for a busy controller")
    decision_action: str = Field(
        description=(
            "One of: fight | refund | accept | escalate. "
            "fight=customer has zero merit, oppose entirely. "
            "refund=pay the customer some amount (can be less than the disputed "
            "amount if customer over-claimed). "
            "accept=pay the full disputed amount. "
            "escalate=human judgment needed. "
            "If the customer's claim is partly valid but they over-claimed, the "
            "action is REFUND with the correctly-computed smaller amount, not "
            "fight. Fighting is reserved for cases where the customer has no "
            "legitimate basis."
        )
    )
    decision_amount_minor: int | None = Field(
        default=None,
        description=(
            "Amount in MINOR currency units (cents for USD, pence for GBP, etc.). "
            "A $4,200 amount = 420000. A $900 amount = 90000. A $111 amount = 11100. "
            "Multiply dollar values by 100 before setting this field. "
            "Leave null for 'fight' and 'escalate' actions where no money moves."
        ),
    )
    decision_currency: str | None = None
    decision_rationale: str = Field(
        description="2-4 sentences with finding citations [1][2]"
    )
    decision_confidence: float = Field(ge=0, le=1)
    drafted_actions: list[DraftedAction] = Field(
        default_factory=list,
        description=(
            "List of DraftedAction objects - one per concrete action the "
            "Action Executor should fire after human approval. Draft the "
            "COMPLETE set for this decision_action / case_type (see the "
            "Drafted-action rules in the system prompt). Each item MUST "
            "include kind, payload, and description. Empty / partial / "
            "TODO payloads are rejected. Pull identifiers (charge_id, "
            "dispute_id, customer_email, hubspot_company_id) from the "
            "case trigger_payload - do NOT leave them blank.\n\n"
            "Worked examples (use as exact templates, swap in real ids):\n"
            '  {"kind": "stripe_refund", "payload": {"charge_id": "ch_xxx", '
            '"amount_minor": 56000, "currency": "usd", "reason": '
            '"documented_incident_pro_rata"}, "description": "Refund $560 '
            'against ch_xxx - 2/30 × $8,400 pro-rata", "reversibility": '
            '"reversible"}\n'
            '  {"kind": "stripe_dispute_response", "payload": {"dispute_id": '
            '"du_xxx", "submit": true, "evidence": {"uncategorized_text": '
            '"Pro-rata credit issued - conceding remainder."}}, '
            '"description": "Concede dispute du_xxx", "reversibility": '
            '"partial"}\n'
            '  {"kind": "customer_email", "payload": {"to": '
            '"customer@example.com", "subject": "Update on your dispute '
            'du_xxx", "body_text": "Hi,\\n\\nWe issued a $560 credit..."}, '
            '"description": "Email customer about credit", "reversibility": '
            '"irreversible"}\n'
            '  {"kind": "hubspot_note", "payload": {"company_id": '
            '"324968425171", "body_html": "<p>APR-xxx - partial_credit '
            '($560)...</p>"}, "description": "Log resolution to HubSpot", '
            '"reversibility": "reversible"}\n'
            '  {"kind": "slack_brief", "payload": {"channel": "#billing-ops", '
            '"text": "RESOLVED · APR-xxx · partial_credit ($560)..."}, '
            '"description": "Post brief to #billing-ops", "reversibility": '
            '"reversible"}\n'
            '  {"kind": "linear_ticket", "payload": {"team_id": "BILLING", '
            '"title": "SLO: Custom Reports degraded 48h", "description": '
            '"Datadog INC-... covers a 48h degradation..."}, "description": '
            '"File SLO follow-up", "reversibility": "reversible"}'
        ),
    )
    hitl_question: str = Field(
        description="Decision-quality question naming the tradeoff"
    )


# ──────────────────────────────────────────────────────────────────────
# Tool registry
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    schema: type[BaseModel]
    read_only: bool
    is_terminal: bool = False  # if True, calling it ends the loop


TOOLS: list[ToolDef] = [
    ToolDef(
        name="coral_sql",
        description=(
            "Execute SQL against Coral's local SQL plane (which aggregates "
            "~30 source APIs). Returns structured rows with full provenance "
            "(source, table, record_id). Prefer ONE query joining multiple "
            "sources over N single-source queries."
        ),
        schema=CoralSqlArgs,
        read_only=True,
    ),
    ToolDef(
        name="coral_list_catalog",
        description=(
            "List all schemas, tables, and table-functions visible to Coral. "
            "Call this once at the start of investigation to know what's available."
        ),
        schema=CoralListCatalogArgs,
        read_only=True,
    ),
    ToolDef(
        name="coral_describe_table",
        description=(
            "Return the column list and types for one Coral table. "
            "Use before composing SQL against a table you haven't queried before."
        ),
        schema=CoralDescribeTableArgs,
        read_only=True,
    ),
    ToolDef(
        name="record_finding",
        description=(
            "Assert a factual claim with at least one Evidence citation. "
            "Findings are the building blocks of the final brief. "
            "Every claim in your reasoning should be a Finding with citations."
        ),
        schema=RecordFindingArgs,
        read_only=False,
    ),
    ToolDef(
        name="ask_human",
        description=(
            "Pause investigation and ask the human a decision-quality "
            "question. Use when evidence contradicts, when you're below "
            "0.7 confidence on a high-stakes call, or when the case is "
            "genuinely novel."
        ),
        schema=AskHumanArgs,
        read_only=False,
        is_terminal=True,
    ),
    ToolDef(
        name="conclude",
        description=(
            "End the investigation. Emit the final Brief with TL;DR, "
            "Decision, DraftedActions, and HITL question. Call this when "
            "your confidence is high enough to recommend OR when evidence "
            "is saturated."
        ),
        schema=ConcludeArgs,
        read_only=False,
        is_terminal=True,
    ),
]


def tool_by_name(name: str) -> ToolDef | None:
    for t in TOOLS:
        if t.name == name:
            return t
    return None


def openai_schema() -> list[dict[str, Any]]:
    """Render all tools as OpenAI-shape function definitions.

    Uses `strict: true` per the 2026 production pattern - the model
    cannot emit a malformed call. Combined with the
    `structured-outputs-2025-11-13` header on the client, this gives
    us constrained decoding at the token level.
    """
    out: list[dict[str, Any]] = []
    for t in TOOLS:
        schema = t.schema.model_json_schema()
        # OpenAI requires additionalProperties: false on every nested object
        # for strict mode. Pydantic doesn't add it by default.
        _enforce_strict(schema)
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": schema,
                    "strict": True,
                },
            }
        )
    return out


def _enforce_strict(schema: dict[str, Any]) -> None:
    """Walk a JSON schema and add `additionalProperties: false` to
    every object, plus ensure all properties are in `required` (OpenAI
    strict mode demands this; use `null` unions for optional)."""
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        props = schema.get("properties", {})
        if props:
            schema["required"] = list(props.keys())
        for v in props.values():
            _enforce_strict(v)
    if "items" in schema and isinstance(schema["items"], dict):
        _enforce_strict(schema["items"])
    if "$defs" in schema:
        for v in schema["$defs"].values():
            _enforce_strict(v)
    if "anyOf" in schema:
        for v in schema["anyOf"]:
            _enforce_strict(v)


# ──────────────────────────────────────────────────────────────────────
# Mock implementations (step 1)
# Step 3 replaces these with real Coral MCP calls.
# ──────────────────────────────────────────────────────────────────────


MockHandler = Callable[[dict[str, Any], list[Evidence]], ToolResult]


# ----------------------------------------------------------------------
# Source-aware mock fixture for CASE-SMK-001 / CASE-INSP-001 (TechCorp).
#
# A wider JOIN should surface more evidence - that's Coral's whole moat.
# The naive previous mock returned the same 8 fields regardless of query
# shape, giving the model no incentive to JOIN. This mock parses the SQL
# string for `<source>.<table>` references and unions the corresponding
# fact bundles into the returned row. So:
#
#   - A single-source `SELECT * FROM stripe.disputes` gets ~15 stripe
#     fields.
#   - A 6-source JOIN gets ~50 fields covering payments, sub state, CRM,
#     support history, policy, and usage.
#
# Ground truth picture: customer claims they cancelled, but no formal
# cancel was ever submitted; subscription is active; product was used
# 3 days before the dispute; policy says fight when usage exists within
# 14 days. Correct decision: fight.
# ----------------------------------------------------------------------

_KNOWN_SOURCES: set[str] = {
    "stripe", "chargebee", "razorpay", "hubspot", "salesforce", "intercom",
    "zendesk", "slack", "notion", "confluence", "gmail", "postmark", "resend",
    "mailchimp", "loops", "twilio", "clerk", "cal", "mixpanel", "posthog",
    "sentry", "datadog", "grafana", "pagerduty", "statusgator", "launchdarkly",
    "github", "linear", "google_drive", "k8s",
}


# Contextvar hooks so callers (e.g. scenario_bake.py) can swap the
# mock's world per-case without touching the call signature. When
# unset, mocks fall back to the built-in TechCorp fixture below. Bind
# via set_scenario_world() inside a single run_case() context.
_ACTIVE_HEADER: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("manthan_mock_header", default=None)
)
_ACTIVE_FACTS: contextvars.ContextVar[dict[str, dict[str, Any]] | None] = (
    contextvars.ContextVar("manthan_mock_facts", default=None)
)
_ACTIVE_CATALOG: contextvars.ContextVar[list[dict[str, Any]] | None] = (
    contextvars.ContextVar("manthan_mock_catalog", default=None)
)
# NEW: when set, the mock dispatches to a real DuckDB connection.
# Scenarios with brutal volume + row-level navigation use this path;
# flat scenarios use the legacy bundle path above.
_ACTIVE_DUCKDB: contextvars.ContextVar[Any | None] = (
    contextvars.ContextVar("manthan_mock_duckdb", default=None)
)


def set_scenario_world(
    *,
    header: dict[str, Any] | None = None,
    facts: dict[str, dict[str, Any]] | None = None,
    catalog: list[dict[str, Any]] | None = None,
    duckdb_con: Any | None = None,
) -> tuple[contextvars.Token, contextvars.Token, contextvars.Token, contextvars.Token]:
    """Bind a scenario world to the mock for the current async context.

    Pass either (facts + header + catalog) for the legacy bundle path,
    or duckdb_con for the brutal-data path. Returns a token tuple; pass
    it to clear_scenario_world() to unwind.
    """
    return (
        _ACTIVE_HEADER.set(header),
        _ACTIVE_FACTS.set(facts),
        _ACTIVE_CATALOG.set(catalog),
        _ACTIVE_DUCKDB.set(duckdb_con),
    )


def clear_scenario_world(
    tokens: tuple[contextvars.Token, contextvars.Token, contextvars.Token, contextvars.Token],
) -> None:
    h_tok, f_tok, c_tok, d_tok = tokens
    _ACTIVE_HEADER.reset(h_tok)
    _ACTIVE_FACTS.reset(f_tok)
    _ACTIVE_CATALOG.reset(c_tok)
    _ACTIVE_DUCKDB.reset(d_tok)

_SOURCE_REF_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*")


def _sources_in_query(q: str) -> set[str]:
    return {
        m.group(1) for m in _SOURCE_REF_RE.finditer(q.lower())
        if m.group(1) in _KNOWN_SOURCES
    }


# Always-present case header - every query at minimum identifies the
# case under investigation.
_DISPUTE_HEADER: dict[str, Any] = {
    "dispute_id": "dp_mock_1Qxxxx",
    "dispute_amount_minor": 120000,
    "dispute_currency": "usd",
    "dispute_reason": "subscription_canceled",
    "dispute_status": "needs_response",
    "dispute_evidence_due_by": "2026-06-08T00:00:00Z",
    "customer_email": "ops@techcorp.example",
    "stripe_customer_id": "cus_8mFqZ",
}

# Per-source fact bundles. Touching a source via JOIN unions its bundle
# into the returned row. Bundles are intentionally rich (8-15 fields)
# so a wide JOIN has plenty of signal to extract findings from.
_FACTS_BY_SOURCE: dict[str, dict[str, Any]] = {
    "stripe": {
        "charge_id": "ch_mock_3MqXfL",
        "charge_amount_minor": 120000,
        "charge_currency": "usd",
        "charge_created": "2026-05-12T14:21:00Z",
        "charge_status": "succeeded",
        "charge_payment_method": "card_visa_4242",
        "subscription_id": "sub_mock_Qxx",
        "subscription_status": "active",
        "subscription_cancel_at_period_end": False,
        "subscription_canceled_at": None,
        "subscription_current_period_start": "2026-05-12T00:00:00Z",
        "subscription_current_period_end": "2027-05-12T00:00:00Z",
        "subscription_collection_method": "charge_automatically",
        "prior_disputes_14mo": 0,
        "prior_refunds_24mo": 1,
        "refund_last_amount_minor": 4500,
        "refund_last_reason": "duplicate_charge",
        "invoice_last_paid_at": "2026-05-12T14:21:00Z",
    },
    "salesforce": {
        "sf_account_id": "001Qxxxxx",
        "sf_account_name": "TechCorp Industries",
        "sf_plan": "Pro Annual",
        "sf_arr_minor": 4000000,
        "sf_health": "green",
        "sf_nps_last": 7,
        "sf_csm_owner": "amelia@us",
        "sf_renewal_date": "2027-05-12",
        "sf_account_owner_notes": "Renewed 2024, expanded 2025. No churn signals on file.",
    },
    "hubspot": {
        "hs_company_id": "12345",
        "hs_company_industry": "industrial automation",
        "hs_lifecycle_stage": "customer",
        "hs_last_contacted": "2026-05-02T09:00:00Z",
        "hs_owner": "amelia@us",
        "hs_deal_stage_latest": "closed_won_renewal",
    },
    "intercom": {
        "ic_conversations_90d": 4,
        "ic_last_subject": "Plan pricing question",
        "ic_last_body_snippet": (
            "We are reviewing plans and may downgrade. Can you share Standard "
            "tier pricing? Not cancelling - just evaluating."
        ),
        "ic_last_at": "2026-04-29T15:00:00Z",
        "ic_cancel_intent_mentions_90d": 1,
        "ic_formal_cancel_requests_90d": 0,
    },
    "zendesk": {
        "zd_open_tickets": 0,
        "zd_tickets_90d": 2,
        "zd_last_subject": "Add seats to plan",
        "zd_last_status": "solved",
        "zd_last_at": "2026-04-15T11:23:00Z",
        "zd_cancel_tickets_90d": 0,
    },
    "slack": {
        "slack_cs_escalations_90d": 1,
        "slack_last_text_snippet": (
            "TechCorp asked about downgrade options on Apr 29 - Amelia handled, "
            "no cancel request followed."
        ),
        "slack_last_ts": "2026-04-29T16:10:00Z",
    },
    "notion": {
        "notion_refunds_title": "Refunds & Disputes - 2026 SOP",
        "notion_refunds_body": (
            "Refunds are not issued after 30 days from charge except for "
            "duplicate billing or proven service outage. For chargeback "
            "disputes, FIGHT when documented product usage exists within "
            "14 days before the dispute."
        ),
        "notion_refunds_updated_at": "2026-02-10T09:00:00Z",
        "notion_chargeback_runbook_title": "Chargeback Response Playbook v3",
    },
    "posthog": {
        "ph_last_active_at": "2026-05-09T22:14:00Z",
        "ph_logins_30d": 12,
        "ph_distinct_users_active_30d": 8,
        "ph_critical_actions_14d": 22,
        "ph_signups_30d": 0,
    },
}


def _mock_coral_sql_duckdb(
    query: str,
    con: Any,
    evidence_acc: list[Evidence],
) -> ToolResult:
    """Brutal-data path: run the agent's SQL against a real DuckDB.

    Returns a single Evidence whose fields carry the result rows + meta.
    A SQL error becomes a ToolResult with status="error" and a message
    the model can read and self-correct off.
    """
    cols, rows, total_matches, err = duckdb_world.execute_query(con, query)
    sources_used = sorted(_sources_in_query(query))

    if err is not None:
        # SQL error - record an Evidence (so the agent sees the query
        # was attempted) but mark the result as error.
        ev = Evidence(
            source="coral_error",
            table=",".join(sources_used) or "(unknown)",
            record_id=f"err_{len(evidence_acc):02d}",
            fields={"sql_error": err, "query": query},
            query=query,
            retrieved_at=datetime.utcnow(),
        )
        idx = len(evidence_acc)
        evidence_acc.append(ev)
        return ToolResult(
            tool_call_id="",
            status="error",
            data={
                "error": err,
                "hint": "SQL error from Coral. Inspect the message, "
                        "verify column/table names with coral_describe_table, "
                        "and retry.",
                "evidence_indices": [idx],
            },
            evidence=[ev],
        )

    # Success - package the rows into one Evidence.
    is_join = len(sources_used) > 1
    source_label = "coral_join" if is_join else (sources_used[0] if sources_used else "coral")
    table_label = "+".join(sources_used) if is_join else (sources_used[0] if sources_used else "(none)")

    ev = Evidence(
        source=source_label,
        table=table_label,
        record_id=f"q_{len(evidence_acc):02d}",
        fields={
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "total_matches": total_matches,
        },
        query=query,
        retrieved_at=datetime.utcnow(),
    )
    idx = len(evidence_acc)
    evidence_acc.append(ev)

    return ToolResult(
        tool_call_id="",
        status="ok",
        data={
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "total_matches": total_matches,
            "truncated": total_matches > len(rows),
            "evidence_indices": [idx],
            "sources_joined": sources_used,
        },
        is_complete=total_matches <= len(rows),
        total_matches=total_matches,
        evidence=[ev],
    )


def _mock_coral_sql(args: dict[str, Any], evidence_acc: list[Evidence]) -> ToolResult:
    """Mock that dispatches to one of two backends.

    1. If a DuckDB connection is bound via set_scenario_world(duckdb_con=...),
       execute the agent's SQL against it for real. Volume, JOINs, WHERE
       filters, aggregates - the agent gets back actual result-sets and
       has to navigate them.
    2. Otherwise, fall back to the legacy source-aware bundle path: parse
       which `<source>.<table>` references appear in the SQL, union the
       matching pre-curated bundles into a single row. Used by simple
       single-row scenarios.
    """
    query = args.get("query", "<unknown>")

    duck_con = _ACTIVE_DUCKDB.get()
    if duck_con is not None:
        return _mock_coral_sql_duckdb(query, duck_con, evidence_acc)

    referenced = _sources_in_query(query)
    facts_by_source = _ACTIVE_FACTS.get() or _FACTS_BY_SOURCE
    header = _ACTIVE_HEADER.get() or _DISPUTE_HEADER

    # Default to "stripe" if no source is referenced and stripe is in the
    # world; otherwise to the first source available. Don't crash on a
    # world that doesn't include stripe.
    if referenced:
        sources_used: list[str] = sorted(referenced)
    elif "stripe" in facts_by_source:
        sources_used = ["stripe"]
    elif facts_by_source:
        sources_used = sorted(facts_by_source.keys())[:1]
    else:
        sources_used = []

    fields: dict[str, Any] = dict(header)
    for src in sources_used:
        bundle = facts_by_source.get(src)
        if bundle:
            fields.update(bundle)

    is_join = len(sources_used) > 1
    source_label = "coral_join" if is_join else sources_used[0]
    table_label = "+".join(sources_used) if is_join else "joined_view"

    row = Evidence(
        source=source_label,
        table=table_label,
        record_id=f"join_{len(evidence_acc):02d}",
        fields=fields,
        query=query,
        retrieved_at=datetime.utcnow(),
    )
    idx = len(evidence_acc)
    evidence_acc.append(row)

    return ToolResult(
        tool_call_id="",  # filled by dispatcher
        status="ok",
        data={
            "rows": [fields],
            "row_count": 1,
            "evidence_indices": [idx],
            "sources_joined": sources_used,
            "column_count": len(fields),
        },
        is_complete=True,
        total_matches=1,
        evidence=[row],
    )


_DEFAULT_CATALOG: list[dict[str, Any]] = [
    {"name": "stripe",     "tables": ["disputes", "charges", "customers", "invoices", "subscriptions", "refunds"]},
    {"name": "salesforce", "tables": ["accounts", "opportunities", "contacts"]},
    {"name": "hubspot",    "tables": ["companies", "contacts", "deals", "notes"]},
    {"name": "intercom",   "tables": ["conversations", "contacts"]},
    {"name": "zendesk",    "tables": ["tickets", "users"]},
    {"name": "slack",      "tables": ["channels", "messages"]},
    {"name": "notion",     "tables": ["pages", "blocks"]},
    {"name": "posthog",    "tables": ["events", "persons"]},
]


def _mock_coral_list_catalog(args: dict[str, Any], _ev: list[Evidence]) -> ToolResult:
    duck_con = _ACTIVE_DUCKDB.get()
    if duck_con is not None:
        schemas = duckdb_world.list_catalog(duck_con)
    else:
        catalog = _ACTIVE_CATALOG.get()
        schemas = catalog if catalog is not None else _DEFAULT_CATALOG
    return ToolResult(
        tool_call_id="",
        status="ok",
        data={
            "schemas": schemas,
            "note": "MOCK CATALOG - real Coral wires in step 3.",
        },
    )


def _mock_coral_describe(args: dict[str, Any], _ev: list[Evidence]) -> ToolResult:
    qname = args.get("qualified_name", "")
    duck_con = _ACTIVE_DUCKDB.get()
    if duck_con is not None:
        columns = duckdb_world.describe_table(duck_con, qname)
        return ToolResult(
            tool_call_id="",
            status="ok",
            data={
                "table": qname,
                "columns": columns,
                "note": "Live schema from active scenario DB.",
            },
        )
    return ToolResult(
        tool_call_id="",
        status="ok",
        data={
            "table": qname,
            "columns": [
                {"name": "id",       "type": "string"},
                {"name": "amount",   "type": "int64"},
                {"name": "currency", "type": "string"},
                {"name": "reason",   "type": "string"},
                {"name": "status",   "type": "string"},
                {"name": "created",  "type": "timestamp"},
            ],
            "note": "MOCK SCHEMA - flat fallback.",
        },
    )


MOCK_HANDLERS: dict[str, MockHandler] = {
    "coral_sql": _mock_coral_sql,
    "coral_list_catalog": _mock_coral_list_catalog,
    "coral_describe_table": _mock_coral_describe,
}


# ──────────────────────────────────────────────────────────────────────
# Real Coral handlers (async - called when get_active_coral_session()
# returns a live ClientSession; otherwise mocks take over).
# ──────────────────────────────────────────────────────────────────────


import json  # noqa: E402 - defer to keep imports grouped


def _extract_text(call_result: Any) -> str:
    """Pull the first text content block from an MCP call result."""
    if not call_result.content:
        return ""
    first = call_result.content[0]
    return getattr(first, "text", str(first))


async def _real_coral_sql(
    args: dict[str, Any], evidence_acc: list[Evidence]
) -> ToolResult:
    session = get_active_coral_session()
    if session is None:
        # Defensive - caller should only invoke this when session is set
        return _mock_coral_sql(args, evidence_acc)

    query = args.get("query", "<unknown>")
    referenced = _sources_in_query(query)
    sources_used = sorted(referenced)

    # Coral's `sql` tool takes its statement under the `sql` key, not `query`.
    call_result = await session.call_tool("sql", arguments={"sql": query})

    if call_result.isError:
        err_text = _extract_text(call_result) or "Coral returned isError=True"
        ev = Evidence(
            source="coral_error",
            table=",".join(sources_used) or "(unknown)",
            record_id=f"err_{len(evidence_acc):02d}",
            fields={"sql_error": err_text, "query": query},
            query=query,
            retrieved_at=datetime.utcnow(),
        )
        idx = len(evidence_acc)
        evidence_acc.append(ev)
        return ToolResult(
            tool_call_id="",
            status="error",
            data={
                "error": err_text,
                "hint": "SQL error from real Coral. Check column/table names "
                        "with coral_describe_table.",
                "evidence_indices": [idx],
            },
            evidence=[ev],
        )

    # Parse the result content. Coral returns rows as JSON.
    raw = _extract_text(call_result)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = {"rows": [], "_raw": raw}

    # Coral's sql tool wraps results in different shapes depending on
    # version. Normalize to a row list + column inference.
    rows: list[dict[str, Any]] = []
    cols: list[str] = []
    if isinstance(parsed, list):
        rows = [r for r in parsed if isinstance(r, dict)]
    elif isinstance(parsed, dict):
        candidate = parsed.get("rows") or parsed.get("result") or parsed.get("items")
        if isinstance(candidate, list):
            rows = [r for r in candidate if isinstance(r, dict)]
    if rows:
        cols = list(rows[0].keys())

    is_join = len(sources_used) > 1
    source_label = "coral_join" if is_join else (sources_used[0] if sources_used else "coral")
    table_label = "+".join(sources_used) if is_join else (sources_used[0] if sources_used else "(none)")

    ev = Evidence(
        source=source_label,
        table=table_label,
        record_id=f"q_{len(evidence_acc):02d}",
        fields={
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
        },
        query=query,
        retrieved_at=datetime.utcnow(),
    )
    idx = len(evidence_acc)
    evidence_acc.append(ev)

    return ToolResult(
        tool_call_id="",
        status="ok",
        data={
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "total_matches": len(rows),
            "evidence_indices": [idx],
            "sources_joined": sources_used,
        },
        is_complete=True,
        total_matches=len(rows),
        evidence=[ev],
    )


async def _real_coral_list_catalog(
    args: dict[str, Any], _ev: list[Evidence]
) -> ToolResult:
    session = get_active_coral_session()
    if session is None:
        return _mock_coral_list_catalog(args, _ev)
    # Bump limit so even a large catalog (>50 tables) comes through in one call.
    call_result = await session.call_tool("list_catalog", arguments={"limit": 200})
    raw = _extract_text(call_result)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = {"items": []}

    # Coral's list_catalog returns {"items":[...], "total":N, ...}.
    # Each item has shape:
    #   {"kind":"table", "schema_name":"stripe", "name":"stripe.disputes",
    #    "sql_reference":"stripe.disputes", "description":"...",
    #    "table":{"table_name":"disputes", ...}}
    schemas: dict[str, list[str]] = {}
    items = parsed.get("items", []) if isinstance(parsed, dict) else []
    for it in items:
        if not isinstance(it, dict):
            continue
        schema = it.get("schema_name") or it.get("schema") or it.get("source")
        table_info = it.get("table") or {}
        bare = (
            (table_info.get("table_name") if isinstance(table_info, dict) else None)
            or it.get("name", "").split(".", 1)[-1]
        )
        if schema and bare:
            schemas.setdefault(schema, []).append(bare)

    schema_list = [{"name": s, "tables": sorted(ts)} for s, ts in sorted(schemas.items())]
    return ToolResult(
        tool_call_id="",
        status="ok",
        data={"schemas": schema_list, "note": "Live catalog from real Coral."},
    )


async def _real_coral_describe(
    args: dict[str, Any], _ev: list[Evidence]
) -> ToolResult:
    session = get_active_coral_session()
    if session is None:
        return _mock_coral_describe(args, _ev)
    qname = args.get("qualified_name", "")
    if "." not in qname:
        return ToolResult(
            tool_call_id="",
            status="error",
            data={
                "error": f"qualified_name must be 'schema.table', got '{qname}'",
                "hint": "Pass e.g. 'stripe.disputes', not just 'disputes'.",
            },
        )
    schema_name, table_name = qname.split(".", 1)
    # Coral exposes describe_table + list_columns; list_columns is
    # the richer shape (per-column types).
    call_result = await session.call_tool(
        "list_columns",
        arguments={"schema": schema_name, "table": table_name},
    )
    raw = _extract_text(call_result)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = {"columns": []}
    # Coral returns {"items": [{name, data_type, ...}, ...]} or {"columns": [...]}.
    cols_raw: list[Any] = []
    if isinstance(parsed, dict):
        cols_raw = parsed.get("items") or parsed.get("columns") or []
    columns = [
        {
            "name": c.get("name") or c.get("column_name"),
            "type": c.get("type") or c.get("data_type"),
        }
        for c in cols_raw
        if isinstance(c, dict)
    ]
    return ToolResult(
        tool_call_id="",
        status="ok",
        data={"table": qname, "columns": columns, "note": "Live schema from real Coral."},
    )


# Map tool name → async real handler. The executor uses these when a
# coral session is bound via coral_session.set_active_coral_session().
REAL_CORAL_HANDLERS: dict[str, Any] = {
    "coral_sql": _real_coral_sql,
    "coral_list_catalog": _real_coral_list_catalog,
    "coral_describe_table": _real_coral_describe,
}


# ──────────────────────────────────────────────────────────────────────
# Executor: parallel reads, serial writes
# ──────────────────────────────────────────────────────────────────────


class ToolExecutor:
    """Dispatch a batch of tool calls.

    Read-only tools run in parallel via asyncio.gather. Write tools
    (none of the v0 tools are external writes - `record_finding`,
    `ask_human`, `conclude` are pure orchestration) run serially.
    """

    def __init__(self) -> None:
        # Shared per-case Evidence accumulator. The mocks append to it;
        # real Coral calls will too. Findings reference these by index.
        self.evidence: list[Evidence] = []

    async def dispatch(self, calls: list[ToolCall]) -> list[ToolResult]:
        reads: list[tuple[int, ToolCall]] = []
        writes: list[tuple[int, ToolCall]] = []
        for i, c in enumerate(calls):
            tool = tool_by_name(c.name)
            if tool is None:
                continue
            if tool.read_only:
                reads.append((i, c))
            else:
                writes.append((i, c))

        results: list[ToolResult | None] = [None] * len(calls)

        # Parallel reads
        async def run_read(idx: int, call: ToolCall) -> tuple[int, ToolResult]:
            res = await self._invoke(call)
            return idx, res

        if reads:
            read_results = await asyncio.gather(*(run_read(i, c) for i, c in reads))
            for i, r in read_results:
                results[i] = r

        # Serial writes (none of these are external in v0; this scaffold
        # is what the Action Executor will eventually become for real
        # writes like Stripe refunds - those go through a separate
        # process per the locked architecture).
        for i, c in writes:
            results[i] = await self._invoke(c)

        return [r for r in results if r is not None]

    async def _invoke(self, call: ToolCall) -> ToolResult:
        # Real Coral wins when a session is bound. Falls through to mock
        # otherwise. Non-coral tools (record_finding, ask_human, conclude)
        # are orchestration - handled by the loop directly.
        if get_active_coral_session() is not None and call.name in REAL_CORAL_HANDLERS:
            res = await REAL_CORAL_HANDLERS[call.name](call.arguments, self.evidence)
            return res.model_copy(update={"tool_call_id": call.id})

        handler = MOCK_HANDLERS.get(call.name)
        if handler is None:
            return ToolResult(
                tool_call_id=call.id,
                status="ok",
                data={"acknowledged": True, "tool": call.name},
            )
        res = handler(call.arguments, self.evidence)
        return res.model_copy(update={"tool_call_id": call.id})
