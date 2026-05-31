"""Shared utilities for per-source seeders.

Conventions every seeder follows:
  1. Idempotent: re-running creates no duplicates. Use the
     `manthan:<slug>` marker (CompanyIdentity.manthan_marker) on every
     record where the source supports a metadata field.
  2. Phase-banner output via `seed_phase(...)` so the user can see what's
     happening and where time is going.
  3. Fail loud on misconfiguration (missing key, scope error). Fail
     informatively - say which env var to fix.
  4. Read scenarios from `seed.scenarios.SCENARIOS`. Don't hardcode
     scenario data inside source modules - keep that single source of
     truth.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console

console = Console()


class SeederNotConfigured(RuntimeError):
    """Raised when a source's required env vars are missing.

    Subclasses (`StripeSeederNotConfigured`, etc.) include a clear message
    naming the var to set.
    """


@contextmanager
def seed_phase(label: str) -> Iterator[None]:
    """Print a phase banner, time the block, print elapsed on exit.

    Usage:
        with seed_phase("create stripe customers"):
            for scenario in SCENARIOS:
                ...
    """
    console.print(f"[bold cyan]→[/bold cyan] {label}")
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        console.print(f"  [dim]done in {elapsed:.1f}s[/dim]")


def report(action: str, item: str, *, status: str = "ok") -> None:
    """Per-record log line.

    `status` is one of: ok | skipped | error. Color-coded.
    """
    palette = {"ok": "green", "skipped": "yellow", "error": "red"}
    glyph = {"ok": "✓", "skipped": "↺", "error": "✗"}
    color = palette.get(status, "white")
    g = glyph.get(status, "·")
    console.print(f"  [{color}]{g}[/{color}] {action} [dim]{item}[/dim]")
