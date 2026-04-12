"""Memory store HTTP router.

Thin shell over :class:`src.core.memory.MemoryStore` giving the agent
persistent, cross-session notes scoped to datasets, users, or the
whole deployment.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.memory import MemoryEntry, MemoryError
from src.core.state import AppState, get_state

router = APIRouter(prefix="/memory", tags=["memory"])

StateDep = Annotated[AppState, Depends(get_state)]


class MemoryPutRequest(BaseModel):
    """Body of ``POST /memory``."""

    scope_type: str = Field(..., description="dataset | user | global | session")
    scope_id: str
    key: str
    value: Any
    category: str = Field(
        default="note",
        description="preference | definition | caveat | fact | note",
    )
    description: str | None = None


class MemoryEntryResponse(BaseModel):
    """Serialized form of a :class:`MemoryEntry`."""

    scope_type: str
    scope_id: str
    key: str
    value: Any
    category: str
    description: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_entry(cls, entry: MemoryEntry) -> MemoryEntryResponse:
        return cls(
            scope_type=entry.scope_type,
            scope_id=entry.scope_id,
            key=entry.key,
            value=entry.value,
            category=entry.category,
            description=entry.description,
            created_at=entry.created_at.isoformat(),
            updated_at=entry.updated_at.isoformat(),
        )


@router.post("", response_model=MemoryEntryResponse)
def put_memory(request: MemoryPutRequest, state: StateDep) -> MemoryEntryResponse:
    try:
        entry = state.memory.put(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            key=request.key,
            value=request.value,
            category=request.category,
            description=request.description,
        )
    except MemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MemoryEntryResponse.from_entry(entry)


@router.get("/{scope_type}/{scope_id}/{key}", response_model=MemoryEntryResponse)
def get_memory(
    scope_type: str, scope_id: str, key: str, state: StateDep
) -> MemoryEntryResponse:
    try:
        entry = state.memory.get(scope_type=scope_type, scope_id=scope_id, key=key)
    except MemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return MemoryEntryResponse.from_entry(entry)


@router.delete("/{scope_type}/{scope_id}/{key}")
def delete_memory(
    scope_type: str, scope_id: str, key: str, state: StateDep
) -> dict[str, bool]:
    try:
        removed = state.memory.delete(scope_type=scope_type, scope_id=scope_id, key=key)
    except MemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"removed": removed}


@router.get("/{scope_type}/{scope_id}", response_model=list[MemoryEntryResponse])
def list_scope(
    scope_type: str,
    scope_id: str,
    state: StateDep,
    category: str | None = None,
) -> list[MemoryEntryResponse]:
    try:
        entries = state.memory.list_scope(
            scope_type=scope_type, scope_id=scope_id, category=category
        )
    except MemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [MemoryEntryResponse.from_entry(entry) for entry in entries]


@router.get("/search/", response_model=list[MemoryEntryResponse])
def search_memory(
    state: StateDep,
    query: str,
    scope_type: str | None = None,
) -> list[MemoryEntryResponse]:
    try:
        entries = state.memory.search(query=query, scope_type=scope_type)
    except MemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [MemoryEntryResponse.from_entry(entry) for entry in entries]
