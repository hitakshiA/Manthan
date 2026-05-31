"""Seed Slack workspace ``ManthanDemo`` for the Manthan billing-dispute agent.

Coral surface limitation
------------------------
The Coral ``slack`` source ONLY exposes the ``channels`` and ``users``
tables - it does NOT expose messages. So nothing this script writes to
chat is discoverable by the agent through Coral today. We still create
channels (queryable as the ``channels`` table) and post a handful of
realistic messages for future use, but the workflow signals (W1/W2/W3)
that the agent actually relies on live in the OTHER seeded sources
(Stripe / HubSpot / Linear / Notion / Intercom / etc.).

What this script does
---------------------
1. Verifies ``auth.test`` succeeds and we're in the ManthanDemo workspace.
2. Lists existing public channels (``conversations.list``) and creates
   any of the target 9 channels that are missing.
3. The bot ``manthantest`` automatically joins channels it creates, so
   no explicit invite is required for those - for any channel that
   already existed (e.g. user-pre-created), it self-joins via
   ``conversations.join``.
4. Lists workspace users (``users.list``) - we cannot create new humans
   programmatically (Slack workspace users require email invite +
   acceptance), so we accept the existing ~2 humans + the bot.
5. Posts ~30-50 ambient messages across the channels: deploy pings,
   AR-collection nudges, customer-success chatter - plus three explicit
   W1/W2/W3 signal messages in #cs-escalations / #engineering-incidents.

Idempotency
-----------
Creates check existence first. Messages are NOT deduped automatically -
if you re-run this script you'll get a fresh batch. If that ever matters,
gate the message section with an env flag.

Run with:
    .venv/bin/python scripts/seed_slack.py
"""

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ────────────────────────────────────────────────────────────────────────
# Env
# ────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
AGENT_DIR = SCRIPT_DIR.parent
load_dotenv(AGENT_DIR / ".env")

TOKEN = os.getenv("SLACK_TOKEN")
if not TOKEN or not TOKEN.startswith("xoxb-"):
    sys.exit("ERROR: SLACK_TOKEN missing or not a bot token in agent/.env")

BASE = "https://slack.com/api"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json; charset=utf-8",
}

# Slack Tier-1/Tier-2 rate limits hover around 1 req/sec for postMessage.
# Keep a generous sleep so we don't get throttled.
MSG_SLEEP = 1.05
API_SLEEP = 0.4

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


# ────────────────────────────────────────────────────────────────────────
# Target channels
# ────────────────────────────────────────────────────────────────────────

# Note: #cs-escalations, #ar-collections, #deal-desk are documented as
# pre-created by the user. We treat them the same as the rest - list
# first, create only if missing.
TARGET_CHANNELS: list[tuple[str, str]] = [
    ("cs-escalations",         "Customer-success escalations and red accounts."),
    ("ar-collections",         "Accounts-receivable collections and dunning."),
    ("deal-desk",              "Deal-desk reviews, discounts, non-standard terms."),
    ("engineering-incidents",  "Production incidents and SEVs."),
    ("billing-platform",       "Billing platform engineering chatter."),
    ("customer-success",       "General CS team channel."),
    ("revops",                 "Revenue operations."),
    ("all-hands",              "Company-wide announcements."),
    ("random",                 "Watercooler."),
]


# ────────────────────────────────────────────────────────────────────────
# Workflow signal messages (W1 / W2 / W3)
# ────────────────────────────────────────────────────────────────────────

