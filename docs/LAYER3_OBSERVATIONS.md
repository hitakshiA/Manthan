# Layer 3 Observations — What a Frontend Must Do With What the Agent Produces

**Context:** Across 24 render specs (8 simple, 8 moderate, 8 complex) produced during the Layer 1 stress test, I had to design and emit the complete Layer 3 rendering contract from the agent side. This document captures every observation about what Layer 3 (the frontend) needs to handle, what the agent gives it, what's missing, and what the three modes actually look like when driven by real data through a real pipeline.

---

## 1. The Three Modes Are Not Complexity Levels — They're Different Products

This is the most important observation. Simple, moderate, and complex are NOT "show less vs show more." They are fundamentally different user experiences with different interaction patterns, different information density, and different UI architectures.

| Mode | What the user sees | Interaction model | Time to consume | Analogy |
|---|---|---|---|---|
| **Simple** | A number, a sentence, and a chart | Glance and go | 5-10 seconds | A Google snippet |
| **Moderate** | A single-page dashboard with KPIs, story sections, and drill-down hooks | Scan top-to-bottom, click drill-downs | 2-5 minutes | A PowerBI dashboard page |
| **Complex** | A multi-page report with executive summary, dedicated analysis pages, appendix, and cross-session continuity | Read like a document, navigate between pages, revisit via memory | 10-30 minutes | A McKinsey deck |

**Layer 3 implication:** these aren't three skins on the same component tree. They're three distinct page architectures. Simple is a card. Moderate is a dashboard. Complex is a document viewer with pagination.

---

## 2. What the Agent Actually Emits (From 24 Real Specs)

### Structural inventory across all 24 specs

| Feature | Simple (8) | Moderate (8) | Complex (8) |
|---|---|---|---|
| `headline` object | 8/8 | 0/8 | 0/8 |
| `narrative` (string) | 8/8 | 0/8 (per-section instead) | 0/8 (per-block) |
| `kpi_row` (cards array) | 0/8 | 8/8 | 0/8 (moved to page blocks) |
| `sections[]` with titles | 0/8 | 8/8 (3-4 per spec) | 0/8 (replaced by `pages[]`) |
| `pages[]` | 0/8 | 0/8 | 8/8 (1-3 per spec) |
| `executive_summary` | 0/8 | 0/8 | 8/8 |
| `appendix` | 0/8 | 0/8 | 8/8 |
| `visuals[]` (flat) | 8/8 | 0/8 (nested in sections) | 0/8 (nested in blocks) |
| `citations[]` | 8/8 | 8/8 | 0/8 (moved to page-level) |
| `caveats[]` | 5/8 | 8/8 | 0/8 (moved to appendix) |
| `drill_downs[]` | 0/8 | 4/8 | 0/8 |
| `plan_id` | 0/8 | 8/8 | 8/8 (as `plan_ids[]`) |
| `subagent_ids[]` | 0/8 | 4/8 | 8/8 |
| `memory_refs[]` | 0/8 | 0/8 | 8/8 |

### Visual types actually used

| Chart type | Count | Where used |
|---|---|---|
| `bar` | 27 | Everywhere — the workhorse for categorical comparisons |
| `line` | 6 | Temporal trends (trip volume by day, wins over decades) |
| `kpi` | 5 | Subagent summary cards (Tier 4 fan-out results) |
| `scatter` | 2 | Two continuous vars (area vs price, distance vs tip rate) |
| `histogram` | 1 | Distribution of fare amounts (Tier 1 Taxi) |
| `box` | 1 | Quality distribution across neighborhoods (Tier 3 Ames) |
| `heatmap` | 0 | Planned for day×hour but implemented as line instead |
| `funnel` | 0 | Would have been used for Olist order funnel (dataset was swapped) |
| `sankey` | 0 | Same |
| `treemap` | 0 | Never needed in practice |
| `pie` | 0 | Deliberately avoided — bar is always clearer |

**Layer 3 implication:** a v1 frontend needs exactly 4 chart renderers: **bar**, **line**, **scatter**, **kpi card**. That covers 98% of the stress test output. Histogram can be a bar variant. Box and heatmap are stretch goals. Funnel and sankey are nice-to-haves for marketplace/e-commerce use cases.

### Layout types actually used

| Layout | Count | Where used |
|---|---|---|
| `two_col` | 16 | Most common — two charts side by side |
| `single` | 13 | One centered chart or narrative block |
| `three_col` | 6 | Three charts in a grid (composition views) |
| `hero_plus_grid` | 4 | Complex mode pages (one big chart + supporting grid) |
| `narrative_only` | 4 | Complex mode follow-up pages (text-only recall from memory) |

