"""Clicky-citation endpoints.

Surfaces the citation-reasoning service. Two routes:

  POST /api/cases/{id}/citations/reasoning
       body: {source, table, ref, field?}
       returns: {source, table, ref, field, url, reasoning, model,
                 generated_at, cached}

  GET  /api/cases/{id}/citations
       returns: {reasonings: [...]}   - every cached reasoning for the
       case, for the UI to pre-warm on workspace load.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx
from manthan_api.services.citation_links import resolve_url
from manthan_api.services.citation_reasoning import (
    get_or_generate_reasoning,
    list_reasonings_for_case,
)

router = APIRouter(prefix="/api/cases", tags=["citations"])


class CitationReasoningRequest(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    table: str = Field(min_length=1, max_length=128)
    ref: str = Field(min_length=1, max_length=512)
    field: str | None = Field(default=None, max_length=128)


class CitationReasoningResponse(BaseModel):
    source: str
    table: str
    ref: str
    field: str | None
    url: str | None
    reasoning: str
    model: str | None
    generated_at: str
    cached: bool


@router.post(
    "/{case_id}/citations/reasoning",
    response_model=CitationReasoningResponse,
)
async def post_citation_reasoning(
    case_id: UUID,
    body: CitationReasoningRequest,
    ctx: TenantCtx = Depends(get_ctx),
) -> CitationReasoningResponse:
    """Return the 'why this matters' reasoning for a single citation.

    Caches in `citation_reasonings`. Falls back to a deterministic line
    if the LLM call fails or no API key is configured.
    """
    # Guard rail: confirm the case belongs to this tenant before we
    # bother generating anything.
    async with get_conn() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="case not found",
        )

    result = await get_or_generate_reasoning(
        org_id=ctx.org_id,
        case_id=case_id,
        source=body.source,
        table=body.table,
        ref=body.ref,
        field=body.field,
    )
    return CitationReasoningResponse(
        source=result.source,
        table=result.table,
        ref=result.ref,
        field=result.field,
        url=resolve_url(result.source, result.table, result.ref),
        reasoning=result.reasoning,
        model=result.model,
        generated_at=result.generated_at.isoformat(),
        cached=result.cached,
    )


@router.get("/{case_id}/citations")
async def list_case_citations(
    case_id: UUID,
    ctx: TenantCtx = Depends(get_ctx),
) -> dict:
    """All cached reasonings for the case. UI uses this to pre-warm."""
    async with get_conn() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="case not found",
        )

    reasonings = await list_reasonings_for_case(ctx.org_id, case_id)
    # Sprinkle the resolved url on each so the UI doesn't need a second
    # roundtrip per chip.
    for r in reasonings:
        r["url"] = resolve_url(r["source"], r["table"], r["ref"])
    return {"reasonings": reasonings}
