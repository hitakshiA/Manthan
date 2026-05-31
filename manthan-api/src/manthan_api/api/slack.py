"""Slack inbound endpoints - Events API + Interactive (Block Kit buttons + modals).

Two POST routes:

  POST /webhooks/slack/{org_slug}/events
      Slack Events API delivery. Handles URL verification + event_callback.
      We open a case for app_mention / message.im / route thread replies to
      chat_followup on a known case.

  POST /webhooks/slack/{org_slug}/interactive
      Block Kit button clicks + modal submits. The Approve button on a
      Manthan brief card opens a signature modal; submitting the modal
      hits /api/cases/{id}/approve internally.

Both verify the Slack signature using SLACK_SIGNING_SECRET (HMAC-SHA256
over `v0:{timestamp}:{body}` per Slack spec). Requests older than 5min
or with bad signatures are rejected.

Idempotency: Slack retries failed deliveries with the same event_id +
X-Slack-Retry-Num. We dedupe by event_id stored on the case payload.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from manthan_api.config import get_settings
from manthan_api.db import get_conn, get_pool
from manthan_api.services import slack_bot

router = APIRouter(prefix="/webhooks/slack", tags=["slack"])
logger = logging.getLogger("manthan_api.slack")


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _resolve_org(slug: str):
    async with get_conn() as conn:
        row = await conn.fetchrow("SELECT id FROM orgs WHERE slug = $1", slug)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"org not found: {slug}",
        )
    return row["id"]


def _verify_slack_signature(body: bytes, headers: dict[str, str]) -> bool:
    """Verify Slack signature per
    https://api.slack.com/authentication/verifying-requests-from-slack."""
    settings = get_settings()
    secret = settings.slack_signing_secret
    if not secret:
        # In dev with no secret, skip verification but log warning.
        if settings.is_dev:
            logger.warning("SLACK_SIGNING_SECRET unset - skipping signature check (dev only)")
            return True
        return False

    timestamp = headers.get("x-slack-request-timestamp", "")
    sig = headers.get("x-slack-signature", "")
    if not timestamp or not sig:
        return False

    # Reject anything older than 5 minutes (replay attack window).
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False

    base = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


async def _is_duplicate_event(org_id, event_id: str) -> bool:
    """Skip events we've already processed (Slack retries)."""
    if not event_id:
        return False
    async with get_pool().acquire() as conn:
        already = await conn.fetchval(
            """
            SELECT 1 FROM cases
            WHERE org_id = $1
              AND trigger_payload->>'slack_event_id' = $2
            LIMIT 1
            """,
            org_id, event_id,
        )
    return bool(already)


# ──────────────────────────────────────────────────────────────────────
# POST /webhooks/slack/{org_slug}/events
# ──────────────────────────────────────────────────────────────────────


