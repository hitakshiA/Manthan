import { useState, useCallback, useRef } from "react";
import { motion } from "motion/react";
import { FileText, Cloud, Database, Plug, X, Link2, File as FileIcon, Trash2, ShieldCheck } from "lucide-react";
import {
  uploadDatasetAsync,
  uploadMultiDataset,
} from "@/api/datasets";
import { useProcessingStore } from "@/stores/processing-store";
import { BASE_URL } from "@/api/client";
import { cn } from "@/lib/utils";
import { ConnectorIcon } from "./ConnectorIcon";

/**
 * Source picker — the production entry point for any ingestion.
 * Four tabs:
 *   - Files: drag-drop multi-file / folder, pipes to /datasets/upload-multi
 *   - Cloud URL: paste https/s3/gs/az URL, pipes to /datasets/connect-url
 *   - Database: Postgres/MySQL/SQLite connection form, pipes to /datasets/connect
 *   - SaaS: placeholder listing dlt-backed connectors (Phase 6)
 *
 * Rendered as a scrim + modal overlay. Close via the X or Escape.
 */

type Tab = "files" | "cloud" | "database" | "saas";

export function SourcePicker({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("files");
  return (
    <>
      <div
        className="fixed inset-0 bg-black/35 z-40 animate-fade-in"
        onClick={onClose}
        aria-hidden
      />
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="fixed inset-0 z-50 flex items-center justify-center p-6 pointer-events-none"
      >
        <div className="pointer-events-auto bg-surface-0 border border-border rounded-2xl shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[86vh]">
          <header className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
            <div>
              <h2 className="text-lg font-display text-text-primary">Add data</h2>
              <p className="text-xs text-text-tertiary font-body mt-0.5">
                Drop a file, paste a URL, or connect a warehouse.
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 text-text-faint hover:text-text-secondary rounded-md hover:bg-surface-sunken transition-all"
            >
              <X size={14} />
            </button>
          </header>

          <nav className="flex border-b border-border bg-surface-1 shrink-0">
            {(
              [
                { id: "files", label: "Files", icon: FileText },
                { id: "cloud", label: "Cloud URL", icon: Cloud },
                { id: "database", label: "Database", icon: Database },
                { id: "saas", label: "Apps", icon: Plug },
              ] as const
            ).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2.5 text-sm font-body transition-colors border-b-2",
                  tab === id
                    ? "text-accent border-accent"
                    : "text-text-secondary border-transparent hover:text-text-primary",
                )}
              >
                <Icon size={13} /> {label}
              </button>
            ))}
          </nav>

          <div className="flex-1 overflow-y-auto p-5 font-body">
            {tab === "files" && <FilesPanel onClose={onClose} />}
            {tab === "cloud" && <CloudPanel onClose={onClose} />}
            {tab === "database" && <DatabasePanel onClose={onClose} />}
            {tab === "saas" && <SaasPanel />}
          </div>
        </div>
      </motion.div>
    </>
  );
}

// ── Files ────────────────────────────────────────────────────────

