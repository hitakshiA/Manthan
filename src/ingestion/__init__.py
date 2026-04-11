"""Bronze stage: source detection, validation, and raw data loading into DuckDB.

Accepts files (CSV, Excel, JSON, Parquet) and database connections, detects
the source type, validates the payload for basic viability, and emits a raw
table in DuckDB that the Silver (profiling) stage operates on. No semantic
interpretation happens here — the goal is fidelity to the source.
"""
