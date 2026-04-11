# Manthan

**Seamless Self-Service Intelligence — Talk to Data.**

Manthan is a data layer that ingests arbitrary datasets, profiles and annotates
them autonomously, and exposes them to downstream analysis agents through a
small set of well-defined tools. Built for the NatWest *Code for Purpose* India
Hackathon — Problem Statement: *Talk to Data*.

Hand Manthan a CSV it has never seen, and a minute later it gives back: a
validated Data Context Document describing every column, a curated Parquet
dataset optimized for DuckDB, a library of verified SQL queries covering the
four NatWest use-case types, and a REST API that analysis agents can query with
zero guesswork.

## Features

- **Source-agnostic ingestion (Bronze stage).** CSV, TSV, TXT, and Parquet
  files are routed through an extensible loader gateway into a DuckDB-backed
  registry. Filenames and file paths are bound as SQL parameters; table
  identifiers pass a strict allow-list; arbitrary CSV column names are safely
  double-quoted so no external name reaches SQL as plain string interpolation.
- **Autonomous profiling agent (Silver stage).** A ReAct-inspired pipeline
  perceives the raw table, classifies every column's role via an LLM
  (OpenRouter free-tier models by default), runs a layered PII detector, and
  enriches the result with temporal-grain detection and computed-metric
  proposals. Classifier output is validated against the statistical profile
  and inconsistencies surface as explicit warnings.
- **Data Context Document (DCD).** A pydantic-validated YAML artifact that
  encodes the full semantic contract: columns, metrics, temporal range, PII
  classifications, data-quality caveats, agent instructions, and verified
  query pairs. Built deterministically from the Silver outputs.
- **Gold materialization.** Rewrites the raw table sorted on
  low-cardinality dimensions + the temporal column, attaches `COMMENT ON`
  documentation, builds temporal and per-dimension summary tables, generates
  verified SQL pairs covering breakdown / summary / trend / change /
  comparison intents, and exports everything (Gold + summaries + DCD +
  verified queries) to a self-contained dataset directory.
- **Agent tools & HTTP API.** `run_sql` (read-only, truncation-aware),
  `get_context` (full or query-pruned DCD), and `get_schema` (compact
  summary) are exposed both as Python functions and as FastAPI routes under
  `/datasets` and `/tools`.

## Status

End-to-end Bronze → Silver → Gold flow is implemented and tested against the
checked-in `sample_sales.csv` fixture: an uploaded CSV produces a validated
DCD, an optimized Gold table, summary tables, verified queries executable
through `/tools/sql`, and a dataset directory with Parquet + YAML + JSON
artifacts on disk.

See [`SPEC.md`](SPEC.md) for the engineering specification and
[`AGENTS.md`](AGENTS.md) for contribution guidelines.

### What's deliberately deferred

- **Presidio PII Layer 2** (value-pattern scanning). Column-name heuristics
  (Layer 1) and statistical heuristics (Layer 3) are in place; Layer 2
  arrives after the spaCy + Presidio install is wired up.
- **Python sandbox tool** (Docker-backed `run_python`). The agent tool
  interface is ready for it; the sandbox container is a subsequent
  milestone.
- **Great Expectations quality suite.** Simple completeness and freshness
  indicators live in the DCD today.
- **Interactive clarification (`ask_user`).** The profiling agent picks
  deterministic fallbacks and surfaces low-confidence classifications as
  warnings on the `ProfilingResult`.
- **Excel / JSON / database loaders.** CSV and Parquet are live; the
  remaining formats fit the existing gateway/loader protocol.

## Architecture

```
upload CSV
    │
    ▼
[Bronze] ingestion/ — gateway + CSV/Parquet loaders + registry
    │    → raw_{dataset} table in DuckDB
    ▼
[Silver] profiling/ — statistical + classifier (LLM) + PII + enricher + agent
    │    → ProfilingResult (profiles, classifications, PII flags,
    │      temporal grain, metric proposals, warnings)
    ▼
semantic/ — generator → DataContextDocument (pydantic, YAML)
    │
    ▼
[Gold] materialization/ — optimizer (sort + COMMENT) → summarizer
    │    (temporal rollups + dimension breakdowns) → verified_query generator
    │    → exporter (Parquet + YAML + JSON under /data/{dataset_id}/)
    ▼
tools/ + api/ — run_sql, get_context, get_schema
    exposed as FastAPI routes and Python callables
```

