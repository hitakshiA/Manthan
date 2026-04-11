# Manthan Data Layer
## Engineering Specification & Product Requirements

```
Document ID    : MANTHAN-DL-001
Version        : 1.0
Status         : Draft
Author         : Manthan Engineering
License        : Apache 2.0
Last Updated   : 2026-04-11
```

---

## 1. Problem Context

NatWest's "Talk to Data" challenge requires a system where non-technical users ask natural language questions about any dataset and receive trustworthy, sourced, instant answers. The operative word is "any." The system cannot assume a fixed schema, a known domain, or a pre-configured database. Data arrives cold from unknown sources, and the system must understand it deeply enough that downstream analysis agents can query it with zero guesswork.

This document specifies the data layer that makes that possible. Everything upstream (the user interface) and downstream (the analysis agents) depends on the guarantees this layer provides.

### 1.1 What This Layer Must Guarantee to Downstream Agents

An analysis agent receiving a user question like "why did revenue drop last month" must have immediate, reliable answers to:

- What table contains revenue data, and what is the column called?
- Is "revenue" a raw column or a computed metric? What is the exact aggregation rule?
- What is the temporal grain? Daily? Monthly? What column holds the date?
- What dimensions can revenue be broken down by? Region? Product? Channel?
- Are there sensitive columns the agent must never expose in outputs?
- What date range does the data cover? Is the data fresh?
- Are there known quality issues (missing values, outliers, caveats)?
- What does a correct query look like? Are there verified examples?

If the agent has to guess any of these, the system fails. The data layer's job is to answer every one of them before the agent writes a single line of code.

### 1.2 Design Constraints from the Problem Statement

Derived directly from the hackathon transcripts and problem statement PDFs:

| Constraint | Source | Implication |
|---|---|---|
| "Any dataset" | Problem statement title | Source-agnostic ingestion |
| "Structured, unstructured" | Ravi, transcript | Support files and databases |
| "Self-service to aid re-use" | Problem statement | Data context must travel with the dataset |
| "Consistent metrics" | Learning outcomes | Semantic layer with canonical definitions |
| "No exposure of private data" | Core description | Agent output discipline: never enumerate ``identifier`` columns in answers (see §6) |
| "Source transparency" | Trust pillar | Full provenance chain from question to column |
| "Near instant responses" | Speed pillar | Pre-computed summaries for common patterns |
| "Free-tier AI" | Hackathon rules | LLM calls must be economical, cacheable |
| "Apache 2.0 compatible" | Submission guidelines | All dependencies MIT or Apache 2.0 |

---

## 2. Architectural Decisions

Each decision follows the ADR format: context, decision, consequences.

### ADR-001: DuckDB as the Analytical Engine

**Context.** The system needs an analytical query engine that handles CSV/Excel/JSON/Parquet ingestion, provides SQL for structured queries, interoperates with pandas for code execution, requires zero infrastructure, and runs embedded in a Python process.

**Decision.** Use DuckDB (MIT license) as the single analytical engine for ingestion, profiling, storage, and SQL query serving.

**Rationale.**
- Reads CSV, Excel (via spatial extension), JSON, Parquet natively with auto type inference
- Columnar storage with vectorized execution: 5x faster than pandas on grouped aggregations at 100M rows
- Zero-copy Arrow interop: `.df()` returns pandas, `.pl()` returns Polars, `.arrow()` returns PyArrow
- `SUMMARIZE` command provides instant profiling (min, max, mean, stddev, quartiles, nulls, unique count)
- `COMMENT ON` attaches descriptions directly to tables and columns in the catalog
- `ENUM` types enforce categorical constraints
- Single-file database, no server process, embeds in any Python application
- Morsel-driven parallelism saturates all CPU cores automatically
- Zone maps on every row group enable predicate pushdown without manual indexing
- Database scanner extensions for PostgreSQL, MySQL, SQLite when connecting to external sources

**Consequences.**
- Single-writer limitation: only one process can open a `.duckdb` file in write mode. Mitigated by Parquet export for sandbox access.
- Not suitable for transactional workloads (OLTP). Application state (sessions, chat history) uses a separate SQLite instance.
- Schema evolution requires explicit ALTER TABLE. Mitigated by treating each upload as a new dataset rather than appending to existing tables.

### ADR-002: Parquet as the Interchange Format

**Context.** Analysis agents execute Python code in a Docker sandbox. The sandbox needs access to the dataset without holding a write lock on the DuckDB file. Data must be portable, compressed, and queryable from inside the container.

**Decision.** After ingestion and profiling, export the curated dataset to Parquet with Zstandard compression. Mount the Parquet file into the Docker sandbox. DuckDB inside the sandbox queries it directly via `read_parquet()`.

