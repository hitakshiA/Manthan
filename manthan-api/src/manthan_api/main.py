"""FastAPI app entry point - `uvicorn manthan_api.main:app`."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

# Load env from BOTH manthan-api/.env and the sibling agent/.env. The
# /api/sources endpoint reads source credentials directly from the
# environment (STRIPE_API_KEY, NOTION_API_KEY, etc.) and those live in
# agent/.env. Without this, "0 live · 11 available" on the Sources page
# even when everything is configured.
from dotenv import load_dotenv
_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "manthan-api" / ".env")
load_dotenv(_ROOT / "agent" / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from manthan_api import __version__
from manthan_api.api import (
    actions, audit, cases, chat, citations, clerk_webhook, demo,
    email_webhook, events, health, inbox, me, memory, metrics, narrative,
    policy, slack, sources, webhooks,
)
from manthan_api.config import get_settings
from manthan_api.db import close_pool, init_pool

logger = logging.getLogger("manthan_api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await init_pool()
    logger.info("manthan_api startup complete - version=%s", __version__)
    try:
        yield
    finally:
        await close_pool()
        logger.info("manthan_api shutdown complete")


app = FastAPI(
    title="Manthan API",
    version=__version__,
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_app_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


app.include_router(health.router)
app.include_router(cases.router)
app.include_router(events.router)
app.include_router(inbox.router)
app.include_router(citations.router)
app.include_router(actions.router)
app.include_router(metrics.router)
app.include_router(webhooks.router)
app.include_router(slack.router)
app.include_router(email_webhook.router)
app.include_router(clerk_webhook.router)
app.include_router(policy.router)
app.include_router(audit.router)
app.include_router(demo.router)
app.include_router(sources.router)
app.include_router(me.router)
app.include_router(memory.router)
app.include_router(chat.router)
app.include_router(narrative.router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "manthan-api",
        "version": __version__,
        "docs": "/docs",
    }
