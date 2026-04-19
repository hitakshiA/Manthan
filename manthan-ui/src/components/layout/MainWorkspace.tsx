import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { useProcessingStore } from "@/stores/processing-store";
import { useUIStore } from "@/stores/ui-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ConversationStream } from "@/components/conversation/ConversationStream";
import { ArtifactPanel } from "@/components/artifact/ArtifactPanel";
import { InlineVisualPanel } from "@/components/conversation/InlineVisualPanel";
import { RoleBar } from "@/components/datasets/RoleBar";
import { ProcessingWizard } from "@/components/datasets/ProcessingWizard";
import { MetricCard } from "@/components/datasets/MetricCard";
import { RollupChip } from "@/components/datasets/RollupChip";
import { SemanticGraph } from "@/components/datasets/SemanticGraph";
import { EntityCard } from "@/components/datasets/EntityCard";
import { useAllSchemas } from "@/hooks/use-all-schemas";
import { buildNodes, deriveEdges } from "@/lib/semantic-graph";
import { HistoryDrawer } from "@/components/audit/HistoryDrawer";
import { useSchema, prefetchSchemas } from "@/hooks/use-schema";
import {
  BarChart3,
  Database, ArrowLeft, ArrowRight, ChevronRight,
  Columns3, Layers, ShieldCheck,
  RefreshCw, History, ShieldAlert, Zap, Link2,
} from "lucide-react";
import { TegakiRenderer } from "tegaki/react";
import italianno from "tegaki/fonts/italianno";
import { queryStream } from "@/api/agent";
import { uploadDatasetAsync, uploadMultiDataset, refreshDataset } from "@/api/datasets";
import type { DatasetSummary, SchemaSummary } from "@/types/api";
import { useCallback, useMemo, useRef, useState, useEffect } from "react";
import { formatNumber, cn } from "@/lib/utils";
import { deriveExecChips } from "@/lib/exec-chips";
import type { ComponentType } from "react";

function describeDataset(schema: SchemaSummary): string {
  const desc = schema.description;
  if (desc && !desc.includes("dataset loaded from") && desc.length > 20) return desc;
  const metrics = schema.columns.filter((c) => c.role === "metric");
  const dims = schema.columns.filter((c) => c.role === "dimension");
  const parts: string[] = [];
  if (metrics.length > 0) parts.push(`tracks ${metrics.slice(0, 2).map((c) => c.name.replace(/_/g, " ")).join(" and ")}`);
  if (dims.length > 0) parts.push(`segmented by ${dims.slice(0, 3).map((c) => c.name.replace(/_/g, " ")).join(", ")}`);
  if (parts.length === 0) return `${schema.columns.length} columns across ${schema.row_count.toLocaleString()} records.`;
  return `${parts.join(", ")}. ${schema.row_count.toLocaleString()} records.`;
}

/* ═══════════════════════════════════════════════════════
   VIEW 1: Landing — Tableau AI–inspired hero
   ═══════════════════════════════════════════════════════ */