**Layer 3 implication:** the layout engine needs 5 templates. CSS grid with `grid-template-columns` handles all of them: `single` = `1fr`, `two_col` = `1fr 1fr`, `three_col` = `1fr 1fr 1fr`, `hero_plus_grid` = `1fr` (hero) + `1fr 1fr` (grid below), `narrative_only` = `1fr` (prose block).

---

## 3. Simple Mode — What Layer 3 Renders

### What the agent gives

```json
{
  "mode": "simple",
  "headline": { "value": "$18.18", "label": "Average January 2024 fare" },
  "narrative": "Across 2,964,624 NYC Yellow Taxi trips in January 2024, the average fare was $18.18. Trips cluster in the $5-$15 bucket; a long-distance tail pulls the mean above the median.",
  "visuals": [
    {
      "id": "v1",
      "type": "histogram",
      "title": "Distribution of fare amounts",
      "data_ref": "files/fare_hist.parquet",
      "encoding": { "x": "lower_bound", "y": "trip_count" },
      "caption": "Most rides fall in the $5-15 bucket"
    }
  ],
  "citations": [
    { "kind": "column", "identifier": "fare_amount", "reason": "primary revenue measure" }
  ]
}
```

### What the user should see

```
┌──────────────────────────────────────────────┐
│                                              │
│          $18.18                               │
│   Average January 2024 fare                  │
│                                              │
│   Across 2,964,624 NYC Yellow Taxi trips     │
│   in January 2024, the average fare was      │
│   $18.18. Trips cluster in the $5-$15        │
│   bucket; a long-distance tail pulls the     │
│   mean above the median.                     │
│                                              │
│   ┌──────────────────────────────────┐       │
│   │ ▓▓▓▓                            │       │
│   │ ▓▓▓▓▓▓▓▓▓▓                      │       │
│   │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓              │       │
│   │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓                  │       │
│   │ ▓▓▓▓▓▓▓▓▓▓                      │       │
│   │ ▓▓▓▓▓                           │       │
│   │ ▓▓                              │       │
│   └──────────────────────────────────┘       │
│   Distribution of fare amounts               │
│   Most rides fall in the $5-15 bucket        │
│                                              │
│   Source: fare_amount (DCD)                  │
└──────────────────────────────────────────────┘
```

### UI components needed

1. **Hero KPI card** — large value + label, prominent, above the fold
2. **Narrative paragraph** — markdown-rendered text, 2-4 sentences
3. **Chart container** — renders one chart from `data_ref` parquet + `encoding`
4. **Caption** — small text below the chart
5. **Citations footer** — collapsible, shows DCD column provenance

### UX rules

- **No scrolling required.** Simple mode fits on one viewport.
- **No interactivity.** No drill-downs, no filters, no tooltips (those belong in moderate mode).
- **Load time target: <2 seconds.** The parquet file is tiny (a few KB of aggregated data). The chart library should render instantly.
- **Mobile-friendly.** Single-column layout works on phone screens.

### Real data observations from the 8 simple specs

| Spec | Headline value | Visual type | Narrative length |
|---|---|---|---|
| 1A Taxi | $18.18 | histogram | 220 chars |
| 1B Adult | 23.9% | bar | 272 chars |
| 1C Lahman | NYA | bar | 141 chars |
| 1D Ames | $319,000 | bar | 117 chars |
| 2A Taxi | 710,135 | line | 152 chars |
| 2B Adult | 23.9% | bar | 180 chars |
| 2C Lahman | 1884s | bar | 168 chars |
| 2D Ames | 25 | bar | 164 chars |

**Observation:** narrative is always 100-280 characters. Never more. The agent is concise in simple mode. Layer 3 should allocate 3-4 lines of text, not a scrollable area.

**Observation:** headline values are heterogeneous — dollar amounts, percentages, counts, team codes, decade names. Layer 3 should render the `value` field as-is (the agent already formats it: `$18.18`, `23.9%`, `710,135`). Don't try to reformat.

---

## 4. Moderate Mode — What Layer 3 Renders

### What the agent gives

A spec with: `title`, `subtitle`, `kpi_row` (3-5 cards), `sections[]` (3-4, each with title, narrative, layout, visuals, drill_downs), `caveats[]`, `citations[]`, `plan_id`.

### What the user should see

