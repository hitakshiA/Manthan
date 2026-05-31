"""
publish_hykr_notion.py - publish the Manthan technical documentation
to Notion (the "manthan" bot in the Miny-labs workspace), as a single
sub-page under "Manthan Ops".

Reads NOTION_API_KEY from manthan-api/.env. Images are referenced via
their raw.githubusercontent.com URLs so we don't have to upload
binaries through Notion's attachment endpoint.

Run:
    python3 scripts/publish_hykr_notion.py

The script is idempotent in spirit: re-running creates a new dated
page each time (Notion has no native upsert for pages by title).
The printed URL at the end is what the user pastes into the HyKr form.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT_PAGE_ID = "36d43656-c526-80b4-b6f6-f64039a09caf"  # "Manthan Ops"
REPO_RAW = "https://raw.githubusercontent.com/akash-mondal/manthan/main"
NOTION_VERSION = "2022-06-28"


def load_notion_key() -> str:
    env_path = ROOT / "manthan-api" / ".env"
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("NOTION_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("NOTION_API_KEY missing from manthan-api/.env")


def request(method: str, path: str, body: dict | None = None) -> dict:
    key = load_notion_key()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"https://api.notion.com/v1{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_txt = exc.read().decode(errors="replace")
        raise RuntimeError(f"Notion {method} {path} -> {exc.code}: {body_txt}") from exc


# ── block helpers (Notion's rich-text JSON is verbose; wrap it) ────────

def _rt(text: str, *, bold: bool = False, code: bool = False,
        link: str | None = None, color: str = "default") -> dict:
    return {
        "type": "text",
        "text": {"content": text, "link": {"url": link} if link else None},
        "annotations": {
            "bold": bold, "italic": False, "strikethrough": False,
            "underline": False, "code": code, "color": color,
        },
    }


def _parse(s: str) -> list[dict]:
    """Mini-parser for inline markup: **bold**, `code`, and [text](url).
    Plain text only otherwise. No em-dashes ever - kept as plain hyphens.
    """
    out: list[dict] = []
    i = 0
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            out.append(_rt(buf))
            buf = ""

    while i < len(s):
        # **bold**
        if s.startswith("**", i):
            end = s.find("**", i + 2)
            if end != -1:
                flush()
                out.append(_rt(s[i + 2 : end], bold=True))
                i = end + 2
                continue
        # `code`
        if s[i] == "`":
            end = s.find("`", i + 1)
            if end != -1:
                flush()
                out.append(_rt(s[i + 1 : end], code=True))
                i = end + 1
                continue
        # [text](url)
        if s[i] == "[":
            close_bracket = s.find("]", i + 1)
            if close_bracket != -1 and close_bracket + 1 < len(s) and s[close_bracket + 1] == "(":
                close_paren = s.find(")", close_bracket + 2)
                if close_paren != -1:
                    flush()
                    out.append(_rt(s[i + 1 : close_bracket], link=s[close_bracket + 2 : close_paren]))
                    i = close_paren + 1
                    continue
        buf += s[i]
        i += 1
    flush()
    return out


def heading(level: int, text: str) -> dict:
    key = {1: "heading_1", 2: "heading_2", 3: "heading_3"}[level]
    return {"object": "block", "type": key, key: {"rich_text": _parse(text)}}


def para(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _parse(text)}}


def bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _parse(text)}}


def numbered(text: str) -> dict:
    return {"object": "block", "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": _parse(text)}}


def code(text: str, lang: str = "plain text") -> dict:
    return {"object": "block", "type": "code",
            "code": {"rich_text": [_rt(text)], "language": lang}}


def callout(text: str, emoji: str = "🪸") -> dict:
    return {"object": "block", "type": "callout",
            "callout": {
                "rich_text": _parse(text),
                "icon": {"type": "emoji", "emoji": emoji},
                "color": "gray_background",
            }}


def divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def image(url: str, caption: str = "") -> dict:
    return {"object": "block", "type": "image",
            "image": {"type": "external", "external": {"url": url},
                      "caption": _parse(caption) if caption else []}}


def quote(text: str) -> dict:
    return {"object": "block", "type": "quote",
            "quote": {"rich_text": _parse(text)}}


# ── doc content (no em-dashes; human voice) ────────────────────────────

def build_blocks() -> list[dict]:
    img = lambda name, cap="": image(f"{REPO_RAW}/docs/hykr/{name}", cap)  # noqa: E731

    blocks: list[dict] = []

    # Header
    blocks += [
        callout(
            "**HyKr Build Challenge · MVP submission.** This doc walks a "
            "technical reviewer through what Manthan is, how it is built, "
            "and how to run it. The whole product runs at "
            "[manthan.quest](https://manthan.quest); the code is at "
            "[github.com/akash-mondal/manthan](https://github.com/akash-mondal/manthan).",
            emoji="📄",
        ),
        img("01_system_architecture.jpg",
            "Figure 1. End-to-end view. Triggers on the left land in the API. "
            "Three workers pick rows off the cases queue and either query Coral "
            "(read plane) or call action adapters (write plane)."),
    ]

    # 1. What we built
    blocks += [
        heading(1, "1. What we built"),
        para(
            "Manthan is the operations layer for revenue disputes at B2B "
            "SaaS companies. The moment a chargeback hits Stripe, a refund "
            "request lands at support@, or a teammate mentions Manthan in "
            "Slack, the agent reads across every connected system in one "
            "query, drafts a cited decision brief, and queues the right "
            "actions for one-click human approval."
        ),
        para(
            "A senior billing analyst spends about five hours on a "
            "chargeback. Manthan spends about three minutes. The brief "
            "carries an inline citation chip for every claim it makes, so "
            "the operator can verify any number with one click before "
            "they approve."
        ),
        para(
            "The piece that makes the agent fast and grounded is "
            "**Coral** (the hackathon's sponsor product). Coral exposes "
            "eleven SaaS APIs as Postgres-compatible SQL schemas, so the "
            "agent writes one wide `JOIN` across Stripe, HubSpot, Datadog, "
            "Notion, and friends instead of looping through eleven REST "
            "calls and stitching JSON in-prompt."
        ),
    ]

    # 2. System architecture
    blocks += [
        heading(1, "2. System architecture"),
        para(
            "The system is one API, three workers, one Postgres, one "
            "frontend, and the Coral subprocess. The architecture diagram "
            "above shows the full flow. Here is what each piece does:"
        ),
        heading(3, "Triggers"),
        bullet("**Stripe webhook** at `/api/webhooks/stripe`. Verified with the signing secret, opens a case row immediately."),
        bullet("**Resend inbound** at `/api/webhooks/email`. Parses inbound email at `support@manthan.quest`, attaches it to an existing case or opens a new one."),
        bullet("**Slack mention** at `/api/webhooks/slack`. Picks up `@manthan` mentions in `#billing-ops` and lifts the surrounding context."),
        heading(3, "API · `manthan-api`"),
        para(
            "FastAPI + asyncpg. Holds per-org Postgres schemas: `cases`, "
            "`events`, `findings`, `actions`, `approvals`. Exposes the "
            "frontend SSE feeds (`/api/inbox/stream`, "
            "`/api/cases/:id/stream`) and the human-in-the-loop endpoint "
            "`/api/cases/:id/approve`."
        ),
        heading(3, "Three workers"),
        bullet("`investigate` runs the agent loop for one case at a time. Picks rows off the queue with `SELECT ... FOR UPDATE SKIP LOCKED` so multiple workers across multiple users stay parallel-safe."),
        bullet("`actor` executes approved actions sequentially. Each action is idempotent (Stripe charge ID, Resend message ID, HubSpot note ID) so retries do not double-fire."),
        bullet("`prettifier` listens for raw tool-call events and writes a one-line plain-English summary the UI shows beside the SQL."),
        heading(3, "Two output planes"),
        bullet("**Read plane: Coral.** All read traffic goes through Coral SQL. The investigate worker spawns `coral mcp-stdio` as a subprocess and the agent's `coral_sql` tool dispatches queries through that MCP session. See section 3."),
        bullet("**Write plane: native adapters.** Side effects (Stripe refund, Resend email, HubSpot note, Slack post, Notion block, Linear issue) hit each vendor's HTTP API directly so we can return real `external_ref` IDs to the audit trail. Each adapter ships with a demo-mode fallback so a missing key never breaks a demo."),
    ]

    # 3. Coral
    blocks += [
        heading(1, "3. The Coral data plane"),
        img("02_coral_data_plane.jpg",
            "Figure 2. The agent writes one wide SELECT. Coral fans it out "
            "across eleven schemas and returns one rowset. No per-source "
            "round-trips, no in-prompt JSON stitching."),
        para(
            "Coral is what makes the agent honest. The default pattern for "
            "tool-using LLMs is one API call per source: get_stripe_dispute, "
            "wait, get_hubspot_company, wait, get_datadog_incidents, wait, "
            "then ask the model to make sense of the pile. Manthan refuses "
            "to do that. The system prompt forbids one-shot lookups and "
            "the agent is required to think in joins."
        ),
        heading(3, "How the integration works"),
        numbered("The `investigate` worker spawns the Coral binary with `coral mcp-stdio` and keeps the subprocess open for the duration of the case."),
        numbered("The agent has three tools wired to that MCP session: `coral_list_catalog`, `coral_describe_table`, and `coral_sql`."),
        numbered("When the agent calls `coral_sql`, Coral fans the query out to each referenced upstream (Stripe API, Datadog API, Notion API, etc.), normalises the responses into Postgres-compatible rows, and returns one rowset over the MCP channel."),
        numbered("The worker writes the `(seq, source, sql, rows, ms)` tuple into the events table as a `tool_call` and `tool_result` pair. The frontend's Coral toggle renders this raw feed live, so operators can see exactly what the agent asked."),
        heading(3, "The eleven schemas Coral exposes"),
        para(
            "`stripe`, `salesforce`, `hubspot`, `intercom`, `zendesk`, "
            "`slack`, `notion`, `posthog`, `sentry`, `datadog`, `pagerduty`. "
            "Each schema is a real set of tables (e.g. `stripe.disputes`, "
            "`stripe.charges`, `stripe.subscriptions`) shaped to match the "
            "upstream's data model."
        ),
        heading(3, "What a real query looks like"),
        code(
            "SELECT\n"
            "  -- payments + dispute context\n"
            "  d.id AS dispute_id, d.amount, d.reason, d.evidence_due_by,\n"
            "  ch.id AS charge_id, ch.amount AS charge_amount,\n"
            "  s.id AS subscription_id, s.status AS subscription_status,\n"
            "  c.email AS customer_email, c.name AS customer_name,\n"
            "  (SELECT COUNT(*) FROM stripe.disputes\n"
            "     WHERE customer = d.customer AND id <> d.id) AS prior_disputes_total,\n"
            "\n"
            "  -- CRM context\n"
            "  sf.name AS sf_account, sf.industry, sf.annual_revenue,\n"
            "\n"
            "  -- support history\n"
            "  (SELECT COUNT(*) FROM intercom.conversations\n"
            "     WHERE source_author_email = c.email) AS ic_conversations,\n"
            "\n"
            "  -- platform health correlation\n"
            "  (SELECT COUNT(*) FROM datadog.incidents\n"
            "     WHERE service = 'custom-reports-svc'\n"
            "       AND window @> tstzrange(ch.created, ch.created + interval '7 days')) AS incidents_in_window,\n"
            "\n"
            "  -- documented policy\n"
            "  (SELECT body FROM notion.pages\n"
            "     WHERE title ILIKE '%pro-rata credit%' AND active = TRUE) AS policy_body\n"
            "FROM stripe.disputes d\n"
            "JOIN stripe.charges        ch ON ch.id = d.charge_id\n"
            "LEFT JOIN stripe.subscriptions s ON s.customer = d.customer\n"
            "JOIN stripe.customers      c  ON c.id = d.customer\n"
            "LEFT JOIN salesforce.accounts sf ON sf.website ILIKE '%' || split_part(c.email,'@',2) || '%'\n"
            "WHERE d.id = 'dp_aperture_345478';",
            "sql",
        ),
        para(
            "One query. One round-trip. One rowset that contains every "
            "fact the brief will cite. The agent then calls "
            "`record_finding` for each grounded claim, attaching the row "
            "index that supports it. Those finding records become the "
            "citation chips in the brief."
        ),
    ]

    # 4. Case lifecycle
    blocks += [
        heading(1, "4. Case lifecycle"),
        img("03_case_lifecycle.jpg",
            "Figure 3. A case moves through five states. Workers and one "
            "human drive the transitions; every change is one row in the "
            "events table."),
        para(
            "A case is a row in the `cases` table. It moves through five "
            "states, and every transition is appended to the `events` "
            "table as an immutable row. That events log is the source of "
            "truth for the SSE feed, the audit trail, and the demo "
            "playback. Nothing in the UI is computed from in-memory state."
        ),
        heading(3, "The five states"),
        bullet("**Opened.** A trigger landed; the case row exists; no worker has touched it."),
        bullet("**Investigating.** The `investigate` worker has the row locked. The agent is running, emitting `tool_call` / `tool_result` / `finding_recorded` events as it goes."),
        bullet("**Awaiting approval.** The agent has called `draft_brief()` and `draft_action()` a few times; a brief is ready and the actions are queued. The case sits here until a human clicks Approve."),
        bullet("**Acting.** The `actor` worker is firing the approved actions one by one."),
        bullet("**Resolved.** Every action returned a terminal status. The case is closed; the full event log is preserved."),
        para(
            "Workers coordinate through Postgres alone (no Redis, no "
            "rabbit). Each worker runs the same query: `SELECT ... FROM "
            "cases WHERE status = $1 ORDER BY created_at LIMIT 1 FOR "
            "UPDATE SKIP LOCKED`. Two workers can race on the same row "
            "and only one will hold the lock. This is what makes the "
            "per-Clerk-user workspace isolation work in practice."
        ),
    ]

    # 5. Brief + citations
    blocks += [
        heading(1, "5. The brief and the citation chips"),
        img("04_brief_anatomy.jpg",
            "Figure 4. The brief is a two-column editorial spread. Prose "
            "with inline brand-coloured citation chips on the left. "
            "Drafted actions on the right, with the Approve button at the "
            "bottom."),
        para(
            "When the agent calls `record_finding`, it has to attach a "
            "source: which schema, which row, which column. That tuple "
            "becomes a citation chip in the prose. Click any chip and the "
            "underlying source dashboard opens to the exact record (the "
            "Stripe dispute, the Notion page, the Datadog incident). "
            "There is no fabrication in the brief because there is "
            "nothing in the brief that the agent did not see in a real row."
        ),
        para(
            "Approving the brief switches the canvas into a full-screen "
            "cinematic that walks through each drafted action one at a "
            "time. Each tile shows the source logo, the action title, "
            "and the actual HTTP endpoint being called. When the action "
            "returns its `external_ref`, the tile flips to a green check "
            "and the ref is written to the audit trail."
        ),
    ]

    # 6. Tech stack
    blocks += [
        heading(1, "6. Tech stack"),
        heading(3, "Frontend (`manthan-ui/`)"),
        bullet("React 19 + Vite + TypeScript"),
        bullet("Tailwind v4 for styling, motion/react for the cinematic animations"),
        bullet("Clerk for auth (per-user workspace isolation derived from the Clerk user ID)"),
        bullet("Server-sent events for live inbox + live case streams"),
        heading(3, "Backend (`manthan-api/`)"),
        bullet("FastAPI + asyncpg + PostgreSQL 16"),
        bullet("Three workers as separate `python -m` processes coordinated by `FOR UPDATE SKIP LOCKED`"),
        bullet("Cryptographic signing of every event row (`EVENT_SIGNING_KEY`)"),
        bullet("Per-org schema isolation; each Clerk user gets `usr_<10char_sha256(email)>` as their org"),
        heading(3, "Agent (`agent/`)"),
        bullet("Plain Python loop, no agent framework. About 400 lines."),
        bullet("LLM access via the OpenAI-compatible client pointed at OpenRouter"),
        bullet("Tools: `coral_sql`, `coral_list_catalog`, `coral_describe_table`, `record_finding`, `draft_action`, `draft_brief`"),
        heading(3, "Data plane (`coral`)"),
        bullet("Coral binary built from the sibling Coral repo (Rust)"),
        bullet("Spawned per-investigation as `coral mcp-stdio`"),
        bullet("Eleven schemas exposed as pg-compatible SQL"),
        heading(3, "Models (all via OpenRouter)"),
        bullet("Investigator + chat: `x-ai/grok-build-0.1`"),
        bullet("Tool-call prettifier (the live one-line summaries): `inception/mercury-2`"),
        bullet("Story image generation (demo overlays): `google/gemini-3.1-flash-image-preview`"),
        heading(3, "External services"),
        bullet("Stripe (payments + disputes)"),
        bullet("Resend (transactional + inbound email)"),
        bullet("HubSpot (CRM notes)"),
        bullet("Slack (ops notifications)"),
        bullet("Notion (policy + resolution blocks)"),
        bullet("Linear (escalation issues)"),
    ]

    # 7. Repo layout
    blocks += [
        heading(1, "7. Repo layout"),
        code(
            "manthan/\n"
            "├── manthan-api/          FastAPI service + 3 workers + Postgres schema\n"
            "│   └── src/manthan_api/\n"
            "│       ├── main.py       app factory, SSE routes, webhook handlers\n"
            "│       ├── workers/      investigate.py, actor.py, prettifier.py\n"
            "│       └── adapters/     stripe, resend, hubspot, slack, notion, linear\n"
            "├── manthan-ui/           React 19 + Vite + Tailwind v4\n"
            "│   └── src/\n"
            "│       ├── pages/        Landing, Inbox, Workspace, drafts/*\n"
            "│       ├── components/   AppShell, BriefCanvas, ApprovalCinematic\n"
            "│       └── lib/          api.ts, useCaseEvents.ts, useInboxStream.ts\n"
            "├── agent/                the agent brain (imported by manthan-api as a lib)\n"
            "│   └── src/manthan_agent/\n"
            "│       ├── loop.py       the loop: list_catalog → sql → reflexion → brief\n"
            "│       ├── prompts.py    the join-don't-loop system prompt\n"
            "│       ├── tools.py      coral_sql, record_finding, draft_action, ...\n"
            "│       └── coral_session.py  MCP/stdio subprocess manager\n"
            "├── infra/vps/            Caddy + cloud-init + setup.sh for the live VPS\n"
            "├── scripts/              fly secrets bootstrap, this docs generator\n"
            "├── docs/hykr/            the four diagrams embedded above\n"
            "├── DEPLOY.md             Fly.io + Vercel deploy runbook\n"
            "├── DEMO_RUNBOOK.md       what we say during a live pitch\n"
            "└── README.md             public README on GitHub",
            "plain text",
        ),
    ]

    # 8. Deployment
    blocks += [
        heading(1, "8. Deployment"),
        para(
            "Manthan ships as one API + three workers + one Postgres + a "
            "Vite static frontend + the Coral subprocess. There are two "
            "production-grade paths."
        ),
        heading(3, "VPS (what runs at manthan.quest)"),
        bullet("Single DigitalOcean droplet, 4 GB RAM"),
        bullet("Postgres in Docker on port 5433"),
        bullet("Four systemd units: `manthan-api`, `manthan-investigate`, `manthan-actor`, `manthan-prettifier`"),
        bullet("Caddy as a reverse proxy with auto-TLS via Let's Encrypt"),
        bullet("Coral binary at `/usr/local/bin/coral`, built from source on the box"),
        bullet("Setup is reproducible: `infra/vps/cloud-init.yaml` + `infra/vps/setup.sh`"),
        heading(3, "Fly.io + Vercel (alternate)"),
        bullet("Frontend on Vercel (zero-config Vite build)"),
        bullet("API + workers on Fly.io as a single app with four processes"),
        bullet("Fly Postgres attached automatically"),
        bullet("Full runbook in [`DEPLOY.md`](https://github.com/akash-mondal/manthan/blob/main/DEPLOY.md)"),
    ]

    # 9. Quick start
    blocks += [
        heading(1, "9. Running it locally"),
        code(
            "git clone https://github.com/akash-mondal/manthan\n"
            "cd manthan\n"
            "\n"
            "# 1. environment\n"
            "cp manthan-api/.env.example manthan-api/.env\n"
            "cp agent/.env.example      agent/.env\n"
            "# fill in OPENROUTER_API_KEY, CORAL_BINARY, STRIPE_API_KEY,\n"
            "# RESEND_API_KEY, HUBSPOT_ACCESS_TOKEN, SLACK_TOKEN,\n"
            "# NOTION_TOKEN, CLERK_*\n"
            "\n"
            "# 2. Postgres\n"
            "docker compose -f manthan-api/docker-compose.yml up -d postgres\n"
            "\n"
            "# 3. backend (API + 3 workers)\n"
            "cd manthan-api && uv sync\n"
            "uv run uvicorn manthan_api.main:app --reload --port 8765 &\n"
            "uv run python -m manthan_api.workers.investigate &\n"
            "uv run python -m manthan_api.workers.actor        &\n"
            "uv run python -m manthan_api.workers.prettifier   &\n"
            "\n"
            "# 4. frontend\n"
            "cd ../manthan-ui && npm install && npm run dev",
            "shell",
        ),
        para(
            "Then open [localhost:5173](http://localhost:5173), sign in "
            "with Clerk, and click **Stripe Chargeback** on the empty "
            "inbox. That fires the canonical Aperture demo: an $8,400 "
            "dispute Manthan resolves to a $560 partial credit by "
            "cross-referencing Datadog incidents and the Notion "
            "pro-rata-credit policy."
        ),
    ]

    # 10. Links
    blocks += [
        heading(1, "10. Links for the reviewer"),
        bullet("**Live MVP:** [manthan.quest](https://manthan.quest)"),
        bullet("**GitHub repo:** [github.com/akash-mondal/manthan](https://github.com/akash-mondal/manthan)"),
        bullet("**README (the public overview):** [README.md](https://github.com/akash-mondal/manthan/blob/main/README.md)"),
        bullet("**Deploy runbook:** [DEPLOY.md](https://github.com/akash-mondal/manthan/blob/main/DEPLOY.md)"),
        bullet("**Demo runbook:** [DEMO_RUNBOOK.md](https://github.com/akash-mondal/manthan/blob/main/DEMO_RUNBOOK.md)"),
        divider(),
        para(
            "Questions or evaluator credentials needed for a deeper look: "
            "reach out at hitakshi@miny-labs.com."
        ),
    ]

    return blocks


def main() -> int:
    blocks = build_blocks()
    print(f"→ building {len(blocks)} blocks")

    title = f"Manthan · Technical Documentation (HyKr · {date.today():%b %-d, %Y})"

    # Create page with the first 100 blocks inline (Notion's create-page
    # limit is 100 children).
    initial_chunk = blocks[:100]
    rest = blocks[100:]
    create_body = {
        "parent": {"page_id": PARENT_PAGE_ID},
        "properties": {
            "title": [{"type": "text", "text": {"content": title}}],
        },
        "icon": {"type": "emoji", "emoji": "📄"},
        "children": initial_chunk,
    }
    page = request("POST", "/pages", create_body)
    page_id = page["id"]
    page_url = page.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")
    print(f"  ✓ created page  ({len(initial_chunk)} blocks inline)")

    # Append the remaining blocks in chunks of 100.
    while rest:
        chunk, rest = rest[:100], rest[100:]
        request("PATCH", f"/blocks/{page_id}/children", {"children": chunk})
        print(f"  ✓ appended {len(chunk)} more blocks ({len(rest)} remaining)")

    print()
    print("Done.")
    print(f"  URL: {page_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
