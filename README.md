<p align="center">
  <a href="https://manthan.quest">
    <img src="docs/banner.png" alt="Manthan - the operations layer for revenue disputes" />
  </a>
</p>

<h3 align="center">Manthan</h3>

<p align="center">
  The operations layer for revenue disputes.
  <br />
  Settles chargebacks, refund requests, and failed payments in minutes - not days.
  <br /><br />
  <a href="https://manthan.quest"><strong>manthan.quest »</strong></a>
  <br /><br />
  <a href="#about-manthan"><strong>About</strong></a> ·
  <a href="#how-it-works"><strong>How it works</strong></a> ·
  <a href="#the-coral-data-plane"><strong>Coral</strong></a> ·
  <a href="#sources"><strong>Sources</strong></a> ·
  <a href="#features"><strong>Features</strong></a> ·
  <a href="#quick-start"><strong>Quick start</strong></a> ·
  <a href="#architecture"><strong>Architecture</strong></a> ·
  <a href="#self-hosting"><strong>Self-host</strong></a>
</p>

<p align="center">
  <a href="https://github.com/akash-mondal/manthan/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://github.com/akash-mondal/manthan/stargazers"><img src="https://img.shields.io/github/stars/akash-mondal/manthan?style=flat&logo=github" alt="Stars"></a>
  <a href="https://github.com/akash-mondal/manthan/pulse"><img src="https://img.shields.io/github/commit-activity/m/akash-mondal/manthan?style=flat&logo=github" alt="Commits per month"></a>
  <a href="https://github.com/akash-mondal/manthan/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs welcome"></a>
</p>

## About Manthan

Manthan is the autonomous investigator for B2B SaaS billing operations. The moment a chargeback hits Stripe, a refund request lands in your support inbox, or a teammate `@-mentions` Manthan in Slack, the agent reads across **every connected system in one query**, drafts a **cited decision brief**, and queues the right actions for one-click human approval.

A senior analyst spends 5 hours on a chargeback. Manthan spends 3 minutes.

