"""Agent tool interface exposed to downstream analysis agents.

The four tools — ``get_context``, ``run_sql``, ``run_python``, ``get_schema``
— are the only surface through which analysis agents may access data. Each
tool is deliberately narrow and auditable; free-form code execution is
confined to the Docker sandbox managed by ``run_python``.
"""
