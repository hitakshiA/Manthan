"""
gen_hykr_diagrams.py - generate architecture diagrams for the HyKr
technical-documentation submission using OpenRouter's
google/gemini-3.1-flash-image-preview (Nano Banana 2).

Reads OPENROUTER_API_KEY from manthan-api/.env. Saves each image as
JPEG under docs/hykr/. We commit + push these afterwards so the
Notion doc can reference them via raw.githubusercontent.com URLs.

The prompts here intentionally lean into the model's strengths
(modern isometric infographic, deep technical labels, clean lines)
while pinning the Manthan visual language (warm dark, emerald accent,
brand-coloured source pills, Spectral serif feel).

Usage:
    cd manthanv2
    uv run python scripts/gen_hykr_diagrams.py             # generate all
    uv run python scripts/gen_hykr_diagrams.py hero        # just hero
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "hykr"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_openrouter_key() -> str:
    """Pull OPENROUTER_API_KEY from manthan-api/.env (no python-dotenv dep)."""
    env_path = ROOT / "manthan-api" / ".env"
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"OPENROUTER_API_KEY not found in {env_path}")


def generate(prompt: str, *, aspect_ratio: str = "16:9") -> bytes:
    """Call OpenRouter, return raw image bytes (decoded from the base64 data URL)."""
    key = load_openrouter_key()
    body = json.dumps(
        {
            "model": "google/gemini-3.1-flash-image-preview",
            "modalities": ["image", "text"],
            "messages": [{"role": "user", "content": prompt}],
            "image_config": {"aspect_ratio": aspect_ratio},
        }
    ).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read())
    if "error" in payload:
        raise RuntimeError(f"OpenRouter error: {payload['error']}")
    images = payload["choices"][0]["message"].get("images") or []
    if not images:
        raise RuntimeError(
            f"No image in response. Full message: {payload['choices'][0]['message']}"
        )
    data_url: str = images[0]["image_url"]["url"]
    if "," not in data_url:
        raise RuntimeError(f"Unexpected image URL shape: {data_url[:80]!r}")
    return base64.b64decode(data_url.split(",", 1)[1])


# --- Visual-language guard rails shared by every prompt ----------------
STYLE = (
    "Modern isometric infographic, clean editorial style. "
    "Warm dark background (oklch 0.135 0.006 75, a near-black with the "
    "warmth of newsprint, no pure black). Restrained palette: a single "
    "emerald accent (#56cf83) for flow arrows and primary highlights, "
    "soft hairline rules in warm gray, brand-coloured pills (Stripe "
    "purple-blue, HubSpot orange, Slack aubergine, Datadog purple, "
    "Notion white, Intercom blue, Zendesk green, PostHog warm orange, "
    "Sentry violet, Salesforce sky blue, PagerDuty green) where the "
    "diagram references a specific SaaS. Labels in clean sans (Geist Mono "
    "feel) for technical text, Spectral serif feel for headline labels. "
    "No glow effects, no neon, no purple-cyan gradients, no glassmorphism. "
    "Generous whitespace. Reads like a NYT technical infographic or a "
    "Bloomberg Terminal docs page. Sharp angles, no shadows beyond a single "
    "soft drop. All labels must be legible at thumbnail size."
)

PROMPTS: dict[str, tuple[str, str]] = {
    "01_system_architecture": (
        "16:9",
        f"""{STYLE}

Title in the top-left corner in small caps serif: "Manthan · system overview".

The diagram is a left-to-right pipeline arranged in 4 vertical columns.

Column 1 ("TRIGGERS", labeled at the top in tiny mono caps): three small
rounded tiles stacked vertically.
  - Top tile: Stripe logo + label "stripe webhook · chargeback opened".
  - Middle tile: an envelope icon + label "resend inbound · support@ email".
  - Bottom tile: Slack logo + label "@manthan mention in #billing-ops".
Each tile has an emerald arrow pointing right into column 2.

