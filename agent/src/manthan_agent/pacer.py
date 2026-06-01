# mypy: strict
"""Round-level policy auditor for the investigate loop.

The agent's own LLM is the brain. This module is the *pacer* — a
narrow set of rules that watch the running state of a case and step in
when the brain looks like it's about to stall, loop, or finalize on
shaky ground.

Why factor it out (instead of stuffing more bullets into the system
prompt):
  - The prompt is read once per round; rules in the prompt can't observe
    cross-round state ("did stripe ever get queried?" or "is this the
    third identical query?"). The pacer can.
  - We want each rule individually testable without spinning up an LLM.
  - Money-moving cases need stronger pre-conclude invariants than a
    read-only investigator does. The pacer is the place we encode them.

Design rules:
  - Pure. No I/O. No LLM calls. Inputs in, decision out.
  - Idempotent: each rule fires at most once per case. The caller passes
    the already-fired rule ids so we never spam the same nudge twice.
  - Manthan-specific. The rules reference our actual tool names
    (`coral_sql`, `record_finding`, `conclude`) and our actual case
    shape (decision_action, decision_amount_minor). Read-only audit
    tools have different rules and live elsewhere.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

# Public verdict the loop acts on.
PaceKind = Literal["proceed", "nudge", "wrap_up", "halt"]


@dataclass(frozen=True)
class PaceDecision:
    """What the pacer wants the loop to do this round."""

    kind: PaceKind
    rule_id: str = ""
    message: str = ""
    reason: str = ""

    @classmethod
    def proceed(cls) -> PaceDecision:
        return cls(kind="proceed")


@dataclass
class CaseSnapshot:
    """Lightweight projection of case state. The loop builds this from
    its event log + in-memory findings; the pacer reads only what's here.

    Keeping a tight projection (instead of accepting the event store) is
    deliberate — the pacer stays trivially testable and the dependency
    on the loop's internals is just this dataclass.
    """

    round_count: int
    findings_count: int
    findings_text: list[str] = field(default_factory=list)
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    nudges_fired: set[str] = field(default_factory=set)
    trigger_text: str = ""

    # ---- helpers the rules below read through ----

    def coral_queries(self) -> list[str]:
        """Every raw SQL string the agent has issued so far."""
        out: list[str] = []
        for name, args in self.tool_calls:
            if name == "coral_sql":
                q = args.get("query")
                if isinstance(q, str):
                    out.append(q)
        return out

    def queried_source(self, source_prefix: str) -> bool:
        """Has the agent touched any table whose qualified name starts
        with `source_prefix.` (e.g. 'stripe', 'notion')? Looks both at
        raw SQL queries and describe_table / list_catalog calls."""
        prefix = source_prefix.lower() + "."
        for q in self.coral_queries():
            if prefix in q.lower():
                return True
        for name, args in self.tool_calls:
            if name == "coral_describe_table":
                qn = str(args.get("qualified_name", "")).lower()
                if qn.startswith(prefix):
                    return True
        return False

    def looks_like_stripe_trigger(self) -> bool:
        """Trigger text mentions a charge/dispute id - i.e. we expect
        the agent to query stripe at some point. Used to avoid nudging
        about stripe on non-stripe triggers (e.g. inbound email)."""
        t = (self.trigger_text or "").lower()
        return ("ch_" in t) or ("du_" in t) or ("stripe" in t)


# ──────────────────────────────────────────────────────────────────────
# Rules. Each is a pure function; the caller composes them via
# `judge_pre_round` / `judge_pre_conclude` below.
# ──────────────────────────────────────────────────────────────────────


_MATH_HINT = re.compile(
    # numbers with / or * or × between them (pro-rata math); or the literal
    # words "pro-rata" / "prorated"; or a fraction-of-cycle phrasing.
    r"(\d+\s*[/*×]\s*\d+)|(pro[-\s]?rata)|(prorated)|(\d+\s*/\s*\d+\s*(day|cycle))",
    re.IGNORECASE,
)


def _r_stripe_not_queried(s: CaseSnapshot) -> PaceDecision | None:
    """R1 — the trigger references a Stripe charge/dispute but the
    agent is two rounds in without touching the stripe schema."""
    if s.round_count < 3:
        return None
    if not s.looks_like_stripe_trigger():
        return None
    if s.queried_source("stripe"):
        return None
    return PaceDecision(
        kind="nudge",
        rule_id="R1_stripe_unqueried",
        message=(
            "[pacer] You're a few rounds in but haven't queried `stripe.*` yet. "
            "The case trigger references a Stripe charge/dispute - pull "
            "stripe.charges or stripe.disputes before drawing conclusions."
        ),
        reason="stripe-shaped trigger, no stripe.* in tool history",
    )


def _r_notion_not_queried(s: CaseSnapshot) -> PaceDecision | None:
    """R2 — agent has gathered some evidence but never consulted the
    Notion knowledge base where policies live."""
    if s.round_count < 4 or s.findings_count < 2:
        return None
    if s.queried_source("notion"):
        return None
    return PaceDecision(
        kind="nudge",
        rule_id="R2_notion_unqueried",
        message=(
            "[pacer] You have findings but haven't consulted Notion. "
            "Refund/credit decisions almost always need the relevant policy "
            "page - try `coral_sql` against notion.pages or "
            "notion.page_search before concluding."
        ),
        reason="multiple findings without notion lookup",
    )


def _r_redundant_query(s: CaseSnapshot) -> PaceDecision | None:
    """R3 — the same coral_sql query (normalized whitespace + case)
    appeared two or more times in the last three calls."""
    qs = s.coral_queries()
    if len(qs) < 2:
        return None
    norm = [re.sub(r"\s+", " ", q.strip().lower()) for q in qs[-3:]]
    # any value appearing 2+ times in the tail-3 means we looped
    if len(norm) - len(set(norm)) == 0:
        return None
    return PaceDecision(
        kind="nudge",
        rule_id="R3_redundant_query",
        message=(
            "[pacer] You just re-ran a query you've already run. Either "
            "the result was sufficient (proceed) or you need a different "
            "WHERE clause / different table - don't repeat the same call."
        ),
        reason="duplicate coral_sql in last 3 calls",
    )


def _r_no_findings_late(s: CaseSnapshot) -> PaceDecision | None:
    """R4 — many rounds deep with zero findings recorded.

    Threshold set generously: the agent legitimately spends several
    turns exploring the catalog (coral_list_catalog, describe_table)
    before it has anything worth recording. Firing too early just
    derails an investigation that was on track."""
    if s.round_count < 10 or s.findings_count > 0:
        return None
    return PaceDecision(
        kind="nudge",
        rule_id="R4_no_findings_late",
        message=(
            "[pacer] You're 10 turns in without recording any findings. "
            "Use `record_finding` to capture what you've learned from "
            "the queries so far - the synthesis step needs them."
        ),
        reason="round>=10 with findings_count=0",
    )


def _r_round_budget(s: CaseSnapshot, max_rounds: int) -> PaceDecision | None:
    """R5/R6 — exceeded the round budget. If we have findings, force a
    wrap-up; if we don't, halt the case for human review."""
    if s.round_count <= max_rounds:
        return None
    if s.findings_count > 0:
        return PaceDecision(
            kind="wrap_up",
            rule_id="R5_round_budget_wrap",
            message=(
                "[pacer] You've used your round budget. Conclude on the "
                "next turn with the evidence you have. Pick the best "
                "decision_action you can support and call `conclude`."
            ),
            reason=f"round_count={s.round_count} > max_rounds={max_rounds}",
        )
    return PaceDecision(
        kind="halt",
        rule_id="R6_round_budget_halt",
        message=(
            "[pacer] Round budget exhausted and no findings recorded. "
            "Routing to human review."
        ),
        reason=f"round_count={s.round_count}>{max_rounds}, no findings",
    )


