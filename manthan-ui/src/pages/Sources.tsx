/**
 * Sources - connected data sources, brand-tile grid.
 *
 * Each source is a square-ish tile dominated by its brand logo, with a
 * faint wash of the brand hex behind the icon. Hover lifts the tile
 * slightly. Click to drill into the source detail (not wired yet -
 * `href={null}` for now). Wired to /api/sources.
 *
 * Layout: 4-column grid (auto-fits down at narrow widths). A short
 * editorial header sits above; a thin footer with totals sits below.
 */

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Database, Key } from "lucide-react";

import {
  getSourceCoralDetail,
  listSources,
  type ApiSource,
  type SourceCoralDetail,
} from "@/lib/api";
import { getSource } from "@/lib/sources";

const CATEGORY_LABELS: Record<string, string> = {
  payments: "Payments",
  crm: "CRM",
  support: "Support",
  comms: "Comms",
  knowledge: "Knowledge",
  docs: "Docs",
  policy_docs: "Policy docs",
  analytics: "Analytics",
  product_analytics: "Product analytics",
  ops: "Observability",
  observability: "Observability",
  identity: "Identity",
  feature_flags: "Feature flags",
  issue_tracking: "Issue tracking",
  incident: "Incident",
  version_control: "Version control",
  infra: "Infra",
  marketing: "Marketing",
  billing: "Billing",
};

// ──────────────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────────────

