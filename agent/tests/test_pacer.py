"""Unit tests for the round pacer.

Every rule has at least one positive case (rule fires) and one negative
case (rule stays silent when its precondition isn't met). We also check
the idempotency wiring: a rule that's already fired this case (recorded
via the `nudges_fired` set) shouldn't fire again.

These tests are pure-function: no LLM, no DB, no event store. The pacer
is designed to be testable in isolation and these tests exercise that.
"""

from __future__ import annotations

from manthan_agent.pacer import (
    CaseSnapshot,
    PaceDecision,
    judge_pre_conclude,
    judge_pre_round,
    snapshot_from_events,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _stripe_snap(**overrides: object) -> CaseSnapshot:
    """Stripe-trigger-shaped snapshot. Tests override what they need."""
    defaults = dict(
        round_count=4,
        findings_count=0,
        findings_text=[],
        tool_calls=[],
        nudges_fired=set(),
        trigger_text=(
            "Stripe chargeback opened on charge ch_3Tch1L (dispute du_1Tch1O). "
            "Amount $8,400 USD."
        ),
    )
    defaults.update(overrides)
    return CaseSnapshot(**defaults)  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────
# R1 - stripe not queried
# ──────────────────────────────────────────────────────────────────────


def test_r1_fires_when_stripe_trigger_and_no_stripe_query() -> None:
    s = _stripe_snap(round_count=3, tool_calls=[
        ("coral_sql", {"query": "SELECT * FROM hubspot.companies LIMIT 5"}),
    ])
    d = judge_pre_round(s)
    assert d.kind == "nudge"
    assert d.rule_id == "R1_stripe_unqueried"


def test_r1_silent_when_stripe_already_queried() -> None:
    s = _stripe_snap(round_count=3, tool_calls=[
        ("coral_sql", {"query": "SELECT amount FROM stripe.charges WHERE id='ch_x'"}),
    ])
    d = judge_pre_round(s)
    assert d.kind == "proceed"


def test_r1_silent_when_not_a_stripe_trigger() -> None:
    s = _stripe_snap(
        round_count=3,
        trigger_text="Customer email from Maya about a duplicate invoice",
        tool_calls=[],
    )
    d = judge_pre_round(s)
    assert d.kind == "proceed"


def test_r1_silent_before_round_3() -> None:
    s = _stripe_snap(round_count=2, tool_calls=[])
    d = judge_pre_round(s)
    assert d.kind == "proceed"


# ──────────────────────────────────────────────────────────────────────
# R2 - notion not queried after findings exist
# ──────────────────────────────────────────────────────────────────────


def test_r2_fires_with_findings_but_no_notion() -> None:
    s = _stripe_snap(
        round_count=4,
        findings_count=2,
        findings_text=["finding a", "finding b"],
        tool_calls=[
            ("coral_sql", {"query": "SELECT * FROM stripe.charges WHERE id='ch_x'"}),
        ],
    )
    d = judge_pre_round(s)
    assert d.kind == "nudge"
    assert d.rule_id == "R2_notion_unqueried"


def test_r2_silent_when_notion_described() -> None:
    s = _stripe_snap(
        round_count=4,
        findings_count=2,
        findings_text=["a", "b"],
        tool_calls=[
            ("coral_sql", {"query": "SELECT * FROM stripe.charges"}),
            ("coral_describe_table", {"qualified_name": "notion.pages"}),
        ],
    )
    d = judge_pre_round(s)
    assert d.kind == "proceed"


# ──────────────────────────────────────────────────────────────────────
# R3 - redundant query
# ──────────────────────────────────────────────────────────────────────


def test_r3_fires_when_same_query_repeated() -> None:
    q = "SELECT * FROM stripe.disputes WHERE id='du_1'"
    s = _stripe_snap(
        round_count=5,
        tool_calls=[
            ("coral_sql", {"query": q}),
            ("coral_sql", {"query": q}),
        ],
    )
    d = judge_pre_round(s)
    assert d.kind == "nudge"
    assert d.rule_id == "R3_redundant_query"


def test_r3_silent_when_queries_vary() -> None:
    s = _stripe_snap(
        round_count=5,
        tool_calls=[
            ("coral_sql", {"query": "SELECT * FROM stripe.charges"}),
            ("coral_sql", {"query": "SELECT * FROM stripe.disputes"}),
        ],
    )
    d = judge_pre_round(s)
    # R2 might fire here (no notion + no findings), but R3 should not
    assert d.rule_id != "R3_redundant_query"


def test_r3_normalizes_whitespace_and_case() -> None:
    s = _stripe_snap(
        round_count=5,
        tool_calls=[
            ("coral_sql", {"query": "SELECT * FROM stripe.charges"}),
            ("coral_sql", {"query": "select  *   from  STRIPE.charges  "}),
        ],
    )
    d = judge_pre_round(s)
    assert d.rule_id == "R3_redundant_query"


# ──────────────────────────────────────────────────────────────────────
# R4 - no findings late
# ──────────────────────────────────────────────────────────────────────


def test_r4_fires_after_10_rounds_with_no_findings() -> None:
    s = _stripe_snap(
        round_count=11,
        findings_count=0,
        tool_calls=[
            ("coral_sql", {"query": "SELECT 1 FROM stripe.charges"}),
            ("coral_describe_table", {"qualified_name": "notion.pages"}),
        ],
    )
    d = judge_pre_round(s)
    assert d.kind == "nudge"
    assert d.rule_id == "R4_no_findings_late"


def test_r4_silent_with_any_finding() -> None:
    s = _stripe_snap(
        round_count=11,
        findings_count=1,
        findings_text=["something useful"],
        tool_calls=[
            ("coral_sql", {"query": "SELECT 1 FROM stripe.charges"}),
            ("coral_describe_table", {"qualified_name": "notion.pages"}),
        ],
    )
    d = judge_pre_round(s)
    # R1/R2 won't fire here (stripe queried, notion described). R4 shouldn't either.
    assert d.kind == "proceed"


def test_r4_silent_before_threshold() -> None:
    """R4 must not fire during the legitimate exploratory phase."""
    s = _stripe_snap(
        round_count=8,
        findings_count=0,
        tool_calls=[
            ("coral_sql", {"query": "SELECT 1 FROM stripe.charges"}),
            ("coral_describe_table", {"qualified_name": "notion.pages"}),
        ],
    )
    d = judge_pre_round(s)
    assert d.kind == "proceed"


# ──────────────────────────────────────────────────────────────────────
# R5/R6 - round budget
# ──────────────────────────────────────────────────────────────────────


def test_r5_wrap_up_when_budget_exceeded_with_findings() -> None:
    s = _stripe_snap(
        round_count=22,
        findings_count=3,
        findings_text=["a", "b", "c"],
    )
    d = judge_pre_round(s, max_rounds=20)
    assert d.kind == "wrap_up"
    assert d.rule_id == "R5_round_budget_wrap"


def test_r6_halt_when_budget_exceeded_with_no_findings() -> None:
    s = _stripe_snap(round_count=22, findings_count=0)
    d = judge_pre_round(s, max_rounds=20)
    assert d.kind == "halt"
    assert d.rule_id == "R6_round_budget_halt"


def test_round_budget_silent_at_realistic_turn_counts() -> None:
    """The default max_rounds (100) should never halt a normal run."""
    s = _stripe_snap(round_count=60, findings_count=2, findings_text=["a", "b"])
    d = judge_pre_round(s)
    # R5/R6 shouldn't fire at 60 turns with default max_rounds=100
    assert d.rule_id not in ("R5_round_budget_wrap", "R6_round_budget_halt")


# ──────────────────────────────────────────────────────────────────────
# Idempotency - a rule that's already fired stays silent
# ──────────────────────────────────────────────────────────────────────


def test_already_fired_rule_does_not_refire() -> None:
    # R1 would fire here on a fresh snapshot - but it's in nudges_fired.
    s = _stripe_snap(
        round_count=3,
        tool_calls=[],
        nudges_fired={"R1_stripe_unqueried"},
    )
    d = judge_pre_round(s)
    assert d.rule_id != "R1_stripe_unqueried"


# ──────────────────────────────────────────────────────────────────────
# C1 - pre-conclude refund-needs-math
# ──────────────────────────────────────────────────────────────────────


def test_c1_blocks_refund_without_math_finding() -> None:
    s = _stripe_snap(
        findings_count=2,
        findings_text=[
            "Stripe charge ch_x for $8,400 on 2026-04-12",
            "Customer downgraded plan after the cycle",
        ],
    )
    d = judge_pre_conclude(s, {
        "decision_action": "refund",
        "decision_amount_minor": 56000,
    })
    assert d.kind == "nudge"
    assert d.rule_id == "C1_refund_math_missing"


def test_c1_allows_refund_when_math_is_in_a_finding() -> None:
    s = _stripe_snap(
        findings_count=2,
        findings_text=[
            "Datadog INC-2026-04-13 shows 2-day degradation on Custom Reports",
            "Per documented-incident policy: 2/30 × $8,400 = $560 pro-rata credit",
        ],
    )
    d = judge_pre_conclude(s, {
        "decision_action": "refund",
        "decision_amount_minor": 56000,
    })
    assert d.kind == "proceed"


def test_c1_allows_non_refund_decisions() -> None:
    s = _stripe_snap(findings_count=1, findings_text=["evidence of legitimate use"])
    d = judge_pre_conclude(s, {
        "decision_action": "fight",
        "decision_amount_minor": 0,
    })
    assert d.kind == "proceed"


def test_c1_does_not_loop_forever() -> None:
    """If C1 already fired once for this case, let the next conclude
    through to avoid pinging the model in a loop it can't escape."""
    s = _stripe_snap(
        findings_count=2,
        findings_text=["bare finding 1", "bare finding 2"],
        nudges_fired={"C1_refund_math_missing"},
    )
    d = judge_pre_conclude(s, {
        "decision_action": "refund",
        "decision_amount_minor": 56000,
    })
    assert d.kind == "proceed"


# ──────────────────────────────────────────────────────────────────────
# snapshot_from_events - mini integration
# ──────────────────────────────────────────────────────────────────────


class _FakeEvent:
    """Minimal Event lookalike so we don't depend on state.py here."""

    def __init__(self, kind: str, data: dict[str, object]) -> None:
        self.kind = kind
        self.data = data


def test_snapshot_captures_tool_calls_findings_and_recovers_nudges() -> None:
    """round_count is owned by the caller (the loop tracks actual LLM
    turn count via budget.steps), so we pass it explicitly. The
    snapshot still collects tool calls, findings, and fired nudge ids
    from the event log."""
    events = [
        _FakeEvent("case_opened", {}),
        _FakeEvent("tool_call", {"name": "coral_sql", "arguments": {"query": "SELECT 1"}}),
        _FakeEvent("tool_result", {"tool_call_id": "1", "result": {}}),
        _FakeEvent("tool_call", {"name": "record_finding", "arguments": {}}),
        _FakeEvent("finding_recorded", {"text": "x", "idx": 0, "confidence": 0.9}),
        _FakeEvent("agent_thought", {"text": "[pacer] R1...", "pacer_rule_id": "R1_stripe_unqueried"}),
    ]
    snap = snapshot_from_events(events, trigger_text="ch_x", round_count=2)
    assert snap.round_count == 2
    assert snap.findings_count == 1
    assert len(snap.tool_calls) == 2
    assert "R1_stripe_unqueried" in snap.nudges_fired
    assert snap.trigger_text == "ch_x"


def test_snapshot_round_count_defaults_to_zero_when_unspecified() -> None:
    """No round_count argument -> 0. Pacer rules guarded by round_count
    minimums will simply stay silent."""
    snap = snapshot_from_events([], trigger_text="anything")
    assert snap.round_count == 0


def test_pace_decision_proceed_constructor() -> None:
    d = PaceDecision.proceed()
    assert d.kind == "proceed"
    assert d.rule_id == ""
