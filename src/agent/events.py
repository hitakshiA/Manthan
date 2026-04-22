"""SSE event types for streaming agent output to Layer 3.

Every decision point in the agent loop emits an event. Layer 3
renders these as a live activity feed — the user sees exactly
what the agent is doing, thinking, and waiting on at all times.

The alias-catalog context variable lets each /agent/query request
install its own physical-name → business-name mapping. Event
factories that render agent-written SQL (``tool_start``,
``tool_complete``, ``sql_result``) consult it so
``gold_orders_16b49dbd39_by_status`` renders as ``orders.by_status``
in the exec's thinking timeline.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel

from src.agent.aliasing import AliasCatalog

# Per-request alias catalog. Set by the agent loop at session_start
# and reset at session end. Using a ContextVar (not a module-level
# global) so concurrent /agent/query requests don't trample each
# other's mappings.
_alias_catalog: ContextVar[AliasCatalog | None] = ContextVar(
    "manthan_alias_catalog", default=None
)


def set_alias_catalog(catalog: AliasCatalog | None) -> object:
    """Install a catalog for the current request; returns a token to reset."""
    return _alias_catalog.set(catalog)


def reset_alias_catalog(token: object) -> None:
    """Restore the previous catalog (pair with :func:`set_alias_catalog`)."""
    _alias_catalog.reset(token)  # type: ignore[arg-type]


_EMPTY_LINK_MD = re.compile(r"\[([^\]\n]+)\]\(\)")
_SCRIPT_TAG_RE = re.compile(
    r"(<script\b[^>]*>)(.*?)(</script>)",
    re.IGNORECASE | re.DOTALL,
)


def _mask(text: str) -> str:
    """Apply the active alias catalog to ``text``, if any is set."""
    catalog = _alias_catalog.get()
    if catalog is None:
        return text
    return catalog.mask(text)


def _strip_empty_link_md(text: str) -> str:
    """Remove ``[value]()`` stubs from HTML bodies.

    The agent is instructed to wrap every cited number in empty-href
    markdown so ``NarrativeBlock`` can attach a click-to-audit drawer
    in the conversation stream. That preprocessor never runs inside
    ``emit_visual`` or ``artifact`` HTML (those render in iframes),
    so any surviving ``[70.9%]()`` would render as literal brackets
    to the exec. Strip them here — the iframe gets clean text.
    """
    return _EMPTY_LINK_MD.sub(lambda m: m.group(1), text)


def _close_unclosed_try(code: str) -> str:
    """Auto-heal unclosed ``try {`` blocks in inline ``<script>`` tags.

    Agents were instructed historically to "wrap the whole script in
    try/catch" and a subset of them produce ``<script>try { ... ; } ...
    </script>`` without the matching ``catch`` clause. That's a
    ``SyntaxError`` → nothing executes → every dashboard tile renders
    blank. We scan the top of each inline script; if we see a bare
    ``try {`` and the brace count is positive (i.e. the block never
    balanced + no ``catch``/``finally`` appears), we append the
    minimum closing ``} catch(e){console.error(e);}`` before
    ``</script>``. Defense-in-depth for an instruction that was
    removed from the prompt.
    """

    def _fix_script(match: re.Match[str]) -> str:
        head, body, tail = match.group(1), match.group(2), match.group(3)
        # Bail if there's no bare top-level ``try {``
        if not re.search(r"(^|\s)try\s*\{", body):
            return match.group(0)
        # Bail if a catch/finally clause exists in the same script
        if re.search(r"\}\s*(catch|finally)\b", body):
            return match.group(0)
        # Quick brace count — string/comment literals may throw off the
        # math, so only act when the mismatch is unambiguous (>0).
        opens = body.count("{")
        closes = body.count("}")
        if opens <= closes:
            return match.group(0)
        missing = opens - closes
        # ``} catch (e) {...}`` contributes net +1 close. Any remaining
        # imbalance (deeper unclosed blocks) gets bare ``}`` appended so
        # the script at least parses; the catch will swallow runtime
        # errors inside the outer try.
        extra = "}" * max(0, missing - 1)
        patch = "\n} catch (e) { console.error(e); }" + extra + "\n"
        return head + body + patch + tail

    return _SCRIPT_TAG_RE.sub(_fix_script, code)


class AgentEvent(BaseModel):
    """One SSE event emitted during the agent loop."""

    type: str
    data: dict[str, Any]

    def to_sse(self) -> str:
        return f"data: {json.dumps({'type': self.type, **self.data})}\n\n"


# ── Lifecycle events ──


def session_start(session_id: str, dataset_id: str, model: str) -> AgentEvent:
    return AgentEvent(
        type="session_start",
        data={
            "session_id": session_id,
            "dataset_id": dataset_id,
            "model": model,
        },
    )


def done(
    summary: str,
    turns: int,
    tool_calls: int = 0,
    elapsed: float = 0.0,
    mode: str | None = None,
) -> AgentEvent:
    return AgentEvent(
        type="done",
        data={
            "summary": summary[:2000],
            "turns": turns,
            "tool_calls": tool_calls,
            "elapsed_seconds": round(elapsed, 2),
            "mode": mode,
        },
    )


def error(message: str, recoverable: bool = True) -> AgentEvent:
    return AgentEvent(
        type="error",
        data={"message": message[:500], "recoverable": recoverable},
    )


# ── Discovery events (before the loop starts) ──


def discovering_tables(dataset_id: str) -> AgentEvent:
    return AgentEvent(
        type="discovering_tables",
        data={"dataset_id": dataset_id, "status": "scanning"},
    )


def tables_found(table_names: list[str], total: int) -> AgentEvent:
    return AgentEvent(
        type="tables_found",
        data={
            "tables": table_names[:20],
            "total": total,
        },
    )


def loading_schema(dataset_id: str) -> AgentEvent:
    return AgentEvent(
        type="loading_schema",
        data={"dataset_id": dataset_id},
    )


def checking_memory(dataset_id: str) -> AgentEvent:
    return AgentEvent(
        type="checking_memory",
        data={"dataset_id": dataset_id},
    )


def memory_found(count: int) -> AgentEvent:
    return AgentEvent(
        type="memory_found",
        data={"prior_analyses": count},
    )


# ── Thinking events ──


def thinking(text: str) -> AgentEvent:
    return AgentEvent(
        type="thinking",
        data={"text": text[:500]},
    )


def deciding_gate(gate: str, decision: str, reason: str) -> AgentEvent:
    """Agent passed through a decision gate."""
    return AgentEvent(
        type="deciding",
        data={
            "gate": gate,
            "decision": decision,
            "reason": reason[:200],
        },
    )


# ── Tool events ──


def tool_start(name: str, args: dict[str, Any], turn: int) -> AgentEvent:
    return AgentEvent(
        type="tool_start",
        data={
            "tool": name,
            "turn": turn,
            "args_preview": _mask(_preview_args(name, args)),
        },
    )


def tool_complete(name: str, preview: str, elapsed_ms: float) -> AgentEvent:
    return AgentEvent(
        type="tool_complete",
        data={
            "tool": name,
            "preview": _mask(preview[:400]),
            "elapsed_ms": round(elapsed_ms, 1),
        },
    )


def tool_error(name: str, error_msg: str, will_retry: bool) -> AgentEvent:
    return AgentEvent(
        type="tool_error",
        data={
            "tool": name,
            "error": error_msg[:300],
            "will_retry": will_retry,
        },
    )


# ── Human-in-the-loop events ──


def waiting_for_user(
    question_id: str,
    prompt: str,
    options: list[str],
    interpretation: str | None = None,
    why: str | None = None,
    ambiguity_type: str | None = None,
) -> AgentEvent:
    data: dict[str, Any] = {
        "question_id": question_id,
        "prompt": _mask(prompt[:500]),
        "options": [_mask(o) for o in options[:10]],
    }
    if interpretation:
        data["interpretation"] = _mask(interpretation[:400])
    if why:
        data["why"] = _mask(why[:400])
    if ambiguity_type:
        data["ambiguity_type"] = ambiguity_type
    return AgentEvent(type="waiting_for_user", data=data)


def user_answered(answer: str) -> AgentEvent:
    return AgentEvent(
        type="user_answered",
        data={"answer": answer[:300]},
    )


# ── Plan events ──


def plan_created(plan_id: str, interpretation: str, steps: int) -> AgentEvent:
    return AgentEvent(
        type="plan_created",
        data={
            "plan_id": plan_id,
            "interpretation": _mask(interpretation[:300]),
            "steps": steps,
        },
    )


def plan_pending(plan_id: str, interpretation: str) -> AgentEvent:
    return AgentEvent(
        type="plan_pending",
        data={
            "plan_id": plan_id,
            "interpretation": _mask(interpretation[:500]),
        },
    )


def plan_approved(plan_id: str) -> AgentEvent:
    return AgentEvent(
        type="plan_approved",
        data={"plan_id": plan_id},
    )


# ── Progress events ──


def progress(step: int, total: int, description: str) -> AgentEvent:
    return AgentEvent(
        type="progress",
        data={
            "step": step,
            "total": total,
            "description": description[:200],
        },
    )


def turn_complete(turn: int, tools_used: list[str]) -> AgentEvent:
    return AgentEvent(
        type="turn_complete",
        data={"turn": turn, "tools_used": tools_used},
    )


# ── Subagent events ──


def subagent_spawned(subagent_id: str, task: str) -> AgentEvent:
    return AgentEvent(
        type="subagent_spawned",
        data={
            "subagent_id": subagent_id,
            "task": task[:200],
        },
    )


def subagent_complete(subagent_id: str, result_preview: str) -> AgentEvent:
    return AgentEvent(
        type="subagent_complete",
        data={
            "subagent_id": subagent_id,
            "result": result_preview[:300],
        },
    )


# ── Conversation stream events ──


def sql_result(
    tool_call_id: str,
    query: str,
    columns: list[str],
    rows: list[list[Any]],
    row_count: int,
    truncated: bool,
    elapsed_ms: float,
) -> AgentEvent:
    """Emitted after every successful run_sql so the UI shows the result inline."""
    return AgentEvent(
        type="sql_result",
        data={
            "tool_call_id": tool_call_id,
            "query": _mask(query[:500]),
            "columns": columns,
            "rows": rows[:20],  # first 20 rows for inline preview
            "row_count": row_count,
            "truncated": truncated or row_count > 20,
            "elapsed_ms": round(elapsed_ms, 1),
        },
    )


def narrative(text: str) -> AgentEvent:
    """Agent's out-loud commentary — shown as bold text between thinking groups.

    Masked through the active AliasCatalog so the exec never sees
    physical table names (``gold_orders_16b49dbd39``) inside the agent's
    own prose — only the business slug/name.
    """
    return AgentEvent(
        type="narrative",
        data={"text": _mask(text[:6000])},
    )


def inline_visual(
    visual_id: str,
    visual_type: str,
    html: str,
    height: int = 200,
) -> AgentEvent:
    """Small inline HTML visual rendered in the conversation stream."""
    return AgentEvent(
        type="inline_visual",
        data={
            "visual_id": visual_id,
            "visual_type": visual_type,
            "html": _strip_empty_link_md(_mask(html)),
            "height": height,
        },
    )


def artifact_created(
    artifact_id: str,
    title: str,
    code: str,
    filename: str,
) -> AgentEvent:
    """A self-contained HTML artifact (dashboard, report, interactive tool).

    Title + HTML body are masked through the active AliasCatalog —
    any ``gold_orders_16b49dbd39`` that sneaks into embedded SQL or
    display text is rewritten to the business slug before the artifact
    reaches the exec's screen.
    """
    return AgentEvent(
        type="artifact_created",
        data={
            "artifact_id": artifact_id,
            "title": _mask(title[:200]),
            "code": _close_unclosed_try(_strip_empty_link_md(_mask(code))),
            "filename": filename,
        },
    )


def _format_variants(value: float | int, unit: str | None) -> list[str]:
    """Generate plausible string forms the agent might use in prose.

    The narrative preprocessor matches these against the rendered text
    to attach the audit drawer. We cast a wide net: raw int, comma
    form, abbreviated scales ($706K / $0.7M), bare abbreviations
    (706K), percent forms. Duplicates get de-duped at the consumer.
    """
    if value is None:
        return []
    out: list[str] = []
    unit_l = (unit or "").lower()
    absval = abs(value)
    sign = "-" if value < 0 else ""

    is_money = unit_l in {"usd", "eur", "gbp", "inr", "cad", "aud"}
    is_percent = unit_l in {"percent", "%"}

    def _scaled(prefix: str) -> list[str]:
        vs: list[str] = []
        if absval >= 1_000_000_000:
            n = absval / 1_000_000_000
            vs.append(f"{sign}{prefix}{n:.1f}B")
            vs.append(f"{sign}{prefix}{n:.2f}B")
            vs.append(f"{sign}{prefix}{round(n)}B")
        if absval >= 1_000_000:
            n = absval / 1_000_000
            vs.append(f"{sign}{prefix}{n:.1f}M")
            vs.append(f"{sign}{prefix}{n:.2f}M")
            vs.append(f"{sign}{prefix}{round(n)}M")
        if absval >= 1_000:
            n = absval / 1_000
            vs.append(f"{sign}{prefix}{n:.1f}K")
            vs.append(f"{sign}{prefix}{n:.2f}K")
            vs.append(f"{sign}{prefix}{round(n)}K")
        return vs

    if is_money:
        out.extend(_scaled("$"))
        out.append(f"{sign}${absval:,.2f}")
        out.append(f"{sign}${absval:,.0f}")
        out.append(f"{sign}${int(absval)}")
    elif is_percent:
        out.append(f"{value:.0f}%")
        out.append(f"{value:.1f}%")
        out.append(f"{value:.2f}%")
    else:
        # Numeric — emit both bare and common suffix forms. Many
        # dataset numeric columns represent dollars without a unit
        # column (e.g. gov-finance Totals.Revenue), so $ forms widen
        # the audit net without harming non-money cases (narrative
        # simply won't contain those variants).
        out.extend(_scaled(""))
        out.extend(_scaled("$"))
        if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
            out.append(f"{int(absval):,}")
            out.append(f"{int(absval)}")
        else:
            out.append(f"{absval:,.2f}")
            out.append(f"{absval:.2f}")
            out.append(f"{absval:.1f}")

    # De-dup while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def numeric_claim(
    *,
    value: float | int,
    formatted: str,
    label: str,
    description: str | None = None,
    entity: str | None = None,
    metric_ref: str | None = None,
    filters_applied: list[str] | None = None,
    dimensions: list[str] | None = None,
    grain: str | None = None,
    sql: str | None = None,
    row_count_scanned: int | None = None,
    run_id: str | None = None,
    unit: str | None = None,
) -> AgentEvent:
    """Structured lineage event paired with every exec-facing number.

    The UI underlines the ``formatted`` value in the narrative and
    opens a drawer when clicked. The drawer shows the metric
    definition (if known) + filters + SQL + scanned rows + run_id,
    giving the exec a one-click audit path from "$706K" back to the
    exact query that produced it.

    ``description`` is a plain-English one-liner the drawer renders
    as "What this measures" — sourced from the DCD metric's
    ``description`` field when the claim came from ``compute_metric``,
    or generated from the SQL when it came from ``run_sql``.

    ``formatted_variants`` widens the matcher — the same raw value
    may be rendered as ``$706K``, ``$0.7M``, or ``706,532``; the UI
    tries all of them so the click-to-audit underline survives a
    format mismatch between tool output and prose.
    """
    variants = _format_variants(value, unit)
    # Ensure the primary formatted string is always in the list first
    if formatted and formatted not in variants:
        variants = [formatted, *variants]
    elif formatted:
        variants = [formatted] + [v for v in variants if v != formatted]
    return AgentEvent(
        type="numeric_claim",
        data={
            "value": value,
            "formatted": formatted,
            "formatted_variants": variants,
            "label": label,
            "description": _mask(description) if description else None,
            "entity": entity,
            "metric_ref": metric_ref,
            # Filter strings often embed physical table names via
            # subqueries (``"Year" = (SELECT MAX("Year") FROM
            # gold_finance_5f55e55ccb)``); mask each before the drawer
            # shows them in natural language.
            "filters_applied": [_mask(f) for f in (filters_applied or [])],
            "dimensions": list(dimensions or []),
            "grain": grain,
            "sql": _mask(sql[:2000]) if sql else None,
            "row_count_scanned": row_count_scanned,
            "run_id": run_id,
        },
    )


def artifact_updated(
    artifact_id: str,
    title: str,
    code: str,
    filename: str,
) -> AgentEvent:
    """Updated version of an existing artifact."""
    return AgentEvent(
        type="artifact_updated",
        data={
            "artifact_id": artifact_id,
            "title": _mask(title[:200]),
            "code": _close_unclosed_try(_strip_empty_link_md(_mask(code))),
            "filename": filename,
        },
    )


def building_artifact(artifact_id: str, title: str, filename: str) -> AgentEvent:
    """Emitted IMMEDIATELY when ``create_artifact`` starts — before
    validation, repair, or disk write. The UI opens the artifact panel
    with a skeleton state so the exec sees work-in-progress instead of
    a silent 30s-3m gap while ``node --check`` and the repair LLM run."""
    return AgentEvent(
        type="building_artifact",
        data={
            "artifact_id": artifact_id,
            "title": _mask(title[:200]),
            "filename": filename,
        },
    )


def repairing_artifact(artifact_id: str, reason: str) -> AgentEvent:
    """Emitted when the validator caught a JS parse error in a fresh
    artifact and a single-shot LLM repair pass is in flight. UI shows a
    subtle "Polishing dashboard…" banner; the follow-up
    ``artifact_updated`` (or ``artifact_created`` with the fixed code)
    replaces it."""
    return AgentEvent(
        type="repairing_artifact",
        data={
            "artifact_id": artifact_id,
            "reason": reason[:300],
        },
    )


# ── Helpers ──


def _preview_args(name: str, args: dict[str, Any]) -> str:
    """Human-readable preview of tool arguments.

    For ``run_sql`` / ``run_python`` we return the FULL code (capped at
    6 KB) so the UI's expandable Script block can render it. The UI
    gates the reveal behind a click, so shipping more text up-front
    costs nothing at rest.
    """
    if name == "run_sql":
        return args.get("sql", "")[:6000]
    if name == "run_python":
        return args.get("code", "")[:6000]
    if name == "compute_metric":
        entity = args.get("entity", "?")
        metric = args.get("metric", "?")
        pieces = [f"{entity}.{metric}"]
        dims = args.get("dimensions") or []
        if dims:
            pieces.append("by " + ", ".join(dims))
        grain = args.get("grain")
        if grain:
            pieces.append(f"({grain})")
        filters = args.get("filters") or {}
        if filters:
            pieces.append("filters=" + json.dumps(filters)[:80])
        return " ".join(pieces)[:200]
    if name == "ask_user":
        return args.get("prompt", "")[:150]
    if name == "create_plan":
        return args.get("interpretation", "")[:150]
    if name == "emit_visual":
        return f"Showing: {args.get('visual_type', 'visual')}"
    if name == "create_artifact":
        return f"Creating: {args.get('title', 'artifact')}"
    return json.dumps(args)[:150]
