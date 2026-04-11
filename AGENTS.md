# AGENTS.md — Manthan

> Read this file before writing any code, making any commit, or adding any feature.
> This is the single source of truth for how this codebase is maintained.

---

## Identity

**Product**: Manthan — Seamless Self-Service Intelligence
**License**: Apache 2.0 (all code, all commits, no exceptions)
**Hackathon**: NatWest Code for Purpose — India Hackathon
**Problem Statement**: Talk to Data
**Repository visibility**: PRIVATE during hackathon. May become public post-review.

---

## Non-Negotiable Rules

These come directly from the NatWest submission guidelines and transcript. Violating any of these risks disqualification.

### Licensing & Compliance

- Every file in this repository is Apache 2.0 licensed.
- Every dependency must be Apache 2.0, MIT, BSD, or PSF licensed. No GPL, AGPL, LGPL, SSPL, or BUSL dependencies. Check before you `pip install` or `npm install` anything.
- Every commit must be signed off with DCO: `git commit -s -m "message"`. No unsigned commits. Ever.
- Every team member uses ONE personal email address for all commits throughout the hackathon. Do not switch emails between commits.
- Use personal GitHub accounts only. No institutional, corporate, or shared accounts.

### Security & Secrets

- **Never commit**: passwords, API keys, tokens, secrets, real customer data, .env files.
- Store all secrets in environment variables. Reference them in code via `os.getenv()`.
- Provide `.env.example` listing every required variable with placeholder values.
- If a secret accidentally gets committed, rotate it immediately and force-push to remove from history. Treat it as compromised.
- All data used in development and demos must be synthetic. Use Faker, Mockaroo, or generate with AI. Names like "John Doe", emails like "test@example.com". No real PII from any source, including Kaggle datasets with real names.

### Code Honesty

- The README must describe only features that are implemented and working.
- Partially implemented features must be explicitly labeled: "Dashboard page is present but charts are static and not connected to live data."
- Never list planned or future features as if they exist.
- Limitations section is mandatory. Be honest about what doesn't work.
- Future improvements section is separate from features.

---

## Repository Structure

