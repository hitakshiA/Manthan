# Manthan Layer 1 — Technical Specification

**Version:** 1.0 | **Status:** Complete + Live-Tested | **Date:** April 2026

---

## 1. What Layer 1 Is

Layer 1 is the **data + semantic + agent toolbox** layer of Manthan. It takes raw files (CSV, Parquet, Excel, JSON, database connections), runs them through a Bronze → Silver → Gold pipeline, produces a semantic Data Context Document (DCD), and exposes a toolbox of HTTP endpoints that an autonomous agent (Layer 2) uses to query, analyze, plan, ask questions, delegate to subagents, and persist memory across sessions.

Layer 1 is not an agent. It is the toolbox an agent uses. It does not reason, decide, or render. It ingests, profiles, materializes, and serves.

**Stack:** Python 3.13, FastAPI, DuckDB (in-memory + Parquet), pydantic/pydantic-settings, OpenRouter (any chat-completion model), SQLite (memory + plan audit persistence), structlog, httpx.

---

## 2. Architecture

```
                         ┌───────────────────────────────┐
                         │          FastAPI App           │
                         │     (src/main.py, 58 routes)   │
                         └──────┬────────────────────────┘
                                │
    ┌───────────────────────────┼───────────────────────────────┐
    │                           │                               │
    ▼                           ▼                               ▼
┌─────────┐  ┌──────────────────────────┐  ┌─────────────────────────┐
│ Datasets│  │        Tools             │  │    Agent Primitives     │
│ Router  │  │  SQL · Python · Schema   │  │ Plans · ask_user · Mem  │
│         │  │  Context · Tool List     │  │ Tasks · Subagents       │
└────┬────┘  └──────────┬───────────────┘  └───────────┬─────────────┘
     │                  │                              │
     ▼                  ▼                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        AppState (singleton)                     │
│  registry · connection · dcds · gold_table_names · memory ·     │
│  plans · agent_tasks · ask_user · subagents · python_sessions   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
    ┌──────────┐      ┌──────────────┐     ┌──────────────┐
    │  DuckDB  │      │   SQLite     │     │  Filesystem  │
    │ (in-mem) │      │ memory.db    │     │ data/ds_*/   │
    │ Gold tbls│      │ plan_audit.db│     │ *.parquet    │
    │ temp tbls│      │              │     │ *.yaml       │
    └──────────┘      └──────────────┘     └──────────────┘
```

### AppState

`src/core/state.py` — singleton dataclass holding every per-process resource. Created lazily by `get_state()` and cached via `@lru_cache`. On startup, calls `rehydrate_datasets_from_disk()` to restore previously-ingested datasets from `data/ds_*/manthan-context.yaml`.

| Field | Type | Persistence |
|---|---|---|
| `registry` | `DatasetRegistry` | In-memory + disk rehydration on restart |
| `connection` | `duckdb.DuckDBPyConnection` | In-memory; Gold views re-attached from parquet on restart |
| `data_directory` | `Path` | `./data` (configurable) |
| `memory` | `MemoryStore` | SQLite WAL at `data/agent_memory.db` |
| `plans` | `PlanStore` | In-memory plan objects + SQLite WAL audit at `data/plan_audit.db` |
| `dcds` | `dict[str, DataContextDocument]` | In-memory + YAML on disk |
| `gold_table_names` | `dict[str, str]` | In-memory, rebuilt from parquet filenames |
| `python_sessions` | `PythonSessionManager` | Subprocess per session, idle-reaped at 30min |
| `agent_tasks` | `AgentTaskStore` | In-memory only (ephemeral per conversation) |
| `ask_user` | `AskUserRegistry` | In-memory only (blocking events, not persisted) |
| `subagents` | `SubagentStore` | In-memory only |
| `clarifications` | `dict` | In-memory only |

---

## 3. Pipeline: Bronze → Silver → Gold

### 3.1 Bronze — Raw Ingestion

**Entry points:** `POST /datasets/upload` (single file), `POST /datasets/upload-multi` (related files), `POST /datasets/connect` (database source)