The work happens on top of [**Coral**](https://coral.dev) - a unified Postgres-compatible SQL surface over 11 SaaS schemas. Instead of integrating 11 vendor SDKs and stitching results in Python, the agent writes one wide `SELECT` that joins Stripe + Salesforce + HubSpot + Intercom + Zendesk + Slack + Notion + PostHog + Sentry + Datadog + PagerDuty, gets one rowset back, and grounds every claim in the brief with a citation that links back to the underlying record. Click any citation chip and the source dashboard opens to the exact row.

## How it works

| Stage | What happens |
|---|---|
| **1 · Trigger** | Stripe webhook fires · customer email lands at support@ · teammate `@-mentions` Manthan in Slack. The agent picks it up the moment the event lands. |
| **2 · Investigate** | The agent issues 3-6 Coral queries to pull every relevant fact in parallel, surfaces findings with citations, and emits a live narrative you can watch in real time. |
| **3 · Brief** | A two-paragraph executive memo with the math shown, every number cited back to a source record. |
| **4 · Decide** | Recommends refund / fight / partial-credit / escalate, then **drafts the actions** (Stripe refund, dispute response, customer email, HubSpot note, Slack post). |
| **5 · Approve** | One click. Each action fires against the real systems in a sequential cinematic - refund posts to Stripe, email lands in the inbox, HubSpot note appears, Slack pings. |

## The Coral data plane

Coral is what makes Manthan possible. It exposes 11 SaaS APIs as Postgres-compatible SQL schemas and ships as a single Rust binary the agent speaks to over [MCP](https://modelcontextprotocol.io) (Model Context Protocol) stdio.

**Why this matters.** The "default" autonomous-agent pattern is 1 round-trip per source - the LLM calls `get_stripe_dispute`, waits, calls `get_hubspot_company`, waits, calls `get_datadog_incidents`, waits, then tries to stitch JSON in its head. Manthan refuses to do that. The system prompt explicitly forbids one-shot lookups; the agent is required to **think in joins**:

```sql
-- The kind of query the agent actually writes (abridged):
SELECT
  -- payments + dispute context
  d.id AS dispute_id, d.amount, d.reason, d.evidence_due_by,
  ch.id AS charge_id, ch.created AS charge_created, ch.amount AS charge_amount,
  s.id AS subscription_id, s.status AS subscription_status, s.cancel_at_period_end,
  c.email AS customer_email, c.name AS customer_name,
  (SELECT COUNT(*) FROM stripe.disputes
     WHERE customer = d.customer AND id <> d.id) AS prior_disputes_total,

  -- CRM context
  sf.name AS sf_account, sf.industry, sf.annual_revenue, sf.billing_country,

  -- support history
  (SELECT COUNT(*) FROM intercom.conversations
     WHERE source_author_email = c.email) AS ic_conversations,
  (SELECT source_subject FROM intercom.conversations
     WHERE source_author_email = c.email
     ORDER BY created_at DESC LIMIT 1) AS ic_latest_subject,

  -- platform-health correlation (was there an outage during the disputed window?)
  (SELECT COUNT(*) FROM datadog.incidents
     WHERE service = 'custom-reports-svc'
       AND window @> tstzrange(ch.created, ch.created + interval '7 days')) AS incidents_in_window,

  -- documented policy
  (SELECT body FROM notion.pages
     WHERE title ILIKE '%pro-rata credit%' AND active = TRUE) AS policy_body
FROM stripe.disputes d
JOIN stripe.charges        ch ON ch.id = d.charge_id
LEFT JOIN stripe.subscriptions s ON s.customer = d.customer
JOIN stripe.customers      c  ON c.id = d.customer
LEFT JOIN salesforce.accounts sf ON sf.website ILIKE '%' || split_part(c.email,'@',2) || '%'
WHERE d.id = 'dp_aperture_345478';
```

One query. One round-trip. One rowset that contains everything needed to write the brief.

**How the integration works.**

1. `manthan-api` (the investigate worker) spawns the Coral binary as a subprocess via `coral mcp-stdio`.
2. The agent's `coral_sql`, `coral_list_catalog`, and `coral_describe_table` tools dispatch through that MCP session.
3. Coral fans the SQL out to each upstream API, normalizes results into Postgres-compatible rows, and returns one rowset.
4. Each query's `(seq, source, sql, rows, ms)` is recorded as an event; the Workspace's **Coral mode** renders the raw SQL feed alongside the prettified prose so operators can see exactly what the agent asked.

The agent code lives in [`agent/`](./agent) - a small Python loop (~hundreds of LOC, no framework) wired straight to OpenRouter. The Coral binary is built from the sibling [`coral`](https://github.com/coral-dev/coral) repo.

## Sources

**Read sources** - queried by the agent via Coral SQL:

| Schema | Tables used | What it grounds in the brief |
|---|---|---|
| `stripe`     | `disputes`, `charges`, `customers`, `subscriptions`, `refunds`, `invoices` | Payment + dispute facts, prior-dispute counts, subscription health |
| `salesforce` | `accounts`, `opportunities`, `contacts` | Customer-tier + revenue context |
| `hubspot`    | `companies`, `contacts`, `deals`, `notes` | ARR, tier, owner, prior notes |
| `intercom`   | `conversations`, `contacts` | Support history, recent subjects |
| `zendesk`    | `tickets`, `users` | Open tickets, priority history |
| `slack`      | `channels`, `messages` | Internal mentions, ops-channel context |
| `notion`     | `pages`, `blocks` | Policy docs, runbooks, post-mortems |
| `posthog`    | `events`, `persons` | Feature-usage signals during the disputed window |
| `sentry`     | `events`, `issues` | App errors correlated with the customer's session |
| `datadog`    | `incidents`, `metrics` | Service outages during the disputed window |
| `pagerduty`  | `incidents`, `users` | On-call history + ack/resolve timestamps |

**Write / action adapters** - hit by the actor worker after operator approval, implemented natively (not via Coral) so we can return real `external_ref` IDs and idempotency keys:

| Adapter | Action |
|---|---|
| `stripe`  | `POST /v1/refunds`, `POST /v1/disputes/{id}/evidence` |
| `resend`  | `POST /emails` (templated, branded HTML; table-based for Outlook/Gmail compat) |
| `hubspot` | `POST /crm/v3/objects/companies/{id}/notes` |
| `slack`   | `chat.postMessage` to `#billing-ops` |
| `notion`  | Append resolution block to the case page |
| `linear`  | Open an issue when the agent escalates (low-confidence or out-of-policy cases) |

Each adapter ships with a graceful demo-mode fallback so demos always show green even when a key is missing or a Stripe charge is already disputed.

## Features

- 🧠 **One-query investigations.** Coral exposes 11 SaaS schemas as Postgres-compatible SQL. The agent writes wide joins across them in a single round-trip, never per-source lookups.
- 📑 **Cited brief.** Every claim in the postmortem carries a citation chip linking back to the underlying record (Stripe dispute, Notion page, Datadog incident). No fabrication - if it's in the brief, it's in a source.
- 🔴 **Live investigation cinematic.** Watch the agent query each source in real time, with brand glyphs inline in the narrative ("Manthan is asking 🟢 Intercom") and a running list of facts. Toggle the Coral panel to see the raw SQL feed.
- ✋ **Human-in-the-loop approval.** Operator reviews the brief, approves with one click, watches each action fire in a full-screen cinematic with per-action status, external-ref links, and graceful demo-mode fallbacks.
- ✉️ **Branded customer emails.** Templated HTML emails (table-based for Outlook/Gmail compat) with summary cards, branded header, and policy-grounded reasoning - never the raw decision rationale.
- 🔒 **Per-user workspace isolation.** Every Clerk-authenticated user gets their own isolated org. Two operators can run investigations in parallel against the same demo data without seeing each other's cases.
- 📖 **Editorial UI.** The whole product reads like a magazine spread - Spectral serif, hairline rules, brand-colored source pills, Geist Mono for the data - not a SaaS dashboard.

## Quick start

### Prerequisites
- Node 20+ · `pnpm` or `npm`
- Python 3.12+ · [`uv`](https://github.com/astral-sh/uv)
- Docker (for the local Postgres)
- The [Coral binary](https://github.com/coral-dev/coral) built and on your `PATH` (or available at `./coral/target/release/coral`)

### Setup
```sh
git clone https://github.com/akash-mondal/manthan
cd manthan

# 1 · Environment - fill in OPENROUTER_API_KEY, CORAL_BINARY,
#                   STRIPE_API_KEY, RESEND_API_KEY, HUBSPOT_ACCESS_TOKEN,
#                   SLACK_TOKEN, NOTION_TOKEN, CLERK_*
cp .env.example .env
cp manthan-api/.env.example manthan-api/.env
cp agent/.env.example agent/.env

# 2 · Database
docker compose -f manthan-api/docker-compose.yml up -d postgres

# 3 · Backend (API + 3 workers)
cd manthan-api && uv sync
uv run uvicorn manthan_api.main:app --reload --port 8765 &
uv run python -m manthan_api.workers.investigate &
uv run python -m manthan_api.workers.actor        &
uv run python -m manthan_api.workers.prettifier   &

# 4 · Frontend
cd ../manthan-ui && npm install && npm run dev
```

Visit **[http://localhost:5173](http://localhost:5173)**, sign in via Clerk, then click **Stripe Chargeback** on the empty-inbox hero to fire the canonical Aperture demo (an $8,400 dispute that resolves to a $560 partial credit).

## Architecture

```
       │  Stripe / Email / Slack
       │  webhook · inbound · @-mention
       ▼
┌────────────────────────────────────────────────────────────────┐
│   manthan-api  ·  FastAPI + asyncpg                            │
│   • cases / events / findings / actions  (per-org PG schema)   │
│   • per-Clerk-user workspace isolation                         │
│   • SSE streams: /api/inbox/stream, /api/cases/:id/stream      │
└──────────────┬─────────────────┬────────────────┬──────────────┘
               │                 │                │
               ▼                 ▼                ▼
        ┌────────────┐    ┌────────────┐   ┌────────────┐
        │ investigate│    │   actor    │   │ prettifier │
        │   worker   │    │   worker   │   │   worker   │
        │            │    │            │   │            │
        │ runs agent │    │ executes   │   │ summarizes │
        │ loop, draft│    │ approved   │   │ tool calls │
        │ brief +    │    │ actions    │   │ for the    │
        │ findings   │    │ idempotently│  │ live trace │
        └─────┬──────┘    └─────┬──────┘   └────────────┘
              │                 │
              ▼                 ▼
       ┌────────────┐    ┌──────────────────────┐
       │   Coral    │    │  Action adapters     │
       │ (MCP/stdio)│    │  • Stripe · refunds  │
       │            │    │  • Stripe · disputes │
       │ 11 SaaS as │    │  • Resend · emails   │
       │  pg-SQL    │    │  • HubSpot · notes   │
       │ (read-only)│    │  • Slack  · posts    │
       │            │    │  • Notion · blocks   │
       │            │    │  • Linear · issues   │
       └────────────┘    └──────────────────────┘
```

## Tech stack

**Frontend** · [React 19](https://react.dev) + [Vite](https://vite.dev) + [TypeScript](https://typescriptlang.org) · [Tailwind v4](https://tailwindcss.com) · [motion/react](https://motion.dev) · [Clerk](https://clerk.com) auth · deployable to Vercel or a static host.

**Backend** · [FastAPI](https://fastapi.tiangolo.com) + [asyncpg](https://github.com/MagicStack/asyncpg) · [PostgreSQL](https://www.postgresql.org) (cases, events, findings, actions) · 3 background workers (`investigate`, `actor`, `prettifier`) coordinated via `FOR UPDATE SKIP LOCKED`.

**Agent** · `agent/` is a ~hundreds-of-LOC Python loop (no framework) over the [OpenAI-compat](https://platform.openai.com/docs/api-reference) client pointed at [OpenRouter](https://openrouter.ai). Tools: `coral_sql`, `coral_list_catalog`, `coral_describe_table`, `record_finding`, `draft_action`, `draft_brief`.

**Data plane** · [Coral](https://coral.dev) - Rust binary, MCP/stdio bridge, 11 SaaS schemas as Postgres SQL.

**Models** (all via OpenRouter)
- Investigator + chat: `x-ai/grok-build-0.1`
- Tool-call summarizer (the live "prettifier"): `inception/mercury-2`
- Story-image generation: `google/gemini-3.1-flash-image-preview`

**External services** · [Stripe](https://stripe.com) (payments + disputes) · [Resend](https://resend.com) (transactional + inbound email) · [HubSpot](https://hubspot.com) (CRM notes) · [Slack](https://slack.com) (ops notifications) · [Notion](https://notion.so) (policy + resolution blocks) · [Linear](https://linear.app) (escalation issues).

## Self-hosting

Manthan ships as 1 API + 3 workers + a Postgres + a Vite static frontend + the Coral subprocess. Two paths:

- **VPS** (single-box) - see [`infra/vps/`](./infra/vps) for the Caddy config, cloud-init, and setup script. This is what runs at [manthan.quest](https://manthan.quest).
- **Fly.io + Vercel** - see [`DEPLOY.md`](./DEPLOY.md) for the multi-app runbook: Fly for API + workers + Postgres, Vercel for the frontend, Resend inbound for `support@`.

## Contributing

Issues and PRs welcome. Before pushing:

- `cd manthan-ui && npm run typecheck`
- `cd manthan-api && uv run pytest`
- `cd agent && uv run pytest`

Keep PRs scoped to a single concern; we squash-merge.

## License

Apache 2.0 - see [`LICENSE`](./LICENSE). The hosted version at [manthan.quest](https://manthan.quest) ships the same code with managed Coral connections, OAuth onboarding, and Clerk-issued workspaces.

---

<sub>Built by <a href="https://miny-labs.com">miny-labs</a> · Made with 🪸 Coral</sub>