# These will be invisible to Coral today but live in the workspace for
# any future Slack source that exposes messages.
SIGNAL_MESSAGES: list[tuple[str, str, str]] = [
    (
        "cs-escalations",
        "W1",
        (
            "Acme Genomics dispute #3 incoming. Same pattern as before - "
            "claim 'I cancelled' but no formal cancel on file and they're "
            "still actively using the product. AE wants the logo retained "
            "but RevOps lead is overriding to fight this one. "
            "dp_acme_v3 on the May renewal, $4,200."
        ),
    ),
    (
        "engineering-incidents",
        "W2",
        (
            ":rotating_light: SEV-1 - billing-webhook-handler "
            "unhandled TypeError 2026-05-12 10:00 UTC. "
            "`invoice.payment_succeeded` events failing to flip the "
            "entitlements table. Customer charges going through but "
            "internal tier not upgrading. @platform-oncall paged. "
            "Sentry: ENT-1742. Datadog dashboard linked in thread."
        ),
    ),
    (
        "cs-escalations",
        "W3",
        (
            "Mockingbird Media double-billed across the legacy → Stripe "
            "cutover. Both ledgers still active, both charged $5,500 in "
            "March + April. They want a refund on the legacy charge. "
            "Per the migration cleanup SOP (Notion: post-acquisition "
            "billing runbook) this is automatic refund + force-cancel "
            "the legacy subscription. Routing to AR."
        ),
    ),
]


# ────────────────────────────────────────────────────────────────────────
# Ambient noise messages - realistic chatter for cosmetic seeding
# ────────────────────────────────────────────────────────────────────────

NOISE_MESSAGES: list[tuple[str, str]] = [
    # ── #engineering-incidents ──
    ("engineering-incidents", "Deploy #4892 going out to prod in 5 min. Touches billing-api only."),
    ("engineering-incidents", "Deploy complete. Error rate stable. Closing watch."),
    ("engineering-incidents", "Brief blip on the public API around 09:14 UTC - already recovered. Investigating."),
    ("engineering-incidents", "Postmortem for INC-238 (CDN cache miss storm) posted: see notion link in #engineering."),
    ("engineering-incidents", "Scheduled DB maintenance window tonight 02:00-03:00 UTC. Read-only mode for ~20 minutes."),
    ("engineering-incidents", ":green_check: SEV-3 from yesterday resolved. Root cause was a stale env var on the staging cluster."),

    # ── #billing-platform ──
    ("billing-platform", "PR up to dedupe webhook deliveries - would appreciate eyes from @karan or @priya."),
    ("billing-platform", "Anyone seen the Stripe `invoice.finalized` event lag spike up to 90s today? Or just me?"),
    ("billing-platform", "Migrating the legacy proration logic into the new Pricing service. Tracking ticket BILL-417."),
    ("billing-platform", "Reminder: please don't hand-edit the entitlements table in prod. There's a runbook for everything."),
    ("billing-platform", "Refactor of dispute-evidence-bundler is in code review. Cleans up the tangled stripe.disputes.update calls."),

    # ── #cs-escalations ──
    ("cs-escalations", "Helix Bio is 47 days past due on a $134k invoice. AR lead is on it but they're going silent."),
    ("cs-escalations", "Acme Logistics churned - final notice sent, will cancel auto-renew at end of cycle."),
    ("cs-escalations", "Voyager Shipping pinged about API rate limits. Bumping their plan throughput by 2x temporarily."),
    ("cs-escalations", "Northwind Logistics opened a ticket - their Enterprise upgrade isn't showing up. Looking into it."),
    ("cs-escalations", "Summit Payments is in renewal negotiation, asking for a 15% discount. Sending to deal-desk."),

    # ── #ar-collections ──
    ("ar-collections", "Dunning run #14 sent this morning. 23 accounts in cycle, 4 paid within the hour."),
    ("ar-collections", "Reminder: any invoice over $50k goes through the manual review queue before automated dunning."),
    ("ar-collections", "Closing Q1 books today. Please file any outstanding writeoff requests by EOD."),
    ("ar-collections", "Stripe payouts arrived on schedule. No discrepancies vs the ledger this week."),
    ("ar-collections", "Helix Bio: escalating to CFO. AR lead requested a payment plan but no response in 5 days."),

    # ── #deal-desk ──
    ("deal-desk", "Q2 pipeline review tomorrow 10am PT. Please update HubSpot stages before then."),
    ("deal-desk", "Phoenix Fund Enterprise renewal closed at $168k - 4% uplift, same logo."),
    ("deal-desk", "Stellar AI multi-year ask - finance needs ramp deal structured by Friday."),
    ("deal-desk", "Reminder: any non-standard MSA terms require legal sign-off in writing, not Slack."),

    # ── #customer-success ──
    ("customer-success", "QBR template v3 is now live in Notion. Please use it for all >$60k ARR accounts."),
    ("customer-success", "Health-score model refresh this week. Some yellows will flip green and vice versa."),
    ("customer-success", "Sharing a great win from Saga Foods - their team expanded usage 3x quarter-over-quarter."),
    ("customer-success", "Friendly reminder: log all customer calls in HubSpot, not in DMs."),
    ("customer-success", "Onboarding deck refresh for the new Pro Annual tier landed. Linked in the playbook."),

    # ── #revops ──
    ("revops", "Pipeline -> ARR conversion rate is up 7% QoQ. Sharing the breakdown in the all-hands tomorrow."),
    ("revops", "Salesforce + HubSpot sync had a 14-minute lag this morning. Resolved."),
    ("revops", "New leadcycle automation rolling out next week. Heads up to AEs - expect fewer manual assignments."),
    ("revops", "Forecast call moved to Wednesday 11am PT. Calendar updated."),

    # ── #all-hands ──
    ("all-hands", "Welcome to our two new hires this week - quick intros at the all-hands tomorrow."),
    ("all-hands", "Q2 OKR check-in posted in Notion. Please update your team's progress by Friday."),
    ("all-hands", "Office closed Memorial Day. Remote-first folks: take the day, you earned it."),
    ("all-hands", "Reminder: open enrollment for benefits ends June 1."),

    # ── #random ──
    ("random", ":coffee: New office espresso machine arrives Friday. Names being accepted."),
    ("random", "Anyone want to grab lunch at the new Thai place down the block? Thursday-ish?"),
    ("random", "Dog of the week: Karan brought in Mochi. Photos in thread."),
    ("random", "Friendly reminder that the rooftop is open Fridays after 4."),
    ("random", "Book club is reading 'The Manager's Path' this month if anyone wants to join."),
]


