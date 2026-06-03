"""Slack notifier - mirror major case events back to the originating Slack thread.

Called from the investigate worker + chat_loop after writing key events to PG:
  - brief_drafted: post the brief Block Kit card to the thread
  - agent_reply  : post the plain text reply
  - case_closed (after acting): post a success summary with action results

A case has a Slack thread ref iff it was opened via slack_mention or slack_dm
(in which case trigger_payload carries slack_thread_channel + slack_thread_ts).
For cases opened elsewhere, this is a no-op.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from manthan_api.db import get_pool

logger = logging.getLogger("services.slack_notifier")


async def maybe_notify(
    *,
    org_id: UUID,
    thread_id: UUID,
    case_id: UUID,
    event_type: str,
    event_data: dict[str, Any] | None = None,
) -> None:
    """Dispatch a Slack notification if the case has a thread ref."""
    if event_type not in ("brief_drafted", "agent_reply", "case_closed"):
        return

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT trigger_surface,
                   trigger_payload->>'slack_thread_ts' AS thread_ts,
                   trigger_payload->>'slack_thread_channel' AS channel_id,
                   trigger_payload->>'slack_event_ts' AS event_ts,
                   trigger_payload->>'slack_channel_id' AS origin_channel_id
            FROM cases WHERE id = $1
            """,
            case_id,
        )
    if row is None:
        return

    surface = row["trigger_surface"]
    if surface not in ("slack_mention", "slack_dm"):
        return

    # Use the saved thread ts/channel if the brief was posted; otherwise
    # fall back to the original mention/DM channel + ts.
    channel_id = row["channel_id"] or row["origin_channel_id"]
    # For channel mentions: thread under the ack so the conversation stays
    # in one anchor. For DMs: post FLAT (thread_ts=None) - DM threads are
    # hidden behind a "View replies" tap and users would miss the brief.
    # The user's DM thread IS the conversation, so flat is the natural
    # surface; matches the handwritten-flow note "agent reachable from DM".
    if surface == "slack_dm":
        thread_ts = None
    else:
        thread_ts = row["thread_ts"] or row["event_ts"]
    if not channel_id:
        return

    try:
        if event_type == "brief_drafted":
            from manthan_api.services.slack_bot import post_brief_to_thread
            await post_brief_to_thread(
                org_id=org_id,
                case_id=case_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
        elif event_type == "agent_reply":
            text = (event_data or {}).get("text") or ""
            if text:
                from manthan_api.services.slack_bot import post_reply_to_thread
                await post_reply_to_thread(
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    text=text,
                )
        elif event_type == "case_closed":
            # Rich "Actions performed · Case closed" Block Kit card,
            # gathered fresh from the database so it reflects every
            # action's external_ref + verified-or-not status.
            await maybe_notify_case_closed_card(
                org_id=org_id,
                case_id=case_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("slack notify failed (case=%s event=%s): %s", case_id, event_type, e)


async def maybe_notify_case_closed_card(
    *,
    org_id: UUID,
    case_id: UUID,
    channel_id: str | None = None,
    thread_ts: str | None = None,
) -> None:
    """Post the actions-performed close card to the Slack thread.

    Caller can pass (channel_id, thread_ts) when they already know them;
    otherwise we look them up from trigger_payload. No-op if the case
    isn't Slack-originated.
    """
    import os

    async with get_pool().acquire() as conn:
        case = await conn.fetchrow(
            """
            SELECT short_id, customer_ref, trigger_surface,
                   trigger_payload->>'slack_thread_ts' AS ts,
                   trigger_payload->>'slack_thread_channel' AS channel,
                   trigger_payload->>'slack_signer_display' AS signer
            FROM cases WHERE id = $1
            """,
            case_id,
        )
        if case is None:
            return
        if case["trigger_surface"] not in ("slack_mention", "slack_dm"):
            return
        channel_id = channel_id or case["channel"]
        # DMs: post flat (thread_ts=None) so the close card lands directly
        # in the DM and the user actually sees it. Channel mentions: keep
        # threading under the original ack/brief anchor.
        is_dm_surface = case["trigger_surface"] == "slack_dm"
        if is_dm_surface:
            thread_ts = None
            if not channel_id:
                return
        else:
            thread_ts = thread_ts or case["ts"]
            if not channel_id or not thread_ts:
                return

        action_rows = await conn.fetch(
            """
            SELECT type, status, external_ref, payload
            FROM actions
            WHERE case_id = $1
            ORDER BY seq ASC
            """,
            case_id,
        )

    # Build executed / failed groupings.
    from manthan_api.services.slack_bot import (
        _action_block_summary,
        build_actions_performed_card,
        post_blocks_to_thread,
    )

    def _row_dict(row) -> dict:
        summary = _action_block_summary(row["type"], row["payload"])
        ref = row["external_ref"]
        ref_url = _ref_url(row["type"], ref) if ref else None
        return {
            "emoji": summary["emoji"],
            "title": summary["title"] + (f" - {summary['target']}" if summary["target"] else ""),
            "ref_text": ref or "",
            "ref_url": ref_url or "",
        }

    executed = [_row_dict(r) for r in action_rows if r["status"] == "succeeded"]
    failed = [
        _row_dict(r) for r in action_rows if r["status"] in ("failed", "drift")
    ]

    web_origin = os.environ.get("WEB_APP_ORIGIN", "https://demo.manthan.quest")
    deep_link = f"{web_origin}/app/case/{case_id}"

    blocks = build_actions_performed_card(
        short_id=case["short_id"],
        customer=case["customer_ref"] or "(unknown customer)",
        executed=executed,
        failed=failed,
        signer_display=case["signer"],
        deep_link=deep_link,
    )
    try:
        await post_blocks_to_thread(
            channel_id=channel_id,
            thread_ts=thread_ts,
            text=f"Case closed · {case['short_id']}",
            blocks=blocks,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("close-card post failed: %s", e)


def _ref_url(kind: str, ref: str) -> str | None:
    """Slim version of the actor's _source_ref_url - kept here so the
    close card can build links without importing the worker module."""
    if kind == "stripe_refund":
        return f"https://dashboard.stripe.com/test/refunds/{ref}"
    if kind == "stripe_dispute_response":
        return f"https://dashboard.stripe.com/test/disputes/{ref}"
    if kind == "notion_decision_log":
        return f"https://www.notion.so/{ref.replace('-', '')}"
    return None