_PRE_ROUND_RULES = (
    _r_stripe_not_queried,
    _r_notion_not_queried,
    _r_redundant_query,
    _r_no_findings_late,
)


def judge_pre_round(s: CaseSnapshot, *, max_rounds: int = 100) -> PaceDecision:
    """Run all pre-round rules. Returns the first non-proceed decision
    whose rule hasn't already fired. Round-budget rule has priority over
    the nudges since halting beats nudging."""
    budget = _r_round_budget(s, max_rounds)
    if budget is not None and budget.rule_id not in s.nudges_fired:
        return budget
    for rule in _PRE_ROUND_RULES:
        d = rule(s)
        if d is None:
            continue
        if d.rule_id in s.nudges_fired:
            continue
        return d
    return PaceDecision.proceed()


# ──────────────────────────────────────────────────────────────────────
# Pre-conclude rules. These look at the conclude() arguments themselves
# and block the finalisation if a money-mover invariant fails.
# ──────────────────────────────────────────────────────────────────────


def judge_pre_conclude(
    s: CaseSnapshot, conclude_args: dict[str, Any]
) -> PaceDecision:
    """Gate the finalisation. The loop calls this right before it
    accepts a `conclude` tool call. If we return a nudge, the loop
    should append it to the event log and continue the round instead
    of writing the brief."""
    action = str(conclude_args.get("decision_action", "")).lower()
    try:
        amount_minor = int(conclude_args.get("decision_amount_minor", 0) or 0)
    except (TypeError, ValueError):
        amount_minor = 0

    # C1 - refund with a non-trivial amount but no finding shows the math.
    # A money-mover invariant: hallucinated amounts cost real money, so
    # we refuse to finalize a numeric refund unless at least one finding
    # contains the arithmetic that produced it.
    if action == "refund" and amount_minor > 0:
        rule_id = "C1_refund_math_missing"
        if rule_id in s.nudges_fired:
            # Already nudged this case once; let it through to avoid an
            # infinite ping-pong if the model can't satisfy the rule.
            return PaceDecision.proceed()
        has_math = any(_MATH_HINT.search(t or "") for t in s.findings_text)
        if not has_math:
            return PaceDecision(
                kind="nudge",
                rule_id=rule_id,
                message=(
                    f"[pacer] You're concluding with refund "
                    f"${amount_minor/100:.2f} but no finding shows how "
                    f"that number was derived. Record a finding "
                    f"containing the math (e.g. '2/30 × $8,400 = $560') "
                    f"before concluding. If the amount is a flat "
                    f"refund, record a finding stating the basis."
                ),
                reason="refund>0 without math-shaped finding text",
            )
    return PaceDecision.proceed()


