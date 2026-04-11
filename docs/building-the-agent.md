# Building the Agent (Layer 2 integration guide)

This guide is for the engineer building **Layer 2** — the analysis
agent that sits on top of Manthan and answers natural-language
questions about data. Layer 1 (this repo) gives you a trustworthy
semantic foundation and a small set of sharp, composable tools. Your
job is to compose those tools to answer the four PDF use cases:
understand what changed, compare, break down, summarize.

This doc is opinionated about *how* the agent should think. You don't
have to follow it — the tools are general enough to support any
approach — but this is the shortest path from "I have Manthan running"
to "I have a working conversational analyst."

## The architecture you're building

```
┌───────────────────────────┐
│ Layer 3 — Chat UI         │  (your frontend, Round 3)
└──────────────┬────────────┘
               │ natural language
               ▼
┌───────────────────────────┐
│ Layer 2 — Analysis Agent  │  (what this doc helps you build)
│  - LLM with tool use      │
│  - Manthan tool bindings  │
│  - Narrative composer     │
└──────────────┬────────────┘
               │ HTTP / in-process calls
               ▼
┌───────────────────────────┐
│ Layer 1 — Manthan         │  (this repo)
│  - DCD + verified queries │
│  - SQL / Python tools     │
│  - Gold tables + Parquet  │
└───────────────────────────┘
```

## The tools you have

Layer 1 gives you four composable primitives and a few helpers.

### Core tools

- **`get_context(dataset_id, query?)`** — returns the DCD as YAML.
  When you pass a natural-language query, it prunes to the columns
  relevant to that query so you don't burn tokens on the full schema.
  Call this **first** on every user question.

- **`get_schema(dataset_id)`** — compact structural view. Cheaper
  than the full DCD. Use when you just need column names + roles +
  verified queries.

- **`run_sql(dataset_id, sql, session_id?)`** — read-only SQL execution
  against the Gold table. Accepts `SELECT`, `WITH`, `CREATE TEMP TABLE`,
  `CREATE TEMP VIEW`, `DROP TABLE/VIEW` (temp only). 30-second timeout.
  Returns columns, rows, row_count, truncation flag, execution time.
  **Use the temp-table scratchpad** to build up intermediate results
  across turns — it's the single biggest latency and reliability win
  you can make.

- **`run_python(dataset_id, code, session_id?)`** — stateful Python
  sandbox. Variables defined in turn N are still in scope in turn N+1
  when you pass the same `session_id`. Pre-loaded: `df` (pandas, the
  primary Gold table), `con` (DuckDB), `OUTPUT_DIR` (writable).
  Libraries: `pandas`, `numpy`, `scipy`, `sklearn`, `plotly`,
  `matplotlib`, `duckdb`. Use this for anything SQL can't express
  cleanly — statistical tests, clustering, custom attribution logic,
  chart generation.

### Helper endpoints

- **`GET /datasets/{id}/schema`** — same as `get_schema` but via HTTP.
- **`GET /datasets/{id}/context?query=...`** — same as `get_context`.
- **`GET /datasets/{id}/progress`** — poll pipeline progress events.
- **`WebSocket /datasets/{id}/status`** — live progress stream.
- **`GET /clarification/{id}`** — pending classifier clarification
  questions the user should answer before you commit to an interpretation.

## The agent's reasoning loop

For any user question, have your agent run this loop:

```
1. perceive  — pull pruned context for the question
2. plan      — pick one or more tools to use, in order
3. act       — call each tool, capture output
4. observe   — inspect results, decide if more work is needed
5. narrate   — compose a plain-language answer with source citations
```

The key insight: **don't try to generate one perfect SQL query**.
Build up the answer across multiple tool calls, using temp tables and
Python session state to pass results forward.

## How to answer each PDF use case

Here are agent pseudocode sketches for each of the four use cases.
These aren't optimal — they're the simplest thing that works. You
can refine them.

### Use case 1 — "Why did revenue drop last month?"

