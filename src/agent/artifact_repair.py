"""Server-side artifact JS syntax validator + single-shot repair pass.

Problem this solves: the agent occasionally emits a ``create_artifact``
whose inline ``<script>`` contains a parse-level JavaScript error
(unclosed try, mismatched braces, stray comma). Chart.js never runs,
the dashboard renders as empty cards, and the exec sees blank
preview. Detection after-the-fact via ``window.onerror`` is noisy
(sandbox obscures real errors as ``"Script error."``), so we do it
deterministically on the server before the artifact event leaves the
loop:

  1. Extract every inline ``<script>`` body from the HTML.
  2. Feed each body to ``node --check`` via subprocess (Node is
     already required by the UI toolchain, so it's always present in
     a dev/prod environment).
  3. If any script fails to parse, route the HTML + the Node error
     to a focused LLM repair call. The repair prompt is narrow — fix
     the parse error, preserve data / design / structure — so it's
     much cheaper and faster than a full agent turn.
  4. Re-validate after repair. If still broken, ship the original and
     let the client best-effort-render; at least the exec sees
     something instead of silently retrying forever.

``_close_unclosed_try`` in ``events.py`` is the cheap pre-pass — it
catches the single most common failure shape (unclosed outer try)
without an LLM hop. This module is the wider safety net for
everything else (template literal bugs, stray commas, bad string
escapes, etc.).
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass

_SCRIPT_TAG_RE = re.compile(
    r"<script\b([^>]*)>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_SRC_ATTR_RE = re.compile(r"""\bsrc\s*=\s*['"]""", re.IGNORECASE)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error: str  # First failing node-check error, or "" if ok
    skipped: bool = False  # True when Node isn't available


def extract_inline_scripts(html: str) -> list[str]:
    """Return the bodies of inline ``<script>`` tags (``src=`` skipped)."""
    bodies: list[str] = []
    for m in _SCRIPT_TAG_RE.finditer(html):
        attrs = m.group(1) or ""
        if _SRC_ATTR_RE.search(attrs):
            continue  # external script — trust the CDN
        body = (m.group(2) or "").strip()
        if body:
            bodies.append(body)
    return bodies


def check_js_syntax(code: str, timeout: float = 5.0) -> ValidationResult:
    """Run ``node --check`` against ``code``. Non-parseable → ``ok=False``.

    We pipe code via stdin (``node --check -``) so no tempfile needed.
    If Node isn't installed or the subprocess fails for a reason
    unrelated to JS syntax (FileNotFound, permission), we treat the
    check as skipped so artifact emission isn't blocked.
    """
    if not code.strip():
        return ValidationResult(ok=True, error="")
    try:
        proc = subprocess.run(
            ["node", "--check", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return ValidationResult(ok=True, error="", skipped=True)
    except subprocess.TimeoutExpired:
        return ValidationResult(ok=True, error="", skipped=True)
    except OSError:
        return ValidationResult(ok=True, error="", skipped=True)

    if proc.returncode == 0:
        return ValidationResult(ok=True, error="")

    err = (proc.stderr or proc.stdout or "").strip()
    # Node's error has a useful 3–5 line preamble (source line + caret +
    # error type + message). Keep that; drop the long stack trace.
    short = "\n".join(err.splitlines()[:6])
    return ValidationResult(ok=False, error=short or "unknown parse error")


def validate_artifact_html(html: str) -> ValidationResult:
    """Validate every inline script body. Return the first failure."""
    for body in extract_inline_scripts(html):
        res = check_js_syntax(body)
        if not res.ok:
            return res
    return ValidationResult(ok=True, error="")


async def validate_artifact_html_async(html: str) -> ValidationResult:
    """Async-friendly validation — runs subprocess in a thread so the
    agent loop's event stream isn't blocked while Node parses."""
    return await asyncio.to_thread(validate_artifact_html, html)


REPAIR_SYSTEM_PROMPT = """\
You are an artifact REPAIR agent. A dashboard HTML document failed
JavaScript syntax validation. You receive the broken HTML and the
exact parse error from Node. Return the COMPLETE FIXED HTML document,
nothing else — no prose, no markdown fences, no commentary.

Constraints:
- Fix ONLY what's needed to resolve the parse error.
- Preserve every data array, every chart config, every class method,
  every CSS rule. Do not restructure the dashboard.
- Do NOT wrap the script in ``try { ... } catch``. Unclosed try blocks
  are a common cause of these failures; prefer correct code over
  defensive wrappers.
- Keep all Chart.js setup, KPI rendering, drill-down logic intact.
- The output must be a single complete HTML document starting with
  ``<!DOCTYPE html>`` or ``<html``.

Node's error:
{error}
"""


def extract_html_from_llm_response(content: str) -> str:
    """Strip markdown fences or prose preamble the repair LLM may have
    added despite instructions.

    Returns an empty string if the response doesn't look like an HTML
    document — a clear "not a repair" signal so callers can fall back
    rather than ship an apology or half-message as the dashboard.
    """
    s = content.strip()
    # Code fence
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
        s = s.strip()
    # If the LLM ignored instructions and wrote prose first, pull the
    # first HTML document out of it
    m = re.search(r"(<!DOCTYPE\s+html[^>]*>.*?</html>)", s, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"(<html[^>]*>.*?</html>)", s, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    # Final sanity gate — if there's no ``<html`` or ``<!DOCTYPE`` in
    # the response at all, treat it as garbage (apology, refusal,
    # truncation) and signal "no repair available" to the caller.
    low = s.lower()
    if "<html" not in low and "<!doctype" not in low:
        return ""
    return s