**Process:**
1. File saved to temp dir, type detected by `IngestionGateway` (`src/ingestion/gateway.py`)
2. Loader creates a `raw_{stem}` table in DuckDB via `CREATE TABLE raw_foo AS SELECT * FROM read_csv(...)` (or `read_parquet`, `read_json`, `st_read` for Excel)
3. `LoadResult` captured: table_name, source_type, original_filename, row_count, column_count, raw_size_bytes, ingested_at
4. Registry entry created with `status=bronze`

**Supported formats:**

| Format | Extensions | Loader | Notes |
|---|---|---|---|
| CSV | `.csv`, `.tsv`, `.txt` | `CsvLoader` | DuckDB auto-detection, 10k-row sample |
| Parquet | `.parquet`, `.pq` | `ParquetLoader` | Columnar, zero-copy |
| Excel | `.xlsx`, `.xls`, `.xlsm` | `ExcelLoader` | First sheet extracted |
| JSON | `.json`, `.jsonl`, `.ndjson` | `JsonLoader` | Line-delimited supported |
| Database | connection string | `DbLoadRequest` | Postgres/MySQL/SQLite via DuckDB extensions |

### 3.2 Silver — Profiling + Classification

**Process:**
1. `profile_columns()` (`src/profiling/statistical.py`) computes per-column: dtype, row_count, null_count, completeness, distinct_count, cardinality_ratio, sample_values (20), numeric stats (min/max/mean/median/stddev/p25/p75), temporal range
2. `classify_columns()` (`src/profiling/classifier.py`) sends column profiles to the configured LLM via OpenRouter. Each column gets: `role` (metric/dimension/temporal/identifier/auxiliary), `description`, `aggregation` (SUM/AVG/COUNT/MIN/MAX for metrics), `confidence` (0-1), `reasoning`, `synonyms`
3. If the LLM is unavailable (rate-limited, quota exhausted, transport error), the **heuristic fallback classifier** kicks in automatically — deterministic rules based on column name patterns, dtype, and cardinality. Classifications are labeled `heuristic-fallback:` in the reasoning field
4. Temporal column detected; grain inferred (daily/weekly/monthly/quarterly/yearly/irregular)
5. Functional-dependency hierarchies detected (e.g., city → state → country)
6. Metric proposals generated (e.g., `average_revenue_per_order_id`)
7. Clarification questions generated for low-confidence classifications
8. Multi-file datasets: `detect_relationships()` finds FKs via value-containment analysis across shared column names. Both sides cast to VARCHAR to survive mixed-dtype keys
9. Registry entry updated to `status=silver`

**Classifier model:** configurable via `OPENROUTER_MODEL` env var. Tested with `nvidia/nemotron-3-nano-30b-a3b:free` (136 tok/s throughput, 6s E2E latency) and `nvidia/nemotron-3-super-120b-a12b:free` (slower reasoning model — works but not justified for classification).

**LLM retry policy:** 6 attempts, exponential backoff 5s/10s/20s/40s/80s/90s (capped). Retries on: HTTP 429/500/502/503/504, HTTP 200 with error-body envelope, HTTP 200 with missing `choices`. Short-circuits immediately on `free-models-per-day` quota exhaustion (daily free tier ceiling).

### 3.3 Gold — Materialization + Export

**Process:**
1. `create_gold_table()` (`src/materialization/optimizer.py`): deduplicate, sort by temporal column, optimize dimension columns as DuckDB ENUMs where cardinality ≤ 100
2. `create_summary_tables()` (`src/materialization/summarizer.py`): one temporal rollup at the detected grain + additional coarser rollups (daily→monthly, monthly→quarterly), one dimension breakdown per dimension column. Non-numeric columns tagged as metrics are filtered out to prevent SUM(VARCHAR) crashes. Column names sanitized via `sanitize_for_identifier()` for table-name safety
3. `generate_verified_queries()` (`src/materialization/query_generator.py`): 6-12 deterministic NL↔SQL pairs covering breakdown, summary, trend, change, comparison intents. Uses the DCD's column metadata to pick appropriate aggregations and groupings
4. `run_quality_suite()` (`src/materialization/quality.py`): validates non-null constraints, cardinality bounds, temporal continuity
5. `export_dataset()` (`src/materialization/exporter.py`): writes Gold parquet + manthan-context.yaml + verified-queries.json to `data/ds_{id}/`
6. Registry entry updated to `status=gold`

