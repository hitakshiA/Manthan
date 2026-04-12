import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ActivityFeed } from "@/components/workspace/ActivityFeed";
import { RenderRouter } from "@/components/render/RenderRouter";
import { NarrativeBlock } from "@/components/render/shared/NarrativeBlock";
import {
  Clock, Wrench, RotateCcw, BarChart3, TrendingUp, FileText,
  Upload, Database, ArrowLeft, FileSpreadsheet,
} from "lucide-react";
import { ManthanLogo } from "@/components/ManthanLogo";
import { queryStream } from "@/api/agent";
import type { RenderSpec } from "@/types/render-spec";
import { useCallback, useRef, useState } from "react";
import { formatNumber, cn } from "@/lib/utils";

/* ─── First-open: two-path welcome ─── */

function FirstOpen() {
  const [view, setView] = useState<"home" | "explore">("home");
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const { uploadDataset, datasets, fetchDatasets, uploading } = useDatasetStore();
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);

  // Fetch datasets when switching to explore
  const showExplore = () => {
    fetchDatasets();
    setView("explore");
  };

  const handleFile = useCallback(async (file: File) => {
    const ds = await uploadDataset(file);
    setActiveDataset(ds.dataset_id);
  }, [uploadDataset, setActiveDataset]);

  if (view === "explore") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-6 animate-fade-up">
        <div className="w-full max-w-lg">
          <button
            onClick={() => setView("home")}
            className="flex items-center gap-1.5 text-xs text-text-faint hover:text-text-secondary mb-6 transition-colors"
          >
            <ArrowLeft size={13} />
            Back
          </button>

          <h2 className="text-lg font-semibold text-text-primary mb-1">Choose a dataset</h2>
          <p className="text-sm text-text-secondary mb-5">
            Each dataset has a semantic layer ready — column roles confirmed, summary tables materialized.
          </p>

          <div className="space-y-2">
            {datasets.length === 0 && (
              <p className="text-sm text-text-faint py-8 text-center">
                No datasets loaded yet. Upload one first.
              </p>
            )}
            {datasets.map((ds) => (
              <button
                key={ds.dataset_id}
                onClick={() => setActiveDataset(ds.dataset_id)}
                className="w-full flex items-center gap-4 p-4 rounded-xl bg-surface-raised border border-border shadow-xs hover:shadow-sm hover:border-border-strong transition-all duration-200 text-left group"
              >
                <div className="w-10 h-10 rounded-lg bg-accent-soft flex items-center justify-center shrink-0 group-hover:bg-accent transition-colors">
                  <span className="text-sm font-bold text-accent group-hover:text-accent-text transition-colors">
                    {ds.name.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-semibold text-text-primary">{ds.name}</p>
                  <p className="text-[11px] text-text-faint mt-0.5">
                    {formatNumber(ds.row_count)} rows · {ds.column_count} columns · {ds.source_type.toUpperCase()}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Home view — two action cards
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      {/* Logo + title */}
      <div className="text-center mb-10 stagger-item" style={{ "--i": 0 } as React.CSSProperties}>
        <ManthanLogo size={36} className="text-accent mx-auto mb-3" />
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Manthan</h1>
        <p className="text-sm text-text-secondary mt-1">Your autonomous data analyst</p>
      </div>

      {/* Two action cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-xl stagger-item" style={{ "--i": 1 } as React.CSSProperties}>
        {/* Upload card */}
        <input ref={fileRef} type="file" className="hidden" accept=".csv,.tsv,.parquet,.json,.xlsx,.xls"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
        <button
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files[0];
            if (f) handleFile(f);
          }}
          disabled={uploading}
          className={cn(
            "flex flex-col items-start p-5 rounded-xl bg-surface-raised border shadow-xs text-left transition-all duration-200",
            "hover:shadow-md hover:-translate-y-0.5",
            "focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2",
            dragOver ? "border-accent bg-accent-soft shadow-md -translate-y-0.5" : "border-border hover:border-border-strong",
            uploading && "opacity-60 pointer-events-none",
          )}
        >
          <div className="w-10 h-10 rounded-lg bg-accent-soft flex items-center justify-center mb-4">
            {uploading ? (
              <FileSpreadsheet size={20} className="text-accent animate-pulse" />
            ) : (
              <Upload size={20} className="text-accent" />
            )}
          </div>
          <h3 className="text-[15px] font-semibold text-text-primary">
            {uploading ? "Processing…" : "Upload a dataset"}
          </h3>
          <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">
            Drop a CSV, Parquet, Excel, or JSON file. Manthan classifies every column and asks about ambiguous ones before analysis.
          </p>
          <span className="text-[10px] text-text-faint mt-3">
            Drag & drop or click to browse
          </span>
        </button>

        {/* Explore card */}
        <button
          onClick={showExplore}
          className={cn(
            "flex flex-col items-start p-5 rounded-xl bg-surface-raised border border-border shadow-xs text-left transition-all duration-200",
            "hover:shadow-md hover:-translate-y-0.5 hover:border-border-strong",
            "focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2",
          )}
        >
          <div className="w-10 h-10 rounded-lg bg-success-soft flex items-center justify-center mb-4">
            <Database size={20} className="text-success" />
          </div>
          <h3 className="text-[15px] font-semibold text-text-primary">Explore existing data</h3>
          <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">
            Pick from datasets already on the server. Each has a semantic layer built — column roles confirmed, summary tables ready.
          </p>
          <span className="text-[10px] text-text-faint mt-3">
            {datasets.length} dataset{datasets.length !== 1 ? "s" : ""} available
          </span>
        </button>
      </div>
    </div>
  );
}

