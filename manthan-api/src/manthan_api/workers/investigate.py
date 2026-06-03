"""worker.investigate - listens on PG NOTIFY, runs the agent brain per case.

Flow per case:
    case_opened event arrives → fetch trigger text + org context →
    spawn Coral session for this org → run manthan_agent.loop.run_case →
    for each Event the agent yields, write a row to PG events +
    update derived projections (cases.status, findings table).

This wraps the existing agent brain - no logic changes. The brain is
package `manthan_agent` from /Users/akshmnd/Dev Projects/manthanv2/agent.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import re  # noqa: F401 (used in nested function)
from typing import Any
from uuid import UUID

import asyncpg

from manthan_api.config import get_settings
from manthan_api.db import get_pool

# Bring in the existing agent brain
from manthan_agent import config as agent_config
from manthan_agent.coral_session import (
    clear_active_coral_session,
    coral_mcp_session,
    set_active_coral_session,
)
from manthan_agent.loop import run_case
from manthan_agent.state import EventStore as AgentEventStore
from manthan_agent.types import CaseTrigger

logger = logging.getLogger("worker.investigate")


# ──────────────────────────────────────────────────────────────────────
# Mapping agent's Event.kind → our Postgres event types
# Mostly a passthrough; we just make sure they all land.
# ──────────────────────────────────────────────────────────────────────


def _serialize(value: Any) -> Any:
    """Best-effort JSON-friendly serializer for arbitrary agent payloads."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if dataclasses.is_dataclass(value):
        return _serialize(dataclasses.asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:  # noqa: BLE001
            pass
    return str(value)


# ──────────────────────────────────────────────────────────────────────
# Worker
# ──────────────────────────────────────────────────────────────────────


class InvestigateWorker:
    """Drains case_opened events from Postgres NOTIFY + investigates each."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()
        self._stop = asyncio.Event()

    async def run(self) -> None:
        """Subscribe to manthan_event channel and dispatch."""
        pool = get_pool()
        # Hold a dedicated listener connection (not from the pool - listener
        # connections shouldn't be returned mid-use).
        conn = await asyncpg.connect(dsn=get_settings().database_url)

        try:
            await conn.add_listener("manthan_event", self._on_notify)
            logger.info("worker.investigate listening on manthan_event")

            # Catch up on any case_opened events that landed before we
            # started - process them now.
            await self._catch_up_pending()

            await self._stop.wait()
        finally:
            try:
                await conn.remove_listener("manthan_event", self._on_notify)
            except Exception:  # noqa: BLE001
                pass
            await conn.close()
            for task in list(self._tasks):
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

    def stop(self) -> None:
        self._stop.set()

    # ───────── notifier callback ─────────

    def _on_notify(
        self,
        _conn: asyncpg.Connection,
        _pid: int,
        _channel: str,
        payload: str,
    ) -> None:
        try:
            data = json.loads(payload)
        except Exception:  # noqa: BLE001
            return
        evt_type = data.get("type")
        org_id = UUID(data["org_id"])
        thread_id = UUID(data["thread_id"])

        if evt_type == "case_opened":
            task = asyncio.create_task(self._investigate(org_id, thread_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        elif evt_type == "human_followup":
            task = asyncio.create_task(self._followup(org_id, thread_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    # ───────── catch up on missed events from before startup ─────────

    async def _catch_up_pending(self) -> None:
        """Find any case_opened events with no corresponding case_closed and
        kick off investigation."""
        async with get_pool().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT e.org_id, e.thread_id
                FROM events e
                WHERE e.type = 'case_opened'
                  AND NOT EXISTS (
                      SELECT 1 FROM events f
                      WHERE f.org_id = e.org_id
                        AND f.thread_id = e.thread_id
                        AND f.type IN ('case_closed', 'investigation_started')
                  )
                ORDER BY e.org_id, e.thread_id
                """,
            )
        for row in rows:
            task = asyncio.create_task(
                self._investigate(row["org_id"], row["thread_id"])
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        if rows:
            logger.info("worker.investigate caught up: %d pending cases", len(rows))

    # ───────── per-case investigation ─────────

    async def _investigate(self, org_id: UUID, thread_id: UUID) -> None:
        """Pull the trigger event, run the agent, mirror events to PG."""
        log = logger.getChild(str(thread_id)[:8])
        log.info("investigation start org=%s", org_id)

        async with get_pool().acquire() as conn:
            opened = await conn.fetchrow(
                """
                SELECT data FROM events
                WHERE org_id = $1 AND thread_id = $2 AND type = 'case_opened'
                ORDER BY seq ASC LIMIT 1
                """,
                org_id,
                thread_id,
            )
            case_row = await conn.fetchrow(
                """
                SELECT id, short_id, status FROM cases
                WHERE org_id = $1 AND thread_id = $2
                """,
                org_id,
                thread_id,
            )
        if opened is None or case_row is None:
            log.warning("no case row or case_opened event - skipping")
            return

        case_id = case_row["id"]
        opened_data = opened["data"] if isinstance(opened["data"], dict) else json.loads(opened["data"])
        trigger_text = opened_data.get("trigger_text", "")

        # Dedupe: if investigation_started already exists for this thread,
        # someone else is already on it.
        async with get_pool().acquire() as conn:
            already = await conn.fetchval(
                """
                SELECT 1 FROM events
                WHERE org_id=$1 AND thread_id=$2 AND type='investigation_started'
                LIMIT 1
                """,
                org_id, thread_id,
            )
        if already:
            log.info("already in flight (investigation_started exists) - skipping")
            return

        # Mark investigation_started so catch-up + NOTIFY don't race.
        await self._append_event(
            org_id, thread_id, "investigation_started", "system",
            {"trigger_surface": opened_data.get("trigger_surface", "api")},
        )

        # Mark case status investigating
        async with get_pool().acquire() as conn:
            await conn.execute(
                "UPDATE cases SET status = 'investigating' WHERE id = $1",
                case_id,
            )

        trigger = CaseTrigger(
            case_id=str(thread_id),
            text=trigger_text,
            source_surface=opened_data.get("trigger_surface", "api"),
        )
        cfg = agent_config.load()
        agent_store = AgentEventStore()

        finding_seq = 0
        terminal_summary: dict[str, Any] = {}

        # Spawn a Coral session per investigation. Future: pool per org.
        coral_binary = get_settings().coral_binary
        try:
            async with coral_mcp_session(coral_binary) as session:
                token = set_active_coral_session(session)
                try:
                    async for evt in run_case(trigger, cfg, agent_store):
                        await self._mirror_event(
                            org_id=org_id,
                            thread_id=thread_id,
                            case_id=case_id,
                            agent_evt=evt,
                            finding_seq_ref=[finding_seq],
                        )
                        # finding_seq may have advanced inside _mirror_event
                        if evt.kind == "finding_recorded":
                            finding_seq += 1
                        if evt.kind == "case_closed":
                            terminal_summary = _serialize(evt.data) if isinstance(evt.data, dict) else {}
                finally:
                    clear_active_coral_session(token)
        except Exception as e:  # noqa: BLE001
            log.exception("investigation failed: %s", e)
            await self._append_event(
                org_id, thread_id, "error", "system",
                {"reason": "worker_exception", "detail": f"{type(e).__name__}: {e}"},
            )
            async with get_pool().acquire() as conn:
                await conn.execute(
                    "UPDATE cases SET status = 'errored' WHERE id = $1",
                    case_id,
                )
            return

        # Update case projection with final decision.
        await self._finalize_case(
            org_id=org_id, thread_id=thread_id, case_id=case_id,
            agent_store=agent_store, terminal_summary=terminal_summary,
        )
        log.info("investigation done")

    # ───────── follow-up (chat) ─────────

    async def _followup(self, org_id: UUID, thread_id: UUID) -> None:
        """User asked a follow-up. Hand off to the toolful chat loop which
        can re-run Coral queries, record new findings, amend the brief, and
        reply - the operator is talking to the same agent that wrote the
        brief, with the same tool surface."""
        log = logger.getChild(str(thread_id)[:8] + ".chat")

        # Fetch the case + last human_followup event.
        async with get_pool().acquire() as conn:
            case_row = await conn.fetchrow(
                "SELECT id FROM cases WHERE org_id=$1 AND thread_id=$2",
                org_id, thread_id,
            )
            followup = await conn.fetchrow(
                """
                SELECT data FROM events
                WHERE org_id=$1 AND thread_id=$2 AND type='human_followup'
                ORDER BY seq DESC LIMIT 1
                """,
                org_id, thread_id,
            )
        if case_row is None or followup is None:
            log.warning("no case or followup event - skipping")
            return

        case_id = case_row["id"]
        fdata = followup["data"] if isinstance(followup["data"], dict) else json.loads(followup["data"])
        user_message = fdata.get("message", "")
        log.info("followup (toolful): %s", user_message[:120])

        # Mark thinking (UI shows "agent is investigating your follow-up…").
        await self._append_event(
            org_id, thread_id, "agent_thinking", "agent",
            {"about": "human_followup_toolful"},
        )

        # Delegate to the chat loop - spawns Coral session, runs ReAct with
        # coral_sql/record_finding/amend_brief/reply tools, emits all
        # tool_call/tool_result/finding_recorded/brief_amended/agent_reply
        # events back into the same thread.
        from manthan_api.workers.chat_loop import run_chat_followup

        try:
            await run_chat_followup(
                org_id=org_id,
                thread_id=thread_id,
                case_id=case_id,
                user_message=user_message,
                append_event=self._append_event,
                append_finding=self._append_finding,
                synthesize_actions=self._synthesize_actions,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("chat loop failed: %s", e)
            await self._append_event(
                org_id, thread_id, "error", "system",
                {"reason": "chat_loop_failed", "detail": f"{type(e).__name__}: {e}"},
            )

        # Return case to awaiting_approval so the UI re-renders the
        # drafted-actions surface (the chat loop may have regenerated them).
        async with get_pool().acquire() as conn:
            await conn.execute(
                "UPDATE cases SET status='awaiting_approval' WHERE id=$1 AND status='investigating'",
                case_id,
            )
        log.info("followup chat loop done")

    async def _append_finding(
        self,
        org_id: UUID,
        case_id: UUID,
        text: str,
        confidence: float,
        citations: list[dict[str, Any]],
    ) -> None:
        """Insert a new finding row (used by chat loop's record_finding)."""
        async with get_pool().acquire() as conn:
            next_seq = await conn.fetchval(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM findings WHERE case_id = $1",
                case_id,
            )
            await conn.execute(
                """
                INSERT INTO findings (org_id, case_id, seq, text, confidence, citations)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                org_id, case_id, next_seq, text, confidence, citations,
            )

    async def _synthesize_actions(
        self,
        org_id: UUID,
        thread_id: UUID,
        case_id: UUID,
        decision_action: str | None,
        amount_minor: int | None,
    ) -> list[dict[str, Any]]:
        """Build a defensible action set from the decision + case context.

        Used when the agent's brief doesn't populate drafted_actions itself.
        Parses charge/dispute IDs out of the trigger text + findings.
        """
        import re

        # Pull trigger + key context
        async with get_pool().acquire() as conn:
            opened = await conn.fetchrow(
                """
                SELECT data FROM events
                WHERE org_id=$1 AND thread_id=$2 AND type='case_opened'
                ORDER BY seq ASC LIMIT 1
                """,
                org_id, thread_id,
            )
            case_row = await conn.fetchrow(
                "SELECT short_id, customer_ref FROM cases WHERE id=$1",
                case_id,
            )
        opened_data = opened["data"] if isinstance(opened["data"], dict) else {}
        trigger_text = str(opened_data.get("trigger_text", ""))
        short_id = case_row["short_id"] if case_row else ""
        customer = case_row["customer_ref"] if case_row else "the customer"

        # Prefer an explicitly-labeled "Duplicate charge:" id when present
        # (Maya scenario lists both the original AND the duplicate; refund
        # the latter). Falls back to first ch_* match for chargeback cases
        # that only mention one charge.
        opened_payload = opened_data  # already the full case_opened data dict
        duplicate_explicit = opened_payload.get("duplicate_charge_id")
        if duplicate_explicit:
            charge_id = str(duplicate_explicit)
        else:
            duplicate_label_match = re.search(
                r"Duplicate charge:\s*(ch_[A-Za-z0-9]+)", trigger_text
            )
            if duplicate_label_match:
                charge_id = duplicate_label_match.group(1)
            else:
                m = re.search(r"(ch_[A-Za-z0-9]+)", trigger_text)
                charge_id = m.group(1) if m else None

        dispute_match = re.search(r"(du_[A-Za-z0-9]+)", trigger_text)
        dispute_id = dispute_match.group(1) if dispute_match else None

        actions: list[dict[str, Any]] = []

        # 1. Money action (Stripe)
        if decision_action == "refund" and charge_id:
            actions.append({
                "kind": "stripe_refund",
                "description": f"Refund {_dollars(amount_minor)} to {customer} via Stripe",
                "payload": {
                    "charge": charge_id,
                    "amount_minor": amount_minor,
                    "reason": "requested_by_customer",
                    "metadata": {"manthan_case_short_id": short_id},
                },
            })
        elif decision_action == "fight" and dispute_id:
            actions.append({
                "kind": "stripe_dispute_response",
                "description": f"Submit fight evidence to Stripe dispute {dispute_id}",
                "payload": {
                    "dispute": dispute_id,
                    "submit": False,  # safe demo default - don't auto-submit
                    "evidence": {
                        "uncategorized_text": (
                            f"Manthan investigation brief for case {short_id}: "
                            "customer-claimed cancellation not supported by records. "
                            "See findings."
                        ),
                    },
                },
            })
        elif decision_action == "partial_credit" and charge_id and amount_minor:
            actions.append({
                "kind": "stripe_refund",
                "description": f"Issue partial credit of {_dollars(amount_minor)} via Stripe",
                "payload": {
                    "charge": charge_id,
                    "amount_minor": amount_minor,
                    "reason": "requested_by_customer",
                    "metadata": {
                        "manthan_case_short_id": short_id,
                        "credit_type": "partial",
                    },
                },
            })

        # 2. Customer email (Resend) - every case ends with a comms touchpoint
        email_subject = {
            "refund": f"Refund processed - case {short_id}",
            "fight": f"Update on your dispute - case {short_id}",
            "partial_credit": f"Credit applied - case {short_id}",
            "escalate": f"We're looking into your request - case {short_id}",
        }.get(decision_action or "", f"Update on your case {short_id}")
        # Resolve customer email:
        # - If customer_ref looks like an email (e.g. from inbound_email surface
        #   where Maya is `hitakshi220@gmail.com`), use it directly.
        # - Otherwise fall back to a deliverable internal address until CRM
        #   resolution is wired (TODO).
        import re as _re
        if customer and _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(customer)):
            customer_email_to = str(customer)
        else:
            customer_email_to = os.environ.get(
                "MANTHAN_FALLBACK_CUSTOMER_EMAIL", "ops@manthan.quest",
            )

        # Body - keep autonomous-refund tone distinct from HITL tone
        if decision_action == "refund":
            body_text = (
                f"Hi,\n\n"
                f"Confirmed the duplicate charge on your account - we've issued a "
                f"refund of {_dollars(amount_minor)}. You should see it back on your card "
                f"within 5-10 business days.\n\n"
                f"For transparency: our records show the charge was retried due to "
                f"a brief webhook handler error on our side. We've already filed an "
                f"internal ticket to harden that path.\n\n"
                f"If you don't see the refund land or have any other questions, just "
                f"reply to this email.\n\n"
                f"- Caldera Support\n"
                f"(handled autonomously by Manthan · case {short_id} · policy: small-refund-auto)"
            )
        elif decision_action == "fight":
            body_text = (
                f"Hi,\n\nWe've reviewed the dispute on your account and we're "
                f"submitting evidence to your bank that the charge was valid. "
                f"Our records show active product usage during the period in "
                f"question.\n\n- Caldera Support\n(case {short_id})"
            )
        elif decision_action == "partial_credit":
            body_text = (
                f"Hi,\n\nWe've credited {_dollars(amount_minor)} back to your account. "
                f"Reach out if you'd like to discuss further.\n\n"
                f"- Caldera Support\n(case {short_id})"
            )
        else:
            body_text = (
                f"Hi,\n\nWe're looking into your request. A team member will be "
                f"in touch shortly.\n\n- Caldera Support\n(case {short_id})"
            )

        actions.append({
            "kind": "customer_email",
            "description": f"Send {decision_action or 'status'} email to {customer}",
            "payload": {
                "to": customer_email_to,
                "subject": email_subject,
                "body_text": body_text,
            },
        })

        # 3. Notion decision log - internal audit trail
        notion_parent = os.environ.get("NOTION_DECISION_LOG_PARENT_ID")
        if notion_parent:
            actions.append({
                "kind": "notion_decision_log",
                "description": "Append decision log to Notion ops repo",
                "payload": {
                    "parent_page_id": notion_parent,
                    "title": f"{short_id} · {customer} · {decision_action}",
                    "body": (
                        f"Case: {short_id}\n\nCustomer: {customer}\n\nDecision: {decision_action}\n\n"
                        f"Amount: {_dollars(amount_minor)}\n\nTrigger:\n\n{trigger_text[:500]}"
                    ),
                },
            })

        # 4. Slack channel post (commented-out by default to avoid spam)
        slack_channel = os.environ.get("MANTHAN_SLACK_CHANNEL")
        if slack_channel:
            actions.append({
                "kind": "slack_brief",
                "description": f"Post brief to #{slack_channel}",
                "payload": {
                    "channel": slack_channel,
                    "text": f"{short_id} · {customer} · {decision_action} ({_dollars(amount_minor)})",
                },
            })

        return actions

    async def _enrich_drafted_actions(
        self,
        org_id: UUID,
        thread_id: UUID,
        case_id: UUID,
        decision_action: str | None,
        amount_minor: int | None,
        decision_rationale: str,
        drafted: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Overlay missing structured fields onto each drafted action.

        The agent often emits actions that have a description but a
        thin/empty payload (e.g. {"kind": "stripe_refund", "description":
        "Refund $560", "payload": {}}). Adapters reject these. This
        method:

          1. Pulls the case context (trigger_payload, customer_ref, short_id)
          2. Extracts canonical identifiers (charge_id, dispute_id,
             customer_email, hubspot_company_id)
          3. For each drafted action, fills in required fields the agent
             omitted - agent-supplied fields always win.

        Returns the modified list (same shape as input, payloads enriched).
        """
        import re as _re

        # ── Pull case context once ──────────────────────────────────────
        async with get_pool().acquire() as conn:
            opened = await conn.fetchrow(
                """
                SELECT data FROM events
                WHERE org_id=$1 AND thread_id=$2 AND type='case_opened'
                ORDER BY seq ASC LIMIT 1
                """,
                org_id, thread_id,
            )
            case_row = await conn.fetchrow(
                """
                SELECT short_id, customer_ref, trigger_payload, currency, case_type
                FROM cases WHERE id=$1
                """,
                case_id,
            )
        opened_data = opened["data"] if (opened and isinstance(opened["data"], dict)) else {}
        trigger_text = str(opened_data.get("trigger_text", ""))
        short_id = case_row["short_id"] if case_row else ""
        customer_ref = case_row["customer_ref"] if case_row else ""
        currency = (case_row["currency"] if case_row else "usd") or "usd"
        case_type = (case_row["case_type"] if case_row else "") or ""
        trigger_payload = (
            case_row["trigger_payload"]
            if (case_row and isinstance(case_row["trigger_payload"], dict))
            else {}
        )

        # ── Resolve canonical identifiers ───────────────────────────────
        # charge id: trigger_payload top-level, then event_object, then
        # duplicate_charge_id (Maya), then ch_* regex on trigger text.
        event_object = (
            trigger_payload.get("event_object")
            if isinstance(trigger_payload.get("event_object"), dict)
            else {}
        )
        charge_id = (
            trigger_payload.get("charge")
            or trigger_payload.get("duplicate_charge_id")
            or event_object.get("charge")
            or opened_data.get("charge")
            or opened_data.get("duplicate_charge_id")
        )
        if not charge_id:
            m = _re.search(r"Duplicate charge:\s*(ch_[A-Za-z0-9]+)", trigger_text)
            if m:
                charge_id = m.group(1)
            else:
                m = _re.search(r"(ch_[A-Za-z0-9]+)", trigger_text)
                charge_id = m.group(1) if m else None

        # dispute id: trigger_payload top-level, then event_object.id, then
        # du_* regex.
        dispute_id = (
            trigger_payload.get("dispute")
            or event_object.get("id")
            or opened_data.get("dispute")
        )
        if not dispute_id or not str(dispute_id).startswith("du_"):
            m = _re.search(r"(du_[A-Za-z0-9]+)", trigger_text)
            if m:
                dispute_id = m.group(1)

        # customer email: trigger_payload, then event_object, then
        # customer_ref if it looks like an email, then fallback env.
        customer_email = (
            trigger_payload.get("customer_email")
            or event_object.get("customer_email")
            or opened_data.get("customer_email")
            or trigger_payload.get("from_addr")
            or opened_data.get("from_addr")
        )
        if not customer_email and customer_ref and _re.match(
            r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(customer_ref)
        ):
            customer_email = str(customer_ref)
        if not customer_email:
            customer_email = os.environ.get(
                "MANTHAN_FALLBACK_CUSTOMER_EMAIL", "ops@manthan.quest"
            )

        # HubSpot company id: trigger_payload, then event_object metadata.
        # No name→id lookup adapter wired yet; if missing we drop the
        # hubspot_note action rather than fail at execute time.
        hubspot_company_id = (
            trigger_payload.get("hubspot_company_id")
            or event_object.get("hubspot_company_id")
            or opened_data.get("hubspot_company_id")
        )

        # Slack channel (env-configured default for billing-ops postings).
        slack_channel = os.environ.get(
            "MANTHAN_SLACK_CHANNEL",
            os.environ.get("SLACK_DEFAULT_CHANNEL", "#billing-ops"),
        )

        # From + reply-to email defaults.
        resend_from = (
            os.environ.get("MANTHAN_EMAIL_FROM")
            or os.environ.get("RESEND_FROM_ADDRESS")
            or "manthan@miny-labs.com"
        )

        # Decision summary used by email/hubspot/slack bodies when the
        # agent's payload is empty.
        amount_str = _dollars(amount_minor)
        decision_label = (decision_action or "update").replace("_", " ")
        brief_html = (
            f"<p><strong>{short_id} - {decision_label} ({amount_str})</strong></p>"
            f"<p>{(decision_rationale or '').strip() or 'See case findings.'}</p>"
        )
        brief_text = (
            f"{short_id} - {decision_label} ({amount_str}). "
            f"{(decision_rationale or '').strip() or 'See case findings.'}"
        )
        # Customer-facing email - properly templated per decision_action.
        # We DELIBERATELY do not pipe `decision_rationale` straight into
        # the email body: that field is the agent's operator-facing
        # narrative ("Per Notion policy [2][3]: credit = degraded_days /
        # cycle_days × tier_amount…") and reads like a support engineer
        # talking to themselves, not a customer-facing apology + receipt.
        customer_name = _customer_display_name(customer_ref)
        # Treat the case as a duplicate-charge refund when the
        # trigger-time signal (case_type, trigger_text) says so. The
        # template uses this to swap "we approved your dispute" wording
        # for "we caught the duplicate charge" wording - the dispute
        # framing is wrong for inbound-email refund requests that never
        # went through Stripe Disputes.
        is_duplicate_charge = (
            "duplicate" in case_type.lower()
            or "duplicate" in trigger_text.lower()
        )
        email_subject_default, email_html_default, email_text_default = _build_customer_email(
            decision_action=decision_action,
            amount_str=amount_str,
            short_id=short_id,
            dispute_id=dispute_id,
            customer_name=customer_name,
            is_duplicate_charge=is_duplicate_charge,
        )

        # ── Per-action enrichment ──────────────────────────────────────
        enriched: list[dict[str, Any]] = []
        for da in drafted:
            if not isinstance(da, dict):
                continue
            kind = da.get("kind")
            # Tolerate the agent leaving payload as None / missing entirely.
            payload = dict(da.get("payload") or {})
            description = da.get("description") or ""
            reversibility = da.get("reversibility") or "reversible"

            if kind == "stripe_refund":
                # Stripe adapter requires charge (or payment_intent) + amount_minor.
                # Agent's `charge_id` alias also accepted.
                if "charge" not in payload and "payment_intent" not in payload:
                    agent_charge = payload.pop("charge_id", None) or charge_id
                    if agent_charge:
                        payload["charge"] = agent_charge
                if "amount_minor" not in payload and amount_minor is not None:
                    payload["amount_minor"] = amount_minor
                if "currency" not in payload:
                    payload["currency"] = currency
                if "reason" not in payload:
                    payload["reason"] = "requested_by_customer"
                metadata = dict(payload.get("metadata") or {})
                metadata.setdefault("manthan_case_short_id", short_id)
                metadata.setdefault("case_id", str(case_id))
                payload["metadata"] = metadata

            elif kind == "stripe_dispute_response":
                if "dispute" not in payload:
                    # Accept agent's `dispute_id` alias too.
                    agent_dispute = payload.pop("dispute_id", None) or dispute_id
                    if agent_dispute:
                        payload["dispute"] = agent_dispute
                if "submit" not in payload:
                    # Safe demo default - draft, don't auto-submit.
                    payload["submit"] = False
                if "evidence" not in payload:
                    payload["evidence"] = {
                        "uncategorized_text": (
                            (decision_rationale or "").strip()
                            or f"Manthan investigation brief for case {short_id}."
                        ),
                    }

            elif kind == "customer_email":
                # Per-case demo override: if the trigger plumbed an
                # operator email (`demo_email_to`) the email delivers
                # there directly - no env-level rewrite, no [demo →]
                # subject prefix, no "to" hijack downstream. This is the
                # Aperture-from-the-empty-state path: the operator wants
                # to see the email land in their own inbox.
                demo_email_to = trigger_payload.get("demo_email_to") if isinstance(
                    trigger_payload, dict
                ) else None
                if demo_email_to:
                    payload["to"] = demo_email_to
                    payload["bypass_demo_override"] = True
                elif not payload.get("to"):
                    payload["to"] = customer_email
                if not payload.get("from"):
                    payload["from"] = resend_from
                # Customer-facing emails ALWAYS use the templated body.
                # The agent tends to dump its operator-facing decision
                # rationale here ("...per policy [Finding 3,5,6] [Cites:
                # 0-6]") which is unreadable for a real customer. The
                # templater produces a branded, plain-English version
                # that's safe to send. We deliberately overwrite the
                # agent's subject too so case-id leakage and internal
                # framing don't sneak in.
                payload["subject"] = email_subject_default
                # Resend's raw path reads `body_html` (with `html` as a
                # fallback we've added in the adapter). Set BOTH so the
                # branded HTML actually ships - without `body_html` the
                # adapter sends a text-only email and the customer sees
                # an unstyled plain-text wall.
                payload["body_html"] = email_html_default
                payload["html"] = email_html_default
                payload["body_text"] = email_text_default
                payload.pop("template", None)

            elif kind == "hubspot_note":
                if not payload.get("company_id"):
                    if hubspot_company_id:
                        payload["company_id"] = str(hubspot_company_id)
                    # else: leave blank - adapter will fail and surface the
                    # missing-lookup gap rather than silently mis-routing.
                if not payload.get("body") and not payload.get("body_html"):
                    payload["body_html"] = brief_html
                    payload["body"] = brief_text

            elif kind == "slack_brief":
                if not payload.get("channel"):
                    payload["channel"] = slack_channel
                if not payload.get("text") and not payload.get("blocks"):
                    payload["text"] = brief_text

            enriched.append({
                "kind": kind,
                "description": description,
                "payload": payload,
                "reversibility": reversibility,
            })

        return enriched

    async def _build_chat_history(
        self,
        org_id: UUID,
        thread_id: UUID,
        latest_user_message: str,
    ) -> list[dict[str, Any]]:
        """Translate the case's event log into a chat history for follow-up."""
        async with get_pool().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT type, actor, data FROM events
                WHERE org_id=$1 AND thread_id=$2 AND type IN (
                    'case_opened', 'finding_recorded', 'brief_drafted',
                    'agent_reply', 'human_followup', 'action_executed'
                )
                ORDER BY seq ASC
                """,
                org_id, thread_id,
            )

        system = (
            "You are Manthan, a billing-ops investigator. You already drafted "
            "a case brief earlier in this thread. The operator is now asking a "
            "follow-up question or pushing back. Answer directly and "
            "specifically using the findings and decision below - cite finding "
            "numbers when relevant. Keep replies 2-6 sentences. If the user "
            "asks you to amend the drafted actions, describe the exact change "
            "in plain English - don't pretend to have actually edited the action."
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]

        trigger_text = ""
        findings_text: list[str] = []
        brief_text = ""

        for r in rows:
            data = r["data"] if isinstance(r["data"], dict) else {}
            if r["type"] == "case_opened":
                trigger_text = str(data.get("trigger_text") or data.get("text") or "")
            elif r["type"] == "finding_recorded":
                findings_text.append(str(data.get("text", "")))
            elif r["type"] == "brief_drafted":
                brief_text = json.dumps(
                    {
                        "decision": data.get("decision"),
                        "tldr": data.get("tldr"),
                        "drafted_actions": [
                            {"kind": a.get("kind"), "description": a.get("description")}
                            for a in (data.get("drafted_actions") or [])
                            if isinstance(a, dict)
                        ],
                    },
                    default=str,
                )
            elif r["type"] == "agent_reply":
                messages.append({"role": "assistant", "content": str(data.get("text", ""))})
            elif r["type"] == "human_followup":
                messages.append({"role": "user", "content": str(data.get("message", ""))})

        # Bake the case context into the initial system turn.
        context = f"=== CASE TRIGGER ===\n{trigger_text}\n\n"
        if findings_text:
            context += "=== FINDINGS ===\n" + "\n".join(
                f"[{i + 1}] {t}" for i, t in enumerate(findings_text)
            ) + "\n\n"
        if brief_text:
            context += f"=== DRAFTED BRIEF ===\n{brief_text}\n"
        if context:
            messages.insert(1, {"role": "user", "content": context})

        # The actual current follow-up question (last event):
        if not messages or messages[-1].get("content") != latest_user_message:
            messages.append({"role": "user", "content": latest_user_message})
        return messages

    # ───────── helpers ─────────

    async def _mirror_event(
        self,
        org_id: UUID,
        thread_id: UUID,
        case_id: UUID,
        agent_evt: Any,
        finding_seq_ref: list[int],
    ) -> None:
        """Translate an agent Event to a PG events row + side-effect projections."""
        data = _serialize(agent_evt.data) if hasattr(agent_evt, "data") else {}
        await self._append_event(
            org_id=org_id, thread_id=thread_id,
            type_=agent_evt.kind, actor=agent_evt.actor, data=data,
        )

        # Side-effect: notify Slack if this case was opened from a Slack
        # mention/DM. The notify call needs to see the actions table
        # already populated for brief_drafted (the brief card lists
        # the suggested actions), so we DEFER it until the projection
        # block below has run. The case_closed branch also defers to
        # keep the dispatch path consistent, but its notifier has a
        # status='resolved' guard so the agent's premature case_closed
        # (emitted when the investigation phase ends, before the actor
        # has fired anything) does not double-post.
        _notify_slack_after = agent_evt.kind in ("brief_drafted", "case_closed")

        # Project findings into the findings table so the UI doesn't have
        # to scan events on every read.
        if agent_evt.kind == "finding_recorded" and isinstance(data, dict):
            text = data.get("text") or data.get("finding") or ""
            conf = data.get("confidence")
            # Prefer the resolved citation dicts the agent loop now emits
            # (each with {source, table, ref, field, idx}). Fall back to the
            # legacy `citations` field for events emitted before the loop
            # was taught to resolve indices - older events stored raw int
            # indices which never had enough info to render.
            resolved = data.get("citations_resolved") or []
            if not (isinstance(resolved, list) and resolved):
                resolved = data.get("citations") or []
            if isinstance(resolved, list):
                norm_cites = [
                    {
                        "source": c.get("source", "manthan"),
                        "table": c.get("table", ""),
                        "ref": c.get("ref", ""),
                        "field": c.get("field"),
                    }
                    for c in resolved
                    if isinstance(c, dict)
                ]
            else:
                norm_cites = []

            async with get_pool().acquire() as conn:
                # Get next seq
                next_seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM findings WHERE case_id = $1",
                    case_id,
                )
                await conn.execute(
                    """
                    INSERT INTO findings (org_id, case_id, seq, text, confidence, citations)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    org_id, case_id, next_seq, text,
                    float(conf) if isinstance(conf, (int, float)) else None,
                    norm_cites,
                )

        # When the agent drafts the final brief, capture the decision on the
        # case row so the UI shows the verdict, AND materialize the
        # drafted_actions into the actions table for the Action Executor
        # to drain on approval.
        if agent_evt.kind == "brief_drafted" and isinstance(data, dict):
            decision = (data.get("decision") or {}) if isinstance(data.get("decision"), dict) else {}
            action = decision.get("action") or data.get("decision_action")
            amount = decision.get("amount_minor") or data.get("decision_amount_minor")
            conf = decision.get("confidence") or data.get("decision_confidence")
            async with get_pool().acquire() as conn:
                await conn.execute(
                    """
                    UPDATE cases
                    SET decision_action = $1,
                        decision_amount_minor = $2,
                        decision_confidence = $3
                    WHERE id = $4
                    """,
                    action, amount, conf, case_id,
                )

            # Materialize drafted_actions → actions table (status='drafted',
            # blocked from execution until POST /api/cases/{id}/approve flips
            # them to 'approved'). If the agent's brief didn't include
            # drafted_actions, synthesize a sensible default from the decision.
            from manthan_api.workers.actor import make_idempotency_key

            drafted = data.get("drafted_actions") or []
            if not drafted:
                drafted = await self._synthesize_actions(
                    org_id=org_id, thread_id=thread_id, case_id=case_id,
                    decision_action=action, amount_minor=amount,
                )

            # Pre-flight enrichment: even when the agent DID draft actions,
            # it often omits required structured fields (charge_id on a
            # stripe_refund, to on a customer_email, etc.). Pull case
            # context once and overlay sensible defaults wherever the
            # agent left a field blank. Agent-supplied fields always win.
            if isinstance(drafted, list) and drafted:
                drafted = await self._enrich_drafted_actions(
                    org_id=org_id, thread_id=thread_id, case_id=case_id,
                    decision_action=action, amount_minor=amount,
                    decision_rationale=(
                        decision.get("rationale")
                        if isinstance(decision, dict) else None
                    ) or data.get("decision_rationale") or "",
                    drafted=drafted,
                )

            if isinstance(drafted, list):
                for i, da in enumerate(drafted):
                    if not isinstance(da, dict):
                        continue
                    kind = da.get("kind")
                    payload = dict(da.get("payload") or {})
                    if not kind:
                        continue
                    # Preserve the agent's narrative description + reversibility
                    # inside the payload so the approve-page card has
                    # something readable even when the agent left the
                    # action-specific payload fields empty.
                    if da.get("description") and "description" not in payload:
                        payload["description"] = da["description"]
                    if da.get("reversibility") and "reversibility" not in payload:
                        payload["reversibility"] = da["reversibility"]
                    idem = make_idempotency_key(case_id, kind, payload)
                    async with get_pool().acquire() as conn:
                        try:
                            await conn.execute(
                                """
                                INSERT INTO actions (
                                    org_id, case_id, seq, type, payload,
                                    idempotency_key, status
                                )
                                VALUES ($1, $2, $3, $4, $5, $6, 'drafted')
                                ON CONFLICT (org_id, idempotency_key) DO NOTHING
                                """,
                                org_id, case_id, i + 1, kind, payload, idem,
                            )
                        except Exception:  # noqa: BLE001
                            pass

        # Deferred Slack notify - runs AFTER all projection side-effects
        # (decision update + actions insertion). Was running before the
        # actions table got populated, so the brief card said "No
        # actions drafted - nothing for you to approve" even though
        # three actions were about to land.
        if _notify_slack_after:
            try:
                from manthan_api.services.slack_notifier import maybe_notify
                await maybe_notify(
                    org_id=org_id,
                    thread_id=thread_id,
                    case_id=case_id,
                    event_type=agent_evt.kind,
                    event_data=data if isinstance(data, dict) else None,
                )
            except Exception:  # noqa: BLE001
                pass

    async def _append_event(
        self,
        org_id: UUID,
        thread_id: UUID,
        type_: str,
        actor: str,
        data: dict[str, Any],
    ) -> None:
        """Append one event with an atomic seq increment. Retries on race."""
        async with get_pool().acquire() as conn:
            # Atomic INSERT with computed seq inside the same statement.
            # COALESCE(MAX, 0)+1 inside the SELECT is read-locked by the
            # CTE, but to be safe against true concurrency we retry on
            # unique-violation up to 5 times.
            for attempt in range(5):
                try:
                    await conn.execute(
                        """
                        WITH next AS (
                            SELECT COALESCE(MAX(seq), 0) + 1 AS s
                            FROM events
                            WHERE org_id = $1 AND thread_id = $2
                        )
                        INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                        SELECT $1, $2, s, $3, $4, $5 FROM next
                        """,
                        org_id, thread_id, type_, actor, data,
                    )
                    return
                except asyncpg.UniqueViolationError:
                    if attempt == 4:
                        raise
                    await asyncio.sleep(0.02 * (attempt + 1))

    async def _finalize_case(
        self,
        org_id: UUID,
        thread_id: UUID,
        case_id: UUID,
        agent_store: AgentEventStore,
        terminal_summary: dict[str, Any],
    ) -> None:
        """Update the cases projection with the final state.

        After the brief drops, we evaluate policy rules. If a rule matches
        with mode=auto, the case skips awaiting_approval - its drafted
        actions are auto-approved and the actor will execute them. The
        UI surfaces the policy match so it's clear who decided.
        """
        log = logger.getChild(str(thread_id)[:8] + ".finalize")
        # Find the brief
        brief_events = [e for e in agent_store.list_for_case(str(thread_id))
                         if e.kind == "brief_drafted"]
        final_status = "awaiting_approval"  # default until HITL exists
        if any(e.kind == "hitl_pause" for e in agent_store.list_for_case(str(thread_id))):
            final_status = "escalated"
        if not brief_events and terminal_summary.get("reason") == "error":
            final_status = "errored"

        # ── Policy evaluation ────────────────────────────────────────
        # Only if we drafted a brief AND aren't already errored/escalated.
        # Demo cases with an operator-routed email (`demo_email_to` in
        # trigger_payload) ALWAYS require manual approval - we want the
        # operator to see the brief and click Approve before any action
        # fires against their own inbox.
        policy_match = None
        force_human_approval = False
        if brief_events:
            async with get_pool().acquire() as conn:
                tp_row = await conn.fetchrow(
                    "SELECT trigger_payload FROM cases WHERE id=$1",
                    case_id,
                )
            tp = tp_row["trigger_payload"] if tp_row else None
            if isinstance(tp, dict) and tp.get("demo_email_to"):
                force_human_approval = True

        if final_status == "awaiting_approval" and brief_events:
            try:
                from manthan_api.services.policy import evaluate_for_case
                policy_match = await evaluate_for_case(org_id, case_id)
            except Exception as e:  # noqa: BLE001
                log.warning("policy evaluation failed: %s", e)

            if policy_match is not None:
                await self._append_event(
                    org_id, thread_id, "policy_matched", "system",
                    {
                        "rule_id": str(policy_match.rule_id),
                        "rule_name": policy_match.rule_name,
                        "mode": policy_match.mode,
                        "decision": policy_match.decision,
                        "auto_approval_skipped": force_human_approval,
                    },
                )
                if policy_match.mode == "auto" and not force_human_approval:
                    # Auto-approve drafted actions. Status flips to 'acting'
                    # so the actor worker picks them up via NOTIFY.
                    final_status = "acting"
                    async with get_pool().acquire() as conn:
                        await conn.execute(
                            """
                            UPDATE actions
                            SET status = 'approved',
                                approved_at = now(),
                                payload = payload || jsonb_build_object(
                                    'approved_via', 'policy',
                                    'policy_rule_id', $2::text,
                                    'policy_rule_name', $3::text
                                )
                            WHERE case_id = $1 AND status = 'drafted'
                            """,
                            case_id, str(policy_match.rule_id), policy_match.rule_name,
                        )
                    await self._append_event(
                        org_id, thread_id, "human_approved", "system",
                        {
                            "via": "policy_auto",
                            "rule_name": policy_match.rule_name,
                            "rule_id": str(policy_match.rule_id),
                        },
                    )

        async with get_pool().acquire() as conn:
            await conn.execute(
                """
                UPDATE cases
                SET status = $1,
                    resolved_at = CASE WHEN $1 IN ('resolved','errored') THEN now() ELSE NULL END
                WHERE id = $2
                """,
                final_status, case_id,
            )


# ──────────────────────────────────────────────────────────────────────
# Entry point: `uv run python -m manthan_api.workers.main`
# ──────────────────────────────────────────────────────────────────────


def _dollars(amount_minor: int | None) -> str:
    if amount_minor is None:
        return "-"
    return f"${amount_minor / 100:,.2f}"


def _customer_display_name(customer_ref: Any) -> str:
    """Best-effort first-name-ish display for the email greeting.
    `customer_ref` can be an email (billing@aperture-analytics.co), a
    company name ("Aperture Analytics"), or None. We strip after @,
    drop common role prefixes (billing, ops, support), and title-case.
    """
    if not customer_ref:
        return "there"
    s = str(customer_ref).strip()
    if "@" in s:
        s = s.split("@", 1)[0]
    s = s.replace(".", " ").replace("_", " ").replace("-", " ")
    first = s.split()[0] if s.split() else s
    if first.lower() in {"billing", "ops", "support", "admin", "team", "info", "hello"}:
        return "there"
    return first[0].upper() + first[1:] if first else "there"


def _build_customer_email(
    *,
    decision_action: str | None,
    amount_str: str,
    short_id: str,
    dispute_id: str | None,
    customer_name: str,
    is_duplicate_charge: bool = False,
) -> tuple[str, str, str]:
    """Return (subject, html, text) for the customer-facing email.

    Designed for Resend - fully-styled responsive HTML email with a
    branded header bar, headline, a summary "card" for the resolution
    amount, and a clean signature + reference block. Inline styles
    only (Gmail strips <style> blocks). Max width 600px.

    Tone: plain English, second-person, no internal citation markers,
    no [Finding N] or [Cites: ...] tags, no engineering jargon, no
    policy formulas. The agent's operator-facing rationale never
    reaches this function - by the time we render, all that's left is
    the decision plus a small set of resolution-context flags.

    `is_duplicate_charge` swaps "approved your dispute" framing for
    "caught a duplicate charge" framing - the latter is correct for
    inbound-email refund requests that never went through Stripe
    Disputes (e.g. Maya scenario).
    """
    # ── Brand tokens ────────────────────────────────────────────────
    BG = "#f6f5f1"            # warm off-white outer
    SURFACE = "#ffffff"       # card surface
    INK = "#1a1a1a"
    INK_MUTED = "#5a5a5a"
    INK_FAINT = "#9a9a9a"
    RULE = "#e9e7e1"
    ACCENT = "#1a8f55"        # caldera emerald
    ACCENT_TINT = "#e8f5ec"

    safe_name = customer_name.strip() or "there"

    # ── Per-decision copy ──────────────────────────────────────────
    if decision_action == "refund":
        if is_duplicate_charge:
            subject = f"We refunded the duplicate {amount_str} charge"
            headline = "Refund processed"
            paragraphs = [
                f"We caught the duplicate charge on your account and have already "
                f"refunded <strong>{amount_str}</strong> back to your original card.",
                f"The cause was a retry bug on our payment system - we've fixed it, "
                f"and you won't see the duplicate again. The refund should land in "
                f"your account within 5–10 business days, depending on your bank.",
                f"If anything still looks off once the refund lands, just reply to "
                f"this email and we'll take another look.",
            ]
            summary_label = "Refund"
            summary_caption = "Back to your original card · 5–10 business days"
        else:
            subject = (
                f"Refund of {amount_str} approved on your dispute"
                if dispute_id
                else f"Refund of {amount_str} processed"
            )
            headline = "Refund approved"
            paragraphs = [
                f"We've finished reviewing your case and approved a refund of "
                f"<strong>{amount_str}</strong> back to your original payment method.",
                f"The funds should land within 5–10 business days, depending on "
                f"your bank.",
                f"If anything still looks off once the refund arrives, just reply "
                f"to this email - we'll take another look.",
            ]
            summary_label = "Refund"
            summary_caption = "Back to your original payment method"

    elif decision_action in ("partial_credit", "partial_refund"):
        subject = f"Partial credit of {amount_str} approved"
        headline = "Partial credit approved"
        paragraphs = [
            f"Thanks for raising this. After reviewing what happened during the "
            f"period in question, we've approved a partial credit of "
            f"<strong>{amount_str}</strong> on your account.",
            f"The credit will appear on your next invoice. If you'd prefer it "
            f"back on your original payment method instead, reply to this email "
            f"and we'll switch it over.",
        ]
        summary_label = "Credit applied"
        summary_caption = "Will appear on your next invoice"

    elif decision_action == "fight":
        subject = "Update on your dispute"
        headline = "Dispute response submitted"
        paragraphs = [
            f"We've finished reviewing the dispute on your account. Based on the "
            f"records we have, the charge was for service you actively used during "
            f"the period - so we've submitted evidence to your bank that the "
            f"charge was valid.",
            f"Your bank will make the final decision, usually within a couple of "
            f"weeks. We'll let you know as soon as we hear back. If there's "
            f"context we may have missed, just reply to this email.",
        ]
        summary_label = "Disputed charge"
        summary_caption = "Awaiting your bank's decision"

    elif decision_action == "escalate":
        subject = "We're taking another look at your case"
        headline = "We're on it"
        paragraphs = [
            f"Thanks for flagging this. A member of our team is taking another "
            f"look and will follow up shortly with the next steps.",
        ]
        summary_label = None
        summary_caption = None

    else:
        subject = "Update on your case"
        headline = "Quick update"
        paragraphs = [
            f"We have an update on your recent case. A team member will follow "
            f"up shortly with the details.",
        ]
        summary_label = None
        summary_caption = None

    # ── HTML body - table-based for Outlook/Gmail compat ───────────
    summary_card_html = ""
    if summary_label and amount_str:
        summary_card_html = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'width="100%" style="margin:28px 0 8px 0;border-collapse:separate;'
            f'border:1px solid {RULE};border-radius:8px;background:{ACCENT_TINT};">'
            f'<tr><td style="padding:20px 24px;">'
            f'<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,'
            f'Helvetica,Arial,sans-serif;font-size:11px;letter-spacing:0.16em;'
            f'text-transform:uppercase;color:{ACCENT};font-weight:600;">'
            f'{summary_label}</div>'
            f'<div style="font-family:Georgia,Cambria,Times,serif;font-size:32px;'
            f'line-height:1.1;color:{INK};margin-top:6px;font-weight:400;">'
            f'{amount_str}</div>'
        )
        if summary_caption:
            summary_card_html += (
                f'<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,'
                f'Helvetica,Arial,sans-serif;font-size:13px;color:{INK_MUTED};'
                f'margin-top:8px;">{summary_caption}</div>'
            )
        summary_card_html += "</td></tr></table>"

    paragraphs_html = "".join(
        f'<p style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,'
        f'Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;'
        f'color:{INK};margin:0 0 16px 0;">{p}</p>'
        for p in paragraphs
    )

    html = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{subject}</title></head>'
        f'<body style="margin:0;padding:0;background:{BG};">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%" style="background:{BG};">'
        f'<tr><td align="center" style="padding:32px 16px;">'

        # Outer 600px container
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="600" style="width:600px;max-width:100%;background:{SURFACE};'
        f'border:1px solid {RULE};border-radius:12px;overflow:hidden;">'

        # Header bar
        f'<tr><td style="padding:20px 32px;border-bottom:1px solid {RULE};">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">'
        f'<tr>'
        f'<td align="left" style="font-family:-apple-system,BlinkMacSystemFont,'
        f'Segoe UI,Helvetica,Arial,sans-serif;font-size:12px;letter-spacing:0.18em;'
        f'text-transform:uppercase;color:{INK};font-weight:600;">'
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
        f'background:{ACCENT};margin-right:8px;vertical-align:middle;"></span>'
        f'Caldera Support</td>'
        f'<td align="right" style="font-family:Menlo,Consolas,Monaco,monospace;'
        f'font-size:11px;letter-spacing:0.12em;color:{INK_FAINT};">'
        f'{short_id}</td>'
        f'</tr></table></td></tr>'

        # Body
        f'<tr><td style="padding:36px 32px 32px 32px;">'
        f'<h1 style="font-family:Georgia,Cambria,Times,serif;font-size:28px;'
        f'line-height:1.2;color:{INK};margin:0 0 24px 0;font-weight:400;'
        f'letter-spacing:-0.01em;">{headline}</h1>'
        f'<p style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,'
        f'Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;color:{INK};'
        f'margin:0 0 16px 0;">Hi {safe_name},</p>'
        f'{paragraphs_html}'
        f'{summary_card_html}'

        # Signature
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%" style="margin-top:32px;border-top:1px solid {RULE};">'
        f'<tr><td style="padding-top:20px;font-family:-apple-system,'
        f'BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;font-size:14px;'
        f'color:{INK_MUTED};">- Caldera Support</td></tr></table>'
        f'</td></tr>'

        # Footer
        f'<tr><td style="padding:18px 32px;background:{BG};border-top:1px solid {RULE};'
        f'font-family:Menlo,Consolas,Monaco,monospace;font-size:10.5px;letter-spacing:0.10em;'
        f'color:{INK_FAINT};text-transform:uppercase;">'
        f'Case ref · {short_id}'
        + (f' · dispute {dispute_id}' if dispute_id else "")
        + f'</td></tr>'

        f'</table>'
        f'</td></tr></table></body></html>'
    )

    # Plain-text fallback - strip HTML tags + bullet the summary card.
    text_paragraphs = "\n\n".join(
        _strip_html_tags(p) for p in paragraphs
    )
    summary_text = ""
    if summary_label and amount_str:
        summary_text = f"\n\n{summary_label}: {amount_str}"
        if summary_caption:
            summary_text += f"\n({summary_caption})"
    text = (
        f"{headline}\n"
        f"{'=' * len(headline)}\n\n"
        f"Hi {safe_name},\n\n"
        f"{text_paragraphs}"
        f"{summary_text}\n\n"
        f"- Caldera Support\n"
        f"Case ref: {short_id}"
        + (f" · dispute {dispute_id}" if dispute_id else "")
        + "\n"
    )

    return subject, html, text


def _strip_html_tags(s: str) -> str:
    """Tiny HTML→text for plaintext fallback. Keeps inline <strong>
    text by replacing the tags with empty strings; collapses whitespace."""
    import re as _re
    out = _re.sub(r"<[^>]+>", "", s)
    out = _re.sub(r"\s+", " ", out).strip()
    return out


async def main() -> None:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    from manthan_api.db import close_pool, init_pool

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await init_pool()
    worker = InvestigateWorker()
    try:
        await worker.run()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
