"""Saved-connection CRUD endpoints.

The credential vault holds one record per connection; this router
exposes the minimal endpoints the frontend needs to list, create,
update, and delete them. Plaintext secrets never cross the API
boundary on reads — a ``ConnectionInfo`` only carries metadata.

Concrete source types:

    * ``postgres`` / ``mysql`` / ``sqlite`` — ``secret = {connection_string}``
    * ``snowflake`` — ``secret = {account, user, password, warehouse, database, role}``
    * ``bigquery`` — ``secret = {project_id, service_account_json}``
    * ``s3`` / ``gcs`` / ``azure`` — matches :func:`cloud_loader._install_secret`
    * ``gsheet`` — ``secret = {refresh_token, access_token, client_id, client_secret}``
    * ``saas-<provider>`` — free-form dict of API key / OAuth tokens

The agent never talks to this router directly — connections are a
user-facing concept, managed through the Settings page.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.credentials import VaultError
from src.core.state import AppState, get_state


router = APIRouter(prefix="/connections", tags=["connections"])

StateDep = Annotated[AppState, Depends(get_state)]


class ConnectionInfo(BaseModel):
    """Metadata-only view of a saved connection."""

    connection_id: str
    label: str
    source_type: str
    created_at: str
    updated_at: str


class CreateConnectionRequest(BaseModel):
    label: str = Field(..., description="Exec-facing name, e.g. 'Production Postgres'.")
    source_type: str = Field(..., description="postgres|mysql|snowflake|bigquery|s3|gcs|azure|gsheet|...")
    secret: dict[str, Any] = Field(..., description="Credentials payload; shape depends on source_type.")


class UpdateConnectionRequest(BaseModel):
    label: str | None = None
    source_type: str | None = None
    secret: dict[str, Any] | None = None


@router.get("", response_model=list[ConnectionInfo])
def list_connections(state: StateDep) -> list[ConnectionInfo]:
    if state.credentials is None:
        return []
    return [
        ConnectionInfo(**row)
        for row in state.credentials.list()
    ]


@router.post("", response_model=ConnectionInfo)
def create_connection(req: CreateConnectionRequest, state: StateDep) -> ConnectionInfo:
    if state.credentials is None:
        raise HTTPException(status_code=503, detail="Credential vault not initialized.")
    cid = f"conn_{uuid4().hex[:10]}"
    state.credentials.store(
        connection_id=cid,
        label=req.label,
        source_type=req.source_type,
        secret=req.secret,
    )
    record = state.credentials.get(cid)
    return ConnectionInfo(
        connection_id=record.connection_id,
        label=record.label,
        source_type=record.source_type,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


@router.patch("/{connection_id}", response_model=ConnectionInfo)
def update_connection(
    connection_id: str,
    req: UpdateConnectionRequest,
    state: StateDep,
) -> ConnectionInfo:
    if state.credentials is None:
        raise HTTPException(status_code=503, detail="Credential vault not initialized.")
    try:
        existing = state.credentials.get(connection_id)
    except VaultError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    new_label = req.label or existing.label
    new_type = req.source_type or existing.source_type
    new_secret = req.secret if req.secret is not None else existing.secret
    state.credentials.store(
        connection_id=connection_id,
        label=new_label,
        source_type=new_type,
        secret=new_secret,
    )
    record = state.credentials.get(connection_id)
    return ConnectionInfo(
        connection_id=record.connection_id,
        label=record.label,
        source_type=record.source_type,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


@router.delete("/{connection_id}")
def delete_connection(connection_id: str, state: StateDep) -> dict[str, Any]:
    if state.credentials is None:
        raise HTTPException(status_code=503, detail="Credential vault not initialized.")
    if not state.credentials.delete(connection_id):
        raise HTTPException(status_code=404, detail="Connection not found.")
    return {"connection_id": connection_id, "status": "deleted"}
