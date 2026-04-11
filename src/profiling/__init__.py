"""Silver stage: autonomous exploration, classification, and PII detection.

Hosts the Profiling Agent — a ReAct-loop agent that perceives a raw table via
DuckDB, classifies column roles with an LLM, detects PII with a layered
pipeline (column-name heuristics + Presidio + statistical checks), proposes
computed metrics, and emits a Data Context Document consumed by the semantic
and materialization stages.
"""
