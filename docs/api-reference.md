# API Reference

All endpoints are mounted on the FastAPI app in `src/main.py`. JSON is
the default content-type; the context endpoint returns YAML.

## Health

### `GET /health`

Liveness probe.

```json
{ "status": "ok" }
```

## Datasets

### `POST /datasets/upload`

Upload a file (CSV / TSV / TXT / Parquet / Excel / JSON) and run the
full Bronze → Silver → Gold pipeline.

Multipart form field: `file` (required).

Returns `200 DatasetSummary`:

```json
{
  "dataset_id": "ds_abcdef1234",
  "name": "Nexaretail Sales",
  "source_type": "csv",
  "row_count": 500,
  "column_count": 12,
  "status": "gold",
  "created_at": "2026-04-11T14:30:00Z"
}
```

Errors: `400` ingestion / file issues, `502` LLM failures after retries.

### `POST /datasets/connect`

Connect to a remote database and pull one table through the full
pipeline. The connection string is used only during the `ATTACH` call
and never persisted.

```json
{
  "source_type": "postgres",
  "connection_string": "host=localhost port=5432 user=... password=... dbname=...",
  "source_table": "public.orders",
  "destination_table": "orders_local"
}
```

Supported `source_type`: `postgres`, `mysql`, `sqlite`.

Returns `200 DatasetSummary`.

### `GET /datasets`

List every registered dataset.

### `GET /datasets/{dataset_id}`

Return a `DatasetSummary` for one dataset.

### `GET /datasets/{dataset_id}/context?query=...`

Return the DCD as YAML. When `query` is provided the DCD is
query-pruned via `src.semantic.pruner.prune_for_query` before
serialization — temporal and metric columns are always retained.

Response: `application/x-yaml`.

### `PUT /datasets/{dataset_id}/context`

Apply user edits to the generated DCD. Column names referenced in the
request are validated against the Gold table's catalog.

```json
{
  "dataset_name": "Nexaretail Retail Sales",
  "columns": [
    { "name": "revenue", "description": "Net revenue in USD (returns excluded)" },
    { "name": "quantity", "role": "auxiliary" }
  ],
  "agent_instructions": [
    "Always filter by channel = 'Online' unless the user says otherwise"
  ],
  "known_limitations": [
    "Data before 2024-03 was migrated from the legacy system"
  ]
}
```

Returns `200 DatasetSummary`. `400` on unknown columns or schema
mismatch.

### `GET /datasets/{dataset_id}/schema`

Return a compact `SchemaSummary` (column list + roles + descriptions +
sensitivity + verified queries). Cheaper for agents than pulling the
full DCD.

### `DELETE /datasets/{dataset_id}`

Remove the dataset from the registry. Does not delete on-disk artifacts.

### `GET /datasets/{dataset_id}/progress`

Return accumulated progress events for the pipeline (bronze / silver /
gold with timestamps). Useful for polling.

## Websocket status

### `WS /datasets/{dataset_id}/status`

Streams progress events as the pipeline advances. Sends a final
`{"stage": "done"}` frame when the run terminates.

## Tools (agent-facing)

### `POST /tools/sql`

Execute a read-only SQL query against the Gold tables for a dataset.

```json
{ "dataset_id": "ds_abcdef1234", "sql": "SELECT region, SUM(revenue) FROM gold_sales_abcdef1234 GROUP BY region", "max_rows": 1000 }
```

Only `SELECT` and `WITH` statements are allowed; comments are stripped
and DDL/DML keywords rejected outright. 30-second timeout is enforced
via `connection.interrupt()`.

```json
{
  "columns": ["region", "total"],
  "rows": [["North", 125000.5], ["South", 98000.0]],
  "row_count": 2,
  "truncated": false,
  "execution_time_ms": 3.2
}
```

### `POST /tools/python`

Execute Python code in the Docker sandbox with the dataset's Parquet
files mounted read-only at `/data` and a writable `/output` directory.

```json
{ "dataset_id": "ds_abcdef1234", "code": "print(df.shape); df.to_csv('/output/summary.csv')", "timeout_seconds": 60 }
```

The sandbox container is `manthan-sandbox:latest` with 2 GB RAM / 2 CPUs
/ network disabled. The prelude auto-loads the first Parquet file as
`df` (pandas) and exposes `con` (DuckDB) and `OUTPUT_DIR` (pathlib).

```json
{
  "stdout": "(500, 12)\n",
  "stderr": "",
  "files_created": [
    { "name": "summary.csv", "path": "/data/ds_abcdef1234/output/summary.csv", "size": 2048 }
  ],
  "execution_time_ms": 820.3,
  "exit_code": 0,
  "timed_out": false
}
```

Errors: `404` unknown dataset, `503` Docker daemon unavailable or image
missing.

### `GET /tools/context/{dataset_id}?query=...`

Same as `GET /datasets/{id}/context` but wraps the YAML in a JSON
envelope (`{ "dataset_id": ..., "yaml": ... }`).

### `GET /tools/schema/{dataset_id}`

Returns a `SchemaSummary` — identical payload to
`GET /datasets/{id}/schema`.

## Clarification

### `GET /clarification/{dataset_id}`

Return the list of pending clarification questions for a dataset. The
profiling agent emits a question when it sees a short column name
(≤3 chars), a numeric column classified as auxiliary, or a metric with
≤3 distinct values.

### `POST /clarification/{dataset_id}`

Submit answers. Each answer chooses a final role (and aggregation for
metrics) for one question.

```json
{
  "answers": [
    { "question_id": "q_a1b2", "column_name": "amt", "chosen_role": "metric", "aggregation": "SUM" }
  ]
}
```

## Observability

### `GET /metrics`

Return a snapshot of in-process counters and histograms (ingestion
rows, profiling datasets, materialization summary tables, quality
scores, etc.).

```json
{
  "counters": { "ingestion.rows_loaded": 10500, "profiling.datasets_total": 21 },
  "histograms": {
    "materialization.quality_success_percent": { "count": 21, "avg": 98.4, "min": 92.0, "max": 100.0 }
  }
}
```