# ────────────────────────────────────────────────────────────────────────
# HTTP helper with retry + 429 handling
# ────────────────────────────────────────────────────────────────────────


def slack_call(
    client: httpx.Client,
    method: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    retries: int = 3,
) -> dict:
    """POST to a Slack Web API method (always JSON body) and return ``response.json()``.

    Handles 429 ``Retry-After`` automatically. ``params`` is unused except
    for the rare GET endpoint."""
    url = f"{BASE}/{method}"
    for attempt in range(retries):
        if json is None and params is not None:
            r = client.get(url, params=params, headers=HEADERS)
        else:
            r = client.post(url, json=json or {}, headers=HEADERS)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", "1.0"))
            print(f"  ! 429 - sleeping {wait:.1f}s")
            time.sleep(max(wait, 1.0))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(0.5 * (attempt + 1))
            continue
        try:
            return r.json()
        except Exception:
            return {"ok": False, "error": "non_json", "raw": r.text[:200]}
    return {"ok": False, "error": "exhausted_retries"}


# ────────────────────────────────────────────────────────────────────────
# Steps
# ────────────────────────────────────────────────────────────────────────


def step_auth(client: httpx.Client) -> dict:
    print("→ auth.test")
    data = slack_call(client, "auth.test")
    if not data.get("ok"):
        sys.exit(f"ERROR: auth.test failed: {data}")
    print(f"  workspace={data.get('team')!r} user={data.get('user')!r} "
          f"team_id={data.get('team_id')!r}")
    return data


def list_existing_channels(client: httpx.Client) -> dict[str, dict]:
    """Return a {name: channel-dict} map of every non-archived channel."""
    by_name: dict[str, dict] = {}
    cursor = None
    while True:
        params: dict = {
            "limit": 200,
            "exclude_archived": "true",
            "types": "public_channel,private_channel",
        }
        if cursor:
            params["cursor"] = cursor
        data = slack_call(client, "conversations.list", params=params)
        if not data.get("ok"):
            print(f"  ! conversations.list failed: {data}")
            break
        for c in data.get("channels", []):
            by_name[c["name"]] = c
        cursor = data.get("response_metadata", {}).get("next_cursor") or None
        if not cursor:
            break
        time.sleep(API_SLEEP)
    return by_name