**Rationale.**
- Parquet is columnar, self-describing, and universally supported (Apache 2.0)
- Zstandard compression yields 5-10x reduction from raw CSV
- DuckDB reads Parquet with predicate pushdown against row group statistics
- No locking conflicts: Parquet files are immutable once written
- Portable: same file works across DuckDB, pandas, Polars, Spark
- Row group statistics (min/max/null count) enable query planning without full scans

**Consequences.**
- Data duplication: same data exists in both DuckDB (for the API server) and Parquet (for the sandbox). Acceptable for dataset sizes under 1GB. At scale, shared object storage with Arrow Flight would replace this.
- Parquet files are immutable. If the user updates the semantic layer, the Parquet is re-exported. This is fast for hackathon-scale data.

### ADR-003: Progressive Refinement via Bronze-Silver-Gold

**Context.** Raw uploaded data is messy. Agents need clean, annotated, optimized data. The transformation cannot happen in one monolithic step because each stage produces artifacts other stages depend on (profiling stats feed into semantic classification, which feeds into storage optimization).

**Decision.** Apply a three-stage refinement model inspired by the medallion architecture, adapted for single-dataset agent workloads:

| Stage | Name | What Happens | Artifact Produced |
|---|---|---|---|
| Bronze | Raw Capture | Ingest source file as-is into DuckDB with metadata columns | `raw_{dataset}` table |
| Silver | Profiled & Annotated | Statistical profiling, type classification, PII detection, LLM-powered semantic annotation | Data Context Document (YAML) |
| Gold | Agent-Ready | Sort by key dimensions, create ENUMs, attach COMMENTs, build summary tables, generate verified queries, export Parquet | `{dataset}` table + `{dataset}_summary` + Parquet + verified queries JSON |

**Rationale.**
- Each stage is independently testable and retriable
- Bronze preserves the raw data for audit and re-processing
- Silver can be re-run if the LLM produces poor annotations (retry with different prompt)
- Gold is optimized specifically for the query patterns agents will use
- Artifacts at each stage serve different consumers: Bronze for debugging, Silver for the semantic layer, Gold for agent tools

**Consequences.**
- Three copies of the data at different stages. For hackathon scale (sub-1M rows), storage cost is negligible. At production scale, Bronze could be archived to cold storage after Gold is materialized.
- Additional complexity versus a single-pass pipeline. Justified by the debugging and retry benefits.

### ADR-004: Data Context Document as the Semantic Contract

**Context.** Downstream agents need a machine-readable artifact that describes everything about a dataset: what columns mean, how to aggregate them, what's sensitive, what the temporal structure is. This artifact must be auto-generated but human-editable, must travel with the dataset, and must be the single source of truth for all agent queries.

**Decision.** Define a YAML-based Data Context Document (DCD) that encodes the complete semantic understanding of a dataset. The DCD is auto-generated by the Profiling Agent (Silver stage) and finalized after interactive user refinement.

**Structure:**

