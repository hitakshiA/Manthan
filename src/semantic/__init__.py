"""Data Context Document (DCD) management.

The DCD is Manthan's semantic contract with downstream agents: a YAML artifact
describing columns, metrics, temporal grain, PII classifications, quality
caveats, agent instructions, and verified queries. This module owns the DCD
schema, generator, editor, and query-relevant schema pruner.
"""
