# Deploy Manthan to demo.manthan.quest

End-to-end deploy guide for the live demo. Estimated time: ~45 min.

## What you'll end up with

| Subdomain | What | Host |
|---|---|---|
| `demo.manthan.quest` | UI (Landing → Try Demo → /app) | Vercel |
| `api.demo.manthan.quest` | FastAPI + 3 workers | Fly.io |
| (MX records) | Inbound mail for `support@demo.manthan.quest` | Resend inbound |

---

## 1. UI on Vercel (~5 min)

```bash
cd manthan-ui
vercel login
vercel link              # link this dir to a new Vercel project
vercel domains add demo.manthan.quest
```

Vercel will surface the CNAME you need (usually `cname.vercel-dns.com`). Add
it at your DNS provider for `demo.manthan.quest`.

Set env vars in Vercel project settings (or edit `vercel.json` and redeploy):

```
VITE_MANTHAN_API_URL=https://api.demo.manthan.quest
VITE_MANTHAN_DEV_ORG=acme
```

Deploy:

```bash
vercel --prod
```

---

## 2. Postgres on Fly (~5 min)

```bash
fly auth login
fly postgres create --name manthan-db --region iad --vm-size shared-cpu-1x \
                    --volume-size 10 --initial-cluster-size 1
fly postgres attach --app manthan-api manthan-db
```

Apply schema:

```bash
fly proxy 5432 -a manthan-db &
psql 'postgres://manthan:<password>@127.0.0.1:5432/manthan' \
    -f manthan-api/schema/001_initial.sql \
    -f manthan-api/schema/002_event_summary.sql \
    -f manthan-api/schema/003_policy_engine.sql
```

Seed the demo org + admin:

```bash
cd manthan-api && uv run python -m manthan_api.scripts.bootstrap_dev_org
```

Seed the demo policy rule (already in `003_policy_engine.sql` - verify it landed):

```bash
psql ... -c "SELECT name FROM policy_rules"
```

---

## 3. API on Fly (~15 min)

From the **repo root** (Dockerfile expects the `agent/` sibling in context):

```bash
fly launch --no-deploy --copy-config --name manthan-api \
           --dockerfile manthan-api/Dockerfile .
```

Set secrets (one per line - paste your real keys):

```bash
fly secrets set \
  OPENROUTER_API_KEY=sk-or-v1-... \
  STRIPE_API_KEY=sk_test_... \
  STRIPE_WEBHOOK_SECRET=whsec_... \
  RESEND_API_KEY=re_... \
  RESEND_FROM_ADDRESS=support@demo.manthan.quest \
  RESEND_INBOUND_WEBHOOK_SECRET=whsec_... \
  SLACK_TOKEN=xoxb-... \
  SLACK_SIGNING_SECRET=... \
  SLACK_WORKSPACE_HANDLE=caldera-demo \
  SALESFORCE_API_URL=https://...my.salesforce.com \
  SALESFORCE_ACCESS_TOKEN=... \
  HUBSPOT_ACCESS_TOKEN=... \
  HUBSPOT_PORTAL_ID=... \
  INTERCOM_ACCESS_TOKEN=... \
  INTERCOM_WORKSPACE_ID=... \
  ZENDESK_SUBDOMAIN=... \
  ZENDESK_USER_EMAIL_WITH_TOKEN=... \
  ZENDESK_API_TOKEN=... \
  NOTION_API_KEY=secret_... \
  POSTHOG_API_KEY=phx_... \
  POSTHOG_PROJECT_ID=... \
  SENTRY_ORG=... \
  SENTRY_TOKEN=sntryu_... \
  DD_API_KEY=... \
  DD_APPLICATION_KEY=... \
  DD_SITE=datadoghq.com \
  PAGERDUTY_API_TOKEN=... \
  PAGERDUTY_SUBDOMAIN=... \
  EVENT_SIGNING_KEY=$(openssl rand -hex 32) \
  SOURCE_CONFIG_KEY=$(openssl rand -hex 32) \
  WEB_APP_ORIGIN=https://demo.manthan.quest
```

Deploy:

```bash
fly deploy --remote-only
```

Add domain:

```bash
fly certs create api.demo.manthan.quest
# Add the A/AAAA records Fly shows at your DNS provider
```