```yaml
# manthan-context.yaml
version: "1.0"
dataset:
  id: "ds_a1b2c3"
  name: "NexaRetail Sales"
  description: "Transaction-level e-commerce sales data across 4 regions"
  source:
    type: "csv"
    original_filename: "sales_data.csv"
    ingested_at: "2026-04-11T14:30:00Z"
    row_count: 1500000
    raw_size_bytes: 245000000

  temporal:
    grain: "daily"
    column: "order_date"
    range:
      start: "2024-01-01"
      end: "2026-03-31"
    timezone: "UTC"

  columns:
    - name: "order_date"
      dtype: "DATE"
      role: "temporal"
      description: "Date when the order was placed"
      nullable: false
      completeness: 1.0

    - name: "revenue"
      dtype: "DOUBLE"
      role: "metric"
      description: "Total order amount in USD, excludes returns processed after 30 days"
      aggregation: "SUM"
      format: "currency_usd"
      nullable: false
      completeness: 1.0
      stats:
        min: 0.50
        max: 24999.99
        mean: 142.37
        median: 89.50
        stddev: 203.14
        p25: 45.00
        p75: 178.00

    - name: "region"
      dtype: "VARCHAR"
      role: "dimension"
      description: "Geographic sales region"
      cardinality: 4
      values: ["North", "South", "East", "West"]
      distribution:
        North: 0.28
        South: 0.25
        East: 0.24
        West: 0.23

    - name: "customer_name"
      dtype: "VARCHAR"
      role: "identifier"
      description: "Customer full name"
      sensitivity: "pii"
      pii_type: "PERSON"
      handling: "never_expose_in_outputs"
      completeness: 0.87
      quality_note: "13% of records have missing names"

    - name: "customer_email"
      dtype: "VARCHAR"
      role: "identifier"
      description: "Customer email address"
      sensitivity: "pii"
      pii_type: "EMAIL_ADDRESS"
      handling: "never_expose_in_outputs"

  computed_metrics:
    - name: "average_order_value"
      formula: "SUM(revenue) / COUNT(DISTINCT order_id)"
      description: "Average revenue per unique order"
      depends_on: ["revenue", "order_id"]

    - name: "order_count"
      formula: "COUNT(DISTINCT order_id)"
      description: "Number of unique orders"
      depends_on: ["order_id"]

  relationships: []

  quality:
    overall_score: 0.92
    freshness:
      last_record_date: "2026-03-31"
      expected_frequency: "daily"
      status: "fresh"
    completeness:
      fully_complete_columns: 14
      partial_columns: 2
      details:
        - column: "customer_name"
          completeness: 0.87
          note: "13% missing, concentrated in online channel"
    known_limitations:
      - "Revenue excludes returns processed after 30 days"
      - "South region data prior to 2024-03 may have duplicate orders from migration"
    validation_rules:
      - "revenue >= 0"
      - "order_date BETWEEN '2024-01-01' AND CURRENT_DATE"
      - "region IN ('North', 'South', 'East', 'West')"

  verified_queries:
    - question: "What is total revenue by region?"
      sql: "SELECT region, SUM(revenue) as total_revenue FROM nexaretail_sales GROUP BY region ORDER BY total_revenue DESC"
      intent: "breakdown"

    - question: "How has monthly revenue changed over time?"
      sql: "SELECT DATE_TRUNC('month', order_date) as month, SUM(revenue) as monthly_revenue FROM nexaretail_sales GROUP BY 1 ORDER BY 1"
      intent: "trend"

    - question: "What is this week vs last week revenue?"
      sql: "SELECT CASE WHEN order_date >= CURRENT_DATE - INTERVAL '7 days' THEN 'this_week' ELSE 'last_week' END as period, SUM(revenue) as revenue FROM nexaretail_sales WHERE order_date >= CURRENT_DATE - INTERVAL '14 days' GROUP BY 1"
      intent: "comparison"

  agent_instructions:
    - "Always aggregate revenue using SUM, never AVG unless computing average_order_value"
    - "When user says 'last month', resolve to the calendar month immediately preceding today"
    - "Never include customer_name or customer_email in query outputs"
    - "When breaking down metrics, try region first, then product_category, then channel"
    - "Surface data quality warnings for columns with completeness < 0.95"
```

**Rationale.**
- YAML is human-readable and LLM-parseable
- The structure mirrors Snowflake's semantic model spec and dbt's MetricFlow YAML, proven patterns at enterprise scale
- `agent_instructions` is a novel addition: natural language directives that get injected into the analysis agent's system prompt, acting as the dataset's own "system prompt"
- `verified_queries` follow the Verified Query Repository pattern (Snowflake Cortex Analyst) that demonstrably improves text-to-SQL accuracy
- `quality` section gives agents the trust metadata they need to surface caveats
- `sensitivity` classification integrates with the output filtering layer
- The entire file is portable: move it with the Parquet file and any DuckDB instance can reconstruct the full context

**Consequences.**
- YAML can become verbose for datasets with 100+ columns. Mitigated by agent tools that query the DCD programmatically rather than injecting the entire file into prompts. Schema-pruning retrieves only relevant column definitions per query.
- Manual edits to the YAML could break schema validation. Mitigated by a validation step that checks DCD against the actual DuckDB schema before agents use it.

### ADR-005: Profiling Agent Architecture

**Context.** The Silver stage requires an autonomous agent that explores uploaded data, detects semantic types, identifies PII, proposes computed metrics, and generates the Data Context Document. This agent must work iteratively (like Claude Code: plan → execute → observe → refine) and ask the user clarifying questions when it encounters ambiguity.

**Decision.** Implement the Profiling Agent as a ReAct-loop agent with four tool capabilities:

| Tool | Purpose | Implementation |
|---|---|---|
| `execute_sql` | Run DuckDB queries against the raw table | DuckDB Python API |
| `profile_columns` | Get statistical profiles for all or specific columns | ydata-profiling `to_json()` or DuckDB `SUMMARIZE` |
| `detect_pii` | Scan column values for personally identifiable information | Microsoft Presidio `AnalyzerEngine` |
| `ask_user` | Present a question to the user and wait for a response | API callback to the frontend |

**Agent Loop (Silver Stage):**

