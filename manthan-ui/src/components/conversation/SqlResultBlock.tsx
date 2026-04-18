import { useState } from "react";
import { ChevronDown, ChevronUp, Code2, Copy, Check } from "lucide-react";
import type { SqlResultBlock as SqlResultType } from "@/types/conversation";
import { cn } from "@/lib/utils";

/** Turn a raw column name (FOUNDED_YEAR, amount_usd) into an exec-readable
 * label ("Founded year", "Amount USD"). Preserves common all-caps acronyms. */
function humanizeColumn(raw: string): string {
  const ACRONYMS = new Set(["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD", "CEO", "CTO", "CFO", "COO", "VP", "SKU", "UUID", "URL", "API", "ID"]);
  return raw
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .split(" ")
    .filter(Boolean)
    .map((word) => {
      const upper = word.toUpperCase();
      if (ACRONYMS.has(upper)) return upper;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ");
}

export function SqlResultBlock({ result }: { result: SqlResultType }) {
  const [showAll, setShowAll] = useState(false);
  const [showQuery, setShowQuery] = useState(false);
  const [copied, setCopied] = useState(false);
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  const visibleRows = showAll ? result.rows : result.rows.slice(0, 10);
  const hasMore = result.rows.length > 10;

  // Sort
  let displayRows = visibleRows;
  if (sortCol !== null) {
    displayRows = [...visibleRows].sort((a, b) => {
      const av = a[sortCol] ?? "";
      const bv = b[sortCol] ?? "";
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortAsc ? cmp : -cmp;
    });
  }

  const handleSort = (colIdx: number) => {
    if (sortCol === colIdx) setSortAsc(!sortAsc);
    else { setSortCol(colIdx); setSortAsc(true); }
  };

  const copyAsCSV = () => {
    const header = result.columns.join(",");
    const rows = result.rows.map((r) => r.map((v) => String(v ?? "")).join(",")).join("\n");
    navigator.clipboard.writeText(`${header}\n${rows}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="rounded-xl border border-border bg-surface-raised overflow-hidden text-xs font-body">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-surface-sunken/50 border-b border-border/50">
        <span className="text-text-faint">
          {result.row_count.toLocaleString()} row{result.row_count !== 1 ? "s" : ""}
          {result.truncated && " (truncated)"}
          <span className="mx-1.5 text-border">·</span>
          {result.elapsed_ms < 1000 ? `${Math.round(result.elapsed_ms)}ms` : `${(result.elapsed_ms / 1000).toFixed(1)}s`}
        </span>
        <div className="flex items-center gap-1.5">
          <button onClick={() => setShowQuery(!showQuery)} className="text-text-faint hover:text-text-secondary transition-colors p-0.5" title="Show query">
            <Code2 size={12} />
          </button>
          <button onClick={copyAsCSV} className="text-text-faint hover:text-text-secondary transition-colors p-0.5" title="Copy as CSV">
            {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
          </button>
        </div>
      </div>

      {/* Query (collapsible) */}
      {showQuery && (
        <pre className="px-3 py-2 bg-surface-sunken text-[11px] text-text-tertiary font-mono overflow-x-auto border-b border-border/50">
          {result.query}
        </pre>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              {result.columns.map((col, i) => (
                <th
                  key={i}
                  onClick={() => handleSort(i)}
                  className="text-left px-3 py-2 text-[11px] font-semibold text-text-faint tracking-wide cursor-pointer hover:text-text-secondary select-none whitespace-nowrap"
                >
                  {humanizeColumn(col)}
                  {sortCol === i && (
                    <span className="ml-1">{sortAsc ? "▲" : "▼"}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr key={i} className={cn("hover:bg-surface-0", i % 2 === 1 && "bg-surface-sunken/20")}>
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-1.5 text-text-secondary whitespace-nowrap font-mono text-[11px]">
                    {cell == null ? <span className="text-text-faint italic">null</span> : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Show more/less */}
      {hasMore && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="w-full flex items-center justify-center gap-1 py-1.5 text-[10px] text-text-faint hover:text-text-secondary border-t border-border/50 transition-colors"
        >
          {showAll ? <><ChevronUp size={10} /> Show less</> : <><ChevronDown size={10} /> Show all {result.rows.length} rows</>}
        </button>
      )}
    </div>
  );
}
