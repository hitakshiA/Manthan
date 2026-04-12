"""Unit tests for :mod:`src.core.ask_user`."""

from __future__ import annotations

import threading
import time

from src.core.ask_user import AskUserRegistry


def test_ask_creates_pending_question() -> None:
    registry = AskUserRegistry()
    q = registry.ask(
        session_id="s1",
        prompt="Calendar month or trailing 30 days?",
        options=["calendar", "trailing_30"],
    )
    assert q.status == "pending"
    assert registry.list_pending("s1") == [q]


def test_wait_returns_immediately_after_answer() -> None:
    registry = AskUserRegistry()
    q = registry.ask(session_id="s1", prompt="?")

    def _answer() -> None:
        time.sleep(0.05)
        registry.answer(q.id, "trailing_30")

    thread = threading.Thread(target=_answer)
    thread.start()

    result = registry.wait(q.id, timeout_seconds=2.0)
    thread.join()

    assert result.status == "answered"
    assert result.answer == "trailing_30"
    assert result.answered_at is not None


def test_wait_times_out() -> None:
    registry = AskUserRegistry()
    q = registry.ask(session_id="s1", prompt="?")

    start = time.monotonic()
    result = registry.wait(q.id, timeout_seconds=0.1)
    elapsed = time.monotonic() - start

    assert result.status == "pending"
    assert elapsed >= 0.1


def test_cancel_wakes_waiters() -> None:
    registry = AskUserRegistry()
    q = registry.ask(session_id="s1", prompt="?")

    def _cancel() -> None:
        time.sleep(0.05)
        registry.cancel(q.id)

    thread = threading.Thread(target=_cancel)
    thread.start()
    result = registry.wait(q.id, timeout_seconds=2.0)
    thread.join()

    assert result.status == "cancelled"


def test_list_pending_excludes_answered() -> None:
    registry = AskUserRegistry()
    q1 = registry.ask(session_id="s", prompt="a")
    q2 = registry.ask(session_id="s", prompt="b")
    registry.answer(q1.id, "yes")
    pending = registry.list_pending("s")
    assert [q.id for q in pending] == [q2.id]


def test_drop_session_wakes_waiters() -> None:
    registry = AskUserRegistry()
    q = registry.ask(session_id="s", prompt="?")

    def _drop() -> None:
        time.sleep(0.05)
        registry.drop_session("s")

    thread = threading.Thread(target=_drop)
    thread.start()
    # wait for event set — the question is gone, so re-reading would KeyError
    event = q._event
    assert event.wait(timeout=2.0)
    thread.join()
