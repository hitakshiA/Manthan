# Architecture

Manthan is a data layer that turns any dataset into something analysis
agents can query with zero guesswork. It does this through a three-stage
pipeline — **Bronze → Silver → Gold** — and a small, strict tool
interface exposed via FastAPI.

## High-level dataflow

```
┌─────────────┐
│  Upload     │  POST /datasets/upload (file)
│  or Connect │  POST /datasets/connect (db)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  Bronze — src/ingestion/                                │
│  - gateway dispatches to a Loader by file extension     │
│  - Loader copies the raw rows into a DuckDB table       │
│  - Validators check file size, encoding, non-empty      │
│  - Registry assigns a ds_* id and tracks status         │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  Silver — src/profiling/                                │
│  1. PERCEIVE  — per-column statistical profile          │
│  2. CLASSIFY  — LLM assigns role + aggregation          │
│  3. PII       — Layer 1 regex + Layer 2 Presidio        │
│                  + Layer 3 statistical heuristics       │
│  4. ENRICH    — temporal grain + metric proposals       │
│  5. DISAMBIG  — emit clarification questions            │
│  6. VALIDATE  — cross-check classifier vs dtypes        │
│  7. EMIT      — ProfilingResult                         │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  Semantic — src/semantic/                               │
│  - generator.build_dcd() → DataContextDocument          │
│  - editor applies user PUTs on top of generated DCD     │
│  - pruner emits a query-scoped subset for agents        │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  Gold — src/materialization/                            │
│  - optimizer: ORDER BY + COMMENT + ENUM conversion      │
│  - summarizer: temporal rollups + dimension breakdowns  │
│  - query_generator: verified question↔SQL pairs         │
│  - quality: GE-style expectation suite                  │
│  - exporter: Parquet (zstd) + manthan-context.yaml      │
│               + verified-queries.json                   │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  Tools — src/tools/                                     │
│  - run_sql: read-only guardrails, 30s timeout           │
│  - run_python: Docker sandbox, 2GB/2CPU, no network     │
│  - get_context: full or pruned DCD                      │
│  - get_schema: compact schema summary                   │
└─────────────────────────────────────────────────────────┘
```

## Module layout

```
src/
├── core/                # Settings, logger, DuckDB, OpenRouter, state, metrics
├── ingestion/           # Bronze: loaders + gateway + validators + registry
├── profiling/           # Silver: statistical + classifier + PII + enricher +
│                        #         clarification + ReAct-style agent
├── semantic/            # DCD schema, generator, editor, pruner
├── materialization/     # Gold: optimizer, summarizer, exporter, verified
│                        #       queries, quality
├── tools/               # Agent-facing tools (sql, python, context, schema)
├── api/                 # FastAPI routers (datasets, tools, clarification,
│                        #                   status, pipeline)
├── sandbox/             # Docker image for run_python
└── main.py              # FastAPI entry point + lifespan + /metrics
```

Dependency direction (enforced by convention per AGENTS.md):
`api → tools → materialization → semantic → profiling → ingestion → core`.
`core/` never imports from any other `src/` module.

## Data directory layout

Per-dataset artifacts live under `{DATA_DIRECTORY}/{dataset_id}/`:

```
data/ds_abcdef1234/
├── manthan-context.yaml      # Full DCD
├── verified-queries.json     # Few-shot examples for downstream agents
├── data/
│   ├── gold_{name}_{id}.parquet           # Sorted + ENUM'd main table
│   ├── gold_{name}_{id}_{grain}.parquet   # Temporal rollups (daily,monthly)
│   └── gold_{name}_{id}_by_{dim}.parquet  # Dimension breakdowns
├── metadata/                 # Reserved for profile.json, quality.json
└── output/                   # run_python file outputs
```

The directory is self-contained. Copy it anywhere and any DuckDB process
can reconstruct the agent-queryable view.

## Process model

A single FastAPI process owns one in-memory DuckDB connection plus the
registry, DCD store, and clarification queue via
`src/core/state.AppState`. The Docker sandbox runs each `run_python`
invocation as an ephemeral container with `/data/{id}/data` mounted
read-only. Multi-dataset and multi-tenant routing is a growth-path
concern; today one process serves one user.