@router.post("/{org_slug}/events", status_code=status.HTTP_200_OK)
async def slack_events(
    org_slug: str,
    request: Request,
    background: BackgroundTasks,
) -> dict[str, Any]:
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not _verify_slack_signature(body, headers):
        raise HTTPException(status_code=401, detail="invalid Slack signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    # 1. URL verification (initial Slack setup).
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    # 2. event_callback.
    if payload.get("type") != "event_callback":
        return {"ok": True, "ignored": True, "type": payload.get("type")}

    org_id = await _resolve_org(org_slug)
    event = payload.get("event") or {}
    event_id = payload.get("event_id") or ""
    event_type = event.get("type")
    event_subtype = event.get("subtype")

    if await _is_duplicate_event(org_id, event_id):
        return {"ok": True, "deduplicated": True, "event_id": event_id}

    # Slack uses "bot_message" subtype for messages posted by our bot - ignore.
    if event_subtype == "bot_message" or event.get("bot_id"):
        return {"ok": True, "ignored": True, "reason": "bot_message"}

    # Run the heavy logic in background so we ACK Slack within 3s.
    background.add_task(_handle_event, org_id, event_id, event)
    return {"ok": True, "queued": True, "event_id": event_id}


async def _handle_event(org_id, event_id: str, event: dict[str, Any]) -> None:
    """Dispatch one Slack event to the right bot handler."""
    try:
        event_type = event.get("type")
        text = event.get("text", "")
        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        thread_ts = event.get("thread_ts")
        event_ts = event.get("ts", "")
        channel_type = event.get("channel_type")

        # Look up user's name for nicer audit trail (best-effort).
        user_name = await _resolve_user_name(user_id)
        channel_name = await _resolve_channel_name(channel_id) if not channel_type == "im" else None

        is_dm = channel_type == "im" or event_type == "message" and channel_type == "im"

        # 1. Thread reply on a known case → chat_followup.
        if thread_ts and thread_ts != event_ts:
            routed = await slack_bot.route_thread_reply(
                org_id=org_id,
                thread_ts=thread_ts,
                channel_id=channel_id,
                user_id=user_id,
                user_name=user_name,
                text=text,
            )
            if routed:
                return
            # Falls through if the thread isn't a known case (treat as new mention).

        # 2. App mention or DM → open a new case.
        if event_type == "app_mention" or is_dm or (
            event_type == "message" and "<@" in text
        ):
            case_id, short_id = await slack_bot.open_case_from_slack(
                org_id=org_id,
                text=text,
                user_id=user_id,
                user_name=user_name,
                channel_id=channel_id,
                channel_name=channel_name,
                is_dm=is_dm,
                event_ts=event_ts,
            )
            # Save the Slack event id for dedup.
            async with get_pool().acquire() as conn:
                await conn.execute(
                    """
                    UPDATE cases
                    SET trigger_payload = trigger_payload ||
                        jsonb_build_object('slack_event_id', $1::text)
                    WHERE id = $2
                    """,
                    event_id, case_id,
                )
            # Acknowledge in-thread with a rich "investigating" Block Kit
            # card. Saves the ack ts as the canonical thread_ts so the
            # brief lands in the same thread + future replies route here.
            try:
                from manthan_api.services.slack_bot import (
                    _client,
                    build_investigating_card,
                    parse_customer_hint,
                )
                import os
                origin = os.environ.get("WEB_APP_ORIGIN", "https://demo.manthan.quest")
                deep_link = f"{origin}/app/case/{case_id}"
                customer_hint = parse_customer_hint(text)
                surface_label = "Slack DM" if is_dm else f"#{channel_name or 'channel'} mention"
                blocks = build_investigating_card(
                    short_id=short_id,
                    customer_hint=customer_hint,
                    requester_slack_id=user_id,
                    deep_link=deep_link,
                    surface_label=surface_label,
                )
                resp = _client().chat_postMessage(
                    channel=channel_id,
                    thread_ts=event_ts if not is_dm else None,
                    text=f"Manthan investigating {short_id}",
                    blocks=blocks,
                )
                ack_ts = resp.get("ts")
                # Persist the ack ts as the canonical thread anchor so
                # subsequent thread replies route here (and so the brief
                # card lands in the same thread).
                if ack_ts:
                    async with get_pool().acquire() as conn:
                        await conn.execute(
                            """
                            UPDATE cases
                            SET trigger_payload = trigger_payload ||
                                jsonb_build_object(
                                    'slack_thread_ts', $1::text,
                                    'slack_thread_channel', $2::text,
                                    'slack_investigating_ts', $1::text
                                )
                            WHERE id = $3
                            """,
                            ack_ts, channel_id, case_id,
                        )
            except Exception as e:  # noqa: BLE001
                logger.warning("investigating card post failed: %s", e)
            return

        logger.info("slack event unhandled: type=%s subtype=%s",
                    event_type, event.get("subtype"))
    except Exception as e:  # noqa: BLE001
        logger.exception("slack event handler crashed: %s", e)


async def _resolve_user_name(user_id: str) -> str:
    """Best-effort users.info lookup. Falls back to the ID."""
    if not user_id:
        return "(unknown)"
    try:
        from manthan_api.services.slack_bot import _client
        r = _client().users_info(user=user_id)
        u = r.get("user") or {}
        return u.get("real_name") or u.get("name") or user_id
    except Exception:
        return user_id


async def _resolve_channel_name(channel_id: str) -> str | None:
    if not channel_id:
        return None
    try:
        from manthan_api.services.slack_bot import _client
        r = _client().conversations_info(channel=channel_id)
        ch = r.get("channel") or {}
        return ch.get("name")
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# POST /webhooks/slack/{org_slug}/interactive
# ──────────────────────────────────────────────────────────────────────


@router.post("/{org_slug}/interactive", status_code=status.HTTP_200_OK)
async def slack_interactive(
    org_slug: str,
    request: Request,
    background: BackgroundTasks,
) -> dict[str, Any]:
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not _verify_slack_signature(body, headers):
        raise HTTPException(status_code=401, detail="invalid Slack signature")

    # Interactive payloads are urlencoded with `payload=<json>`.
    form = urllib.parse.parse_qs(body.decode("utf-8"))
    raw = (form.get("payload") or [""])[0]
    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid interactive payload")

    org_id = await _resolve_org(org_slug)
    ptype = payload.get("type")

    # Block Kit button click on a brief card.
    if ptype == "block_actions":
        actions = payload.get("actions") or []
        if not actions:
            return {"ok": True}
        action = actions[0]
        action_id = action.get("action_id", "")
        case_id = action.get("value", "")
        trigger_id = payload.get("trigger_id", "")
        user = payload.get("user") or {}

        if action_id == "manthan_approve":
            # Open signature modal.
            from manthan_api.services.slack_bot import build_signature_modal, open_modal
            # Look up short_id for the modal title.
            async with get_pool().acquire() as conn:
                short = await conn.fetchval(
                    "SELECT short_id FROM cases WHERE org_id=$1 AND id=$2",
                    org_id, case_id,
                )
            view = build_signature_modal(case_id, short or "case")
            background.add_task(open_modal, trigger_id, view)
            return {"ok": True}

        if action_id == "manthan_hold":
            background.add_task(
                _do_hold, org_id, case_id, user.get("id"), user.get("name"),
                payload.get("channel", {}).get("id"),
                payload.get("message", {}).get("ts"),
            )
            return {"ok": True}

        if action_id == "manthan_view":
            return {"ok": True}  # link click - no server action needed

    # Modal submission (signature submit).
    if ptype == "view_submission":
        view = payload.get("view") or {}
        if view.get("callback_id") != "manthan_approve_modal":
            return {"ok": True}
        case_id = view.get("private_metadata") or ""
        state_values = (view.get("state") or {}).get("values") or {}
        full_name = (
            ((state_values.get("full_name_input") or {}).get("full_name") or {})
            .get("value")
        ) or ""
        role = (
            ((state_values.get("role_input") or {}).get("role") or {}).get("value")
        ) or ""
        note = (
            ((state_values.get("note_input") or {}).get("note") or {}).get("value")
        ) or ""
        user = payload.get("user") or {}

        # Validate both fields filled (Slack already enforces required on
        # an input block, but defend in depth).
        if not full_name.strip() or not role.strip():
            return {
                "response_action": "errors",
                "errors": {
                    "full_name_input"
                    if not full_name.strip()
                    else "role_input": (
                        "Required for the audit signature."
                    ),
                },
            }

        background.add_task(
            _do_approve_with_signature,
            org_id, case_id, user.get("id"), user.get("name") or "(slack user)",
            full_name.strip(), role.strip(), note,
        )
        # Slack expects empty response_action for a successful close.
        return {"response_action": "clear"}

    return {"ok": True}


async def _do_hold(
    org_id,
    case_id: str,
    slack_user_id: str | None,
    slack_user_name: str | None,
    channel_id: str | None,
    message_ts: str | None,
) -> None:
    """Flip the case to escalated + post a thread acknowledgment."""
    try:
        async with get_pool().acquire() as conn:
            thread_id = await conn.fetchval(
                "SELECT thread_id FROM cases WHERE org_id=$1 AND id=$2",
                org_id, case_id,
            )
            if thread_id is None:
                return
            await conn.execute(
                "UPDATE cases SET status='escalated' WHERE id=$1",
                case_id,
            )
            for attempt in range(5):
                try:
                    await conn.execute(
                        """
                        WITH next AS (
                            SELECT COALESCE(MAX(seq), 0) + 1 AS s
                            FROM events WHERE org_id=$1 AND thread_id=$2
                        )
                        INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                        SELECT $1, $2, s, 'human_hold', $3, $4 FROM next
                        """,
                        org_id, thread_id,
                        f"slack:user:{slack_user_id}",
                        json.dumps({"slack_user_name": slack_user_name, "via": "slack"}),
                    )
                    break
                except Exception:
                    if attempt == 4:
                        raise
                    import asyncio
                    await asyncio.sleep(0.02 * (attempt + 1))

        if channel_id and message_ts:
            from manthan_api.services.slack_bot import post_reply_to_thread
            await post_reply_to_thread(
                channel_id=channel_id,
                thread_ts=message_ts,
                text=f":pause_button: Held for review by {slack_user_name}. No actions will execute.",
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("hold action failed: %s", e)


async def _do_approve_with_signature(
    org_id,
    case_id: str,
    slack_user_id: str,
    slack_user_name: str,
    full_name: str,
    role: str,
    note: str,
) -> None:
    """Flip drafted actions to approved with the signature attached, write
    human_approved event, post confirmation in the thread.

    Signature shape: `<full_name>, <role>` (stored verbatim on each
    action payload + replicated as the `approval_full_name` and
    `approval_role` fields for clean structured access from the UI).
    """
    signature = f"{full_name}, {role}"
    signer_display = f"{full_name} · {role}"
    try:
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                approved = await conn.fetch(
                    """
                    UPDATE actions
                    SET status='approved',
                        approved_at=now(),
                        payload = payload || jsonb_build_object(
                            'approved_via', 'slack',
                            'approval_signature', $3::text,
                            'approval_full_name', $4::text,
                            'approval_role', $5::text,
                            'approval_note', $6::text,
                            'approved_by_slack_user', $7::text
                        )
                    WHERE org_id=$1 AND case_id=$2 AND status='drafted'
                    RETURNING id, type
                    """,
                    org_id, case_id, signature, full_name, role, note,
                    slack_user_name,
                )
                await conn.execute(
                    "UPDATE cases SET status='acting' WHERE id=$1",
                    case_id,
                )
                # Stash the signer display on the case so the
                # actions-performed card later includes it verbatim.
                await conn.execute(
                    """
                    UPDATE cases
                    SET trigger_payload = trigger_payload ||
                        jsonb_build_object('slack_signer_display', $2::text)
                    WHERE id=$1
                    """,
                    case_id, signer_display,
                )
                thread_id = await conn.fetchval(
                    "SELECT thread_id FROM cases WHERE id=$1", case_id,
                )
                for attempt in range(5):
                    try:
                        await conn.execute(
                            """
                            WITH next AS (
                                SELECT COALESCE(MAX(seq), 0) + 1 AS s
                                FROM events WHERE org_id=$1 AND thread_id=$2
                            )
                            INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                            SELECT $1, $2, s, 'human_approved', $3, $4 FROM next
                            """,
                            org_id, thread_id,
                            f"slack:user:{slack_user_id}",
                            json.dumps({
                                "action_ids": [str(r["id"]) for r in approved],
                                "signature": signature,
                                "full_name": full_name,
                                "role": role,
                                "note": note,
                                "slack_user_name": slack_user_name,
                                "via": "slack",
                            }),
                        )
                        break
                    except Exception:
                        if attempt == 4:
                            raise
                        import asyncio
                        await asyncio.sleep(0.02 * (attempt + 1))

        # Post confirmation in the Slack thread tied to this case.
        async with get_pool().acquire() as conn:
            t = await conn.fetchrow(
                """
                SELECT trigger_payload->>'slack_thread_ts' AS ts,
                       trigger_payload->>'slack_thread_channel' AS channel
                FROM cases WHERE id=$1
                """,
                case_id,
            )
        if t and t["ts"] and t["channel"]:
            from manthan_api.services.slack_bot import post_reply_to_thread
            await post_reply_to_thread(
                channel_id=t["channel"],
                thread_ts=t["ts"],
                text=(
                    f":white_check_mark: Signed by *{full_name}* - _{role}_.\n"
                    f"Executing {len(approved)} action(s). I'll post the "
                    "final receipts here when they land."
                ),
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("approve-with-signature failed: %s", e)