```
manthan/
├── AGENTS.md                    # This file. Read first.
├── README.md                    # Project documentation (golden source for judges)
├── LICENSE                      # Apache 2.0 full text
├── .env.example                 # All required environment variables
├── .gitignore                   # Standard Python + Node ignores
├── pyproject.toml               # Python project config and dependencies
├── docker-compose.yml           # Local development stack
│
├── src/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application entry point
│   │
│   ├── ingestion/               # Bronze stage: source detection, validation, loading
│   │   ├── __init__.py
│   │   ├── gateway.py           # Source type detection and routing
│   │   ├── validators.py        # File validation rules
│   │   ├── loaders/
│   │   │   ├── __init__.py
│   │   │   ├── csv_loader.py
│   │   │   ├── excel_loader.py
│   │   │   ├── json_loader.py
│   │   │   ├── parquet_loader.py
│   │   │   └── db_loader.py     # PostgreSQL, MySQL, SQLite via DuckDB scanners
│   │   └── registry.py          # Dataset registry (tracks all loaded datasets)
│   │
│   ├── profiling/               # Silver stage: autonomous exploration and annotation
│   │   ├── __init__.py
│   │   ├── agent.py             # Profiling agent ReAct loop orchestration
│   │   ├── statistical.py       # DuckDB SUMMARIZE + ydata-profiling wrappers
│   │   ├── classifier.py        # LLM-powered column role classification
│   │   ├── pii_detector.py      # Presidio integration + heuristic layers
│   │   ├── enricher.py          # Computed metrics, temporal grain detection
│   │   └── clarification.py     # Interactive question generation and handling
│   │
│   ├── semantic/                # Data Context Document management
│   │   ├── __init__.py
│   │   ├── schema.py            # DCD YAML schema definition and validation
│   │   ├── generator.py         # Assemble DCD from profiling outputs
│   │   ├── editor.py            # User edits to DCD (CRUD operations)
│   │   └── pruner.py            # Query-relevant schema extraction for agents
│   │
│   ├── materialization/         # Gold stage: optimization and export
│   │   ├── __init__.py
│   │   ├── optimizer.py         # Sort order, ENUM creation, COMMENT attachment
│   │   ├── summarizer.py        # Summary table generation
│   │   ├── exporter.py          # Parquet export with compression
│   │   ├── query_generator.py   # Verified query pair generation
│   │   └── quality.py           # Great Expectations validation suite
│   │
│   ├── tools/                   # Agent tool interface (downstream-facing)
│   │   ├── __init__.py
│   │   ├── sql_tool.py          # run_sql: read-only DuckDB query execution
│   │   ├── python_tool.py       # run_python: Docker sandbox management
│   │   ├── context_tool.py      # get_context: DCD retrieval and pruning
│   │   └── schema_tool.py       # get_schema: lightweight schema summary
│   │
│   ├── analysis/                # Analysis agent layer (future: the "talk to data" agents)
│   │   └── __init__.py          # Placeholder for analysis agent implementation
│   │
│   ├── api/                     # FastAPI route definitions
│   │   ├── __init__.py
│   │   ├── datasets.py          # Dataset upload, connect, list, delete
│   │   ├── tools.py             # Agent tool endpoints
│   │   ├── clarification.py     # Interactive question endpoints
│   │   └── health.py            # Health check and status
│   │
│   ├── core/                    # Shared infrastructure
│   │   ├── __init__.py
│   │   ├── config.py            # Application configuration from env vars
│   │   ├── database.py          # DuckDB connection management
│   │   ├── llm.py               # OpenRouter API client (free-tier models)
│   │   ├── logger.py            # Structured JSON logging
│   │   └── exceptions.py        # Custom exception hierarchy
│   │
│   └── sandbox/                 # Docker sandbox configuration
│       ├── Dockerfile           # Python sandbox image definition
│       ├── requirements.txt     # Sandbox-specific Python packages
│       └── prelude.py           # Auto-run script that loads data into DuckDB/pandas
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures (sample datasets, DuckDB connections)
│   ├── test_ingestion/
│   ├── test_profiling/
│   ├── test_semantic/
│   ├── test_materialization/
│   ├── test_tools/
│   └── test_api/
│
├── data/                        # Local dataset storage (gitignored)
│   └── .gitkeep
│
├── scripts/                     # Helper scripts
│   ├── generate_demo_data.py    # Create synthetic NexaRetail dataset
│   └── seed_database.py         # Load demo data for development
│
├── docs/
│   ├── architecture.md          # System architecture overview with diagrams
│   ├── data-context-schema.md   # DCD YAML specification
│   └── api-reference.md         # API endpoint documentation
│
└── assets/                      # Screenshots, diagrams for README
    └── .gitkeep
```

### Rules for Structure

- No single-file projects. Ever. Logic is separated by domain.
- Each directory has an `__init__.py` with a module-level docstring explaining what this module does.
- No file exceeds 300 lines. If it does, split by responsibility.
- No circular imports. Dependency flows downward: `api → tools → materialization → profiling → ingestion → core`.
- `core/` has zero imports from any other `src/` module. Everything else can import from `core/`.

---

## Coding Standards

### Python

- Python 3.12+ only.
- Type hints on every function signature. No exceptions.
  ```python
  def load_csv(file_path: Path, sample_size: int = 10000) -> duckdb.DuckDBPyRelation:
  ```
- Docstrings on every public function, class, and module. Google style.
  ```python
  def detect_temporal_grain(date_column: Series) -> str:
      """Detect the temporal grain of a date column by analyzing gaps.

      Examines the most common interval between consecutive dates
      to determine if data is daily, weekly, monthly, or yearly.

      Args:
          date_column: Pandas Series containing date values.

      Returns:
          One of: "daily", "weekly", "monthly", "quarterly", "yearly", "irregular".

      Raises:
          ValueError: If the column contains fewer than 2 non-null dates.
      """
  ```