Column 2 ("MANTHAN API · FASTAPI"): one tall rectangle. Inside, three
horizontal bands stacked: "/api/inbox/stream  (SSE)",
"/api/cases/:id/stream (SSE)", "/api/cases/:id/approve".
Subtle Postgres elephant icon at the bottom of the rectangle, labeled
"per-org schemas · cases · events · findings · actions".
Three emerald arrows fan out to the right into column 3.

Column 3 ("WORKERS · FOR UPDATE SKIP LOCKED"): three squat tiles stacked
with a tiny worker-gear icon on each, labeled top to bottom:
  - "investigate · runs agent loop"
  - "actor · executes approved actions"
  - "prettifier · LLM summaries"
investigate worker has an arrow to the right into the Coral block in
column 4; actor worker has arrows to the right into the Adapter block;
prettifier has a short loop-back arrow into the API.

Column 4 ("DATA PLANE & WRITE PLANE"): two stacked blocks.
  - TOP block titled "CORAL · MCP/stdio subprocess". A small Rust-crab
    icon. Inside, the 11 source pills in a 4x3 grid: stripe, salesforce,
    hubspot, intercom, zendesk, slack, notion, posthog, sentry, datadog,
    pagerduty. Below the grid: tiny caption "11 SaaS as pg-compatible SQL".
  - BOTTOM block titled "ACTION ADAPTERS · native HTTP". 6 source pills
    in a row: stripe, resend, hubspot, slack, notion, linear.

Bottom strip across the whole image: a single thin emerald line with
the caption "every claim cited · every action approved · every event
logged" in tiny mono caps.

The whole composition should look like a technical infographic from a
serious engineering blog, not a marketing page.""",
    ),
    "02_coral_data_plane": (
        "16:9",
        f"""{STYLE}

Title top-left, large Spectral serif: "The Coral data plane".
Subtitle just below it in smaller mono caps: "one query, eleven schemas".

Layout is THREE vertical columns, very generous spacing, lots of
whitespace. Read left to right.

LEFT COLUMN ("THE AGENT", labelled at the top in mono caps):
  A single tall rounded card. At the top, a small page-document icon.
  Below it: "manthan-agent" in Spectral serif, then in tiny mono:
  "python loop · openrouter · ~hundreds of LOC, no framework".
  Below that, a small code block (monospace) with three lines:
    coral_list_catalog()
    coral_describe_table()
    coral_sql(...)
  with the third line highlighted in emerald.

  Out of this card, one thick emerald arrow goes RIGHT into the middle
  column, labeled along its length in mono: "one wide SELECT".

MIDDLE COLUMN ("CORAL · RUST BINARY"):
  A single LARGE rounded card, centered. Inside the card from top to
  bottom:
    - The Coral logo (a stylised pink coral branch).
    - Spectral serif title: "Coral".
    - Below, in small mono caps: "spawned by the investigate worker as
      a child process via MCP stdio".
    - A small Rust crab icon in the corner.
  No source pills inside this card.

  Out of this card, one thick emerald arrow goes RIGHT into the right
  column, labeled in mono: "one pg-compatible rowset".

  A second, slightly thinner arrow loops BACK from the right column to
  the agent in the left column, labeled "returned in one MCP message".

RIGHT COLUMN ("11 SAAS · pg-COMPATIBLE SCHEMAS"):
  A grid of 11 brand-coloured pills, 3 columns by 4 rows (last row has
  2). Each pill is a rounded rectangle with the source logo and the
  schema name in mono below:
    stripe.disputes   salesforce.accounts   hubspot.companies
    intercom.convos   zendesk.tickets       slack.messages
    notion.pages      posthog.events        sentry.issues
    datadog.incidents pagerduty.incidents

Bottom of the image, a single horizontal hairline rule, and beneath it
a tiny annotation in mono caps:
"join, don't loop · the system prompt forbids one-shot per-source lookups".

Editorial, infographic, dark warm theme, very restrained, very airy.""",
    ),
    "03_case_lifecycle": (
        "16:9",
        f"""{STYLE}

Title top-left: "Case lifecycle · state machine and worker handoffs".

