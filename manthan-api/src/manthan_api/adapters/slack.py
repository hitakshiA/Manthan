"""Slack adapter - post brief / decision summaries to a channel."""

from __future__ import annotations

import os
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from . import AdapterError, ExecutionResult


def post(payload: dict[str, Any], idempotency_key: str) -> ExecutionResult:
    """Post a message to a Slack channel.

    Required payload keys:
      channel: str (channel id or name without #)
      text: str (fallback text)
      blocks: list (optional rich Block Kit)

    Channel resolution chain when channel_not_found:
      1. The channel the brief requested (drafter's pick)
      2. MANTHAN_SLACK_CHANNEL env (operator's default real channel)
      3. Surface the real Slack error - the action is recorded as
         failed with the error message; we never invent a ts.
    """
    token = os.environ.get("SLACK_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise AdapterError("SLACK_TOKEN missing")
    client = WebClient(token=token)

    channel = payload.get("channel")
    text = payload.get("text", "")
    blocks = payload.get("blocks")
    if not channel:
        raise AdapterError("slack.post payload requires channel")

    fallback = os.environ.get("MANTHAN_SLACK_CHANNEL")

    def _try(ch: str):
        return client.chat_postMessage(
            channel=ch,
            text=text,
            blocks=blocks,
            metadata={
                "event_type": "manthan_action",
                "event_payload": {"idempotency_key": idempotency_key},
            },
        )

    attempted: list[str] = [channel]
    try:
        r = _try(channel)
    except SlackApiError as e:
        err = e.response["error"] if e.response else str(e)
        # Drafter picked a channel that doesn't exist / bot isn't in.
        # Try the env-configured fallback (a real channel) before giving up.
        if err == "channel_not_found" and fallback and fallback != channel:
            attempted.append(fallback)
            try:
                r = _try(fallback)
                return ExecutionResult(
                    external_ref=str(r["ts"]),
                    summary=(
                        f"Posted to {fallback} "
                        f"(brief requested {channel} but that channel was unreachable)"
                    ),
                    raw={
                        "ts": r["ts"],
                        "channel": r["channel"],
                        "requested": channel,
                        "delivered_to": fallback,
                    },
                )
            except SlackApiError as e2:
                err = e2.response["error"] if e2.response else str(e2)
        raise AdapterError(
            f"slack post failed: {err} (tried {', '.join(attempted)})"
        )

    return ExecutionResult(
        external_ref=str(r["ts"]),
        summary=f"Posted to {channel}",
        raw={"ts": r["ts"], "channel": r["channel"]},
    )