```
┌──────────────────────────────────────────────────────────────────┐
│  Weekend vs weekday tipping — January 2024                      │
│  NYC Yellow Taxi, hour-by-hour behavior                         │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │  15.2%   │ │  13.1%   │ │ 461,203  │ │2,503,421 │          │
│  │ Weekend  │ │ Weekday  │ │ Weekend  │ │ Weekday  │          │
│  │ tip rate │ │ tip rate │ │  trips   │ │  trips   │          │
│  │ +2.1pp ↑ │ │          │ │          │ │          │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                  │
│  ─── Weekend riders tip more, but the gap is time-of-day ───    │
│  │   driven                                                │    │
│  │                                                         │    │
│  │   Over the full month, weekend trips averaged a 15.2%   │    │
│  │   tip rate vs 13.1% on weekdays...                     │    │
│  │                                                         │    │
│  │   ┌────────────────┐  ┌────────────────┐               │    │
│  │   │  Tip rate by   │  │  Trip volume   │               │    │
│  │   │  hour (line)   │  │  split (bar)   │               │    │
│  │   └────────────────┘  └────────────────┘               │    │
│  │                                                         │    │
│  │   [ Show me only 11PM-2AM rides → ]                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ─── The five most generous hour/day combinations ───           │
│  │   ...                                                   │    │
│  │   ┌──────────────────────────────────┐                  │    │
│  │   │  Top 5 combos (bar)             │                  │    │
│  │   └──────────────────────────────────┘                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ─── Distance and fare mix across hours ───                     │
│  │   ...                                                   │    │
│  │   ┌────────────────┐  ┌────────────────┐               │    │
│  │   │ Distance vs    │  │ Avg fare by    │               │    │
│  │   │ tip (scatter)  │  │ hour (line)    │               │    │
│  │   └────────────────┘  └────────────────┘               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ⚠ Weekend defined as EXTRACT(dow)==0 OR 6                      │
│  ⚠ Weighted averages used so high-volume hours dominate         │
│                                                                  │
│  Plan: plan_abc123 │ Powered by Manthan                         │
└──────────────────────────────────────────────────────────────────┘
```

### UI components needed

1. **Dashboard header** — title + subtitle, full-width
2. **KPI row** — horizontal card strip, each card showing value + label + optional delta with sentiment color (green for positive, red for negative, grey for neutral)
3. **Section container** — repeated 3-4 times, each with:
   - Section title (styled as a divider/heading)
   - Narrative paragraph
   - Layout container (single/two_col/three_col) holding 1-3 charts
   - Drill-down buttons (styled as clickable pills/links)
4. **Caveats footer** — warning icon + collapsible text
5. **Plan linkage footer** — small text linking to the plan audit trail

### KPI card design observations

From the 8 moderate specs:

| Spec | Cards | Best card design observation |
|---|---|---|
| 3A Taxi | 4 | Weekend tip rate has `delta: "+2.1pp vs weekday"` + `sentiment: "positive"` (green) |
| 3B Adult | 4 | High-earner avg hours has `delta: "+4.7h vs low"` — relative comparison baked in |
| 3C Lahman | 3 | `value: "2000s"` for decade — string, not number. Layer 3 must render as-is |
| 3D Ames | 3 | `value: "StoneBr"` — a neighborhood name as the primary KPI. Not numeric. |
| 4A Taxi | 4 | Each card is a time-slot trip count — the "KPI row as mini-leaderboard" pattern |
| 4B Adult | 3 | Each card is a factor's top bucket — the "KPI row as factor summary" pattern |
| 4C Lahman | 2 | Padded with subagent/section count — fallback when real KPIs are sparse |
| 4D Ames | 4 | Each card is a price tier's leader — the "KPI row as tier summary" pattern |

**Layer 3 implications for KPI cards:**
- Values are heterogeneous: `$319,000`, `23.9%`, `StoneBr`, `2000s`, `710,135`. Render as-is.
- Deltas are strings: `"+2.1pp vs weekday"`, `"+4.7h vs low"`, `"$319,000"`. Render as-is with sentiment color.
- Sentiment is a 3-value enum: `positive` (green), `negative` (red), `neutral` (grey).
- Not every card has a delta — `null` delta means no comparison badge.

### Section title observations

The agent writes section titles as **insights, not labels**:

| Bad (label) | Good (insight — what the agent actually wrote) |
|---|---|
| "Tipping analysis" | "Weekend riders tip more, but the gap is time-of-day driven" |
| "Education breakdown" | "Education is the single biggest wedge" |
| "Championship data" | "Championship density by decade" |
| "Price comparison" | "The StoneBr premium — top 3 Ames neighborhoods compared" |
| "Time slot 1" | "Night slot: 230,555 trips" |

**Layer 3 implication:** section titles should be rendered as bold heading text, NOT as tab labels or sidebar items. They're sentences, not keywords. Reserve ~80 characters of width.

### Drill-down observations

4 of 8 moderate specs have drill-downs. When present, they look like:

