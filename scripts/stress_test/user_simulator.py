"""Auto-responder thread that simulates Layer 3 user interaction.

Runs alongside a tier script: polls ``/ask_user/pending`` and
``/plans?session_id=`` for questions/plans waiting on the given
``session_id``, and answers/approves them with canned persona-flavored
responses. This is how the test drives blocking human-in-the-loop
endpoints without a real human.

Usage:

    from scripts.stress_test.user_simulator import UserSimulator

    sim = UserSimulator(
        session_id="tier2_taxi",
        ask_user_answers={"last week": "trip count by day for Jan 22-28"},
        plan_decision="approve",
    )
    sim.start()
    # ... run the tier scenario ...
    sim.stop()
"""

from __future__ import annotations

import threading
import time

import httpx

BASE_URL = "http://127.0.0.1:8000"


class UserSimulator:
    """Background responder for ask_user and plan approvals."""

    def __init__(
        self,
        *,
        session_id: str,
        ask_user_answers: dict[str, str] | None = None,
        plan_decision: str = "approve",
        plan_feedback: str | None = None,
        poll_interval: float = 0.4,
        base_url: str = BASE_URL,
    ) -> None:
        self.session_id = session_id
        self.ask_user_answers = ask_user_answers or {}
        self.plan_decision = plan_decision
        self.plan_feedback = plan_feedback
        self._poll_interval = poll_interval
        self._base_url = base_url
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.answered_questions: list[str] = []
        self.decided_plans: list[str] = []

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"user-sim-{self.session_id}", daemon=True
        )
        self._thread.start()

    def stop(self, *, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def __enter__(self) -> UserSimulator:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _pick_answer(self, prompt: str, options: list[str]) -> str:
        """Pick an answer for a pending ask_user question.

        Matching strategy: find the first configured key whose lowercase
        form is a substring of the (lowercase) prompt. If nothing
        matches and options exist, pick the first option. Otherwise
        return a safe-default free-text answer.
        """
        prompt_lc = prompt.lower()
        for key, answer in self.ask_user_answers.items():
            if key.lower() in prompt_lc:
                return answer
        if options:
            return options[0]
        return "default answer (user-simulator)"

    def _run(self) -> None:
        with httpx.Client(base_url=self._base_url, timeout=15.0) as client:
            while not self._stop.is_set():
                try:
                    self._poll_once(client)
                except Exception:
                    # Never kill the simulator over a transient error
                    pass
                self._stop.wait(self._poll_interval)

    def _poll_once(self, client: httpx.Client) -> None:
        # Answer pending ask_user questions for this session
        r = client.get("/ask_user/pending", params={"session_id": self.session_id})
        if r.status_code == 200:
            for q in r.json():
                qid = q["id"]
                if qid in self.answered_questions:
                    continue
                answer = self._pick_answer(q["prompt"], q.get("options") or [])
                client.post(
                    f"/ask_user/{qid}/answer",
                    json={"answer": answer},
                )
                self.answered_questions.append(qid)

        # Approve/reject/amend any pending plans for this session
        r = client.get("/plans", params={"session_id": self.session_id})
        if r.status_code == 200:
            for plan in r.json():
                if plan.get("status") != "pending":
                    continue
                pid = plan["id"]
                if pid in self.decided_plans:
                    continue
                if self.plan_decision == "approve":
                    client.post(
                        f"/plans/{pid}/approve",
                        json={"actor": "user-simulator"},
                    )
                elif self.plan_decision == "reject":
                    client.post(
                        f"/plans/{pid}/reject",
                        json={
                            "actor": "user-simulator",
                            "feedback": self.plan_feedback or "rejected by sim",
                        },
                    )
                self.decided_plans.append(pid)
                # Yield a hair to let the wait endpoint unblock cleanly.
                time.sleep(0.05)
