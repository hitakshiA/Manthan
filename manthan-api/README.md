# manthan-api

Multi-tenant backend for Manthan: the HTTP surface, the three background
workers, and the action-adapter layer around the agent brain. Speaks
to `manthan-ui` over JSON + SSE and imports `manthan-agent` as a
library.

## Quick start (local dev)

```bash
# 1. Start Postgres
docker compose up -d postgres

# 2. Install Python deps with uv
uv sync

# 3. Copy + edit env
cp .env.example .env
# fill in OPENROUTER_API_KEY, CLERK_*, STRIPE_*, SLACK_*, RESEND_*, CORAL_BINARY

# 4. Apply the schema (only the first time)
docker exec -i manthan-postgres psql -U manthan -d manthan \
    < schema/001_initial.sql
docker exec -i manthan-postgres psql -U manthan -d manthan \
    < schema/002_event_summary.sql
docker exec -i manthan-postgres psql -U manthan -d manthan \
    < schema/003_policy_engine.sql
docker exec -i manthan-postgres psql -U manthan -d manthan \
    < schema/004_citation_reasonings.sql
docker exec -i manthan-postgres psql -U manthan -d manthan \
    < schema/005_auth_signups.sql

# 5. Seed a dev org + admin member
uv run python -m manthan_api.scripts.bootstrap_dev_org

# 6. Run the API + the three workers (each in its own terminal, or all
#    backgrounded - production uses systemd for these)
uv run uvicorn manthan_api.main:app --reload --port 8000
uv run python -m manthan_api.workers.investigate
uv run python -m manthan_api.workers.actor
uv run python -m manthan_api.workers.prettifier
```

Verify:

```bash
curl http://localhost:8000/healthz
# {"status":"ok","version":"0.1.0"}

curl http://localhost:8000/readyz
# {"status":"ready","db":true,"version":"0.1.0"}

curl -H "X-Manthan-Dev-Org: acme" http://localhost:8000/api/cases
# {"cases":[],"total":0}
```

## Layout

```
manthan-api/
├── pyproject.toml
├── docker-compose.yml           # local Postgres + the API container
├── schema/                      # forward-only PG migrations
│   ├── 001_initial.sql          # orgs, members, cases, events, findings, actions
│   ├── 002_event_summary.sql    # prettifier output cache
│   ├── 003_policy_engine.sql    # policy_rules + match log
│   ├── 004_citation_reasonings.sql
│   └── 005_auth_signups.sql     # waitlist for the hosted version
└── src/manthan_api/
    ├── main.py                  # FastAPI app entry, router wiring
    ├── config.py                # env-driven settings
    ├── db.py                    # asyncpg pool + JSONB codec
    ├── models.py                # Pydantic request/response shapes
    ├── api/                     # HTTP routers
    │   ├── health.py            #   /healthz · /readyz
    │   ├── me.py                #   /api/me  (Clerk-resolved tenant)
    │   ├── inbox.py             #   /api/inbox/stream  (SSE)
    │   ├── cases.py             #   /api/cases · /api/cases/{id}
    │   ├── actions.py           #   /api/cases/{id}/approve · /hold · /deny
    │   ├── events.py            #   /api/cases/{id}/events  (SSE)
    │   ├── chat.py              #   /api/cases/{id}/chat  (followup)
    │   ├── policy.py            #   policy CRUD + match history
    │   ├── audit.py             #   /api/audit
    │   ├── citations.py         #   citation deep-links
    │   ├── narrative.py         #   live prettified trace
    │   ├── memory.py            #   per-org knowledge memory
    │   ├── metrics.py           #   counters for the inbox header
    │   ├── demo.py              #   POST /api/demo/scenarios/trigger (aperture)
    │   ├── demo_v2.py           #   guided autonomous-email wizard
    │   ├── demo_v3.py           #   guided Slack-mention wizard
    │   ├── email_webhook.py     #   /api/webhooks/email/{org}  (Resend inbound)
    │   └── clerk_webhook.py     #   /api/webhooks/clerk        (member sync)
    ├── middleware/
    │   └── tenant.py            # org + member resolver (Clerk + dev bypass)
    ├── workers/
    │   ├── main.py              #   shared LISTEN loop helpers
    │   ├── investigate.py       #   drives the agent loop, projects events
    │   ├── actor.py             #   drains approved actions to the adapters
    │   ├── prettifier.py        #   generates event summaries for the UI
    │   └── chat_loop.py         #   handles human-followup turns post-brief
    ├── adapters/                # external-write integrations (not via Coral)
    │   ├── stripe.py            #   refunds + dispute evidence
    │   ├── hubspot.py           #   CRM notes
    │   ├── slack.py             #   chat.postMessage + thread replies
    │   ├── resend.py            #   templated transactional email
    │   └── notion.py            #   appended resolution blocks
    ├── services/                # cross-router helpers (slack_bot, brief PDF…)
    └── scripts/                 # bootstrap_dev_org, seeders, one-shots
```

## Architecture

The events table is the single source of truth (12-Factor Agents #3
and #5: events drive everything, state is derived). Workers
`LISTEN manthan_event` and react. Projection tables (`cases`,
`actions`, `findings`, `event_summary`) are updated by the same
workers that emit the events. The frontend reads from projection
tables; the audit log reads from `events` directly.

Three workers, one API:

| Worker | Job |
|---|---|
| `manthan-investigate` | Picks up new cases, drives the agent loop in [`agent/`](../agent), persists each agent event back to PG, materializes drafted_actions into the actions table. |
| `manthan-actor` | Drains approved actions from the actions queue, dispatches to the adapter (`stripe.py`, `resend.py`, etc.), records the external_ref + status. Idempotent via `actions.idempotency_key`. |
| `manthan-prettifier` | Walks unsummarized events (tool_call / tool_result / finding_recorded) and writes a one-line human-readable summary into `event_summary`. Drives the "Manthan is asking Stripe…" live narrative in the workspace. |

See [`../agent/README.md`](../agent/README.md) for the agent brain
that the investigate worker wraps. Production deploy notes are in
[`../DEPLOY.md`](../DEPLOY.md).
