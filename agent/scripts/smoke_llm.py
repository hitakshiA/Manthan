"""Smoke test 1: confirm the LLM is reachable via OpenRouter.

Run with:
    cd manthanv2/agent
    uv run python scripts/smoke_llm.py

Exit codes:
    0 - success, or OPENROUTER_API_KEY missing (skipped cleanly)
    1 - API key present but the call failed
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel

from manthan_agent import config
from manthan_agent.llm import LLMNotConfigured, chat

console = Console()


def main() -> int:
    cfg = config.load()

    if not cfg.openrouter_api_key:
        console.print(
            Panel(
                "[yellow]OPENROUTER_API_KEY is not set.[/yellow]\n\n"
                "Add it to [bold]manthanv2/agent/.env[/bold] and re-run.\n"
                "Get a key at https://openrouter.ai/keys",
                title="LLM smoke - skipped",
                border_style="yellow",
            )
        )
        return 0

    console.print(
        f"[dim]→ POST /chat/completions  model=[bold]{cfg.model}[/bold]  "
        f"via OpenRouter[/dim]"
    )

    try:
        resp = chat(
            cfg,
            [
                {
                    "role": "system",
                    "content": (
                        "You are the Manthan investigation agent. "
                        "When asked for a smoke test, reply with exactly: "
                        "'manthan online'. Nothing else."
                    ),
                },
                {"role": "user", "content": "smoke test"},
            ],
        )
    except LLMNotConfigured as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    except Exception as exc:
        # Surface any provider error verbatim - class name + message.
        console.print(f"[red]LLM call failed:[/red] {type(exc).__name__}: {exc}")
        return 1

    msg = resp.choices[0].message
    reply = (msg.content or "").strip()
    usage = getattr(resp, "usage", None)
    finish = resp.choices[0].finish_reason

    panel = Panel(
        f"[bold green]reply[/bold green]   {reply!r}\n"
        f"[dim]finish[/dim]   {finish}\n"
        + (
            f"[dim]tokens[/dim]   in={usage.prompt_tokens} "
            f"out={usage.completion_tokens} total={usage.total_tokens}"
            if usage
            else ""
        ),
        title="LLM smoke - ok",
        border_style="green",
    )
    console.print(panel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
