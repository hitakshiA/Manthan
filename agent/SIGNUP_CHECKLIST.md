# Source signup checklist - Manthan v2 phase 1

30 sources. All free-tier or free-trial. All accessible to a solo dev
without a sales call or a credit card (one exception: K8s - see #30).
Goal: get every `*_API_KEY` line in `.env` filled.

Order is recommended (top 5 unlock 14/16 in-scope cases). Power through in
parallel tabs.

After each: paste the key into `manthanv2/agent/.env` at the listed line.
Drop them in as you go - I'll start seeding the moment they appear.

---

## 1. Stripe - test mode trigger surface (~3 min)

**Signup:** https://dashboard.stripe.com/register
**Steps:**
1. Sign up with work email (or log in if existing).
2. Top-right toggle → **Test mode**. The header should turn orange.
3. Side nav → **Developers → API keys**.
4. **Create restricted key** → name: `manthan-agent-read-only`.
5. Set **Read** for all of:
   `Customers, Charges, Disputes, PaymentIntents, Refunds, Events,
    Balance transactions, Payouts, Subscriptions, Invoices, Products,
    Prices, Coupons`.
6. Create key → copy `rk_test_...` (shown once).

**`.env` line:** `STRIPE_API_KEY=rk_test_...`

---

## 2. HubSpot - free CRM (~3 min)

**Signup:** https://www.hubspot.com/products/get-started-free
**Steps:**
1. Sign up. Pick "for a personal project" if asked.
2. After landing in the CRM → **Settings (gear icon)** → **Integrations →
   Private Apps**.
3. **Create a private app** → name: `Manthan Agent`.
4. Tab **Scopes** → enable:
   - CRM: `crm.objects.companies.*`, `crm.objects.contacts.*`,
     `crm.objects.deals.*`, `crm.objects.notes.*`, `crm.objects.owners.read`
   - Standard: `tickets`, `timeline`, `e-commerce` (if shown)
5. **Create app** → copy the access token (starts with `pat-`).

**`.env` line:** `HUBSPOT_ACCESS_TOKEN=pat-...`

---

## 3. Slack - new workspace + bot app (~7 min)

**Signup:** https://slack.com/get-started
**Steps:**
1. **Create a new workspace** dedicated to Manthan dev (don't mix with
   personal/work). Name: `Manthan Dev` or similar.
2. Open https://api.slack.com/apps → **Create New App** → **From scratch**.
3. App name: `Manthan Agent`. Pick the Manthan Dev workspace.
4. Left nav: **OAuth & Permissions** → scroll to **Scopes → Bot Token
   Scopes** → add:
   ```
   channels:history     channels:join      channels:manage
   channels:read        chat:write         groups:history
   groups:read          groups:write       im:history
   im:read              im:write           mpim:history
   mpim:read            mpim:write         reactions:read
   users:read           users:read.email
   ```
5. Top of same page → **Install to Workspace** → Allow.
6. Copy the **Bot User OAuth Token** (starts with `xoxb-`).

**`.env` line:** `SLACK_BOT_TOKEN=xoxb-...`

**Note:** the bot auto-joins channels it creates programmatically. You
don't need to `/invite` it anywhere.

---

## 4. Notion - workspace + integration (~5 min)

**Signup:** https://notion.so (use existing if you have one)
**Steps:**
1. Create or open a workspace dedicated to Manthan (avoid personal
   workspace - easier to clean up later).
2. https://www.notion.so/profile/integrations → **New integration** →
   name: `Manthan Agent`, associated workspace: Manthan dev.
3. Capabilities: **Read, Update, Insert content**. Leave user-info as
   "No user information".
4. Submit → copy the **Internal Integration Token** (starts with `ntn_` or
   `secret_`).
5. **Critical extra step:** in the Notion app, create a top-level page
   called `Manthan` (or anything). Click `••• → Connect to → Manthan Agent`.
   This grants the integration access to that page tree. I'll create all
   runbooks and account memos under it.

**`.env` line:** `NOTION_API_KEY=ntn_...`

---

## 5. Intercom - developer workspace (~5 min)

**Signup:** https://app.intercom.com/admins/sign_up (use the dev signup -
not the sales-led free trial)
**Steps:**
1. Sign up. If it asks for company info, use minimal answers.
2. **Settings (gear)** → **Integrations → Developer Hub** (or
   `app.intercom.com/a/developer-signup`).
