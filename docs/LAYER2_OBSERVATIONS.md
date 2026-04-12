# Layer 2 Observations — What I Actually Had to Do as the Agent

**Context:** I (Claude) acted as the Layer 2 autonomous analyst agent across 24 scenarios (5 tiers × 4 datasets + 4 cross-session follow-ups). This document captures every decision, workaround, reasoning pattern, and failure mode I encountered — not as a post-hoc reflection, but as raw field notes from having to BE the agent. These observations should feed directly into the Layer 2 spec.

---

## 1. The Agent Loop I Actually Ran

For every scenario, my reasoning loop followed this pattern:

```
1. Read the user's question
2. Decide: does this need clarification? (→ ask_user)
3. Decide: does this need a plan? (→ plan approval)
4. Decide: can one session handle this or do I need subagents? (→ spawn)
5. Read the pruned DCD context for the question
6. Decide: SQL first or Python first?
7. Execute tool calls, iterating if intermediate results change the approach
8. Decide: what mode should the output be? (simple / moderate / complex)
9. Compose the render_spec.json with the right structure for the chosen mode
10. Write durable conclusions to memory if the user might ask follow-ups
```

**What this tells us about Layer 2 architecture:** the loop is NOT "pick a tool, run it, return the result." It's a multi-stage decision tree where earlier decisions (ask vs. don't ask, plan vs. just-do-it, fan-out vs. sequential) gate the entire downstream flow. Layer 2 needs a decision engine at each gate, not just a tool-calling loop.

---

## 2. Decision Gates — Where I Had to Think

### Gate 1: Does this question need clarification?

**Rule I followed:** if the question has ≥2 plausible interpretations that would produce materially different answers, ask. If there's only one reasonable reading, don't.

| Question | Did I ask? | Why |
|---|---|---|
| "What was the average fare?" | No | Unambiguous: AVG(fare_amount) |
| "How busy were we last week?" | Yes | "busy" = trip count / revenue / driver hours; "last week" = relative to what? |
| "Who counts as successful?" | Yes | Success = income alone / income+education / subjective wellbeing? |
| "Which homes are undervalued?" | Yes | Undervalued relative to what baseline? |
| "Which era dominates baseball?" | Yes | "era" = decade / generation / expansion period; "dominates" = championships / wins / dynasty runs |

**Pattern:** questions with adjectives ("busy", "successful", "undervalued", "dominant") almost always need clarification. Questions with specific column references ("average fare") almost never do.

**What Layer 2 needs:** a pre-classification step that scores the question for ambiguity BEFORE reading the DCD. The DCD helps resolve column-level ambiguity ("which revenue column?") but not intent-level ambiguity ("what does 'successful' mean in this domain?"). The agent should ask about intent first, then use the DCD to ground the resolved intent.

### Gate 2: Does this need a plan?

**Rule I followed:** if the expected work is ≤3 tool calls AND the interpretation is unambiguous, skip the plan. Otherwise, plan.

| Tier | Plan used? | Why |
|---|---|---|
| Tier 1 (atomic lookup) | No | 1 SQL + 1 Python = 2 calls, no ambiguity |
| Tier 2 (ambiguous) | Yes | After resolving ambiguity, the user should see what the agent will do BEFORE it runs |
| Tier 3 (multi-step) | Yes | 4-6 tool calls, depends_on edges, user should review the approach |
| Tier 4 (subagents) | Yes | Expensive multi-agent work; user must approve the fan-out |
| Tier 5 (complex) | Yes | Long-horizon, multiple phases, durable outputs |

**What Layer 2 needs:** a cost estimator that looks at the question + DCD and predicts the number of tool calls needed. If ≥3, enter plan mode. The plan's `expected_cost` field already exists in Layer 1 — Layer 2 just needs to populate it honestly and use it as the gate threshold.

### Gate 3: Single session or subagent fan-out?

