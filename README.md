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
  <a href="#features"><strong>Features</strong></a> ·
  <a href="#quick-start"><strong>Quick start</strong></a> ·
  <a href="#architecture"><strong>Architecture</strong></a> ·
  <a href="#tech-stack"><strong>Tech stack</strong></a> ·
  <a href="#self-hosting"><strong>Self-host</strong></a> ·
  <a href="#contributing"><strong>Contributing</strong></a>
</p>

<p align="center">
  <a href="https://github.com/miny-labs/manthan/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://github.com/miny-labs/manthan/stargazers"><img src="https://img.shields.io/github/stars/miny-labs/manthan?style=flat&logo=github" alt="Stars"></a>
  <a href="https://github.com/miny-labs/manthan/pulse"><img src="https://img.shields.io/github/commit-activity/m/miny-labs/manthan?style=flat&logo=github" alt="Commits per month"></a>
  <a href="https://github.com/miny-labs/manthan/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs welcome"></a>
  <a href="https://twitter.com/manthan_quest"><img src="https://img.shields.io/twitter/follow/manthan_quest?style=flat&label=%40manthan_quest&logo=twitter&color=0bf&logoColor=fff" alt="Twitter"></a>
</p>

## About Manthan

Manthan is the autonomous investigator for B2B SaaS billing operations. The moment a chargeback hits Stripe, a refund request lands in your inbox, or a customer @-mentions you in Slack, Manthan reads across **every connected system** - Stripe, HubSpot, Datadog, Notion, Intercom, Zendesk, Slack, PostHog - drafts a **cited decision brief**, and queues the right actions (refunds, dispute responses, customer emails, CRM notes, Slack posts) for one-click human approval.

A senior analyst spends 5 hours on a chargeback. Manthan spends 3 minutes.

