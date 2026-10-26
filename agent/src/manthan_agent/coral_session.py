"""Async context manager that spawns `coral mcp-stdio` and yields a session.

Wrap every run_case() call in this manager — the agent's coral_sql,
coral_list_catalog, and coral_describe_table tools dispatch through the
session it binds. Without an active session the tool handlers raise
RuntimeError so misconfiguration fails loudly.

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

# Shared contextvar - tools.py reads this to dispatch coral_sql /
# coral_list_catalog / coral_describe_table through the live Coral
# MCP session bound here.
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