- Variable names are descriptive. `column_profile` not `cp`. `dataset_registry` not `dr`. `pii_detection_results` not `results`.
- No abbreviations in variable names unless universally understood (`df` for DataFrame, `sql` for SQL strings, `llm` for language model).
- Constants are UPPER_SNAKE_CASE and live in `core/config.py`.
- No magic numbers in code. Define constants.
  ```python
  # Bad
  if cardinality < 100:

  # Good
  ENUM_CARDINALITY_THRESHOLD = 100
  if cardinality < ENUM_CARDINALITY_THRESHOLD:
  ```
- Use `pathlib.Path` for all file paths. Never string concatenation.
- Use `httpx` for HTTP calls (async-first). Not `requests`.
- Use `pydantic` for all data models and API schemas.
- Formatting: `ruff format` (88 char line length). Linting: `ruff check`.
- No bare `except:` clauses. Catch specific exceptions.
- No `print()` statements. Use the structured logger from `core/logger.py`.

### SQL (DuckDB)

- All SQL queries are parameterized. Never string-format user input into SQL.
  ```python
  # Bad
  con.sql(f"SELECT * FROM {table_name} WHERE region = '{region}'")

  # Good
  con.sql("SELECT * FROM ? WHERE region = ?", [table_name, region])
  ```
- Read-only queries only in the tool interface. DDL/DML only during ingestion and materialization.
- All generated SQL is validated against the DuckDB catalog before execution (table exists, columns exist).
- SQL keywords in UPPERCASE. Table/column names in lowercase.

### Error Handling

- Every external call (LLM API, file I/O, Docker, DuckDB) is wrapped in try/except with specific exception types.
- Errors are logged with full context (dataset_id, stage, operation).
- User-facing errors are clear and actionable. Internal errors are logged but surfaced as generic messages.
- Never swallow exceptions silently.
  ```python
  # Bad
  try:
      result = llm_client.classify(columns)
  except Exception:
      pass

  # Good
  try:
      result = llm_client.classify(columns)
  except httpx.TimeoutException:
      logger.warning("LLM classification timed out", dataset_id=dataset_id, attempt=attempt)
      raise ProfilingRetryableError("LLM service timeout, retrying") from None
  ```

---

## Git Workflow

### Branch Naming

```
main                             # Production-ready. Never push directly.
feature/{short-description}      # New features: feature/excel-loader
fix/{short-description}          # Bug fixes: fix/csv-encoding-detection
refactor/{short-description}     # Code restructuring: refactor/profiling-agent-loop
docs/{short-description}         # Documentation: docs/api-reference
```

### Commit Messages

Format: `type(scope): description`

