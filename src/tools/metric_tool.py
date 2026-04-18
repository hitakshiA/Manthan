"""``compute_metric`` — the governed happy-path for named business metrics.

Instead of asking the agent to hand-roll SQL for ``revenue`` (and risk
dropping the ``status='delivered'`` filter that defines it), the
agent names the metric + dimensions + filters and this module
composes the SQL from the declared :class:`DcdMetric` contract.

Everything the metric's definition guarantees — the aggregation
expression, the baked-in filter, the aggregation_semantics — is
applied automatically. Two agents, two sessions, two models produce
the same number for the same metric call.

The composed SQL is also the source-of-truth for the ``numeric_claim``
lineage event emitted in Phase 3, so the "How was this calculated?"
drawer can show the exact query that produced the number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from src.core.state import AppState
from src.ingestion.base import quote_identifier
from src.semantic.schema import DataContextDocument, DcdEntity, DcdMetric


@dataclass(slots=True)
class MetricExecution:
    """The full, auditable result of a ``compute_metric`` call."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    sql_used: str
    metric_slug: str
    metric_label: str
    metric_description: str | None
    metric_expression: str
    metric_filter: str | None
    metric_unit: str | None
    dimensions: list[str]
    extra_filters: dict[str, Any]
    grain: str | None
    elapsed_ms: float


class MetricRequest(BaseModel):
    """Body of a ``compute_metric`` call from the agent."""

    entity: str = Field(..., description="Entity slug (e.g. 'orders').")
    metric: str = Field(..., description="Metric slug (e.g. 'revenue').")
    dimensions: list[str] = Field(
        default_factory=list,
        description="Columns to GROUP BY. Must be declared as dimension columns.",
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Additional filters ANDed with the metric's declared filter. "
            "Keys are column names. Values may be scalar, list "
            "(IN clause), or a dict ``{'gte': ..., 'lte': ...}`` for "
            "ranges."
        ),
    )
    grain: str | None = Field(
        default=None,
        description=(
            "Optional time grain (``daily``, ``weekly``, ``monthly``, "
            "``quarterly``, ``yearly``). Requires the entity to have a "
            "temporal column. Overrides the metric's default_grain."
        ),
    )
    limit: int = Field(default=500, ge=1, le=10_000)


class ComputeMetricError(Exception):
    """Raised when a metric call can't be honored."""


def _resolve_entity(state: AppState, slug: str) -> tuple[DataContextDocument, DcdEntity]:
    dcd = state.resolve_entity(slug)
    if dcd is None:
        known = sorted(state.entity_to_dataset.keys())
        raise ComputeMetricError(
            f"Unknown entity '{slug}'. Known entities: {known}"
        )
    entity = dcd.dataset.entity
    if entity is None:
        raise ComputeMetricError(
            f"Entity '{slug}' resolves to a pre-v1.1 dataset without an "
            "entity block. Re-ingest or wait for the boot-time migration."
        )
    return dcd, entity


def _find_metric(entity: DcdEntity, metric_slug: str) -> DcdMetric:
    slug = metric_slug.lower()
    for m in entity.metrics:
        if m.slug.lower() == slug or m.label.lower() == slug:
            return m
        if slug in {s.lower() for s in m.synonyms}:
            return m
    available = [m.slug for m in entity.metrics]
    raise ComputeMetricError(
        f"Metric '{metric_slug}' is not declared on entity '{entity.slug}'. "
        f"Declared: {available or '(none — add one via the schema editor)'}."
    )


def _temporal_column(dcd: DataContextDocument) -> str | None:
    """Return the primary temporal column for the entity, if any."""
    for col in dcd.dataset.columns:
        if col.role == "temporal":
            return col.name
    return dcd.dataset.temporal.column


def _render_filter_clause(
    column: str,
    value: Any,
    dcd: DataContextDocument,
) -> str:
    """Render one user-supplied filter into SQL. Scalar / list / range."""
    col_sql = quote_identifier(column)
    col_type = _column_dtype(dcd, column)
    if isinstance(value, dict):
        fragments: list[str] = []
        if "gte" in value:
            fragments.append(f"{col_sql} >= {_sql_literal(value['gte'], col_type)}")
        if "gt" in value:
            fragments.append(f"{col_sql} > {_sql_literal(value['gt'], col_type)}")
        if "lte" in value:
            fragments.append(f"{col_sql} <= {_sql_literal(value['lte'], col_type)}")
        if "lt" in value:
            fragments.append(f"{col_sql} < {_sql_literal(value['lt'], col_type)}")
        if "eq" in value:
            fragments.append(f"{col_sql} = {_sql_literal(value['eq'], col_type)}")
        if fragments:
            return "(" + " AND ".join(fragments) + ")"
        return "TRUE"
    if isinstance(value, list):
        if not value:
            return "FALSE"
        rendered = ", ".join(_sql_literal(v, col_type) for v in value)
        return f"{col_sql} IN ({rendered})"
    return f"{col_sql} = {_sql_literal(value, col_type)}"


def _column_dtype(dcd: DataContextDocument, column: str) -> str:
    for col in dcd.dataset.columns:
        if col.name.lower() == column.lower():
            return col.dtype.upper()
    return ""


