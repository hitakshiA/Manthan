# Manthan

**Seamless Self-Service Intelligence — Talk to Data.**

Manthan is the **data and semantic foundation** for a NatWest *Code for Purpose*
India Hackathon "Talk to Data" submission. It is **Layer 1 of a planned three-
layer architecture**:

```
┌─────────────────────────────┐
│  Layer 3 — Chat UI          │  Round 3 deliverable
│  (conversational frontend)  │
└───────────────┬─────────────┘
                │ natural language
                ▼
┌─────────────────────────────┐
│  Layer 2 — Analysis Agent   │  Round 3 deliverable
│  (LLM + tool use + narrate) │
└───────────────┬─────────────┘
                │ composable tool calls
                ▼
┌─────────────────────────────┐
│  Layer 1 — Manthan          │  ← this repo
│  (DCD + toolbox + Gold)     │
└─────────────────────────────┘
```

This layering mirrors the architecture cited in the PDF's own references —
Snowflake's semantic model → Cortex Analyst → Snowflake Intelligence. Manthan
is the semantic-model layer. The analysis agent and the conversational UI are
intentionally separate layers with their own lifecycles and test boundaries.

Hand Manthan a CSV, Excel, JSON, Parquet file, or a live PostgreSQL / MySQL /
SQLite connection and it gives back:

1. **A validated Data Context Document** — YAML with every column's role,
   description, confidence score, reasoning, synonyms, drill-up hierarchy,
   and source provenance.
2. **A curated Zstandard-compressed Parquet dataset** with sorted Gold table,
   ENUM-converted dimensions, temporal rollups, and dimension breakdowns
   pre-computed.
3. **A library of verified SQL queries** covering the four PDF use-case types
   (change / compare / breakdown / summarize).
4. **An expansive agent toolbox** — stateful Python sessions (variables
   persist across calls), SQL with temp-table scratchpad (CREATE TEMP TABLE
   AS SELECT... across turns), DCD context retrieval, schema introspection,
   and sandboxed Python execution. Layer 2 composes these primitives to
   answer any business question. See [`docs/building-the-agent.md`](docs/building-the-agent.md).

## Status

**Layer 1 is complete and tested end-to-end.** 230 tests pass (unit,
integration, Docker sandbox, ephemeral Postgres via testcontainers, and
three golden-DCD fixtures for retail / HR / marketing funnel datasets).
The live OpenRouter smoke test against `openai/gpt-oss-120b:free` exercises
the full Bronze → Silver → Gold flow with real LLM classification.

Layer 2 (analysis agent) and Layer 3 (chat UI) are Round 3 deliverables and
live in separate commits/repos.

## Features

- **Source-agnostic ingestion (Bronze).** CSV, TSV, TXT, Parquet, Excel
  (`.xlsx`/`.xls`/`.xlsm`), JSON/JSONL/NDJSON file loaders plus a database
  loader for PostgreSQL, MySQL, and SQLite that uses DuckDB's native scanner
  extensions (no Python DB driver required). File paths bind as SQL
  parameters; table identifiers pass a strict allow-list; arbitrary external
  column names are safely double-quoted.
- **Autonomous profiling agent (Silver).** A ReAct-inspired pipeline perceives
  the raw table, classifies every column's role (`metric`, `dimension`,
  `temporal`, `identifier`, `auxiliary`) via an LLM (OpenRouter
  `gpt-oss-120b:free` by default, validated against a 10-column benchmark
  with a perfect 10/10 score) **together with a confidence score, a one-
  sentence explanation of why that role was picked, and a list of user-
  facing synonyms**, detects temporal grain from gap analysis, **detects
  dimension hierarchies via functional-dependency analysis** (city →
  state → country), proposes computed metrics, emits interactive
  clarification questions for low-confidence columns, and surfaces
  classifier inconsistencies as explicit validation warnings. LLM calls
  are retried with exponential backoff on transient failures.
