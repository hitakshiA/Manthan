# Layer 3 Render Spec Schema

This schema is the test-proven contract that 24 render specs passed during the Layer 1 stress test. It is intended as the starting point for Layer 2 agents when they produce output for Layer 3's `simple` / `moderate` / `complex` modes.

The validator implementation lives at `scripts/stress_test/validate_render_spec.py` and should be promoted to `src/semantic/render_spec.py` as a Pydantic model when Layer 2 is built.

---

## Mode 1: Simple

Use when: the user wants a quick answer, low ceremony, visible KPI plus one or two supporting charts.

### Required fields

- `mode`: `"simple"`
- `headline`: `{value: str, label: str}` — the single KPI the user is looking for
- `narrative`: `str` — 2-4 sentences, human-readable
- `visuals`: `list` of length **1-3**, each:
  - `id`: `str`
  - `type`: one of `histogram`, `bar`, `line`, `area`, `scatter`, `bubble`, `heatmap`, `funnel`, `sankey`, `treemap`, `pie`, `box`, `violin`, `kpi`
  - `title`: `str`
  - `data_ref`: `str | null` — path to a parquet file under OUTPUT_DIR
  - `encoding`: `dict` — chart-specific (`x`, `y`, `color`, `value`, etc.)
  - `caption`: `str` (optional)
- `citations`: non-empty `list` of `{kind, identifier, reason}` backing the answer in the DCD

### Optional fields

- `caveats`: `list[str]` — known limitations the user should see

### Example

```json
{
  "mode": "simple",
  "headline": {"value": "$18.18", "label": "Average January 2024 fare"},
  "narrative": "Across 2,964,624 NYC Yellow Taxi trips in January 2024, the average fare was $18.18. Trips cluster in the $5-$15 bucket; a long-distance tail pulls the mean above the median.",
  "visuals": [
    {
      "id": "v1",
      "type": "histogram",
      "title": "Distribution of fare amounts",
      "data_ref": "files/fare_hist.parquet",
      "encoding": {"x": "lower_bound", "y": "trip_count"},
      "caption": "Most rides fall in the $5-15 bucket"
    }
  ],
  "citations": [
    {"kind": "column", "identifier": "fare_amount", "reason": "primary revenue measure"}
  ]
}
```

---

## Mode 2: Moderate

Use when: the user wants a basic dashboard with a narrative arc, 3-5 sections, and drill-down hooks.

### Required fields

- `mode`: `"moderate"`
- `title`: `str` — agent-authored, not template
- `kpi_row`: non-empty `list` of cards, each `{value, label, delta, sentiment}` where `sentiment` ∈ `{positive, negative, neutral}`. **Must have ≥2 cards.**
- `sections`: non-empty `list` with **≥3** items, each:
  - `title`: `str` — story-arc title (NOT "Section 1")
  - `narrative`: `str`
  - `layout`: one of `single`, `two_col`, `three_col`, `hero_chart`, `kpi_grid`. **At least one section must use `two_col` or `three_col`.**
  - `visuals`: `list` of visual objects (same shape as Simple mode)
  - `drill_downs`: `list` of `{label, query_hint}` hints the user can click
- `citations`: non-empty list
- `plan_id`: `str` — links the rendered output back to the Plan that produced it

### Optional fields

- `subtitle`: `str`
- `caveats`: `list[str]`

### Available layout primitives

| Layout | Use when |
|---|---|
| `single` | One centered chart dominates |
| `two_col` | Two charts side by side |
| `three_col` | Three charts in a grid |
| `hero_chart` | One large headline chart with a narrative below |
| `kpi_grid` | Grid of KPI cards |

### Available chart types

`histogram`, `bar` (horizontal/vertical/stacked/grouped), `line`, `area`, `scatter`, `bubble`, `heatmap`, `funnel`, `sankey`, `treemap`, `pie`, `box`, `violin`, `kpi`.

**Agent must pick the right chart for the data shape.** Heatmap for day×hour cross-tabs, funnel for sequential stages, scatter for two continuous vars, line for temporal series, bar for discrete comparisons. The stress test explicitly scores this.

---

## Mode 3: Complex

Use when: the user asks for a deep, multi-page report — executive summary + drill-down pages + appendix + durable conclusions for follow-up sessions.

### Required fields

- `mode`: `"complex"`
- `report_title`: `str`
- `executive_summary`: `dict` with:
  - `headline`: `str`
  - `key_findings`: `list[str]` — **≥2** items, one-liners, quantified where possible
  - `recommendations`: non-empty `list` of `{id, action, rationale, expected_impact, evidence_page, confidence}` where `confidence` ∈ `{low, medium, high}`
- `pages`: non-empty `list` (typically 3-8), each:
  - `id`: `str`
  - `title`: `str`
  - `purpose`: `str` — one line describing what the page is for
  - `layout`: one of `hero_plus_grid`, `single`, `two_col`, `three_col`, `narrative_only`
  - `blocks`: `list` of mixed block types (see below)
  - `cross_references`: `list[{to_page, reason}]` (optional)