```json
{
  "label": "Show me only 11PM-2AM rides",
  "query_hint": "hour BETWEEN 23 AND 2"
}
```

**What Layer 3 should do with these:**
- Render as a clickable pill/button below the section
- On click, the frontend sends the `query_hint` back to Layer 2 as a new user message (e.g., "Filter the analysis to: hour BETWEEN 23 AND 2")
- Layer 2 re-runs with the filter and produces a new simple or moderate spec
- This creates a **drill-down interaction loop**: moderate dashboard → click → deeper view → click → even deeper

**This is the path to PowerBI-like interactivity** without building a full BI tool. The agent decides what the drill-down options are; the frontend just renders them as buttons.

---

## 5. Complex Mode — What Layer 3 Renders

### What the agent gives

A multi-page report spec with: `report_title`, `report_subtitle`, `executive_summary` (headline + key_findings + recommendations), `pages[]` (each with id, title, purpose, layout, blocks), `appendix` (methodology + data_quality_notes + open_questions), `plan_ids[]`, `subagent_ids[]`, `memory_refs[]`.

### What the user should see

A **paginated document viewer** — not a single-page scroll. Think Google Slides or Notion, not a long-scroll blog post.

```
┌──────────────────────────────────────────────────────────────────┐
│  NYC Taxi January 2024 Operations Strategy                      │
│  For Priya Sharma, NYC TLC Operations                           │
│                                                                  │
│  ┌─ Executive Summary ────────────────────────────────────────┐ │
│  │                                                            │ │
│  │  Revenue is concentrated in 4 peak hours; off-peak has     │ │
│  │  surge-pricing upside.                                     │ │
│  │                                                            │ │
│  │  Key findings:                                             │ │
│  │  • 60% of revenue comes from 10am-2pm and 5pm-9pm peaks   │ │
│  │  • Tip rate is ~30% higher on credit-card rides vs cash    │ │
│  │  • Overnight trips show longest distances + highest fares  │ │
│  │                                                            │ │
│  │  Recommendations:                                          │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │ 🟡 Shift surge pricing to 23:00-02:00               │  │ │
│  │  │    Est +$1.2M/month · Evidence: page 1 →             │  │ │
│  │  ├──────────────────────────────────────────────────────┤  │ │
│  │  │ 🟢 Incentivize cash rides via app                    │  │ │
│  │  │    Data quality improvement · Evidence: page 3 →     │  │ │
│  │  └──────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  [Page 1: Profitability by hour]  [Page 2: Off-peak gap]        │
│  [Page 3: Payment mix]           [Appendix]                     │
└──────────────────────────────────────────────────────────────────┘
```

### UI components needed (beyond what moderate already has)

1. **Page navigation** — tabs, sidebar, or bottom pagination. Each page is a separate view.
2. **Executive summary card** — a styled hero block with headline, bullet-point key_findings, and recommendation cards.
3. **Recommendation card** — action, rationale, expected_impact, confidence badge (🟢 high / 🟡 medium / 🔴 low), clickable `evidence_page` link that navigates to the referenced page.
4. **Appendix page** — methodology as prose, data_quality_notes as bullet list, open_questions as bullet list.
5. **Cross-reference links** — inline links from one page to another (e.g., "see page 3 for payment analysis").
6. **Memory provenance badge** — for phase-2 follow-ups, a small callout: "Findings recalled from prior session (Apr 11) — not re-derived."

### Page block rendering

Each page contains a `blocks[]` array with mixed types:

| Block type | What to render |
|---|---|
| `kpi_row` | Horizontal strip of KPI cards (same as moderate) |
| `hero_chart` | Full-width chart, large, visually dominant |
| `chart_grid` | 2-3 smaller charts in a CSS grid |
| `table` | Data table with sortable columns |
| `narrative` | Markdown prose paragraph |
| `callout` | Highlighted box with icon (info=blue, warning=yellow, action=green) |
| `comparison` | Two-column side-by-side block |

**From the 8 complex specs, block types actually emitted:** `kpi_row`, `narrative`, `callout`. No `hero_chart` or `table` blocks in the stress test output (because Tier 5 focused on structural completeness over per-page visual richness). These types exist in the schema and should be implemented for production.

### Phase-2 follow-up rendering

4 of the 8 complex specs are phase-2 follow-ups (new session after server restart). They have a distinctive shape:

```json
{
  "mode": "complex",
  "report_title": "Follow-up: NYC Taxi January 2024 Operations Strategy",
  "executive_summary": {
    "headline": "Follow-up to yesterday's report. Key findings recalled from persistent memory, no re-derivation.",
    "key_findings": [
      "Phase-1 concluded: 60% of revenue comes from 10am-2pm and 5pm-9pm peaks",
      "Phase-1 concluded: Tip rate is ~30% higher on credit-card rides vs cash"
    ]
  },
  "pages": [{
    "id": "followup_page_1",
    "title": "Yesterday's conclusions (recalled from memory)",
    "blocks": [
      { "type": "callout", "style": "info", "text": "Retrieved via memory_get(dataset, ds_xxx, tier5_5A_taxi_conclusions)" },
      { "type": "narrative", "text": "- 60% of revenue comes from 10am-2pm and 5pm-9pm peaks\n- ..." }
    ]
  }],
  "memory_refs": [{"scope": "dataset", "key": "tier5_5A_taxi_conclusions"}],
  "phase": 2
}
```

**Layer 3 should render phase-2 specs with a visual distinction:**
- A banner at the top: "📎 This report references a prior analysis from [date]. Findings were recalled from persistent memory, not re-derived."
- The `callout` block with `style: "info"` should render as a blue info box with the memory provenance path
- Key findings prefixed with "Phase-1 concluded:" should be visually distinguished (lighter text, or an icon indicating they're recalled, not fresh)

---

## 6. Data Flow: How Parquet Files Reach the Chart Library

The render spec contains `data_ref` fields pointing to parquet files. Here's how the data flows:

```
Agent (Layer 2)                    Server (Layer 1)                     Frontend (Layer 3)
     │                                   │                                    │
     │  run_python(code)                 │                                    │
     │ ──────────────────────────────►   │                                    │
     │                                   │  sandbox writes                    │
     │                                   │  fare_hist.parquet                 │
     │                                   │  to OUTPUT_DIR                     │
     │                                   │                                    │
     │   response: files_created:        │                                    │
     │   [{name: "fare_hist.parquet",    │                                    │
     │     path: "fare_hist.parquet"}]   │                                    │
     │ ◄──────────────────────────────   │                                    │
     │                                   │                                    │
     │  render_spec.json includes:       │                                    │
     │  data_ref: "files/fare_hist.parquet"                                   │
     │                                   │                                    │
     │                                   │  GET /datasets/{id}/output/        │
     │                                   │  fare_hist.parquet                 │
     │                                   │ ◄──────────────────────────────    │
     │                                   │  ──────────────────────────────►   │
     │                                   │  (parquet bytes)                   │
     │                                   │                                    │
     │                                   │                                    │ parquet → DataFrame
     │                                   │                                    │ → chart library
     │                                   │                                    │ → render
```

### What Layer 3 needs to implement

1. **Parquet reader in the browser.** Options:
   - **apache-arrow JS** (recommended): `import { tableFromIPC } from 'apache-arrow'` — reads parquet into a columnar table, zero-copy where possible
   - **parquet-wasm**: smaller bundle, WebAssembly-based parquet reader
   - **Fallback**: agent emits CSV alongside parquet (worse performance, but simpler)

2. **Data resolver.** Given a `data_ref` like `"files/fare_hist.parquet"`, Layer 3 fetches from `GET /datasets/{dataset_id}/output/{filename}`. This endpoint needs to exist in Layer 1 (currently `output/` is just a filesystem directory — an explicit file-serving endpoint would be cleaner).

3. **Chart library.** Options by complexity:
   - **Plotly.js** (heavy but comprehensive): handles bar, line, scatter, histogram, box, heatmap, funnel, sankey out of the box
   - **Observable Plot** (lighter, modern): clean API, good defaults, fewer chart types
   - **ECharts** (most PowerBI-like): interactive, supports large datasets, dashboard-oriented
   - **D3** (low-level): maximum control, most work

   **My recommendation: ECharts for moderate/complex, Observable Plot for simple.** ECharts' built-in dashboard layout, tooltip, zoom, and drill-down interactions align directly with the moderate mode's needs. Observable Plot's simplicity is ideal for the single-chart simple mode.

4. **Encoding mapper.** The render spec's `encoding` field maps column names to chart axes:
   ```json
   { "x": "lower_bound", "y": "trip_count" }
   ```
   Layer 3 reads the parquet columns, maps `encoding.x` → x-axis data, `encoding.y` → y-axis data, `encoding.color` → series split. The mapping is always explicit — the agent never says "figure out the axes."

---

## 7. Interactivity Patterns Layer 3 Should Support

### 7.1 Drill-down (moderate mode)

When the user clicks a drill-down button like `"Show me only 11PM-2AM rides"`:
1. Layer 3 sends the `query_hint` as a new message to Layer 2
2. Layer 2 runs a filtered analysis and returns a new render_spec
3. Layer 3 replaces the current view with the new spec (or opens it as a child panel)

This is **agent-driven interactivity** — the agent decides what drill-downs are available, not the frontend. Layer 3 just renders them as buttons.

### 7.2 Page navigation (complex mode)

Pages in a complex spec are explicitly ordered. Layer 3 renders navigation tabs or a sidebar. Clicking a page tab swaps the visible content. No agent call needed — the data is already in the spec.

### 7.3 Recommendation evidence links (complex mode)

Each recommendation has an `evidence_page` field pointing to a page ID. Layer 3 renders this as a clickable link that scrolls/navigates to that page. Pure frontend — no agent call.

### 7.4 Memory provenance (complex mode, phase 2)

When `memory_refs` is present, Layer 3 shows a provenance badge. Clicking it could show the raw memory entry (fetched via `GET /memory/{scope}/{scope_id}/{key}`).

### 7.5 Plan audit trail (moderate + complex)

When `plan_id` is present, Layer 3 can fetch `GET /plans/{plan_id}/audit` and render the state machine timeline (created → submit → approve → execute → done). This gives the user transparency into the agent's process.

### 7.6 What Layer 3 should NOT do

- **Don't let users edit the render spec.** That's Layer 2's job (via a new user message).
- **Don't re-aggregate data.** The parquet files contain pre-computed aggregates. Layer 3 reads and renders, not computes.
- **Don't choose chart types.** The agent already chose. Layer 3 respects the `type` field.
- **Don't reorder sections/pages.** The agent already ordered them by narrative importance.

---

## 8. Responsive Layout Strategy

### Simple mode

Mobile-first. Single column. KPI card at top, narrative below, chart below that.

```
┌──────────────────┐
│     $18.18       │  ← hero KPI
│ Avg January fare │
├──────────────────┤
│ Narrative text   │  ← 2-4 sentences
├──────────────────┤
│ ┌──────────────┐ │
│ │   Chart      │ │  ← full-width
│ └──────────────┘ │
│ Caption          │
└──────────────────┘
```

### Moderate mode

Desktop: 2-3 column grid per section. Tablet: 2 columns. Mobile: stack to single column.

```
Desktop:                           Mobile:
┌───────────────────────┐          ┌─────────────┐
│ KPI  KPI  KPI  KPI   │          │    KPI      │
├───────────────────────┤          │    KPI      │
│ Section title         │          │    KPI      │
│ ┌──────┐ ┌──────┐    │          │    KPI      │
│ │Chart1│ │Chart2│    │          ├─────────────┤
│ └──────┘ └──────┘    │          │ Section     │
│ [Drill down →]       │          │ ┌─────────┐ │
├───────────────────────┤          │ │ Chart 1 │ │
│ Section title         │          │ └─────────┘ │
│ ┌──────────────────┐  │          │ ┌─────────┐ │
│ │ Full-width chart │  │          │ │ Chart 2 │ │
│ └──────────────────┘  │          │ └─────────┘ │
└───────────────────────┘          │ [Drill →]  │
                                   └─────────────┘
```

### Complex mode

Desktop: sidebar page nav + content area. Tablet: top tab nav + content. Mobile: hamburger menu + full-width content.

```
Desktop:                                    Mobile:
┌────────────┬──────────────────────┐       ┌─────────────────┐
│ ☰ Pages    │  Exec Summary       │       │ ☰ Menu          │
│            │  ─────────────      │       ├─────────────────┤
│ • Summary  │  Key findings...    │       │ Exec Summary    │
│ • Page 1   │  Recommendations... │       │ Key findings... │
│ • Page 2   │                     │       │ [Page 1 →]      │
│ • Page 3   │  ┌────────────────┐ │       │ [Page 2 →]      │
│ • Appendix │  │ Rec card       │ │       └─────────────────┘
│            │  │ Evidence: p1 → │ │
│            │  └────────────────┘ │
└────────────┴──────────────────────┘
```

---

## 9. What Layer 1 Needs to Add for Layer 3

### 9.1 File serving endpoint for output artifacts

Currently: `OUTPUT_DIR` is a filesystem path. The frontend has no HTTP endpoint to fetch parquet files.

**Needed:** `GET /datasets/{dataset_id}/output/{filename}` that serves files from `data/{ds_id}/output/`. Content-type should be `application/octet-stream` for parquet, `application/json` for render_spec.json.

### 9.2 Render spec persistence endpoint

Currently: render specs are JSON files written by the Python sandbox to OUTPUT_DIR. There's no typed Layer 1 endpoint to store/retrieve them.

**Needed:** `POST /renders` that validates the spec against the mode-specific schema, persists it, and returns a `render_id`. `GET /renders/{render_id}` to retrieve. This gives Layer 3 a clean URL to point at for each dashboard.

### 9.3 Session-to-render lookup

Currently: there's no way for Layer 3 to ask "what's the latest render spec for this session?"

**Needed:** `GET /renders?session_id=X&latest=true` that returns the most recent render_id for a session. Layer 3 calls this on page load to know what to display.

---

## 10. The Technology Stack Recommendation for Layer 3

Based on what the render specs actually demand:

| Requirement | Recommendation | Why |
|---|---|---|
| **Framework** | Next.js (App Router) or SvelteKit | Server-side rendering for exec summaries, client-side for charts. Both handle the page-navigation patterns of complex mode well |
| **Chart library** | ECharts (via `echarts-for-react` or `svelte-echarts`) | Covers bar/line/scatter/histogram/box/kpi. Built-in tooltips, zoom, responsive. Dashboard-first design philosophy. PowerBI aesthetic achievable |
| **Parquet reader** | `apache-arrow` WASM or `hyparquet` | Reads parquet in the browser without a server-side intermediary |
| **Layout engine** | CSS Grid + Tailwind | `grid-template-columns` maps directly to `single`/`two_col`/`three_col`/`hero_plus_grid` layouts |
| **State management** | Zustand (React) or Svelte stores | Tracks current mode, active page, loaded data refs, session context |
| **Markdown rendering** | `react-markdown` or `svelte-markdown` | Narratives may contain simple markdown (bold, bullet points) |
| **KPI card component** | Custom (Tailwind) | Small enough to build custom; no library needed. Value + label + delta badge + sentiment color |

### Minimal viable component tree

```
<App>
├── <ModeRouter mode={spec.mode}>
│   ├── <SimpleView>
│   │   ├── <HeroKPI headline={spec.headline} />
│   │   ├── <Narrative text={spec.narrative} />
│   │   ├── <ChartContainer visual={spec.visuals[0]} />
│   │   └── <CitationsFooter citations={spec.citations} />
│   │
│   ├── <ModerateView>
│   │   ├── <DashboardHeader title subtitle />
│   │   ├── <KPIRow cards={spec.kpi_row} />
│   │   ├── {spec.sections.map(s =>
│   │   │     <Section title narrative layout>
│   │   │       <LayoutGrid layout={s.layout}>
│   │   │         {s.visuals.map(v => <ChartContainer visual={v} />)}
│   │   │       </LayoutGrid>
│   │   │       <DrillDownBar items={s.drill_downs} />
│   │   │     </Section>
│   │   │   )}
│   │   ├── <CaveatsFooter caveats={spec.caveats} />
│   │   └── <PlanLink planId={spec.plan_id} />
│   │
│   └── <ComplexView>
│       ├── <ReportHeader title subtitle />
│       ├── <PageNav pages={spec.pages} />
│       ├── <ExecSummaryPage summary={spec.executive_summary} />
│       ├── {spec.pages.map(p =>
│       │     <ReportPage title purpose layout>
│       │       {p.blocks.map(b => <BlockRenderer block={b} />)}
│       │     </ReportPage>
│       │   )}
│       ├── <AppendixPage appendix={spec.appendix} />
│       └── <ProvenanceBadge memoryRefs={spec.memory_refs} phase={spec.phase} />
│
├── <DataLoader>  // fetches parquet files referenced by data_ref
└── <ChartRenderer type encoding data />  // maps encoding to ECharts options
```

### Bundle size budget

| Component | Estimated size |
|---|---|
| ECharts (tree-shaken) | ~300 KB gzipped |
| Apache Arrow WASM | ~150 KB gzipped |
| Next.js/Svelte runtime | ~80 KB gzipped |
| Tailwind CSS (purged) | ~15 KB gzipped |
| App code | ~50 KB gzipped |
| **Total** | **~600 KB gzipped** |

Target: first meaningful paint in <1.5 seconds on a 4G connection. Achievable if parquet files are small (they are — aggregated data, typically 1-50 KB per chart).

---

## 11. The Three User Journeys

### Journey 1: Quick lookup (Simple mode)

```
User: "What was the average fare?"
                    │
                    ▼
         ┌──────────────────┐
         │   Layer 2 runs   │  ← 2-3 tool calls, no plan
         │   1 SQL + 1 Py   │
         └────────┬─────────┘
                  │
                  ▼  render_spec.json (mode=simple)
         ┌──────────────────┐
         │   Layer 3 shows  │
         │   $18.18 + chart │  ← single card, <5 seconds to consume
         └──────────────────┘
```

### Journey 2: Guided analysis (Moderate mode)

```
User: "How busy were we last week?"
                    │
                    ▼
         ┌──────────────────┐
         │   Layer 2 asks   │  "What does 'busy' mean?"
         │   user answers   │  "Trip count by day"
         └────────┬─────────┘
                  │
                  ▼  plan submitted + approved
         ┌──────────────────┐
         │   Layer 2 runs   │  ← 4-6 tool calls
         │   SQL + Python   │
         └────────┬─────────┘
                  │
                  ▼  render_spec.json (mode=moderate)
         ┌──────────────────┐
         │   Layer 3 shows  │  ← dashboard with KPIs, sections, drill-downs
         │   3-section dash │
         └────────┬─────────┘
                  │  user clicks drill-down
                  ▼
         ┌──────────────────┐
         │   Layer 2 runs   │  ← filtered re-analysis
         │   with filter    │
         └────────┬─────────┘
                  │
                  ▼  new render_spec (simple or moderate)
```

### Journey 3: Deep research (Complex mode)

```
User: "Build me a full operations strategy report"
                    │
                    ▼
         ┌──────────────────┐
         │   Layer 2 plans  │  8-step plan with 3 subagents
         │   user approves  │
         └────────┬─────────┘
                  │
         ┌───────┼───────┐
         ▼       ▼       ▼
       Sub A   Sub B   Sub C   ← parallel analysis
         │       │       │
         └───────┼───────┘
                 │  memory bridge
                 ▼
         ┌──────────────────┐
         │   Master stitches│  ← integration step
         │   3-page report  │
         └────────┬─────────┘
                  │
                  ▼  render_spec.json (mode=complex) + memory write
         ┌──────────────────────────────────────────┐
         │   Layer 3 shows paginated report         │
         │   Exec summary → Pages → Appendix        │
         │   Recommendations with evidence links    │
         └──────────────────────────────────────────┘
                  │
                  │  next day, new session
                  ▼
         ┌──────────────────┐
         │   Layer 2 recalls│  ← memory_get finds yesterday's conclusions
         │   phase 1 memory │
         └────────┬─────────┘
                  │
                  ▼  render_spec.json (mode=complex, phase=2)
         ┌──────────────────────────────────────────┐
         │   Layer 3 shows follow-up with           │
         │   "recalled from prior session" badge    │
         └──────────────────────────────────────────┘
```

---

## 12. What the Stress Test Proves About Layer 3 Feasibility

1. **The render spec contract is stable.** 24 specs, 3 modes, 0 structural ambiguities. A frontend developer can implement against this schema with confidence.

2. **Data volumes are frontend-friendly.** The largest parquet file in the stress test was ~50 KB (the Taxi tip_agg with 48 rows). Chart rendering will be instant.

3. **The agent makes good layout decisions.** Section titles are insights not labels. KPI card composition is sensible. Chart types match data shapes (with the noted exception of over-reliance on bar charts). The frontend doesn't need to second-guess the agent's choices.

4. **Drill-downs create a natural interaction loop.** The agent proposes what the user might want to explore next. The frontend renders it as a button. The click generates a new agent query. This is achievable without building a full BI engine.

5. **Cross-session continuity is real.** Phase-2 specs prove that "the report remembers yesterday" works end-to-end through Layer 1's memory. Layer 3 just needs to render the provenance badge.

6. **Complex mode is a document, not a dashboard.** The page-based structure with exec summary + analysis pages + appendix maps naturally to a tabbed document viewer, not a grid dashboard. Layer 3's complex-mode UI is closer to Google Docs than PowerBI.

---

## 13. Summary: What Layer 3 Must Be

Layer 3 is a **spec-driven rendering engine** that:

1. **Receives a render_spec.json** from Layer 2 (via a Layer 1 endpoint)
2. **Routes by mode**: simple → card, moderate → dashboard, complex → document
3. **Fetches data** from parquet files referenced by `data_ref`
4. **Renders charts** using the explicit `type` and `encoding` fields — never guesses
5. **Renders narrative** as markdown — the agent writes the text, the frontend just displays it
6. **Renders KPIs** with value + label + delta + sentiment color — always as-is, no reformatting
7. **Renders drill-downs** as clickable buttons that trigger a new Layer 2 query
8. **Renders pages** as a tabbed/paginated document with sidebar navigation
9. **Renders provenance** when `memory_refs` is present — badges showing cross-session continuity
10. **Renders plan audit trails** when `plan_id` is present — transparency into the agent's process

It is NOT:
- A BI tool (it doesn't build queries or choose aggregations)
- A chart configurator (it doesn't let users pick chart types)
- A data editor (it doesn't modify datasets)
- An agent (it doesn't reason about what to show)

It is the screen that shows what the analyst decided. The analyst is Layer 2. The data is Layer 1. The screen is Layer 3.
