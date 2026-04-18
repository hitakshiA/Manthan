import { Database, FileText, Cloud, Plug, Key, ShieldAlert, Link2, BarChart3, Clock, Layers } from "lucide-react";
import type { GraphNode, ColumnWithPort } from "@/lib/semantic-graph";
import {
  NODE_WIDTH,
  HEADER_HEIGHT,
  COL_ROW_HEIGHT,
  FOOTER_HEIGHT,
} from "@/lib/semantic-graph";
import { cn } from "@/lib/utils";

/**
 * UML-style table node — the whole column list is visible, each row
 * is a port candidate for an FK edge, and the header carries the
 * entity identity + governed-layer posture.
 */

export interface TableNodeProps {
  node: GraphNode;
  columns: ColumnWithPort[];
  hiddenCount: number;
  height: number;
  isFocused: boolean;
  isDimmed: boolean;
  isHot: boolean;
  onHover: (id: string | null) => void;
  onClick: () => void;
}

export function TableNode({
  node,
  columns,
  hiddenCount,
  height,
  isFocused,
  isDimmed,
  isHot,
  onHover,
  onClick,
}: TableNodeProps) {
  const SourceIcon = pickSourceIcon(node.sourceType);
  const metrics = node.metricCount;
  const rollups = node.rollupCount;

  return (
    <div
      onMouseEnter={() => onHover(node.id)}
      onMouseLeave={() => onHover(null)}
      onClick={onClick}
      style={{ width: NODE_WIDTH, height }}
      className={cn(
        "relative rounded-xl border backdrop-blur-md transition-all duration-300 cursor-pointer overflow-hidden select-none",
        isFocused
          ? "border-white bg-white/10 shadow-[0_0_50px_rgba(147,197,253,0.35)]"
          : isHot
            ? "border-white/80 bg-white/8 shadow-[0_0_30px_rgba(147,197,253,0.25)]"
            : "border-white/25 bg-white/5 hover:border-white/55 hover:bg-white/8",
        isDimmed && "opacity-30",
      )}
    >
      {/* Header */}
      <div
        className="px-3.5 py-2.5 border-b border-white/10"
        style={{ height: HEADER_HEIGHT }}
      >
        <div className="flex items-center gap-1.5">
          <SourceIcon size={10} className="text-white/70 shrink-0" />
          <span className="font-mono text-[9.5px] text-white/55 truncate">
            {node.slug}
          </span>
          <span className="text-[9.5px] text-white/35">·</span>
          <span className="font-mono text-[9.5px] text-white/45 truncate capitalize">
            {node.sourceType.replace(/-/g, " ")}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2 mt-1">
          <div className="font-display text-[13.5px] text-white leading-tight truncate">
            {node.name}
          </div>
          <div className="flex items-center gap-2 text-[9px] text-white/55 font-mono shrink-0">
            {metrics > 0 && (
              <span className="flex items-center gap-0.5 text-accent" title="Governed metrics">
                <BarChart3 size={8} /> {metrics}
              </span>
            )}
            {rollups > 0 && (
              <span className="flex items-center gap-0.5 text-success" title="Rollups">
                <Layers size={8} /> {rollups}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Column rows — each is a potential edge port */}
      <div>
        {columns.map((c, i) => (
          <ColumnRow key={c.name} col={c} index={i} />
        ))}
        {hiddenCount > 0 && (
          <div
            className="px-3.5 flex items-center text-[10px] text-white/45 font-mono border-b border-white/5"
            style={{ height: COL_ROW_HEIGHT }}
          >
            + {hiddenCount} more field{hiddenCount === 1 ? "" : "s"}
          </div>
        )}
      </div>

      {/* Footer — row count */}
      <div
        className="px-3.5 flex items-center justify-between border-t border-white/10 bg-white/5"
        style={{ height: FOOTER_HEIGHT }}
      >
        <span className="text-[9.5px] font-mono text-white/55 tabular-nums">
          {formatRowCount(node.rowCount)} rows
        </span>
        {node.piiCount > 0 && (
          <span
            title={`${node.piiCount} PII field${node.piiCount === 1 ? "" : "s"}`}
            className="flex items-center gap-0.5 text-[9px] text-warning"
          >
            <ShieldAlert size={8} /> {node.piiCount}
          </span>
        )}
      </div>
    </div>
  );
}

function ColumnRow({ col, index }: { col: ColumnWithPort; index: number }) {
  const label = col.label || col.name;
  const tint = roleTint(col.role);
  return (
    <div
      className="px-3 flex items-center gap-2 border-b border-white/5 last:border-0"
      style={{ height: COL_ROW_HEIGHT }}
      data-col-idx={index}
    >
      {/* Left marker: key for identifier, link for FK */}
      <span className="w-3 shrink-0 flex items-center justify-center">
        {col.role === "identifier" && (
          <Key size={9} className="text-amber-300" />
        )}
        {col.isFK && (
          <Link2 size={9} className="text-sky-300" />
        )}
        {col.role === "metric" && !col.isFK && (
          <BarChart3 size={9} className="text-accent" />
        )}
        {col.role === "temporal" && (
          <Clock size={9} className="text-success" />
        )}
      </span>
      <span className="text-[10.5px] font-mono text-white/85 flex-1 truncate">
        {label}
      </span>
      {col.pii && (
        <ShieldAlert size={8} className="text-warning shrink-0" />
      )}
      <span
        className={cn(
          "text-[8.5px] font-body uppercase tracking-wider px-1 rounded shrink-0",
          tint,
        )}
      >
        {shortRole(col.role)}
      </span>
    </div>
  );
}

function shortRole(role: string): string {
  switch (role) {
    case "metric": return "num";
    case "temporal": return "time";
    case "dimension": return "cat";
    case "identifier": return "key";
    case "auxiliary": return "aux";
    default: return role;
  }
}

function roleTint(role: string): string {
  switch (role) {
    case "metric": return "bg-accent/20 text-accent";
    case "temporal": return "bg-success/20 text-success";
    case "dimension": return "bg-white/10 text-white/60";
    case "identifier": return "bg-amber-300/20 text-amber-300";
    default: return "bg-white/8 text-white/40";
  }
}

function pickSourceIcon(source: string) {
  const s = source.toLowerCase();
  if (/(postgres|mysql|sqlite|snowflake|bigquery|duckdb|db)/.test(s)) return Database;
  if (/(s3|gs|gcs|azure|http|https|url|cloud)/.test(s)) return Cloud;
  if (/(stripe|hubspot|salesforce|shopify|notion|airtable|github|slack|saas|dlt)/.test(s))
    return Plug;
  return FileText;
}

function formatRowCount(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}K`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}
