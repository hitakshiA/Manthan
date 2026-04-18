"""Ask_user HTTP router.

The agent calls ``POST /ask_user`` then ``POST /ask_user/{id}/wait``
to block on an answer. A user-facing UI polls
``GET /ask_user/pending?session_id=`` for pending questions and
answers them via ``POST /ask_user/{id}/answer``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.ask_user import AskUserQuestion
from src.core.state import AppState, get_state

router = APIRouter(prefix="/ask_user", tags=["ask_user"])

StateDep = Annotated[AppState, Depends(get_state)]

_DEFAULT_WAIT_SECONDS = 300.0
_MAX_WAIT_SECONDS = 900.0


class AskRequest(BaseModel):
    session_id: str
    prompt: str
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True
    context: str | None = None
    # Propose-first structure — analyst's working interpretation and
    # why-this-matters, rendered prominently by the UI
    proposed_interpretation: str | None = None
    why_this_matters: str | None = None
    ambiguity_type: str | None = None


class AnswerRequest(BaseModel):
    answer: str


class QuestionResponse(BaseModel):
    id: str
    session_id: str
    prompt: str
    options: list[str]
    allow_free_text: bool
    context: str | None
    status: str
    answer: str | None
    answered_at: str | None
    created_at: str
    timed_out: bool = False
    proposed_interpretation: str | None = None
    why_this_matters: str | None = None
    ambiguity_type: str | None = None

    @classmethod
    def from_question(
        cls, question: AskUserQuestion, *, timed_out: bool = False
    ) -> QuestionResponse:
        return cls(
            id=question.id,
            session_id=question.session_id,
            prompt=question.prompt,
            options=list(question.options),
            allow_free_text=question.allow_free_text,
            context=question.context,
            status=question.status,
            answer=question.answer,
            answered_at=question.answered_at.isoformat()
            if question.answered_at
            else None,
            created_at=question.created_at.isoformat(),
            timed_out=timed_out,
            proposed_interpretation=question.proposed_interpretation,
            why_this_matters=question.why_this_matters,
            ambiguity_type=question.ambiguity_type,
        )


@router.post("", response_model=QuestionResponse)
def ask(request: AskRequest, state: StateDep) -> QuestionResponse:
    question = state.ask_user.ask(
        session_id=request.session_id,
        prompt=request.prompt,
        options=request.options,
        allow_free_text=request.allow_free_text,
        context=request.context,
        proposed_interpretation=request.proposed_interpretation,
        why_this_matters=request.why_this_matters,
        ambiguity_type=request.ambiguity_type,
    )
    return QuestionResponse.from_question(question)


@router.post("/{question_id}/wait", response_model=QuestionResponse)
def wait_for_answer(
    question_id: str,
    state: StateDep,
    timeout_seconds: float = _DEFAULT_WAIT_SECONDS,
) -> QuestionResponse:
    timeout = min(max(1.0, timeout_seconds), _MAX_WAIT_SECONDS)
    try:
        question = state.ask_user.wait(question_id, timeout_seconds=timeout)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    timed_out = question.status == "pending"
    return QuestionResponse.from_question(question, timed_out=timed_out)


@router.post("/{question_id}/answer", response_model=QuestionResponse)
def answer(
    question_id: str, request: AnswerRequest, state: StateDep
) -> QuestionResponse:
    try:
        question = state.ask_user.answer(question_id, request.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return QuestionResponse.from_question(question)


@router.get("/pending", response_model=list[QuestionResponse])
def list_pending(session_id: str, state: StateDep) -> list[QuestionResponse]:
    return [
        QuestionResponse.from_question(q)
        for q in state.ask_user.list_pending(session_id)
    ]


@router.get("/{question_id}", response_model=QuestionResponse)
def get_question(question_id: str, state: StateDep) -> QuestionResponse:
    question = state.ask_user.get(question_id)
    if question is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown question_id: {question_id}"
        )
    return QuestionResponse.from_question(question)
