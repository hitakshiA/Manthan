import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ActivityFeed } from "@/components/workspace/ActivityFeed";
import { RenderRouter } from "@/components/render/RenderRouter";
import { NarrativeBlock } from "@/components/render/shared/NarrativeBlock";
import { RoleBar } from "@/components/datasets/RoleBar";
import { useSchema, prefetchSchemas } from "@/hooks/use-schema";
import {
  Clock, Wrench, RotateCcw, BarChart3, TrendingUp, FileText,
  Upload, Database, ArrowLeft, FileSpreadsheet, ChevronRight,
  Layers, Table2, Zap,
} from "lucide-react";
import { ManthanLogo } from "@/components/ManthanLogo";
import { queryStream } from "@/api/agent";
import type { RenderSpec } from "@/types/render-spec";
import type { DatasetSummary } from "@/types/api";
import { useCallback, useRef, useState, useEffect } from "react";
import { formatNumber, cn } from "@/lib/utils";

/* ═══════════════════════════════════════════════════════
   VIEW 1: First Open — Upload or Explore
   ═══════════════════════════════════════════════════════ */

function FirstOpen() {
  const [view, setView] = useState<"home" | "explore">("home");
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const { uploadDataset, datasets, fetchDatasets, uploading } = useDatasetStore();
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);

  const showExplore = () => { fetchDatasets(); setView("explore"); };

  const handleFile = useCallback(async (file: File) => {
    const ds = await uploadDataset(file);
    setActiveDataset(ds.dataset_id);
  }, [uploadDataset, setActiveDataset]);

  // Pre-fetch schemas for explore cards
  useEffect(() => {
    if (view === "explore" && datasets.length > 0) {
      prefetchSchemas(datasets.map((d) => d.dataset_id));
    }
  }, [view, datasets]);

  if (view === "explore") return <ExploreView datasets={datasets} onBack={() => setView("home")} />;

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      <div className="text-center mb-10 stagger-item" style={{ "--i": 0 } as React.CSSProperties}>
        <ManthanLogo size={36} className="text-accent mx-auto mb-3" />
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Manthan</h1>
        <p className="text-sm text-text-secondary mt-1">Your autonomous data analyst</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-xl stagger-item" style={{ "--i": 1 } as React.CSSProperties}>
        <input ref={fileRef} type="file" className="hidden" accept=".csv,.tsv,.parquet,.json,.xlsx,.xls"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
        <button
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
          disabled={uploading}
          className={cn(
            "flex flex-col items-start p-5 rounded-xl bg-surface-raised border shadow-xs text-left transition-all duration-200",
            "hover:shadow-md hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-accent",
            dragOver ? "border-accent bg-accent-soft shadow-md -translate-y-0.5" : "border-border hover:border-border-strong",
            uploading && "opacity-60 pointer-events-none",
          )}
        >
          <div className="w-10 h-10 rounded-lg bg-accent-soft flex items-center justify-center mb-4">
            {uploading ? <FileSpreadsheet size={20} className="text-accent animate-pulse" /> : <Upload size={20} className="text-accent" />}
          </div>
          <h3 className="text-[15px] font-semibold text-text-primary">{uploading ? "Processing…" : "Upload a dataset"}</h3>
          <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">
            Drop a CSV, Parquet, Excel, or JSON file. Manthan classifies every column and asks about ambiguous ones before analysis.
          </p>
          <span className="text-[10px] text-text-faint mt-3">Drag & drop or click to browse</span>
        </button>

        <button
          onClick={showExplore}
          className="flex flex-col items-start p-5 rounded-xl bg-surface-raised border border-border shadow-xs text-left transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 hover:border-border-strong focus-visible:ring-2 focus-visible:ring-accent"
        >
          <div className="w-10 h-10 rounded-lg bg-success-soft flex items-center justify-center mb-4">
            <Database size={20} className="text-success" />
          </div>
          <h3 className="text-[15px] font-semibold text-text-primary">Explore existing data</h3>
          <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">
            Pick from datasets already on the server. Each has a semantic layer built — column roles confirmed, summary tables ready.
          </p>
          <span className="text-[10px] text-text-faint mt-3">{datasets.length} dataset{datasets.length !== 1 ? "s" : ""} available</span>
        </button>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   VIEW 2: Explore — Rich dataset cards
   ═══════════════════════════════════════════════════════ */

