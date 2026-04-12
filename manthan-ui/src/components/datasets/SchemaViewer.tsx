import { useEffect, useState } from "react";
import type { SchemaSummary } from "@/types/api";
import { getSchema } from "@/api/datasets";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const ROLE_COLORS: Record<string, string> = {
  metric: "bg-blue-100 text-blue-700",
  dimension: "bg-purple-100 text-purple-700",
  temporal: "bg-emerald-100 text-emerald-700",
  identifier: "bg-gray-100 text-gray-600",
  auxiliary: "bg-orange-100 text-orange-600",
};

export function SchemaViewer({ datasetId }: { datasetId: string }) {
  const [schema, setSchema] = useState<SchemaSummary | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    getSchema(datasetId).then(setSchema).catch(() => {});
  }, [datasetId]);

  if (!schema) return null;

  return (
    <div className="border-t border-border">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-text-secondary hover:bg-surface-2 transition-colors"
      >
        <span>{schema.columns.length} columns</span>
        <ChevronDown
          size={14}
          className={cn("transition-transform duration-200", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-1">
          {schema.columns.map((col) => (
            <div key={col.name} className="flex items-center gap-2 py-1">
              <span className="text-xs font-mono text-text-primary truncate flex-1">
                {col.name}
              </span>
              <span
                className={cn(
                  "text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0",
                  ROLE_COLORS[col.role] ?? "bg-gray-100 text-gray-600",
                )}
              >
                {col.role}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