3. **New app** → name: `Manthan Agent`.
4. **Authentication** tab → enable **Access tokens** → copy the token
   (starts with `dG9rOm...` typically).

**`.env` line:** `INTERCOM_ACCESS_TOKEN=dG9rOm...`

---

## 6. Linear - free workspace + key (~2 min)

**Signup:** https://linear.app/signup
**Steps:**
1. Create workspace. Name: `Manthan Dev`.
2. **Settings → Account → Security & access → Personal API keys**.
3. **New API key** → label: `manthan-agent`. Copy the value (starts with
   `lin_api_...`).

**`.env` line:** `LINEAR_API_KEY=lin_api_...`

---

## 7. GitHub - existing acct + PAT (~3 min)

Use your existing GitHub.
**Steps:**
1. https://github.com/settings/tokens → **Generate new token (classic)**
   (fine-grained also works but classic is simpler).
2. Name: `manthan-agent`. Expiration: 90 days (or longer).
3. Scopes: `repo`, `read:org`, `read:user`, `workflow` (skip if you don't
   plan to seed Actions data).
4. Generate → copy the token (starts with `ghp_...`).

**`.env` line:** `GITHUB_TOKEN=ghp_...`

---

## 8. Sentry - free developer tier (~5 min)

**Signup:** https://sentry.io/signup/
**Steps:**
1. Sign up. Org name: `manthan-dev` (single word, no spaces).
2. Skip the language picker - we'll create projects programmatically.
3. **Settings → Account → API → Auth Tokens** (or
   https://sentry.io/settings/account/api/auth-tokens/).
4. **Create New Token** → scopes: `project:read`, `event:read`,
   `org:read`, `member:read`, `team:read`. Name: `manthan-agent`.
5. Copy token (starts with `sntrys_...`).

**`.env` lines:**
```
SENTRY_AUTH_TOKEN=sntrys_...
SENTRY_ORG=manthan-dev
```

---

## 9. PostHog - free tier (~3 min)

**Signup:** https://us.posthog.com/signup
**Steps:**
1. Sign up. Project name: `Manthan Dev`. Region: US.
2. **Settings → Project → API keys**.
3. **Personal API key** (not the project key - we want the user-level
   one for the read API): https://us.posthog.com/settings/user-api-keys
4. **Create personal API key** → name: `manthan-agent`. Scopes: enable
   `project:read`, `event:read`, `person:read`, `query:read`,
   `insight:read`.
5. Copy the key (starts with `phx_...`).

**`.env` lines:**
```
POSTHOG_API_KEY=phx_...
POSTHOG_HOST=https://us.posthog.com
```

---

## 10. Zendesk - 14-day trial (~6 min)

**Signup:** https://www.zendesk.com/register/
**Steps:**
1. Sign up. Subdomain: `manthan-dev` (yours will be
   `manthan-dev.zendesk.com`).
2. Skip product configuration; go to **Admin Center (Z gear icon at
   top-right of Support)** → **Apps and integrations → Zendesk API**.
3. **Settings** → **Token access: enabled**.
4. **Add API token** → label: `manthan-agent` → copy the token.

**`.env` lines:**
```
ZENDESK_SUBDOMAIN=manthan-dev
ZENDESK_EMAIL=your-signup-email/token
ZENDESK_API_TOKEN=...
```

**Note:** the `EMAIL` value has the literal `/token` suffix at the end
(Zendesk's quirk). Example: `akash@miny-labs.com/token`.

---

## 11. Chargebee - trial site (~5 min)

**Signup:** https://www.chargebee.com/trial-signup/
**Steps:**
1. Sign up. Site name: `manthan-dev` (yours will be
   `manthan-dev.chargebee.com`).
2. Pick currency: INR (or USD - your call).
3. **Settings (gear) → API Keys & Webhooks → API Keys**.
4. **Add API Key → Full-Access key** (we need create permissions for
   seeding). Name: `manthan-agent`.
5. Copy key.

**`.env` lines:**
```
CHARGEBEE_SITE=manthan-dev
CHARGEBEE_API_KEY=live_...
```

---

## 12. Razorpay - test mode (~5 min)

**Signup:** https://dashboard.razorpay.com/signup
**Steps:**
1. Sign up. Verify email.
2. **Top toggle → Test mode** (left of profile).
3. **Account & Settings → API keys** (left side).
4. **Generate Test Key** → copy both `Key Id` (starts with `rzp_test_`)
   and `Key Secret` (shown once).

**`.env` lines:**
```
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
```

---

## 13. Salesforce - Developer Edition (~10 min, most tedious)

**Signup:** https://developer.salesforce.com/signup
**Steps:**
1. Sign up with a real-ish email. Username should follow
   `you+manthan@miny-labs.com.dev` pattern (Salesforce requires unique
   usernames globally - appending `.dev` works).
2. Confirm email → **set a password** in the verification email.
3. After login, top-right gear → **Setup**.
4. Quick Find: type `My Personal Information` → **Reset My Security Token**
   → submit. Token arrives by email (looks random). Note it.
5. Quick Find: type `App Manager` → **New Connected App** → name:
   `Manthan Agent`. Enable OAuth → callback URL:
   `https://localhost:8080/callback`. Selected OAuth scopes:
   `Full access (full)`, `Perform requests at any time (refresh_token,
   offline_access)`. Save.
6. After ~10 min (Salesforce delay), back to App Manager → find your app
   → **View** → copy `Consumer Key` and `Consumer Secret`.

**`.env` lines:**
```
SALESFORCE_INSTANCE_URL=https://manthan-dev-dev-ed.develop.my.salesforce.com
SALESFORCE_ACCESS_TOKEN=  # generated by an OAuth call I'll script after signup
```

**Note:** Salesforce auth is the gnarliest. I'll handle the OAuth-token
flow programmatically once you have the consumer-key/secret + username +
password + security-token. Don't worry about the access-token line - it's
derived.

---

## Bookkeeping

After each key drops in:

1. Run `cd manthanv2/agent && .venv/bin/python -c "from manthan_agent.config import load, configured_sources; print(configured_sources(load()))"` to see what's wired.
2. Reply with `source X in` (e.g. `stripe in`) and I'll add it to Coral +
   start that source's seeder.

You don't have to do all 30 to start - the agent gets more interesting
with each source added. Stripe alone unlocks 12 of the 16 scenarios as a
single-source ablation. Stripe + HubSpot + Slack + Notion + Intercom hits
the cross-source sweet spot. Sources 14–30 below add depth to specific
case categories (email evidence, incidents, identity, alt providers).

---

## 14. Gmail - customer email (OAuth, ~8 min)

**Signup:** uses your existing Google account.
**Steps:**
1. Open https://console.cloud.google.com/ → create a new project named
   `manthan-dev`.
2. Enable **Gmail API**:
   https://console.cloud.google.com/apis/library/gmail.googleapis.com
3. Enable **Google Drive API** (we'll reuse the same OAuth client):
   https://console.cloud.google.com/apis/library/drive.googleapis.com
4. **APIs & Services → OAuth consent screen** → External → fill the
   minimum required fields (app name `Manthan Agent`, your email twice).
   Test users: add yourself.
5. **APIs & Services → Credentials → + Create Credentials → OAuth
   client ID → Desktop app** → name `Manthan Agent (desktop)`.
6. Copy the **Client ID** (ends in `.apps.googleusercontent.com`) and
   **Client secret**.
7. Drop into `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=...apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=...
   ```
8. **Add a redirect URI** to the same OAuth client in step 5:
   `http://127.0.0.1:8765/callback`
9. Run the bootstrap once:
   ```bash
   cd manthanv2/agent
   .venv/bin/python scripts/gmail_oauth_bootstrap.py
   ```
   Your browser opens, you grant Gmail + Drive read access, the script
   writes `GMAIL_*` and `GOOGLE_DRIVE_*` tokens back to `.env`.

**`.env` lines:** all 6 `GOOGLE_*` / `GMAIL_*` / `GOOGLE_DRIVE_*` lines
populated by the bootstrap.

---

## 15. Google Drive - same OAuth as Gmail

Already done in #14. No separate signup. The Drive access token is the
same as Gmail's (single OAuth, dual scope).

---

## 16. Postmark - transactional email evidence (~3 min)

**Signup:** https://account.postmarkapp.com/sign_up
**Steps:**
1. Sign up. Server name: `Manthan Dev`.
2. **Servers → your server → API Tokens** → copy **Server API token**.

**`.env` line:** `POSTMARK_SERVER_TOKEN=...`

---

## 17. Resend - modern transactional email (~2 min)

**Signup:** https://resend.com/signup
**Steps:**
1. Sign up.
2. **API Keys → Create API Key** → name: `manthan-agent` → permission:
   Full access (we need send + list).

**`.env` line:** `RESEND_API_KEY=re_...`

---

## 18. Mailchimp - marketing email evidence (~3 min)

**Signup:** https://mailchimp.com/signup/
**Steps:**
1. Sign up. Free plan is fine (up to 500 contacts).
2. **Profile → Extras → API keys → Create A Key** → copy.
3. Note the **server prefix** - it's the last segment of your dashboard
   URL hostname, e.g. for `us21.admin.mailchimp.com` the prefix is `us21`.

**`.env` lines:**
```
MAILCHIMP_API_KEY=...
MAILCHIMP_SERVER_PREFIX=us21
```

---

## 19. Loops - PLG marketing email (~2 min)

**Signup:** https://app.loops.so/signup
**Steps:**
1. Sign up.
2. **Settings → API → Create API Key** → name: `manthan-agent`.

**`.env` line:** `LOOPS_API_KEY=...`

---

## 20. Twilio - SMS evidence (~5 min)

**Signup:** https://www.twilio.com/try-twilio
**Steps:**
1. Sign up (trial credit included). Verify your phone.
2. Console: copy **Account SID** (starts with `AC...`).
3. **Account → API keys & tokens → Create API key** → friendly name
   `manthan-agent`, type: **Standard** → save.
4. Copy **SID** (the key SID, starts with `SK...`) and **Secret**.

**`.env` lines:**
```
TWILIO_ACCOUNT_SID=AC...
TWILIO_API_KEY=SK...
TWILIO_API_KEY_SECRET=...
```

---

## 21. Clerk - auth events (~2 min)

**Signup:** https://dashboard.clerk.com/sign-up
**Steps:**
1. Sign up. Create an application named `Manthan Dev`. Select email
   auth (we don't actually need users, just the API surface).
2. **API Keys → Show secret key** → copy.

**`.env` line:** `CLERK_SECRET_KEY=sk_test_...`

---

## 22. Cal.com - meeting history (~2 min)

**Signup:** https://app.cal.com/signup
**Steps:**
1. Sign up. Pick a username.
2. **Settings → Developer → API Keys → Add** → name: `manthan-agent` →
   never expires → copy key.

**`.env` line:** `CAL_API_KEY=cal_...`

---

## 23. Mixpanel - alt product analytics (~4 min)

**Signup:** https://mixpanel.com/register/
**Steps:**
1. Sign up. Create project `Manthan Dev` (Org Free tier).
2. **Settings (gear) → Organization Settings → Service Accounts → +
   Add Service Account** → role: `Consumer (read-only)`. Copy
   **Username** and **Secret** (shown once).
3. Note the **Project ID** from the URL of your project (a numeric ID).

**`.env` lines:**
```
MIXPANEL_PROJECT_ID=...
MIXPANEL_SERVICE_ACCOUNT_USERNAME=...
MIXPANEL_SERVICE_ACCOUNT_SECRET=...
```

---

## 24. Confluence - alt docs / runbooks (~5 min)

**Signup:** https://www.atlassian.com/try/cloud/signup?bundle=confluence
**Steps:**
1. Sign up for Atlassian Cloud (Free tier - up to 10 users).
2. Pick a site name: `manthan-dev` → your URL becomes
   `manthan-dev.atlassian.net`.
3. https://id.atlassian.com/manage-profile/security/api-tokens →
   **Create API token** → name: `manthan-agent`.

**`.env` lines:**
```
CONFLUENCE_BASE_URL=https://manthan-dev.atlassian.net
CONFLUENCE_EMAIL=your-signup-email
CONFLUENCE_API_TOKEN=...
```

---

## 25. Grafana Cloud - observability (~4 min)

**Signup:** https://grafana.com/auth/sign-up/create-user
**Steps:**
1. Sign up. Pick a stack name: `manthan-dev`. Region: closest to you.
2. After provisioning lands you on your stack page, the URL will be
   `https://manthan-dev.grafana.net`. Note it.
3. **Configuration (gear) → API keys → Add API key** → name:
   `manthan-agent`, role: `Viewer`.

**`.env` lines:**
```
GRAFANA_URL=https://manthan-dev.grafana.net
GRAFANA_TOKEN=glsa_...
```

---

## 26. Datadog - observability (~5 min)

**Signup:** https://www.datadoghq.com/free-datadog-trial/
**Steps:**
1. Sign up (14-day free trial - no card needed for trial).
2. Org name: `Manthan Dev`. Site region: pick the closest (US5 / EU /
   AP1). Note which one.
3. After install screen: **Integrations (left rail) → APIs** →
   **API Keys → New Key**, name: `manthan-agent` → copy.
4. Same page, **Application Keys → New Key**, name: `manthan-agent` →
   copy.

**`.env` lines:**
```
DD_SITE=datadoghq.com   # or us5.datadoghq.com / eu.datadoghq.com / ap1.datadoghq.com
DD_API_KEY=...
DD_APPLICATION_KEY=...
```

---

## 27. StatusGator - vendor status aggregator (~3 min)

**Signup:** https://statusgator.com/users/sign_up
**Steps:**
1. Sign up.
2. **Account → API Access → Generate API Token** (Free tier gives a
   read-only token for your watched services).

**`.env` line:** `STATUSGATOR_API_TOKEN=...`

---

## 28. PagerDuty - incidents (~5 min)

**Signup:** https://www.pagerduty.com/sign-up/
**Steps:**
1. Sign up (free trial). Subdomain: `manthan-dev`.
2. **Integrations → API Access Keys → Create New API Key** → name:
   `manthan-agent`, read-only.

**`.env` line:** `PAGERDUTY_API_TOKEN=...`

---

## 29. LaunchDarkly - feature flags (~5 min)

**Signup:** https://app.launchdarkly.com/signup
**Steps:**
1. Sign up. Organization: `Manthan Dev`.
2. After login, **Account settings → Authorization → +Token** →
   name: `manthan-agent`, role: `Reader`.

**`.env` line:** `LAUNCHDARKLY_TOKEN=api-...`

---

## 30. Kubernetes - infrastructure (optional, complex)

**Caveat:** K8s coverage requires a reachable cluster API endpoint with
a bearer token. Solo-dev options:

- **Skip** - descope k8s for phase 1. Scenarios that touch it are rare.
- **Civo / DigitalOcean / Linode** - free credits give you a small
  managed cluster (~$10/month equivalent on trial).
- **Local cluster (Minikube, Kind, k3s)** - works but the API server
  is on localhost; Coral has to run on the same machine and may need
  cert config.

If you skip: leave `K8S_BASE_URL=` empty. The agent's coverage drops
on incident-correlation scenarios that involve deploys.

**`.env` line (if used):** `K8S_BASE_URL=https://<cluster>.example.com:6443`

