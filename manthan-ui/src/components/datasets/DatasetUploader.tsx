import { useState, useCallback } from "react";
import { Upload, FileSpreadsheet } from "lucide-react";
import { useDatasetStore } from "@/stores/dataset-store";
import { useSessionStore } from "@/stores/session-store";
import { cn } from "@/lib/utils";

export function DatasetUploader() {
  const [dragOver, setDragOver] = useState(false);
  const { uploadDataset, uploading } = useDatasetStore();
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);

  const handleFile = useCallback(
    async (file: File) => {
      const ds = await uploadDataset(file);
      setActiveDataset(ds.dataset_id);
    },
    [uploadDataset, setActiveDataset],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={cn(
        "mx-4 my-3 rounded-lg border-2 border-dashed transition-all duration-200 flex flex-col items-center justify-center gap-2 py-8 cursor-pointer",
        dragOver
          ? "border-accent bg-accent-soft scale-[1.02]"
          : "border-border hover:border-accent/40 hover:bg-surface-2",
        uploading && "opacity-50 pointer-events-none",
      )}
      onClick={() => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".csv,.tsv,.parquet,.json,.xlsx,.xls";
        input.onchange = (e) => {
          const file = (e.target as HTMLInputElement).files?.[0];
          if (file) handleFile(file);
        };
        input.click();
      }}
    >
      {uploading ? (
        <>
          <div className="w-8 h-8 rounded-lg bg-accent-soft flex items-center justify-center animate-pulse">
            <FileSpreadsheet size={18} className="text-accent" />
          </div>
          <p className="text-sm text-text-secondary">Processing...</p>
        </>
      ) : (
        <>
          <div className="w-8 h-8 rounded-lg bg-surface-2 flex items-center justify-center">
            <Upload size={16} className="text-text-tertiary" />
          </div>
          <p className="text-sm text-text-secondary">
            Drop a file or <span className="text-accent font-medium">browse</span>
          </p>
          <p className="text-xs text-text-tertiary">CSV, Parquet, Excel, JSON</p>
        </>
      )}
    </div>
  );
}
