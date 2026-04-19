"""Layer 2 agent HTTP endpoint."""

from __future__ import annotations

import logging
import traceback
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agent import events as agent_events
from src.agent.config import AgentConfig
from src.agent.loop import ManthanAgent

router = APIRouter(prefix="/agent", tags=["agent"])
_log = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    session_id: str
    dataset_id: str
    message: str


def _get_agent_config() -> AgentConfig:
    return AgentConfig()


AgentConfigDep = Annotated[AgentConfig, Depends(_get_agent_config)]


@router.post("/query")
async def agent_query(request: QueryRequest, config: AgentConfigDep):
    """Run the agent loop and stream SSE events.

    The event generator is wrapped in a blanket try/except so an
    unexpected failure inside the loop (bad tool args, LLM timeout,
    sandbox glitch) surfaces as an SSE ``error`` event + clean ``done``
    instead of crashing the ASGI worker.
    """

    async def event_stream():
        try:
            async with ManthanAgent(config) as agent:
                async for event in agent.run_stream(
                    session_id=request.session_id,
                    dataset_id=request.dataset_id,
                    user_message=request.message,
                ):
                    yield event.to_sse()
        except Exception as exc:
            tb = traceback.format_exc()
            _log.exception(
                "agent stream crashed session=%s dataset=%s",
                request.session_id,
                request.dataset_id,
            )
            yield agent_events.error(
                f"{type(exc).__name__}: {exc}"[:500],
                recoverable=False,
            ).to_sse()
            yield agent_events.done(
                summary="Agent run failed — see logs.",
                turns=0,
                tool_calls=0,
                elapsed=0.0,
            ).to_sse()
            # Print to stderr too — the supervisor log captures this.
            print(f"[agent.stream] CRASH {type(exc).__name__}: {exc}\n{tb}", flush=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/query/sync")
async def agent_query_sync(request: QueryRequest, config: AgentConfigDep) -> dict:
    """Run the agent loop synchronously (for testing). Returns result JSON."""
    async with ManthanAgent(config) as agent:
        result = await agent.run(
            session_id=request.session_id,
            dataset_id=request.dataset_id,
            user_message=request.message,
        )
    return {
        "text": result.text,
        "turns": result.turns,
        "tool_calls": result.tool_calls_total,
        "elapsed_seconds": result.elapsed_seconds,
    }
