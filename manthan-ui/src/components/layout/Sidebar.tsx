import { useUIStore } from "@/stores/ui-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { useSessionStore } from "@/stores/session-store";
import { cn, formatNumber } from "@/lib/utils";
import { Upload, Trash2 } from "lucide-react";
import { useEffect, useRef } from "react";

function DatasetsSidebar() {
  const { datasets, fetchDatasets, uploadDataset, uploading, removeDataset } = useDatasetStore();
  const { activeDatasetId, setActiveDataset } = useSessionStore();
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { fetchDatasets(); }, [fetchDatasets]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ds = await uploadDataset(file);
    setActiveDataset(ds.dataset_id);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary tracking-tight">Datasets</h2>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {datasets.length === 0 && (
          <p className="px-4 py-8 text-sm text-text-tertiary text-center">
            Drop a CSV to get started
          </p>
        )}
        {datasets.map((ds) => (
          <button
            key={ds.dataset_id}
            onClick={() => setActiveDataset(ds.dataset_id)}
            className={cn(
              "w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors duration-100",
              activeDatasetId === ds.dataset_id
                ? "bg-accent-soft"
                : "hover:bg-surface-2",
            )}
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">
                {ds.name}
              </p>
              <p className="text-xs text-text-tertiary">
                {formatNumber(ds.row_count)} rows · {ds.column_count} cols
              </p>
            </div>
            <span
              className={cn(
                "text-[10px] font-medium px-1.5 py-0.5 rounded uppercase tracking-wider",
                ds.status === "gold" && "bg-success-soft text-success",
                ds.status === "silver" && "bg-warning-soft text-warning",
                ds.status === "bronze" && "bg-surface-3 text-text-tertiary",
              )}
            >
              {ds.status}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                removeDataset(ds.dataset_id);
              }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-error-soft text-text-tertiary hover:text-error transition-all"
            >
              <Trash2 size={14} />
            </button>
          </button>
        ))}
      </div>
      <div className="p-3 border-t border-border">
        <input ref={fileRef} type="file" className="hidden" accept=".csv,.tsv,.parquet,.json,.xlsx,.xls" onChange={handleUpload} />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className={cn(
            "w-full flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors duration-150",
            uploading
              ? "bg-surface-2 text-text-tertiary"
              : "bg-accent text-accent-text hover:bg-accent-hover",
          )}
        >
          <Upload size={15} />
          {uploading ? "Uploading..." : "Upload dataset"}
        </button>
      </div>
    </div>
  );
}

function MemorySidebar() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary tracking-tight">Memory</h2>
      </div>
      <p className="px-4 py-8 text-sm text-text-tertiary text-center">
        Cross-session memory entries will appear here after analyses
      </p>
    </div>
  );
}

function HistorySidebar() {
  const { queryHistory } = useSessionStore();
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary tracking-tight">History</h2>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {queryHistory.length === 0 && (
          <p className="px-4 py-8 text-sm text-text-tertiary text-center">
            Your queries will appear here
          </p>
        )}
        {queryHistory.map((q) => (
          <div key={q.id} className="px-4 py-2.5 hover:bg-surface-2 transition-colors">
            <p className="text-sm text-text-primary truncate">{q.message}</p>
            <p className="text-xs text-text-tertiary mt-0.5">
              {new Date(q.timestamp).toLocaleTimeString()}
              {q.renderMode && (
                <span className="ml-2 text-accent">{q.renderMode}</span>
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
    <aside className="w-60 shrink-0 border-r border-border bg-surface-1 overflow-hidden">
      {sidebarView === "datasets" && <DatasetsSidebar />}
      {sidebarView === "memory" && <MemorySidebar />}
      {sidebarView === "history" && <HistorySidebar />}
    </aside>
  );
}
