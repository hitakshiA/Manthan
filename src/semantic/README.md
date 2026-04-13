# semantic/ — Data Context Document + Render Spec

This module defines the two key contracts in Manthan:

1. **DCD (Data Context Document)** — the semantic layer between raw data and the agent
2. **Render Spec** — the visualization contract between the agent and the frontend

## Data Context Document

The DCD is a YAML artifact encoding everything about a dataset: column roles, descriptions, statistics, aggregation rules, verified queries, and agent instructions. Generated during Layer 1 ingestion, read by the agent before every query.

```yaml
columns:
  - name: payment_type
    role: dimension           # NOT a metric
    description: "1=Credit, 2=Cash, 3=No charge, 4=Dispute"
    aggregation: null         # don't aggregate this
    completeness: 1.0
    cardinality: 4
```

**Key files**: `schema.py` (Pydantic models), `generator.py` (builds DCD from profiling), `editor.py` (applies user edits), `pruner.py` (query-relevant column pruning)

## Render Spec

Three output modes the agent can produce:

| Mode | When | Output |
|------|------|--------|
| **Simple** | Single fact (1-2 tool calls) | Headline KPI + 1-3 charts + narrative |
| **Moderate** | Comparison/breakdown (3-6 steps) | KPI row + 3+ story sections with charts |
| **Complex** | Report/strategy (6+ steps) | Executive summary + paginated pages + appendix |

**Key files**: `render_spec.py` (Pydantic models + `normalize_render_spec()` for bridging agent output to strict types)