```
feat(ingestion): add Excel file loader via DuckDB spatial extension
fix(profiling): handle empty string columns in PII detection
refactor(tools): extract SQL validation into dedicated module
docs(readme): add architecture diagram and installation steps
test(profiling): add unit tests for temporal grain detection
chore(deps): update duckdb to 1.3.0
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
Scope: module name from the repo structure (ingestion, profiling, semantic, materialization, tools, api, core, sandbox)

Every commit is signed off:
```bash
git commit -s -m "feat(ingestion): add Excel file loader via DuckDB spatial extension"
```

### Pull Request Checklist

Before merging any PR:

- [ ] All tests pass (`pytest tests/`)
- [ ] No new linting errors (`ruff check src/`)
- [ ] Code is formatted (`ruff format src/`)
- [ ] Type hints on all new functions
- [ ] Docstrings on all new public functions
- [ ] No secrets, API keys, or real data in the diff
- [ ] Commit(s) signed off with DCO (`-s` flag)
- [ ] README updated if feature is user-facing
- [ ] .env.example updated if new env vars added

---

## Adding New Features

### Adding a New Data Source Loader

1. Create `src/ingestion/loaders/{source}_loader.py`
2. Implement the loader interface:
   ```python
   class NewSourceLoader:
       """Loads data from {source} into DuckDB.

       Handles {specific edge cases for this source}.
       """

       def detect(self, input_path: Path) -> bool:
           """Return True if this loader handles the given input."""

       def load(self, input_path: Path, connection: duckdb.DuckDBPyConnection, table_name: str) -> LoadResult:
           """Load data into DuckDB and return metadata about the load."""
   ```
3. Register the loader in `src/ingestion/gateway.py`
4. Add tests in `tests/test_ingestion/test_{source}_loader.py` with at least:
   - Happy path (valid file loads correctly)
   - Edge cases (empty file, malformed data, encoding issues)
   - Type inference validation (spot check that DuckDB inferred correct types)
5. Update `.env.example` if the source requires credentials
6. Update `docs/architecture.md` with the new source in the ingestion section

### Adding a New Agent Tool

1. Create `src/tools/{tool_name}_tool.py`
2. Implement the tool interface:
   ```python
   class NewTool:
       """Brief description of what this tool does.

       Used by analysis agents when they need to {specific capability}.
       """

       def execute(self, dataset_id: str, **params) -> ToolResult:
           """Execute the tool and return structured results."""

       def validate_params(self, **params) -> None:
           """Validate parameters before execution. Raise ValueError if invalid."""
   ```
3. Register the tool in `src/api/tools.py` as a new endpoint
4. Document the tool's input/output schema in `docs/api-reference.md`
5. Add integration tests that verify the tool against a known dataset
6. Update the DCD schema if the tool produces new metadata

### Adding a New Analysis Agent (Future)

1. Create module under `src/analysis/{agent_name}/`
2. The agent must:
   - Read the DCD via `get_context` tool before any query
   - Respect PII flags: never expose columns marked `sensitivity: pii` in outputs
   - Use `run_sql` for data retrieval and `run_python` for analysis/visualization
   - Include provenance in responses: which columns, which filters, which aggregation
   - Handle errors from tools gracefully (retry with modified approach)
3. Agent system prompts must include:
   - The `agent_instructions` section from the DCD
   - The `verified_queries` as few-shot examples
   - The `quality.known_limitations` as caveats to surface
4. Add tests that verify the agent handles all four NatWest use cases:
   - Change analysis ("Why did X change?")
   - Comparison ("A vs B")
   - Breakdown ("What makes up X?")
   - Summary ("Weekly summary of key metrics")

---

## Environment Configuration

All configuration flows through `src/core/config.py` which reads from environment variables.

```bash
# .env.example — copy to .env and fill in values

# LLM Configuration
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=google/gemma-4-27b-it:free      # Free tier model
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# DuckDB
DUCKDB_MEMORY_LIMIT=4GB
DUCKDB_THREADS=4
DUCKDB_TEMP_DIRECTORY=/tmp/duckdb

# Sandbox
SANDBOX_IMAGE=manthan-sandbox:latest
SANDBOX_MEMORY_LIMIT=2g
SANDBOX_CPU_LIMIT=2
SANDBOX_TIMEOUT_SECONDS=60
SANDBOX_NETWORK_DISABLED=true

# Storage
DATA_DIRECTORY=/data
MAX_UPLOAD_SIZE_MB=500

# Server
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
LOG_FORMAT=json

# PII Detection
PRESIDIO_NLP_MODEL=en_core_web_lg
PII_CONFIDENCE_THRESHOLD=0.7
PII_SAMPLE_SIZE=100
```

### Configuration Rules

- No default values for secrets. The application must fail to start if a required secret is missing.
- Non-secret configs have sensible defaults in `config.py`.
- Never read `os.getenv()` outside of `core/config.py`. All other modules import from config.
- Config is validated at startup using pydantic `BaseSettings`.

---

## Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific module
pytest tests/test_profiling/ -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

### Test Data

- All test data lives in `tests/fixtures/`
- Test CSVs are small (10-100 rows), synthetic, and checked into git
- No real data in test fixtures
- `conftest.py` provides shared fixtures:
  - `sample_csv_path`: Path to a basic test CSV
  - `duckdb_connection`: Fresh in-memory DuckDB connection per test
  - `sample_dcd`: A pre-built Data Context Document for testing
  - `mock_llm_client`: Mocked LLM client with deterministic responses

### Test Categories

- **Unit tests**: Test individual functions in isolation. Mock external dependencies. Fast.
- **Integration tests**: Test module interactions (profiling agent against real DuckDB). Slower.
- **System tests**: End-to-end from file upload to agent query. Require Docker. Slowest.

Mark slow tests:
```python
@pytest.mark.slow
def test_full_pipeline_csv_to_agent_query():
    ...
