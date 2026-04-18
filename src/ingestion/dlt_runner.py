"""SaaS-connector long tail via the ``dlt`` library.

``dlt`` (Apache-2.0) provides 60+ verified connectors + a REST-API
scaffold (``dlt-init-openapi``) for generating new ones. We target
``duckdb`` as the destination so the output lands in the same
DuckDB file the rest of Manthan queries, slotting into the existing
Silver + Gold pipeline without a second storage layer.

The pattern:

    1. Caller names a source (``stripe``, ``hubspot``, ``github``, ...)
       and supplies credentials.
    2. :func:`run_dlt_pipeline` imports the matching ``dlt.sources.*``
       module, instantiates it with the creds, and runs a pipeline
       whose destination is the in-process DuckDB connection.
    3. The top-level resource becomes the raw_ table the normal
       pipeline profiles and materializes.

For Phase 6 we ship a minimal set of first-class sources:
``stripe``, ``github``, ``notion``, ``filesystem`` (MIT/Apache all).
More are one import line away; the scaffold is what matters.

Custom connectors can be generated via ``dlt-init-openapi``; this
module exposes a :func:`scaffold_from_openapi` thin wrapper the
frontend can call with a spec URL.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from src.ingestion.base import LoadResult, validate_identifier


@dataclass(slots=True)
class DltRunRequest:
    """One SaaS-ingest request from the API layer."""

    source: str  # "stripe" | "github" | "notion" | "filesystem" | ...
    resource: str | None  # top-level resource to pull (e.g. "charges" for Stripe)
    credentials: dict[str, Any]
    destination_table: str


def run_dlt_pipeline(
    connection: duckdb.DuckDBPyConnection,
    request: DltRunRequest,
) -> LoadResult:
    """Pull a SaaS source into a raw_ table via dlt's DuckDB destination.

    The dlt pipeline writes its own DuckDB file; we then materialize
    the result into the active Manthan connection as a single table
    so downstream profiling is identical to file ingest.

    Credentials are passed through as-is to the dlt source, which
    normalizes them per-source (Stripe: ``api_key``; GitHub:
    ``access_token``; etc.).
    """
    validate_identifier(request.destination_table)

    # dlt writes to a pipelines dir by default; point it somewhere
    # ephemeral so runs don't leak state across datasets.
    with tempfile.TemporaryDirectory(prefix="manthan_dlt_") as workdir:
        import dlt
        from dlt.destinations import duckdb as duckdb_dest

        # Output DuckDB lives under the temp dir; we read from it
        # once the pipeline finishes.
        out_db = Path(workdir) / "dlt.duckdb"
        pipeline = dlt.pipeline(
            pipeline_name=f"manthan_{request.source}",
            destination=duckdb_dest(str(out_db)),
            dataset_name="raw",
            pipelines_dir=workdir,
            dev_mode=True,
        )

        source_obj = _build_source(request)
        if request.resource:
            # Narrow to one resource if caller specified (some sources
            # expose dozens; without narrowing we'd pull everything).
            source_obj = source_obj.with_resources(request.resource)

        info = pipeline.run(source_obj)
        if info is None:
            raise RuntimeError("dlt pipeline returned no info object")

        # Copy the resulting table into the active Manthan connection.
        # dlt creates tables inside schemas; after ``dataset_name='raw'``
        # the resource's table lives at ``raw.<resource>``.
        with duckdb.connect(str(out_db), read_only=True) as dlt_con:
            schema_name = "raw"
            table_candidates = dlt_con.execute(
                f"SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = '{schema_name}' "
                f"AND table_name NOT LIKE '_dlt_%' "
                f"ORDER BY table_name"
            ).fetchall()
            if not table_candidates:
                raise RuntimeError(
                    f"dlt {request.source} pipeline produced no output tables"
                )
            source_table = table_candidates[0][0]
            arrow_tbl = dlt_con.execute(
                f'SELECT * FROM "{schema_name}"."{source_table}"'
            ).arrow()

        connection.register("__dlt_arrow", arrow_tbl)
        connection.execute(
            f'CREATE OR REPLACE TABLE "{request.destination_table}" AS '
            "SELECT * FROM __dlt_arrow"
        )
        connection.unregister("__dlt_arrow")

        row_count = int(
            connection.execute(
                f'SELECT COUNT(*) FROM "{request.destination_table}"'
            ).fetchone()[0]
        )
        col_count = len(
            connection.execute(f'DESCRIBE "{request.destination_table}"').fetchall()
        )

    return LoadResult(
        table_name=request.destination_table,
        source_type=f"saas-{request.source}",
        original_filename=f"{request.source}:{request.resource or '*'}",
        ingested_at=datetime.now(UTC),
        row_count=row_count,
        column_count=col_count,
        raw_size_bytes=None,
    )


def _build_source(request: DltRunRequest) -> Any:
    """Instantiate the right dlt source with credentials.

    This is a thin registry — each case maps to a dlt-native source
    module. Missing cases raise so the API can 400 cleanly rather
    than silently producing empty tables.
    """
    creds = request.credentials
    if request.source == "filesystem":
        from dlt.sources.filesystem import (  # type: ignore
            filesystem,
            read_csv,
            read_parquet,
        )

        bucket_url = creds.get("bucket_url")
        file_glob = creds.get("file_glob", "*.csv")
        if not bucket_url:
            raise ValueError("filesystem source requires credentials['bucket_url']")
        reader = read_parquet if file_glob.endswith("parquet") else read_csv
        return (
            filesystem(bucket_url=bucket_url, file_glob=file_glob) | reader()
        ).with_name(request.resource or "imported")
    if request.source == "github":
        from dlt.sources.github import github_reactions  # type: ignore

        owner = creds.get("owner")
        name = creds.get("repo")
        token = creds.get("access_token")
        if not (owner and name and token):
            raise ValueError(
                "github source requires credentials['owner', 'repo', 'access_token']"
            )
        return github_reactions(owner, name, access_token=token)
    if request.source == "stripe":
        # dlt doesn't ship a first-class Stripe source in the base
        # install — it's in dlt-hub/verified-sources. We raise with a
        # helpful message; Phase 6 extension can install the source.
        raise NotImplementedError(
            "Stripe requires `pip install 'dlt[duckdb] dlt-sources-stripe'` "
            "and a scaffolded pipeline; not yet included in this build."
        )
    if request.source == "notion":
        raise NotImplementedError(
            "Notion requires the verified-sources Notion source; "
            "installable via the dlt-init-openapi scaffolder."
        )
    raise ValueError(f"Unknown dlt source: {request.source}")


def list_available_sources() -> list[dict[str, Any]]:
    """Enumerate the sources this build can run, for the API/UI to list."""
    return [
        {
            "slug": "filesystem",
            "label": "Cloud filesystem (S3/GCS/Azure)",
            "ready": True,
            "credential_schema": {
                "bucket_url": {
                    "type": "string",
                    "required": True,
                    "description": "s3://bucket/prefix or gs://…",
                },
                "file_glob": {
                    "type": "string",
                    "required": False,
                    "description": "*.csv / *.parquet / *.json",
                },
            },
        },
        {
            "slug": "github",
            "label": "GitHub (issues, reactions, pulls)",
            "ready": True,
            "credential_schema": {
                "owner": {"type": "string", "required": True},
                "repo": {"type": "string", "required": True},
                "access_token": {"type": "string", "required": True, "secret": True},
            },
        },
        {
            "slug": "stripe",
            "label": "Stripe — charges, subscriptions, invoices",
            "ready": False,
            "install_hint": "Needs the verified-sources Stripe source installed.",
        },
        {
            "slug": "notion",
            "label": "Notion — databases & pages",
            "ready": False,
            "install_hint": "Needs the verified-sources Notion source installed.",
        },
    ]


def scaffold_from_openapi(spec_url: str, dest_name: str) -> dict[str, Any]:
    """Thin wrapper over ``dlt init --from-openapi``.

    Returns a summary the frontend can display (generated files, next
    steps). Actual code execution requires the user to review and
    commit the scaffolded module — we never auto-install a generated
    connector into the live process.
    """
    # A stub — real implementation would spawn ``dlt init ...`` in a
    # subprocess and capture the generated files.
    return {
        "spec_url": spec_url,
        "dest_name": dest_name,
        "status": "scaffold_pending",
        "note": (
            "Custom connectors are generated via `dlt-init-openapi` "
            "in a subprocess. Review + commit the scaffolded code, "
            "then restart to pick it up."
        ),
    }
