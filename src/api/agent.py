"""Layer 2 agent HTTP endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agent.config import AgentConfig
from src.agent.loop import ManthanAgent

router = APIRouter(prefix="/agent", tags=["agent"])


class QueryRequest(BaseModel):
    session_id: str
    dataset_id: str
    message: str


def _get_agent_config() -> AgentConfig:
    return AgentConfig()


AgentConfigDep = Annotated[AgentConfig, Depends(_get_agent_config)]


@router.post("/query")
async def agent_query(request: QueryRequest, config: AgentConfigDep):
    """Run the agent loop and stream SSE events."""

    async def event_stream():
        async with ManthanAgent(config) as agent:
            async for event in agent.run_stream(
                session_id=request.session_id,
                dataset_id=request.dataset_id,
                user_message=request.message,
            ):
                yield event.to_sse()

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
    # Extract render_spec from the done event if present
    render_spec = None
    for e in reversed(result.events_emitted):
        if e.type == "done" and e.data.get("render_spec"):
            render_spec = e.data["render_spec"]
            break

    resp: dict = {
        "text": result.text,
        "turns": result.turns,
        "tool_calls": result.tool_calls_total,
        "elapsed_seconds": result.elapsed_seconds,
    }
    if render_spec:
        resp["render_spec"] = render_spec
    return resp