```python
async def answer_what_changed(dataset_id: str, user_question: str) -> str:
    # 1. perceive
    dcd = await manthan.get_context(dataset_id, query=user_question)
    temporal = dcd["dataset"]["temporal"]
    primary_metric = first_metric_column(dcd)
    primary_dimension = first_dimension_column(dcd)

    # 2. plan: we need baseline period vs current period, broken down
    #    by the primary dimension, then rank contributions.
    #    Ask the LLM to resolve "last month" → concrete date ranges
    #    against temporal.range.
    baseline_start, baseline_end, current_start, current_end = \
        await llm.resolve_period_pair(user_question, temporal["range"])

    # 3. act: stash each period as a temp table (SQL scratchpad)
    session_id = "sess_" + generate_id()

    await manthan.run_sql(dataset_id, f"""
        CREATE TEMP TABLE baseline AS
        SELECT "{primary_dimension}" AS dim,
               SUM("{primary_metric}") AS amount
        FROM {gold_table(dcd)}
        WHERE "{temporal['column']}" BETWEEN '{baseline_start}' AND '{baseline_end}'
        GROUP BY 1
    """)
    await manthan.run_sql(dataset_id, f"""
        CREATE TEMP TABLE current AS
        SELECT "{primary_dimension}" AS dim,
               SUM("{primary_metric}") AS amount
        FROM {gold_table(dcd)}
        WHERE "{temporal['column']}" BETWEEN '{current_start}' AND '{current_end}'
        GROUP BY 1
    """)

    # 4. act: compute contribution
    drivers = await manthan.run_sql(dataset_id, """
        SELECT c.dim, b.amount AS baseline, c.amount AS current,
               c.amount - b.amount AS delta,
               (c.amount - b.amount) / b.amount * 100 AS pct_change
        FROM baseline b JOIN current c USING (dim)
        ORDER BY ABS(c.amount - b.amount) DESC
    """)

    # 5. narrate
    biggest = drivers["rows"][0]
    total_before = sum(row[1] for row in drivers["rows"])
    total_after = sum(row[2] for row in drivers["rows"])
    overall_pct = (total_after - total_before) / total_before * 100

    return (
        f"{primary_metric} {'fell' if overall_pct < 0 else 'rose'} by "
        f"{abs(overall_pct):.1f}% from the baseline period to the current "
        f"period. The biggest contributor was {biggest[0]}, which moved "
        f"from {biggest[1]:.2f} to {biggest[2]:.2f} "
        f"(a {biggest[4]:+.1f}% change). "
        f"Source: gold table, columns {primary_metric} and {primary_dimension}, "
        f"filtered on {temporal['column']}."
    )
```

Three SQL calls, all using temp tables. No pre-baked driver tool
needed — the agent composed it from primitives. A judge seeing this
flow in a video demo knows the architecture works.

### Use case 2 — "Region A vs Region B revenue"

Simpler — one SQL call, one narration call:

```python
async def answer_comparison(dataset_id: str, user_question: str) -> str:
    dcd = await manthan.get_context(dataset_id, query=user_question)
    # Extract the two dimension values and the metric the user cares about.
    a, b, metric, dimension = await llm.extract_comparison(user_question, dcd)

    result = await manthan.run_sql(dataset_id, f"""
        SELECT "{dimension}", SUM("{metric}") AS total, COUNT(*) AS records
        FROM {gold_table(dcd)}
        WHERE "{dimension}" IN ('{a}', '{b}')
        GROUP BY 1
        ORDER BY total DESC
    """)
    return await llm.narrate_comparison(result["rows"], metric, dimension)
```

The LLM's job is just parameter extraction and narration. The hard
part (SQL) is one simple GROUP BY.

### Use case 3 — "What makes up total sales?"

Check the schema for a pre-aggregated summary table first:

```python
async def answer_breakdown(dataset_id: str, user_question: str) -> str:
    schema = await manthan.get_schema(dataset_id)
    metric, dimension = await llm.extract_breakdown(user_question, schema)

    # The Gold stage pre-builds gold_*_by_{dim}.parquet tables with
    # pct_of_total already computed. Check the summary_tables list
    # in the schema and use it if available.
    breakdown_table = f"gold_{dataset_name}_by_{dimension}"
    if breakdown_table in schema["summary_tables"]:
        result = await manthan.run_sql(dataset_id, f"""
            SELECT "{dimension}", "{metric}", pct_of_total
            FROM {breakdown_table}
            ORDER BY "{metric}" DESC LIMIT 10
        """)
    else:
        result = await manthan.run_sql(dataset_id, f"""
            SELECT "{dimension}", SUM("{metric}") AS total,
                   ROUND(SUM("{metric}") * 100.0 / SUM(SUM("{metric}")) OVER (), 2) AS pct_of_total
            FROM {gold_table(dcd)}
            GROUP BY 1
            ORDER BY total DESC LIMIT 10
        """)
    return await llm.narrate_breakdown(result["rows"], metric, dimension)
```

### Use case 4 — "Give me a weekly summary of customer metrics"

Use Python session state to compute week-over-week changes:

```python
async def answer_summary(dataset_id: str, user_question: str) -> str:
    dcd = await manthan.get_context(dataset_id, query=user_question)
    session_id = "sess_" + generate_id()

    # Step 1 — load the weekly rollup into pandas
    await manthan.run_python(dataset_id, session_id=session_id, code="""
        import duckdb
        weekly = con.execute(\"\"\"
            SELECT DATE_TRUNC('week', order_date) AS week, SUM(revenue) AS revenue,
                   COUNT(DISTINCT order_id) AS orders
            FROM dataset
            GROUP BY 1 ORDER BY 1
        \"\"\").df()
    """)

    # Step 2 — compute WoW change + anomaly flag, same session so 'weekly' is in scope
    result = await manthan.run_python(dataset_id, session_id=session_id, code="""
        weekly['revenue_wow'] = weekly['revenue'].pct_change()
        weekly['orders_wow'] = weekly['orders'].pct_change()
        latest = weekly.iloc[-1]
        baseline = weekly.iloc[:-1]
        revenue_anomaly = abs((latest['revenue'] - baseline['revenue'].mean()) /
                             baseline['revenue'].std()) > 2
        print(f"Week: {latest['week']}")
        print(f"Revenue: {latest['revenue']:,.0f} ({latest['revenue_wow']:+.1%} WoW)")
        print(f"Orders:  {latest['orders']:,} ({latest['orders_wow']:+.1%} WoW)")
        if revenue_anomaly: print("⚠ Revenue is ±2σ from baseline mean")
    """)

    return result["stdout"]
```

