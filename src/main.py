"""FastAPI application entry point for the Manthan data layer.

Wires together configuration, logging, and API routers. All business
logic lives in the domain modules under ``src/``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import __version__
from src.api import (
    agent_tasks,
    ask_user,
    clarification,
    datasets,
    health,
    memory,
    plans,
    status,
    subagents,
    tool_discovery,
    tools,
)
from src.core import metrics
from src.core.config import get_settings
from src.core.logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and load settings on startup."""
    del app  # parameter is required by FastAPI's lifespan protocol
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    yield


app = FastAPI(
    title="Manthan",
    description="Seamless Self-Service Intelligence — Talk to Data",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(datasets.router)
app.include_router(tools.router)
app.include_router(clarification.router)
app.include_router(status.router)
app.include_router(memory.router)
app.include_router(agent_tasks.router)
app.include_router(ask_user.router)
app.include_router(plans.router)
app.include_router(subagents.router)
app.include_router(tool_discovery.router)


@app.get("/metrics", tags=["observability"])
def read_metrics() -> dict[str, object]:
    """Return a snapshot of in-process metrics."""
    return metrics.snapshot()