def _sql_literal(value: Any, dtype: str) -> str:
    """Format a Python value as a SQL literal for DuckDB."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    # Strings, dates, timestamps — always quote and escape single-quotes.
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _grain_expr(col: str, grain: str) -> str:
    """DuckDB DATE_TRUNC expression for a named grain."""
    grain_l = grain.lower()
    mapping = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
        "quarterly": "quarter",
        "yearly": "year",
    }
    key = mapping.get(grain_l, grain_l)
    return f"DATE_TRUNC('{key}', {quote_identifier(col)}) AS period"


def compose_sql(
    dcd: DataContextDocument,
    entity: DcdEntity,
    metric: DcdMetric,
    request: MetricRequest,
) -> str:
    """Build the SQL statement for a metric call.

    Rendering order mirrors the semantic contract so audit readers
    can trace each clause to its declaration:

        1. Select: metric expression aliased with metric slug (+
           optional temporal grain + dimensions).
        2. From: the entity's physical_table. Rollups aren't used
           here — rollups are an optimization, not a semantic
           boundary. Phase 5 plumbing can add a rollup-router.
        3. Where: the metric's declared filter + any user-supplied
           filters (ANDed).
        4. Group by: grain + dimensions.
        5. Order by: metric expression DESC (most interesting first).
        6. Limit.
    """
    select_parts: list[str] = []

    # Only bucket by time if the caller explicitly asked for a grain.
    # ``metric.default_grain`` is a HINT surfaced to the UI, not a
    # silent default — if it auto-fired when the agent asked for a
    # scalar total, every "what's our revenue?" would come back as
    # a 33-row monthly series the agent then has to re-summarize.
    grain = request.grain
    if grain:
        temporal = _temporal_column(dcd)
        if temporal:
            select_parts.append(_grain_expr(temporal, grain))

    for dim in request.dimensions:
        select_parts.append(f"{quote_identifier(dim)}")

    metric_alias = f"{metric.expression} AS {quote_identifier(metric.slug)}"
    select_parts.append(metric_alias)

    from_clause = f"FROM {quote_identifier(entity.physical_table)}"

    where_parts: list[str] = []
    if metric.filter:
        where_parts.append(f"({metric.filter})")
    for col, val in request.filters.items():
        where_parts.append(_render_filter_clause(col, val, dcd))
    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    group_parts: list[str] = []
    if grain:
        group_parts.append("period")
    for dim in request.dimensions:
        group_parts.append(quote_identifier(dim))
    group_clause = "GROUP BY " + ", ".join(group_parts) if group_parts else ""

    # ORDER BY doesn't make sense for a scalar (no GROUP BY); skip it.
    if not group_parts:
        order_clause = ""
    elif grain and not request.dimensions:
        # Time series: order by period ascending is more useful.
        order_clause = "ORDER BY period ASC"
    else:
        order_clause = f"ORDER BY {quote_identifier(metric.slug)} DESC"

    limit_clause = f"LIMIT {request.limit}"

    sql = "\n".join(
        [
            "SELECT " + ", ".join(select_parts),
            from_clause,
            *([where_clause] if where_clause else []),
            *([group_clause] if group_clause else []),
            *([order_clause] if order_clause else []),
            limit_clause,
        ]
    )
    return sql


def compute_metric(state: AppState, request: MetricRequest) -> MetricExecution:
    """Resolve, compose, validate, execute.

    All four steps live here so the agent loop has one clean entry
    point — it never sees a partial result, and the returned object
    carries everything needed for the Phase 3 ``numeric_claim`` event.
    """
    import time

    dcd, entity = _resolve_entity(state, request.entity)
    metric = _find_metric(entity, request.metric)

    # Validate that requested dimensions are either dimension columns
    # or temporal columns on the entity (any declared column name is OK
    # — the validator won't see our composed SQL because we trust
    # ourselves to build it correctly, so we pre-check here).
    declared = {c.name.lower() for c in dcd.dataset.columns}
    for dim in request.dimensions:
        if dim.lower() not in declared:
            raise ComputeMetricError(
                f"Dimension '{dim}' is not a declared column on entity "
                f"'{entity.slug}'. Declared: {sorted(declared)}"
            )
    if metric.valid_dimensions:
        whitelist = {d.lower() for d in metric.valid_dimensions}
        for dim in request.dimensions:
            if dim.lower() not in whitelist:
                raise ComputeMetricError(
                    f"Metric '{metric.slug}' can't be sliced by '{dim}'. "
                    f"Valid dimensions: {sorted(whitelist)}"
                )

    sql = compose_sql(dcd, entity, metric, request)

    t0 = time.perf_counter()
    with state.connection_lock:
        try:
            rel = state.connection.execute(sql)
        except duckdb.Error as exc:
            raise ComputeMetricError(
                f"Metric query failed: {exc}. Composed SQL:\n{sql}"
            ) from exc
        columns = [d[0] for d in rel.description]
        rows = rel.fetchmany(request.limit)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    truncated = len(rows) == request.limit
    row_count = len(rows)

    return MetricExecution(
        columns=columns,
        rows=[list(r) for r in rows],
        row_count=row_count,
        truncated=truncated,
        sql_used=sql,
        metric_slug=metric.slug,
        metric_label=metric.label,
        metric_description=metric.description,
        metric_expression=metric.expression,
        metric_filter=metric.filter,
        metric_unit=metric.unit,
        dimensions=list(request.dimensions),
        extra_filters=dict(request.filters),
        grain=request.grain,
        elapsed_ms=elapsed_ms,
    )