```
1. PERCEIVE
   - execute_sql: SELECT * FROM information_schema.columns
   - execute_sql: SUMMARIZE raw_{dataset}
   - execute_sql: SELECT * FROM raw_{dataset} LIMIT 20
   → Agent now has: column names, types, basic stats, sample values

2. CLASSIFY
   - For each column, the LLM classifies:
     role: metric | dimension | temporal | identifier | auxiliary
     Inputs: column name, dtype, cardinality, sample values, stats
   - detect_pii: scan sample values of string columns
   → Agent now has: role assignments and PII flags

3. DISAMBIGUATE
   - Identify low-confidence classifications
     (short column names, ambiguous types, multiple possible roles)
   - ask_user: targeted questions with context
     "Column 'amt' (numeric, min=0.50, max=24999.99, mean=142.37)
      — is this a revenue/sales amount, a quantity, or something else?"
   → Agent now has: user-confirmed classifications

4. ENRICH
   - Propose computed metrics based on column relationships
     (If revenue and order_id exist → propose average_order_value)
   - Generate natural language descriptions for each column
   - Detect temporal grain (daily/weekly/monthly) from date column gaps
   - Identify natural dimension hierarchies
   → Agent now has: enriched semantic understanding

5. VALIDATE
   - Cross-check: do metric aggregation rules make sense?
   - Cross-check: are all PII columns flagged?
   - Cross-check: does the temporal range look reasonable?
   - Generate data quality validation rules
   → Agent now has: validated, complete understanding

6. EMIT
   - Generate the Data Context Document (YAML)
   - Present summary to user for final confirmation
   → DCD is finalized
```

**Rationale.**
- The ReAct loop mirrors how Claude Code explores a codebase: gather context → form hypotheses → execute → observe → iterate. This is the proven pattern for autonomous exploration of unknown structures.
- Separating PERCEIVE from CLASSIFY allows the profiling stats to be computed once (using ydata-profiling or DuckDB SUMMARIZE) and reused across all classification decisions.
- The DISAMBIGUATE step (interactive clarification) is the largest differentiation point. No existing open-source tool implements agent-driven data clarification.
- Using four discrete tools rather than free-form code execution keeps the agent constrained and auditable. Every action is one of four types, making the exploration traceable.
- The LLM is called for classification and description generation, not for SQL generation. SQL is deterministic (SUMMARIZE, information_schema queries). This keeps LLM usage minimal and reduces hallucination risk.

**Consequences.**
- The agent loop requires multiple LLM calls (classification, description generation, disambiguation). For a 20-column dataset, expect 3-5 LLM calls total. Using free-tier models via OpenRouter, this is zero cost.
- Interactive clarification (ask_user) introduces a blocking step. The agent must be designed to ask all questions in a single batch rather than one at a time, to minimize user friction.
- The agent may produce poor classifications on unusual datasets. Mitigated by the user confirmation step at the end, and by the ability to re-run the Silver stage with corrected inputs.

---

## 3. Gold Stage: Agent-Ready Materialization

After the DCD is finalized, the Gold stage transforms the raw table into an optimized, annotated dataset that agents can query at maximum speed with full semantic context.

### 3.1 Table Optimization

**Sort Order.** The table is re-created with `ORDER BY` on the primary dimension columns (lowest cardinality first) followed by the temporal column. This maximizes zone map effectiveness for the most common agent query pattern: `WHERE dimension = X AND date BETWEEN Y AND Z`.

```sql
CREATE TABLE {dataset} AS
  SELECT * FROM raw_{dataset}
  ORDER BY {lowest_cardinality_dimension}, {temporal_column};
```

The sort order is determined from the DCD: columns with `role: dimension` sorted by ascending cardinality, then the column with `role: temporal`.

**ENUM Types.** Categorical dimension columns with cardinality < 100 are converted to DuckDB ENUM types. This compresses storage, enforces valid values, and makes equality comparisons faster.

```sql
CREATE TYPE {column}_enum AS ENUM (
  SELECT DISTINCT {column} FROM raw_{dataset} ORDER BY {column}
);
ALTER TABLE {dataset} ALTER COLUMN {column} TYPE {column}_enum;
```

**Schema Comments.** Every table and column receives a `COMMENT ON` statement populated from the DCD descriptions. This makes the schema self-documenting at the database level, accessible via `information_schema.columns.comment`.

```sql
COMMENT ON TABLE {dataset} IS '{dataset.description}';
COMMENT ON COLUMN {dataset}.{column} IS '{column.description}';
```

### 3.2 Summary Tables

Pre-computed summary tables accelerate the most common agent query patterns. The Profiling Agent generates these based on the DCD's column roles:

**Temporal rollups.** For each metric column, aggregate at multiple temporal grains:

```sql
CREATE TABLE {dataset}_daily AS
  SELECT {temporal_column},
         {for each dimension: dimension_column,}
         {for each metric: SUM/AVG(metric) as metric_name,}
         COUNT(*) as record_count
  FROM {dataset}
  GROUP BY ALL;

CREATE TABLE {dataset}_monthly AS
  SELECT DATE_TRUNC('month', {temporal_column}) as month,
         {for each dimension: dimension_column,}
         {for each metric: SUM/AVG(metric) as metric_name,}
         COUNT(*) as record_count
  FROM {dataset}
  GROUP BY ALL;
```

