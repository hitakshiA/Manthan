# Manthan demo - runbook

Step-by-step for presenting the 3 scenarios. Each scenario is pre-seeded
across all 11 sources; you just fire the trigger and Manthan does the rest.

## Pre-flight (do once, before any take)

```bash
# 1. Services running locally (or on demo.manthan.quest in prod)
curl http://127.0.0.1:8765/                          # → {"service":"manthan-api",...}
curl http://127.0.0.1:8765/api/policy/rules \
  -H 'X-Manthan-Dev-Org: acme' | jq '.[].name'       # → "small-refund-auto"

# 2. Workers up
ps aux | grep manthan_api | grep -v grep             # → uvicorn + investigate + actor + prettifier

# 3. Clean state (if not your first take)
curl -X POST http://127.0.0.1:8765/api/demo/reset \
  -H 'X-Manthan-Dev-Org: acme'                       # → 204

# 4. Verify policy rule is enabled
curl http://127.0.0.1:8765/api/policy/rules \
  -H 'X-Manthan-Dev-Org: acme' | jq '.[0].enabled'   # → true

# 5. Browser ready
open http://localhost:5173/                          # marketing landing
# Click "Try the live demo" → drops into /app
```

---

## Scenario A - Quill Logistics $9k chargeback (Segment 3, centerpiece)

**Story you tell:** *"Quill's CFO filed a $9,000 Stripe chargeback claiming our service was down during Q1. An AR analyst would probably refund - $9k against $40k ARR isn't worth the fight. But we don't know if there was actually an outage. The agent has to cross-check 11 systems to find out."*

**Trigger** (one of two - use whichever works in your demo env):

```bash
# Option A: synthetic demo trigger (always works)
curl -X POST http://127.0.0.1:8765/api/demo/trigger/quill \
  -H 'X-Manthan-Dev-Org: acme'

# Option B: real Stripe CLI (looks more dramatic, requires `stripe login`)
stripe trigger charge.dispute.created \
  --override charge:customer=cus_UbEaY6PNSHT340 \
  --override charge.dispute:amount=900000 \
  --override charge.dispute:reason=product_not_received
```

**What happens (live, ~60 seconds):**
1. Case appears in Inbox at the top (you'll see it animate in)
2. Click into the case → live timeline streams (Coral SQL across 7-11 sources)
3. After ~45 sec: brief drops with **FIGHT** recommendation
4. Findings cite Stripe + Salesforce + HubSpot + Notion + PostHog + Sentry + Datadog + PagerDuty
5. Each citation chip is clickable → opens the actual source record in a new tab

**HITL beat** (Segment 3, ~30 sec):
- Click into Chat panel at the bottom
- Type: *"Are you sure there's no Notion exception for renewals over $50k ARR? Re-check that."*
- Agent calls `coral_sql` again → looks for renewal exception → confirms none → replies in chat
- You approve → action fires → Stripe dispute evidence submitted (open Stripe Dashboard, see it land)

---

## Scenario B - Vermillion Studios $4.5k seat dispute (Segment 4, Slack)

**Story you tell:** *"Vermillion's CFO filed a $4,500 chargeback claiming we billed for 25 seats but they only have 15. Probably a billing error. But did their own COO sign a 25-seat addendum that the CFO forgot about? Let's see what Manthan finds."*

**Trigger** (Slack-first, but you can also use the demo endpoint):

```bash
# Option A: real Slack mention (most dramatic)
# In your demo workspace, in #cs-escalations channel, type:
@manthan Vermillion Studios just filed a $4,500 chargeback claiming we billed for 25 seats but they only have 15. Look into it.

# Option B: synthetic demo trigger
curl -X POST http://127.0.0.1:8765/api/demo/trigger/vermillion \
  -H 'X-Manthan-Dev-Org: acme'
```

**What happens:**
1. Bot replies in thread: ":hourglass: On it - opening case `VRM-XXXXXX`. I'll post the brief here when done."
2. ~45 sec later: bot posts the brief card in the thread with TLDR + decision + "Approve & Execute" / "Hold" buttons
3. **PDF brief auto-uploads** to the same thread (Segment 4's "asky PDF")
4. You click "Approve & Execute" → modal asks for signature
5. Type: "Approved - fight but offer the call. - Mark, RevOps"
6. Submit → action fires (Stripe dispute evidence + email to Brightwell CFO)
7. Bot replies in thread confirming: ":white_check_mark: Approved by Mark · executing 2 actions"

**Thread Q&A** (Segment 4's "asky" piece):
- Reply in the thread: *"What's their usage volume?"*
- Bot calls `coral_sql` on PostHog → replies in thread with the number

---

## Scenario C - Maya Patel $89 duplicate (Segment 5, autonomous)

**Story you tell:** *"This one's small. Maya emailed support saying she was charged twice. If we ignore her, she'll dispute it. But this is exactly what policy should auto-resolve - duplicate charge under $200 from a customer in good standing. The agent will find the root cause, refund her, and reply, all without a human."*

**Trigger:**

```bash
# Option A: real Gmail (most dramatic - viewer sees the thread)
# From hitakshi220@gmail.com, send to support@demo.manthan.quest:
#   Subject: Charged twice for Caldera Pro - please refund
#   Body: Hi, I was charged $89 twice on 2026-05-22 for my Caldera Pro
#         subscription. Please refund the duplicate. Thanks, Maya

# Option B: synthetic demo trigger
curl -X POST http://127.0.0.1:8765/api/demo/trigger/maya \
  -H 'X-Manthan-Dev-Org: acme'
```

**What happens (live, ~60 seconds, zero human input):**
1. Case opens with `trigger_surface=email`
2. Investigation runs across 11 sources
3. Agent finds: 2 charges 4min apart + Sentry error + Datadog webhook retry + PagerDuty incident → confirms duplicate caused by OUR webhook bug
4. Brief drops: decision=`refund`, amount=$89
5. **Policy engine fires** - "small-refund-auto" matches → mode=`auto`
6. Case status flips directly to `acting` (no `awaiting_approval` step)
7. Actor executes: Stripe refund $89 + Resend email reply to Maya

**Refresh Gmail** → Maya gets a reply in the same thread within ~60s.

**Show the policy beat:**
- Navigate to `/app/policy` → highlight the "small-refund-auto" rule
- Navigate to `/app/audit` → show the chronological event stream:
  `case_opened → brief_drafted → policy_matched (auto) → human_approved (via policy_auto) → action_executed (stripe_refund) → action_executed (customer_email) → case_closed`

---

## Recovery

If anything goes wrong mid-take, the reset is one command:

```bash
curl -X POST http://127.0.0.1:8765/api/demo/reset -H 'X-Manthan-Dev-Org: acme'
```

Wipes cases/events/findings/actions/policy_matches. Keeps org, members, policy rules, sources.

---

## Closing slide notes (Segment 6)

After Scenario C completes, switch to the closing slide. Three talking points:

1. **Easy integration of years of data** - point at the Sources page (11 logos, all "connected", lived-in last-sync times). Coral fronts the breadth.
2. **Agent budget + speed** - point at the trace (60 seconds for what an analyst takes 2-3 hours).
3. **Not possible without long horizon** - emphasize that the agent had to chain queries across systems, hold context, decide when to act vs. ask. The cross-source join is the moat.

Then: "Try it yourself - demo.manthan.quest. Same data you just saw, persistent until your next reset."
