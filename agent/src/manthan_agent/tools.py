"""Tool registry + executor.

The agent gets a fixed toolkit. Each tool has a Pydantic-schemad input
type and a `read_only` flag that determines dispatch behavior:

  read_only = True   → run in parallel (asyncio.gather)
  read_only = False  → run serially through an idempotency queue

Every Coral tool (coral_sql, coral_list_catalog, coral_describe_table)
dispatches to the real Coral binary via the MCP session bound on
`coral_session.set_active_coral_session()`. The session is mandatory:
without it the executor raises, so config drift fails loudly instead
of silently returning fabricated rows.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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
    text: str = Field(
        description=(
            "ONE PLAIN-ENGLISH SENTENCE STATING THE CLAIM, optionally followed by "
            "the precise evidence in parentheses. This text is rendered verbatim as "
            "a numbered bullet in the case brief that a finance lead (often not an "
            "engineer) reads.\n\n"
            "SHAPE:\n"
            "  '<plain-English claim in finance language>. (<precise evidence: "
            "ids, exact numbers, system specifics>)'\n\n"
            "GOOD examples (note the plain-English lede + parenthetical evidence):\n"
            "  'The disputed charge is $8,400 for the customer's April subscription "
            "cycle. (Stripe charge ch_3Tch1L..., disputed in full via du_1Tch1O...).'\n"
            "  'Our monitoring confirms a 48-hour service outage during the billed "
            "cycle, matching the customer's claim. (Datadog monitor 20175237 "
            "documents SLA breach 2026-04-13 08:00 -> 04-15 08:00 on custom-reports-svc.)'\n"
            "  'The relevant pro-rata refund policy is on file and authoritative. "
            "(Notion page \"Documented Incident Pro-Rata Refund Credit Policy\", "
            "id 37043656-c526-...)'\n\n"
            "BAD (don't do):\n"
            "  'Stripe dispute du_1Tch1O... amount 840000 reason "
            "product_not_received/product_not_as_described status needs_response'\n"
            "  -> raw IDs and enum strings in the lede. The bullet reads like a SQL "
            "row dump, not a finding. Lead with the human claim.\n\n"
            "Tone: finance-team English. Numbers with commas ($8,400 not $8400). "
            "Don't drop raw enum strings ('product_not_as_described') into the lede - "
            "say 'cited a degraded feature' or 'cited the product was not as described' "
            "instead. Don't say system names like 'Stripe / Notion / Datadog' as the "
            "subject of the sentence - they're SOURCES of the evidence, not the SUBJECT."
        )
    )
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
    tldr: str = Field(
        description=(
            "The CFO-FACING SUMMARY of the recommendation. This is what a finance "
            "lead (often NOT an engineer) reads FIRST when they open the brief. "
            "Treat it as the opening paragraph of an internal memo.\n\n"
            "STRUCTURE (3-5 sentences total):\n"
            "  1. ONE sentence stating the recommendation: dollar amount + what "
            "     percentage of the disputed total, in plain English. Open with "
            "     'We recommend...' or the customer's name doing something, NOT "
            "     with raw IDs.\n"
            "  2. ONE-TWO sentences naming the customer, what they claimed, and "
            "     what actually happened - in finance language. Don't reference "
            "     internal system names ('Notion', 'Datadog', 'Stripe') by name; "
            "     say 'our policy docs', 'our monitoring', 'the payment provider', "
            "     'our support tool', etc.\n"
            "  3. ONE sentence showing the pro-rata math in NATURAL LANGUAGE "
            "     ('two affected days in a thirty-day cycle = $560, or roughly 7% "
            "     of the invoice'), NOT computer syntax ('(2/30)*$8400=$560').\n"
            "  4. (Optional) ONE sentence on supporting context - downgrade timing, "
            "     credit-promise history, etc.\n\n"
            "FORMATTING RULES:\n"
            "  - Money: '$8,400' (comma), never '$8400'.\n"
            "  - Math: 'two of thirty days', not '(2/30)*' or '2/30 × $8,400 = $560'.\n"
            "  - No raw enum strings: 'product_not_received/product_not_as_described' "
            "    -> 'cited a degraded feature' or 'cited that the product was not "
            "    as described'.\n"
            "  - No raw IDs in the lede ('du_1Tch1O...', 'ch_3Tch1L...', "
            "    'INC-2026-04-13-customreports'). They'll be shown as chips below "
            "    the prose; keep the prose readable.\n"
            "  - Open with a normal English sentence, NOT 'AcmeCo) disputed...' or "
            "    '(Customer Co) disputed...' - that pattern produces a chopped-"
            "    looking opener.\n"
            "  - End with a recommendation, not a peer verdict. 'We recommend "
            "    issuing the partial refund' beats 'Legitimate partial claim only'.\n\n"
            "EXAMPLE (FORMAT only - don't copy the numbers):\n"
            "  'We recommend a $X partial refund on the customer's $Y disputed "
            "  charge, roughly Z% of the invoice. The customer cited a service "
            "  issue during their billed cycle, and our monitoring confirms N hours "
            "  of degraded service during that window. Under our documented-"
            "  incident policy, the owed credit is N days in a M-day cycle, which "
            "  works out to $X. The customer downgraded their plan immediately "
            "  after the issue and filed the chargeback W weeks later, after a "
            "  promised credit was never processed.'"
        )
    )
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
            "Worked examples (FORMAT only - placeholders for shape, swap in "
            "the real ids and the amount you DERIVED from this case's evidence; "
            "don't copy the literal numbers below):\n"
            '  {"kind": "stripe_refund", "payload": {"charge_id": "ch_REAL", '
            '"amount_minor": 12300, "currency": "usd", "reason": '
            '"requested_by_customer"}, "description": "Refund $<derived> '
            'against ch_<real> - <one-line rationale>", "reversibility": '
            '"reversible"}\n'
            '  {"kind": "stripe_dispute_response", "payload": {"dispute_id": '
            '"du_REAL", "submit": true, "evidence": {"uncategorized_text": '
            '"<short narrative of the math and why the credit was issued>."}}, '
            '"description": "Concede dispute du_<real>", "reversibility": '
            '"partial"}\n'
            '  {"kind": "customer_email", "payload": {"to": '
            '"<customer email from stripe.customers>", "subject": "Update on '
            'your dispute du_<real>", "body_text": "Hi,\\n\\n<one paragraph '
            'stating the finding, the policy, the math, and the outcome>."}, '
            '"description": "Email customer about the resolution", '
            '"reversibility": "irreversible"}\n'
            '  {"kind": "hubspot_note", "payload": {"company_id": '
            '"<derived from hubspot.companies>", "body_html": "<p><strong>'
            '<case shortId> - <outcome></strong></p><p><one paragraph: amount, '
            'policy, math, decision>.</p>"}, "description": "Log resolution to '
            'HubSpot", "reversibility": "reversible"}\n'
            '  {"kind": "slack_brief", "payload": {"channel": "#billing-ops", '
            '"text": "RESOLVED · <case shortId> · <customer> · <decision> ($'
            '<amount>). <one line of context>."}, "description": "Post brief '
            'to billing-ops", "reversibility": "reversible"}'
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
# Source-name detection — every real Coral handler tags Evidence rows
# with the schemas the query touched so the brief's citation chips can
# show the right brand pill.
# ──────────────────────────────────────────────────────────────────────


_KNOWN_SOURCES: set[str] = {
    "stripe", "chargebee", "razorpay", "hubspot", "salesforce", "intercom",
    "zendesk", "slack", "notion", "confluence", "gmail", "postmark", "resend",
    "mailchimp", "loops", "twilio", "clerk", "cal", "mixpanel", "posthog",
    "sentry", "datadog", "grafana", "pagerduty", "statusgator", "launchdarkly",
    "github", "linear", "google_drive", "k8s",
}

_SOURCE_REF_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*")


def _sources_in_query(q: str) -> set[str]:
    return {
        m.group(1)
        for m in _SOURCE_REF_RE.finditer(q.lower())
        if m.group(1) in _KNOWN_SOURCES
    }



# ──────────────────────────────────────────────────────────────────────
# Coral handlers (async) — dispatch SQL / catalog / describe-table calls
# through the MCP session bound on coral_session.set_active_coral_session().
# The handlers raise RuntimeError when no session is bound so config drift
# fails loudly instead of silently returning anything synthesized.
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
        raise RuntimeError(
            "coral_sql invoked without an active Coral session. "
            "Bind one via coral_session.set_active_coral_session()."
        )

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
        raise RuntimeError(
            "coral_list_catalog invoked without an active Coral session."
        )
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
        raise RuntimeError(
            "coral_describe_table invoked without an active Coral session."
        )
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
        # Per-case Evidence accumulator. Every Coral tool call appends
        # its returned rows here; findings then reference them by index.
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
        # Coral tools dispatch through the live MCP session; the handler
        # itself raises if no session is bound, so misconfiguration fails
        # loudly. Non-coral tools (record_finding, ask_human, conclude)
        # are orchestration - the loop handles them directly, so an
        # untracked name here is just acknowledged.
        if call.name in REAL_CORAL_HANDLERS:
            res = await REAL_CORAL_HANDLERS[call.name](call.arguments, self.evidence)
            return res.model_copy(update={"tool_call_id": call.id})

        return ToolResult(
            tool_call_id=call.id,
            status="ok",
            data={"acknowledged": True, "tool": call.name},
        )
