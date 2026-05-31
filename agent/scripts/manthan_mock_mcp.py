"""MCP server that wraps a brutal-scenario DuckDB world.

Exposes one tool per (source, table) in the scenario world. Each tool
returns `{"result": [...rows...]}` so Coral's mcp-backend can read it
as a virtual SQL table.

Coral spawns this script as a subprocess via the source manifest's
`server.command` field. The scenario world is loaded from a JSON file
whose path is in the MANTHAN_SCENARIO_JSON env var.

Run standalone for debugging:
    MANTHAN_SCENARIO_JSON=/tmp/world.json python scripts/manthan_mock_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ----------------------------------------------------------------------
# Load scenario world
# ----------------------------------------------------------------------

_DEFAULT_JSON = (
    Path(__file__).parent.parent / ".manthan" / "scenario_world.json"
)
# Path resolution priority:
#   1) sys.argv[1] (how Coral's source manifest passes it)
#   2) MANTHAN_SCENARIO_JSON env var (standalone debugging)
#   3) default fallback path
if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    _JSON_PATH = Path(sys.argv[1])
else:
    _JSON_PATH = Path(os.environ.get("MANTHAN_SCENARIO_JSON", str(_DEFAULT_JSON)))


def _load_world() -> dict[str, dict[str, list[dict[str, Any]]]]:
    if not _JSON_PATH.exists():
        # Don't crash - return empty world. Coral will see zero rows
        # rather than a server failure.
        return {}
    return json.loads(_JSON_PATH.read_text())


_WORLD = _load_world()


def _tool_name(source: str, table: str) -> str:
    """Coral-friendly tool name: lowercase, underscore-joined."""
    return f"get_{source.lower()}_{table.lower()}"


def _parse_tool_name(name: str) -> tuple[str, str] | None:
    if not name.startswith("get_"):
        return None
    rest = name[4:]
    # The first underscore-separated chunk is the source if it matches a known
    # key; otherwise we walk until we find a (source, table) that exists.
    for source in _WORLD:
        prefix = source.lower() + "_"
        if rest.startswith(prefix):
            return source, rest[len(prefix):]
    return None


# ----------------------------------------------------------------------
# MCP server
# ----------------------------------------------------------------------

server: Server = Server("manthan-mock")


@server.list_tools()
async def _list_tools() -> list[Tool]:
    tools: list[Tool] = []
    for source, tables in _WORLD.items():
        for table, rows in tables.items():
            if not rows:
                continue
            tools.append(
                Tool(
                    name=_tool_name(source, table),
                    description=(
                        f"Returns all rows from the mock {source}.{table} "
                        f"table ({len(rows)} rows). No filter arguments; "
                        f"Coral filters in its SQL plane."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                )
            )
    return tools


@server.call_tool()
async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    parsed = _parse_tool_name(name)
    if parsed is None:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {"result": [], "error": f"Unknown tool: {name}"}
                ),
            )
        ]
    source, table = parsed
    rows = _WORLD.get(source, {}).get(table, [])
    payload = {"result": rows, "row_count": len(rows)}
    return [TextContent(type="text", text=json.dumps(payload, default=str))]


# ----------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------


async def _amain() -> None:
    async with stdio_server() as (read, write):
        await server.run(
            read,
            write,
            server.create_initialization_options(),
        )


def main() -> int:
    if not _WORLD:
        sys.stderr.write(
            f"[manthan_mock_mcp] WARNING: empty world. "
            f"MANTHAN_SCENARIO_JSON={_JSON_PATH} does not exist or has no data.\n"
        )
    asyncio.run(_amain())
    return 0


if __name__ == "__main__":
    sys.exit(main())