function FirstOpen() {
  const view = useUIStore((s) => s.landingView);
  const setView = useUIStore((s) => s.setLandingView);
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const setShowPicker = useUIStore((s) => s.setSourcePickerOpen);
  const { datasets, fetchDatasets } = useDatasetStore();
  const startProcessing = useProcessingStore((s) => s.startProcessing);
  const [localUploading, setLocalUploading] = useState(false);

  // Hero choreography: handwriting lays down the wordmark, then the
  // subtitle + trust line fade in, then the CTA row joins.
  const [step, setStep] = useState<"writing" | "subtitle" | "ready">("writing");
  useEffect(() => {
    if (step === "subtitle") {
      const t = setTimeout(() => setStep("ready"), 520);
      return () => clearTimeout(t);
    }
  }, [step]);

  const showExplore = () => { fetchDatasets(); setView("explore"); };

  const handleFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    setLocalUploading(true);
    try {
      if (files.length === 1) {
        const { dataset_id } = await uploadDatasetAsync(files[0]);
        startProcessing(dataset_id);
      } else {
        const ds = await uploadMultiDataset(files);
        startProcessing(ds.dataset_id);
      }
    } catch { /* */ } finally { setLocalUploading(false); }
  }, [startProcessing]);

  useEffect(() => {
    if (view === "explore") fetchDatasets();
  }, [view, fetchDatasets]);

  useEffect(() => {
    if (view === "explore" && datasets.length > 0) {
      const seen = new Set<string>();
      const unique = datasets.filter((d) => { if (seen.has(d.name)) return false; seen.add(d.name); return true; });
      prefetchSchemas(unique.map((d) => d.dataset_id));
    }
  }, [view, datasets]);

  if (view === "explore") return <ExploreView datasets={datasets} onBack={() => setView("home")} />;

  return (
    <div className="flex-1 flex flex-col relative overflow-hidden">
      {/* Background video — full bleed */}
      <div className="absolute inset-0 z-0">
        <video
          autoPlay
          loop
          muted
          playsInline
          className="absolute inset-0 w-full h-full object-cover"
        >
          <source src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260314_131748_f2ca2a28-fed7-44c8-b9a9-bd9acdd5ec31.mp4" type="video/mp4" />
        </video>
      </div>

      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 -mt-[14vh] sm:-mt-[24vh]">
        <input
          ref={fileRef}
          type="file"
          multiple
          className="hidden"
          accept=".csv,.tsv,.parquet,.json,.xlsx,.xls"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length > 0) handleFiles(files);
          }}
        />

        <div className="flex flex-col items-center text-center">
          <TegakiRenderer
            font={italianno}
            time={{ mode: "uncontrolled", duration: 1.9 }}
            onComplete={() =>
              setStep((s) => (s === "writing" ? "subtitle" : s))
            }
            className="text-white select-none"
            style={{
              fontSize: "clamp(4rem, 16vw, 9.5rem)",
              lineHeight: 0.95,
              textAlign: "center",
              display: "inline-block",
              filter: "drop-shadow(0 4px 28px rgba(0,0,0,0.35))",
            }}
          >
            Manthan
          </TegakiRenderer>

          <p
            className={cn(
              "font-body text-white/70 text-sm sm:text-lg max-w-2xl mt-4 leading-relaxed font-medium transition-all duration-700 ease-out",
              step === "writing"
                ? "opacity-0 translate-y-2"
                : "opacity-100 translate-y-0",
            )}
          >
            The analyst team you wish you had. Drop any dataset — ask what&apos;s
            going on in plain English, get back a brief with the rigor of a
            senior analyst, fast enough for the meeting before the meeting.
          </p>

          <div
            className={cn(
              "font-body text-white/55 text-[11px] sm:text-xs mt-3 flex items-center gap-2 sm:gap-2.5 flex-wrap justify-center transition-all duration-700 ease-out delay-150",
              step === "writing"
                ? "opacity-0 translate-y-2"
                : "opacity-100 translate-y-0",
            )}
          >
            <span className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-white/40" />
              Governed metrics
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-white/40" />
              Auditable lineage
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-white/40" />
              Postgres · Snowflake · S3 · Sheets
            </span>
          </div>

          <div
            className={cn(
              "mt-8 sm:mt-10 transition-all duration-700 ease-out",
              step === "ready"
                ? "opacity-100 translate-y-0"
                : "opacity-0 translate-y-3 pointer-events-none",
            )}
          >
            {/* Mobile (< md): GitHub-only — phone isn't for running the app */}
            <a
              href="https://github.com/hitakshiA/Manthan"
              target="_blank"
              rel="noopener noreferrer"
              className="md:hidden liquid-glass rounded-full px-8 py-3.5 text-sm text-white font-body font-medium hover:scale-[1.03] transition-transform cursor-pointer inline-flex items-center gap-2.5"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 .5C5.73.5.5 5.73.5 12c0 5.08 3.29 9.38 7.86 10.9.58.1.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.88-1.54-3.88-1.54-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.25.45-2.28 1.18-3.08-.12-.29-.51-1.46.11-3.05 0 0 .97-.31 3.18 1.18.92-.26 1.9-.39 2.88-.39.98 0 1.96.13 2.88.39 2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.24 2.76.12 3.05.74.8 1.18 1.83 1.18 3.08 0 4.41-2.69 5.39-5.26 5.67.41.36.77 1.05.77 2.12 0 1.53-.01 2.77-.01 3.15 0 .31.21.67.8.56C20.21 21.37 23.5 17.08 23.5 12 23.5 5.73 18.27.5 12 .5Z" />
              </svg>
              View on GitHub
            </a>

            {/* Desktop (≥ md): full three-CTA row — Drop / Explore / Connect */}
            <div className="hidden md:flex items-center gap-4">
              <button
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  const all = Array.from(e.dataTransfer.files ?? []);
                  const allowed = /\.(csv|tsv|parquet|json|xlsx|xls)$/i;
                  const files = all.filter((f) => allowed.test(f.name));
                  if (files.length > 0) handleFiles(files);
                }}
                disabled={localUploading}
                className={cn(
                  "liquid-glass rounded-full px-10 py-4 text-base text-white font-body font-medium whitespace-nowrap",
                  "hover:scale-[1.03] transition-transform cursor-pointer",
                  dragOver && "scale-[1.03] ring-2 ring-white/40",
                  localUploading && "opacity-60 pointer-events-none",
                )}
                title="Single file, multiple files, or a whole folder — FK relationships auto-detected"
              >
                {localUploading ? "Uploading…" : "Drop a file or folder"}
              </button>

              <button
                onClick={showExplore}
                className="liquid-glass rounded-full px-10 py-4 text-base text-white font-body font-medium whitespace-nowrap hover:scale-[1.03] transition-transform cursor-pointer"
              >
                Explore existing
              </button>

              <button
                onClick={() => setShowPicker(true)}
                className="liquid-glass rounded-full px-10 py-4 text-base text-white font-body font-medium whitespace-nowrap hover:scale-[1.03] transition-transform cursor-pointer"
              >
                Connect a warehouse
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   VIEW 2: Explore — Card grid
   ═══════════════════════════════════════════════════════ */

/** Group raw source_type values into exec-friendly buckets for filter chips. */
function bucketSource(sourceType: string): "file" | "database" | "cloud" | "saas" | "other" {
  const s = sourceType.toLowerCase();
  if (/(csv|tsv|parquet|json|xlsx|xls|file|upload)/.test(s)) return "file";
  if (/(postgres|mysql|sqlite|snowflake|bigquery|duckdb|db|database)/.test(s)) return "database";
  if (/(s3|gs|gcs|azure|http|https|url|cloud)/.test(s)) return "cloud";
  if (/(stripe|hubspot|salesforce|shopify|notion|airtable|github|slack|saas|dlt)/.test(s)) return "saas";
  return "other";
}

const BUCKET_LABEL: Record<ReturnType<typeof bucketSource>, string> = {
  file: "Files",
  database: "Databases",
  cloud: "Cloud",
  saas: "Apps",
  other: "Other",
};

type Sort = "recent" | "rows" | "metrics" | "connections";

