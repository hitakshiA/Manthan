# Contributing to Manthan

Thanks for your interest in contributing! Manthan welcomes contributions that improve the data pipeline, semantic layer, or agent toolbox.

## Quick Start

```bash
git clone https://github.com/hitakshiA/Manthan.git
cd Manthan
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # add your OPENROUTER_API_KEY
pytest tests/ -q       # 294 tests, ~14s
```

## Development Workflow

1. **Branch** from `main` — use `feature/`, `fix/`, or `docs/` prefixes
2. **Write code** — follow existing patterns in `src/`
3. **Lint** — `ruff format src/ tests/ && ruff check src/ tests/`
4. **Test** — `pytest tests/ -q` (all must pass)
5. **PR** — one clear purpose per PR, reference any related issue

## Code Standards

- **Python 3.12+** with type hints everywhere
- **Ruff** for formatting (88-col line length) and linting
- **pydantic** for all data models
- **No secrets in code** — everything goes through `Settings` from `.env`
- **Tests required** for new features — follow existing patterns in `tests/`

## Architecture Rules

- Layer 1 is a **toolbox, not an agent** — it does not reason or decide
- Every endpoint is **stateless** except where explicitly documented (sessions, memory, plans)
- SQL identifiers must go through `validate_identifier()` or `quote_identifier()`
- LLM calls happen **only** in `src/profiling/classifier.py` — nowhere else in Layer 1

## Adding a New Tool

1. Add the core logic in `src/tools/` or `src/core/`
2. Add the HTTP router in `src/api/`
3. Mount the router in `src/main.py`
4. Add the tool to `_TOOL_MANIFEST` in `src/api/tool_discovery.py`
5. Write tests in `tests/`
6. Run the full suite

## Reporting Issues

Use [GitHub Issues](https://github.com/hitakshiA/Manthan/issues). Include:
- What you expected vs what happened
- Steps to reproduce
- Python version and OS
