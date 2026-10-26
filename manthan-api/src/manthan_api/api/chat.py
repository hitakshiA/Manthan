"""Cross-case agent chat.

Different from per-case chat (workers/chat_loop). This is the "talk to
the agent across all the cases" surface - answers questions like
"which customers had refunds delayed past 5 days?" or "MRR down 4%, why?"

For v1 it's a stateless single-shot LLM call seeded with recent cases.
For v2 we'd add coral_sql tool access so the agent can run live queries.

Endpoint: POST /api/chat  body: { message: str }
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger("manthan_api.chat")

MODEL = os.environ.get("MANTHAN_CHAT_MODEL", "google/gemini-3.1-flash-lite")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    cases_seen: int


SYSTEM = """\
You are Manthan, a billing operations AI working alongside a Director of Revenue Accounting (or similar). You speak in plain English. No engineering jargon.

You're answering a question about the operator's billing cases. The CONTEXT block below has the last 20 cases this workspace has seen with their status, customer, decision, and amount. Use it to answer.

Rules:
- If the question can be answered from the context, answer it directly and cite the case short_ids inline (e.g. "QLO-198835 was a $9k chargeback against Quill Logistics - fight recommended").
- If the question cannot be answered from the context, say so honestly. Don't make up data.
- Keep replies 2-5 sentences. The operator skims.
- No markdown beyond inline `code` for ids. No bullet points unless answering a list question.
"""


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    ctx: TenantCtx = Depends(get_ctx),
) -> ChatResponse:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENROUTER_API_KEY is not configured",
        )

    # Pull recent cases for grounding.
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT short_id, status, case_type, trigger_surface, customer_ref,
                   amount_minor, decision_action, decision_amount_minor,
                   decision_confidence, created_at
            FROM cases
            WHERE org_id=$1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            ctx.org_id,
        )

    if not rows:
        return ChatResponse(
            reply=(
                "No cases yet in this workspace, so I don't have anything "
                "to reason over. Fire a demo scenario from the TopBar and "
                "ask me again."
            ),
            cases_seen=0,
        )

    context_lines = []
    for r in rows:
        amt = f"${(r['amount_minor'] or 0) / 100:,.0f}" if r["amount_minor"] else "-"
        dec = r["decision_action"] or "pending"
        dec_amt = (
            f"${(r['decision_amount_minor']) / 100:,.0f}"
            if r["decision_amount_minor"] else ""
        )
        context_lines.append(
            f"{r['short_id']} · {r['customer_ref'] or 'unknown'} · "
            f"{r['case_type'] or 'case'} · {amt} · {r['trigger_surface']} · "
            f"status={r['status']} · decision={dec} {dec_amt}".strip()
        )
    context_block = "\n".join(context_lines)

    user_payload = (
        f"CONTEXT - last 20 cases for this workspace:\n{context_block}\n\n"
        f"OPERATOR ASKS: {body.message}"
    )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as http:
            r = await http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://app.manthan.quest",
                    "X-Title": "Manthan cross-case chat",
                },
                json={
                    "model": MODEL,
                    "max_tokens": 320,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user_payload},
                    ],
                },
            )
            r.raise_for_status()
            body_json: Any = r.json()
            reply_text = (
                ((body_json.get("choices") or [{}])[0].get("message") or {}).get("content")
                or "(no reply)"
            )
    except httpx.HTTPError as e:
        logger.exception("chat LLM call failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM call failed: {type(e).__name__}",
        )

    return ChatResponse(reply=reply_text.strip(), cases_seen=len(rows))