## Patterns you'll use a lot

### Caching via DCD fingerprint

Every tool response includes the DCD version. Cache your pruned
context by `dataset_id + user_question`; invalidate when the DCD
changes (e.g., after a user PUT-edits it via
`PUT /datasets/{id}/context`).

### Using temp tables as a scratchpad

When you're building a multi-step analysis, materialize each step
as a temp table. Temp tables live only in the current DuckDB
connection — they're cleaned up automatically. Name them with a
`scratch_` prefix so it's obvious they're yours.

```sql
CREATE TEMP TABLE scratch_january AS SELECT ... FROM gold_* WHERE ...;
CREATE TEMP TABLE scratch_february AS SELECT ... FROM gold_* WHERE ...;
SELECT j.region, j.total - f.total AS delta
FROM scratch_january j JOIN scratch_february f USING (region)
ORDER BY ABS(j.total - f.total) DESC;
```

### Using Python session state to build incrementally

Think of a Python session as a Jupyter notebook you're driving. Each
turn is one cell. Variables persist. Load the DataFrame once, slice
it ten times, save a chart at the end.

```python
# Turn 1
df_filtered = df[df.region == 'North']

# Turn 2 (same session_id)
monthly = df_filtered.resample('M', on='order_date').revenue.sum()

# Turn 3
import scipy.stats; z_scores = scipy.stats.zscore(monthly)

# Turn 4
outliers = monthly[abs(z_scores) > 2]
print(outliers)
```

### Citing sources

Every answer should reference the DCD (source of truth for
definitions) and the Gold table (source of truth for numbers). Use
the `provenance` block in every SQL result — it tells you which
columns and tables the query touched.

```python
f"...the answer above. Source: {provenance['tables_used']}, "
f"columns {provenance['columns_used']}."
```

### Respecting the identifier rule

**Never enumerate individual values of `role: identifier` columns in
your output.** Aggregate or count them instead. The DCD's
`agent_instructions` list includes this rule explicitly with the
identifier columns named. Inject those into your system prompt so the
LLM follows them consistently.

## Error handling

Layer 1 wraps errors into typed exceptions:

- `SqlValidationError` (HTTP 400) → your SQL is malformed. Show the
  error to the user and retry with a fix.
- `ToolError` (HTTP 500) → DuckDB couldn't execute. May be a timeout
  or a bad table reference. Retry with a simpler query.
- `ProfilingError` (HTTP 502) → the classifier LLM failed. Usually
  transient; retry with exponential backoff (Layer 1 already does
  this internally up to 3 times).
- `SandboxError` (HTTP 503) → the Python sandbox is unavailable.
  Fall back to SQL-only analysis if possible.

Agent responses should be best-effort. If one tool fails, don't give
up — try a different approach or narrate the partial answer.

## Testing your agent

Use Manthan's golden fixtures:

- `tests/fixtures/golden/retail_sales.csv` — 10-row retail sales
- `tests/fixtures/golden/hr_roster.csv` — 10-row HR roster
- `tests/fixtures/golden/marketing_funnel.csv` — 10-row funnel

Upload one of these, ask the four PDF questions, and verify the
agent's answers are correct. These datasets are small enough to
reason about by hand and complex enough to stress every primitive.

## When to change Layer 1 vs add to Layer 2

Rule of thumb:

- If you find yourself generating the same SQL template over and
  over (e.g., driver attribution), the template belongs in Layer 2
  — as a prompt pattern, not as a new Layer 1 endpoint. Layer 1
  keeps its primitives small and general.
- If you need a new kind of data to answer questions (e.g., the
  Gold table doesn't have a column you need), that's a Layer 1
  change — add to the Silver stage's column profiling or the Gold
  stage's summary tables.
- If you need a new sandbox capability (e.g., a new Python
  library), add it to `src/sandbox/requirements.txt` (affects the
  sandbox image, not the Python session — session uses host Python).
- If you need new semantic metadata (e.g., per-column business
  owner), add it to the DCD schema in `src/semantic/schema.py`.

## What Layer 1 does NOT give you

Things your agent has to handle itself:

- **Natural language parsing** — extracting entities (metrics,
  dimensions, time ranges) from user questions. Use your LLM.
- **Time phrase resolution** — "last month" → concrete date range.
  Use the `temporal.range` from the DCD to ground your LLM's
  interpretation.
- **Narrative composition** — turning SQL results into sentences.
  Use your LLM with a few-shot prompt.
- **Chart rendering** — do it in `run_python` via plotly or
  matplotlib, save to `/output`, return the file path.
- **User memory** — the DCD is stateless between users. If a user
  says "show me this month" and then "now compare it to Q4", you
  need to track conversation state yourself.
- **Authentication** — Layer 1 has no auth. Put it behind your own
  auth layer.
