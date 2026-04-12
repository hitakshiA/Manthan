# Manthan

**Seamless Self-Service Intelligence — Talk to Data**

[![CI](https://github.com/hitakshiA/Manthan/actions/workflows/ci.yml/badge.svg)](https://github.com/hitakshiA/Manthan/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

Upload any dataset. Get a semantic understanding of your data. Query it with SQL or Python. Build dashboards with an autonomous agent. Manthan is the data + semantic + agent toolbox layer — Layer 1 of a 3-layer autonomous data analyst.

## Run It (1 command)

```bash
# 1. Clone + configure
git clone https://github.com/hitakshiA/Manthan.git && cd Manthan
cp .env.example .env   # add your OPENROUTER_API_KEY

# 2. Run
docker compose up --build

# 3. Use
curl http://localhost:8000/health
curl -X POST http://localhost:8000/datasets/upload -F "file=@your_data.csv"
```

Or without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload
```

## Architecture

```mermaid
graph TB
    subgraph "Layer 1 - Data + Semantic + Toolbox"
        Upload["Upload CSV/Parquet/Excel/JSON"] --> Bronze["Bronze\nLoad into DuckDB"]
        Bronze --> Silver["Silver\nLLM classify columns"]
        Silver --> Gold["Gold\nMaterialize + summarize"]
        Gold --> DCD["Data Context Document"]

        subgraph "Agent Toolbox"
            SQL["SQL tool"] & Python["Python sandbox"] & Plans["Plan approval"] & AskUser["Ask user"] & Memory["Memory store"] & Subagents["Subagents"]
        end
        DCD --> SQL & Python
    end

    Agent["Layer 2 Agent"] -->|calls| SQL & Python & Plans & AskUser & Memory & Subagents
    Agent -->|render_spec| UI["Layer 3 Frontend"]
```

## Pipeline

```mermaid
flowchart LR
    A[Upload] --> B[Bronze]
    B --> C[Silver]
    C --> D{LLM up?}
    D -->|Yes| E[Qwen3/gpt-oss\n3-5s]
    D -->|No| F[Heuristic\n0s]
    E & F --> G[Gold]
    G --> H[Ready]
```

Three models cascade automatically: **Qwen3 Next 80B** (3.5s) -> **gpt-oss-120b** (4.3s) -> **Nemotron Nano** (20.7s) -> heuristic fallback (instant). Each on a different provider so rate limits don't stack.

## Configuration

```bash
# .env
OPENROUTER_API_KEY=sk-or-...         # required
OPENROUTER_FREE_TIER=true            # true=$0 rate-limited, false=paid fast
OPENROUTER_MODEL=qwen/qwen3-next-80b-a3b-instruct
```

## API

### Data Pipeline
| Endpoint | What it does |
|---|---|
| `POST /datasets/upload` | Upload file, run full Bronze->Silver->Gold pipeline |
| `POST /datasets/upload-multi` | Upload related files, auto-detect foreign keys |
| `GET /datasets/{id}/context` | Get semantic DCD as YAML |
| `GET /datasets/{id}/schema` | Compact JSON schema |

### Analysis Tools
| Endpoint | What it does |
|---|---|
| `POST /tools/sql` | Read-only SQL + temp table scratchpad |
| `POST /tools/python` | Stateful Python sandbox (df, con, OUTPUT_DIR pre-loaded) |
| `GET /tools/list` | Tool manifest for agent discovery |

### Agent Primitives
| Endpoint | What it does |
|---|---|
| `POST /plans` | Structured plan with DCD citations + approval gate |
| `POST /ask_user` | Blocking human-in-the-loop clarification |
| `POST /memory` | Persistent cross-session key-value store (SQLite) |
| `POST /subagents/spawn` | Isolated multi-agent workspaces with memory bridging |
| `POST /tasks` | Per-session agent task tracking |

## Formats Supported

CSV, TSV, Parquet, Excel (xlsx/xls), JSON/JSONL, Postgres, MySQL, SQLite.

Multi-file uploads auto-detect FK relationships via value-containment analysis.

## Stress Test Results

Tested with 4 real datasets, 5 complexity tiers, 24 scenarios — all passing:

| Dataset | Rows | Cols | Time |
|---|---|---|---|
| NYC Taxi Jan 2024 | 2.96M | 19 | 8.4s |
| UCI Adult | 48.8K | 15 | 6.1s |
| Ames Housing | 2.9K | 82 | 17.9s |
| Lahman Baseball (10 files) | 366K | 7-50/table | 51s |

## Project Structure

```
src/
  api/              # 12 FastAPI routers
  core/             # State, config, LLM client, memory, plans
  ingestion/        # Bronze: loaders, registry, FK detection
  profiling/        # Silver: stats, LLM + heuristic classifier
  semantic/         # DCD schema, generator, render spec models
  materialization/  # Gold: optimizer, summarizer, query gen
  tools/            # SQL tool, Python session manager
  sandbox/          # Python REPL worker
tests/              # 294 tests
```

## Dev

```bash
pip install -e ".[dev]"
ruff format src/ tests/ && ruff check src/ tests/
pytest tests/ -q
```

## License

[Apache 2.0](LICENSE)
