"""Health + liveness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from manthan_api import __version__
from manthan_api.db import get_pool

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Cheap liveness probe - no DB hit."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
async def readyz() -> dict:
    """Readiness probe - verifies DB pool is alive."""
    pool = get_pool()
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT 1")
    return {"status": "ready", "db": n == 1, "version": __version__}