The data layer is [**Coral**](https://coral.dev), a unified SQL surface over the 8 vendors above - the agent literally writes `SELECT * FROM stripe.disputes JOIN hubspot.companies ON …` and gets one rowset back, no per-API integration code. Every claim in the brief is grounded in a citation chip that links back to the underlying record; click it to open the source dashboard.

## How it works

| Stage | What happens |
|---|---|
| **1 · Trigger** | Stripe webhook fires → customer emails support → teammate @-mentions Manthan in Slack. The agent picks it up the moment the event lands. |
| **2 · Investigate** | The agent queries every connected source in parallel via Coral SQL, surfaces facts with citations, and writes a live narrative you can watch in real time. |
| **3 · Brief** | A two-paragraph executive memo with the math shown, every number cited back to a source record. |
| **4 · Decide** | Recommends refund / fight / partial-credit / escalate, and **drafts the actions** (Stripe refund, dispute response, customer email, HubSpot note, Slack post). |
| **5 · Approve** | One click. Each action fires against the real systems in a sequential cinematic - refund posts to Stripe, email lands in the inbox, HubSpot note appears, Slack pings. |

## Features

- 🧠 **Cross-source investigation.** Coral exposes Stripe, HubSpot, Salesforce, Zendesk, Intercom, Slack, Notion, PostHog, Sentry, Datadog, PagerDuty, Resend as queryable SQL schemas. The agent writes joins across all of them in a single query.
- 📑 **Cited brief.** Every claim in the postmortem carries a citation chip linking back to the underlying record (Stripe dispute, Notion page, Datadog incident). No fabrication - if it's in the brief, it's in a source.
- 🔴 **Live cinematic investigation.** Watch the agent query each source in real time, with brand glyphs inline in the narrative ("Manthan is asking 🟢 Intercom") and a running list of facts it surfaces.
- ✋ **Human-in-the-loop approval.** Operator reviews the brief, approves with one click, and watches each action fire in a full-screen cinematic with per-action status, external-ref links, and graceful demo-mode fallbacks when a source isn't fully wired.
- ✉️ **Branded customer emails.** Templated HTML emails (table-based for Outlook/Gmail compat) with summary cards, branded header, and policy-grounded reasoning - never the raw decision rationale.
- 🔒 **Per-user workspace isolation.** Every Clerk-authenticated user gets their own isolated org. Two operators can run investigations in parallel against the same demo data without seeing each other's cases.
- 📖 **Editorial UI.** The whole product reads like a magazine spread - Spectral serif, hairline rules, brand-colored source pills, Geist Mono for the data - not a SaaS dashboard.
- 🔌 **Demo-mode adapters.** All four side-effecting adapters (Stripe / HubSpot / Slack / Linear) ship with graceful fallbacks so demos always show green even when a key is missing or a Stripe charge is already disputed.

## Quick start

### Prerequisites
- Node 20+ · `pnpm` or `bun`
- Python 3.12+ · [`uv`](https://github.com/astral-sh/uv)
- Docker (for the local Postgres)
- `ffmpeg` (only for regenerating story-slide images - optional)

### Setup
```sh
git clone https://github.com/miny-labs/manthan
cd manthan

# 1 · Environment
cp .env.example .env
cp manthan-api/.env.example manthan-api/.env
cp agent/.env.example agent/.env
# → fill in OPENROUTER_API_KEY, STRIPE_API_KEY, RESEND_API_KEY,
#   HUBSPOT_ACCESS_TOKEN, SLACK_TOKEN, CLERK_*

# 2 · Database
docker compose up -d postgres
uv run python -m manthan_api.scripts.bootstrap_dev_org

# 3 · Backend (API + 3 workers)
cd manthan-api && uv sync
uv run uvicorn manthan_api.main:app --reload --port 8765 &
uv run python -m manthan_api.workers.investigate &
uv run python -m manthan_api.workers.actor        &
uv run python -m manthan_api.workers.prettifier   &

# 4 · Frontend
cd ../manthan-ui && pnpm install && pnpm dev
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
       │   Coral    │    │  Adapters            │
       │ (MCP/stdio)│    │  • Stripe  · refunds │
       │            │    │  • Stripe  · disputes│
       │ Unified SQL│    │  • Resend  · emails  │
       │ over 8     │    │  • HubSpot · notes   │
       │ sources    │    │  • Slack   · posts   │
       │ (read-only)│    │  • Linear  · issues  │
       └────────────┘    └──────────────────────┘
```

## Tech stack

**Frontend**
- [React 19](https://react.dev) + [Vite](https://vite.dev) + [TypeScript](https://typescriptlang.org)
- [Tailwind v4](https://tailwindcss.com) for styling, [motion/react](https://motion.dev) for animation
- [Clerk](https://clerk.com) for auth
- [Vercel](https://vercel.com) for hosting

**Backend**
- [FastAPI](https://fastapi.tiangolo.com) + [asyncpg](https://github.com/MagicStack/asyncpg)
- [PostgreSQL](https://www.postgresql.org) as the system-of-record (cases, events, findings, actions)
- [Coral](https://coral.dev) as the unified data layer over 8 SaaS sources
- [Fly.io](https://fly.io) for hosting

**LLM / models** (all via [OpenRouter](https://openrouter.ai))
- **Investigator + chat agent**: `x-ai/grok-build-0.1`
- **Tool-call summarizer (prettifier)**: `inception/mercury-2`
- **Story-image generation**: `google/gemini-3.1-flash-image-preview`

**External services**
- [Stripe](https://stripe.com) · payments + disputes
- [Resend](https://resend.com) · transactional email
- [HubSpot](https://hubspot.com) · CRM notes
- [Slack](https://slack.com) · ops notifications

## Self-hosting

Manthan is designed to be deployed as 1 API + 3 workers + a Postgres + a Vite static frontend. See [`DEPLOY.md`](./DEPLOY.md) for the full Fly.io + Vercel runbook, including machine sizing, Postgres backups, Clerk webhook configuration, and Coral binary setup.

For a one-shot demo run, [`DEMO_RUNBOOK.md`](./DEMO_RUNBOOK.md) walks the exact sequence we use during live pitches.

## Contributing

Issues and PRs welcome - start with a [help-wanted issue](https://github.com/miny-labs/manthan/labels/help%20wanted) or open a discussion. A formal `CONTRIBUTING.md` is on the way; in the meantime:

- Run `pnpm typecheck` in `manthan-ui/` before pushing
- Run `uv run pytest` in `manthan-api/` and `agent/`
- Keep PRs scoped to a single concern; we squash-merge

## Security

If you find a security vulnerability, please email **security@miny-labs.com** directly - do not file a public issue. We'll acknowledge within 48 hours.

## Community

- 💬 [Discord](https://discord.gg/manthan) - chat with the team and other operators
- 🐦 [@manthan_quest](https://twitter.com/manthan_quest) - release notes + product clips
- 📨 [hello@miny-labs.com](mailto:hello@miny-labs.com) - design partnerships, customer ops, anything else

## License

Manthan is open-source under the [Apache 2.0](./LICENSE) license. The hosted version at [manthan.quest](https://manthan.quest) ships the same code with managed Coral connections, OAuth onboarding, and Clerk-issued workspaces.

---

<sub>Built by <a href="https://miny-labs.com">miny-labs</a> · Made with 🪸 Coral</sub>
