"""URL-based ingestion via DuckDB's httpfs extension.

One loader, three protocols:

    * ``https://host/path/file.csv`` — any public (or pre-signed) URL
    * ``s3://bucket/path/*.csv`` — AWS S3 (and S3-compatible: R2, MinIO)
    * ``gs://bucket/path/file.parquet`` — Google Cloud Storage
    * ``az://container/path/*.json`` — Azure Blob (requires `azure` ext)

DuckDB's httpfs + secret system handles auth; we just shape the
``CREATE SECRET`` call from whatever credentials the user provided.
For public URLs no secret is needed.

Returns a :class:`LoadResult` identical to the file loaders so the
rest of the pipeline (profiling, DCD build, materialization) is
unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb

from src.ingestion.base import LoadResult, quote_identifier, validate_identifier

_CSV_EXT = re.compile(r"\.(csv|tsv)(\.gz)?$", re.IGNORECASE)
_PARQUET_EXT = re.compile(r"\.parquet$", re.IGNORECASE)
_JSON_EXT = re.compile(r"\.(json|jsonl|ndjson)(\.gz)?$", re.IGNORECASE)


@dataclass(slots=True)
class CloudLoadRequest:
    """One cloud-ingest request from the API layer.

    The URL's scheme determines which extension we load; the optional
    ``secret`` block is passed to DuckDB's ``CREATE SECRET`` for auth.
    """

    url: str
    destination_table: str
    secret: dict[str, Any] | None = None


def _detect_format(url: str) -> str:
    if _PARQUET_EXT.search(url):
        return "parquet"
    if _JSON_EXT.search(url):
        return "json"
    # Default to CSV (most common and most permissive).
    return "csv"


def _read_function(fmt: str, url: str) -> str:
    quoted = url.replace("'", "''")
    if fmt == "parquet":
        return f"read_parquet('{quoted}')"
    if fmt == "json":
        return f"read_json_auto('{quoted}')"
    return f"read_csv('{quoted}', AUTO_DETECT=TRUE, UNION_BY_NAME=TRUE)"


def _ensure_extensions(connection: duckdb.DuckDBPyConnection, url: str) -> None:
    """Install + load the extensions needed for this URL's protocol.

    ``httpfs`` covers http/https + s3/r2/gs. ``azure`` is separate for
    the ``az://`` scheme. Extensions are cached by DuckDB after the
    first install, so re-calling ``INSTALL`` is cheap.
    """
    connection.execute("INSTALL httpfs; LOAD httpfs;")
    if url.startswith(("az://", "azure://")):
        # The azure extension isn't bundled in all DuckDB builds — if
        # install fails, fall through and let the read surface a clearer
        # error than "unknown extension". Using contextlib.suppress would
        # work too but loses the inline explanation here.
        try:  # noqa: SIM105
            connection.execute("INSTALL azure; LOAD azure;")
        except duckdb.Error:
            pass


def _install_secret(
    connection: duckdb.DuckDBPyConnection,
    url: str,
    secret: dict[str, Any] | None,
) -> None:
    """Create a DuckDB secret for the URL's scheme if credentials exist."""
    if not secret:
        return
    scheme = url.split("://", 1)[0].lower() if "://" in url else ""
    # Sanitized secret name — one per scheme per process.
    secret_name = f"manthan_{scheme or 'http'}"
    # Map scheme → DuckDB TYPE + KEY/VALUE pairs.
    if scheme == "s3":
        keys = {
            "KEY_ID": secret.get("access_key_id"),
            "SECRET": secret.get("secret_access_key"),
            "REGION": secret.get("region"),
            "ENDPOINT": secret.get("endpoint"),
            "SESSION_TOKEN": secret.get("session_token"),
        }
        secret_type = "S3"
    elif scheme == "gs" or scheme == "gcs":
        keys = {
            "KEY_ID": secret.get("hmac_key_id"),
            "SECRET": secret.get("hmac_secret"),
        }
        secret_type = "GCS"
    elif scheme in {"az", "azure"}:
        keys = {
            "CONNECTION_STRING": secret.get("connection_string"),
            "ACCOUNT_NAME": secret.get("account_name"),
        }
        secret_type = "AZURE"
    else:
        return  # plain https — no secret needed
    pairs = ", ".join(
        f"{k} '{str(v).replace(chr(39), chr(39) + chr(39))}'"
        for k, v in keys.items()
        if v is not None
    )
    if not pairs:
        return
    connection.execute(
        f"CREATE OR REPLACE SECRET {secret_name} (TYPE {secret_type}, {pairs})"
    )


def load_from_url(
    connection: duckdb.DuckDBPyConnection,
    request: CloudLoadRequest,
) -> LoadResult:
    """Materialize a URL's contents as a raw_ DuckDB table."""
    validate_identifier(request.destination_table)
    _ensure_extensions(connection, request.url)
    _install_secret(connection, request.url, request.secret)

    fmt = _detect_format(request.url)
    read_fn = _read_function(fmt, request.url)

    connection.execute(
        f"CREATE OR REPLACE TABLE {quote_identifier(request.destination_table)} "
        f"AS SELECT * FROM {read_fn}"
    )

    count_row = connection.execute(
        f"SELECT COUNT(*), COUNT(*) OVER () "
        f"FROM {quote_identifier(request.destination_table)} "
        f"LIMIT 1"
    ).fetchone()
    row_count = int(count_row[0]) if count_row else 0
    col_count = len(
        connection.execute(
            f"DESCRIBE {quote_identifier(request.destination_table)}"
        ).fetchall()
    )

    # Derive a display filename from the URL's last path segment so
    # downstream humanization has something reasonable to work with.
    display_name = request.url.rsplit("/", 1)[-1] or request.url

    # LoadResult.source_type is a ``Literal["csv"|"excel"|"json"|"parquet"|...]``,
    # so we return the bare format. The URL origin is captured separately
    # via ``original_filename`` and the ingestion log — no need to smuggle
    # provenance into the type field.
    return LoadResult(
        table_name=request.destination_table,
        source_type=fmt,
        original_filename=display_name,
        ingested_at=datetime.now(UTC),
        row_count=row_count,
        column_count=col_count,
        raw_size_bytes=None,
    )
