"""Policy engine - evaluates rules against a case to decide auto vs HITL.

After a brief drops, the investigate worker calls `evaluate_for_case()`. We
walk enabled rules in priority order, evaluate conditions, return the first
match (if any). If the match has mode=auto, the worker skips
awaiting_approval and lets the actor fire the drafted actions immediately.

Rule conditions use a small JSON DSL:

  {"all": [<clause>, <clause>, ...]}    -- AND
  {"any": [<clause>, <clause>, ...]}    -- OR
  {"not": <clause>}                     -- NOT

A clause is `{field_path: {op: value}}`, e.g.
  {"case.amount_minor": {"lte": 20000}}
  {"case.case_type": {"in": ["refund_request", "duplicate_charge"]}}
  {"case.trigger_surface": {"eq": "email"}}
  {"case.decision_action": {"eq": "refund"}}
  {"customer.has_prior_disputes": {"eq": false}}

Supported ops: eq, ne, lt, lte, gt, gte, in, not_in.

Field paths resolve against a flat context dict built by
`build_context_for_case()`. New paths = new key in that builder.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from manthan_api.db import get_pool

logger = logging.getLogger("services.policy")


@dataclass
class PolicyMatch:
    rule_id: UUID
    rule_name: str
    mode: str             # auto | recommend | hitl
    decision: dict[str, Any]
    snapshot: dict[str, Any]


# ──────────────────────────────────────────────────────────────────────
# Public entry: evaluate for a case
# ──────────────────────────────────────────────────────────────────────


async def evaluate_for_case(org_id: UUID, case_id: UUID) -> PolicyMatch | None:
    """Return the first matching rule for the case, or None."""
    ctx = await build_context_for_case(org_id, case_id)
    if ctx is None:
        return None

    async with get_pool().acquire() as conn:
        rules = await conn.fetch(
            """
            SELECT id, name, conditions, decision
            FROM policy_rules
            WHERE org_id = $1 AND enabled = TRUE
            ORDER BY priority ASC, created_at ASC
            """,
            org_id,
        )

    for r in rules:
        conditions = r["conditions"]
        if isinstance(conditions, str):
            conditions = json.loads(conditions)
        decision = r["decision"]
        if isinstance(decision, str):
            decision = json.loads(decision)
        try:
            if _evaluate_clause(conditions or {}, ctx):
                logger.info("policy MATCH: rule=%s case=%s mode=%s",
                            r["name"], case_id, decision.get("mode"))
                # Record the match.
                snapshot = {k: v for k, v in ctx.items() if not k.startswith("_")}
                async with get_pool().acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO policy_matches (org_id, case_id, rule_id, mode, snapshot)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        org_id, case_id, r["id"],
                        decision.get("mode", "recommend"),
                        json.dumps(snapshot, default=str),
                    )
                return PolicyMatch(
                    rule_id=r["id"],
                    rule_name=r["name"],
                    mode=decision.get("mode", "recommend"),
                    decision=decision,
                    snapshot=snapshot,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("rule %s eval failed: %s", r["name"], e)
            continue

    return None


# ──────────────────────────────────────────────────────────────────────
# Context builder
# ──────────────────────────────────────────────────────────────────────


async def build_context_for_case(org_id: UUID, case_id: UUID) -> dict[str, Any] | None:
    """Pull case + customer state into a flat dict for clause evaluation."""
    async with get_pool().acquire() as conn:
        case = await conn.fetchrow(
            """
            SELECT short_id, status, trigger_surface, case_type, customer_ref,
                   amount_minor, currency, decision_action,
                   decision_amount_minor, decision_confidence,
                   trigger_payload, created_at
            FROM cases WHERE org_id=$1 AND id=$2
            """,
            org_id, case_id,
        )
        if case is None:
            return None
        findings_count = await conn.fetchval(
            "SELECT COUNT(*) FROM findings WHERE case_id=$1",
            case_id,
        )
        # "Prior disputes" check: any closed cases for the same customer_ref
        # that were chargebacks.
        prior_disputes = 0
        if case["customer_ref"]:
            prior_disputes = await conn.fetchval(
                """
                SELECT COUNT(*) FROM cases
                WHERE org_id = $1
                  AND customer_ref = $2
                  AND id != $3
                  AND case_type = 'chargeback'
                  AND status IN ('resolved', 'errored', 'acting')
                """,
                org_id, case["customer_ref"], case_id,
            ) or 0
        # Age of case in days (typically 0 for fresh)
        from datetime import datetime, timezone
        age_days = max(
            0,
            int((datetime.now(timezone.utc) - case["created_at"]).total_seconds() / 86400),
        )

    # Derived: did the agent draft a partial refund (less than the
    # disputed amount, but greater than zero)?  This is the shape of a
    # pro-rata credit decision, and the documented-incident-prorata
    # policy keys off it.
    is_partial_refund = False
    if (
        case["decision_action"] == "refund"
        and case["decision_amount_minor"] is not None
        and case["amount_minor"] is not None
        and 0 < case["decision_amount_minor"] < case["amount_minor"]
    ):
        is_partial_refund = True

    return {
        "case.short_id": case["short_id"],
        "case.status": case["status"],
        "case.trigger_surface": case["trigger_surface"],
        "case.case_type": case["case_type"],
        "case.amount_minor": case["amount_minor"],
        "case.currency": case["currency"],
        "case.decision_action": case["decision_action"],
        "case.decision_amount_minor": case["decision_amount_minor"],
        "case.decision_confidence": float(case["decision_confidence"]) if case["decision_confidence"] is not None else None,
        "case.is_partial_refund": is_partial_refund,
        "case.age_days": age_days,
        "case.findings_count": findings_count,
        "customer.ref": case["customer_ref"],
        "customer.has_prior_disputes": prior_disputes > 0,
        "customer.prior_dispute_count": prior_disputes,
    }


# ──────────────────────────────────────────────────────────────────────
# DSL evaluator
# ──────────────────────────────────────────────────────────────────────


def _evaluate_clause(clause: dict[str, Any], ctx: dict[str, Any]) -> bool:
    if not isinstance(clause, dict):
        return False
    if "all" in clause:
        return all(_evaluate_clause(c, ctx) for c in clause["all"])
    if "any" in clause:
        return any(_evaluate_clause(c, ctx) for c in clause["any"])
    if "not" in clause:
        return not _evaluate_clause(clause["not"], ctx)

    # Leaf clause: {field_path: {op: value}}
    for field, predicate in clause.items():
        if not isinstance(predicate, dict):
            return False
        actual = ctx.get(field)
        for op, expected in predicate.items():
            if not _op(op, actual, expected):
                return False
    return True


def _op(op: str, actual: Any, expected: Any) -> bool:
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "lt":
        return actual is not None and actual < expected
    if op == "lte":
        return actual is not None and actual <= expected
    if op == "gt":
        return actual is not None and actual > expected
    if op == "gte":
        return actual is not None and actual >= expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "exists":
        return (actual is not None) == bool(expected)
    return False
