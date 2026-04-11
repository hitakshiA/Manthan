"""Gold stage: agent-ready materialization.

Transforms the raw table into an optimized, annotated dataset: sort order,
DuckDB ENUM types for low-cardinality dimensions, COMMENT ON attachments,
pre-computed summary tables, verified query pairs, Parquet export with
Zstandard compression, and a Great Expectations quality suite.
"""
