import type { ColumnSchema } from "@/types/api";
import { cn } from "@/lib/utils";

interface Props {
  columns: ColumnSchema[];
  showLabels?: boolean;
  className?: string;
}

const ROLE_CONFIG: Record<string, { color: string; label: string }> = {
  metric:     { color: "bg-accent",       label: "metrics" },
  dimension:  { color: "bg-border-strong", label: "dimensions" },
  temporal:   { color: "bg-success",       label: "temporal" },
  identifier: { color: "bg-surface-3",     label: "identifiers" },
  auxiliary:  { color: "bg-surface-3",     label: "auxiliary" },
};

export function RoleBar({ columns, showLabels = false, className }: Props) {
  const counts: Record<string, number> = {};
  for (const col of columns) {
    counts[col.role] = (counts[col.role] ?? 0) + 1;
  }

  const total = columns.length;
  if (total === 0) return null;

  const segments = Object.entries(counts)
    .sort(([a], [b]) => {
      const order = ["metric", "dimension", "temporal", "identifier", "auxiliary"];
      return order.indexOf(a) - order.indexOf(b);
    });

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex h-1 rounded-full overflow-hidden bg-surface-2">
        {segments.map(([role, count]) => (
          <div
            key={role}
            className={cn("transition-all duration-500", ROLE_CONFIG[role]?.color ?? "bg-surface-3")}
            style={{ width: `${(count / total) * 100}%` }}
          />
        ))}
      </div>

      {showLabels && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {segments.map(([role, count]) => (
            <span key={role} className="flex items-center gap-1 text-[10px] text-text-faint">
              <span className={cn("w-1.5 h-1.5 rounded-full", ROLE_CONFIG[role]?.color ?? "bg-surface-3")} />
              {count} {ROLE_CONFIG[role]?.label ?? role}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