def ensure_channel(
    client: httpx.Client,
    name: str,
    purpose: str,
    existing: dict[str, dict],
) -> tuple[str | None, str]:
    """Idempotently ensure ``name`` exists. Returns (channel_id, action)."""
    if name in existing:
        ch = existing[name]
        ch_id = ch["id"]
        # Make sure the bot is a member so it can post.
        if not ch.get("is_member"):
            join = slack_call(
                client, "conversations.join", json={"channel": ch_id}
            )
            if join.get("ok"):
                action = "existing+joined"
            else:
                err = join.get("error", "?")
                # `is_archived`, `method_not_supported_for_channel_type` etc.
                action = f"existing+join_failed:{err}"
            time.sleep(API_SLEEP)
        else:
            action = "existing"
        # Best-effort purpose update - non-fatal if it fails.
        if purpose and ch.get("purpose", {}).get("value", "") != purpose:
            slack_call(
                client,
                "conversations.setPurpose",
                json={"channel": ch_id, "purpose": purpose},
            )
            time.sleep(API_SLEEP)
        return ch_id, action

    print(f"  + creating #{name}")
    data = slack_call(
        client,
        "conversations.create",
        json={"name": name, "is_private": False},
    )
    if not data.get("ok"):
        print(f"  ! create #{name} failed: {data.get('error')}")
        return None, f"create_failed:{data.get('error')}"
    ch_id = data["channel"]["id"]
    time.sleep(API_SLEEP)

    if purpose:
        slack_call(
            client,
            "conversations.setPurpose",
            json={"channel": ch_id, "purpose": purpose},
        )
        time.sleep(API_SLEEP)

    return ch_id, "created"


def list_users(client: httpx.Client) -> list[dict]:
    """Return non-deleted workspace users (humans + bots)."""
    users: list[dict] = []
    cursor = None
    while True:
        params: dict = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = slack_call(client, "users.list", params=params)
        if not data.get("ok"):
            print(f"  ! users.list failed: {data}")
            break
        for u in data.get("members", []):
            if not u.get("deleted"):
                users.append(u)
        cursor = data.get("response_metadata", {}).get("next_cursor") or None
        if not cursor:
            break
        time.sleep(API_SLEEP)
    return users