---

## 4. Inbound email (~10 min)

In **Resend dashboard**:
1. Add domain `manthan.quest` (or `demo.manthan.quest`) - verify SPF + DKIM + DMARC records they show
2. Enable **Inbound** - they'll give you MX records to add (typically pointing to `inbound-smtp.resend.com`)
3. Create an Inbound Webhook → URL: `https://api.demo.manthan.quest/webhooks/email/acme`
4. Copy the signing secret → `fly secrets set RESEND_INBOUND_WEBHOOK_SECRET=...`

DNS records to add at your registrar (Cloudflare / GoDaddy / etc):

```
TYPE    NAME                          VALUE
A       demo.manthan.quest            <Vercel A record>
CNAME   api.demo.manthan.quest        <Fly CNAME>
MX      demo.manthan.quest      10    inbound-smtp.resend.com
TXT     demo.manthan.quest            "v=spf1 include:resend.com ~all"
TXT     resend._domainkey...          (DKIM from Resend dashboard)
TXT     _dmarc.demo.manthan.quest     "v=DMARC1; p=quarantine; rua=mailto:..."
```

---

## 5. Stripe webhook (~3 min)

In **Stripe Dashboard** (test mode):
1. Developers → Webhooks → Add endpoint
2. Endpoint URL: `https://api.demo.manthan.quest/webhooks/stripe/acme`
3. Events to send:
   - `charge.dispute.created`
   - `charge.dispute.funds_withdrawn`
   - `radar.early_fraud_warning.created`
   - `invoice.payment_failed`
   - `charge.refund.updated`
4. Copy signing secret → `fly secrets set STRIPE_WEBHOOK_SECRET=whsec_...`

---

## 6. Slack bot (~10 min)

In **Slack Apps → Create New App → From scratch**:
1. App name: `Manthan` (workspace: your demo workspace)
2. **OAuth & Permissions**:
   - Scopes: `app_mentions:read`, `channels:history`, `chat:write`, `chat:write.public`, `commands`, `files:write`, `im:history`, `im:read`, `im:write`, `users:read`, `conversations.connect:read`
3. **Event Subscriptions** → Enable Events:
   - Request URL: `https://api.demo.manthan.quest/webhooks/slack/acme/events`
   - Subscribe to bot events: `app_mention`, `message.im`
4. **Interactivity & Shortcuts** → Enable:
   - Request URL: `https://api.demo.manthan.quest/webhooks/slack/acme/interactive`
5. Install to workspace → copy Bot Token + Signing Secret:
   ```bash
   fly secrets set SLACK_TOKEN=xoxb-... SLACK_SIGNING_SECRET=...
   ```
6. Invite the bot to your demo channel: `/invite @manthan`

---

## 7. Verify (5 min)

```bash
# UI loads
curl https://demo.manthan.quest

# API health
curl https://api.demo.manthan.quest/

# Webhooks reachable
curl -X POST https://api.demo.manthan.quest/webhooks/stripe/acme \
     -H 'Content-Type: application/json' -d '{}'   # should 400 (bad sig, but reachable)

# Trigger Quill scenario via Stripe CLI
stripe trigger charge.dispute.created \
       --add charge.dispute:amount=900000 \
       --add charge.dispute:currency=usd

# Watch the UI Inbox at https://demo.manthan.quest/app - a new case should appear
# within ~2 seconds.
```

---

## Nightly reset (optional but recommended)

A cron that wipes the DB and re-seeds, so each demo viewer sees a clean state:

```toml
# fly.toml - add another process
[processes]
  reset = "uv run python -m manthan_api.scripts.nightly_reset"
```

Or run as a one-shot from local: `fly machine run --schedule daily ...`.

---

## Troubleshooting

- **CORS errors in browser**: check `WEB_APP_ORIGIN` matches `demo.manthan.quest` exactly
- **Slack signature mismatch**: timestamp drift > 5 min → check Fly machine clock
- **Resend inbound 404**: webhook URL slug must be `acme` (or whatever your org slug is - see DB `orgs.slug`)
- **Stripe webhook 400**: signature secret must be the **test mode** one, not live
- **Worker not picking up cases**: tail `fly logs --process investigate` - likely a missing env var
