"""Runtime ask_user — blocking human-in-the-loop clarification.

When the agent hits ambiguity mid-task (e.g. ``"last month"`` could
mean calendar month or trailing 30 days), it calls
:meth:`AskUserRegistry.ask`, which posts a question to a pending queue
and **blocks** on a :class:`threading.Event` until the user answers or
a timeout fires. The server's long-poll endpoint exposes this wait to
HTTP clients.

The pattern:

1. Agent: ``POST /ask_user`` with question + options → returns question_id
2. Agent: ``POST /ask_user/{id}/wait?timeout=300`` (blocks)
3. UI: ``GET /ask_user/pending?session_id=X`` to see what's pending
4. User: ``POST /ask_user/{id}/answer`` → server wakes up the waiting agent
5. Agent: receives the answer, continues its tool loop

Timeout without an answer is not an error — the agent just gets a
``timed_out=True`` result and can decide what to do (retry, give up,
pick a default). This keeps the wait bounded so subagents can't
deadlock the whole system.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

QuestionStatus = Literal["pending", "answered", "expired", "cancelled"]


@dataclass
class AskUserQuestion:
    """One pending / answered clarification question."""

    id: str
    session_id: str
    prompt: str
    options: list[str]
    allow_free_text: bool
    context: str | None
    status: QuestionStatus = "pending"
    answer: str | None = None
    answered_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    _event: threading.Event = field(default_factory=threading.Event)


class AskUserRegistry:
    """Thread-safe registry + blocking wait for human-in-the-loop questions."""

    def __init__(self) -> None:
        self._questions: dict[str, AskUserQuestion] = {}
        self._lock = threading.Lock()

    def ask(
        self,
        *,
        session_id: str,
        prompt: str,
        options: list[str] | None = None,
        allow_free_text: bool = True,
        context: str | None = None,
    ) -> AskUserQuestion:
        question = AskUserQuestion(
            id=f"q_{uuid4().hex[:10]}",
            session_id=session_id,
            prompt=prompt,
            options=list(options or []),
            allow_free_text=allow_free_text,
            context=context,
        )
        with self._lock:
            self._questions[question.id] = question
        return question

    def wait(self, question_id: str, timeout_seconds: float) -> AskUserQuestion:
        """Block until the question is answered or the timeout elapses.

        Returns the (possibly still pending) question object. Callers
        should check ``status``: ``answered`` means ``answer`` is
        populated, ``pending`` means the timeout fired with no answer.
        """
        with self._lock:
            question = self._questions.get(question_id)
            if question is None:
                raise KeyError(f"Unknown question_id: {question_id}")

        event = question._event
        event.wait(timeout=timeout_seconds)

        with self._lock:
            # Re-read under the lock in case the answer landed right
            # after our wake-up.
            return self._questions[question_id]

    def answer(self, question_id: str, answer: str) -> AskUserQuestion:
        with self._lock:
            question = self._questions.get(question_id)
            if question is None:
                raise KeyError(f"Unknown question_id: {question_id}")
            question.answer = answer
            question.answered_at = datetime.now(UTC)
            question.status = "answered"
            question._event.set()
            return question

    def cancel(self, question_id: str) -> AskUserQuestion | None:
        with self._lock:
            question = self._questions.get(question_id)
            if question is None:
                return None
            question.status = "cancelled"
            question._event.set()
            return question

    def get(self, question_id: str) -> AskUserQuestion | None:
        with self._lock:
            return self._questions.get(question_id)

    def list_pending(self, session_id: str) -> list[AskUserQuestion]:
        with self._lock:
            return sorted(
                (
                    q
                    for q in self._questions.values()
                    if q.session_id == session_id and q.status == "pending"
                ),
                key=lambda q: q.created_at,
            )

    def drop_session(self, session_id: str) -> int:
        with self._lock:
            to_remove = [
                qid for qid, q in self._questions.items() if q.session_id == session_id
            ]
            for qid in to_remove:
                question = self._questions[qid]
                question._event.set()  # wake any blocked waiters
                del self._questions[qid]
            return len(to_remove)