# ──────────────────────────────────────────────────────────────────────
# Helper for the loop: walk the event log and pull a CaseSnapshot.
# Kept here (not in state.py) so the loop's existing event API stays
# untouched and the pacer's reading shape lives next to its rules.
# ──────────────────────────────────────────────────────────────────────


def snapshot_from_events(
    events: Iterable[Any],
    *,
    trigger_text: str = "",
    round_count: int = 0,
) -> CaseSnapshot:
    """Project the event log down to the fields the pacer reads.

    `events` is any iterable yielding Event-shaped objects (with .kind
    and .data). We don't import the Event type here so the pacer stays
    decoupled from state.py.

    `round_count` is the number of LLM turns the loop has taken so far.
    The caller (loop.py) owns this counter - we don't derive it from
    the event log because a single turn can emit multiple tool_call
    events (parallel reads) and that would inflate the count."""
    findings_text: list[str] = []
    tool_calls: list[tuple[str, dict[str, Any]]] = []
    nudges_fired: set[str] = set()

    for e in events:
        kind = getattr(e, "kind", "")
        data = getattr(e, "data", {}) or {}

        if kind == "tool_call":
            name = str(data.get("name", ""))
            args = data.get("arguments", {})
            if not isinstance(args, dict):
                try:
                    args = json.loads(args)  # defensive
                except (TypeError, ValueError, json.JSONDecodeError):
                    args = {}
            tool_calls.append((name, args))

        elif kind == "finding_recorded":
            txt = data.get("text", "")
            if isinstance(txt, str):
                findings_text.append(txt)

        elif kind == "agent_thought":
            # System-emitted thoughts are how the pacer logs its own
            # nudges; we recover fired rule ids from them.
            rule_id = data.get("pacer_rule_id")
            if isinstance(rule_id, str) and rule_id:
                nudges_fired.add(rule_id)

    return CaseSnapshot(
        round_count=round_count,
        findings_count=len(findings_text),
        findings_text=findings_text,
        tool_calls=tool_calls,
        nudges_fired=nudges_fired,
        trigger_text=trigger_text,
    )
