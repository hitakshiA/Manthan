"""Smoke test 2: confirm Coral is reachable over MCP from Python.

Spawns `coral mcp-stdio` as a subprocess, opens an MCP session, lists the
tools Coral exposes, and (if available) calls `list_catalog` to confirm
SQL-plane access. This is the agent's first cross-layer step - once this
works, the agent loop can wire `coral_sql` as a tool against the same
client.

Run with:
    cd manthanv2/agent
    .venv/bin/python scripts/smoke_coral.py

Exit codes:
    0 - success
    1 - Coral binary missing, MCP handshake failed, or tool call errored
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from manthan_agent import config

console = Console()


def _resolve_binary(name_or_path: str) -> str | None:
    """Return an absolute path to the coral binary, or None if not found.

    Accepts an absolute path (returned as-is if executable) or a bare
    command name (resolved via PATH).
    """
    p = Path(name_or_path)
    if p.is_absolute():
        return str(p) if p.is_file() and os.access(p, os.X_OK) else None
    found = shutil.which(name_or_path)
    return found


async def run() -> int:
    cfg = config.load()

    resolved = _resolve_binary(cfg.coral_binary)
    if resolved is None:
        console.print(
            Panel(
                f"[red]Coral binary not found:[/red] {cfg.coral_binary}\n\n"
                "Either install via Homebrew (`brew install withcoral/tap/coral`)\n"
                "or build the Manthan fork:\n"
                "  cd /Users/akshmnd/Dev\\ Projects/coral\n"
                "  cargo build --release -p coral-cli --no-default-features\n\n"
                "Then set CORAL_BINARY in manthanv2/agent/.env.",
                title="Coral smoke - binary missing",
                border_style="red",
            )
        )
        return 1

    console.print(f"[dim]→ spawning [bold]{resolved} mcp-stdio[/bold][/dim]")

    params = StdioServerParameters(
        command=resolved,
        args=["mcp-stdio"],
        env=None,  # inherit os.environ so coral picks up source creds later
    )

    try:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
                await session.initialize()

                # Tool inventory
                tools_result = await session.list_tools()
                tools = tools_result.tools

                tbl = Table(title="Coral MCP tools", show_header=True)
                tbl.add_column("Name", style="green")
                tbl.add_column("Description", style="dim", overflow="fold")
                for t in tools:
                    desc = (t.description or "").strip().replace("\n", " ")
                    if len(desc) > 100:
                        desc = desc[:97] + "..."
                    tbl.add_row(t.name, desc or "(no description)")
                console.print(tbl)
                console.print(
                    f"[dim]{len(tools)} tool(s) exposed by coral mcp-stdio[/dim]"
                )

                # Catalog probe - try list_catalog first; fall back to running
                # a SQL query against the meta schema if the named tool is absent.
                tool_names = {t.name for t in tools}
                console.print()

                if "list_catalog" in tool_names:
                    console.print("[dim]→ call list_catalog()[/dim]")
                    result = await session.call_tool("list_catalog", arguments={})
                elif "sql" in tool_names:
                    console.print(
                        "[dim]→ list_catalog not exposed; falling back to sql() over coral.tables[/dim]"
                    )
                    result = await session.call_tool(
                        "sql",
                        arguments={
                            "query": (
                                "SELECT schema_name, table_name FROM coral.tables "
                                "ORDER BY 1, 2 LIMIT 20"
                            )
                        },
                    )
                else:
                    console.print(
                        f"[yellow]Neither list_catalog nor sql tool exposed. "
                        f"Available: {sorted(tool_names)}[/yellow]"
                    )
                    return 1

                if result.isError:
                    console.print(
                        f"[red]Tool returned isError=True:[/red] {result.content}"
                    )
                    return 1

                # Render result content (mostly text blocks)
                if not result.content:
                    console.print("[yellow](empty result)[/yellow]")
                else:
                    first = result.content[0]
                    text = getattr(first, "text", str(first))
                    if len(text) > 1200:
                        text = text[:1200] + "\n... (truncated)"
                    console.print(
                        Panel(
                            text,
                            title="catalog probe - first result block",
                            border_style="green",
                        )
                    )

                return 0
    except FileNotFoundError as exc:
        console.print(f"[red]Cannot spawn coral binary:[/red] {exc}")
        return 1
    except Exception as exc:
        # Surface any provider/transport error verbatim - class + message.
        console.print(
            f"[red]Coral MCP smoke failed:[/red] {type(exc).__name__}: {exc}"
        )
        return 1


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
