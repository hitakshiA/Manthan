"""Cross-cases inbox SSE stream.

The per-case stream lives in `events.py` (`/api/cases/{id}/stream`). This
file owns the *cross-cases* surface - the Inbox page subscribes here and
gets pushed an updated list whenever any case in the org changes.

Why a separate endpoint instead of N per-case streams: the Inbox shows
~60 cards at once. Opening 60 EventSources from the browser hits the
6-per-host HTTP/1 connection cap and is generally awful. One stream,
one update on changes - debounced to ~1s so investigation bursts collapse.

Wire flow
─────────
1. Replay: emit one `cases` event with the current list immediately.
2. Subscribe to `manthan_event` NOTIFY channel (same one used by the
   per-case stream and the investigate worker).
3. On each notification matching this org, set a dirty flag.
4. A debounce coroutine wakes every ~1s. If dirty, refetch the cases
   list and emit a fresh `cases` event.
5. Heartbeat `ping` every 15s so the client knows we're alive.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import asyncpg
from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from manthan_api.api.cases import fetch_cases_for_org
from manthan_api.config import get_settings
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api/inbox", tags=["inbox"])
logger = logging.getLogger("manthan_api.inbox")

# Min gap between emitted refreshes. The agent worker writes 5–10 events
# per investigation step; without this the stream would saturate.
DEBOUNCE_SECONDS = 1.0

# Send a ping if no real event has fired in this long, so clients can
# detect a dead connection.
HEARTBEAT_SECONDS = 15.0


@router.get("/stream")
async def stream_inbox(
    request: Request,
    ctx: TenantCtx = Depends(get_ctx),
    limit: int = Query(60, ge=1, le=200),
) -> EventSourceResponse:
    """Stream the inbox: one `cases` event per change, debounced ~1s.

    Each `cases` event carries the same payload shape as `GET /api/cases`:
        { "cases": [...], "total": N }
    """
    settings = get_settings()
    org_id = ctx.org_id
    member_id = ctx.member_id

    async def fetch_payload() -> dict:
        cases, total = await fetch_cases_for_org(org_id, member_id=member_id, limit=limit)
        return {
            "cases": [c.model_dump(mode="json") for c in cases],
            "total": total,
        }

    async def gen() -> AsyncIterator[dict]:
        # 1. Initial snapshot.
        try:
            initial = await fetch_payload()
        except Exception as e:  # noqa: BLE001
            logger.exception("inbox stream initial fetch failed: %s", e)
            yield {"event": "error", "data": json.dumps({"detail": str(e)})}
            return
        yield {"event": "cases", "data": json.dumps(initial)}

        # 2. LISTEN connection - dedicated, not pooled, because asyncpg
        #    holds the conn for the duration of the listener.
        notify_conn = await asyncpg.connect(dsn=settings.database_url)
        # Asyncio.Event is set whenever any matching NOTIFY arrives. The
        # debounce loop below clears it after each emit.
        dirty = asyncio.Event()

        def on_notify(_c, _p, _ch, payload):
            try:
                data = json.loads(payload)
            except Exception:
                return
            # Match on org_id so we ignore other tenants' chatter.
            if str(data.get("org_id")) == str(org_id):
                dirty.set()

        try:
            await notify_conn.add_listener("manthan_event", on_notify)

            while True:
                if await request.is_disconnected():
                    return

                # Wait for either:
                #   - a dirty flag (some case in this org changed), or
                #   - HEARTBEAT_SECONDS timeout (send a ping).
                try:
                    await asyncio.wait_for(dirty.wait(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue

                # Burst absorber: hold for DEBOUNCE_SECONDS before
                # refetching. Investigation produces clusters of 5–10
                # events in <100ms; we want one refetch per cluster.
                await asyncio.sleep(DEBOUNCE_SECONDS)
                dirty.clear()

                if await request.is_disconnected():
                    return

                try:
                    payload = await fetch_payload()
                except Exception as e:  # noqa: BLE001
                    logger.exception("inbox stream refetch failed: %s", e)
                    continue
                yield {"event": "cases", "data": json.dumps(payload)}
        finally:
            try:
                await notify_conn.remove_listener("manthan_event", on_notify)
            except Exception:
                pass
            await notify_conn.close()

    return EventSourceResponse(gen())