**On-disk structure per dataset:**
```
data/ds_a0e60ba9b2/
├── data/
│   ├── gold_yellow_tripdata_2024_01_a0e60ba9b2.parquet          # primary
│   ├── gold_yellow_tripdata_2024_01_a0e60ba9b2_daily.parquet    # temporal rollup
│   ├── gold_yellow_tripdata_2024_01_a0e60ba9b2_monthly.parquet
│   ├── gold_yellow_tripdata_2024_01_a0e60ba9b2_by_payment_type.parquet
│   └── ...
├── manthan-context.yaml     # full DCD
├── verified-queries.json    # NL↔SQL pairs
├── metadata/                # (reserved)
└── output/                  # Python sandbox OUTPUT_DIR
    ├── render_spec.json     # agent's Layer 3 contract artifact
    ├── fare_hist.parquet    # chart data
    └── ...
```

---

## 4. Data Context Document (DCD)

The DCD is the semantic contract between Layer 1 and Layer 2. It describes what the data means, not just what it looks like.

### Schema (`src/semantic/schema.py`)

```yaml
version: "1.0"
dataset:
  id: ds_a0e60ba9b2
  name: Yellow Tripdata 2024 01
  description: "PARQUET dataset loaded from yellow_tripdata_2024-01.parquet (2964624 rows, 19 columns)."
  source:
    type: parquet
    original_filename: yellow_tripdata_2024-01.parquet
    ingested_at: "2026-04-11T20:08:30.318481Z"
    row_count: 2964624
    raw_size_bytes: 49961641
  temporal:
    grain: daily
    column: tpep_pickup_datetime
    range: { start: "2024-01-01", end: "2024-01-31" }
    timezone: UTC
  columns:
    - name: fare_amount
      dtype: DOUBLE
      role: metric
      description: "Metered fare for the trip"
      aggregation: SUM
      nullable: false
      completeness: 1.0
      cardinality: 8423
      stats: { min: -480.0, max: 398808.4, mean: 18.18, median: 11.4, ... }
      sample_values: [6.5, 14.0, 22.5, 8.0, 52.0]
      hierarchy: null
      synonyms: [fare, base_fare]
      classification_reasoning: "Numeric column representing metered fare amounts..."
      classification_confidence: 0.96
    - name: tpep_pickup_datetime
      dtype: TIMESTAMP
      role: temporal
      ...
  computed_metrics:
    - name: avg_fare_per_trip
      formula: "AVG(fare_amount)"
      description: "Average fare across all trips"
      depends_on: [fare_amount]
  tables: []                    # populated for multi-file uploads
  relationships: []             # FK graph for multi-file
  quality:
    freshness: "2026-04-11T20:08:30Z"
    non_null_percentage: 0.98
    known_limitations: ["Tip amounts on cash rides are underreported"]
    checks_passed: 8
    checks_total: 10
    success_percent: 80.0
  verified_queries:
    - question: "What is the total fare_amount by payment_type?"
      sql: "SELECT \"payment_type\" AS payment_type, SUM(\"fare_amount\") AS total_fare_amount FROM gold_... GROUP BY 1 ORDER BY total_fare_amount DESC"
      intent: breakdown
  agent_instructions:
    - "fare_amount is an identifier — count or aggregate, never enumerate individually."
    - "tpep_pickup_datetime defines the temporal axis; default grain is daily."
```

### DCD access endpoints

