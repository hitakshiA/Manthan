"""FastAPI application entry point for the Manthan data layer.

Wires together configuration, logging, rate limiting, and API routers.
All business logic lives in the domain modules under ``src/``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src import __version__
from src.api import (
    agent,
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
from src.core.rate_limit import WHITELISTED_IPS, get_real_ip, limiter


def _rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    ip = get_real_ip(request)
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": (
                f"Too many requests from {ip}. "
                f"Limit: {exc.detail}. "
                "Retry after the window resets."
            ),
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and load settings on startup."""
    del app
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)

    whitelist_env = getattr(settings, "rate_limit_whitelist", None)
    if whitelist_env:
        for ip in whitelist_env:
            WHITELISTED_IPS.add(ip.strip())
    yield


app = FastAPI(
    title="Manthan",
    description="Autonomous Data Analyst Platform",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://manthan.quest",
        "http://manthan.quest",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(agent.router)


@app.get("/metrics", tags=["observability"])
def read_metrics() -> dict[str, object]:
    """Return a snapshot of in-process metrics."""
    return metrics.snapshot()


# ── Layer 3 SPA serving ──────────────────────────────────────
# Serve the built frontend from manthan-ui/dist/ if it exists.
# All non-API routes fall through to index.html (SPA routing).

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "manthan-ui" / "dist"

if _FRONTEND_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=_FRONTEND_DIR / "assets"),
        name="frontend-assets",
    )

    @app.get("/{path:path}", include_in_schema=False)
    def serve_spa(path: str) -> FileResponse:
        """Serve SPA — any non-API route returns index.html."""
        file = _FRONTEND_DIR / path
        if file.is_file() and ".." not in path:
            return FileResponse(file)
        return FileResponse(_FRONTEND_DIR / "index.html")
