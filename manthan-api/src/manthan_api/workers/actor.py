"""worker.actor - drains the approved-action queue and fires real writes.

Per-org serial worker (one action at a time per org, so writes can't race).
Pattern: SELECT FOR UPDATE SKIP LOCKED → call adapter → record external_ref
→ verify (re-read the source) → mark succeeded/failed/drift.

Idempotency: each action carries a hash-derived key; adapters that support
upstream idempotency pass it through (Stripe). Adapters that don't have
upstream idempotency are guarded by checking the actions row before call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any
from uuid import UUID

from manthan_api.adapters import (
    AdapterError,
    ExecutionResult,
    hubspot as hubspot_adapter,
    linear as linear_adapter,
    notion as notion_adapter,
    resend as resend_adapter,
    slack as slack_adapter,
    stripe as stripe_adapter,
)
from manthan_api.db import get_pool

logger = logging.getLogger("worker.actor")


# action.kind → (adapter callable, verifier callable | None)
ADAPTERS: dict[str, tuple[Any, Any]] = {
    "stripe_refund":            (stripe_adapter.refund, stripe_adapter.verify_refund),
    "stripe_dispute_response":  (stripe_adapter.dispute_response, None),
    "customer_email":           (resend_adapter.send, None),
    "linear_ticket":            (linear_adapter.create_issue, None),
    "hubspot_note":             (hubspot_adapter.create_note, None),
    "slack_brief":              (slack_adapter.post, None),
    "notion_decision_log":      (notion_adapter.append_decision_log, None),
}


def make_idempotency_key(case_id: UUID, kind: str, payload: dict[str, Any]) -> str:
    """Deterministic key per case + action kind + payload."""
    blob = json.dumps([str(case_id), kind, payload], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


class ActorWorker:
    """Drains approved actions from PG and fires them."""

    def __init__(self, poll_interval: float = 1.0) -> None:
        self.poll_interval = poll_interval
        self._stop = asyncio.Event()

    async def run(self) -> None:
        logger.info("worker.actor starting")
        # Startup sweep: any case that's been firing but all actions
        # are terminal needs to be finalized. This catches the cases
        # that were mid-batch when the previous actor process died, and
        # also retro-resolves cases that finished before the finalize
        # logic existed.
        try:
            swept = await self._finalize_sweep()
            if swept:
                logger.info("startup sweep finalized %d case(s)", swept)
        except Exception as e:  # noqa: BLE001
            logger.warning("startup finalize sweep failed: %s", e)

        while not self._stop.is_set():
            try:
                claimed = await self._drain_once()
            except Exception as e:  # noqa: BLE001
                logger.exception("actor loop error: %s", e)
                claimed = 0
            if claimed == 0:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
        logger.info("worker.actor stopped")

    def stop(self) -> None:
        self._stop.set()

    async def _drain_once(self) -> int:
        """Claim one approved action and fire it. Returns 1 if fired, else 0."""
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id, org_id, case_id, type AS kind, payload, idempotency_key, external_ref
                    FROM actions
                    WHERE status = 'approved'
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                )
                if row is None:
                    return 0
                # Move to executing inside the same tx so no other worker grabs it.
                await conn.execute(
                    "UPDATE actions SET status = 'executing' WHERE id = $1",
                    row["id"],
                )

        # Outside the tx (the write may take seconds).
        await self._fire(row)
        return 1

    async def _fire(self, row: Any) -> None:
        action_id = row["id"]
        kind = row["kind"]
        payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
        idem = row["idempotency_key"]
        case_id = row["case_id"]
        org_id = row["org_id"]
        log = logger.getChild(str(action_id)[:8])

        # Wrap the whole adapter run in try/finally so the finalize
        # check ALWAYS runs - including on adapter rejection, unknown
        # kind, or unexpected exception. Previously the failure-return
        # paths each `return`-ed before reaching `_maybe_finalize_case`,
        # so a case whose LAST action failed would sit in
        # status='acting' forever and the UI cinematic would never
        # transition to the closed brief.
        try:
            adapter, verifier = ADAPTERS.get(kind, (None, None))
            if adapter is None:
                log.error("unknown action kind: %s", kind)
                await self._mark_failed(action_id, f"unknown action kind: {kind}")
                await self._append_event(
                    org_id, case_id, "action_failed", "system",
                    {
                        "action_id": str(action_id),
                        "kind": kind,
                        "error": f"unknown action kind: {kind}",
                    },
                )
                return

            # Run sync adapters in a thread pool.
            try:
                result: ExecutionResult = await asyncio.to_thread(adapter, payload, idem)
            except AdapterError as e:
                log.warning("adapter rejected: %s", e)
                await self._mark_failed(action_id, str(e))
                await self._append_event(
                    org_id, case_id, "action_failed", "system",
                    {"action_id": str(action_id), "kind": kind, "error": str(e)},
                )
                return
            except Exception as e:  # noqa: BLE001
                log.exception("unexpected adapter error: %s", e)
                await self._mark_failed(action_id, f"unexpected: {type(e).__name__}: {e}")
                await self._append_event(
                    org_id, case_id, "action_failed", "system",
                    {"action_id": str(action_id), "kind": kind, "error": str(e)},
                )
                return

            # Mark succeeded + record ref.
            await self._mark_succeeded(action_id, result.external_ref)
            await self._append_event(
                org_id, case_id, "action_executed", "system",
                {
                    "action_id": str(action_id),
                    "kind": kind,
                    "external_ref": result.external_ref,
                    "summary": result.summary,
                    "raw": result.raw,
                },
            )
            log.info("action %s fired: %s", kind, result.summary)

            # Mirror to Slack thread if this case was opened from Slack - close
            # the loop visually for Segment 4's "see actions firing in source".
            try:
                from manthan_api.services.slack_notifier import maybe_notify
                await maybe_notify(
                    org_id=org_id,
                    thread_id=await self._thread_id_for_case(case_id),
                    case_id=case_id,
                    event_type="agent_reply",
                    event_data={
                        "text": (
                            f":zap: *{kind}* executed - {result.summary}"
                            + (f"\n<{_source_ref_url(kind, result.external_ref)}|View in source ↗>"
                               if _source_ref_url(kind, result.external_ref) else "")
                        ),
                    },
                )
            except Exception as e:  # noqa: BLE001
                log.warning("slack notify on action_executed failed: %s", e)

            # Optional verify pass.
            if verifier:
                try:
                    ok = await asyncio.to_thread(verifier, result.external_ref)
                    await self._append_event(
                        org_id, case_id, "action_verified" if ok else "drift_detected", "system",
                        {"action_id": str(action_id), "external_ref": result.external_ref, "verified": ok},
                    )
                    if ok:
                        async with get_pool().acquire() as conn:
                            await conn.execute(
                                "UPDATE actions SET verified_at = now() WHERE id = $1",
                                action_id,
                            )
                except Exception as e:  # noqa: BLE001
                    log.warning("verify failed: %s", e)
        finally:
            # Was this the LAST drafted/approved/executing action on the
            # case? If so, finalize: flip cases.status → resolved + emit a
            # case_closed event so downstream (UI cinematic, Slack
            # actions-performed card) picks it up. CRITICAL: runs even on
            # failure return paths above - otherwise a case whose last
            # action fails stays in 'acting' forever.
            try:
                await self._maybe_finalize_case(org_id, case_id, log)
            except Exception as e:  # noqa: BLE001
                log.warning("finalize check failed: %s", e)

    # ───────── helpers ─────────

    async def _mark_failed(self, action_id: UUID, reason: str) -> None:
        async with get_pool().acquire() as conn:
            await conn.execute(
                "UPDATE actions SET status = 'failed', error_message = $1 WHERE id = $2",
                reason, action_id,
            )

    async def _mark_succeeded(self, action_id: UUID, external_ref: str) -> None:
        async with get_pool().acquire() as conn:
            await conn.execute(
                """
                UPDATE actions
                SET status = 'succeeded', external_ref = $1
                WHERE id = $2
                """,
                external_ref, action_id,
            )

    async def _thread_id_for_case(self, case_id: UUID) -> UUID | None:
        """Look up thread_id for a case - used by Slack mirror."""
        async with get_pool().acquire() as conn:
            return await conn.fetchval(
                "SELECT thread_id FROM cases WHERE id = $1",
                case_id,
            )

    async def _finalize_sweep(self) -> int:
        """Look for any case stuck in 'acting' / 'awaiting_approval' where
        every action is terminal, and finalize each one. Called once on
        actor startup. Returns the count finalized."""
        async with get_pool().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.id AS case_id, c.org_id AS org_id
                FROM cases c
                WHERE c.status IN ('acting','awaiting_approval')
                  AND EXISTS (SELECT 1 FROM actions WHERE case_id=c.id)
                  AND NOT EXISTS (
                      SELECT 1 FROM actions
                      WHERE case_id=c.id
                        AND status NOT IN ('succeeded','failed','drift','denied')
                  )
                """,
            )
        finalized = 0
        for r in rows:
            try:
                await self._maybe_finalize_case(
                    r["org_id"], r["case_id"],
                    logger.getChild("sweep"),
                )
                finalized += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("sweep finalize %s failed: %s", r["case_id"], e)
        return finalized

    async def _maybe_finalize_case(
        self,
        org_id: UUID,
        case_id: UUID,
        log: logging.Logger,
    ) -> None:
        """If every action on this case is in a terminal status (succeeded
        / failed / drift / denied), flip the case to resolved + emit a
        case_closed event.

        Idempotent: skips if the case is already in a terminal status,
        and uses a transaction so two concurrent actors firing the last
        two actions can't double-emit case_closed.
        """
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT
                        c.status                AS case_status,
                        c.thread_id             AS thread_id,
                        c.short_id              AS short_id,
                        COUNT(a.id)             AS total,
                        COUNT(a.id) FILTER (
                            WHERE a.status IN ('succeeded','failed','drift','denied')
                        )                       AS terminal,
                        COUNT(a.id) FILTER (
                            WHERE a.status = 'succeeded'
                        )                       AS ok,
                        COUNT(a.id) FILTER (
                            WHERE a.status IN ('failed','drift')
                        )                       AS bad
                    FROM cases c
                    LEFT JOIN actions a ON a.case_id = c.id
                    WHERE c.id = $1
                    GROUP BY c.id, c.status, c.thread_id, c.short_id
                    """,
                    case_id,
                )
                if row is None:
                    return
                # Already terminal? Nothing to do.
                if row["case_status"] in ("resolved", "errored", "escalated"):
                    return
                # Still has pending actions? Wait for the next call.
                if row["total"] == 0 or row["terminal"] < row["total"]:
                    return

                # Flip + emit case_closed atomically.
                await conn.execute(
                    "UPDATE cases SET status='resolved', resolved_at=now() WHERE id=$1",
                    case_id,
                )
                thread_id = row["thread_id"]
                short_id = row["short_id"]
                ok = int(row["ok"])
                bad = int(row["bad"])
                reason = "all actions fired" if bad == 0 else (
                    f"{ok} fired · {bad} failed"
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
                            SELECT $1, $2, s, 'case_closed', 'system', $3 FROM next
                            """,
                            org_id, thread_id,
                            json.dumps({
                                "reason": reason,
                                "actions_total": int(row["total"]),
                                "actions_succeeded": ok,
                                "actions_failed": bad,
                                "via": "actor_finalize",
                            }),
                        )
                        break
                    except Exception:
                        if attempt == 4:
                            raise
                        await asyncio.sleep(0.02 * (attempt + 1))

        log.info("case %s finalized: %s", case_id, reason)

        # Fire the Slack actions-performed card. Outside the tx, since
        # it talks to slack.com and we don't want a slow network hop to
        # hold a DB transaction.
        try:
            from manthan_api.services.slack_notifier import (
                maybe_notify_case_closed_card,
            )
            await maybe_notify_case_closed_card(org_id=org_id, case_id=case_id)
        except Exception as e:  # noqa: BLE001
            log.warning("slack close-card post failed: %s", e)

    async def _append_event(
        self,
        org_id: UUID,
        case_id: UUID,
        type_: str,
        actor: str,
        data: dict[str, Any],
    ) -> None:
        # Find thread_id for this case
        async with get_pool().acquire() as conn:
            thread_id = await conn.fetchval(
                "SELECT thread_id FROM cases WHERE id = $1",
                case_id,
            )
            if thread_id is None:
                return
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
                except Exception:
                    if attempt == 4:
                        raise
                    await asyncio.sleep(0.02 * (attempt + 1))