- **Multi-file upload with foreign-key detection.** `POST /datasets/upload-multi`
  accepts a list of related files (orders.csv + customers.csv + products.csv),
  loads each as its own raw table, profiles every table, and detects foreign
  keys by column-name + value-containment analysis. The DCD gains a `tables`
  list and a `relationships` list so the agent knows how to join across files.
- **Output discipline for sensitive columns (SPEC §6).** Columns tagged
  `role: identifier` (customer_name, order_id, account_number) must never
  be enumerated individually in analysis-agent answers — the DCD's
  `agent_instructions` carry the rule and downstream agents are expected
  to aggregate, count, or group by them instead. Manthan deliberately does
  **not** run a runtime PII scanner on uploads: the hackathon requires
  synthetic data only, and third-party entity scanners (Presidio) produce
  noisy false positives on legitimate dimension columns. Role
  classification is the enforcement primitive.
- **Data Context Document (DCD).** A pydantic-validated YAML artifact encoding
  the full semantic contract: columns, computed metrics, temporal range,
  data-quality caveats, agent instructions, and verified query pairs.
  Supports YAML round-trip serialization, query-aware pruning for
  downstream agent prompts, and user-driven PUT edits validated against
  the live DuckDB catalog.
- **Gold materialization.** Rewrites the raw table sorted on low-cardinality
  dimensions + the temporal column, attaches `COMMENT ON` documentation,
  converts low-cardinality dimensions to DuckDB `ENUM` types, builds temporal
  rollups at multiple granularities (daily + monthly for daily sources,
  monthly + quarterly for monthly sources, etc.) plus one breakdown per
  dimension, generates verified SQL pairs covering breakdown/summary/trend/
  change/comparison intents, runs a Great Expectations-style quality suite
  (non-null, value-set, numeric range), and exports everything as Zstandard-
  compressed Parquet plus a portable `manthan-context.yaml` and
  `verified-queries.json`.
- **Agent toolbox (composable primitives).**
  - `run_sql` — read-only by default, **plus a temp-table scratchpad**:
    `CREATE TEMP TABLE scratch AS SELECT ...` in turn 1 and `JOIN scratch ...`
    in turn 2, with the same session-scoped DuckDB connection. `DROP TABLE`
    is allowed but only on temp objects (verified against `duckdb_tables()`).
    30-second timeout via `connection.interrupt()`, comment-stripping
    guardrails, row limit with truncation flag.
  - `run_python` — **stateful Python sessions**. Variables, imports,
    DataFrames, and DuckDB connections defined in turn N are still in scope
    in turn N+1 when the same `session_id` is passed. Pre-loaded with `df`
    (pandas, primary Gold table), `con` (DuckDB), `OUTPUT_DIR` (writable).
    Libraries: pandas, numpy, scipy, sklearn, plotly, matplotlib, duckdb.
    Idle sessions swept after 30 minutes. Bare-expression evaluation
    captures `repr()` for REPL-style one-liners.
  - `get_context` — full or query-pruned DCD as YAML.
  - `get_schema` — compact summary including verified queries.

  **See [`docs/building-the-agent.md`](docs/building-the-agent.md) for the
  full Layer 2 integration guide** — shows exactly how to compose these
  primitives to answer each of the four PDF use cases.
- **REST API.** `/datasets/upload`, `/datasets/connect`, `/datasets/{id}`,
  `/datasets/{id}/context` (GET + PUT), `/datasets/{id}/schema`,
  `/datasets/{id}/progress`, `/clarification/{id}` (GET + POST),
  `/tools/sql`, `/tools/python`, `/tools/context/{id}`, `/tools/schema/{id}`,
  `WebSocket /datasets/{id}/status` for live pipeline progress, and
  `/metrics` for in-process counters + histograms.
- **Observability.** Structured JSON logging via structlog. In-process
  metrics for ingestion rows, profiling datasets, summary tables,
  materialization runs, and quality success percentage.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full architecture
diagram, and [`docs/data-context-schema.md`](docs/data-context-schema.md) and
[`docs/api-reference.md`](docs/api-reference.md) for the DCD shape and HTTP
surface.