The granularities created depend on the temporal grain detected: if the source is daily, create daily and monthly summaries. If weekly, create weekly and monthly. Always create at least one level of rollup.

**Dimension breakdowns.** For each dimension column, a summary table with all metrics aggregated:

```sql
CREATE TABLE {dataset}_by_{dimension} AS
  SELECT {dimension},
         {for each metric: SUM/AVG(metric) as metric_name,}
         COUNT(*) as record_count,
         ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct_of_total
  FROM {dataset}
  GROUP BY {dimension}
  ORDER BY {primary_metric} DESC;
```

Summary tables are named with a clear convention (`{dataset}_{grain}` or `{dataset}_by_{dimension}`) and documented in the DCD under a `summary_tables` section.

### 3.3 Parquet Export

The Gold table and all summary tables are exported as Parquet files into a dataset directory:

```
/data/{dataset_id}/
  ├── manthan-context.yaml          # Data Context Document
  ├── verified-queries.json         # Few-shot examples for agents
  ├── data/
  │   ├── {dataset}.parquet         # Main curated table
  │   ├── {dataset}_daily.parquet   # Daily summary
  │   ├── {dataset}_monthly.parquet # Monthly summary
  │   └── {dataset}_by_{dim}.parquet # Dimension breakdowns
  └── metadata/
      ├── profile.json              # ydata-profiling output
      └── quality.json              # Validation results
```

This directory is the atomic unit of a Manthan dataset. It is self-contained: copy the directory anywhere, mount it into a Docker container, and any DuckDB instance can reconstruct the full agent-queryable dataset by reading the Parquet files and the DCD.

### 3.4 Verified Query Generation

The system auto-generates 8-12 verified question-SQL pairs covering the four use case types from the NatWest problem statement:

| Use Case | Template Questions |
|---|---|
| Change Analysis | "Why did {metric} change in {recent_period}?", "What drove the change in {metric}?" |
| Comparison | "{dim_value_1} vs {dim_value_2} {metric}", "{period_1} vs {period_2}" |
| Breakdown | "What makes up total {metric}?", "Breakdown of {metric} by {dimension}" |
| Summary | "Weekly summary of key metrics", "What happened this month?" |

Template variables are populated from the DCD (metric names, dimension values, date ranges). The SQL for each is generated deterministically from the schema, not by the LLM, ensuring correctness. These pairs are stored in `verified-queries.json` and served to analysis agents as few-shot examples.

---

## 4. Agent Tool Interface

The data layer exposes four tools to downstream analysis agents. These are the only interface through which agents access data.

### 4.1 Tool: `get_context`

Returns the Data Context Document for a dataset, or a pruned subset relevant to a specific query.

```
Input:  dataset_id: str
        query: str (optional, for schema pruning)
Output: YAML string (full DCD or relevant subset)
```

When `query` is provided, the tool uses keyword matching against column descriptions and names to return only the relevant columns, reducing prompt token usage. For datasets with <30 columns, returns the full DCD.

### 4.2 Tool: `run_sql`

Executes a read-only SQL query against the DuckDB database and returns results.

```
Input:  dataset_id: str
        sql: str
        max_rows: int (default 1000)
Output: {
          columns: [str],
          rows: [[any]],
          row_count: int,
          truncated: bool,
          execution_time_ms: float
        }
```

Guardrails:
- Read-only: only SELECT statements allowed. DDL/DML rejected at parse time.
- Row limit: results truncated to `max_rows` with a `truncated` flag.
- Timeout: queries killed after 30 seconds.
- Column validation: every table and column referenced in the SQL is checked against the DuckDB catalog before execution.

### 4.3 Tool: `run_python`

Executes Python code in the Docker sandbox with the dataset available as Parquet files.

```
Input:  dataset_id: str
        code: str
        timeout_seconds: int (default 60)
Output: {
          stdout: str,
          stderr: str,
          files_created: [{name: str, path: str, size: int}],
          execution_time_ms: float,
          exit_code: int
        }
```

The sandbox container is pre-configured with:
- Python 3.12+ with: duckdb, pandas, numpy, plotly, matplotlib, scipy, scikit-learn, faker
- Dataset Parquet files mounted at `/data/`
- A prelude script that auto-loads the dataset:
  ```python
  import duckdb
  con = duckdb.connect()
  df = con.sql("SELECT * FROM read_parquet('/data/*.parquet')").df()
  ```
- Write access to `/output/` for saving charts and results
- No network access (security isolation)
- Memory limit: 2GB
- CPU limit: 2 cores

Files created in `/output/` are returned to the API server and made available to the frontend (charts, exported CSVs, etc).

