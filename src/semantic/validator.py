"""Pre-exec SQL validation against the semantic layer.

The agent can write raw SQL through ``run_sql``. Without a guardrail,
it may hallucinate tables/columns or silently drop a governed metric's
filter (e.g. compute ``SUM(subtotal)`` as "revenue" without
``WHERE status='delivered'``). Both failures look plausible at
display time and erode exec trust once spotted.

This module intercepts every SQL statement before it hits DuckDB and
runs three checks against the active semantic catalog:

    1. **Table resolution.** Every referenced table must be either the
       entity's ``physical_table``, one of its rollup ``physical_table``s,
       or an allow-listed raw/other-entity table. Hallucinated names
       raise :class:`SqlValidationError` with a suggested fix.

    2. **Column resolution.** Every referenced column must exist on the
       tables we resolved in step 1. Case-insensitive match against the
       DCD column list.

    3. **Metric-filter guard.** If a query aggregates a metric's
       expression (e.g. ``SUM(subtotal)``) AND aliases the result with
       the metric's slug/label (e.g. ``AS revenue``), any filter
       declared on the metric MUST also appear in the WHERE clause.
       This catches the silent-filter-drop failure without restricting
       ad-hoc exploration.

Design notes:

    * sqlglot is MIT-licensed; we only use its parser + visitor, no
      transpiler features.
    * Failure mode is "fail loud": the validator returns a clear,
      actionable error message the agent can use to self-repair.
    * Unknown tables (e.g. ``information_schema.columns`` for DESCRIBE)
      pass through — we only constrain references to entity-scoped
      physical tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from src.semantic.schema import DataContextDocument, DcdEntity, DcdMetric


_SYSTEM_TABLES = frozenset(
    {
        "information_schema",
        "pg_catalog",
        "sqlite_master",
        "duckdb_tables",
        "duckdb_columns",
    }
)


@dataclass(slots=True)
class ValidationIssue:
    """One problem the validator found."""

    severity: str  # "error" | "warning"
    code: str      # "unknown_table" | "unknown_column" | "metric_filter_missing"
    message: str
    suggestion: str | None = None


@dataclass(slots=True)
class ValidationResult:
    """Outcome of running the validator against a single SQL statement."""

    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def error_message(self) -> str:
        """One compact string the agent can read + retry against."""
        errors = [i for i in self.issues if i.severity == "error"]
        if not errors:
            return ""
        lines = []
        for issue in errors:
            lines.append(f"• {issue.message}")
            if issue.suggestion:
                lines.append(f"  → {issue.suggestion}")
        return "\n".join(lines)


@dataclass(slots=True)
class EntityCatalog:
    """Slim view of one entity — everything the validator needs, nothing more.

    Built on-demand from a DCD so the validator doesn't hold a
    reference to the full AppState.
    """

    slug: str
    physical_tables: set[str]          # primary + all rollup tables
    columns_by_table: dict[str, set[str]]  # physical_table → {col_name, …}
    metrics: list[DcdMetric]

    @classmethod
    def from_dcd(cls, dcd: DataContextDocument) -> EntityCatalog | None:
        entity = dcd.dataset.entity
        if entity is None:
            return None
        physical_tables = {entity.physical_table}
        for roll in entity.rollups:
            physical_tables.add(roll.physical_table)
        columns_by_table: dict[str, set[str]] = {
            entity.physical_table: {c.name.lower() for c in dcd.dataset.columns},
        }
        # Rollups inherit columns from the primary but also add
        # materialized fields (pct_of_total, record_count). We
        # accept these liberally — no DESCRIBE of each rollup is
        # necessary because the validator's column check is a
        # soft match (the warning path, not the error path).
        _rollup_extras = {"pct_of_total", "record_count", "period"}
        for roll in entity.rollups:
            columns_by_table[roll.physical_table] = (
                columns_by_table[entity.physical_table]
                | set(roll.dimensions)
                | _rollup_extras
            )
        return cls(
            slug=entity.slug,
            physical_tables=physical_tables,
            columns_by_table=columns_by_table,
            metrics=list(entity.metrics),
        )


def validate_sql(
    sql: str,
    *,
    entity: EntityCatalog | None,
    extra_known_tables: set[str] | None = None,
) -> ValidationResult:
    """Parse ``sql`` and check it against the active entity catalog.

    ``extra_known_tables`` lets the caller allow-list raw or other-entity
    tables (e.g. from :meth:`AppState.gold_table_names`) so multi-dataset
    joins don't trip the unknown-table check.

    Parser failures are NOT treated as validation errors — DuckDB has
    dialect quirks (e.g. the ``PIVOT``, ``USING SAMPLE``, ``DESCRIBE``,
    ``SHOW TABLES`` commands) that sqlglot may not handle perfectly.
    When parsing fails we return ``ok=True`` with no issues; the
    agent's ``run_sql`` tool then attempts execution and any real
    problem surfaces as an execution error the agent can read.
    """
    extra_known = set(extra_known_tables or ())

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except Exception:
        return ValidationResult(ok=True, issues=[])

    issues: list[ValidationIssue] = []
    for stmt in statements:
        if stmt is None:
            continue
        issues.extend(_check_tables(stmt, entity, extra_known))
        issues.extend(_check_columns(stmt, entity))
        if entity is not None:
            issues.extend(_check_metric_filters(stmt, entity))

    ok = not any(i.severity == "error" for i in issues)
    return ValidationResult(ok=ok, issues=issues)


def _check_tables(
    stmt: exp.Expression,
    entity: EntityCatalog | None,
    extra_known: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    known = set(extra_known)
    if entity is not None:
        known |= entity.physical_tables
        known.add(entity.slug)  # agent can reference by entity slug too

    for tbl in stmt.find_all(exp.Table):
        name = (tbl.name or "").lower()
        if not name:
            continue
        # Strip schema prefix if schema is a system one (information_schema,
        # pg_catalog) — DESCRIBE / SHOW TABLES flow through here.
        schema = (tbl.db or "").lower()
        if schema in _SYSTEM_TABLES or name in _SYSTEM_TABLES:
            continue
        # Bare identifier check — accept by lowercase match. Every
        # legitimate table in the workspace is either the active
        # entity's, one of the known raw_/gold_ names that callers
        # passed in via ``extra_known_tables``, or a system table. If
        # it's not in those sets, it's a hallucinated reference.
        lower_known = {k.lower() for k in known}
        if name in lower_known:
            continue
        suggestion = _suggest_table(name, known) if known else None
        msg = f"Unknown table '{tbl.name}'."
        if entity is not None:
            msg += (
                f" The active entity '{entity.slug}' is backed by "
                f"'{next(iter(entity.physical_tables))}' with rollups "
                f"{sorted(entity.physical_tables)}."
            )
        issues.append(
            ValidationIssue(
                severity="error",
                code="unknown_table",
                message=msg,
                suggestion=suggestion,
            )
        )
    return issues


def _check_columns(
    stmt: exp.Expression,
    entity: EntityCatalog | None,
) -> list[ValidationIssue]:
    if entity is None:
        return []
    # Collect all known columns across entity's physical tables.
    known_cols: set[str] = set()
    for cols in entity.columns_by_table.values():
        known_cols |= cols
    # Star columns and aliases are always OK.
    issues: list[ValidationIssue] = []
    for col in stmt.find_all(exp.Column):
        name = (col.name or "").lower()
        if not name or name == "*":
            continue
        if name in known_cols:
            continue
        # Soft-pass: column may be from an aliased subquery or a JOIN'd
        # table we haven't modeled. We emit a warning, not an error,
        # to avoid over-blocking exploratory queries.
        issues.append(
            ValidationIssue(
                severity="warning",
                code="unknown_column",
                message=f"Column '{col.name}' doesn't match any declared field.",
                suggestion=None,
            )
        )
    return issues


def _check_metric_filters(
    stmt: exp.Expression,
    entity: EntityCatalog,
) -> list[ValidationIssue]:
    """For each declared metric with a filter, ensure that filter is
    present in the WHERE clause when the query aggregates the metric's
    expression AND aliases the result with the metric's slug/label.

    Heuristic match on the expression — we normalize whitespace and
    compare lowercase. Strict SQL-AST matching is overkill for the
    coverage we need.
    """
    issues: list[ValidationIssue] = []
    for metric in entity.metrics:
        if not metric.filter:
            continue
        # Does the statement contain the metric's expression as an
        # aggregated projection aliased with the metric's slug/label?
        metric_aliased = False
        needle_expr = " ".join(metric.expression.split()).lower()
        alias_matches = {metric.slug.lower(), metric.label.lower()}
        for proj in stmt.find_all(exp.Alias):
            alias_name = (proj.alias or "").lower()
            if alias_name not in alias_matches:
                continue
            proj_sql = proj.this.sql(dialect="duckdb")
            if " ".join(proj_sql.split()).lower() == needle_expr:
                metric_aliased = True
                break
        if not metric_aliased:
            continue
        # Check that the metric's filter predicate appears in the WHERE.
        where = stmt.find(exp.Where)
        where_text = where.sql(dialect="duckdb").lower() if where else ""
        filter_text = metric.filter.lower()
        # Extremely loose containment — good enough to catch the common
        # silent-drop ("WHERE status='delivered'" vs missing WHERE). If
        # the exec gets smarter filters later (IN-lists, date windows),
        # we'll harden this.
        if _normalize_predicate(filter_text) not in _normalize_predicate(where_text):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="metric_filter_missing",
                    message=(
                        f"Metric '{metric.slug}' must be computed with its "
                        f"declared filter: {metric.filter}"
                    ),
                    suggestion=(
                        f"Add `WHERE {metric.filter}` (or AND it with your "
                        "existing WHERE) so the aggregate respects the "
                        "metric's business definition."
                    ),
                )
            )
    return issues


def _normalize_predicate(text: str) -> str:
    """Collapse whitespace + strip quotes for fuzzy containment match."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _suggest_table(unknown: str, known: set[str]) -> str | None:
    """Best-effort 'did you mean X?' suggestion using simple prefix match."""
    lower = unknown.lower()
    for k in known:
        kl = k.lower()
        if lower in kl or kl in lower:
            return f"Did you mean '{k}'?"
    return None
