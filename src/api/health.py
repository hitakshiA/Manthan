"""Health check endpoints.

Exposes a single liveness probe used by local development, tests, and any
future orchestrator. Kept deliberately side-effect-free so it can be hit
safely under any load.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return a simple liveness indicator.

    Returns:
        A mapping with a single ``status`` key whose value is ``"ok"`` when
        the application process is reachable.
    """
    return {"status": "ok"}