def _source_ref_url(kind: str, external_ref: str | None) -> str | None:
    """Build a deep-link URL for the executed action's external ref so the
    Slack thread reply gets a 'View in source ↗' link."""
    if not external_ref:
        return None
    if kind == "stripe_refund":
        return f"https://dashboard.stripe.com/test/refunds/{external_ref}"
    if kind == "stripe_dispute_response":
        return f"https://dashboard.stripe.com/test/disputes/{external_ref}"
    if kind == "customer_email":
        return None  # Resend email IDs aren't user-clickable
    if kind == "notion_decision_log":
        clean = external_ref.replace("-", "")
        return f"https://www.notion.so/{clean}"
    if kind == "slack_brief":
        # external_ref is the message ts; no clean permalink without channel
        return None
    if kind == "linear_issue":
        # Linear issue ID like "ENG-123"
        return f"https://linear.app/issue/{external_ref}"
    if kind == "hubspot_note":
        portal = os.environ.get("HUBSPOT_PORTAL_ID")
        if portal:
            return f"https://app.hubspot.com/contacts/{portal}/note/{external_ref}"
    return None


async def main() -> None:
    import logging
    from dotenv import load_dotenv
    from pathlib import Path

    # Load env explicitly so source adapters (stripe.py, resend.py, ...) which
    # call os.environ.get directly can see STRIPE_API_KEY etc.
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    from manthan_api.db import close_pool, init_pool

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await init_pool()
    worker = ActorWorker()
    try:
        await worker.run()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
