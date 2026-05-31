# Deploy `app.manthan.quest` - 60-90 min runbook

Everything below assumes you're sitting at the manthanv2/ directory.

```
app.manthan.quest         ← UI (Vercel)
api.app.manthan.quest     ← API + workers + Postgres + Coral (Fly.io)
support@demo.manthan.quest ← outbound sender (Resend, already live)
manthan@doraro.resend.app ← inbound receiver (Resend predefined subdomain)
```

Once this runs, your laptop can sleep. Stripe, Resend, and Slack all hit the public API.

---

## Step 1 - install the two CLIs (5 min)

```bash
# Fly
brew install flyctl
fly auth signup     # or: fly auth login

# Vercel
brew install vercel-cli
vercel login        # browser auth
```

## Step 2 - provision Fly infrastructure (10 min)

```bash
cd "/Users/akshmnd/Dev Projects/manthanv2"

# Create the app - picks up fly.toml automatically
fly apps create manthan-api

# Create managed Postgres (free tier, 1GB)
fly postgres create --name manthan-db --region iad --vm-size shared-cpu-1x --volume-size 3

# Attach Postgres to the app - this auto-sets DATABASE_URL secret
fly postgres attach manthan-db --app manthan-api
```

## Step 3 - push all your local secrets to Fly (3 min)

The helper script reads `manthan-api/.env` + `agent/.env` and uploads them as Fly secrets:

```bash
./scripts/set-fly-secrets.sh manthan-api
```

That includes:
- `OPENROUTER_API_KEY`, `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`
- `RESEND_API_KEY`, `RESEND_FROM_ADDRESS`, `RESEND_INBOUND_WEBHOOK_SECRET`
- `SLACK_TOKEN`, `SLACK_SIGNING_SECRET`
- 11 source credentials (Stripe, Salesforce, HubSpot, Intercom, Zendesk, Slack, Notion, PostHog, Sentry, Datadog, PagerDuty)

Skips `DATABASE_URL` (Fly Postgres set it in step 2).

## Step 4 - first deploy (15-20 min, mostly Coral compile)

```bash
cd "/Users/akshmnd/Dev Projects/manthanv2"
fly deploy --remote-only
```

Fly's builder runs the multi-stage Dockerfile:
1. `coral-builder` stage: compiles the Coral binary (~10 min first time, cached after)
2. `base` stage: installs Python deps + bakes Coral into `/usr/local/bin/coral`

Then ships 4 machines: `web` (FastAPI), `investigate`, `actor`, `prettifier`.

```bash
# Check it's healthy
fly status --app manthan-api
curl https://manthan-api.fly.dev/
# → {"service": "manthan-api", ...}
```

## Step 5 - run migrations on the Fly Postgres (2 min)

```bash
# Get a psql shell connected to the prod DB
fly postgres connect --app manthan-db

# Inside psql, paste each schema file:
\i /Users/akshmnd/Dev\ Projects/manthanv2/manthan-api/schema/001_initial.sql
\i /Users/akshmnd/Dev\ Projects/manthanv2/manthan-api/schema/002_event_summary.sql
\i /Users/akshmnd/Dev\ Projects/manthanv2/manthan-api/schema/003_policy_engine.sql
\q
```

(Or use a one-liner: `cat schema/*.sql | fly postgres connect --app manthan-db`)

Then seed the dev org + policy rule:
```bash
# SSH into the web machine and run the bootstrap script
fly ssh console --app manthan-api -C "uv run python -m manthan_api.scripts.bootstrap_dev_org"
fly ssh console --app manthan-api -C "uv run python -m manthan_api.scripts.seed_policy_rules"
```

## Step 6 - assign the API custom domain (5 min)

```bash
fly certs create api.app.manthan.quest --app manthan-api
# Outputs the A and AAAA records you need to add at GoDaddy.
```

**In GoDaddy** → manthan.quest → DNS:
- A record: name `api.app`, value `(the IPv4 Fly printed)`, TTL 1h
- AAAA record: name `api.app`, value `(the IPv6 Fly printed)`, TTL 1h

Wait 2-10 min, then:
```bash
curl https://api.app.manthan.quest/
# → {"service": "manthan-api", ...}
```

## Step 7 - deploy the UI to Vercel (5 min)

```bash
cd manthan-ui

# First-time: pick "Link to existing project" → No → name it "manthan-ui"
# Defaults are fine (Vite framework, dist output)
vercel

# Promote to production
vercel --prod
```

## Step 8 - assign the UI custom domain (3 min)

In Vercel dashboard → manthan-ui project → Settings → Domains → Add `app.manthan.quest`.

Vercel shows you a CNAME to add. **In GoDaddy** → manthan.quest → DNS:
- CNAME: name `app`, value `cname.vercel-dns.com`, TTL 1h

Wait 2-5 min:
```bash
curl https://app.manthan.quest/
# → HTML page (the landing)
```

## Step 9 - repoint webhooks at the public URL (5 min)

You're now at `https://api.app.manthan.quest`. Update three webhook destinations:

### Stripe (in Dashboard)
- Developers → Webhooks → Add endpoint
- URL: `https://api.app.manthan.quest/webhooks/stripe/acme`
- Events: `charge.dispute.created`, `charge.dispute.funds_withdrawn`, `charge.refund.updated`, `radar.early_fraud_warning.created`, `invoice.payment_failed`
- Save → copy "Signing secret" (`whsec_…`)
- ```bash
  fly secrets set STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxx --app manthan-api
  ```

### Resend (in Dashboard)
- Webhooks → Add endpoint
- URL: `https://api.app.manthan.quest/webhooks/email/acme`
- Events: `email.received`
- Save → copy signing secret
- ```bash
  fly secrets set RESEND_INBOUND_WEBHOOK_SECRET=whsec_xxxxxxxx --app manthan-api
  ```

### Slack (later, when you install the Slack bot)
- URL: `https://api.app.manthan.quest/webhooks/slack/acme/events`

## Step 10 - smoke test the live demo (5 min)

```bash
# Quill scenario via the demo trigger
curl -X POST https://api.app.manthan.quest/api/demo/trigger/quill \
  -H 'X-Manthan-Dev-Org: acme'

# Watch the live SSE stream from the API
curl -N "https://api.app.manthan.quest/api/cases/{case_id}/stream?dev_org=acme"
```

Then open https://app.manthan.quest in a browser → the live case should be at the top of the Inbox, streaming the investigation.

For the Maya autonomous flow with real email: send from your Gmail to `manthan@doraro.resend.app` with the duplicate-charge body. Within ~60s the reply should land in your inbox from `Caldera Support <support@demo.manthan.quest>`.

---

## Things that might bite

- **First Coral compile is slow** (~10 min). Subsequent deploys cache the layer.
- **Fly free tier is 3 shared-cpu-1x machines.** This stack uses 4 (web + 3 workers). You'll be charged ~$5/mo for the 4th VM. Acceptable.
- **GoDaddy DNS propagation** can take 5-30 min. Don't panic if `curl api.app.manthan.quest` 502s for a few min.
- **CORS**: `WEB_APP_ORIGIN` env var on Fly must match `https://app.manthan.quest` exactly (no trailing slash, https not http). It's set in fly.toml but double-check.
- **Worker logs**: `fly logs --app manthan-api -i <machine-id>` per process group.

## Rollback

```bash
fly releases --app manthan-api          # find the previous version
fly deploy --image registry.fly.io/manthan-api:deployment-XXXX  # roll back
```
