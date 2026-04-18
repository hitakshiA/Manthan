import { motion } from "motion/react";
import {
  Database,
  FileText,
  Cloud,
  Plug,
  Layers,
  ShieldAlert,
  ArrowUpRight,
  BarChart3,
  Link2,
} from "lucide-react";
import type { DatasetSummary, SchemaSummary } from "@/types/api";
import { cn } from "@/lib/utils";

/**
 * One rich entity card for the portfolio-style lister. Designed to
 * carry the full Layer-1 story at a glance: business name + stable
 * slug, source type, governed metric count, rollup count, inbound/
 * outbound relationship count, and a short description.
 */

export interface EntityCardProps {
  dataset: DatasetSummary;
  schema: SchemaSummary | null | undefined;
  relatedCount: number;
  onOpen: () => void;
  index: number;
}

export function EntityCard({
  dataset,
  schema,
  relatedCount,
  onOpen,
  index,
}: EntityCardProps) {
  const entity = schema?.entity ?? null;
  const metrics = entity?.metrics ?? [];
  const rollups = entity?.rollups ?? [];
  const cols = schema?.columns ?? [];
  const piiCount = cols.filter((c) => c.pii).length;
  const avgCompleteness = cols.length
    ? Math.round(
        (cols.reduce((s, c) => s + (c.completeness ?? 1), 0) / cols.length) * 100,
      )
    : null;

  const displayName = entity?.name ?? dataset.name;
  const slug = entity?.slug ?? dataset.name.toLowerCase().replace(/[^a-z0-9]/g, "_");
  const SourceIcon = pickSourceIcon(dataset.source_type);
  const description =
    entity?.description ||
    schema?.description ||
    `${dataset.row_count.toLocaleString()} rows × ${dataset.column_count} fields`;

  return (
    <motion.button
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, delay: Math.min(index * 0.035, 0.3) }}
      onClick={onOpen}
      className={cn(
        "group relative text-left rounded-2xl border border-border bg-surface-raised",
        "p-5 flex flex-col gap-3 hover:border-border-strong hover:shadow-md hover:-translate-y-0.5 transition-all duration-200",
      )}
    >
      {/* Accent bar — color-codes the source type */}
      <span
        aria-hidden
        className={cn(
          "absolute top-0 left-5 right-5 h-0.5 rounded-full opacity-70 transition-opacity group-hover:opacity-100",
          sourceAccent(dataset.source_type),
        )}
      />

      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <span className={cn(
            "w-9 h-9 rounded-xl flex items-center justify-center shrink-0 transition-colors",
            sourceBg(dataset.source_type),
          )}>
            <SourceIcon size={15} className={sourceIconColor(dataset.source_type)} />
          </span>
          <div className="min-w-0">
            <p className="text-[15px] font-semibold text-text-primary font-body truncate leading-tight">
              {displayName}
            </p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-[10.5px] font-mono text-text-tertiary truncate">
                {slug}
              </span>
              <span className="text-[10.5px] text-text-faint">·</span>
              <span className="text-[10.5px] font-body text-text-tertiary capitalize">
                {dataset.source_type.replace(/-/g, " ")}
              </span>
            </div>
          </div>
        </div>
        <ArrowUpRight
          size={14}
          className="text-text-faint group-hover:text-accent group-hover:rotate-12 transition-all shrink-0 mt-1"
        />
      </div>

      {/* Description */}
      <p className="text-[12.5px] text-text-secondary font-body line-clamp-2 leading-relaxed">
        {description}
      </p>

      {/* Governed contract preview — metric labels inline */}
      {metrics.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {metrics.slice(0, 3).map((m) => (
            <span
              key={m.slug}
              className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-accent-soft text-accent text-[10.5px] font-body"
              title={m.description || m.expression}
            >
              <BarChart3 size={9} />
              {m.label}
            </span>
          ))}
          {metrics.length > 3 && (
            <span className="px-2 py-0.5 rounded-md bg-surface-sunken text-text-tertiary text-[10.5px] font-body">
              +{metrics.length - 3}
            </span>
          )}
        </div>
      )}

      {/* Footer stat rail */}
      <div className="flex items-center justify-between gap-3 mt-auto pt-3 border-t border-border/60">
        <div className="flex items-center gap-3 text-[10.5px] text-text-tertiary font-body tabular-nums">
          <span className="flex items-center gap-1" title="Rollups pre-materialized">
            <Layers size={10} className="text-accent" />
            {rollups.length}
          </span>
          <span className="flex items-center gap-1" title="FK connections">
            <Link2 size={10} className="text-success" />
            {relatedCount}
          </span>
          <span className="flex items-center gap-1" title="Row count">
            {formatRowCount(dataset.row_count)}
          </span>
          {piiCount > 0 && (
            <span
              className="flex items-center gap-1 text-warning"
              title={`${piiCount} PII field${piiCount === 1 ? "" : "s"}`}
            >
              <ShieldAlert size={10} /> {piiCount}
            </span>
          )}
        </div>
        {avgCompleteness != null && (
          <span
            className={cn(
              "text-[10.5px] font-body tabular-nums",
              avgCompleteness >= 95
                ? "text-success"
                : avgCompleteness >= 80
                  ? "text-warning"
                  : "text-error",
            )}
          >
            {avgCompleteness}% clean
          </span>
        )}
      </div>
    </motion.button>
  );
}

function pickSourceIcon(source: string) {
  const s = source.toLowerCase();
  if (/(postgres|mysql|sqlite|snowflake|bigquery|duckdb|db)/.test(s)) return Database;
  if (/(s3|gs|gcs|azure|http|https|url|cloud)/.test(s)) return Cloud;
  if (/(stripe|hubspot|salesforce|shopify|notion|airtable|github|slack|saas|dlt)/.test(s))
    return Plug;
  return FileText;
}

function sourceBg(source: string): string {
  const s = source.toLowerCase();
  if (/(postgres|mysql|sqlite|snowflake|bigquery|duckdb|db)/.test(s))
    return "bg-success-soft group-hover:bg-success-soft/80";
  if (/(s3|gs|gcs|azure|http|https|url|cloud)/.test(s))
    return "bg-accent-soft group-hover:bg-accent-soft/80";
  if (/(stripe|hubspot|salesforce|shopify|notion|airtable|github|slack|saas|dlt)/.test(s))
    return "bg-warning-soft group-hover:bg-warning-soft/80";
  return "bg-surface-sunken group-hover:bg-surface-sunken/80";
}

function sourceIconColor(source: string): string {
  const s = source.toLowerCase();
  if (/(postgres|mysql|sqlite|snowflake|bigquery|duckdb|db)/.test(s)) return "text-success";
  if (/(s3|gs|gcs|azure|http|https|url|cloud)/.test(s)) return "text-accent";
  if (/(stripe|hubspot|salesforce|shopify|notion|airtable|github|slack|saas|dlt)/.test(s))
    return "text-warning";
  return "text-text-secondary";
}

function sourceAccent(source: string): string {
  const s = source.toLowerCase();
  if (/(postgres|mysql|sqlite|snowflake|bigquery|duckdb|db)/.test(s)) return "bg-success";
  if (/(s3|gs|gcs|azure|http|https|url|cloud)/.test(s)) return "bg-accent";
  if (/(stripe|hubspot|salesforce|shopify|notion|airtable|github|slack|saas|dlt)/.test(s))
    return "bg-warning";
  return "bg-text-faint";
}

function formatRowCount(n: number): string {
  if (n < 1000) return `${n} rows`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}K rows`;
  return `${(n / 1_000_000).toFixed(1)}M rows`;
}