### 4.4 Tool: `get_schema`

Returns lightweight schema information without the full DCD. Used by agents for quick reference.

```
Input:  dataset_id: str
Output: {
          tables: [{
            name: str,
            description: str,
            row_count: int,
            columns: [{
              name: str,
              dtype: str,
              role: str,
              description: str,
              sensitivity: str | null
            }]
          }],
          summary_tables: [str],
          verified_queries: [{question: str, sql: str, intent: str}]
        }
```

---

## 5. Multi-Source Handling

### 5.1 Database Connections

For PostgreSQL, MySQL, and SQLite connections, the ingestion gateway uses DuckDB's scanner extensions to pull data into the local DuckDB instance:

```sql
INSTALL postgres;
LOAD postgres;
ATTACH 'postgresql://user:pass@host/db' AS source (TYPE postgres, READ_ONLY);
CREATE TABLE raw_{table} AS SELECT * FROM source.{schema}.{table};
```

The connection string is provided by the user and never stored (only the resulting data persists). For multi-table databases, the user selects which tables to import. Foreign key relationships detected via `information_schema.table_constraints` are stored in the DCD's `relationships` section.

### 5.2 File Format Handling

| Format | Handling | Edge Cases |
|---|---|---|
| CSV | `read_csv(path, auto_detect=true, sample_size=10000)` | Multi-encoding, mixed delimiters, quoted fields with newlines |
| Excel | `INSTALL spatial; LOAD spatial; read_xlsx(path)` | Multiple sheets (user selects or imports all as separate tables), merged cells |
| JSON | `read_json(path, auto_detect=true)` | Nested objects (flattened to columns), arrays (exploded to rows) |
| Parquet | `read_parquet(path)` | Already optimized, minimal processing needed |

### 5.3 Multi-Table Datasets

When multiple tables are loaded (multi-file upload or database import), the DCD includes:
- A `tables` section listing all tables with their column schemas
- A `relationships` section encoding foreign key and join relationships
- Verified queries that demonstrate joins across tables
- Agent instructions specifying default join paths

---

## 6. Output Discipline for Sensitive Columns

The problem statement calls for "no exposure of private or sensitive data"
in agent outputs. Rather than treating this as a runtime PII-scanning
problem, Manthan treats it as an **agent output-discipline** problem
anchored on column role classification.

### Rule

The Silver-stage LLM classifier assigns each column a ``role``:
``metric``, ``dimension``, ``temporal``, ``identifier``, ``auxiliary``.
When a column is marked ``identifier`` (unique-ish keys such as
``customer_name``, ``customer_email``, ``order_id``, ``account_number``),
the downstream analysis agent **must not enumerate individual values**
in its answers. It may aggregate (``COUNT(DISTINCT identifier)``),
group other metrics by it, or look up a single value when the user
explicitly asks — but it must not list them.

This rule is injected into the DCD's ``agent_instructions`` section at
materialization time, e.g.:

> "Never enumerate individual values of identifier columns
> (customer_email, customer_name, order_id). Aggregate (COUNT DISTINCT,
> GROUP BY dimension) or reference them only when the user explicitly
> asks for a lookup."

### Why not Presidio / runtime PII scanning

Two reasons:

1. The NatWest hackathon rules require teams to **use synthetic data
   only** and not scrape real PII. There is no real PII to detect on
   uploads during the hackathon; runtime entity scanning would be
   theatre.
2. Third-party PII scanners (Presidio + spaCy NER) produce noisy false
   positives on legitimate dimension columns — e.g. "North" / "South"
   / "East" / "West" get flagged as LOCATION entities. Labels that
   produce noise erode trust and get ignored.

### Datasets with truly sensitive data (post-hackathon)

If a deployment does accept real-world data containing PII, the
enforcement layer is the analysis agent's output filter plus a SQL tool
guardrail that rejects ``SELECT`` clauses referencing ``identifier``
columns unless the user explicitly opted in. Both extensions are local
to ``src/tools/sql_tool.py`` and the (future) analysis agent system
prompt. The DCD already carries the classifications needed to drive
them — no additional detection pipeline is required.

---

## 7. Scalability Architecture

### 7.1 Current State (Hackathon)

Single-process Python application. DuckDB runs in-process. Docker container started on-demand for Python execution. One dataset active at a time. Single user.

### 7.2 Growth Path

**Multi-dataset.** Each dataset gets its own DuckDB file and Parquet directory under `/data/{dataset_id}/`. The API server maintains a registry of loaded datasets and routes queries to the correct DuckDB instance. DCD files provide dataset-level isolation.

**Multi-user / Multi-tenant.** DuckDB instances are per-session. Each user session gets its own in-memory DuckDB that attaches to the relevant Parquet files as read-only views. No shared write state between sessions. Session metadata (chat history, user preferences) lives in a separate SQLite database.

