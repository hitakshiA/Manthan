"""FastAPI route definitions.

Each submodule defines an ``APIRouter`` that ``src.main`` includes on the
application. Routers here are thin: they validate inputs, delegate to the
appropriate domain module, and shape the response. No business logic lives
in this layer.
"""