/* ─── Dataset selected: suggestions ─── */

function DatasetSelected() {
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const sessionId = useSessionStore((s) => s.sessionId);
  const addQuery = useSessionStore((s) => s.addQuery);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const reset = useAgentStore((s) => s.reset);
  const datasets = useDatasetStore((s) => s.datasets);
  const activeDs = datasets.find((d) => d.dataset_id === activeDatasetId);

  const runSuggestion = useCallback(async (q: string) => {
    if (!activeDatasetId) return;
    reset();
    addQuery(q, activeDatasetId);
    try {
      await queryStream(sessionId, activeDatasetId, q, pushEvent);
    } catch (e) {
      pushEvent({ type: "error", message: e instanceof Error ? e.message : "Failed", recoverable: false });
    }
  }, [activeDatasetId, sessionId, addQuery, pushEvent, reset]);

  if (!activeDs) return null;

  const suggestions = [
    { icon: BarChart3, label: "Overview", text: `What are the key metrics in ${activeDs.name}?` },
    { icon: TrendingUp, label: "Compare", text: "Compare the top categories by volume" },
    { icon: FileText, label: "Report", text: "Full analytical report with recommendations" },
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      <div className="text-center mb-8 stagger-item" style={{ "--i": 0 } as React.CSSProperties}>
        <ManthanLogo size={32} className="text-accent mx-auto mb-3" />
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">{activeDs.name}</h1>
        <p className="text-sm text-text-secondary mt-1">
          {activeDs.row_count.toLocaleString()} rows · {activeDs.column_count} columns
        </p>
        <button
          onClick={() => setActiveDataset(null)}
          className="text-[11px] text-text-faint hover:text-accent mt-2 transition-colors"
        >
          Change dataset
        </button>
      </div>

      <div className="w-full max-w-2xl mb-6 stagger-item" style={{ "--i": 1 } as React.CSSProperties}>
        <QueryInput variant="hero" />
      </div>

      <div className="flex gap-2 stagger-item" style={{ "--i": 2 } as React.CSSProperties}>
        {suggestions.map(({ icon: Icon, label, text }) => (
          <button
            key={label}
            onClick={() => runSuggestion(text)}
            className="flex items-center gap-2 text-[13px] text-text-secondary hover:text-text-primary bg-surface-raised hover:bg-surface-1 border border-border hover:border-border-strong px-4 py-2.5 rounded-xl shadow-xs hover:shadow-sm transition-all duration-200"
          >
            <Icon size={14} className="text-text-tertiary" />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ─── Active workspace: agent running / results ─── */

function ActiveWorkspace() {
  const events = useAgentStore((s) => s.events);
  const phase = useAgentStore((s) => s.phase);
  const renderSpec = useAgentStore((s) => s.renderSpec);
  const agentText = useAgentStore((s) => s.agentText);
  const elapsed = useAgentStore((s) => s.elapsedSeconds);
  const toolCalls = useAgentStore((s) => s.totalToolCalls);
  const reset = useAgentStore((s) => s.reset);
  const isDone = phase === "done";

  return (
    <>
      <div className="flex-1 overflow-y-auto">
        {!isDone && <ActivityFeed />}
        {isDone && (
          <div className="animate-fade-up">
            <div className="px-8 pt-6 pb-4 flex items-center gap-4">
              <div className="flex items-center gap-3 text-[11px] text-text-tertiary">
                <span className="flex items-center gap-1.5 bg-surface-sunken px-2 py-1 rounded-md">
                  <Clock size={11} />
                  {elapsed.toFixed(1)}s
                </span>
                <span className="flex items-center gap-1.5 bg-surface-sunken px-2 py-1 rounded-md">
                  <Wrench size={11} />
                  {toolCalls} tools
                </span>
              </div>
              <div className="flex-1" />
              <details className="text-[11px]">
                <summary className="text-text-faint cursor-pointer hover:text-text-secondary transition-colors select-none">
                  {events.length} agent events
                </summary>
                <div className="absolute right-8 mt-1 w-96 max-h-80 overflow-y-auto bg-surface-raised border border-border rounded-xl shadow-lg p-3 z-50">
                  <ActivityFeed />
                </div>
              </details>
              <button
                onClick={reset}
                aria-label="New query"
                className="flex items-center gap-1.5 text-[11px] text-text-faint hover:text-accent bg-surface-sunken hover:bg-accent-soft px-2.5 py-1 rounded-md transition-all"
              >
                <RotateCcw size={11} />
                New
              </button>
            </div>
            <div className="px-8 pb-8">
              {renderSpec ? (
                <RenderRouter spec={renderSpec as RenderSpec} />
              ) : agentText ? (
                <div className="bg-surface-raised border border-border rounded-xl shadow-sm p-6">
                  <NarrativeBlock text={agentText} />
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
      <div className="px-6 py-3 border-t border-border bg-surface-1">
        <QueryInput variant="compact" />
      </div>
    </>
  );
}

/* ─── Root: route between states ─── */

export function MainWorkspace() {
  const events = useAgentStore((s) => s.events);
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const hasContent = events.length > 0;

  return (
    <main className="flex-1 flex flex-col min-w-0 bg-surface-0 relative" role="main">
      {hasContent ? (
        <ActiveWorkspace />
      ) : activeDatasetId ? (
        <DatasetSelected />
      ) : (
        <FirstOpen />
      )}
    </main>
  );
}
