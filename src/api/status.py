"""Dataset status endpoint and progress websocket (SPEC §10.1).

``GET /datasets/{id}/progress`` returns the accumulated progress events
for a dataset. ``WebSocket /datasets/{id}/status`` streams new events as
the profiling agent advances through PERCEIVE → CLASSIFY → … → EMIT and
is surfaced to the frontend for live progress reporting.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from src.core.state import AppState, get_state

router = APIRouter(tags=["status"])

StateDep = Annotated[AppState, Depends(get_state)]

_POLL_INTERVAL_SECONDS = 0.5


@router.get("/datasets/{dataset_id}/progress")
def progress(dataset_id: str, state: StateDep) -> dict[str, list[dict[str, object]]]:
    if dataset_id not in state.registry._entries:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    return {"events": state.dataset_progress.get(dataset_id, [])}


@router.websocket("/datasets/{dataset_id}/status")
async def status_ws(websocket: WebSocket, dataset_id: str) -> None:
    await websocket.accept()
    state = get_state()
    try:
        sent = 0
        while True:
            events = state.dataset_progress.get(dataset_id, [])
            if len(events) > sent:
                for event in events[sent:]:
                    await websocket.send_json(event)
                sent = len(events)

            if events and events[-1].get("stage") in ("gold", "error"):
                await websocket.send_json({"stage": "done"})
                break

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return