Dependency flow (enforced by convention): `api → tools → materialization →
semantic → profiling → ingestion → core`. `core/` never imports from any
other `src/` module.

## Tech stack

- **Python 3.13+**
- **DuckDB 1.5** — analytical engine, scanner extensions for Postgres /
  MySQL / SQLite / Excel, Zstd Parquet export
- **ydata-profiling** + native DuckDB per-column queries — statistical
  profiling
- **Great Expectations 1.16** — data quality framework (we ship a lightweight
  suite built on top of it)
- **FastAPI + uvicorn + websockets** — HTTP + websocket API
- **pydantic + pydantic-settings** — schemas and configuration
- **httpx** — async OpenRouter client with exponential backoff retry
- **Docker SDK + testcontainers** — sandbox + ephemeral Postgres for tests
- **structlog** — JSON logging
- **ruff + pytest + pytest-asyncio** — linting, formatting, testing

All dependencies are Apache-2.0, MIT, BSD, or PSF licensed per AGENTS.md. No
GPL / LGPL / AGPL.

## Install (local)

```bash
git clone https://github.com/hitakshiA/Manthan.git
cd Manthan
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                           # fill in OPENROUTER_API_KEY
```

## Deploy (Fly.io free tier)

Manthan ships with `Dockerfile` + `fly.toml` for one-command deployment:

```bash
fly launch --no-deploy          # pick app name + region (bom for India)
fly secrets set OPENROUTER_API_KEY=sk-or-v1-...
fly deploy
fly open                        # browse /docs for the live API playground
```

The free-tier config runs a 512 MB VM with auto-stop when idle so the
cost is effectively zero. The `/docs` Swagger page is a live playground
— judges can click through every endpoint without cloning the repo.

## Run

```bash
uvicorn src.main:app --reload
```

Quick liveness check:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## End-to-end usage

Generate synthetic demo data, upload it, inspect the DCD, query it, edit the
DCD, run Python in the sandbox:

```bash
# 1. Generate 500 rows of synthetic retail sales data (no real PII).
python -m scripts.generate_demo_data
# (Optional) also seed a local SQLite database for the /datasets/connect flow.
python -m scripts.seed_database

# 2. Upload and run the pipeline.
curl -X POST http://localhost:8000/datasets/upload \
  -F "file=@data/nexaretail_sales.csv"
# => {"dataset_id": "ds_xxxxxxxxxx", "status": "gold", ...}

# 3. Or connect to a live database.
curl -X POST http://localhost:8000/datasets/connect \
  -H 'Content-Type: application/json' \
  -d '{"source_type":"sqlite","connection_string":"data/nexaretail.db","source_table":"orders","destination_table":"orders_local"}'

# 4. Inspect the DCD (YAML) and compact schema (JSON).
curl http://localhost:8000/datasets/ds_xxxxxxxxxx/context
curl http://localhost:8000/datasets/ds_xxxxxxxxxx/schema

# 5. Run a read-only SQL query through the agent tool.
curl -X POST http://localhost:8000/tools/sql \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_id": "ds_xxxxxxxxxx",
    "sql": "SELECT region, SUM(revenue) AS total FROM gold_nexaretail_sales_xxxxxxxxxx GROUP BY region ORDER BY total DESC",
    "max_rows": 100
  }'

# 6. Run Python in the Docker sandbox (pandas + plotly + matplotlib
#    preloaded, /data read-only, /output writable).
curl -X POST http://localhost:8000/tools/python \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_id": "ds_xxxxxxxxxx",
    "code": "import pandas as pd; print(df.groupby(\"region\")[\"revenue\"].sum()); df.describe().to_csv(\"/output/summary.csv\")"
  }'

# 7. Apply a manual correction to the DCD.
curl -X PUT http://localhost:8000/datasets/ds_xxxxxxxxxx/context \
  -H 'Content-Type: application/json' \
  -d '{"columns":[{"name":"revenue","description":"Net revenue in USD (returns excluded)"}]}'

# 8. Answer any clarification questions the agent emitted.
curl http://localhost:8000/clarification/ds_xxxxxxxxxx
curl -X POST http://localhost:8000/clarification/ds_xxxxxxxxxx \
  -H 'Content-Type: application/json' \
  -d '{"answers":[{"question_id":"q_1234","column_name":"amt","chosen_role":"metric","aggregation":"SUM"}]}'

# 9. Check metrics.
curl http://localhost:8000/metrics
```

