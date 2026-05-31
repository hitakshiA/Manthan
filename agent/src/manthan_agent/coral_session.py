"""Async context manager that spawns `coral mcp-stdio` and yields a session.

Use it around a run_case() call when you want the agent's coral_sql /
coral_list_catalog / coral_describe_table to dispatch to the real Coral
binary instead of the in-process mock.

Example:

    async with coral_mcp_session("/path/to/coral") as session:
        token = set_active_coral_session(session)
        try:
            async for event in run_case(trigger, cfg, store):
                ...
        finally:
            clear_active_coral_session(token)
"""

from __future__ import annotations

import contextvars
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Shared contextvar - tools.py reads this to decide whether to dispatch
# to the real Coral or to the in-process mock.
_ACTIVE_CORAL_SESSION: contextvars.ContextVar[ClientSession | None] = (
    contextvars.ContextVar("manthan_active_coral_session", default=None)
)


def get_active_coral_session() -> ClientSession | None:
    return _ACTIVE_CORAL_SESSION.get()


def set_active_coral_session(session: ClientSession) -> contextvars.Token:
    return _ACTIVE_CORAL_SESSION.set(session)


def clear_active_coral_session(token: contextvars.Token) -> None:
    _ACTIVE_CORAL_SESSION.reset(token)


@asynccontextmanager
async def coral_mcp_session(coral_binary: str) -> Any:
    """Spawn `<coral_binary> mcp-stdio` and yield an initialized session.

    Caller is expected to manage the contextvar binding via
    set_active_coral_session() / clear_active_coral_session() - this
    helper only owns the subprocess lifecycle.
    """
    params = StdioServerParameters(
        command=coral_binary,
        args=["mcp-stdio"],
        env=None,
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session