- `appendix`: `dict` with:
  - `methodology`: `str`
  - `data_quality_notes`: `list[str]`
  - `open_questions`: `list[str]`
- `memory_refs`: `list[{scope, key}]` — must cite the memory rows this report's conclusions are stored under (or recalled from, in phase-2 follow-ups)

### Optional fields

- `report_subtitle`: `str`
- `plan_ids`: `list[str]` — one or more Plan IDs that drove this report
- `subagent_ids`: `list[str]` — traceability back to the subagents that produced sections
- `phase`: `int` — 1 for the original report, 2+ for follow-ups that cite phase-1 via memory_refs

### Block type palette

Inside each page's `blocks`:

| Type | Required fields | Use when |
|---|---|---|
| `kpi_row` | `items: list` of kpi cards | Top-of-page number row |
| `hero_chart` | `visual: {...}` | Page's centerpiece chart |
| `chart_grid` | `cols: int`, `visuals: list` | 2-4 related charts |
| `table` | `title: str`, `data_ref: str`, `columns: list` | Tabular drilldown |
| `narrative` | `text: str` | Markdown prose |
| `callout` | `style: str`, `text: str` | Insight / warning / action item |
| `comparison` | `left: block`, `right: block` | Side-by-side A vs B |

### Cross-session continuity

Phase-2 reports (a new session opening a follow-up to yesterday's work) **must** include `memory_refs` pointing at the phase-1 conclusions and should not re-derive phase-1 findings from scratch. The stress test verifies this by inspecting the phase-2 HTTP trace for duplicate aggregation SQL.

### Example phase-1 → phase-2 linkage

```json
// Phase 1 (session X)
{
  "mode": "complex",
  "report_title": "NYC Taxi January 2024 Operations Strategy",
  "executive_summary": {
    "key_findings": ["60% of revenue in 4 peak hours", "..."],
    "recommendations": [
      {"id": "r1", "action": "Shift surge pricing to 23:00-02:00",
       "confidence": "medium", "evidence_page": "page_1"}
    ]
  },
  "pages": [{"id": "page_1", "title": "Profitability by hour", ...}],
  "memory_refs": [{"scope": "dataset", "key": "tier5_5A_taxi_conclusions"}],
  "phase": 1
}

// Phase 2 (new session Y, after server restart)
{
  "mode": "complex",
  "report_title": "Follow-up: NYC Taxi January 2024 Operations Strategy",
  "executive_summary": {
    "key_findings": ["Phase-1 concluded: 60% of revenue in 4 peak hours", ...],
    "recommendations": [...]  // recalled from memory, not re-derived
  },
  "memory_refs": [{"scope": "dataset", "key": "tier5_5A_taxi_conclusions"}],
  "phase": 2
}
```

---

## Proposed Layer 1 surface for this contract

The stress test emitted render specs as JSON files under `OUTPUT_DIR` via the existing `run_python` tool, with `data_ref` paths relative to the output dir. That worked but leaves schema validation to convention.

### Recommendation: typed `POST /renders` endpoint

```
POST /renders
Request body: {session_id, plan_id (optional), dataset_id, spec: {...}}
Behavior: validates `spec` against the Pydantic schema derived from this
          document, persists to data/{ds_id}/output/render_{uuid}.json,
          attaches a `scope_type=session` memory entry so a UI can
          discover the latest render for a session via memory search.
Response: {render_id, spec_path, memory_key}
```

This gives Layer 2 a typed surface and takes the schema-carrying burden out of the agent's system prompt.

---

## Test-proven required fields (auto-derived from `validate_render_spec.py`)

The following fields are those the stress test's 24 passing specs all carried. A real Pydantic model derived from this table can be generated mechanically from `scripts/stress_test/validate_render_spec.py`.

| Mode | Field | Required | Min/Max |
|---|---|---|---|
| all | `mode` | yes | one of simple/moderate/complex |
| simple | `headline.value`, `headline.label` | yes | |
| simple | `narrative` | yes | |
| simple | `visuals` | yes | 1-3 items |
| simple | `visuals[].id`, `visuals[].type`, `visuals[].title` | yes | |
| simple | `citations` | yes | non-empty |
| moderate | `title`, `kpi_row`, `sections` | yes | kpi_row ≥2, sections ≥3 |
| moderate | `sections[].title`, `.narrative`, `.layout`, `.visuals` | yes | |
| moderate | at least one section with `layout ∈ {two_col, three_col}` | yes | |
| moderate | `plan_id` | yes | |
| complex | `report_title`, `executive_summary`, `pages`, `appendix` | yes | pages ≥1 |
| complex | `executive_summary.key_findings` | yes | ≥2 items |
| complex | `executive_summary.recommendations` | yes | non-empty |
| complex | `pages[].id`, `.title`, `.purpose`, `.layout`, `.blocks` | yes | |
| complex | `appendix.methodology`, `.data_quality_notes`, `.open_questions` | yes | |
| complex | `memory_refs` | yes | |
| complex | `phase=2` → must have non-empty `memory_refs` | yes | |