Dependency flow (enforced by convention, per AGENTS.md): `api → tools →
materialization → semantic → profiling → ingestion → core`. `core/` imports
from nothing else in `src/`.

## Tech stack

- **Python 3.12+**
- **DuckDB** (MIT) — analytical engine for ingestion, profiling, Gold
  materialization, and the `run_sql` tool
- **pydantic + pydantic-settings** — schemas and configuration
- **FastAPI + uvicorn** — HTTP API
- **httpx** — async OpenRouter client for the LLM classifier
- **structlog** — JSON logging
- **PyYAML** — DCD serialization
- **ruff + pytest** — linting, formatting, testing

All dependencies are Apache-2.0, MIT, BSD, or PSF licensed per AGENTS.md.

## Install

```bash
git clone https://github.com/hitakshiA/Manthan.git
cd Manthan
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in OPENROUTER_API_KEY
```

## Run

```bash
uvicorn src.main:app --reload
```

Quick liveness check:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Usage — end to end in one session

Generate synthetic demo data, upload it, inspect the DCD, and run a verified
query:

```bash
# Generate 500 rows of synthetic retail sales data
python scripts/generate_demo_data.py

# Upload and kick off Bronze → Silver → Gold
curl -X POST http://localhost:8000/datasets/upload \
  -F "file=@data/nexaretail_sales.csv"

# Response: {"dataset_id": "ds_abcdef1234", "name": "Nexaretail Sales",
#            "row_count": 500, "status": "gold", ...}

# List loaded datasets
curl http://localhost:8000/datasets

# Fetch the Data Context Document as YAML
curl http://localhost:8000/datasets/ds_abcdef1234/context

# Compact schema summary (includes verified queries)
curl http://localhost:8000/datasets/ds_abcdef1234/schema

# Run a read-only SQL query through the agent tool
curl -X POST http://localhost:8000/tools/sql \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_id": "ds_abcdef1234",
    "sql": "SELECT region, SUM(revenue) AS total FROM gold_nexaretail_sales_abcdef1234 GROUP BY region ORDER BY total DESC",
    "max_rows": 100
  }'
```

The dataset directory (`data/ds_abcdef1234/`) on disk contains a portable
snapshot:

```
data/ds_abcdef1234/
├── manthan-context.yaml      # full DCD
├── verified-queries.json     # 6+ verified question/SQL pairs
└── data/
    ├── gold_nexaretail_sales_abcdef1234.parquet
    ├── gold_nexaretail_sales_abcdef1234_daily.parquet
    ├── gold_nexaretail_sales_abcdef1234_by_region.parquet
    └── gold_nexaretail_sales_abcdef1234_by_customer_segment.parquet
```

Any DuckDB process can reconstruct the agent-queryable view by reading these
files.

## Tests

```bash
pytest tests/ -v
# 192 passed
```

The suite includes unit tests for every module, integration tests for the
ingestion → profiling → materialization pipeline, and a full end-to-end API
test that drives `POST /datasets/upload`, `/datasets/{id}/context`,
`/datasets/{id}/schema`, and `POST /tools/sql` through the FastAPI
`TestClient` with a mocked LLM.

## Limitations

- **LLM dependency for the column classifier.** An OpenRouter API key is
  required for `POST /datasets/upload` to succeed. The classifier is small
  (one JSON call per dataset) and uses the free-tier Gemma model by default.
- **In-memory dataset registry.** The `DatasetRegistry` lives in the FastAPI
  process; restarting the server loses the list (though the per-dataset
  directory on disk is self-contained and can be reloaded).
- **Single writer.** Bronze ingestion writes to a single shared DuckDB
  connection; concurrent uploads against the same process will serialize.
- **Only CSV and Parquet ingestion.** Excel, JSON, and external database
  sources require additional loaders.
- **No Presidio content scan yet**, so value-level PII (e.g. emails embedded
  in a generic "notes" column) is not detected — only column-name and
  statistical signals fire.
- **No authentication** on the API.

## Future improvements

See [`SPEC.md`](SPEC.md) §7.3 for the intentional non-goals and the growth
path: Excel / JSON / database loaders, Presidio Layer 2, Docker sandbox for
`run_python`, Great Expectations quality suite, multi-dataset multi-tenant
routing, cloud deployment with shared Parquet storage.

## Team

- Hitakshi Arora — `hitakshiarora005@gmail.com`

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
