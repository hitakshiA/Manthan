import { useUIStore } from "@/stores/ui-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { useSessionStore } from "@/stores/session-store";
import { cn, formatNumber } from "@/lib/utils";
import { Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useCallback, useState } from "react";
import { SchemaViewer } from "@/components/datasets/SchemaViewer";

function DatasetsSidebar() {
  const { datasets, fetchDatasets, uploadDataset, removeDataset } = useDatasetStore();
  const { activeDatasetId, setActiveDataset } = useSessionStore();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => { fetchDatasets(); }, [fetchDatasets]);

  const handleUpload = useCallback(async (file: File) => {
    setUploading(true);
    try {
      const ds = await uploadDataset(file);
      setActiveDataset(ds.dataset_id);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, [uploadDataset, setActiveDataset]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-border flex items-center justify-between">
        <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Datasets</h2>
        <input ref={fileRef} type="file" className="hidden" accept=".csv,.tsv,.parquet,.json,.xlsx,.xls"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); }} />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          aria-label="Upload dataset"
          className="w-6 h-6 flex items-center justify-center rounded text-text-tertiary hover:text-accent hover:bg-accent-soft transition-colors"
        >
          <Upload size={13} strokeWidth={2} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {datasets.length === 0 && (
          <p className="px-3 py-6 text-xs text-text-tertiary text-center">
            Upload a CSV to get started
          </p>
        )}
        {datasets.map((ds) => (
          <button
            key={ds.dataset_id}
            onClick={() => setActiveDataset(ds.dataset_id)}
            className={cn(
              "group w-full text-left px-3 py-2 flex items-center gap-2 transition-colors duration-100",
              activeDatasetId === ds.dataset_id
                ? "bg-accent-soft border-l-2 border-l-accent"
                : "hover:bg-surface-2 border-l-2 border-l-transparent",
            )}
          >
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-medium text-text-primary truncate">
                {ds.name}
              </p>
              <p className="text-[11px] text-text-tertiary mt-0.5">
                {formatNumber(ds.row_count)} rows · {ds.column_count} cols
              </p>
            </div>
            {ds.status === "gold" && (
              <span className="text-[9px] font-medium px-1 py-px rounded text-text-tertiary bg-surface-2 uppercase tracking-widest">
                ready
              </span>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Delete ${ds.name}?`)) removeDataset(ds.dataset_id);
              }}
              aria-label={`Delete ${ds.name}`}
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-error-soft text-text-tertiary hover:text-error transition-all"
            >
              <Trash2 size={12} />
            </button>
          </button>
        ))}
      </div>

      {activeDatasetId && <SchemaViewer datasetId={activeDatasetId} />}
    </div>
  );
}

function MemorySidebar() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-border">
        <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Memory</h2>
      </div>
      <div className="px-3 py-6 text-center space-y-1.5">
        <p className="text-xs text-text-secondary font-medium">The analyst remembers</p>
        <p className="text-[11px] text-text-tertiary leading-relaxed">
          Key findings from past analyses appear here. The agent recalls them automatically.
        </p>
      </div>
    </div>
  );
}

function HistorySidebar() {
  const { queryHistory } = useSessionStore();
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-border">
        <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">History</h2>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {queryHistory.length === 0 && (
          <div className="px-3 py-6 text-center">
            <p className="text-[11px] text-text-tertiary leading-relaxed">
              Queries appear here after you run them.
            </p>
          </div>
        )}
        {queryHistory.map((q) => (
          <div key={q.id} className="px-3 py-2 hover:bg-surface-2 transition-colors cursor-pointer">
            <p className="text-xs text-text-primary truncate">{q.message}</p>
            <p className="text-[11px] text-text-tertiary mt-0.5">
              {new Date(q.timestamp).toLocaleTimeString()}
              {q.renderMode && (
                <span className="ml-1.5 text-accent font-medium">{q.renderMode}</span>
              )}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Sidebar() {
  const { sidebarView, sidebarOpen } = useUIStore();

  if (!sidebarOpen) return null;

  return (
    <aside className="w-56 shrink-0 border-r border-border bg-surface-1 overflow-hidden">
      {sidebarView === "datasets" && <DatasetsSidebar />}
      {sidebarView === "memory" && <MemorySidebar />}
      {sidebarView === "history" && <HistorySidebar />}
    </aside>
  );
}