**Rule I followed:** if the question decomposes into ≥3 independent slices that don't share intermediate state, fan out. If the slices share state (e.g., a temp table or a DataFrame), stay sequential.

| Question | Fan out? | Slices |
|---|---|---|
| "Weekend vs weekday tipping by hour" | No | Sequential: temp table → aggregate → chart. Slices share the temp table. |
| "Decompose trip volume by time slot" | Yes (4 subagents) | Night/morning/afternoon/evening are independent; no shared state |
| "Income gap by education/occupation/marital" | Yes (3 subagents) | Each factor is an independent GROUP BY; no shared state |
| "4-era baseball decomposition" | Yes (4 subagents) | Each era is a year-range filter; no shared state |

**What Layer 2 needs:** a decomposition heuristic:
- If the question mentions "compare X vs Y vs Z" and X/Y/Z are disjoint filters → fan out, one subagent per filter
- If the question says "broken down by" a single dimension → stay sequential (it's one GROUP BY, not N independent queries)
- If the question says "analyze each [category]" → fan out per category
- Default: sequential. Only fan out when the parallelism is obvious.

### Gate 4: What output mode?

**Rule I followed:**

| Signal | Mode |
|---|---|
| Question asks for a single fact or number | Simple |
| Question asks for a comparison or breakdown with a narrative | Moderate |
| Question asks for a "report" or "brief" or "strategy" | Complex |
| Agent used >1 subagent | Moderate or Complex (depending on page count) |
| Agent resolved an ambiguity via ask_user | At least Moderate (the user invested effort, they deserve more than a number) |

**What Layer 2 needs:** mode selection should happen EARLY — ideally at plan time, so the plan's steps reflect the output complexity. A plan for a simple-mode answer has 2 steps; a plan for a complex-mode report has 6-8 steps with explicit "emit page N" steps.

---

## 3. Tool-Calling Patterns I Fell Into

### Pattern A: "SQL first, Python for render"

Used in: Tier 1 (all), Tier 2 (2A, 2D), Tier 3 (3A, 3C)

```
1. run_sql to get the answer (SELECT AVG(...) or GROUP BY ...)
2. run_python to:
   a. Load the SQL result into a DataFrame
   b. Write data parquet for Layer 3
   c. Compose and write render_spec.json
   d. Print the answer as JSON to stdout
```

**Why:** SQL is faster and more expressive for aggregations. Python is needed for file I/O (parquet writes) and structured output (render_spec). This two-phase pattern was the most reliable across all tiers.

**Gotcha:** the SQL tool and the Python sandbox have DIFFERENT connections. Temp tables created via `/tools/sql` are NOT visible in the Python sandbox's `con`. I had to pass SQL results into Python as literal lists. Layer 2 needs to know this is the boundary.

### Pattern B: "Python-only with sandbox DuckDB"

Used in: Tier 1 (1A, 1B, 1D), Tier 2 (2B), Tier 3 (3B, 3D)

```
1. run_python call 1:
   - con.execute("SELECT ... FROM dataset") → DataFrame
   - Write parquet files
   - Set persist_check variable
2. run_python call 2 (same session_id):
   - Assert persist_check (verify session state survived)
   - Build render_spec from the DataFrame
   - Write render_spec.json
```

**Why:** when the Gold table is available as `dataset` in the sandbox, there's no reason to bounce through `/tools/sql`. The sandbox's DuckDB is fast enough for aggregations, and keeping everything in one session avoids the SQL↔Python boundary.

**Gotcha:** this only works for the primary table. Multi-file datasets (Lahman) forced me back to Pattern A because the sandbox only sees one table.

### Pattern C: "SQL probe → Python with injected data"

Used in: Tier 1 (1C), Tier 2 (2C), Tier 3 (3C), all Tier 4

```
1. run_sql: SELECT table_name FROM information_schema.tables WHERE ...
   (discover the real table name)
2. run_sql: SELECT ... FROM "raw_teams_xxx" ...
   (run the actual query against the server's DuckDB)
3. run_python: pass SQL rows as a Python literal, build DataFrame,
   write parquet + render_spec
```

**Why:** Lahman's multi-file upload materializes 10 tables in the server's DuckDB but the sandbox only sees AllstarFull. To query Teams/Batting/Pitching, I had to use `/tools/sql` and then pipe the result into Python. This is ugly and a real Layer 2 pain point.

**What Layer 2 needs:** either (a) the sandbox loads all tables from multi-file uploads, or (b) the agent has a standard "SQL-to-Python bridge" pattern baked into its system prompt. Both are valid; (a) is a Layer 1 fix, (b) is a Layer 2 workaround.

### Pattern D: "Subagent fan-out → memory bridge → master integration"

Used in: all Tier 4, all Tier 5

```
Master:
1. create_plan with N steps (one per subagent + integration step)
2. submit plan, wait for approval
3. For each subagent:
   a. spawn_subagent(parent_session_id=master_session, task="...")
   b. mark running
   c. Run the subagent's tool calls (SQL/Python) under the subagent's own session
   d. complete_subagent with write_to_parent_memory=True, result=JSON section
4. Master reads back all subagent results via memory_get
5. Master runs final Python to stitch sections into a unified render_spec
6. plan_done
```

**Critical insight:** the subagent's result is a JSON string, not a structured object. I had to serialize the partial render_spec section as JSON, store it as a memory value, and deserialize on the master side. This works but means the master has to know the section schema in advance. If a subagent returns unexpected shape, the master's stitching breaks silently.

**What Layer 2 needs:** a standard "subagent result envelope" schema:

```json
{
  "status": "complete",
  "section": { "title": "...", "narrative": "...", "visuals": [...] },
  "metrics_summary": { "key_metric": value },
  "errors": []
}
```

This gives the master a predictable shape to integrate regardless of what the subagent did internally.

---

## 4. Context Management — What I Read and When

### DCD pruning

I called `get_context(dataset_id, query="...")` at the start of every scenario. The pruned DCD was useful for:
- Confirming which columns are metrics vs dimensions (so I don't SUM a categorical)
- Finding the temporal column name and grain
- Reading `verified_queries` as few-shot SQL examples
- Checking `agent_instructions` for constraints ("never enumerate identifier columns")

**What I didn't use the DCD for:**
- Deciding whether to ask the user (that's about intent, not schema)
- Choosing chart types (that's about data shape, not metadata)
- Writing the narrative sections of the render_spec (that's creative composition)

**Layer 2 implication:** the DCD is a reference, not a reasoning scaffold. Pull it once per turn, extract the column roles and constraints, then reason independently. Don't re-read it per tool call — waste of tokens.

### Schema summary vs full context

`get_schema(dataset_id)` is the compact version — columns with roles, summary_tables, verified_queries. No sample values, no stats, no hierarchy details. I used this when I needed a quick column list (e.g., "does this dataset have a `Neighborhood` column?") and the full context when I needed to understand the data (e.g., "what are the sample values for `income`?").

**Layer 2 implication:** call `get_schema` first (cheap, fits in context). Only call `get_context(pruned)` when you need the full metadata for a specific column subset.

### Memory reads

In Tier 5 phase 2, the first thing I did was `memory_get("dataset", ds_id, "tier5_5A_taxi_conclusions")`. This retrieved the phase-1 findings without re-running any queries. The memory value contained:
- plan_id (for audit trail back-reference)
- subagent_ids (for traceability)
- key_findings (the actual conclusions, as strings)
- recommendations (structured, with confidence levels)

**Layer 2 implication:** at the START of every conversation, the agent should check `memory_search(query=dataset_name)` to see if prior sessions left any conclusions. If they did, load them into the agent's context before deciding what to do. This prevents redundant work and enables "continuing where we left off" behavior.

---

## 5. Render Spec Composition — The Hardest Part

### What made it hard

1. **No schema to validate against at authoring time.** I had to carry the render_spec structure in my head (from the plan document). A real agent would need it in its system prompt — that's ~500 tokens of JSON schema.

2. **Choosing chart types required understanding the data shape, not just the column metadata.** The DCD says `tip_amount` is a metric with role=metric and aggregation=SUM. But is a bar chart or a histogram the right choice? That depends on whether I'm showing a distribution (histogram) or a comparison across categories (bar). The DCD doesn't tell me this — I had to reason from the query intent.

3. **Story arc composition.** Moderate-mode specs need 3+ sections with real titles — not "Section 1, Section 2, Section 3" but "Weekend riders tip more, but the gap is time-of-day driven." Writing these titles requires understanding the insight the section communicates, which requires having already computed the answer. So the render_spec can only be finalized AFTER the analysis, not during planning.

4. **KPI card selection.** Which 3-5 numbers go in the headline KPI row? This is a judgment call. For the Taxi tipping dashboard, I chose: weekend tip rate, weekday tip rate, weekend trip count, weekday trip count. A different analyst might choose: overall tip rate, tip rate delta, peak hour, highest-tip payment type. Layer 2 needs a heuristic: "pick the number the user asked about as KPI #1, then pick 2-3 numbers that contextualize it."

5. **Drill-down hints.** Every moderate section has a `drill_downs` array with `{label, query_hint}`. These are hints that Layer 3's frontend could render as clickable buttons. I had to imagine "what would the user want to click next?" after each section. For the tipping section, I wrote `{"label": "Show me only 11PM-2AM rides", "query_hint": "hour BETWEEN 23 AND 2"}`. A real agent needs a "next question predictor."

### What the agent should do in practice

```
1. Compute the answer FIRST (SQL/Python)
2. Look at the result shape: scalar? one column? two columns? matrix?
3. Map shape to chart type:
   - scalar → kpi card
   - 1 categorical × 1 numeric → bar chart
   - 1 temporal × 1 numeric → line chart
   - 2 categorical × 1 numeric → heatmap or grouped bar
   - 1 numeric × 1 numeric → scatter
   - ordered stages → funnel
   - part-of-whole → pie (rarely) or treemap
4. Compose the section title from the INSIGHT, not the method
   ("Education is the single biggest wedge" not "Education vs income breakdown")
5. Write the narrative from the numbers, not from the DCD
6. Add drill-down hints by asking "what would the user click next?"
7. Assemble sections into story order (not computation order)
8. Write KPIs by picking: the answer, the delta, and 1-2 context numbers
```

---

## 6. Session State Management

### What I had to track across calls

Within a single scenario, I maintained state across multiple tool calls:

- **Python session_id:** reused across 2-3 calls to preserve DataFrames and variables. Critical for Tier 3+ where call 1 computes aggregates and call 2 builds the render_spec from those aggregates.
- **Plan ID:** created at the start, referenced in the render_spec's `plan_id` field and in `plan_done()` at the end.
- **Subagent IDs:** collected during fan-out, passed into the final render_spec's `subagent_ids` array for traceability.
- **Memory keys:** chosen at plan time, used at write time and at read time (in phase 2).
- **Dataset ID:** constant per scenario, but discovered dynamically from the dataset_id file.
- **Gold table name:** discovered via `information_schema.tables` (for `/tools/sql`) or implicitly as `dataset` (for Python sandbox).

**What Layer 2 needs:** a session-level scratchpad that tracks:

```python
class AgentSessionContext:
    session_id: str
    dataset_id: str
    gold_table_name: str        # for /tools/sql
    sandbox_view_name: str      # always "dataset" for /tools/python
    dcd_columns: list[str]      # column names from the pruned DCD
    active_plan_id: str | None
    python_session_id: str | None
    subagent_ids: list[str]
    memory_keys_written: list[str]
    tool_call_count: int        # for cost tracking
    mode: str                   # simple / moderate / complex
```

This scratchpad persists within the agent's reasoning loop for the current user turn and is NOT stored in Layer 1 memory (it's ephemeral agent context, not durable knowledge).

---

## 7. Error Handling I Had to Do

### Errors from Layer 1 that I handled

| Error | How I encountered it | What I did |
|---|---|---|
| 500 on upload (LLM error body) | Taxi upload, first 3 attempts | Retried at harness level (before fixing Layer 1) |
| 500 on upload (dotted column names) | Ames upload | Found the bug, fixed Layer 1, retried |
| 500 on upload (SUM on VARCHAR) | Ames upload | Found the bug, fixed Layer 1, retried |
| 400 on `DESCRIBE` SQL | Lahman table discovery | Switched to `information_schema.columns` |
| 404 on `run_python` after restart | Tier 5 phase 2 | Found missing rehydration, fixed Layer 1 |
| Python exit_code=1, missing pyarrow | All tier 1 cells | Installed pyarrow, retried |
| Python exit_code=1, wrong table name | Tier 1 (used Gold table name in sandbox) | Switched to `FROM dataset` |
| OpenRouter 429 (daily quota) | All datasets after ~50 requests | Heuristic fallback classifier kicked in |

### Error recovery strategies a real Layer 2 needs

1. **On Python exit_code=1:** read stderr, diagnose. Common causes: missing import (tell user), wrong table name (switch to `dataset`), syntax error (fix code). Do NOT blindly retry the same code.

2. **On SQL 400 (validation rejected):** check if the statement type is unsupported. Use `information_schema` instead of `DESCRIBE`. Use `SELECT * FROM ... LIMIT 5` instead of `SHOW TABLES`.

3. **On upload 500:** this is almost always a profiling or materialization bug, not a user error. The agent should surface the error to the user, not retry blindly. The heuristic fallback means the pipeline can survive LLM failures now, but schema-level crashes (dotted names, weird dtypes) still need Layer 1 fixes.

4. **On memory 404:** the key doesn't exist. This is normal for a first conversation. The agent should check and proceed without the memory, not crash.

5. **On plan timeout (timed_out=true):** the user didn't approve in time. The agent should NOT re-submit the same plan. It should either ask the user if they're still there, or fall back to a simpler approach that doesn't need approval.

---

## 8. What I Wish Layer 1 Had

### 8.1 Sandbox should expose all multi-file tables

I spent more time working around the "sandbox only sees AllstarFull" limitation than any other single issue. In every Lahman scenario, I had to:
1. Discover the table name via `information_schema.tables` (through `/tools/sql`)
2. Run the aggregation via `/tools/sql`
3. Serialize the rows as a Python literal
4. Pipe them into `run_python`

If the sandbox pre-loaded all `gold_*.parquet` files as named views (e.g., `dataset_teams`, `dataset_batting`, `dataset_people`), I could have done everything in one Python call.

### 8.2 Tool manifest should describe the sandbox's view contract

I discovered the `dataset` view name by trial and error (first attempt used the Gold table name, which 404'd in the sandbox). The `/tools/list` manifest says "pre-loaded with df, con, OUTPUT_DIR" but doesn't mention that the DuckDB connection has a view called `dataset`. One line of documentation would have saved 20 minutes of debugging.

### 8.3 SQL tool should accept DESCRIBE

`DESCRIBE raw_teams_40db28` is a natural first step for a Layer 2 agent trying to understand a table's schema. The SQL validator rejects it because DESCRIBE isn't in the allowed-statement regex. Using `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '...'` works but is verbose and non-obvious.

### 8.4 A render spec validation endpoint

I was composing JSON render specs by hand and had no way to validate them against a schema until the very end (the `validate_render_spec.py` script I wrote). If Layer 1 had a `POST /renders/validate` endpoint that checked the spec against the schema and returned a list of errors, I could have validated in-flight and fixed mistakes immediately instead of discovering structural issues at the end of the run.

### 8.5 A "what can I query?" discovery endpoint

For multi-file datasets, I had no way to see what tables were available until I queried `information_schema.tables`. A `GET /datasets/{id}/tables` endpoint that returns `[{name, column_count, row_count, type: "gold" | "raw" | "summary"}]` would let the agent decide what to query before making its first SQL call.

---

## 9. Memory Strategy That Worked

### What to persist (and where)

| What | Scope | Key convention | Example |
|---|---|---|---|
| Analysis conclusions | `dataset` | `{context}_{topic}` | `tier5_5A_taxi_conclusions` |
| User corrections | `dataset` | `correction_{column}` | `correction_VendorID_is_dimension` |
| Metric definitions | `dataset` | `definition_{metric}` | `definition_active_user` |
| Subagent partial results | `session` | `subagent_{sub_id}_section` | `subagent_sub_abc123_section` |
| User preferences | `user` | `preference_{setting}` | `preference_currency_format` |

### What NOT to persist

- Intermediate DataFrames or raw query results (too large, stale quickly)
- The render_spec itself (it's on disk at `OUTPUT_DIR/render_spec.json`)
- The plan object (it's in the plan store, not memory)
- Column profiles (they're in the DCD, which is on disk)

### Cross-session retrieval pattern

```
1. Agent starts new session
2. memory_search(query=dataset_name) → find prior conclusions
3. If found:
   a. Load key_findings and recommendations
   b. Check if they're still current (compare ingested_at with memory updated_at)
   c. Surface them to the user: "I found prior analysis from [date]. Findings: ..."
   d. Ask: "Do you want to continue from here or start fresh?"
4. If not found:
   a. Proceed as if first conversation
```

---

## 10. Subagent Orchestration Lessons

### What worked

- **Fixed fan-out (3-4 subagents with predefined slices):** Taxi time-slots (night/morning/afternoon/evening), Adult factors (education/occupation/marital), Lahman eras (dead-ball/golden/expansion/modern), Ames price tiers (top/upper-mid/mid/bottom). When the decomposition is obvious and symmetric, fan-out is clean.

- **Memory bridging:** every subagent called `complete_subagent(write_to_parent_memory=True)` and the master read the results back. Zero data loss across 27 subagents.

- **Section ordering:** the master received sections in spawn order but could reorder them into narrative order. For the era decomposition, spawn order was chronological (dead-ball first) which happened to be narrative order too. For the price-tier decomposition, spawn order was top→bottom which was also narrative order. Lucky — but a real agent should explicitly sort sections by a relevance/chronology key.

### What was awkward

- **Each subagent had to independently discover table names.** In the Lahman era subagents, each one separately queried `information_schema.tables` to find the Teams table. That's 4 redundant discovery queries. The master should have discovered once and passed the table name in `context_hint`.

- **No shared context between subagents.** Each subagent has its own Python kernel. If subagent A computes a baseline (e.g., overall average tip rate), subagent B can't reference it. The master has to either pre-compute the baseline and inject it into each subagent's code, or post-hoc normalize after collection. Pre-compute is better.

- **Subagent result schema was ad-hoc.** I defined `_section()` as a helper to standardize the partial render_spec shape, but a real agent would need a formal subagent result envelope (see section 3 above).

### Subagent rules for Layer 2

1. **Fan out only when slices are independent.** If subagent B needs subagent A's output, they're sequential, not parallel.
2. **Pre-compute shared context in the master.** Baselines, thresholds, column discovery — do it once, pass via `context_hint`.
3. **Limit fan-out to 3-5 subagents.** More than that and the master's integration step becomes unwieldy. If you have 10 slices, group them into 3-4 macro-slices.
4. **Each subagent should return a standardized envelope.** Don't let subagents invent their own result shapes.
5. **The master's integration step is the most important tool call.** It's where the narrative coherence lives. Don't skip it — even if the subagent sections are individually well-written, they need a master summary and an ordering decision.

---

## 11. Cost Tracking and Budget Awareness

### What I tracked

Each plan had an `expected_cost` field:

```json
{
  "sql_calls": 3,
  "python_calls": 2,
  "llm_calls": 0,
  "subagent_spawns": 4
}
```

### Actual vs. expected

| Tier | Expected SQL | Actual SQL | Expected Python | Actual Python | Notes |
|---|---|---|---|---|---|
| 1 | 1 | 0-1 | 1 | 1 | Simpler than expected — sandbox SQL is enough |
| 2 | 0-1 | 0-1 | 1 | 1 | ask_user + plan ceremony adds 4 HTTP calls but no SQL/Python |
| 3 | 1-3 | 1-3 | 2 | 2 | Temp table path (3A) used 3 SQL calls as predicted |
| 4 | 3-5 (across subagents) | 4-8 | 4-5 | 4-5 | Table discovery queries add overhead |
| 5 | 2-4 (per phase) | 2-4 | 2-3 | 2-3 | Phase 2 was cheaper (memory recall, no re-query) |

### Layer 2 implication

The agent should maintain a running `tool_call_count` and compare against the plan's `expected_cost`. If actual exceeds expected by >50%, either:
- Revise the plan (the approach is more complex than anticipated)
- Log a warning (something went wrong — redundant calls, retry loops)
- Ask the user if they want to continue (for expensive long-horizon tasks)

---

## 12. The Things That Are NOT Layer 1 Problems

These are genuine Layer 2 responsibilities that no amount of Layer 1 improvement will solve:

1. **Deciding what to show.** Layer 1 gives the agent the data. Layer 2 decides: is the answer "18.18" or "most trips cluster in the $5-15 bucket"? Both are correct. One is a number, the other is an insight. The agent's job is to pick the insight.

2. **Writing the narrative.** No amount of DCD metadata will tell the agent how to write "Weekend riders tip more, but the gap is time-of-day driven." That's synthesis — combining the data, the user's question, and domain knowledge into a sentence that a human would find useful.

3. **Ordering sections by narrative arc, not computation order.** I computed "overall tip rate" before "hourly breakdown" but presented the hourly breakdown first in the render_spec because that's the more interesting finding. The agent has to reorder its work into a story.

4. **Knowing when to stop.** In Tier 5, I could have generated 10 pages of analysis. I stopped at 3 because the user asked for a strategy report, not a dissertation. The agent needs a "diminishing returns" sensor — when adding another page doesn't change the recommendations, stop.

5. **Calibrating confidence levels on recommendations.** In the exec summary, I wrote `{"action": "Shift surge pricing to 23:00-02:00", "confidence": "medium"}`. Why medium? Because the data shows higher tip rates at night, but I don't know if demand is elastic to surge pricing. That's a judgment call that requires domain knowledge the agent may or may not have.

---

## 13. Summary: What Layer 2 Must Be

Based on having been the agent for 24 scenarios:

Layer 2 is a **multi-gate decision engine** that:

1. **Classifies the question** by ambiguity, complexity, and expected output mode before touching any tool
2. **Routes through gates**: ask_user → plan → decompose → execute → compose → persist
3. **Manages its own context window**: pulls DCD once, caches it, doesn't re-read per call
4. **Tracks cost**: knows how many calls it's made vs. how many it planned
5. **Composes output for Layer 3**: picks chart types from data shapes, writes story-arc titles from insights, orders sections by narrative importance not computation order
6. **Persists intelligently**: writes conclusions (not raw data) to dataset-scoped memory under a naming convention
7. **Recovers from errors**: reads stderr, diagnoses, fixes, doesn't blindly retry
8. **Knows when to stop**: 3 pages is enough, 10 is too many

It is NOT:
- A tool-calling loop
- A prompt-template engine
- A code generator
- A dashboard renderer

It is the analyst who happens to use tools. The tools are Layer 1. The judgment is Layer 2. The presentation is Layer 3.