function ExploreCard({ dataset }: { dataset: DatasetSummary }) {
  const { schema } = useSchema(dataset.dataset_id);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);

  return (
    <button
      onClick={() => setActiveDataset(dataset.dataset_id)}
      className="w-full flex items-center gap-3 p-4 rounded-xl bg-surface-raised border border-border shadow-xs hover:shadow-md hover:-translate-y-0.5 hover:border-border-strong transition-all duration-200 text-left group"
    >
      <div className="w-9 h-9 rounded-lg bg-accent-soft flex items-center justify-center shrink-0 group-hover:bg-accent transition-colors">
        <span className="text-sm font-bold text-accent group-hover:text-accent-text transition-colors">
          {dataset.name.charAt(0).toUpperCase()}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-semibold text-text-primary truncate">{dataset.name}</p>
        <p className="text-[11px] text-text-faint mt-0.5">
          {formatNumber(dataset.row_count)} rows · {dataset.column_count} cols
        </p>
        {schema && <RoleBar columns={schema.columns} className="mt-2" />}
      </div>
      <ChevronRight size={14} className="text-text-faint group-hover:text-text-secondary transition-colors shrink-0" />
    </button>
  );
}

function ExploreView({ datasets, onBack }: { datasets: DatasetSummary[]; onBack: () => void }) {
  // Deduplicate by name — keep the first occurrence of each unique name
  const seen = new Set<string>();
  const unique = datasets.filter((ds) => {
    if (seen.has(ds.name)) return false;
    seen.add(ds.name);
    return true;
  });

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-xl mx-auto px-6 py-8 animate-fade-up">
        <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-text-faint hover:text-text-secondary mb-6 transition-colors">
          <ArrowLeft size={13} /> Back
        </button>
        <h2 className="text-lg font-semibold text-text-primary mb-1">Choose a dataset</h2>
        <p className="text-sm text-text-secondary mb-6">Each has a semantic layer — column roles classified, summary tables materialized.</p>

        <div className="space-y-2">
          {unique.map((ds, i) => (
            <div key={ds.dataset_id} className="stagger-item" style={{ "--i": i } as React.CSSProperties}>
              <ExploreCard dataset={ds} />
            </div>
          ))}
        </div>
        {unique.length === 0 && (
          <p className="text-sm text-text-faint py-12 text-center">No datasets loaded yet. Upload one first.</p>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   VIEW 3: Dataset Profile — the semantic layer showcase
   ═══════════════════════════════════════════════════════ */

function DatasetProfile() {
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);
  const datasets = useDatasetStore((s) => s.datasets);
  const activeDs = datasets.find((d) => d.dataset_id === activeDatasetId);
  const { schema, loading } = useSchema(activeDatasetId);
  const [showQuery, setShowQuery] = useState(false);

  if (!activeDs) return null;

  const metrics = schema?.columns.filter((c) => c.role === "metric") ?? [];
  const dimensions = schema?.columns.filter((c) => c.role === "dimension") ?? [];
  const temporal = schema?.columns.filter((c) => c.role === "temporal") ?? [];
  const other = schema?.columns.filter((c) => !["metric", "dimension", "temporal"].includes(c.role)) ?? [];

  if (showQuery) return <ReadyToQuery />;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-8 animate-fade-up">
        <button onClick={() => setActiveDataset(null)} className="flex items-center gap-1.5 text-xs text-text-faint hover:text-text-secondary mb-6 transition-colors">
          <ArrowLeft size={13} /> All datasets
        </button>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-11 h-11 rounded-xl bg-accent flex items-center justify-center">
              <span className="text-lg font-bold text-accent-text">{activeDs.name.charAt(0).toUpperCase()}</span>
            </div>
            <div>
              <h1 className="text-xl font-bold text-text-primary tracking-tight">{activeDs.name}</h1>
              <p className="text-sm text-text-secondary">
                {activeDs.row_count.toLocaleString()} rows · {activeDs.column_count} columns · {activeDs.source_type.toUpperCase()}
              </p>
            </div>
          </div>

          {schema && (
            <div className="mt-4 p-4 rounded-xl bg-surface-raised border border-border shadow-xs">
              <p className="text-sm text-text-secondary leading-relaxed mb-3">
                Manthan classified {schema.columns.length} columns and identified{" "}
                <span className="font-medium text-text-primary">{metrics.length} measurable value{metrics.length !== 1 ? "s" : ""}</span>,{" "}
                <span className="font-medium text-text-primary">{dimensions.length} grouping categor{dimensions.length !== 1 ? "ies" : "y"}</span>
                {temporal.length > 0 && <>, and <span className="font-medium text-text-primary">{temporal.length} time dimension</span></>}.
              </p>
              <RoleBar columns={schema.columns} showLabels />
            </div>
          )}
        </div>

        {schema ? (
          <div className="space-y-6">
            {metrics.length > 0 && (
              <ColumnGroup icon={<BarChart3 size={14} className="text-accent" />} title="Metrics" subtitle="Values you measure" columns={metrics} />
            )}
            {dimensions.length > 0 && (
              <ColumnGroup icon={<Layers size={14} className="text-border-strong" />} title="Dimensions" subtitle="Categories you group by" columns={dimensions} />
            )}
            {temporal.length > 0 && (
              <ColumnGroup icon={<Clock size={14} className="text-success" />} title="Temporal" subtitle="Time axis for trends" columns={temporal} />
            )}
            {other.length > 0 && (
              <ColumnGroup icon={<Table2 size={14} className="text-text-faint" />} title="Other" subtitle="Identifiers and auxiliary" columns={other} />
            )}
          </div>
        ) : loading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => <div key={i} className="h-14 rounded-xl animate-shimmer" />)}
          </div>
        ) : null}

        {/* CTA — always visible, never blocked by schema loading */}
        <div className="mt-8">
          <button
            onClick={() => setShowQuery(true)}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-accent text-accent-text font-medium text-sm shadow-sm hover:bg-accent-hover hover:shadow-md transition-all duration-200 hover:-translate-y-0.5 active:scale-[0.98]"
          >
            Start analyzing
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

