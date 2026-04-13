# tests/ — 294 Tests

Organized by module, mirroring the `src/` structure.

```bash
pytest tests/ -q           # Run all (294 tests, ~14s)
pytest tests/ -m "not slow" # Skip integration tests
```

## Structure

| Directory | Tests | What it covers |
|-----------|-------|----------------|
| `test_core/` | Config, settings, rate limiting, memory, plans |
| `test_ingestion/` | CSV/Parquet/Excel/JSON loaders, FK detection, registry |
| `test_profiling/` | AI + heuristic classifier, clarification questions |
| `test_semantic/` | DCD schema validation, render spec normalizer |
| `test_materialization/` | Gold table creation, summarizer, verified queries |
| `test_tools/` | SQL tool validation, Python session lifecycle |
| `test_api/` | HTTP endpoint integration tests |

## Fixtures

- `conftest.py` — Isolated settings (test .env), DuckDB in-memory connection, sample DCD
- Tests use `monkeypatch` for environment isolation
- `get_settings.cache_clear()` between tests that modify config
