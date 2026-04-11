"""FastAPI application entry point for the Manthan data layer.

Wires together configuration, logging, and the API routers. This module is
intentionally thin — all business logic lives in the domain modules under
``src/``.
"""

from fastapi import FastAPI

from src import __version__
from src.api import health

app = FastAPI(
    title="Manthan",
    description="Seamless Self-Service Intelligence — Talk to Data",
    version=__version__,
)

app.include_router(health.router)
