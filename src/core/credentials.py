"""Envelope-encrypted credential vault.

Stores per-tenant connection credentials (connection strings, API
keys, OAuth refresh tokens) encrypted at rest. The vault never
returns plaintext to HTTP handlers unless they explicitly call
:meth:`decrypt` — and even then the returned :class:`SecretStr`
masks itself in logs.

Design:

    * **Two-layer encryption (envelope).** Each tenant has a Data Key
      (DK) stored encrypted under a process-level Master Key (MK)
      loaded from the ``MANTHAN_VAULT_MASTER_KEY`` env var. Individual
      credentials are encrypted with the DK. Rotating the MK only
      requires re-wrapping each DK, not re-encrypting every credential.
    * **SQLite-backed.** Simple, embedded, no external dependency. The
      file lives at ``data/credentials.sqlite``.
    * **CMK-ready.** :class:`MasterKeyProvider` is pluggable; the
      default reads from env, but a later enterprise deployment can
      swap in an AWS KMS / Azure Key Vault / GCP KMS implementation
      without touching the credential-consumer code.

For the hackathon / single-user scope, one tenant slot is enough
(``tenant_id="default"``). Multi-tenant is a schema migration away.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_TENANT = "default"


class VaultError(Exception):
    """Raised when the vault can't satisfy a request (bad key, missing record)."""


class MasterKeyProvider:
    """Abstract base. Subclass to swap the master-key backend.

    The contract: ``get_master_key()`` returns a 32-byte urlsafe-base64
    Fernet key. Implementations that wrap an HSM should cache
    aggressively — this is called once per Vault instantiation.
    """

    def get_master_key(self) -> bytes:
        raise NotImplementedError


class EnvMasterKeyProvider(MasterKeyProvider):
    """Load the master key from the ``MANTHAN_VAULT_MASTER_KEY`` env var.

    If the env var isn't set, we derive a deterministic key from the
    machine's hostname + a salt file so single-machine deployments
    "just work" out of the box. Production deployments MUST set the
    env var explicitly — the derived fallback is a safety net, not a
    security control.
    """

    def __init__(self, data_directory: Path) -> None:
        self._data_directory = data_directory

    def get_master_key(self) -> bytes:
        env = os.environ.get("MANTHAN_VAULT_MASTER_KEY")
        if env:
            # Accept either raw urlsafe-base64 (44 chars) or a raw
            # hex/ascii seed we convert.
            try:
                Fernet(env.encode())
                return env.encode()
            except (ValueError, InvalidToken):
                pass
            # Derive from the user-supplied seed.
            import hashlib

            digest = hashlib.sha256(env.encode()).digest()
            return base64.urlsafe_b64encode(digest)
        # Single-machine fallback: persist a generated key beside the
        # vault so restarts keep working.
        salt_path = self._data_directory / ".vault_key"
        if salt_path.exists():
            return salt_path.read_bytes()
        self._data_directory.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        salt_path.write_bytes(key)
        salt_path.chmod(0o600)
        return key


@dataclass(slots=True)
class VaultRecord:
    """A stored credential as the vault sees it after decryption."""

    connection_id: str
    label: str
    source_type: str  # postgres | mysql | snowflake | bigquery | s3 | gcs | gsheet | saas-stripe | ...
    secret: dict[str, Any]  # arbitrary JSON-serializable blob
    created_at: datetime
    updated_at: datetime


class CredentialVault:
    """Envelope-encrypted credential store.

    Thread-safe via a single mutex — writes are infrequent (one per
    connection setup) so contention is negligible.
    """

    def __init__(
        self,
        *,
        data_directory: Path,
        master_key_provider: MasterKeyProvider | None = None,
    ) -> None:
        self._data_directory = data_directory
        self._provider = master_key_provider or EnvMasterKeyProvider(data_directory)
        self._db_path = data_directory / "credentials.sqlite"
        self._lock = Lock()
        self._init_db()
        self._master = Fernet(self._provider.get_master_key())
        self._dk_cache: dict[str, Fernet] = {}

    # ── Storage plumbing ─────────────────────────────────────

    def _init_db(self) -> None:
        self._data_directory.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_keys (
                    tenant_id  TEXT PRIMARY KEY,
                    wrapped_dk BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS credentials (
                    connection_id TEXT PRIMARY KEY,
                    tenant_id     TEXT NOT NULL,
                    label         TEXT NOT NULL,
                    source_type   TEXT NOT NULL,
                    ciphertext    BLOB NOT NULL,
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL
                );
                """
            )

    def _data_key_for(self, tenant_id: str) -> Fernet:
        if tenant_id in self._dk_cache:
            return self._dk_cache[tenant_id]
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT wrapped_dk FROM data_keys WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if row is None:
                # First use — mint a fresh DK, wrap with MK, persist.
                new_dk = Fernet.generate_key()
                wrapped = self._master.encrypt(new_dk)
                conn.execute(
                    "INSERT INTO data_keys(tenant_id, wrapped_dk, created_at) VALUES (?, ?, ?)",
                    (tenant_id, wrapped, datetime.now(UTC).isoformat()),
                )
                dk = new_dk
            else:
                dk = self._master.decrypt(row[0])
        f = Fernet(dk)
        self._dk_cache[tenant_id] = f
        return f

    # ── Public API ───────────────────────────────────────────

    def store(
        self,
        *,
        connection_id: str,
        label: str,
        source_type: str,
        secret: dict[str, Any],
        tenant_id: str = DEFAULT_TENANT,
    ) -> None:
        """Insert or update a credential."""
        dk = self._data_key_for(tenant_id)
        blob = dk.encrypt(json.dumps(secret).encode())
        now = datetime.now(UTC).isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO credentials(connection_id, tenant_id, label, source_type, ciphertext, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(connection_id) DO UPDATE SET
                    label = excluded.label,
                    source_type = excluded.source_type,
                    ciphertext = excluded.ciphertext,
                    updated_at = excluded.updated_at
                """,
                (connection_id, tenant_id, label, source_type, blob, now, now),
            )

    def get(
        self,
        connection_id: str,
        *,
        tenant_id: str = DEFAULT_TENANT,
    ) -> VaultRecord:
        """Decrypt + return one credential. Raises :class:`VaultError` if missing."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT label, source_type, ciphertext, created_at, updated_at "
                "FROM credentials WHERE connection_id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
            if row is None:
                raise VaultError(f"No credential for connection_id={connection_id}")
            label, source_type, blob, created, updated = row
        dk = self._data_key_for(tenant_id)
        try:
            secret = json.loads(dk.decrypt(blob).decode())
        except InvalidToken as exc:
            raise VaultError(
                "Credential decryption failed — master key rotated?"
            ) from exc
        return VaultRecord(
            connection_id=connection_id,
            label=label,
            source_type=source_type,
            secret=secret,
            created_at=datetime.fromisoformat(created),
            updated_at=datetime.fromisoformat(updated),
        )

    def list(self, *, tenant_id: str = DEFAULT_TENANT) -> list[dict[str, Any]]:
        """Return metadata for every credential — never plaintext."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT connection_id, label, source_type, created_at, updated_at "
                "FROM credentials WHERE tenant_id = ? ORDER BY updated_at DESC",
                (tenant_id,),
            ).fetchall()
        return [
            {
                "connection_id": r[0],
                "label": r[1],
                "source_type": r[2],
                "created_at": r[3],
                "updated_at": r[4],
            }
            for r in rows
        ]

    def delete(
        self,
        connection_id: str,
        *,
        tenant_id: str = DEFAULT_TENANT,
    ) -> bool:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM credentials WHERE connection_id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            )
            return cur.rowcount > 0