**Larger datasets (10M+ rows).** DuckDB's buffer manager handles spill-to-disk automatically when data exceeds RAM. Parquet files support predicate pushdown at the row group level, so queries that filter on sorted columns scan only relevant row groups. Summary tables provide sub-second responses for aggregation queries regardless of raw table size.

**Concurrent agent access.** Multiple analysis agents reading the same dataset open separate DuckDB connections against the same Parquet files. Parquet's immutable nature means no read locks or contention. Each agent's sandbox is an isolated Docker container with its own DuckDB process.

**Cloud deployment.** Parquet files move to S3/GCS. DuckDB's `httpfs` extension reads remote Parquet directly with predicate pushdown. The API server becomes stateless (no local DuckDB files), enabling horizontal scaling behind a load balancer. The DCD travels with the Parquet files in the same bucket prefix.

### 7.3 What We Explicitly Do Not Build Now

- Real-time streaming ingestion (CDC from live databases)
- Incremental refresh / append to existing datasets
- Cross-dataset joins and federation
- Role-based access control and column-level masking
- Data versioning / time travel
- Distributed query execution

These are documented as future capabilities, not limitations. The architecture supports them without redesign: the DCD's `relationships` section accommodates cross-dataset joins, the Parquet directory structure supports partitioned incremental writes, and the tool interface already separates read from write operations.

---

## 8. Dependency Matrix

| Package | Version | License | Purpose | Criticality |
|---|---|---|---|---|
| duckdb | >=1.2.0 | MIT | Analytical engine, ingestion, SQL | Core |
| ydata-profiling | >=4.18.0 | MIT | Statistical profiling, JSON export | Silver stage |
| great-expectations | >=1.4.0 | Apache 2.0 | Data quality validation rules | Gold stage |
| pyyaml | >=6.0 | MIT | DCD serialization/deserialization | All stages |
| fastapi | >=0.115.0 | MIT | API server | Tool interface |
| uvicorn | >=0.34.0 | BSD-3 | ASGI server | Tool interface |
| docker | >=7.0 | Apache 2.0 | Python sandbox management | Tool interface |
| httpx | >=0.28.0 | BSD-3 | OpenRouter API calls | Silver stage |
| pandas | >=2.2.0 | BSD-3 | DataFrame interop | Silver stage, sandbox |
| plotly | >=6.0 | MIT | Visualization (in sandbox) | Sandbox |
| matplotlib | >=3.10.0 | PSF | Visualization (in sandbox) | Sandbox |
| scipy | >=1.14.0 | BSD-3 | Statistical tests (in sandbox) | Sandbox |

All licenses are Apache 2.0 compatible. No GPL, AGPL, or SSPL dependencies.

---

## 9. Data Flow Lifecycle

Complete lifecycle of a dataset from upload to agent query:

```
USER UPLOADS FILE
       │
       ▼
[1] INGESTION GATEWAY
    ├── Detect source type (CSV/Excel/JSON/Parquet/DB)
    ├── Validate (size, encoding, minimum viability)
    ├── Load into DuckDB: CREATE TABLE raw_{dataset} AS FROM read_csv(...)
    ├── Record metadata: source type, filename, timestamp, row count
    └── Emit: raw table in DuckDB
       │
       ▼
[2] PROFILING AGENT (Silver Stage)
    ├── PERCEIVE
    │   ├── SUMMARIZE raw_{dataset}
    │   ├── SELECT * FROM information_schema.columns
    │   └── SELECT * FROM raw_{dataset} LIMIT 20
    ├── CLASSIFY
    │   ├── LLM call: classify each column (role, description, aggregation)
    │   └── Presidio: scan string columns for PII entities
    ├── DISAMBIGUATE
    │   ├── Identify low-confidence columns
    │   └── ask_user: batch of targeted questions
    ├── ENRICH
    │   ├── Propose computed metrics from column relationships
    │   ├── Detect temporal grain from date gaps
    │   └── Generate quality validation rules
    ├── VALIDATE
    │   └── Cross-check all classifications for consistency
    └── EMIT
        └── Data Context Document (manthan-context.yaml)
       │
       ▼
[3] MATERIALIZATION ENGINE (Gold Stage)
    ├── Create sorted table: ORDER BY dimensions, temporal
    ├── Create ENUM types for low-cardinality dimensions
    ├── Attach COMMENT ON for all tables and columns
    ├── Build summary tables (daily, monthly, by-dimension)
    ├── Generate verified queries (8-12 pairs)
    ├── Export all tables to Parquet with Zstd compression
    ├── Run Great Expectations validation suite
    └── Write dataset directory: /data/{dataset_id}/
       │
       ▼
[4] DATASET READY
    ├── API server registers dataset in active registry
    ├── Tools available: get_context, run_sql, run_python, get_schema
    └── Analysis agents can now query with zero guesswork
```

