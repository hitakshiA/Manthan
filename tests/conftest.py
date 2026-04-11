"""Shared pytest fixtures.

Concrete fixtures (sample CSVs, in-memory DuckDB connections, a pre-built
DCD, a mock LLM client) are added as the corresponding domain modules come
online. For now this module exists so that every test module has a stable
import target and pytest can discover project-root fixtures.
"""