| Endpoint | Returns |
|---|---|
| `GET /datasets/{id}/context` | Full DCD as YAML text |
| `GET /datasets/{id}/context?query=revenue+by+region` | Pruned DCD (≤30 most relevant columns) |
| `GET /datasets/{id}/schema` | Compact JSON: columns with roles, summary_tables, verified_queries |
| `PUT /datasets/{id}/context` | Apply user corrections (validates against DuckDB catalog) |

---

## 5. Tool Surface (what Layer 2 calls)

### 5.1 SQL Tool — `POST /tools/sql`

**Request:** `{dataset_id, sql, max_rows=1000}`

**Allowed SQL:**
- `SELECT ...` / `WITH ... SELECT ...` — read-only queries against Gold tables, summary tables, temp tables
- `CREATE [OR REPLACE] TEMP TABLE|VIEW name AS SELECT ...` — scratchpad across calls
- `DROP TABLE|VIEW [IF EXISTS] temp_name` — only temp objects (validated against DuckDB's `temp` catalog)

**Blocked:** INSERT, UPDATE, DELETE, ALTER, DROP on persistent objects, DESCRIBE (use `information_schema.columns` instead)

**Response:** `{columns, rows, row_count, truncated, execution_time_ms, statement_kind, affected}`

**Timeout:** 30s default via `threading.Timer` + `connection.interrupt()`

**Temp table scoping:** per-connection. A temp table created in call 1 survives to call 2 because they share the server's `state.connection`. This is the agent's multi-step scratchpad.

**Observed in stress test:** Taxi 2.9M-row queries run sub-second against Gold views. Temp tables work end-to-end (Tier 3A created `taxi_tip_buckets` with 2.9M rows, aggregated against it in the next call). `information_schema.tables` and `information_schema.columns` work for table/column discovery.

### 5.2 Python Tool — `POST /tools/python`

**Request:** `{dataset_id, code, session_id (optional), timeout_seconds=60}`

**Sandbox architecture:** each session is a Python subprocess running `src/sandbox/repl.py`. Variables, imports, DataFrames persist across calls when the same `session_id` is reused.

**Pre-loaded globals:**
| Name | Type | Contents |
|---|---|---|
| `df` | `pandas.DataFrame` | Primary Gold table loaded from parquet |
| `con` | `duckdb.DuckDBPyConnection` | In-memory DuckDB with `dataset` view pointing at the primary Gold parquet |
| `OUTPUT_DIR` | `str` | Writable path at `data/{ds_id}/output/` |
| `DATA_DIR` | `Path` | Read-only path at `data/{ds_id}/data/` |
| `pd`, `duckdb`, `Path` | modules | Pre-imported |

**Critical contract detail (discovered in stress test):** the primary Gold parquet is exposed as a DuckDB view named `dataset`, NOT under the `gold_foo_bar` name that `/tools/sql` uses. The agent must query `FROM dataset` in the sandbox, not `FROM "gold_yellow_tripdata_2024_01_xxx"`. This is the single most common Layer 2 footgun.

**Multi-file limitation:** only the first parquet file in `DATA_DIR` is loaded as `dataset`. Other tables (e.g., in Lahman's 10-table upload) exist on disk but are not auto-loaded. Agent workaround: `con.execute("SELECT * FROM read_parquet('/abs/path/to/other.parquet')")`.

**Response:** `{session_id, stdout, stderr, exit_code, execution_time_ms, repr, files_created, timed_out}`

**`files_created`:** any files written to `OUTPUT_DIR` are returned with name, path, size. This is how the agent emits `render_spec.json` and data parquet files for Layer 3.

**Observed in stress test:** session reuse works reliably. Variable `persist_check = 'ok-1'` set in call 1, asserted in call 2 across all 4 Tier 3 cells. Idle sessions reaped at 30 minutes.

### 5.3 Plans — `POST /plans` + state machine

**Purpose:** the agent proposes a structured analysis plan and blocks until the user approves, rejects, or amends it. Ensures the agent's interpretation (grounded in DCD citations) is validated before burning tool calls.

**State machine:**
```
draft → submit → pending → approve → approved → execute_start → executing → execute_done → executed
                    │                                                  └──────→ failed
                    ├── reject → rejected (terminal)
                    └── amend → amended → submit → pending (loop)
```

**Plan object fields:**
- `session_id`, `dataset_id`, `user_question` (verbatim), `interpretation` (agent's restatement)
- `citations[]`: `{kind, identifier, reason}` — specific DCD columns/metrics/instructions the interpretation relies on
- `steps[]`: `{id, tool, description, arguments, depends_on[]}` — the concrete tool calls the agent intends to run
- `expected_cost`: `{tool_calls: N, llm_calls: N}`
- `risks[]`: caveats the agent is aware of

**Audit trail:** every state transition logged to SQLite at `data/plan_audit.db`. Survives server restart. Endpoint: `GET /plans/{id}/audit` returns event history regardless of whether the Plan object is still in memory.

**Wait semantics:** `POST /plans/{id}/wait?timeout_seconds=600` blocks via `threading.Event.wait()`. Returns when the user approves/rejects/amends OR timeout fires (returns `timed_out: true`).

**Observed in stress test:** 20 plans created across Tiers 2-5. All followed the full state machine. All audit trails captured `created → submit → approve → execute_start → execute_done`. Plan audit trails survive a real uvicorn restart (verified in Tier 5 phase 2).

### 5.4 Ask User — `POST /ask_user` + blocking wait

**Purpose:** human-in-the-loop clarification when the agent hits genuine ambiguity (e.g., "last month" = calendar month or trailing 30 days?).

**Flow:**
1. Agent: `POST /ask_user` with `{session_id, prompt, options[], allow_free_text, context}`
2. Agent: `POST /ask_user/{id}/wait?timeout_seconds=300` — blocks
3. UI: `GET /ask_user/pending?session_id=` — polls for pending questions
4. User: `POST /ask_user/{id}/answer` — wakes the blocked agent
5. Agent receives the answer, continues

**Timeout:** returns `timed_out: true` if the user doesn't respond. Agent can choose a default or retry.

**Observed in stress test:** 4 Tier 2 cells exercised the full flow with a background user-simulator thread polling `/ask_user/pending` and answering automatically. Zero deadlocks, zero timeouts.

### 5.5 Memory — `POST /memory` + `GET /memory/{scope}/{scope_id}/{key}`

**Purpose:** cross-session persistent key-value store. Agents remember user corrections, metric definitions, analysis conclusions, business-specific terminology.

**Scopes:** `dataset` (notes attached to a ds_id), `user` (per-user preferences), `global` (deployment-wide facts), `session` (ephemeral, for subagent→parent bridging)

**Categories:** `preference`, `definition`, `caveat`, `fact`, `note`

**Persistence:** SQLite WAL at `data/agent_memory.db`. Survives server restart.

**Endpoints:** POST (put), GET (single entry), DELETE, GET (list scope with optional category filter), GET `/memory/search/?query=` (substring search on key + description)

**Observed in stress test:** 31 memory writes across Tiers 4-5. All 27 subagent→parent bridges used `scope_type=session`. All 4 Tier 5 dataset-scoped conclusions survived a real server restart. `memory_get` in phase 2 successfully retrieved phase 1's findings across process boundaries.

### 5.6 Subagents — `POST /subagents/spawn` + lifecycle

**Purpose:** isolated workspaces for multi-agent analysis. A master agent spawns subagents, each gets its own `session_id` (→ own Python kernel, own task list, own memory scope). The master waits for subagent results, integrates them, produces a unified report.

**Lifecycle:** `spawned → running → completed | failed | cancelled`

**Memory bridging:** `POST /subagents/{id}/complete` with `write_to_parent_memory=True` automatically writes the result to the parent session's memory scope under a configurable key. The master reads it back via `GET /memory/session/{parent_session_id}/{key}`.

**Observed in stress test:** 27 subagents total across Tiers 4-5. All completed with memory bridging. Master successfully stitched 3-4 subagent sections into coherent moderate/complex render specs. Python kernel isolation is by construction (each session_id gets a new subprocess).

### 5.7 Agent Tasks — `POST /tasks` + update lifecycle

**Purpose:** per-session todo list for tracking decomposition. The agent creates tasks at plan time, marks them `in_progress` when starting, `completed` when done.

**Statuses:** `pending → in_progress → completed | cancelled`

**Observed in stress test:** Tier 3 created 4-5 tasks per cell for plan decomposition tracking. All status transitions worked.

### 5.8 Tool Discovery — `GET /tools/list`

**Purpose:** static manifest of every agent-facing tool in Layer 1. Layer 2 reads this on startup to know what it can call.

**Response:** `{version: "1.0", tool_count: 13, tools: [{name, endpoint, description, input, output}]}`

**Tools listed:** run_sql, run_python, get_context, get_schema, ask_user, plan, tasks, memory, subagents, clarification, upload, connect_database, edit_context

### 5.9 Clarifications — `GET /clarification/{dataset_id}`

**Purpose:** pending Silver-stage questions about low-confidence column classifications. Answer them via `POST /clarification/{id}` to refine the DCD before running expensive analyses.

### 5.10 Edit Context — `PUT /datasets/{dataset_id}/context`

**Purpose:** apply user corrections to a generated DCD. Edits validated against the live DuckDB catalog — can't reference columns that don't exist.

---

## 6. Configuration

All configuration flows through `src/core/config.py` → `Settings` (pydantic-settings). Loaded from `.env` file + environment variables, case-insensitive.

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | *(required, no default)* | OpenRouter API key |
| `OPENROUTER_MODEL` | `openai/gpt-oss-120b:free` | LLM model slug for profiling |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API endpoint |
| `DUCKDB_MEMORY_LIMIT` | `4GB` | DuckDB heap cap |
| `DUCKDB_THREADS` | `4` | DuckDB worker threads |
| `DUCKDB_TEMP_DIRECTORY` | `/tmp/duckdb` | Spill-to-disk scratch |
| `DATA_DIRECTORY` | `./data` | Root for dataset artifacts |
| `MAX_UPLOAD_SIZE_MB` | `500` | Upload ceiling |
| `LOG_LEVEL` | `info` | Logging verbosity |
| `LOG_FORMAT` | `json` | `json` or `console` |

---

## 7. Resilience (built and proven during stress test)

### LLM fault tolerance

| Failure mode | Handling |
|---|---|
| OpenRouter 429 / 500 / 502 / 503 / 504 | Retry up to 6× with exponential backoff (5s → 90s cap) |
| HTTP 200 with `{"error": {...}}` body | Retry (treats as semantic error — upstream provider hiccup) |
| HTTP 200 with missing `choices` | Retry (treats as malformed response) |
| Daily free-tier quota exhausted (`free-models-per-day`) | Short-circuit immediately, fall back to heuristic classifier |
| LLM response not valid JSON | Fall back to heuristic classifier |
| Network timeout (180s ceiling) | Retry with backoff |

### Heuristic fallback classifier

When the LLM is unavailable, `src/profiling/classifier.py:heuristic_classify()` applies deterministic rules:

1. Temporal dtype → role=temporal
2. Column name matches `_id`/`_key` pattern + high cardinality ratio → role=identifier
3. Numeric dtype + name matches metric hint (amount, price, revenue, ...) → role=metric (SUM)
4. Numeric dtype + low distinct count (≤50) → role=dimension
5. String + name matches dimension hint (region, category, status, ...) → role=dimension
6. String + name matches auxiliary hint (description, notes, url, ...) → role=auxiliary
7. Default → auxiliary

All heuristic classifications carry `reasoning="heuristic-fallback: ..."` for auditability.

### Dataset persistence across restart

`rehydrate_datasets_from_disk()` runs on startup: scans `data/ds_*/`, reads DCD YAML, re-attaches Gold parquet as DuckDB views, rebuilds the registry. Verified in Tier 5: server killed between phases, restarted, phase 2 queried yesterday's datasets without re-upload.

### Plan audit persistence

SQLite WAL at `data/plan_audit.db`. The `GET /plans/{id}/audit` endpoint reads directly from the SQLite log — no dependency on the in-memory Plan object. Works across restarts.

### Memory persistence

SQLite WAL at `data/agent_memory.db`. Full CRUD + search. Survives restarts by design.

---

## 8. Live Stress Test Observations

### What the unit tests could NOT have caught

| Bug | Why unit tests missed it |
|---|---|
| OpenRouter 200 + error body | Mock transport always returns clean JSON |
| Dotted column names crash Gold materialization | Fixtures use clean snake_case names |
| VARCHAR metrics crash SUM() | Fixtures have correct dtypes |
| Mixed-dtype FK detection crash | Fixture FKs are same-typed |
| Plan audit 404 after restart | Tests never restart the server |
| Dataset registry lost after restart | Same |

### Performance benchmarks (real data through real pipeline)

| Dataset | Rows | Cols | Pipeline wall time | Classifier |
|---|---|---|---|---|
| NYC Taxi (Parquet) | 2,964,624 | 19 | 3.7s (heuristic) / 37.8s (LLM) | LLM is ~10× slower |
| UCI Adult (CSV) | 48,842 | 15 | 0.7s (heuristic) / 30.2s (LLM) | |
| Lahman Baseball (10 CSVs) | 366,639 total | 7-50 | 6.2s (heuristic) | 165 FKs detected |
| Ames Housing (CSV, 82 cols) | 2,930 | 82 | 1.0s (heuristic) / 101s (LLM) | 82 cols is ~1min with LLM |

### Primitive exercise counts across the full test

| Primitive | Calls | Outcome |
|---|---|---|
| `POST /datasets/upload` | 12+ | all reached `status=gold` |
| `POST /datasets/upload-multi` | 4+ | 165 FKs detected on Lahman |
| `POST /tools/sql` | ~80 | zero execution errors on valid SQL |
| `POST /tools/python` | ~60 | session reuse verified; variable persistence confirmed |
| `POST /plans` (full state machine) | 20 | all audit trails complete |
| `POST /ask_user` (blocking wait) | 4 | all unblocked by simulator |
| `POST /memory` | 31 | all persisted; 4 survived restart |
| `POST /subagents/spawn` | 27 | all completed with memory bridging |
| `POST /tasks` | ~20 | all status transitions worked |
| `GET /tools/list` | 4 | manifest served correctly |

---

## 9. Test Suite

**294 tests, all passing.** Runs in ~13 seconds.

| Directory | Coverage area | Count |
|---|---|---|
| `tests/test_api/` | HTTP endpoints (datasets, plans, memory, subagents, ask_user, primitives) | 4 files |
| `tests/test_core/` | Config, database, LLM, memory, plans, subagents, agent_tasks, ask_user, logger, metrics | 12 files |
| `tests/test_ingestion/` | Loaders, validators, FK detection, registry | ~8 files |
| `tests/test_profiling/` | Classifier (LLM + heuristic), statistical profiler, clarification, enricher | ~6 files |
| `tests/test_semantic/` | DCD generation, schema validation, editor, pruner, golden DCD tests | ~5 files |
| `tests/test_materialization/` | Gold tables, summaries, quality, verified queries, exporter | ~5 files |
| `tests/test_tools/` | SQL tool (allowed/rejected statements), Python sandbox, context/schema tools | ~5 files |

### Test patterns

- `httpx.MockTransport` for LLM stubbing (zero network traffic)
- `FastAPI.dependency_overrides[get_state]` for injecting test AppState
- `tmp_path` for isolated filesystem per test
- `monkeypatch` for env var isolation
- `pytest.mark.slow` for Docker-dependent tests (Postgres loader)
- `threading.Thread` for blocking-wait tests (ask_user, plans)
- `pyarrow` required for parquet writes in Python sandbox

---

## 10. Known Gaps (Layer 2 prerequisites)

These are documented gaps that need fixes before a real Layer 2 agent is built:

1. **`/tools/list` doesn't document the Python sandbox's `dataset` view name.** An agent reading the manifest has no way to know the view is called `dataset`. One-line manifest fix.

2. **Multi-file datasets only expose the primary table to the sandbox.** 9 of Lahman's 10 tables are invisible to `con` unless manually loaded from disk. Fix: load all `gold_*.parquet` as named views on bootstrap.

3. **`DESCRIBE` is rejected by `/tools/sql`.** Agents must use `information_schema.columns` as a workaround. Fix: add DESCRIBE to the allowed-statement regex.

4. **No render_spec contract in Layer 1.** The agent must carry the entire render_spec schema in its system prompt. Fix: either a typed `POST /renders` endpoint or a `render_spec_contract` section in `/tools/list`.

5. **Heuristic classifications don't flag the DCD at the dataset level.** No `profiler_mode` field. Fix: add `profiler_mode: llm | heuristic | mixed` to `DcdDataset`.

---

## 11. File Map

```
src/
├── __init__.py
├── main.py                          # FastAPI app, 58 routes, 12 routers
├── api/
│   ├── datasets.py                  # upload, schema, context, connect
│   ├── pipeline.py                  # Bronze→Silver→Gold orchestration
│   ├── tools.py                     # SQL + Python endpoints
│   ├── plans.py                     # plan state machine HTTP
│   ├── ask_user.py                  # human-in-the-loop HTTP
│   ├── memory.py                    # memory CRUD HTTP
│   ├── agent_tasks.py               # task lifecycle HTTP
│   ├── subagents.py                 # subagent lifecycle HTTP
│   ├── tool_discovery.py            # GET /tools/list manifest
│   ├── clarification.py             # profiling Q&A
│   ├── health.py                    # liveness
│   └── status.py                    # progress tracking
├── core/
│   ├── config.py                    # pydantic-settings
│   ├── state.py                     # AppState + rehydration
│   ├── database.py                  # DuckDB connection factory
│   ├── llm.py                       # OpenRouter client with retry
│   ├── memory.py                    # SQLite-backed memory store
│   ├── plans.py                     # Plan state machine + SQLite audit
│   ├── agent_tasks.py               # per-session task store
│   ├── ask_user.py                  # blocking question registry
│   ├── subagents.py                 # subagent workspace registry
│   ├── exceptions.py                # error hierarchy
│   ├── metrics.py                   # in-process counters
│   └── logger.py                    # structlog config
├── ingestion/
│   ├── base.py                      # LoadResult, validate_identifier, sanitize_for_identifier
│   ├── gateway.py                   # format detection + loader dispatch
│   ├── registry.py                  # DatasetRegistry (in-memory + disk rehydration)
│   ├── relationships.py             # FK detection via value containment
│   ├── csv_loader.py
│   ├── parquet_loader.py
│   ├── excel_loader.py
│   ├── json_loader.py
│   └── db_loader.py
├── profiling/
│   ├── agent.py                     # profile_dataset orchestrator
│   ├── classifier.py                # LLM classifier + heuristic fallback
│   ├── statistical.py               # per-column stats
│   ├── enricher.py                  # metric proposals
│   ├── clarification.py             # low-confidence question generator
│   └── hierarchy.py                 # functional-dependency detection
├── semantic/
│   ├── schema.py                    # DCD pydantic models
│   ├── generator.py                 # build_dcd()
│   ├── editor.py                    # user corrections
│   └── pruner.py                    # query-based column pruning
├── materialization/
│   ├── optimizer.py                 # Gold table creation + ENUM optimization
│   ├── summarizer.py                # temporal rollups + dimension breakdowns
│   ├── query_generator.py           # verified NL↔SQL pair generation
│   ├── quality.py                   # data quality suite
│   └── exporter.py                  # parquet + YAML persistence
├── tools/
│   ├── sql_tool.py                  # SQL validation + execution
│   └── python_session.py            # subprocess session manager
└── sandbox/
    └── repl.py                      # Python REPL worker (subprocess target)
```