export default function Sources() {
  const [data, setData] = useState<ApiSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "connected" | "available">(
    "all",
  );
  const [q, setQ] = useState("");
  const [openSourceId, setOpenSourceId] = useState<string | null>(null);

  useEffect(() => {
    listSources()
      .then((r) => setData(r.sources))
      .catch((e: Error) => setError(e.message));
  }, []);

  const filtered = useMemo(() => {
    if (!data) return null;
    return data.filter((s) => {
      if (filter === "connected" && s.status !== "connected") return false;
      if (filter === "available" && s.status !== "available") return false;
      if (q && !s.name.toLowerCase().includes(q.toLowerCase())) return false;
      return true;
    });
  }, [data, filter, q]);

  const totals = useMemo(() => {
    if (!data) return null;
    const connected = data.filter((s) => s.status === "connected").length;
    const available = data.length - connected;
    return { connected, available, total: data.length };
  }, [data]);

  return (
    <div
      className="h-full w-full overflow-y-auto"
      style={{ background: "var(--color-bg)" }}
    >
      <div className="mx-auto px-6 py-9" style={{ maxWidth: 1280 }}>
        <PageHeader
          totals={totals}
          q={q}
          onQ={setQ}
          filter={filter}
          onFilter={setFilter}
        />

        {error && (
          <p
            className="mt-8 text-[14px] italic"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-danger)",
            }}
          >
            Couldn’t load sources: {error}
          </p>
        )}

        {data === null && !error && (
          <p
            className="mt-12 text-[14px] italic"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-ink-faint)",
            }}
          >
            Loading the source catalog…
          </p>
        )}

        {filtered && filtered.length === 0 && data && data.length > 0 && (
          <p
            className="mt-12 text-[14px] italic"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-ink-faint)",
            }}
          >
            Nothing matches that filter.
          </p>
        )}

        {filtered && filtered.length > 0 && (
          <div
            className="mt-10 grid"
            style={{
              gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
              gap: 12,
            }}
          >
            {filtered.map((src) => (
              <SourceTile
                key={src.id}
                source={src}
                onOpen={() => setOpenSourceId(src.id)}
              />
            ))}
          </div>
        )}

        {totals && (
          <div
            className="mt-12 pt-5 flex items-center justify-between flex-wrap gap-4"
            style={{ borderTop: "1px solid var(--color-rule-soft)" }}
          >
            <span
              className="font-mono text-[12px] uppercase tabular-nums"
              style={{
                color: "var(--color-ink-faint)",
                letterSpacing: "0.18em",
              }}
            >
              {totals.connected} of {totals.total} connected
            </span>
            <span
              className="text-[13px]"
              style={{
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
                color: "var(--color-ink-faint)",
              }}
            >
              From <span className="font-mono not-italic">/api/sources</span>
            </span>
          </div>
        )}
      </div>

      <AnimatePresence>
        {openSourceId && (
          <SourceCoralModal
            sourceId={openSourceId}
            onClose={() => setOpenSourceId(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// SourceCoralModal - click-through inspector for a single source.
// Shows the Coral logo (this is the data layer powering the agent's
// SQL access) + the env vars Coral uses (censored) + the qualified
// tables Coral exposes to the agent. Centered modal with backdrop blur.
// ──────────────────────────────────────────────────────────────────────

function SourceCoralModal({
  sourceId,
  onClose,
}: {
  sourceId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<SourceCoralDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSourceCoralDetail(sourceId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  // ESC + body-scroll lock
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const sourceMeta = getSource(sourceId);
  const brandHex = sourceMeta?.simpleIcon?.hex;
  const isExtreme =
    !brandHex ||
    ["000000", "FFFFFF", "FDFDFD", "FEFEFE"].includes(brandHex.toUpperCase());
  const brandTint = isExtreme
    ? "var(--color-rule-soft)"
    : `#${brandHex}14`;
  const brandRing = isExtreme
    ? "var(--color-rule-soft)"
    : `#${brandHex}33`;
  const brandFill = isExtreme ? "var(--color-ink-strong)" : `#${brandHex}`;
  const sourceIconViewBox = sourceMeta?.simpleIcon?.viewBox ?? "0 0 24 24";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
      className="fixed inset-0 z-50 flex items-center justify-center px-6"
      onClick={onClose}
      style={{
        background:
          "color-mix(in oklch, var(--color-bg) 78%, transparent)",
        backdropFilter: "blur(14px) saturate(120%)",
        WebkitBackdropFilter: "blur(14px) saturate(120%)",
      }}
      role="dialog"
      aria-modal="true"
      aria-label={`Coral connection: ${detail?.name ?? sourceId}`}
    >
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.22, ease: [0.22, 0.61, 0.36, 1] }}
        onClick={(e) => e.stopPropagation()}
        className="relative w-full flex flex-col"
        style={{
          background: "var(--color-bg)",
          border: "1px solid var(--color-rule)",
          borderRadius: 16,
          maxWidth: 640,
          maxHeight: "min(86vh, 800px)",
          overflow: "hidden",
          boxShadow:
            "0 30px 80px -20px color-mix(in oklch, var(--color-ink-strong) 35%, transparent)",
        }}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-line)]"
          style={{
            top: 12,
            right: 12,
            width: 32,
            height: 32,
            borderRadius: 999,
            background: "transparent",
            border: "none",
            color: "var(--color-ink-muted)",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1,
          }}
        >
          <X size={16} strokeWidth={1.6} />
        </button>

        {/* Header - Coral × Source crossover */}
        <header
          className="flex items-center gap-5 px-7 pt-7 pb-6"
          style={{ borderBottom: "1px solid var(--color-rule-soft)" }}
        >
          {/* Coral logo on the left - this is what powers the connection */}
          <img
            src="/coral-button.png"
            alt="Coral"
            style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              objectFit: "cover",
              border: "1px solid var(--color-rule)",
            }}
          />
          <span
            className="font-mono text-[14px]"
            style={{ color: "var(--color-ink-ghost)" }}
            aria-hidden
          >
            ×
          </span>
          {/* Source brand glyph on the right */}
          <div
            className="inline-flex items-center justify-center"
            style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              background: brandTint,
              border: `1px solid ${brandRing}`,
            }}
          >
            {sourceMeta?.simpleIcon ? (
              <svg
                width={26}
                height={26}
                viewBox={sourceIconViewBox}
                fill={brandFill}
                aria-hidden
              >
                <path d={sourceMeta.simpleIcon.path} />
              </svg>
            ) : (
              <span style={{ width: 26, height: 26 }} />
            )}
          </div>

          <div className="flex-1 min-w-0 ml-2">
            <div
              className="text-[10.5px] uppercase"
              style={{
                color: "var(--color-ink-faint)",
                letterSpacing: "0.22em",
                fontFamily: "Geist Mono, ui-monospace, monospace",
              }}
            >
              Coral connection
            </div>
            <div
              className="text-[20px] mt-0.5"
              style={{
                fontFamily: "Spectral, serif",
                color: "var(--color-ink-strong)",
                letterSpacing: "-0.012em",
                fontWeight: 500,
              }}
            >
              {detail?.name ?? sourceId}
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-7 py-6">
          {err && (
            <p
              className="text-[13px]"
              style={{
                color: "var(--color-danger)",
                fontFamily: "Geist Mono, ui-monospace, monospace",
              }}
            >
              {err}
            </p>
          )}

          {!detail && !err && (
            <p
              className="text-[13px] italic"
              style={{
                fontFamily: "Spectral, serif",
                color: "var(--color-ink-faint)",
              }}
            >
              Reading the Coral catalog…
            </p>
          )}

          {detail && (
            <div className="flex flex-col gap-8">
              {/* ENV VARS - censored credentials */}
              <section>
                <div
                  className="flex items-center gap-2 mb-3"
                  style={{ color: "var(--color-ink-faint)" }}
                >
                  <Key size={13} strokeWidth={1.6} />
                  <span
                    className="text-[11px] uppercase"
                    style={{
                      letterSpacing: "0.22em",
                      fontFamily: "Geist Mono, ui-monospace, monospace",
                    }}
                  >
                    Credentials
                  </span>
                </div>
                {detail.env_vars.length === 0 ? (
                  <p
                    className="text-[13px] italic"
                    style={{
                      fontFamily: "Spectral, serif",
                      color: "var(--color-ink-faint)",
                    }}
                  >
                    No env vars wired for this source - Coral falls back
                    to the in-process mock catalog.
                  </p>
                ) : (
                  <ul className="flex flex-col gap-3">
                    {detail.env_vars.map((v) => (
                      <li
                        key={v.name}
                        className="grid items-baseline"
                        style={{
                          gridTemplateColumns: "minmax(180px, 240px) minmax(0, 1fr)",
                          columnGap: 16,
                        }}
                      >
                        <span
                          className="font-mono text-[12.5px] tabular-nums truncate"
                          style={{
                            color: "var(--color-ink-muted)",
                            letterSpacing: "0.02em",
                          }}
                        >
                          {v.name}
                        </span>
                        <span
                          className="font-mono text-[12.5px] tabular-nums truncate"
                          style={{
                            color: v.present
                              ? "var(--color-ink-strong)"
                              : "var(--color-ink-faint)",
                            letterSpacing: "0.005em",
                          }}
                          title={
                            v.present
                              ? "Value masked. Stored in api/.env."
                              : "Not configured"
                          }
                        >
                          {v.present ? v.value_preview : "- not set -"}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {/* TABLES - what Coral exposes */}
              <section>
                <div
                  className="flex items-center gap-2 mb-3"
                  style={{ color: "var(--color-ink-faint)" }}
                >
                  <Database size={13} strokeWidth={1.6} />
                  <span
                    className="text-[11px] uppercase"
                    style={{
                      letterSpacing: "0.22em",
                      fontFamily: "Geist Mono, ui-monospace, monospace",
                    }}
                  >
                    Coral tables · {detail.tables.length}
                  </span>
                </div>
                {detail.tables.length === 0 ? (
                  <p
                    className="text-[13px] italic"
                    style={{
                      fontFamily: "Spectral, serif",
                      color: "var(--color-ink-faint)",
                    }}
                  >
                    No tables registered yet.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {detail.tables.map((t) => (
                      <span
                        key={t}
                        className="inline-flex items-center font-mono text-[12px] tabular-nums"
                        style={{
                          padding: "5px 10px",
                          borderRadius: 6,
                          background: "var(--color-surface)",
                          border: "1px solid var(--color-rule)",
                          color: "var(--color-ink-strong)",
                          letterSpacing: "0.01em",
                        }}
                        title={`SELECT * FROM ${t} LIMIT …`}
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </section>

              {/* Coral metadata footer */}
              <section
                className="pt-5"
                style={{
                  borderTop: "1px solid var(--color-rule-soft)",
                }}
              >
                <div
                  className="grid"
                  style={{
                    gridTemplateColumns: "minmax(180px, 240px) minmax(0, 1fr)",
                    columnGap: 16,
                    rowGap: 8,
                  }}
                >
                  <span
                    className="font-mono text-[11px] uppercase"
                    style={{
                      color: "var(--color-ink-faint)",
                      letterSpacing: "0.18em",
                    }}
                  >
                    Transport
                  </span>
                  <span
                    className="font-mono text-[12.5px]"
                    style={{ color: "var(--color-ink-muted)" }}
                  >
                    {detail.coral.transport}
                  </span>

                  <span
                    className="font-mono text-[11px] uppercase"
                    style={{
                      color: "var(--color-ink-faint)",
                      letterSpacing: "0.18em",
                    }}
                  >
                    Binary
                  </span>
                  <span
                    className="font-mono text-[12.5px]"
                    style={{ color: "var(--color-ink-muted)" }}
                  >
                    {detail.coral.binary}
                  </span>

                  <span
                    className="font-mono text-[11px] uppercase"
                    style={{
                      color: "var(--color-ink-faint)",
                      letterSpacing: "0.18em",
                    }}
                  >
                    MCP tools
                  </span>
                  <span
                    className="font-mono text-[12.5px]"
                    style={{ color: "var(--color-ink-muted)" }}
                  >
                    {detail.coral.tools.join(" · ")}
                  </span>
                </div>
              </section>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// PageHeader - title + subtitle + search + filter.
// ──────────────────────────────────────────────────────────────────────

function PageHeader({
  totals,
  q,
  onQ,
  filter,
  onFilter,
}: {
  totals: { connected: number; available: number; total: number } | null;
  q: string;
  onQ: (v: string) => void;
  filter: "all" | "connected" | "available";
  onFilter: (v: "all" | "connected" | "available") => void;
}) {
  return (
    <header className="flex flex-col gap-5">
      <Eyebrow>Sources</Eyebrow>
      <h1
        className="leading-[1.05]"
        style={{
          fontFamily: "Spectral, serif",
          fontSize: "clamp(34px, 3.4vw, 42px)",
          color: "var(--color-ink-strong)",
          letterSpacing: "-0.014em",
          fontStyle: "italic",
        }}
      >
        What Manthan can see.
      </h1>
      <p
        className="leading-[1.55]"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: 15,
          color: "var(--color-ink-muted)",
          maxWidth: "62ch",
          letterSpacing: "-0.003em",
        }}
      >
        {totals ? (
          <>
            {totals.total} sources ·{" "}
            <span style={{ color: "var(--color-accent)" }}>
              {totals.connected} connected
            </span>
            . Each tile pulls live evidence into the agent when a case
            crosses the trigger.
          </>
        ) : (
          "Loading the catalog…"
        )}
      </p>

      <div className="flex items-center gap-5 flex-wrap mt-1">
        <div
          className="inline-flex items-center px-3 py-2"
          style={{
            background: "var(--color-surface-2)",
            border: "1px solid var(--color-rule)",
            borderRadius: 4,
            minWidth: 280,
          }}
        >
          <span
            className="text-[10.5px] tabular-nums shrink-0 mr-3"
            style={{
              fontFamily: "Geist Mono, ui-monospace, monospace",
              color: "var(--color-ink-faint)",
              letterSpacing: "0.18em",
            }}
          >
            SEARCH
          </span>
          <input
            value={q}
            onChange={(e) => onQ(e.target.value)}
            placeholder="Stripe, Notion, Datadog…"
            className="flex-1 bg-transparent text-[13.5px] outline-none min-w-0"
            style={{
              color: "var(--color-ink-strong)",
              fontFamily: "Spectral, serif",
            }}
          />
        </div>
        <div className="inline-flex items-baseline gap-4">
          {(["all", "connected", "available"] as const).map((f) => (
            <button
              key={f}
              onClick={() => onFilter(f)}
              type="button"
              className="text-[11.5px] uppercase outline-none transition-colors bg-transparent border-0 p-0"
              style={{
                letterSpacing: "0.20em",
                color:
                  filter === f
                    ? "var(--color-ink-strong)"
                    : "var(--color-ink-faint)",
                fontWeight: filter === f ? 500 : 400,
                cursor: "pointer",
              }}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// SourceTile - one box per source. Logo dominates, brand-tinted wash
// behind, name + category + status pill below.
// ──────────────────────────────────────────────────────────────────────

function SourceTile({ source, onOpen }: { source: ApiSource; onOpen: () => void }) {
  const meta = getSource(source.id);
  const brandHex = meta?.simpleIcon?.hex;
  // Pure-black brands (Notion, GitHub) and pure-white brands (Resend)
  // get rendered with our ink tokens by SourceIcon - but for the
  // background wash they read flat. Detect and swap to a neutral tint.
  const isExtremeBrand =
    !brandHex ||
    ["000000", "FFFFFF", "FDFDFD", "FEFEFE"].includes(
      brandHex.toUpperCase(),
    );
  const tint = isExtremeBrand
    ? "var(--color-rule-soft)"
    : `#${brandHex}14`; // 0x14 ≈ 8% alpha
  const ring = isExtremeBrand
    ? "var(--color-rule-soft)"
    : `#${brandHex}28`;

  const category =
    CATEGORY_LABELS[source.category] ?? source.category;

  const isConnected = source.status === "connected";
  const needsAttention = source.status === "needs_attention";

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className="source-tile group flex flex-col outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-line)]"
      style={{
        background: "var(--color-bg)",
        border: "1px solid var(--color-rule)",
        borderRadius: 8,
        overflow: "hidden",
        transition: "transform 200ms ease, border-color 200ms ease",
        cursor: "pointer",
        opacity: isConnected ? 1 : 0.78,
      }}
    >
      {/* Top - brand wash with the huge logo */}
      <div
        className="relative flex items-center justify-center"
        style={{
          height: 132,
          background: tint,
          borderBottom: `1px solid ${ring}`,
        }}
      >
        <BrandGlyph source={source} />

        {/* Status pill - top-right */}
        <span
          className="absolute text-[10px] uppercase font-mono tabular-nums"
          style={{
            top: 10,
            right: 10,
            letterSpacing: "0.18em",
            color: isConnected
              ? "var(--color-accent)"
              : needsAttention
                ? "var(--color-amber)"
                : "var(--color-ink-faint)",
          }}
        >
          {isConnected ? "live" : needsAttention ? "attention" : "available"}
        </span>
      </div>

      {/* Bottom - name + category + activity */}
      <div className="flex flex-col gap-1.5 px-4 pt-3 pb-4">
        <div className="flex items-baseline justify-between gap-2">
          <span
            className="text-[15px]"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-ink-strong)",
              letterSpacing: "-0.005em",
              fontWeight: 500,
            }}
          >
            {source.name}
          </span>
          <span
            className="text-[10.5px] uppercase font-mono tabular-nums shrink-0"
            style={{
              color: "var(--color-ink-faint)",
              letterSpacing: "0.18em",
            }}
          >
            {category}
          </span>
        </div>

        {isConnected && source.queries_total > 0 && (
          <div className="flex items-baseline justify-end gap-2 mt-0.5">
            <span
              className="font-mono text-[11px] tabular-nums shrink-0"
              style={{
                color: "var(--color-ink-muted)",
                letterSpacing: "0.04em",
              }}
              title={`${source.queries_total.toLocaleString()} queries · last ${source.last_query_at ? formatAge(source.last_query_at) + " ago" : "-"}`}
            >
              {compactNum(source.queries_total)}q
            </span>
          </div>
        )}
      </div>

      <style>{`
        .source-tile:hover {
          transform: translateY(-2px);
          border-color: var(--color-rule-strong) !important;
        }
      `}</style>
    </article>
  );
}

/**
 * BrandGlyph - the source logo, rendered LARGE and in its brand color.
 * Uses the simple-icons SVG path directly so we can size it ourselves;
 * the smaller SourceIcon component is for inline use and tops out at
 * 24px. Pure-black / pure-white brands render with the ink token so
 * they don't disappear on dark.
 */
function BrandGlyph({ source }: { source: ApiSource }) {
  const meta = getSource(source.id);
  const icon = meta?.simpleIcon;
  if (!icon) {
    // No SVG - show a stylized initial in mono with the source's id.
    return (
      <span
        className="inline-flex items-center justify-center font-mono tabular-nums"
        style={{
          width: 64,
          height: 64,
          borderRadius: 8,
          background: "var(--color-rule-soft)",
          border: "1px solid var(--color-rule)",
          color: "var(--color-ink)",
          fontSize: 20,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        {source.name.slice(0, 2)}
      </span>
    );
  }
  const EXTREME = new Set([
    "000000",
    "FFFFFF",
    "FDFDFD",
    "FEFEFE",
  ]);
  const fill = EXTREME.has(icon.hex.toUpperCase())
    ? "var(--color-ink-strong)"
    : `#${icon.hex}`;
  const viewBox = icon.viewBox ?? "0 0 24 24";
  return (
    <svg
      width={56}
      height={56}
      viewBox={viewBox}
      fill={fill}
      style={{
        filter: `drop-shadow(0 6px 18px ${fill}22)`,
      }}
      aria-label={`${source.name} logo`}
    >
      <path d={icon.path} />
    </svg>
  );
}


function compactNum(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return n.toString();
}

function formatAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span
      className="text-[12.5px] uppercase"
      style={{
        color: "var(--color-ink-muted)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}