function ExploreView({ datasets, onBack }: { datasets: DatasetSummary[]; onBack: () => void }) {
  const [search, setSearch] = useState("");
  const [bucket, setBucket] = useState<"all" | ReturnType<typeof bucketSource>>("all");
  const [sort, setSort] = useState<Sort>("recent");
  const setShowPicker = useUIStore((s) => s.setSourcePickerOpen);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);

  // Dedupe by name — most recently created wins.
  const unique = useMemo(() => {
    const seen = new Set<string>();
    const sorted = [...datasets].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
    return sorted.filter((ds) => {
      if (seen.has(ds.name)) return false;
      seen.add(ds.name);
      return true;
    });
  }, [datasets]);

  // Bucket counts drive the filter chips.
  const bucketCounts: Record<string, number> = {};
  for (const ds of unique) {
    const b = bucketSource(ds.source_type);
    bucketCounts[b] = (bucketCounts[b] ?? 0) + 1;
  }

  // Load schemas so cards show metric/rollup/PII and the edge-count badge works.
  const ids = useMemo(() => unique.map((d) => d.dataset_id), [unique]);
  const { schemas } = useAllSchemas(ids);

  // Build nodes + edges to compute per-entity relationship count.
  const nodes = useMemo(() => buildNodes(unique, schemas), [unique, schemas]);
  const edges = useMemo(() => deriveEdges(nodes), [nodes]);
  const relatedCount = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of edges) {
      m.set(e.fromId, (m.get(e.fromId) ?? 0) + 1);
      m.set(e.toId, (m.get(e.toId) ?? 0) + 1);
    }
    return m;
  }, [edges]);

  // Portfolio aggregate stats.
  const totalMetrics = useMemo(
    () =>
      unique.reduce((sum, d) => {
        const e = schemas.get(d.dataset_id)?.entity;
        return sum + (e?.metrics.length ?? 0);
      }, 0),
    [unique, schemas],
  );
  const totalRollups = useMemo(
    () =>
      unique.reduce((sum, d) => {
        const e = schemas.get(d.dataset_id)?.entity;
        return sum + (e?.rollups.length ?? 0);
      }, 0),
    [unique, schemas],
  );
  const totalRows = useMemo(
    () => unique.reduce((sum, d) => sum + d.row_count, 0),
    [unique],
  );

  // Search + bucket filter + sort
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = unique.filter((ds) => {
      if (bucket !== "all" && bucketSource(ds.source_type) !== bucket) return false;
      if (q) {
        const schema = schemas.get(ds.dataset_id);
        const slug = schema?.entity?.slug ?? ds.name;
        if (
          !ds.name.toLowerCase().includes(q) &&
          !slug.toLowerCase().includes(q) &&
          !(schema?.entity?.description ?? "").toLowerCase().includes(q)
        )
          return false;
      }
      return true;
    });
    const scored = list.slice();
    scored.sort((a, b) => {
      switch (sort) {
        case "rows":
          return b.row_count - a.row_count;
        case "metrics": {
          const am = schemas.get(a.dataset_id)?.entity?.metrics.length ?? 0;
          const bm = schemas.get(b.dataset_id)?.entity?.metrics.length ?? 0;
          if (bm !== am) return bm - am;
          return b.row_count - a.row_count;
        }
        case "connections":
          return (relatedCount.get(b.dataset_id) ?? 0) - (relatedCount.get(a.dataset_id) ?? 0);
        case "recent":
        default:
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
    });
    return scored;
  }, [unique, search, bucket, sort, schemas, relatedCount]);

  const BUCKETS: Array<{ key: "all" | ReturnType<typeof bucketSource>; label: string; count: number }> = [
    { key: "all", label: "All", count: unique.length },
    ...(["file", "database", "cloud", "saas", "other"] as const)
      .filter((k) => (bucketCounts[k] ?? 0) > 0)
      .map((k) => ({ key: k, label: BUCKET_LABEL[k], count: bucketCounts[k] ?? 0 })),
  ];

  const SORTS: Array<{ key: Sort; label: string }> = [
    { key: "recent", label: "Recent" },
    { key: "rows", label: "Rows" },
    { key: "metrics", label: "Metrics" },
    { key: "connections", label: "Connections" },
  ];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-10 animate-fade-up">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-text-faint hover:text-text-secondary mb-6 transition-colors">
          <ArrowLeft size={14} /> Back
        </button>

        {/* Header band */}
        <div className="flex items-start justify-between gap-6 mb-6">
          <div>
            <h2 className="font-display text-4xl text-text-primary tracking-tight">
              Datasets
            </h2>
            <p className="text-sm text-text-tertiary mt-2 font-body max-w-2xl">
              Every entity the agent can reason over. Pick one to open its contract.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setShowPicker(true)}
              className="px-4 py-2.5 rounded-full bg-accent text-accent-text text-sm font-semibold hover:bg-accent-hover transition-all shadow-sm hover:shadow-md hover:-translate-y-0.5 active:scale-[0.98]"
            >
              + Add data
            </button>
            <div className="relative">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search…"
                className="w-52 pl-9 pr-4 py-2.5 text-sm font-body rounded-full bg-surface-raised border border-border text-text-primary placeholder:text-text-faint focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all"
              />
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-text-faint" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></svg>
            </div>
          </div>
        </div>

        {/* Portfolio stat strip — read the whole semantic layer in one glance */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <PortfolioStat
            icon={Database}
            label="Entities"
            value={unique.length}
            tone="text-text-primary"
          />
          <PortfolioStat
            icon={BarChart3}
            label="Governed metrics"
            value={totalMetrics}
            tone="text-accent"
          />
          <PortfolioStat
            icon={Layers}
            label="Rollups"
            value={totalRollups}
            tone="text-success"
          />
          <PortfolioStat
            icon={Link2}
            label="Relationships"
            value={edges.length}
            tone="text-success"
            hint={totalRows.toLocaleString() + " rows total"}
          />
        </div>

        {/* Filters + sort controls */}
        <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            {BUCKETS.map((b) => (
              <button
                key={b.key}
                onClick={() => setBucket(b.key)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-body transition-all",
                  bucket === b.key
                    ? "bg-accent text-accent-text shadow-sm"
                    : "bg-surface-raised border border-border text-text-secondary hover:border-border-strong hover:text-text-primary",
                )}
              >
                {b.label}
                <span className={cn(
                  "text-[10px] tabular-nums",
                  bucket === b.key ? "text-accent-text/80" : "text-text-faint",
                )}>
                  {b.count}
                </span>
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10.5px] text-text-faint font-body uppercase tracking-wider">
              sort
            </span>
            {SORTS.map((s) => (
              <button
                key={s.key}
                onClick={() => setSort(s.key)}
                className={cn(
                  "px-2.5 py-1 rounded-full text-[11px] font-body transition-all",
                  sort === s.key
                    ? "text-text-primary bg-surface-raised border border-border-strong"
                    : "text-text-tertiary hover:text-text-primary",
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Card grid */}
        {filtered.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map((ds, i) => (
              <EntityCard
                key={ds.dataset_id}
                dataset={ds}
                schema={schemas.get(ds.dataset_id) ?? null}
                relatedCount={relatedCount.get(ds.dataset_id) ?? 0}
                onOpen={() => setActiveDataset(ds.dataset_id)}
                index={i}
              />
            ))}
          </div>
        ) : (
          <div className="py-20 text-center rounded-3xl border border-border bg-surface-raised">
            <Database size={28} className="mx-auto text-text-faint mb-3" />
            <p className="text-sm text-text-faint font-body">
              {search || bucket !== "all"
                ? "Nothing matches your filter."
                : "No datasets loaded yet."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function PortfolioStat({
  icon: Icon,
  label,
  value,
  tone,
  hint,
}: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number | string;
  tone: string;
  hint?: string;
}) {
  return (
    <div className="p-4 rounded-2xl bg-surface-raised border border-border">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon size={12} className="text-text-faint" />
        <p className="text-[10px] text-text-faint font-body uppercase tracking-wider">
          {label}
        </p>
      </div>
      <p className={cn("text-2xl font-display tabular-nums", tone)}>{value}</p>
      {hint && (
        <p className="text-[10.5px] text-text-faint font-body mt-1 tabular-nums">
          {hint}
        </p>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   VIEW 3: Dataset Profile — polished semantic layer view
   ═══════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════
   VIEW 3 helpers — role groupings + column card
   ═══════════════════════════════════════════════════════ */

const ROLE_ORDER: Array<{
  key: "metric" | "temporal" | "dimension" | "identifier" | "auxiliary";
  label: string;
  blurb: string;
  tone: string;
}> = [
  { key: "metric", label: "Numbers", blurb: "Quantities the agent can aggregate.", tone: "text-accent" },
  { key: "temporal", label: "Time", blurb: "Date/time axes the agent rolls up by.", tone: "text-success" },
  { key: "dimension", label: "Categories", blurb: "Ways the agent can slice.", tone: "text-text-secondary" },
  { key: "identifier", label: "Keys", blurb: "Row-level identifiers and FK targets.", tone: "text-text-tertiary" },
  { key: "auxiliary", label: "Auxiliary", blurb: "Extra fields the agent can quote but rarely groups by.", tone: "text-text-faint" },
];

const EXEC_ROLE: Record<string, string> = {
  metric: "number",
  dimension: "category",
  temporal: "date/time",
  identifier: "label",
  auxiliary: "extra",
};

function ColumnCard({ col }: { col: SchemaSummary["columns"][number] }) {
  const execRole = EXEC_ROLE[col.role] ?? col.role;
  const label = col.label || col.name.replace(/[_-]+/g, " ");
  const hasSynonyms = (col.synonyms?.length ?? 0) > 0;
  return (
    <div className="p-4 rounded-xl bg-surface-raised border border-border hover:border-border-strong transition-colors">
      <div className="flex items-center justify-between mb-1.5 gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[14px] font-semibold text-text-primary capitalize truncate">
            {label}
          </span>
          <span
            className={cn(
              "text-[9px] font-medium px-1.5 py-0.5 rounded uppercase tracking-wider shrink-0",
              col.role === "metric" ? "bg-accent-soft text-accent" :
              col.role === "temporal" ? "bg-success-soft text-success" :
              col.role === "dimension" ? "bg-surface-sunken text-text-secondary" :
              "bg-surface-sunken text-text-faint",
            )}
          >
            {execRole}
          </span>
          {col.pii && (
            <span
              title="Personally identifiable — aggregate-only"
              className="flex items-center gap-1 text-[9px] font-medium px-1.5 py-0.5 rounded bg-warning-soft text-warning uppercase tracking-wider shrink-0"
            >
              <ShieldAlert size={8} /> PII
            </span>
          )}
          {col.label && col.label !== col.name && (
            <span className="text-[10px] font-mono text-text-faint truncate">
              {col.name}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-text-tertiary font-body shrink-0">
          {col.cardinality != null && <span>{formatNumber(col.cardinality)} unique</span>}
          {col.completeness != null && (
            <span className={col.completeness >= 0.95 ? "text-success" : col.completeness >= 0.8 ? "text-warning" : "text-error"}>
              {Math.round(col.completeness * 100)}% clean
            </span>
          )}
        </div>
      </div>
      {col.description && (
        <p className="text-[12.5px] text-text-faint font-body">{col.description}</p>
      )}

      {col.stats && (col.stats.min != null || col.stats.max != null || col.stats.mean != null) && (
        <p className="text-[10.5px] text-text-faint mt-1.5 font-mono">
          {col.stats.min != null && <>min {String(col.stats.min)}</>}
          {col.stats.max != null && <> · max {String(col.stats.max)}</>}
          {col.stats.mean != null && <> · avg {String(col.stats.mean)}</>}
        </p>
      )}
      {(col.sample_values?.length ?? 0) > 0 && (
        <div className="flex gap-1 mt-2 flex-wrap">
          {col.sample_values.slice(0, 4).map((v, j) => (
            <span key={j} className="text-[10.5px] text-text-faint bg-surface-sunken px-1.5 py-0.5 rounded-md font-mono">
              {String(v)}
            </span>
          ))}
        </div>
      )}
      {hasSynonyms && (
        <div className="flex flex-wrap gap-1 mt-2">
          <span className="text-[9px] text-text-faint uppercase tracking-wider font-body mr-0.5">
            a.k.a.
          </span>
          {col.synonyms!.slice(0, 5).map((s) => (
            <span
              key={s}
              className="text-[10px] text-text-secondary bg-surface-sunken px-1.5 py-0.5 rounded"
            >
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function RoleGroup({
  role,
  label,
  blurb,
  tone,
  cols,
}: {
  role: string;
  label: string;
  blurb: string;
  tone: string;
  cols: SchemaSummary["columns"];
}) {
  const [expanded, setExpanded] = useState(role === "metric" || role === "temporal");
  if (cols.length === 0) return null;
  return (
    <div className="rounded-2xl border border-border bg-surface-1/40">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-3">
          <ChevronRight
            size={14}
            className={cn(
              "text-text-tertiary transition-transform",
              expanded && "rotate-90",
            )}
          />
          <span className={cn("text-sm font-semibold font-body", tone)}>{label}</span>
          <span className="text-[11px] text-text-faint tabular-nums">
            {cols.length}
          </span>
          <span className="text-[11px] text-text-tertiary font-body hidden sm:inline">
            — {blurb}
          </span>
        </div>
      </button>
      {expanded && (
        <div className="px-4 pb-4 grid grid-cols-1 md:grid-cols-2 gap-2">
          {cols.map((c) => (
            <ColumnCard key={c.name} col={c} />
          ))}
        </div>
      )}
    </div>
  );
}

type AskChip = ReturnType<typeof deriveExecChips>[number];

function StarterChipsPanel({
  chips,
  onRun,
}: {
  chips: AskChip[];
  onRun: (text: string) => void;
}) {
  return (
    <div className="rounded-2xl border border-border bg-gradient-to-br from-accent-soft/40 to-surface-raised p-5 relative overflow-hidden">
      <div
        aria-hidden
        className="absolute -top-10 -right-10 w-40 h-40 rounded-full bg-accent/10 blur-2xl pointer-events-none"
      />
      <div className="relative">
        <div className="flex items-center gap-2 mb-1">
          <Zap size={13} className="text-accent" />
          <h2 className="text-sm font-semibold text-text-primary font-body">
            Ask this entity
          </h2>
        </div>
        <p className="text-[12px] text-text-tertiary font-body mb-3">
          Starter questions derived from the governed contract. Click to fire off a run.
        </p>
        <div className="flex flex-wrap gap-2">
          {chips.map((c) => {
            const Icon = c.icon as ComponentType<{ size?: number; className?: string }>;
            return (
              <button
                key={c.label}
                onClick={() => onRun(c.text)}
                className="group flex items-center gap-2 px-3.5 py-2 rounded-full bg-surface-0 border border-border hover:border-accent hover:bg-accent-soft hover:text-accent text-[12.5px] text-text-secondary font-body transition-all hover:-translate-y-0.5 shadow-xs hover:shadow-sm"
                title={c.text}
              >
                <Icon size={12} className="text-accent" />
                <span>{c.label}</span>
                <ArrowRight
                  size={11}
                  className="text-text-faint group-hover:text-accent transition-all opacity-0 -ml-1 group-hover:opacity-100 group-hover:ml-0"
                />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DatasetProfile() {
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);
  const sessionId = useSessionStore((s) => s.sessionId);
  const addQuery = useSessionStore((s) => s.addQuery);
  const datasets = useDatasetStore((s) => s.datasets);
  const fetchDatasets = useDatasetStore((s) => s.fetchDatasets);
  const activeDs = datasets.find((d) => d.dataset_id === activeDatasetId);
  const { schema, loading, refetch } = useSchema(activeDatasetId);
  const analyzeMode = useUIStore((s) => s.analyzeMode);
  const setAnalyzeMode = useUIStore((s) => s.setAnalyzeMode);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const resetAgent = useAgentStore((s) => s.reset);
  const addUserMessage = useAgentStore((s) => s.addUserMessage);

  const [historyOpen, setHistoryOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const refreshInputRef = useRef<HTMLInputElement>(null);

  const handleRefresh = useCallback(async (file: File) => {
    if (!activeDs) return;
    setRefreshing(true);
    setRefreshError(null);
    try {
      const slugOrId = schema?.entity?.slug ?? activeDs.dataset_id;
      await refreshDataset(slugOrId, file);
      await fetchDatasets();
      if (refetch) await refetch();
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }, [activeDs, schema?.entity?.slug, fetchDatasets, refetch]);

  const runStarter = useCallback(async (q: string) => {
    if (!activeDatasetId) return;
    resetAgent();
    addQuery(q, activeDatasetId);
    addUserMessage(q);
    try {
      await queryStream(sessionId, activeDatasetId, q, pushEvent);
    } catch (e) {
      pushEvent({
        type: "error",
        message: e instanceof Error ? e.message : "Failed to start run",
        recoverable: false,
      });
    }
  }, [activeDatasetId, sessionId, resetAgent, addQuery, addUserMessage, pushEvent]);

  const chips = useMemo(
    () => (activeDs ? deriveExecChips(schema ?? null, activeDs.name) : []),
    [schema, activeDs],
  );

  if (!activeDs) return null;
  if (analyzeMode) return <ReadyToQuery />;

  const entity = schema?.entity ?? null;
  const metrics = entity?.metrics ?? [];
  const rollups = entity?.rollups ?? [];
  const cols = schema?.columns ?? [];

  const metricColCount = cols.filter((c) => c.role === "metric").length;
  const dimensionColCount = cols.filter((c) => c.role === "dimension").length;
  const temporalColCount = cols.filter((c) => c.role === "temporal").length;
  const piiCount = cols.filter((c) => c.pii).length;
  const avgCompleteness = schema && cols.length
    ? Math.round(cols.reduce((s, c) => s + (c.completeness ?? 1), 0) / cols.length * 100)
    : null;

  // Exec-voice stat tiles.
  const STAT_CARDS = schema ? [
    {
      icon: BarChart3,
      label: metrics.length > 0 ? "Governed metrics" : "Numbers to track",
      value: metrics.length > 0 ? metrics.length : metricColCount,
      color: "text-accent",
    },
    {
      icon: Layers,
      label: "Ways to slice",
      value: dimensionColCount + temporalColCount,
      color: "text-success",
    },
    {
      icon: Columns3,
      label: "Fields",
      value: cols.length,
      color: "text-text-primary",
    },
    {
      icon: ShieldCheck,
      label: "Clean",
      value: avgCompleteness != null ? `${avgCompleteness}%` : "—",
      color: avgCompleteness != null && avgCompleteness >= 90 ? "text-success" : "text-warning",
    },
  ] : [];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-8 py-10 animate-fade-up">
        {/* Hidden input for Refresh flow */}
        <input
          ref={refreshInputRef}
          type="file"
          className="hidden"
          accept=".csv,.tsv,.parquet,.json,.xlsx,.xls"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleRefresh(f);
            e.target.value = "";
          }}
        />

        <button
          onClick={() => { setAnalyzeMode(false); setActiveDataset(null); }}
          className="flex items-center gap-1.5 text-sm text-text-faint hover:text-text-secondary mb-8 transition-colors"
        >
          <ArrowLeft size={14} /> All datasets
        </button>

        {/* ═══ Entity header — slug badge + business name + action bar ═══ */}
        <div className="flex items-start justify-between gap-6 mb-6">
          <div className="min-w-0">
            {entity && (
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] font-mono uppercase tracking-wider text-accent bg-accent-soft px-2 py-0.5 rounded">
                  entity
                </span>
                <span className="text-[11px] font-mono text-text-tertiary">
                  {entity.slug}
                </span>
                <span className="text-[11px] text-text-faint">·</span>
                <span className="text-[11px] font-body text-text-tertiary capitalize">
                  {activeDs.source_type.replace(/-/g, " ")}
                </span>
              </div>
            )}
            <h1 className="font-display text-4xl text-text-primary tracking-tight">
              {entity?.name ?? activeDs.name}
            </h1>
            <p className="text-sm text-text-tertiary mt-1.5 font-body">
              {activeDs.row_count.toLocaleString()} records · {activeDs.column_count} fields
              {entity && rollups.length > 0 && (
                <>
                  {" · "}
                  <span className="text-accent">
                    {rollups.length} rollup{rollups.length === 1 ? "" : "s"} pre-materialized
                  </span>
                </>
              )}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => refreshInputRef.current?.click()}
              disabled={refreshing}
              title="Re-ingest with a new file — slug, metrics, and labels are preserved"
              className={cn(
                "flex items-center gap-1.5 px-3 py-2 rounded-full border border-border bg-surface-raised text-xs font-body text-text-secondary hover:border-border-strong hover:text-text-primary transition-all",
                refreshing && "opacity-60 cursor-wait",
              )}
            >
              <RefreshCw size={12} className={cn(refreshing && "animate-spin")} />
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
            <button
              onClick={() => setHistoryOpen(true)}
              title="Change history"
              className="flex items-center gap-1.5 px-3 py-2 rounded-full border border-border bg-surface-raised text-xs font-body text-text-secondary hover:border-border-strong hover:text-text-primary transition-all"
            >
              <History size={12} /> History
            </button>
            <button
              onClick={() => setAnalyzeMode(true)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-accent text-accent-text text-sm font-semibold shadow-sm hover:bg-accent-hover hover:shadow-md transition-all duration-200 hover:-translate-y-0.5 active:scale-[0.98]"
            >
              Start analyzing <ChevronRight size={14} />
            </button>
          </div>
        </div>

        {refreshError && (
          <div className="mb-6 flex items-start gap-2 p-3 rounded-xl bg-error-soft/40 border border-error/30 text-sm text-error font-body">
            <ShieldAlert size={14} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">Refresh failed</p>
              <p className="text-text-secondary text-xs mt-0.5">{refreshError}</p>
            </div>
          </div>
        )}

        {/* Description */}
        {schema && (entity?.description || schema.description) && (
          <p className="text-[15px] text-text-secondary leading-relaxed mb-8 font-body">
            {entity?.description || describeDataset(schema)}
          </p>
        )}

        {/* ═══ Relationships constellation — THIS entity inside the semantic layer ═══ */}
        {datasets.length >= 1 && schema && (
          <section className="mb-10">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-sm font-semibold text-text-primary font-body">
                  Where this sits
                </h2>
                <p className="text-[12px] text-text-tertiary font-body mt-0.5">
                  How this entity links to the rest of the semantic layer. Click a neighbor to jump.
                </p>
              </div>
              <span className="text-[10px] font-mono text-text-faint uppercase tracking-wider">
                focused view
              </span>
            </div>
            <SemanticGraph
              datasets={datasets}
              focusId={activeDatasetId}
              onSelect={(id) => {
                if (id !== activeDatasetId) {
                  setAnalyzeMode(false);
                  setActiveDataset(id);
                }
              }}
            />
          </section>
        )}

        {/* ═══ Stat row ═══ */}
        {schema && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-10">
            {STAT_CARDS.map(({ label, value, color, icon: Icon }) => (
              <div
                key={label}
                className="p-4 rounded-2xl bg-surface-raised border border-border"
              >
                <div className="flex items-center gap-1.5 mb-2">
                  <Icon size={12} className="text-text-faint" />
                  <p className="text-[10px] text-text-faint font-body uppercase tracking-wider">
                    {label}
                  </p>
                </div>
                <p className={cn("text-2xl font-display tabular-nums", color)}>
                  {value}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* ═══ Governed metrics — only renders when entity declares them ═══ */}
        {metrics.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary font-body">
                  Governed metrics
                </h2>
                <p className="text-[12px] text-text-tertiary font-body mt-0.5">
                  Business definitions the agent uses — every answer cites one of these.
                </p>
              </div>
              <span className="text-[10px] font-mono text-text-faint uppercase tracking-wider">
                {metrics.length} declared
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {metrics.map((m) => (
                <MetricCard key={m.slug} metric={m} />
              ))}
            </div>
          </section>
        )}

        {/* ═══ Pre-materialized rollups rail ═══ */}
        {rollups.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-text-primary font-body">
                Pre-materialized slices
              </h2>
              <span className="text-[11px] text-text-tertiary font-body">
                Agent pulls from these when the slice matches — no full-table scan.
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {rollups.map((r) => (
                <RollupChip key={r.slug} rollup={r} />
              ))}
            </div>
          </section>
        )}

        {/* ═══ Starter questions — click fires a run, auto-routes to ActiveWorkspace ═══ */}
        {chips.length > 0 && (
          <section className="mb-10">
            <StarterChipsPanel chips={chips} onRun={runStarter} />
          </section>
        )}

        {/* Role bar + PII callout */}
        {schema && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-text-primary font-body">
                Role composition
              </h2>
              {piiCount > 0 && (
                <span className="flex items-center gap-1.5 text-[11px] text-warning font-body">
                  <ShieldAlert size={11} />
                  {piiCount} PII field{piiCount === 1 ? "" : "s"} — aggregate-only
                </span>
              )}
            </div>
            <RoleBar columns={schema.columns} showLabels />
          </section>
        )}

        {loading && (
          <div className="space-y-4">
            {[...Array(4)].map((_, i) => <div key={i} className="h-24 rounded-2xl animate-shimmer" />)}
          </div>
        )}

        {/* ═══ Columns grouped by role — collapsible ═══ */}
        {schema && (
          <section className="mb-10">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-text-primary font-body">
                Schema
              </h2>
              <span className="text-[11px] text-text-faint font-body">
                {cols.length} fields · click a role to expand
              </span>
            </div>
            <div className="space-y-2">
              {ROLE_ORDER.map((r) => {
                const grouped = cols.filter((c) => c.role === r.key);
                return (
                  <RoleGroup
                    key={r.key}
                    role={r.key}
                    label={r.label}
                    blurb={r.blurb}
                    tone={r.tone}
                    cols={grouped}
                  />
                );
              })}
            </div>
          </section>
        )}

        {/* Provenance footer — entity is the identity, physical rotates beneath */}
        {entity && (
          <div className="mt-8 pt-4 border-t border-border flex items-center justify-between text-[10.5px] font-mono text-text-faint">
            <div className="flex items-center gap-3">
              <span>entity: <span className="text-text-secondary">{entity.slug}</span></span>
              <span>·</span>
              <span>physical: <span className="text-text-secondary">{entity.physical_table}</span></span>
            </div>
            <button
              onClick={() => setHistoryOpen(true)}
              className="flex items-center gap-1 hover:text-text-secondary transition-colors font-body"
            >
              <History size={10} /> change history
            </button>
          </div>
        )}

        {/* Bottom CTA */}
        <div className="mt-10 mb-8">
          <button onClick={() => setAnalyzeMode(true)}
            className="w-full flex items-center justify-center gap-2.5 py-4 rounded-full bg-accent text-accent-text font-semibold text-base shadow-sm hover:bg-accent-hover hover:shadow-md transition-all duration-200 hover:-translate-y-0.5 active:scale-[0.98]">
            Start analyzing <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {historyOpen && activeDatasetId && (
        <HistoryDrawer
          datasetId={activeDatasetId}
          onClose={() => setHistoryOpen(false)}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   VIEW 4: Ready to Query — input + suggestions
   ═══════════════════════════════════════════════════════ */

function getGreeting(datasetName: string): string {
  const h = new Date().getHours();
  const pick = (arr: string[]) => arr[Math.floor(Math.random() * arr.length)];

  const morning = [
    "Fresh data, fresh insights.",
    "What story is hiding in here?",
    `Morning. ${datasetName} is ready.`,
    "Let's find something interesting.",
    "Coffee and queries. Let's go.",
  ];

  const afternoon = [
    "What are we looking for?",
    `${datasetName}, meet curiosity.`,
    "Ask anything. Seriously.",
    "Your data has been waiting.",
    "Let's dig in.",
  ];

  const evening = [
    "Late-night data session.",
    `${datasetName} is ready when you are.`,
    "The best insights come after hours.",
    "Quiet hours, loud data.",
    "Let's see what the data says.",
  ];

  const anytime = [
    "What do you want to know?",
    "Your data. Your questions.",
    `${datasetName} is loaded and listening.`,
    "Ask a question, get a dashboard.",
    "No SQL required.",
  ];

  const pool = h < 12 ? morning : h < 17 ? afternoon : evening;
  return Math.random() < 0.3 ? pick(anytime) : pick(pool);
}

function ReadyToQuery() {
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const sessionId = useSessionStore((s) => s.sessionId);
  const addQuery = useSessionStore((s) => s.addQuery);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const reset = useAgentStore((s) => s.reset);
  const setAnalyzeMode = useUIStore((s) => s.setAnalyzeMode);
  const datasets = useDatasetStore((s) => s.datasets);
  const activeDs = datasets.find((d) => d.dataset_id === activeDatasetId);
  const { schema } = useSchema(activeDatasetId);

  const addUserMessage = useAgentStore((s) => s.addUserMessage);

  const runSuggestion = useCallback(async (q: string) => {
    if (!activeDatasetId) return;
    reset(); addQuery(q, activeDatasetId); addUserMessage(q);
    try { await queryStream(sessionId, activeDatasetId, q, pushEvent); }
    catch (e) { pushEvent({ type: "error", message: e instanceof Error ? e.message : "Failed", recoverable: false }); }
  }, [activeDatasetId, sessionId, addQuery, addUserMessage, pushEvent, reset]);

  if (!activeDs) return null;

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      {/* Greeting */}
      <h1 className="animate-fade-rise font-display text-4xl sm:text-5xl text-text-primary tracking-tight text-center mb-10">
        {getGreeting(activeDs.name)}
      </h1>

      {/* Input */}
      <div className="animate-fade-rise-delay w-full max-w-2xl mb-6">
        <QueryInput variant="hero" />
      </div>

      {/* Suggestion chips — exec-voice, derived from this dataset's schema */}
      <div className="animate-fade-rise-delay-2 flex flex-wrap justify-center gap-2">
        {deriveExecChips(schema ?? null, activeDs.name).map(({ icon: Icon, label, text }) => (
          <button key={label} onClick={() => runSuggestion(text)}
            className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary bg-surface-raised hover:bg-surface-1 border border-border hover:border-border-strong px-4 py-2.5 rounded-full shadow-xs hover:shadow-sm transition-all duration-200 font-body">
            <Icon size={14} className="text-text-tertiary" />
            {label}
          </button>
        ))}
      </div>

      {/* Dataset context */}
      <button
        onClick={() => { setAnalyzeMode(false); setActiveDataset(null); }}
        className="animate-fade-rise-delay-3 mt-8 text-xs text-text-faint hover:text-text-secondary transition-colors font-body"
      >
        Analyzing {activeDs.name} · {activeDs.row_count.toLocaleString()} rows · Change
      </button>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   VIEW 5: Active Workspace — agent running / results
   ═══════════════════════════════════════════════════════ */

function ActiveWorkspace() {
  const artifact = useAgentStore((s) => s.artifact);
  const buildingArtifact = useAgentStore((s) => s.buildingArtifact);

  const artifactOpen = useUIStore((s) => s.artifactOpen);
  const artifactFullscreen = useUIStore((s) => s.artifactFullscreen);
  const setArtifactOpen = useUIStore((s) => s.setArtifactOpen);
  const setArtifactFullscreen = useUIStore((s) => s.setArtifactFullscreen);
  const expandedVisual = useUIStore((s) => s.expandedVisual);
  const expandedVisualFullscreen = useUIStore((s) => s.expandedVisualFullscreen);
  const setExpandedVisual = useUIStore((s) => s.setExpandedVisual);
  const setExpandedVisualFullscreen = useUIStore((s) => s.setExpandedVisualFullscreen);

  // Auto-open the panel when a new artifact arrives — OR as soon as
  // the agent starts building one (so the skeleton is visible during
  // the 30s–3m repair pass, not just after it finishes).
  useEffect(() => {
    if (artifact) setArtifactOpen(true);
  }, [artifact?.id, setArtifactOpen]);

  useEffect(() => {
    if (buildingArtifact) setArtifactOpen(true);
  }, [buildingArtifact?.artifact_id, setArtifactOpen]);

  const showArtifact = (!!artifact || !!buildingArtifact) && artifactOpen;
  const showVisual = !!expandedVisual;

  // Fullscreen: visual takes precedence if it's in fullscreen, else artifact
  if (showVisual && expandedVisualFullscreen) {
    return (
      <div className="flex flex-1 min-h-0 w-full">
        <div className="flex-1 min-w-0">
          <InlineVisualPanel
            fullscreen
            onToggleFullscreen={() => setExpandedVisualFullscreen(false)}
            onClose={() => setExpandedVisual(null)}
          />
        </div>
      </div>
    );
  }
  if (showArtifact && artifactFullscreen) {
    return (
      <div className="flex flex-1 min-h-0 w-full">
        <div className="flex-1 min-w-0">
          <ArtifactPanel
            fullscreen
            onToggleFullscreen={() => setArtifactFullscreen(false)}
            onClose={() => setArtifactOpen(false)}
          />
        </div>
      </div>
    );
  }

  // Only one side panel at a time — the most recently opened slot wins.
  const showRightPanel = showVisual || showArtifact;

  return (
    <div className="flex flex-1 min-h-0">
      <div className={cn("flex flex-col min-w-0 min-h-0", showRightPanel ? "w-1/2" : "flex-1")}>
        <ConversationStream />
        <div className="px-6 pt-4 pb-6 border-t border-border shrink-0 bg-surface-0">
          <QueryInput variant="compact" />
        </div>
      </div>

      {showVisual ? (
        <div className="w-1/2">
          <InlineVisualPanel
            onToggleFullscreen={() => setExpandedVisualFullscreen(true)}
            onClose={() => setExpandedVisual(null)}
          />
        </div>
      ) : showArtifact ? (
        <div className="w-1/2">
          <ArtifactPanel
            onToggleFullscreen={() => setArtifactFullscreen(true)}
            onClose={() => setArtifactOpen(false)}
          />
        </div>
      ) : null}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   ROOT: Route between all views
   ═══════════════════════════════════════════════════════ */

export function MainWorkspace() {
  const events = useAgentStore((s) => s.events);
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const processingActive = useProcessingStore((s) => s.active);
  const hasContent = events.length > 0;

  return (
    <main className="flex-1 flex flex-col min-w-0 bg-surface-0 relative" role="main">
      {processingActive
        ? <ProcessingWizard />
        : hasContent
          ? <ActiveWorkspace />
          : activeDatasetId
            ? <DatasetProfile />
            : <FirstOpen />}
    </main>
  );
}
