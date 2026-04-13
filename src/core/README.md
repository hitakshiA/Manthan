# core/ — Shared Infrastructure

Foundation module imported by everything else. **Zero imports from other `src/` modules** — dependency flow is strictly one-directional:

```
api → tools → materialization → profiling → ingestion → core
```

## Files

| File | Purpose |
|------|---------|
| `config.py` | `Settings` class via pydantic-settings — all config from `.env` |
| `llm.py` | OpenRouter client with 3-model cascade, per-model retry, 429 instant failover |
| `state.py` | `AppState` singleton: DuckDB connection, DCD registry, dataset rehydration |
| `memory.py` | Cross-session key-value store backed by SQLite WAL |
| `plans.py` | Plan state machine: draft → pending → approved → executing → done |
| `subagents.py` | Isolated agent workspaces with parent-child session linking |
| `agent_tasks.py` | Per-session task tracking (create → in_progress → completed) |
| `rate_limit.py` | IP-based rate limiting with configurable whitelist |
| `logger.py` | Structured JSON logging via structlog |
| `database.py` | DuckDB connection factory with config-driven tuning |
| `metrics.py` | In-process counters for observability |
| `exceptions.py` | Exception hierarchy (`ManthanError` base class) |
