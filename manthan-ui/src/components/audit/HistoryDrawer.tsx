import { useEffect, useState } from "react";
import { X, Clock, User, FileText } from "lucide-react";
import { getDatasetHistory } from "@/api/datasets";

type HistoryEntry = {
  timestamp: string;
  changed_by: string;
  reason: string;
  dcd_version: string;
  entity_slug: string | null;
  metric_count: number;
};

/**
 * Audit drawer showing the append-only DCD change log (Phase 3).
 * Every time ``manthan-context.yaml`` is written, a row lands in
 * ``data/<ds>/dcd_history.jsonl`` with a ``{timestamp, changed_by,
 * reason}`` envelope — this drawer renders them newest-first so the
 * exec has a trail from "Revenue changed" → who/when.
 */
export function HistoryDrawer({
  datasetId,
  onClose,
}: {
  datasetId: string;
  onClose: () => void;
}) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await getDatasetHistory(datasetId, { limit: 50 });
        if (!cancelled) setEntries(rows);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load history");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div
        className="fixed inset-0 bg-black/20 z-40 animate-fade-in"
        onClick={onClose}
        aria-hidden
      />
      <aside
        className="fixed top-0 right-0 h-full w-[520px] max-w-[92vw] bg-surface-0 border-l border-border shadow-2xl z-50 flex flex-col animate-fade-rise-delay"
        role="dialog"
        aria-label="Change history"
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-1 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <FileText size={13} className="text-text-tertiary" />
            <span className="text-[11px] text-text-faint font-body uppercase tracking-wider">
              Change history
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-text-faint hover:text-text-secondary rounded-md hover:bg-surface-sunken transition-all"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5 font-body">
          {loading && (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-16 rounded-xl animate-shimmer" />
              ))}
            </div>
          )}

          {error && (
            <p className="text-sm text-error">{error}</p>
          )}

          {!loading && !error && entries.length === 0 && (
            <div className="py-20 text-center">
              <Clock size={22} className="mx-auto text-text-faint mb-3" />
              <p className="text-sm text-text-faint">
                No changes recorded yet — this dataset has not been edited since it was ingested.
              </p>
            </div>
          )}

          <ol className="space-y-0">
            {entries.map((e, i) => {
              const ts = new Date(e.timestamp);
              const when = isNaN(ts.valueOf())
                ? e.timestamp
                : `${ts.toLocaleDateString()} · ${ts.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
              return (
                <li key={i} className="relative pl-6 pb-5 last:pb-0">
                  {/* Timeline rail */}
                  <span
                    className="absolute left-[7px] top-2 bottom-0 w-px bg-border"
                    aria-hidden
                  />
                  <span
                    className="absolute left-1 top-1.5 w-3 h-3 rounded-full bg-accent-soft border-2 border-accent"
                    aria-hidden
                  />
                  <div className="text-[11px] text-text-tertiary tabular-nums">
                    {when}
                  </div>
                  <p className="text-sm text-text-primary mt-0.5 leading-snug">
                    {e.reason}
                  </p>
                  <div className="flex items-center gap-3 text-[11px] text-text-faint mt-1.5">
                    <span className="flex items-center gap-1">
                      <User size={10} />
                      {e.changed_by}
                    </span>
                    <span className="font-mono">v{e.dcd_version}</span>
                    {e.entity_slug && (
                      <span className="font-mono">
                        {e.entity_slug}
                      </span>
                    )}
                    {e.metric_count > 0 && (
                      <span className="text-accent">
                        {e.metric_count} metric{e.metric_count === 1 ? "" : "s"}
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </aside>
    </>
  );
}