def post_message(
    client: httpx.Client, channel_id: str, text: str
) -> dict:
    """Post one message. Auto-joins on `not_in_channel`. Sleeps after."""
    data = slack_call(
        client,
        "chat.postMessage",
        json={"channel": channel_id, "text": text},
    )
    if not data.get("ok") and data.get("error") == "not_in_channel":
        join = slack_call(
            client, "conversations.join", json={"channel": channel_id}
        )
        if join.get("ok"):
            time.sleep(API_SLEEP)
            data = slack_call(
                client,
                "chat.postMessage",
                json={"channel": channel_id, "text": text},
            )
    time.sleep(MSG_SLEEP)
    return data


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("Manthan Slack seeder")
    print("=" * 70)
    print("Workspace: ManthanDemo  |  Bot: manthantest")
    print(
        "Coral surface limitation: the Coral `slack` source exposes ONLY\n"
        "  the `channels` and `users` tables - messages posted by this\n"
        "  script will NOT be queryable by the agent today."
    )
    print()

    with httpx.Client(timeout=TIMEOUT) as client:
        step_auth(client)
        print()

        # ── Channels ────────────────────────────────────────────────
        print("→ conversations.list")
        existing = list_existing_channels(client)
        print(f"  found {len(existing)} existing channels: "
              f"{sorted(existing.keys())}")
        print()

        print("→ ensuring target channels")
        channel_results: dict[str, tuple[str | None, str]] = {}
        for name, purpose in TARGET_CHANNELS:
            ch_id, action = ensure_channel(client, name, purpose, existing)
            channel_results[name] = (ch_id, action)
            print(f"  #{name:<25} {action:<35} {ch_id or '-'}")
        print()

        channel_id_by_name = {
            name: cid for name, (cid, _) in channel_results.items() if cid
        }

        # ── Users ───────────────────────────────────────────────────
        print("→ users.list")
        users = list_users(client)
        humans = [u for u in users if not u.get("is_bot")
                  and u.get("name") != "slackbot"]
        bots = [u for u in users if u.get("is_bot")]
        slackbot = [u for u in users if u.get("name") == "slackbot"]
        print(f"  total users: {len(users)} "
              f"(humans: {len(humans)}, bots: {len(bots)}, "
              f"slackbot: {len(slackbot)})")
        for u in users:
            role = ("bot" if u.get("is_bot")
                    else "slackbot" if u.get("name") == "slackbot"
                    else "human")
            print(f"    [{role:<8}] {u.get('name'):<20} {u.get('id')}")
        print()
        print(
            "  NOTE: cannot create new humans programmatically - Slack\n"
            "  workspace users require email invite + acceptance. The\n"
            "  workspace will remain at the current count until an admin\n"
            "  invites people through the Slack UI."
        )
        print()

        # ── W1 / W2 / W3 signal messages ────────────────────────────
        print("→ posting W1/W2/W3 signal messages")
        signal_results: list[tuple[str, str, str, dict]] = []
        for channel_name, signal, text in SIGNAL_MESSAGES:
            ch_id = channel_id_by_name.get(channel_name)
            if not ch_id:
                print(f"  ! skip {signal}: #{channel_name} not available")
                continue
            data = post_message(client, ch_id, text)
            ok = data.get("ok", False)
            ts = data.get("ts", "")
            err = "" if ok else data.get("error", "?")
            print(f"  {signal} → #{channel_name} ({ch_id})  "
                  f"{'OK' if ok else 'FAIL:' + err}  ts={ts}")
            signal_results.append((signal, channel_name, ts, data))
        print()

        # ── Ambient noise messages ──────────────────────────────────
        print(f"→ posting ambient messages ({len(NOISE_MESSAGES)})")
        rng = random.Random(20260527)  # deterministic ordering
        shuffled = NOISE_MESSAGES[:]
        rng.shuffle(shuffled)

        posted = 0
        failed = 0
        for channel_name, text in shuffled:
            ch_id = channel_id_by_name.get(channel_name)
            if not ch_id:
                print(f"  ! skip - #{channel_name} not available")
                failed += 1
                continue
            data = post_message(client, ch_id, text)
            if data.get("ok"):
                posted += 1
            else:
                failed += 1
                print(f"  ! post to #{channel_name} failed: "
                      f"{data.get('error')}")
        print(f"  posted {posted}/{len(NOISE_MESSAGES)} ambient messages "
              f"({failed} failed)")
        print()

        # ── Summary ────────────────────────────────────────────────
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        created = sum(1 for _, (_, a) in channel_results.items()
                      if a == "created")
        existing_count = sum(1 for _, (_, a) in channel_results.items()
                             if a.startswith("existing"))
        print(f"Channels target:   {len(TARGET_CHANNELS)}")
        print(f"  created:         {created}")
        print(f"  existing:        {existing_count}")
        print(f"  failed:          "
              f"{len(TARGET_CHANNELS) - created - existing_count}")
        print(f"Users (existing):  {len(users)} "
              f"({len(humans)} humans + {len(bots)} bot + "
              f"{len(slackbot)} slackbot)")
        print(f"Ambient messages:  {posted} posted, {failed} failed")
        print("Signal messages:")
        for signal, channel_name, ts, data in signal_results:
            ch_id = channel_id_by_name.get(channel_name, "?")
            status = "OK" if data.get("ok") else f"FAIL:{data.get('error')}"
            print(f"  {signal}  #{channel_name:<22} "
                  f"channel={ch_id}  ts={ts}  {status}")
        print()
        print("Coral surface note:")
        print("  The Coral `slack` source exposes ONLY `channels` and "
              "`users` -")
        print("  the messages above (including W1/W2/W3 signals) are "
              "INVISIBLE")
        print("  to the agent today. The real W1/W2/W3 signals live in "
              "Stripe /")
        print("  HubSpot / Linear / Notion / Intercom / etc. as documented "
              "in")
        print("  seed_world.WORKFLOWS. This script's Slack messages are "
              "cosmetic")
        print("  and forward-compatible with any richer Slack source we "
              "wire up")
        print("  later.")


if __name__ == "__main__":
    main()