Horizontal flow of 5 large rounded rectangles, left to right, each
labeled with a single Spectral-serif word and a small status pill below
in the matching color:
  1. "Opened"            (amber pill: "queued")
  2. "Investigating"     (amber pill: "live")
  3. "Awaiting approval" (blue pill: "human nod")
  4. "Acting"            (amber pill: "firing")
  5. "Resolved"          (emerald pill: "fired ✓")

Between each pair of states, a thick emerald arrow with a small
mono-caps label naming the worker or human that drives the transition:
  Opened → Investigating       : "investigate worker picks up the row"
  Investigating → Awaiting     : "agent calls draft_brief()"
  Awaiting → Acting            : "operator clicks ▶ Approve · Execute"
  Acting → Resolved            : "actor worker fires all actions"

Below the main lifecycle, a second parallel row labeled "EVENTS EMITTED
TO POSTGRES" with tiny event chips that align under their corresponding
state: case_opened, tool_call, tool_result, finding_recorded,
brief_drafted, hitl_pause, action_approved, action_executed, case_closed.
Each chip is a tiny rounded pill in mono caps.

Top-right corner: a small badge "every transition is one Postgres row in
the events table · ordered, replayable, immutable".

Bottom-right corner: a small badge "FOR UPDATE SKIP LOCKED keeps workers
parallel-safe across users".

Editorial, infographic, dark warm.""",
    ),
    "04_brief_anatomy": (
        "16:9",
        f"""{STYLE}

Title top-left: "Anatomy of a cited brief".

The image is a stylised mockup of the Manthan Workspace screen, drawn as
a flat editorial diagram (not a screenshot). A single large rounded
rectangle takes most of the canvas, representing one case workspace.

At the top of the rectangle, a thin header strip with these labels
left-to-right in mono caps: "CASE APR-345478", "·", "Aperture Analytics",
"·", "ELAPSED 00:38 · 14 STEPS", and on the right a small coral toggle
icon and a blue "Awaiting approval" pill.

Below the header, the rectangle is split into two columns:

LEFT column (titled in tiny mono caps: "BRIEF"):
  - Spectral-italic large headline: "Aperture Analytics vs. an $8,400
    chargeback over Custom Reports degradation."
  - A claim → recommended row: mono "$8,400" with an arrow to a large
    Spectral-italic emerald "$560".
  - Two paragraphs of body text shown as horizontal placeholder lines.
    In one paragraph, three inline CITATION CHIPS are visible as small
    brand-coloured pills: a purple [datadog ↗][2], a white [notion ↗][4],
    an orange [hubspot ↗][7]. Each chip has the source's tiny logo and a
    bracketed number.

RIGHT column (titled in tiny mono caps: "DRAFTED ACTIONS · 4"):
  Four stacked rounded action cards, each with a brand logo on the left
  and a Spectral-serif title plus a mono target line:
  - Stripe · "Refund $560.00 to Aperture" / "POST /v1/refunds"
  - Stripe · "Submit dispute evidence pack" / "POST /v1/disputes/.../evidence"
  - Resend · "Email Aperture's billing contact" / "POST /resend/emails"
  - HubSpot · "Append CRM resolution note" / "POST /crm/v3/objects/.../notes"

  Below the four cards, a single large emerald button labeled
  "▶ Approve · Execute" in mono caps.

In the bottom-left corner, a tiny annotation: "every claim in the prose
links back to the underlying source row · no fabrication."

Editorial, infographic, dark warm, generous whitespace.""",
    ),
}


def main() -> int:
    selected = sys.argv[1:] if len(sys.argv) > 1 else None

    for name, (aspect, prompt) in PROMPTS.items():
        if selected and not any(sel in name for sel in selected):
            continue
        out = OUT_DIR / f"{name}.jpg"
        print(f"→ {name}  ({aspect}) ...", flush=True)
        try:
            data = generate(prompt, aspect_ratio=aspect)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {exc}", file=sys.stderr)
            continue
        out.write_bytes(data)
        kb = len(data) // 1024
        print(f"  ✓ wrote {out.relative_to(ROOT)}  ({kb} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
