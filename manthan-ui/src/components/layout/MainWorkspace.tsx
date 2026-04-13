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
  Zap,
} from "lucide-react";
import { ManthanLogo } from "@/components/ManthanLogo";
import { queryStream } from "@/api/agent";
import type { RenderSpec } from "@/types/render-spec";
import type { DatasetSummary, SchemaSummary } from "@/types/api";
import { useCallback, useRef, useState, useEffect } from "react";
import { formatNumber, cn } from "@/lib/utils";

/** Get the dataset description — prefer backend LLM description, fallback to template */
function describeDataset(schema: SchemaSummary): string {
  // If the backend generated an LLM description, use it
  const desc = schema.description;
  if (desc && !desc.includes("dataset loaded from") && desc.length > 20) {
    return desc;
  }

  // Fallback: template from column roles
  const metrics = schema.columns.filter((c) => c.role === "metric");
  const dims = schema.columns.filter((c) => c.role === "dimension");
  const parts: string[] = [];
  if (metrics.length > 0) {
    parts.push(`tracks ${metrics.slice(0, 2).map((c) => c.name.replace(/_/g, " ")).join(" and ")}`);
  }
  if (dims.length > 0) {
    parts.push(`segmented by ${dims.slice(0, 3).map((c) => c.name.replace(/_/g, " ")).join(", ")}`);
  }
  if (parts.length === 0) return `${schema.columns.length} columns across ${schema.row_count.toLocaleString()} records.`;
  return `${parts.join(", ")}. ${schema.row_count.toLocaleString()} records.`;
}

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

  // Pre-fetch schemas for explore cards (deduped)
  useEffect(() => {
    if (view === "explore" && datasets.length > 0) {
      const seen = new Set<string>();
      const unique = datasets.filter((d) => { if (seen.has(d.name)) return false; seen.add(d.name); return true; });
      prefetchSchemas(unique.map((d) => d.dataset_id));
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
        {schema ? (
          <p className="text-[11px] text-text-faint mt-0.5 truncate capitalize">{describeDataset(schema)}</p>
        ) : (
          <p className="text-[11px] text-text-faint mt-0.5">{formatNumber(dataset.row_count)} rows · {dataset.column_count} cols</p>
        )}
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
  if (showQuery) return <ReadyToQuery />;

  const metrics = schema?.columns.filter((c) => c.role === "metric") ?? [];
  const dimensions = schema?.columns.filter((c) => c.role === "dimension") ?? [];
  const temporal = schema?.columns.filter((c) => c.role === "temporal") ?? [];
  const other = schema?.columns.filter((c) => !["metric", "dimension", "temporal"].includes(c.role)) ?? [];
  const avgCompleteness = schema ? Math.round(schema.columns.reduce((s, c) => s + (c.completeness ?? 1), 0) / schema.columns.length * 100) : null;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8 animate-fade-up">
        <button onClick={() => setActiveDataset(null)} className="flex items-center gap-1.5 text-xs text-text-faint hover:text-text-secondary mb-6 transition-colors">
          <ArrowLeft size={13} /> All datasets
        </button>

        {/* Header */}
        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 rounded-xl bg-accent flex items-center justify-center shrink-0">
            <span className="text-lg font-bold text-accent-text">{activeDs.name.charAt(0).toUpperCase()}</span>
          </div>
          <div className="flex-1">
            <h1 className="text-xl font-bold text-text-primary tracking-tight">{activeDs.name}</h1>
            <p className="text-sm text-text-secondary mt-0.5">{activeDs.source_type.toUpperCase()} · {activeDs.row_count.toLocaleString()} rows · {activeDs.column_count} columns</p>
            {schema && (
              <p className="text-sm text-text-secondary mt-1 capitalize leading-relaxed">{describeDataset(schema)}</p>
            )}
          </div>
          <button
            onClick={() => setShowQuery(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-accent text-accent-text text-sm font-medium shadow-xs hover:bg-accent-hover hover:shadow-sm transition-all duration-200 shrink-0"
          >
            Start analyzing <ChevronRight size={14} />
          </button>
        </div>

        {/* Quick stats row */}
        {schema && (
          <div className="grid grid-cols-4 gap-3 mb-6">
            <div className="p-3 rounded-xl bg-surface-raised border border-border">
              <p className="text-lg font-bold text-text-primary tabular-nums">{schema.columns.length}</p>
              <p className="text-[11px] text-text-faint">Columns</p>
            </div>
            <div className="p-3 rounded-xl bg-surface-raised border border-border">
              <p className="text-lg font-bold text-text-primary tabular-nums">{metrics.length}</p>
              <p className="text-[11px] text-text-faint">Metrics</p>
            </div>
            <div className="p-3 rounded-xl bg-surface-raised border border-border">
              <p className="text-lg font-bold text-text-primary tabular-nums">{dimensions.length + temporal.length}</p>
              <p className="text-[11px] text-text-faint">Dimensions</p>
            </div>
            <div className="p-3 rounded-xl bg-surface-raised border border-border">
              <p className="text-lg font-bold text-accent tabular-nums">{avgCompleteness}%</p>
              <p className="text-[11px] text-text-faint">Complete</p>
            </div>
          </div>
        )}

        {/* Role bar */}
        {schema && <RoleBar columns={schema.columns} showLabels className="mb-8" />}

        {loading && (
          <div className="space-y-3">
            {[...Array(4)].map((_, i) => <div key={i} className="h-20 rounded-xl animate-shimmer" />)}
          </div>
        )}

        {/* Column table */}
        {schema && (
          <div className="rounded-xl border border-border bg-surface-raised shadow-xs overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-[1fr_80px_80px_100px] gap-3 px-4 py-2.5 border-b border-border bg-surface-sunken text-[10px] font-semibold text-text-faint uppercase tracking-wider">
              <span>Column</span>
              <span>Type</span>
              <span>Distinct</span>
              <span>Quality</span>
            </div>

            {/* Column rows */}
            {schema.columns.map((col, i) => (
              <div
                key={col.name}
                className={cn(
                  "grid grid-cols-[1fr_80px_80px_100px] gap-3 px-4 py-3 items-start transition-colors hover:bg-surface-0",
                  i < schema.columns.length - 1 && "border-b border-border",
                )}
              >
                {/* Name + description + samples */}
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-text-primary font-mono">{col.name}</span>
                    <span className={cn(
                      "text-[9px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider",
                      col.role === "metric" ? "bg-accent-soft text-accent" :
                      col.role === "temporal" ? "bg-success-soft text-success" :
                      col.role === "dimension" ? "bg-surface-sunken text-text-secondary" :
                      "bg-surface-sunken text-text-faint",
                    )}>
                      {col.role}
                      {col.aggregation && ` · ${col.aggregation}`}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-faint mt-0.5 leading-relaxed">{col.description}</p>
                  {col.stats && (
                    <p className="text-[10px] text-text-faint mt-1 font-mono">
                      {col.stats.min != null && <>min {String(col.stats.min)}</>}
                      {col.stats.max != null && <> · max {String(col.stats.max)}</>}
                      {col.stats.mean != null && <> · avg {String(col.stats.mean)}</>}
                    </p>
                  )}
                  {(col.sample_values?.length ?? 0) > 0 && (
                    <div className="flex gap-1 mt-1.5 flex-wrap">
                      {col.sample_values.slice(0, 3).map((v, j) => (
                        <span key={j} className="text-[9px] text-text-faint bg-surface-sunken px-1.5 py-0.5 rounded font-mono">{String(v)}</span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Type */}
                <span className="text-[11px] text-text-secondary font-mono mt-0.5">{col.dtype}</span>

                {/* Cardinality */}
                <span className="text-[11px] text-text-secondary tabular-nums mt-0.5">
                  {col.cardinality != null ? formatNumber(col.cardinality) : "—"}
                </span>

                {/* Completeness bar */}
                <div className="mt-1">
                  {col.completeness != null ? (
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1 rounded-full bg-surface-2 overflow-hidden">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-500",
                            col.completeness >= 0.95 ? "bg-success" : col.completeness >= 0.8 ? "bg-warning" : "bg-error",
                          )}
                          style={{ width: `${col.completeness * 100}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-text-faint tabular-nums w-8 text-right">
                        {Math.round(col.completeness * 100)}%
                      </span>
                    </div>
                  ) : (
                    <span className="text-[10px] text-text-faint">—</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Summary tables */}
        {schema && schema.summary_tables.length > 0 && (
          <div className="mt-6 p-4 rounded-xl bg-surface-raised border border-border shadow-xs">
            <div className="flex items-center gap-2 mb-3">
              <Zap size={14} className="text-warning" />
              <h3 className="text-sm font-semibold text-text-primary">{schema.summary_tables.length} pre-built tables</h3>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {schema.summary_tables.map((t) => (
                <span key={t} className="text-[10px] font-mono text-text-faint bg-surface-sunken px-2 py-1 rounded">{t.replace(/^gold_/, "").replace(/_[a-f0-9]+$/, "")}</span>
              ))}
            </div>
          </div>
        )}

        {/* Bottom CTA */}
        <div className="mt-8 mb-4">
          <button onClick={() => setShowQuery(true)}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-accent text-accent-text font-medium text-sm shadow-sm hover:bg-accent-hover hover:shadow-md transition-all duration-200 hover:-translate-y-0.5 active:scale-[0.98]">
            Start analyzing <ChevronRight size={15} />
          </button>
        </div>
      </div>
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