---

## 10. API Surface

### 10.1 Dataset Management

```
POST   /datasets/upload          Upload file, trigger ingestion + profiling
POST   /datasets/connect         Connect to external database
GET    /datasets                 List all datasets
GET    /datasets/{id}            Get dataset metadata and status
GET    /datasets/{id}/context    Get the Data Context Document
PUT    /datasets/{id}/context    Update DCD after user edits
DELETE /datasets/{id}            Remove dataset and all artifacts
GET    /datasets/{id}/status     Profiling agent progress (websocket)
```

### 10.2 Agent Tools (internal, called by analysis agents)

```
POST   /tools/sql                Execute SQL against a dataset
POST   /tools/python             Execute Python in sandbox
GET    /tools/schema/{id}        Get schema summary
GET    /tools/context/{id}       Get DCD (optionally pruned by query)
```

### 10.3 Interactive Clarification

```
GET    /clarification/{id}       Get pending questions from profiling agent
POST   /clarification/{id}       Submit user answers
```

During the Silver stage, the profiling agent may emit questions via the clarification endpoint. The frontend polls or subscribes (websocket) and presents them to the user. Once answered, the agent resumes processing.

---

## 11. Error Handling and Recovery

| Failure | Detection | Recovery |
|---|---|---|
| Corrupt or unreadable file | DuckDB read_csv throws exception | Return clear error: "File could not be parsed. Check encoding and format." |
| LLM API timeout | httpx timeout after 30s | Retry up to 3 times with exponential backoff. If all fail, generate DCD with statistical data only (no descriptions). |
| LLM produces invalid classification | YAML validation against schema | Re-prompt with error context. If fails again, default to conservative classification (VARCHAR → dimension, DOUBLE → metric). |
| PII detection false positive | User overrides during clarification | Update DCD, re-run Gold stage without PII flag on that column. |
| Sandbox container crash | Docker health check, non-zero exit code | Return stderr to agent. Agent can modify code and retry. |
| DuckDB out of memory | DuckDB error code | Enable spill-to-disk via `SET temp_directory='/tmp/duckdb'`. Re-run query. |
| Parquet export failure | File system error | Retry. If persistent, check disk space and permissions. |

---

## 12. Observability

### 12.1 Metrics to Track

- **Ingestion**: files processed, rows ingested, time per file, failure rate by format
- **Profiling**: LLM calls per dataset, token usage, profiling time, clarification questions asked
- **Materialization**: Parquet file sizes, summary table row counts, export time
- **Agent Tools**: queries per dataset, execution time distribution, error rate, sandbox container lifetime
- **Data Quality**: validation pass/fail rate per dataset, completeness scores

### 12.2 Logging

Structured JSON logging at every stage transition:

```json
{
  "timestamp": "2026-04-11T14:30:00Z",
  "stage": "silver",
  "step": "classify",
  "dataset_id": "ds_a1b2c3",
  "columns_classified": 16,
  "pii_columns_detected": 2,
  "llm_tokens_used": 1847,
  "duration_ms": 3200
}
```

---

## 13. Testing Strategy

| Layer | Test Type | What It Validates |
|---|---|---|
| Ingestion | Unit | Each file format loads correctly, edge cases (empty files, unicode, mixed types) |
| Profiling | Integration | Given a known CSV, the profiling agent produces a DCD matching expected column roles |
| PII Detection | Unit | Known PII values are detected, known non-PII values are not flagged |
| Materialization | Integration | Summary tables contain correct aggregations, Parquet files are readable |
| Agent Tools | Integration | run_sql returns correct results, run_python sandbox starts and executes |
| DCD Validation | Unit | Generated YAML parses correctly, all required fields present |
| End-to-End | System | Upload CSV → profiling completes → DCD generated → agent queries return correct answers |

Test data: a curated synthetic dataset (NexaRetail) with known answers for each use case type, designed to exercise all column roles, PII patterns, and edge cases.

---

## 14. Glossary

| Term | Definition |
|---|---|
| DCD | Data Context Document. The YAML file encoding complete semantic understanding of a dataset. |
| Bronze | Raw ingested data, unmodified from source. |
| Silver | Profiled and annotated data with semantic classifications. |
| Gold | Agent-optimized data with sort order, ENUMs, comments, summaries, and verified queries. |
| Zone Map | Min/max statistics per column per row group. Used by DuckDB for predicate pushdown. |
| Verified Query | A known-correct question-SQL pair used as a few-shot example for analysis agents. |
| Profiling Agent | The autonomous agent that explores uploaded data and generates the DCD. |
| Sandbox | Isolated Docker container where agent-generated Python code executes against Parquet data. |
