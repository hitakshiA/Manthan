import { useUIStore } from "@/stores/ui-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { useSessionStore } from "@/stores/session-store";
import { cn, formatNumber } from "@/lib/utils";
import { Trash2, Upload, Database, ChevronRight } from "lucide-react";
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
      <div className="px-4 py-3 flex items-center justify-between">
        <h2 className="text-[11px] font-semibold text-text-faint uppercase tracking-widest">Datasets</h2>
        <input ref={fileRef} type="file" className="hidden" accept=".csv,.tsv,.parquet,.json,.xlsx,.xls"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); }} />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          aria-label="Upload dataset"
          className="w-6 h-6 flex items-center justify-center rounded-md text-text-faint hover:text-accent hover:bg-accent-soft transition-all"
        >
          <Upload size={13} strokeWidth={2} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {datasets.length === 0 && (
          <div className="px-2 py-10 text-center">
            <Database size={24} className="text-text-faint mx-auto mb-2" strokeWidth={1.5} />
            <p className="text-xs text-text-faint">Upload a file to begin</p>
          </div>
        )}
        {datasets.map((ds) => {
          const isActive = activeDatasetId === ds.dataset_id;
          return (
            <button
              key={ds.dataset_id}
              onClick={() => setActiveDataset(ds.dataset_id)}
              className={cn(
                "group w-full text-left px-3 py-2.5 rounded-lg mb-0.5 flex items-center gap-2.5 transition-all duration-150",
                isActive
                  ? "bg-surface-raised shadow-xs border border-border"
                  : "hover:bg-surface-raised/60 border border-transparent",
              )}
            >
              <div className={cn(
                "w-7 h-7 rounded-md flex items-center justify-center shrink-0 text-[10px] font-bold",
                isActive ? "bg-accent text-accent-text" : "bg-surface-sunken text-text-faint",
              )}>
                {ds.name.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium text-text-primary truncate">{ds.name}</p>
                <p className="text-[11px] text-text-faint">{formatNumber(ds.row_count)} rows</p>
              </div>
              {isActive && (
                <ChevronRight size={14} className="text-text-faint shrink-0" />
              )}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(`Delete ${ds.name}?`)) removeDataset(ds.dataset_id);
                }}
                aria-label={`Delete ${ds.name}`}
                className="opacity-0 group-hover:opacity-100 p-1 rounded-md hover:bg-error-soft text-text-faint hover:text-error transition-all"
              >
                <Trash2 size={11} />
              </button>
            </button>
          );
        })}
      </div>

      {activeDatasetId && <SchemaViewer datasetId={activeDatasetId} />}
    </div>
  );
}

function MemorySidebar() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3">
        <h2 className="text-[11px] font-semibold text-text-faint uppercase tracking-widest">Memory</h2>
      </div>
      <div className="px-4 py-10 text-center">
        <p className="text-xs text-text-secondary font-medium">The analyst remembers</p>
        <p className="text-[11px] text-text-faint mt-1 leading-relaxed">
          Key findings from past analyses appear here automatically.
        </p>
      </div>
    </div>
  );
}

function HistorySidebar() {
  const { queryHistory } = useSessionStore();
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3">
        <h2 className="text-[11px] font-semibold text-text-faint uppercase tracking-widest">History</h2>
      </div>
      <div className="flex-1 overflow-y-auto px-2">
        {queryHistory.length === 0 && (
          <div className="px-2 py-10 text-center">
            <p className="text-[11px] text-text-faint">Queries appear here after you run them</p>
          </div>
        )}
        {queryHistory.map((q) => (
          <div key={q.id} className="px-3 py-2 hover:bg-surface-raised rounded-lg transition-colors cursor-pointer mb-0.5">
            <p className="text-xs text-text-primary truncate">{q.message}</p>
            <p className="text-[11px] text-text-faint mt-0.5">
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
