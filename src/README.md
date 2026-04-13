# src/ — Manthan Backend

The backend is organized as a 2-layer pipeline: **Layer 1** (data pipeline + semantic layer) and **Layer 2** (autonomous agent harness).

## Module map

```
src/
├── agent/            Layer 2 — the autonomous agent
├── api/              HTTP endpoints (FastAPI routers)
├── core/             Shared infrastructure
├── ingestion/        Bronze stage — file loading
├── profiling/        Silver stage — AI classification
├── semantic/         DCD schema + render spec models
├── materialization/  Gold stage — summary tables
├── tools/            SQL + Python tool implementations
└── sandbox/          Python REPL subprocess worker
```

## Layer 1 pipeline flow

```
Upload file
  → ingestion/    Load into DuckDB (Bronze)
  → profiling/    AI classifies columns, asks user if unsure (Silver)
  → semantic/     Build Data Context Document (DCD)
  → materialization/  Create Gold tables, summary aggregations, verified queries
```

## Layer 2 agent flow

```
User question
  → agent/loop.py    Auto-discover tables → assemble prompt → while loop
  → agent/tools.py   8 tools: SQL, Python, ask_user, plans, memory, subagents
  → agent/prompt.py  System prompt with 3 decision gates + chart rules
  → agent/events.py  22 SSE event types streamed to frontend
```

## Key files

| File | Purpose |
|------|---------|
| `core/config.py` | All configuration via environment variables (pydantic-settings) |
| `core/llm.py` | OpenRouter client with 3-model cascade + retry |
| `core/state.py` | Application state + dataset rehydration on restart |
| `agent/loop.py` | The agent while-loop (ManthanAgent class) |
| `agent/prompt.py` | System prompt assembly with decision gates |
| `semantic/render_spec.py` | Render spec Pydantic models + normalizer |
| `api/pipeline.py` | Full ingestion pipeline (Bronze → Silver → Gold) |