On-disk dataset directory after a run:

```
data/ds_xxxxxxxxxx/
├── manthan-context.yaml
├── verified-queries.json
├── data/
│   ├── gold_nexaretail_sales_xxxxxxxxxx.parquet               # Zstd-compressed
│   ├── gold_nexaretail_sales_xxxxxxxxxx_daily.parquet         # temporal rollups
│   ├── gold_nexaretail_sales_xxxxxxxxxx_monthly.parquet
│   ├── gold_nexaretail_sales_xxxxxxxxxx_by_region.parquet     # dimension breakdowns
│   ├── gold_nexaretail_sales_xxxxxxxxxx_by_channel.parquet
│   ├── gold_nexaretail_sales_xxxxxxxxxx_by_product_category.parquet
│   └── gold_nexaretail_sales_xxxxxxxxxx_by_customer_segment.parquet
└── output/                    # /tools/python file outputs land here
```

## Tests

```bash
pytest tests/                  # full suite including slow tests (~15s)
# 240 passed

pytest tests/ -m "not slow"    # fast-only (~10s)
# 235 passed, 5 deselected
```

The suite includes unit tests for every module, integration tests for the
full Bronze → Silver → Gold pipeline, the sandbox container (builds the
image on demand and executes real Python code), an ephemeral PostgreSQL
container via testcontainers for the DB loader, and a full end-to-end API
test that drives every endpoint through the FastAPI `TestClient` with a
mocked LLM.

## Live-fire smoke test

Validated end-to-end on 2026-04-11 against **real** `openai/gpt-oss-120b:free`
on OpenRouter with 100 rows of synthetic NexaRetail data:

- Upload → classification (~8s, 12 columns correctly typed) → Gold
  materialization → export
- `GET /datasets/{id}/context` returns the full DCD as YAML with real
  `temporal.range`, `quality.freshness`, and LLM-generated column descriptions
- `POST /tools/sql` executes verified queries against the Gold table
  (`SELECT region, SUM(revenue) FROM ... GROUP BY region` returns North/
  South/East/West totals in <1 ms)
- `POST /tools/python` spins up the sandbox container, loads the Parquet
  via prelude, runs `df.groupby("region")["revenue"].sum()`, returns stdout
  and written files (~500 ms)
- `PUT /datasets/{id}/context` applies user corrections with catalog
  validation
- `GET /metrics` reports counters and histograms with quality-success
  percentages

## Limitations

- **In-memory dataset registry.** The `DatasetRegistry` lives in the FastAPI
  process; restarting the server loses the registry (though the per-dataset
  directory on disk is self-contained and can be reloaded).
- **Single writer.** Bronze ingestion writes to a single shared DuckDB
  connection; concurrent uploads against the same process will serialize.
- **Identifier-column filtering is enforcement-by-convention.** The
  `agent_instructions` tell downstream analysis agents not to enumerate
  identifier columns, but `/tools/sql` will still return them if the query
  asks for them. Manthan is designed for synthetic data per the hackathon
  rules; deployments against real-world data should add a SQL-layer filter
  that rejects SELECT clauses referencing `role: identifier` columns unless
  the user explicitly opts in (see SPEC §6).
- **No authentication** on the API.
- **ENUM conversion is opportunistic.** Columns whose distinct sets change
  during the session fall back to their original VARCHAR type rather than
  failing the materialization run.

## Future improvements

See [`SPEC.md`](SPEC.md) §7.3 for the intentional non-goals and the growth
path: multi-dataset multi-tenant routing, persistent registry, cloud
deployment with shared Parquet storage via DuckDB `httpfs`, CDC from live
databases, and cross-dataset joins.

## Team

- Hitakshi Arora — `hitakshiarora005@gmail.com`

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
