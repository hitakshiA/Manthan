"""Notion adapter - write a case decision log page."""

from __future__ import annotations

import os
from typing import Any

import httpx

from . import AdapterError, ExecutionResult

NOTION_VERSION = "2022-06-28"


def _client() -> httpx.Client:
    token = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN")
    if not token:
        raise AdapterError("NOTION_API_KEY missing")
    return httpx.Client(
        base_url="https://api.notion.com/v1",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def append_decision_log(payload: dict[str, Any], idempotency_key: str) -> ExecutionResult:
    """Append a decision log block to a Notion parent page.

    Required payload keys:
      parent_page_id: Notion page id (the case-decision-log parent)
      title: e.g. "CASE-W1R / Acme Genomics / fight $4,200"
      body: markdown-ish text of the brief + decision
    """
    parent = payload.get("parent_page_id")
    title = payload.get("title", "Manthan decision log entry")
    body = payload.get("body", "")
    if not parent:
        raise AdapterError("notion.append payload requires parent_page_id")

    with _client() as c:
        try:
            r = c.post(
                "/pages",
                json={
                    "parent": {"page_id": parent},
                    "properties": {
                        "title": {
                            "title": [{"type": "text", "text": {"content": title}}]
                        }
                    },
                    "children": _markdown_to_blocks(body, idempotency_key),
                },
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise AdapterError(f"notion append failed: {e.response.status_code} {e.response.text[:200]}")

    page = r.json()
    page_id = page.get("id", "")
    return ExecutionResult(
        external_ref=page_id,
        summary=f"Notion decision log page created: {title}",
        raw={"id": page_id, "url": page.get("url")},
    )


def _markdown_to_blocks(body: str, idempotency_key: str) -> list[dict[str, Any]]:
    """Tiny markdown → Notion blocks converter (paragraphs + footer)."""
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    blocks: list[dict[str, Any]] = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": p}}],
            },
        }
        for p in paragraphs
    ]
    blocks.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Manthan idempotency key: {idempotency_key}"},
            }],
            "icon": {"type": "emoji", "emoji": "🪶"},
            "color": "gray_background",
        },
    })
    return blocks
