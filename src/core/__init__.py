"""Shared infrastructure: configuration, logging, database, LLM, exceptions.

``core`` is the foundation of the application. By convention (see
``CONTRIBUTING.md``) this module has **zero imports** from any other ``src/``
module, and every other module is allowed to import from it. Dependency flow:

    api -> tools -> materialization -> profiling -> ingestion -> core
"""