function FilesPanel({ onClose }: { onClose: () => void }) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [staged, setStaged] = useState<File[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const startProcessing = useProcessingStore((s) => s.startProcessing);

  const addFiles = useCallback((files: File[]) => {
    setStaged((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}-${f.size}`));
      const next = [...prev];
      for (const f of files) {
        if (!seen.has(`${f.name}-${f.size}`)) next.push(f);
      }
      return next;
    });
  }, []);

  const removeAt = (i: number) =>
    setStaged((prev) => prev.filter((_, j) => j !== i));

  const commit = useCallback(async () => {
    if (staged.length === 0 || uploading) return;
    setUploading(true);
    try {
      if (staged.length === 1) {
        const { dataset_id } = await uploadDatasetAsync(staged[0]);
        startProcessing(dataset_id);
      } else {
        const ds = await uploadMultiDataset(staged);
        startProcessing(ds.dataset_id);
      }
      onClose();
    } finally {
      setUploading(false);
    }
  }, [staged, uploading, startProcessing, onClose]);

  const totalBytes = staged.reduce((s, f) => s + f.size, 0);
  const formatBytes = (b: number) => {
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
    return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
  };

  return (
    <div className="space-y-4">
      <input
        ref={fileRef}
        type="file"
        multiple
        className="hidden"
        accept=".csv,.tsv,.parquet,.json,.xlsx,.xls"
        onChange={(e) => {
          const f = Array.from(e.target.files ?? []);
          if (f.length > 0) addFiles(f);
          e.target.value = "";
        }}
      />
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const allowed = /\.(csv|tsv|parquet|json|xlsx|xls)$/i;
          const files = Array.from(e.dataTransfer.files ?? []).filter((f) =>
            allowed.test(f.name),
          );
          if (files.length > 0) addFiles(files);
        }}
        onClick={() => fileRef.current?.click()}
        className={cn(
          "rounded-xl border-2 border-dashed p-10 cursor-pointer transition-all flex flex-col items-center justify-center",
          dragOver
            ? "border-accent bg-accent-soft/50"
            : "border-border hover:border-border-strong bg-surface-1",
        )}
      >
        <FileText size={28} className="text-text-tertiary mb-3" />
        <p className="text-sm text-text-primary font-body text-center">
          {staged.length > 0
            ? "Add more files or drop a whole folder"
            : "Drop files here or click to browse"}
        </p>
        <p className="text-[11px] text-text-tertiary mt-1.5 text-center max-w-md">
          CSV · TSV · Parquet · Excel · JSON · multi-file → bundle with auto-detected relationships
        </p>
      </div>

      {/* Staged bundle preview */}
      {staged.length > 0 && (
        <div className="rounded-xl border border-border bg-surface-1 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-surface-raised">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase tracking-wider text-text-tertiary">
                {staged.length === 1 ? "File" : `Bundle · ${staged.length} files`}
              </span>
              <span className="text-[10px] font-mono text-text-faint">
                {formatBytes(totalBytes)}
              </span>
            </div>
            {staged.length > 1 && (
              <span className="flex items-center gap-1 text-[10px] text-accent font-body">
                <ShieldCheck size={10} /> FK relationships will be auto-detected
              </span>
            )}
          </div>
          <ul className="max-h-40 overflow-y-auto divide-y divide-border">
            {staged.map((f, i) => (
              <li
                key={`${f.name}-${f.size}-${i}`}
                className="flex items-center gap-3 px-4 py-2 text-sm font-body"
              >
                <FileIcon size={13} className="text-text-tertiary shrink-0" />
                <span className="flex-1 truncate text-text-primary">{f.name}</span>
                <span className="text-[11px] font-mono text-text-faint shrink-0">
                  {formatBytes(f.size)}
                </span>
                <button
                  onClick={() => removeAt(i)}
                  className="p-1 text-text-faint hover:text-error rounded-md hover:bg-surface-sunken transition-colors"
                  aria-label="Remove"
                >
                  <Trash2 size={12} />
                </button>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-end gap-2 px-4 py-2.5 border-t border-border bg-surface-raised">
            <button
              onClick={() => setStaged([])}
              className="text-xs text-text-tertiary hover:text-text-primary font-body"
            >
              Clear
            </button>
            <button
              onClick={commit}
              disabled={uploading}
              className="px-4 py-1.5 rounded-full bg-accent text-accent-text text-sm font-semibold disabled:opacity-50 hover:bg-accent-hover transition-colors"
            >
              {uploading
                ? "Uploading…"
                : staged.length === 1
                  ? "Ingest file"
                  : `Ingest ${staged.length}-file bundle`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Cloud URL ────────────────────────────────────────────────────

function CloudPanel({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState("");
  const [connId, setConnId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const startProcessing = useProcessingStore((s) => s.startProcessing);

  const submit = async () => {
    if (!url.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${BASE_URL}/datasets/connect-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim(),
          connection_id: connId.trim() || undefined,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const ds = await res.json();
      startProcessing(ds.dataset_id);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to connect.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-text-secondary mb-1.5 font-body">
          URL to ingest
        </label>
        <div className="flex items-center gap-2">
          <Link2 size={14} className="text-text-tertiary shrink-0" />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://host/path/file.csv or s3://bucket/key.parquet"
            className="flex-1 bg-surface-raised border border-border text-sm text-text-primary rounded-lg px-3 py-2 font-mono focus:outline-none focus:border-border-strong"
          />
        </div>
        <div className="flex items-center gap-1.5 mt-2 text-[11px] text-text-tertiary flex-wrap">
          <span>Supports</span>
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-surface-1 border border-border">
            <Link2 size={10} /> https
          </span>
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-surface-1 border border-border">
            <ConnectorIcon slug="s3" size={11} /> s3://
          </span>
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-surface-1 border border-border">
            <ConnectorIcon slug="gcs" size={11} /> gs://
          </span>
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-surface-1 border border-border">
            <ConnectorIcon slug="azure" size={11} /> az://
          </span>
          <span>· public URLs work without auth.</span>
        </div>
      </div>
      <div>
        <label className="block text-xs text-text-secondary mb-1.5 font-body">
          Saved connection (optional — for private buckets)
        </label>
        <input
          value={connId}
          onChange={(e) => setConnId(e.target.value)}
          placeholder="conn_…"
          className="w-full bg-surface-raised border border-border text-sm text-text-primary rounded-lg px-3 py-2 font-mono focus:outline-none focus:border-border-strong"
        />
      </div>
      {err && (
        <p className="text-xs text-error bg-error-soft px-3 py-2 rounded-lg font-body">
          {err}
        </p>
      )}
      <div className="flex justify-end gap-2 pt-2">
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary"
        >
          Cancel
        </button>
        <button
          onClick={submit}
          disabled={!url.trim() || busy}
          className="px-4 py-1.5 rounded-full bg-accent text-accent-text text-sm disabled:opacity-50 hover:bg-accent-hover transition-colors"
        >
          {busy ? "Connecting…" : "Ingest"}
        </button>
      </div>
    </div>
  );
}

// ── Database ─────────────────────────────────────────────────────

function DatabasePanel({ onClose }: { onClose: () => void }) {
  type DbKind = "postgres" | "mysql" | "sqlite";
  const [sourceType, setSourceType] = useState<DbKind>("postgres");
  // Form-mode fields — assembled into a libpq-style connection string
  // at submit time. Most users paste host/user/password individually
  // rather than constructing the full string, so form mode is the
  // default. Raw mode is available via the toggle for power users.
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [dbname, setDbname] = useState("");
  const [sqlitePath, setSqlitePath] = useState("");
  const [rawMode, setRawMode] = useState(false);
  const [rawConnStr, setRawConnStr] = useState("");
  const [sourceTable, setSourceTable] = useState("");
  const [destTable, setDestTable] = useState("raw_imported");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const startProcessing = useProcessingStore((s) => s.startProcessing);

  const defaultPort = sourceType === "postgres" ? "5432" : "3306";

  // Which fields are missing — used to show inline field-level hints
  // and to keep the submit button disabled until the form is valid.
  const validation: { field: string; message: string }[] = (() => {
    const out: { field: string; message: string }[] = [];
    if (sourceType === "sqlite") {
      if (!sqlitePath.trim()) {
        out.push({ field: "sqlitePath", message: "Path to the .db file." });
      }
    } else if (rawMode) {
      if (!rawConnStr.trim())
        out.push({
          field: "rawConnStr",
          message: "Paste a libpq-style connection string.",
        });
    } else {
      if (!host.trim()) out.push({ field: "host", message: "Host is required." });
      if (!user.trim()) out.push({ field: "user", message: "User is required." });
      if (!dbname.trim())
        out.push({ field: "dbname", message: "Database name is required." });
      if (port && !/^\d+$/.test(port.trim()))
        out.push({ field: "port", message: "Port must be a number." });
    }
    if (!sourceTable.trim())
      out.push({ field: "sourceTable", message: "Source table is required." });
    return out;
  })();
  const invalidFields = new Set(validation.map((v) => v.field));
  const valid = validation.length === 0;

  // Assemble the connection string from the form fields. MySQL and
  // Postgres both accept whitespace-separated ``key=value`` tokens;
  // the backend's mysql-specific param normalizer translates
  // ``password`` → ``passwd`` / ``dbname`` → ``db`` where needed.
  const buildConnStr = (): string => {
    if (sourceType === "sqlite") return sqlitePath.trim();
    if (rawMode) return rawConnStr.trim();
    const parts: string[] = [];
    if (host.trim()) parts.push(`host=${host.trim()}`);
    if (port.trim()) parts.push(`port=${port.trim()}`);
    else parts.push(`port=${defaultPort}`);
    if (user.trim()) parts.push(`user=${user.trim()}`);
    if (password) parts.push(`password=${password}`);
    if (dbname.trim()) parts.push(`dbname=${dbname.trim()}`);
    return parts.join(" ");
  };

  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${BASE_URL}/datasets/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_type: sourceType,
          connection_string: buildConnStr(),
          source_table: sourceTable,
          destination_table: destTable || "raw_imported",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const ds = await res.json();
      startProcessing(ds.dataset_id);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to connect.");
    } finally {
      setBusy(false);
    }
  };

  const fieldClass = (field: string) =>
    cn(
      "w-full bg-surface-raised border text-sm text-text-primary rounded-lg px-3 py-2 font-mono focus:outline-none",
      invalidFields.has(field)
        ? "border-error/40 focus:border-error"
        : "border-border focus:border-border-strong",
    );

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-text-secondary mb-1.5 font-body">
          Database
        </label>
        <div className="flex gap-2">
          {(["postgres", "mysql", "sqlite"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setSourceType(t)}
              className={cn(
                "px-3 py-1.5 rounded-lg border text-sm transition-colors inline-flex items-center gap-2",
                sourceType === t
                  ? "border-accent bg-accent-soft text-accent"
                  : "border-border text-text-secondary hover:text-text-primary",
              )}
            >
              <ConnectorIcon
                slug={t}
                size={14}
                // When selected, force the accent color so the brand
                // mark doesn't fight the pill's on-state tint. When
                // idle, show the brand hue so the pill still reads
                // as a Postgres/MySQL/SQLite option at a glance.
                mono={sourceType === t}
              />
              {t === "postgres"
                ? "Postgres"
                : t === "mysql"
                  ? "MySQL"
                  : "SQLite"}
            </button>
          ))}
        </div>
      </div>

      {sourceType === "sqlite" ? (
        <div>
          <label className="block text-xs text-text-secondary mb-1.5 font-body">
            SQLite file path
          </label>
          <input
            value={sqlitePath}
            onChange={(e) => setSqlitePath(e.target.value)}
            placeholder="/path/to/database.db"
            className={fieldClass("sqlitePath")}
          />
          <p className="text-[11px] text-text-tertiary mt-1.5">
            Absolute path on the server — we read the file via DuckDB's
            <code className="font-mono mx-1">sqlite_scanner</code> extension.
          </p>
        </div>
      ) : rawMode ? (
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-xs text-text-secondary font-body">
              Connection string
            </label>
            <button
              type="button"
              onClick={() => setRawMode(false)}
              className="text-[11px] text-accent hover:underline"
            >
              Use form fields →
            </button>
          </div>
          <input
            value={rawConnStr}
            onChange={(e) => setRawConnStr(e.target.value)}
            placeholder={
              sourceType === "postgres"
                ? "host=… port=5432 user=… password=… dbname=…"
                : "host=… port=3306 user=… passwd=… db=…"
            }
            className={fieldClass("rawConnStr")}
            type="password"
          />
          <p className="text-[11px] text-text-tertiary mt-1.5">
            Whitespace-separated <code className="font-mono">key=value</code>{" "}
            tokens. Credentials are used once; a read-only role is
            recommended.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-[11px] text-text-tertiary font-body">
              Fill in the fields below — we'll assemble the connection
              string. Credentials are used once; a read-only role is
              recommended.
            </p>
            <button
              type="button"
              onClick={() => setRawMode(true)}
              className="text-[11px] text-accent hover:underline shrink-0 ml-3"
            >
              Paste string →
            </button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2">
              <label className="block text-[11px] text-text-secondary mb-1 font-body">
                Host
              </label>
              <input
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="db.example.com"
                className={fieldClass("host")}
              />
            </div>
            <div>
              <label className="block text-[11px] text-text-secondary mb-1 font-body">
                Port
              </label>
              <input
                value={port}
                onChange={(e) => setPort(e.target.value)}
                placeholder={defaultPort}
                className={fieldClass("port")}
                inputMode="numeric"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] text-text-secondary mb-1 font-body">
                User
              </label>
              <input
                value={user}
                onChange={(e) => setUser(e.target.value)}
                placeholder="readonly_user"
                className={fieldClass("user")}
              />
            </div>
            <div>
              <label className="block text-[11px] text-text-secondary mb-1 font-body">
                Password
              </label>
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="leave blank if none"
                className={fieldClass("password")}
                type="password"
              />
            </div>
          </div>
          <div>
            <label className="block text-[11px] text-text-secondary mb-1 font-body">
              Database name
            </label>
            <input
              value={dbname}
              onChange={(e) => setDbname(e.target.value)}
              placeholder={sourceType === "postgres" ? "postgres" : "mydb"}
              className={fieldClass("dbname")}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-text-secondary mb-1.5 font-body">
            Source table
          </label>
          <input
            value={sourceTable}
            onChange={(e) => setSourceTable(e.target.value)}
            placeholder={
              sourceType === "postgres"
                ? "public.orders"
                : sourceType === "mysql"
                  ? "orders"
                  : "orders"
            }
            className={fieldClass("sourceTable")}
          />
        </div>
        <div>
          <label className="block text-xs text-text-secondary mb-1.5 font-body">
            Destination table
          </label>
          <input
            value={destTable}
            onChange={(e) => setDestTable(e.target.value)}
            placeholder="raw_orders"
            className={fieldClass("destTable")}
          />
        </div>
      </div>

      {validation.length > 0 && (
        <ul className="text-[11px] text-text-tertiary space-y-0.5">
          {validation.map((v) => (
            <li key={v.field}>· {v.message}</li>
          ))}
        </ul>
      )}
      {err && (
        <p className="text-xs text-error bg-error-soft px-3 py-2 rounded-lg font-body">
          {err}
        </p>
      )}
      <div className="flex justify-end gap-2 pt-2">
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary"
        >
          Cancel
        </button>
        <button
          onClick={submit}
          disabled={!valid || busy}
          className="px-4 py-1.5 rounded-full bg-accent text-accent-text text-sm disabled:opacity-50 hover:bg-accent-hover transition-colors"
        >
          {busy ? "Connecting…" : "Connect"}
        </button>
      </div>
    </div>
  );
}

// ── SaaS ─────────────────────────────────────────────────────────

function SaasPanel() {
  const apps: {
    label: string;
    slug:
      | "stripe"
      | "hubspot"
      | "salesforce"
      | "shopify"
      | "notion"
      | "airtable"
      | "googleads"
      | "meta"
      | "github"
      | "slack";
  }[] = [
    { label: "Stripe", slug: "stripe" },
    { label: "HubSpot", slug: "hubspot" },
    { label: "Salesforce", slug: "salesforce" },
    { label: "Shopify", slug: "shopify" },
    { label: "Notion", slug: "notion" },
    { label: "Airtable", slug: "airtable" },
    { label: "Google Ads", slug: "googleads" },
    { label: "Meta Ads", slug: "meta" },
    { label: "GitHub", slug: "github" },
    { label: "Slack", slug: "slack" },
  ];
  return (
    <div>
      <p className="text-sm text-text-secondary mb-4 font-body">
        SaaS connectors run on the <code className="font-mono">dlt</code>{" "}
        library and land in your workspace as standard datasets.
      </p>
      <div className="grid grid-cols-3 gap-2">
        {apps.map((a) => (
          <div
            key={a.slug}
            className="rounded-lg border border-border bg-surface-1 px-3 py-2.5 text-sm text-text-primary font-body flex items-center gap-2.5"
          >
            <ConnectorIcon slug={a.slug} size={18} showBackground />
            <span className="flex-1 truncate">{a.label}</span>
            <span className="text-[10px] text-text-faint uppercase tracking-wider shrink-0">
              Coming
            </span>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-text-tertiary mt-4">
        Custom connector? Paste an OpenAPI spec URL and we'll scaffold
        one for you.
      </p>
    </div>
  );
}
