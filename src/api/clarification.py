"""Clarification API endpoints (SPEC §10.3).

Stores pending clarification questions for a dataset keyed by
``dataset_id`` and accepts user answers that are merged back onto the
profiling result.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.core.state import AppState, get_state
from src.profiling.clarification import (
    ClarificationAnswer,
    ClarificationQuestion,
)

router = APIRouter(prefix="/clarification", tags=["clarification"])

StateDep = Annotated[AppState, Depends(get_state)]


class ClarificationAnswerRequest(BaseModel):
    answers: list[ClarificationAnswer]


@router.get("/{dataset_id}", response_model=list[ClarificationQuestion])
def pending_questions(dataset_id: str, state: StateDep) -> list[ClarificationQuestion]:
    if dataset_id not in state.dcds:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    return state.clarifications.get(dataset_id, [])


@router.post("/{dataset_id}")
def submit_answers(
    dataset_id: str,
    request: ClarificationAnswerRequest,
    state: StateDep,
) -> dict[str, object]:
    if dataset_id not in state.dcds:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    state.clarification_answers[dataset_id] = list(request.answers)
    state.clarifications.pop(dataset_id, None)
    return {"dataset_id": dataset_id, "answers_received": len(request.answers)}