function ColumnGroup({ icon, title, subtitle, columns }: {
  icon: React.ReactNode; title: string; subtitle: string;
  columns: Array<{ name: string; dtype: string; role: string; description: string; aggregation: string | null }>;
}) {
  const [expanded, setExpanded] = useState(columns.length <= 4);

  const visible = expanded ? columns : columns.slice(0, 3);

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        <span className="text-[11px] text-text-faint">· {subtitle}</span>
      </div>
      <div className="space-y-1.5">
        {visible.map((col) => (
          <div key={col.name} className="flex items-start gap-3 py-2 px-3 rounded-lg hover:bg-surface-raised transition-colors">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-medium text-text-primary font-mono">{col.name}</span>
                <span className="text-[10px] text-text-faint bg-surface-sunken px-1.5 py-0.5 rounded">{col.dtype}</span>
                {col.aggregation && (
                  <span className="text-[10px] text-accent bg-accent-soft px-1.5 py-0.5 rounded font-medium">{col.aggregation}</span>
                )}
              </div>
              {col.description && (
                <p className="text-[11px] text-text-faint mt-0.5 leading-relaxed">{col.description}</p>
              )}
            </div>
          </div>
        ))}
      </div>
      {columns.length > 3 && !expanded && (
        <button onClick={() => setExpanded(true)} className="text-xs text-accent hover:text-accent-hover mt-1 ml-3 transition-colors">
          Show {columns.length - 3} more
        </button>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   VIEW 4: Ready to Query — input + suggestions
   ═══════════════════════════════════════════════════════ */

function ReadyToQuery() {
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
    reset(); addQuery(q, activeDatasetId);
    try { await queryStream(sessionId, activeDatasetId, q, pushEvent); }
    catch (e) { pushEvent({ type: "error", message: e instanceof Error ? e.message : "Failed", recoverable: false }); }
  }, [activeDatasetId, sessionId, addQuery, pushEvent, reset]);

  if (!activeDs) return null;

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 animate-fade-up">
      <div className="text-center mb-8">
        <ManthanLogo size={28} className="text-accent mx-auto mb-2" />
        <h1 className="text-xl font-bold text-text-primary tracking-tight">{activeDs.name}</h1>
        <p className="text-sm text-text-secondary mt-1">{activeDs.row_count.toLocaleString()} rows · {activeDs.column_count} columns</p>
        <button onClick={() => setActiveDataset(null)} className="text-[11px] text-text-faint hover:text-accent mt-1.5 transition-colors">Change dataset</button>
      </div>

      <div className="w-full max-w-2xl mb-6">
        <QueryInput variant="hero" />
      </div>

      <div className="flex gap-2">
        {[
          { icon: BarChart3, label: "Overview", text: `What are the key metrics in ${activeDs.name}?` },
          { icon: TrendingUp, label: "Compare", text: "Compare the top categories by volume" },
          { icon: FileText, label: "Report", text: "Full analytical report with recommendations" },
        ].map(({ icon: Icon, label, text }) => (
          <button key={label} onClick={() => runSuggestion(text)}
            className="flex items-center gap-2 text-[13px] text-text-secondary hover:text-text-primary bg-surface-raised hover:bg-surface-1 border border-border hover:border-border-strong px-4 py-2.5 rounded-xl shadow-xs hover:shadow-sm transition-all duration-200">
            <Icon size={14} className="text-text-tertiary" />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   VIEW 5: Active Workspace — agent running / results
   ═══════════════════════════════════════════════════════ */

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
                <span className="flex items-center gap-1.5 bg-surface-sunken px-2 py-1 rounded-md"><Clock size={11} />{elapsed.toFixed(1)}s</span>
                <span className="flex items-center gap-1.5 bg-surface-sunken px-2 py-1 rounded-md"><Wrench size={11} />{toolCalls} tools</span>
              </div>
              <div className="flex-1" />
              <details className="text-[11px] relative">
                <summary className="text-text-faint cursor-pointer hover:text-text-secondary transition-colors select-none">{events.length} events</summary>
                <div className="absolute right-0 mt-1 w-96 max-h-80 overflow-y-auto bg-surface-raised border border-border rounded-xl shadow-lg p-3 z-50">
                  <ActivityFeed />
                </div>
              </details>
              <button onClick={reset} className="flex items-center gap-1.5 text-[11px] text-text-faint hover:text-accent bg-surface-sunken hover:bg-accent-soft px-2.5 py-1 rounded-md transition-all">
                <RotateCcw size={11} /> New
              </button>
            </div>
            <div className="px-8 pb-8">
              {renderSpec ? <RenderRouter spec={renderSpec as RenderSpec} /> : agentText ? (
                <div className="bg-surface-raised border border-border rounded-xl shadow-sm p-6"><NarrativeBlock text={agentText} /></div>
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

/* ═══════════════════════════════════════════════════════
   ROOT: Route between all views
   ═══════════════════════════════════════════════════════ */

export function MainWorkspace() {
  const events = useAgentStore((s) => s.events);
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const hasContent = events.length > 0;

  return (
    <main className="flex-1 flex flex-col min-w-0 bg-surface-0 relative" role="main">
      {hasContent ? <ActiveWorkspace /> : activeDatasetId ? <DatasetProfile /> : <FirstOpen />}
    </main>
  );
}
