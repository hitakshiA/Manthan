<p align="center">
  <img src="manthan-ui/public/logo.svg" width="48" height="48" alt="Manthan" />
</p>

<h1 align="center">Manthan</h1>

<p align="center">
  Upload a dataset. Ask a question. Get a dashboard.<br/>
  No SQL. No notebooks. No hallucinated answers.
</p>

<p align="center">
  <a href="https://github.com/hitakshiA/Manthan/actions/workflows/ci.yml"><img src="https://github.com/hitakshiA/Manthan/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green.svg" alt="License" /></a>
  <a href="http://142.93.213.82:8000"><img src="https://img.shields.io/badge/demo-live-brightgreen.svg" alt="Live" /></a>
</p>

---

## What it does

Manthan is a 3-layer autonomous data analyst. You give it a CSV, it builds a semantic understanding of every column, then answers natural-language questions with real SQL, real Python, and structured visual output — dashboards, reports, and KPI cards.

The difference from other "talk to your data" tools: **Manthan asks before it guesses.**

When the system isn't sure whether `age` is something you'd sum or group by, it stops and asks you. Your answer gets locked into the semantic layer *before* any analysis runs. Every query afterward is grounded in definitions you confirmed.

## How it works

```
Upload CSV ──→ Classify columns ──→ Ask user if unsure ──→ Build semantic layer
                                                                   │
                                    ┌──────────────────────────────┘
                                    ▼
              User asks question ──→ Agent reasons through decision gates:
                                    │
                                    ├─ Ambiguous? → Ask user to clarify
                                    ├─ Complex? → Show plan, wait for approval
                                    └─ Execute → SQL + Python + render output
                                                                   │
                                    ┌──────────────────────────────┘
                                    ▼
                              Structured output:
                              • Simple — one KPI + one chart
                              • Moderate — multi-section dashboard
                              • Complex — multi-page report with recommendations
```

**Three layers:**

| Layer | What it does | Key feature |
|-------|-------------|-------------|
| **Layer 1** — Data Pipeline | Ingests files, classifies columns via LLM, builds a semantic layer (DCD), materializes Gold tables | Asks the user when classifier confidence is low |
| **Layer 2** — Agent | Autonomous reasoning loop with 8 tools (SQL, Python, plans, memory, subagents) | Shows its plan before executing; saves conclusions to cross-session memory |
| **Layer 3** — Frontend | React workspace that renders SSE events in real-time and displays structured output | Agent activity feed, inline HITL cards, dashboard/report rendering |

## The semantic layer

Without it, the LLM sees raw DDL and guesses:

```sql
-- LLM sees: payment_type INTEGER → SUM(payment_type) = 7,421,832 ← garbage
```

With Manthan's Data Context Document:

```yaml
payment_type:
  role: dimension         # don't aggregate this
  description: "1=Credit, 2=Cash, 3=No charge, 4=Dispute"
```

The agent never sums a dimension. Every query is grounded in confirmed column roles, aggregation rules, and verified sample queries.

## Run it

```bash
git clone https://github.com/hitakshiA/Manthan.git && cd Manthan
cp .env.example .env   # add your OPENROUTER_API_KEY
docker compose up --build
```

Open **http://localhost:8000** — the frontend and API run on the same port.

Or without Docker:

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload

# Frontend (separate terminal)
cd manthan-ui && npm install && npm run dev
```

**Get an API key:** Sign up at [openrouter.ai](https://openrouter.ai) — free tier works out of the box.

### Live demo: **http://142.93.213.82:8000**

---

## Resilience

Manthan doesn't crash when an LLM is unavailable. The classification pipeline uses a 3-model cascade: if the primary model fails, it tries two fallbacks. If all three are down, a deterministic heuristic classifier takes over using column name patterns, data types, and cardinality — no LLM needed. The agent layer has independent retry logic with automatic model failover.

| Failure | What happens |
|---------|-------------|
| Primary model rate-limited | Instant cascade to fallback model |
| All models down | Heuristic classifier runs (deterministic, no LLM) |
| Agent tool call fails | Retries up to 3 times, then explains the issue to the user |
| Server restarts | Datasets rehydrate from disk; memory persists via SQLite WAL |

---

## Benchmark results

Tested against [CORGI](https://github.com/corgibenchmark/CORGI) — synthetic business databases with 18–35 tables, 25–68 foreign keys, and queries requiring 7+ JOINs on average.

| Database | Tables | FKs | Rows | Result |
|----------|--------|-----|------|--------|
| Food Delivery | 32 | 25 | 75K | **8/8 passed** |
| Clothing E-commerce | 35 | 40 | 140K | **6/6 passed** |
| Car Rental | 31 | 68 | 169K | **6/6 passed** |

The agent discovers 30+ tables autonomously, writes multi-table JOINs, and produces structured answers without human guidance.

---

## API surface

### Data Pipeline
| Method | Endpoint | What it does |
|--------|----------|-------------|
| POST | `/datasets/upload` | Upload → classify → clarify → materialize |
| POST | `/datasets/upload-multi` | Multi-file with auto FK detection |
| GET | `/datasets/{id}/schema` | Compact JSON schema with column roles |
| GET | `/datasets/{id}/context` | Full semantic layer as YAML |
| GET | `/datasets/{id}/output/{file}` | Artifacts (render_spec.json, parquet) |

### Agent
| Method | Endpoint | What it does |
|--------|----------|-------------|
| POST | `/agent/query` | SSE stream — real-time thinking, tool calls, results |
| POST | `/agent/query/sync` | Synchronous — returns full result + render_spec |

### Tools & Primitives
| Method | Endpoint | What it does |
|--------|----------|-------------|
| POST | `/tools/sql` | Read-only SQL against Gold tables |
| POST | `/tools/python` | Stateful Python sandbox |
| POST | `/plans` | Structured plan with approval gate |
| POST | `/ask_user` | Blocking human-in-the-loop question |
| POST | `/memory` | Cross-session persistent store |
| POST | `/subagents/spawn` | Isolated parallel analysis |

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI + uvicorn |
| Database | DuckDB (in-memory + Parquet) |
| LLM | OpenRouter (any model — configured via .env) |
| Persistence | SQLite WAL (memory + plan audit) |
| Sandbox | Python subprocess REPL with persistent state |
| Frontend | React 19 + Vite + Tailwind CSS 4 + ECharts |
| State | Zustand |

All backend dependencies are Apache 2.0, MIT, or BSD licensed.

---

## Project structure

```
src/
  agent/            # Layer 2: agent loop, tools, prompt, SSE events
  api/              # FastAPI routers (datasets, tools, agent, plans, memory...)
  core/             # Config, LLM client, rate limiting, memory, plans
  ingestion/        # Bronze: format loaders, FK detection, registry
  profiling/        # Silver: LLM + heuristic classifier, clarification
  semantic/         # DCD schema, render spec models + normalizer
  materialization/  # Gold: optimizer, summarizer, verified queries
  tools/            # SQL tool, Python session manager
  sandbox/          # REPL worker subprocess

manthan-ui/
  src/
    api/            # HTTP client layer
    stores/         # Zustand state (agent, datasets, session, UI)
    components/
      layout/       # App shell: ActivityBar, Sidebar, MainWorkspace
      workspace/    # QueryInput, ActivityFeed, ActivityEvent
      render/       # SimpleView, ModerateView, ComplexView + charts
      hitl/         # AskUserCard, PlanApprovalCard
      datasets/     # Uploader, ColumnClassifier, SchemaViewer

tests/              # 294 tests across 7 directories
```

## Development

```bash
pip install -e ".[dev]"
ruff format src/ tests/ && ruff check src/ tests/
pytest tests/ -q
```

## License

[Apache 2.0](LICENSE)
