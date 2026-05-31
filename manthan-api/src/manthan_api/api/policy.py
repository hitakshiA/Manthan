"""Policy CRUD endpoints - list rules, view match history, edit (later)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/policy", tags=["policy"])


# ──────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────


class PolicyRule(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    conditions: dict[str, Any]
    decision: dict[str, Any]
    priority: int
    enabled: bool
    match_count_90d: int = 0


class PolicyMatch(BaseModel):
    id: UUID
    case_short_id: str
    case_id: UUID
    rule_name: str
    mode: str
    matched_at: str
    decision_action: str | None = None


class CreateRulePayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    conditions: dict[str, Any]
    decision: dict[str, Any]
    priority: int = 100
    enabled: bool = True


# ──────────────────────────────────────────────────────────────────────
# GET /api/policy/rules
# ──────────────────────────────────────────────────────────────────────


@router.get("/rules", response_model=list[PolicyRule])
async def list_rules(ctx: TenantCtx = Depends(get_ctx)) -> list[PolicyRule]:
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT r.id, r.name, r.description, r.conditions, r.decision,
                   r.priority, r.enabled,
                   COALESCE((
                       SELECT COUNT(*) FROM policy_matches m
                       WHERE m.rule_id = r.id
                         AND m.matched_at > now() - interval '90 days'
                   ), 0) AS match_count_90d
            FROM policy_rules r
            WHERE r.org_id = $1
            ORDER BY r.priority ASC, r.created_at ASC
            """,
            ctx.org_id,
        )
    out = []
    for r in rows:
        conds = r["conditions"] if isinstance(r["conditions"], dict) else json.loads(r["conditions"] or "{}")
        dec = r["decision"] if isinstance(r["decision"], dict) else json.loads(r["decision"] or "{}")
        out.append(PolicyRule(
            id=r["id"], name=r["name"], description=r["description"],
            conditions=conds, decision=dec,
            priority=r["priority"], enabled=r["enabled"],
            match_count_90d=r["match_count_90d"],
        ))
    return out


# ──────────────────────────────────────────────────────────────────────
# POST /api/policy/rules  - create
# ──────────────────────────────────────────────────────────────────────


@router.post("/rules", response_model=PolicyRule, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: CreateRulePayload,
    ctx: TenantCtx = Depends(get_ctx),
) -> PolicyRule:
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO policy_rules (
                org_id, name, description, conditions, decision, priority, enabled, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, name, description, conditions, decision, priority, enabled
            """,
            ctx.org_id, body.name, body.description,
            json.dumps(body.conditions), json.dumps(body.decision),
            body.priority, body.enabled, ctx.member_id,
        )
    conds = row["conditions"] if isinstance(row["conditions"], dict) else json.loads(row["conditions"])
    dec = row["decision"] if isinstance(row["decision"], dict) else json.loads(row["decision"])
    return PolicyRule(
        id=row["id"], name=row["name"], description=row["description"],
        conditions=conds, decision=dec,
        priority=row["priority"], enabled=row["enabled"],
    )


# ──────────────────────────────────────────────────────────────────────
# GET /api/policy/matches  - recent match history
# ──────────────────────────────────────────────────────────────────────


@router.get("/matches", response_model=list[PolicyMatch])
async def list_matches(
    ctx: TenantCtx = Depends(get_ctx),
    limit: int = 50,
) -> list[PolicyMatch]:
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT m.id, m.mode, m.matched_at,
                   c.id AS case_id, c.short_id AS case_short_id,
                   c.decision_action,
                   r.name AS rule_name
            FROM policy_matches m
            JOIN cases c ON c.id = m.case_id
            JOIN policy_rules r ON r.id = m.rule_id
            WHERE m.org_id = $1
            ORDER BY m.matched_at DESC
            LIMIT $2
            """,
            ctx.org_id, limit,
        )
    return [
        PolicyMatch(
            id=r["id"],
            case_short_id=r["case_short_id"],
            case_id=r["case_id"],
            rule_name=r["rule_name"],
            mode=r["mode"],
            matched_at=r["matched_at"].isoformat(),
            decision_action=r["decision_action"],
        )
        for r in rows
    ]


# ──────────────────────────────────────────────────────────────────────
# PATCH /api/policy/rules/{id}  - toggle enabled / update priority
# ──────────────────────────────────────────────────────────────────────


class PatchRulePayload(BaseModel):
    enabled: bool | None = None
    priority: int | None = None
    name: str | None = None
    description: str | None = None
    conditions: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None


@router.patch("/rules/{rule_id}", response_model=PolicyRule)
async def patch_rule(
    rule_id: UUID,
    body: PatchRulePayload,
    ctx: TenantCtx = Depends(get_ctx),
) -> PolicyRule:
    sets: list[str] = []
    params: list[Any] = []
    if body.enabled is not None:
        sets.append(f"enabled = ${len(params) + 1}")
        params.append(body.enabled)
    if body.priority is not None:
        sets.append(f"priority = ${len(params) + 1}")
        params.append(body.priority)
    if body.name is not None:
        sets.append(f"name = ${len(params) + 1}")
        params.append(body.name)
    if body.description is not None:
        sets.append(f"description = ${len(params) + 1}")
        params.append(body.description)
    if body.conditions is not None:
        sets.append(f"conditions = ${len(params) + 1}::jsonb")
        params.append(json.dumps(body.conditions))
    if body.decision is not None:
        sets.append(f"decision = ${len(params) + 1}::jsonb")
        params.append(json.dumps(body.decision))
    if not sets:
        raise HTTPException(status_code=400, detail="no fields to update")
    sets.append("updated_at = now()")
    params.extend([ctx.org_id, rule_id])

    async with get_conn() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE policy_rules
            SET {', '.join(sets)}
            WHERE org_id = ${len(params) - 1} AND id = ${len(params)}
            RETURNING id, name, description, conditions, decision, priority, enabled
            """,
            *params,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="rule not found")
    conds = row["conditions"] if isinstance(row["conditions"], dict) else json.loads(row["conditions"])
    dec = row["decision"] if isinstance(row["decision"], dict) else json.loads(row["decision"])
    return PolicyRule(
        id=row["id"], name=row["name"], description=row["description"],
        conditions=conds, decision=dec,
        priority=row["priority"], enabled=row["enabled"],
    )