```

Run fast tests only: `pytest tests/ -v -m "not slow"`

---

## Documentation

### README.md Requirements (from NatWest Guidelines)

The README is the judges' first impression. It must contain:

1. **Overview** (2-5 sentences): What Manthan does, what problem it solves, who it's for.
2. **Features**: Bullet list of implemented, working features only.
3. **Architecture**: System diagram showing the data flow pipeline.
4. **Tech Stack**: Languages, frameworks, databases, AI/ML libraries with versions.
5. **Install and Run**:
   - Prerequisites (Python 3.12+, Docker, etc.)
   - Clone, install dependencies, configure environment
   - Start the application
   - Step-by-step, assume basic technical skills but no knowledge of our code
6. **Usage Examples**: Screenshots, sample inputs/outputs, example API calls.
7. **Limitations**: Honest description of what doesn't work or is incomplete.
8. **Future Improvements**: What we'd build with more time.
9. **Team**: Contributors with single email per person.
10. **License**: Apache 2.0.

### Inline Documentation

- Every module (`__init__.py`) has a docstring explaining the module's purpose.
- Every class has a docstring explaining its responsibility.
- Comments explain "why", not "what". The code should explain "what".
  ```python
  # Bad: increment counter
  counter += 1

  # Good: retry count tracks LLM API failures for circuit breaker logic
  retry_count += 1
  ```

---

## Dependency Management

### Adding a New Dependency

1. Check the license. Must be Apache 2.0, MIT, BSD, or PSF. No exceptions.
2. Check if it's actively maintained (last commit within 6 months).
3. Add to `pyproject.toml` under the appropriate group:
   - `[project.dependencies]` for runtime dependencies
   - `[project.optional-dependencies.dev]` for development-only tools
   - `[project.optional-dependencies.sandbox]` for sandbox container packages
4. Pin to minimum version: `duckdb >= 1.2.0`, not `duckdb == 1.2.0`.
5. Update this file's dependency notes if the package serves a non-obvious purpose.
6. Run full test suite to verify no conflicts.

### Sandbox Dependencies

The Docker sandbox has its own `requirements.txt` at `src/sandbox/requirements.txt`. This is separate from the main application dependencies. Sandbox packages are installed at image build time and include data analysis libraries (pandas, plotly, scipy, etc.) that agents use.

Changes to sandbox dependencies require rebuilding the Docker image:
```bash
docker build -t manthan-sandbox:latest -f src/sandbox/Dockerfile .
```

---

## Performance Considerations

- DuckDB queries on datasets under 1M rows should complete in under 1 second.
- Profiling agent should complete the full Silver stage in under 60 seconds for datasets under 100K rows (including LLM calls).
- Parquet export should complete in under 10 seconds for datasets under 1M rows.
- Sandbox container cold start should be under 5 seconds.
- API endpoints should respond in under 200ms (excluding tool execution time).

If any operation exceeds these thresholds, it's a performance bug. Log it, profile it, fix it.

---

## What Judges Will Evaluate

From the hackathon transcripts, judges care about (in rough priority order):

1. **Does it work?** Can they clone the repo, follow the README, and get a running system?
2. **Code quality**: Readable, structured, well-named, documented. Not "clever."
3. **Innovation**: Does the solution approach the problem in a novel way?
4. **Impact**: Would this actually be useful to real users?
5. **Presentation**: Clear README, clean repo, honest about limitations.
6. **Deployment**: Is it hosted somewhere they can try without cloning? (Strong differentiator.)

Everything in this file serves point 2. The README serves point 5. The architecture serves points 3 and 4. Deployment is handled separately.

---

## Quick Reference

```bash
# Setup
git clone <repo>
cd manthan
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_lg
cp .env.example .env  # Fill in values
docker build -t manthan-sandbox:latest -f src/sandbox/Dockerfile .

# Development
ruff format src/                 # Format code
ruff check src/                  # Lint
pytest tests/ -v                 # Run tests
uvicorn src.main:app --reload    # Start dev server

# Committing
git add .
git commit -s -m "type(scope): description"
git push origin feature/your-branch

# Demo data
python scripts/generate_demo_data.py
python scripts/seed_database.py
```
