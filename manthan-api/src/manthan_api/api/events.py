"""Event timeline endpoints - list + SSE stream.

The timeline is the canonical view of "what the agent is doing right now."
The investigation worker writes events to PG; this endpoint replays the
history then streams new ones via Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from manthan_api.config import get_settings
from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/cases", tags=["events"])
logger = logging.getLogger("manthan_api.events")


@router.get("/{case_id}/events")
async def list_case_events(
    case_id: UUID,
    ctx: TenantCtx = Depends(get_ctx),
    after_seq: int = 0,
) -> dict:
    """Return all events for a case after a given seq (for polling fallback)."""
    async with get_conn() as conn:
        thread_row = await conn.fetchrow(
            "SELECT thread_id FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
        if thread_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")
        thread_id = thread_row["thread_id"]
        rows = await conn.fetch(
            """
            SELECT id, seq, type, actor, data, summary, created_at
            FROM events
            WHERE org_id=$1 AND thread_id=$2 AND seq > $3
            ORDER BY seq ASC
            """,
            ctx.org_id, thread_id, after_seq,
        )
    return {
        "case_id": str(case_id),
        "events": [
            {
                "id": r["id"],
                "seq": r["seq"],
                "type": r["type"],
                "actor": r["actor"],
                "data": r["data"],
                "summary": r["summary"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/{case_id}/stream")
async def stream_case_events(
    request: Request,
    case_id: UUID,
    ctx: TenantCtx = Depends(get_ctx),
) -> EventSourceResponse:
    """Server-Sent Events stream of events for a case.

    Sends every existing event first (replay), then streams new ones until
    the client disconnects or a `case_closed` event is observed.
    """
    async with get_conn() as conn:
        thread_row = await conn.fetchrow(
            "SELECT thread_id FROM cases WHERE org_id=$1 AND id=$2",
            ctx.org_id, case_id,
        )
        if thread_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found")
        thread_id = thread_row["thread_id"]

    async def gen() -> AsyncIterator[dict]:
        last_seq = 0
        # 1. Replay
        async with get_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT seq, type, actor, data, summary, created_at
                FROM events
                WHERE org_id=$1 AND thread_id=$2
                ORDER BY seq ASC
                """,
                ctx.org_id, thread_id,
            )
        closed = False
        for r in rows:
            yield {
                "event": "case_event",
                "data": json.dumps({
                    "seq": r["seq"],
                    "type": r["type"],
                    "actor": r["actor"],
                    "data": r["data"],
                    "summary": r["summary"],
                    "created_at": r["created_at"].isoformat(),
                }),
            }
            last_seq = r["seq"]
            if r["type"] == "case_closed":
                closed = True

        if closed:
            yield {"event": "complete", "data": "{}"}
            return

        # 2. Live tail via a dedicated LISTEN connection.
        notify_conn = await asyncpg.connect(dsn=get_settings().database_url)
        queue: asyncio.Queue[dict] = asyncio.Queue()

        def on_notify(_c, _p, _ch, payload):
            try:
                data = json.loads(payload)
            except Exception:
                return
            if (
                str(data.get("thread_id")) == str(thread_id)
                and str(data.get("org_id")) == str(ctx.org_id)
            ):
                queue.put_nowait(data)

        try:
            await notify_conn.add_listener("manthan_event", on_notify)

            # Poll for new rows (LISTEN delivers signal but we re-fetch the row)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield {"event": "ping", "data": ""}
                    continue

                async with get_conn() as conn:
                    new_rows = await conn.fetch(
                        """
                        SELECT seq, type, actor, data, summary, created_at
                        FROM events
                        WHERE org_id=$1 AND thread_id=$2 AND seq > $3
                        ORDER BY seq ASC
                        """,
                        ctx.org_id, thread_id, last_seq,
                    )
                for r in new_rows:
                    payload = {
                        "seq": r["seq"],
                        "type": r["type"],
                        "actor": r["actor"],
                        "data": r["data"],
                        "summary": r["summary"],
                        "created_at": r["created_at"].isoformat(),
                    }
                    yield {"event": "case_event", "data": json.dumps(payload)}
                    last_seq = r["seq"]
                    if r["type"] == "case_closed":
                        yield {"event": "complete", "data": "{}"}
                        return
        finally:
            try:
                await notify_conn.remove_listener("manthan_event", on_notify)
            except Exception:
                pass
            await notify_conn.close()

    return EventSourceResponse(gen())
