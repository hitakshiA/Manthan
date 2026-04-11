"""Concrete loaders for each supported source type.

Each loader implements a minimal ``detect(path) -> bool`` / ``load(path,
connection, table_name) -> LoadResult`` interface so that the ingestion
gateway can route inputs to the right loader without branching on file
extensions.
"""
