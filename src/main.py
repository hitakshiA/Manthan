"""FastAPI application entry point for the Manthan data layer.

Wires together configuration, logging, rate limiting, and API routers.
All business logic lives in the domain modules under ``src/``.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import traceback
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
    audit,
    clarification,
    connections,
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


def _log_exception(kind: str, exc: BaseException, *, extra: str = "") -> None:
    """Last-resort crash logger — prints to stderr so the supervisor log captures it."""
    print(
        f"[manthan.crash] {kind}: {type(exc).__name__}: {exc} {extra}".strip(),
        file=sys.stderr,
        flush=True,
    )
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    sys.stderr.flush()


def _install_global_handlers() -> None:
    """Wire sys.excepthook + asyncio exception handler so a crash never goes silent."""
    original_excepthook = sys.excepthook

    def excepthook(exc_type, exc, tb):
        _log_exception("uncaught", exc)
        original_excepthook(exc_type, exc, tb)

    sys.excepthook = excepthook

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return

    def handler(_loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        if isinstance(exc, BaseException):
            _log_exception("asyncio", exc, extra=context.get("message", ""))
        else:
            print(
                f"[manthan.crash] asyncio-context: {context}",
                file=sys.stderr,
                flush=True,
            )

    loop.set_exception_handler(handler)


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

    _install_global_handlers()
    logging.getLogger(__name__).info("manthan startup: global crash handlers installed")
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
        "http://localhost:5174",
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
app.include_router(connections.router)
app.include_router(audit.router)


@app.get("/metrics", tags=["observability"])
def read_metrics() -> dict[str, object]:
    """Return a snapshot of in-process metrics."""
    return metrics.snapshot()


# ── Layer 3 SPA serving ──────────────────────────────────────
# Serve the built frontend from manthan-ui/dist/ if it exists.
# All non-API routes fall through to index.html (SPA routing).

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "manthan-ui" / "dist"

if _FRONTEND_DIR.is_dir():
    # Static assets (JS/CSS bundles with hashed filenames)
    app.mount(
        "/assets",
        StaticFiles(directory=_FRONTEND_DIR / "assets"),
        name="frontend-assets",
    )

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        """Serve the SPA index page."""
        return FileResponse(_FRONTEND_DIR / "index.html")

    @app.get("/favicon.svg", include_in_schema=False)
    def serve_favicon() -> FileResponse:
        return FileResponse(_FRONTEND_DIR / "favicon.svg")

    @app.get("/logo.svg", include_in_schema=False)
    def serve_logo() -> FileResponse:
        return FileResponse(_FRONTEND_DIR / "logo.svg")
