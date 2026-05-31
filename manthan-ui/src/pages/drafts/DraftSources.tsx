/**
 * DraftSources - Connected Sources, editorial-memo direction (DRAFT).
 *
 * Each connected source is a MINI-PROFILE memo, stacked. Mirrors the
 * Case Workspace memo vocabulary (HeaderStrip, Eyebrow, SourceWord),
 * but the unit of content is a source, not a case.
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ ⬡ STRIPE   payments              healthy · sync 3 min ago    │
 *   │ ──────────────────────────────────────────────────────────── │
 *   │ What Manthan can do here    │ Recent activity                │
 *   │ Reads: charges, disputes…   │ 3m  · brief drafted on W7R     │
 *   │ Writes: refunds, dispute…   │ 17m · refund of $560 fired     │
 *   │ ─────────────────────────   │ 4h  · case opened W7R          │
 *   │ 4 caps · OAuth · scoped     │                                │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * No glow, no gradients, no glassmorphism. Hairlines + Spectral italic
 * + Geist Mono tabular. The reference is print, not Discord.
 *
 * Throwaway draft - route /app/drafts/sources.
 */

import type { ReactNode } from "react";
import { SourceIcon } from "@/components/ui/SourceIcon";

// ──────────────────────────────────────────────────────────────────────
// Mock data - six connected sources, written to feel like a real stack.
// ──────────────────────────────────────────────────────────────────────

type Health = "healthy" | "degraded" | "down";

interface ActivityEntry {
  /** Time-ago label, mono tabular. */
  age: string;
  /** The verb - muted; reads as the action class. */
  verb: string;
  /** The object - normal weight; reads as the specific subject. */
  object: ReactNode;
}

interface SourceProfile {
  id: string;
  name: string;
  category: string;
  health: Health;
  lastSync: string;
  reads: string[];
  /** Empty array → read-only source; the Writes row is suppressed. */
  writes: string[];
  capCount: number;
  /** "OAuth" or "API key". */
  authMethod: "OAuth" | "API key";
  /** "scoped" or "read-only" - appears after the auth method. */
  scopeNote: "scoped" | "read-only";
  activity: ActivityEntry[];
}

const SOURCES: SourceProfile[] = [
  {
    id: "stripe",
    name: "Stripe",
    category: "payments",
    health: "healthy",
    lastSync: "3 min ago",
    reads: ["charges", "disputes", "customers", "subscriptions"],
    writes: ["refunds", "dispute responses"],
    capCount: 4,
    authMethod: "OAuth",
    scopeNote: "scoped",
    activity: [
      {
        age: "3m",
        verb: "brief drafted on",
        object: <Mono>CASE W7R-APERTURE</Mono>,
      },
      {
        age: "17m",
        verb: "refund fired",
        object: (
          <>
            of <Mono>$560.00</Mono> · charge <Mono>ch_3Tch1L</Mono>
          </>
        ),
      },
      {
        age: "4h",
        verb: "case opened",
        object: <Mono>W7R-APERTURE</Mono>,
      },
    ],
  },
  {
    id: "hubspot",
    name: "HubSpot",
    category: "crm",
    health: "healthy",
    lastSync: "5 min ago",
    reads: ["companies", "contacts", "lifecycle"],
    writes: ["notes", "lifecycle property updates"],
    capCount: 3,
    authMethod: "OAuth",
    scopeNote: "scoped",
    activity: [
      {
        age: "5m",
        verb: "note appended on",
        object: "Aperture Analytics",
      },
      {
        age: "12m",
        verb: "fetched company",
        object: <Mono>324974146247</Mono>,
      },
      {
        age: "1h",
        verb: "fetched contact",
        object: "billing@aperture-analytics.co",
      },
    ],
  },
  {
    id: "intercom",
    name: "Intercom",
    category: "support",
    health: "healthy",
    lastSync: "8 min ago",
    reads: ["conversations", "contacts"],
    writes: [],
    capCount: 2,
    authMethod: "OAuth",
    scopeNote: "read-only",
    activity: [
      {
        age: "8m",
        verb: "fetched conversation",
        object: <Mono>conv/3708443460</Mono>,
      },
      {
        age: "23m",
        verb: "fetched contact",
        object: "Maya Brennan",
      },
      {
        age: "2h",
        verb: "scanned messages",
        object: <>across Aperture's inbox</>,
      },
    ],
  },
  {
    id: "notion",
    name: "Notion",
    category: "policy docs",
    health: "healthy",
    lastSync: "14 min ago",
    reads: ["pages", "databases"],
    writes: ["append blocks to ops pages"],
    capCount: 2,
    authMethod: "API key",
    scopeNote: "scoped",
    activity: [
      {
        age: "14m",
        verb: "read policy",
        object: (
          <em
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              color: "rgba(255,255,255,0.86)",
            }}
          >
            “Documented Incident Pro-Rata Credit”
          </em>
        ),
      },
      {
        age: "47m",
        verb: "read SOP",
        object: (
          <em
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              color: "rgba(255,255,255,0.86)",
            }}
          >
            “Refund Authority Matrix”
          </em>
        ),
      },
      {
        age: "5h",
        verb: "appended decision log on",
        object: <Mono>page/37043656</Mono>,
      },
    ],
  },
  {
    id: "datadog",
    name: "Datadog",
    category: "observability",
    health: "healthy",
    lastSync: "2 min ago",
    reads: ["monitors", "events"],
    writes: [],
    capCount: 2,
    authMethod: "API key",
    scopeNote: "read-only",
    activity: [
      {
        age: "2m",
        verb: "read monitor",
        object: (
          <Mono>custom-reports-svc.error_rate</Mono>
        ),
      },
      {
        age: "21m",
        verb: "read event",
        object: <Mono>id/20175237</Mono>,
      },
      {
        age: "3h",
        verb: "read incident",
        object: (
          <em
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              color: "rgba(255,255,255,0.86)",
            }}
          >
            “Premium SLA breach 04-13 → 04-15”
          </em>
        ),
      },
    ],
  },
  {
    id: "posthog",
    name: "PostHog",
    category: "product analytics",
    health: "degraded",
    lastSync: "26 min ago",
    reads: ["events"],
    writes: [],
    capCount: 1,
    authMethod: "API key",
    scopeNote: "read-only",
    activity: [
      {
        age: "26m",
        verb: "fetched events",
        object: (
          <span style={{ color: "rgba(255,255,255,0.55)" }}>
            ·{" "}
            <em
              style={{
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
                color: "rgba(255,182,77,0.82)",
              }}
            >
              slow - 14.2s
            </em>
          </span>
        ),
      },
      {
        age: "1h",
        verb: "fetched events",
        object: (
          <span style={{ color: "rgba(255,255,255,0.55)" }}>
            ·{" "}
            <em
              style={{
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
                color: "rgba(255,182,77,0.82)",
              }}
            >
              slow - 9.4s
            </em>
          </span>
        ),
      },
      {
        age: "4h",
        verb: "fetched events",
        object: "for cohort=nwl",
      },
    ],
  },
];

// ──────────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────────

export default function DraftSources() {
  const healthyCount = SOURCES.filter((s) => s.health === "healthy").length;
  const degradedCount = SOURCES.filter((s) => s.health === "degraded").length;
  const downCount = SOURCES.filter((s) => s.health === "down").length;

  return (
    <div
      className="h-full w-full overflow-y-auto"
      style={{ background: "var(--color-bg)" }}
    >
      <div className="mx-auto px-6 py-9" style={{ maxWidth: 1280 }}>
        {/* ─────────────────────────────────────────────────────────
            Page header - eyebrow + Spectral italic title + subtitle.
            Hairline below, matched to the source-card top edge below.
            ───────────────────────────────────────────────────────── */}
        <header className="mb-9">
          <Eyebrow>Sources</Eyebrow>
          <h1
            className="mt-3 leading-[1.05]"
            style={{
              fontFamily: "Spectral, serif",
              fontSize: "clamp(34px, 3.4vw, 42px)",
              color: "rgba(255,255,255,0.96)",
              letterSpacing: "-0.014em",
            }}
          >
            What Manthan can see.
          </h1>
          <p
            className="mt-3 leading-[1.55]"
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              fontSize: 15,
              color: "rgba(255,255,255,0.58)",
              maxWidth: "62ch",
              letterSpacing: "-0.003em",
            }}
          >
            Six sources ·{" "}
            <span style={{ color: "var(--color-accent, #56cf83)" }}>
              {healthyCount} healthy
            </span>
            {degradedCount > 0 && (
              <>
                , <span style={{ color: "rgba(255,182,77,0.92)" }}>{degradedCount} degraded</span>
              </>
            )}
            {downCount > 0 && (
              <>
                , <span style={{ color: "rgba(255,107,107,0.92)" }}>{downCount} down</span>
              </>
            )}
            . Click a source to see capabilities and scopes.
          </p>
        </header>

        {/* ─────────────────────────────────────────────────────────
            Stack of source-profile cards. Each is a self-contained
            memo with its own HeaderStrip and two-column canvas.
            ───────────────────────────────────────────────────────── */}
        <div className="flex flex-col gap-5">
          {SOURCES.map((src) => (
            <SourceProfileCard key={src.id} source={src} />
          ))}
        </div>

        {/* Footer breath - small mono index line in the editorial style. */}
        <div
          className="mt-10 pt-5 flex items-center justify-between"
          style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
        >
          <span
            className="font-mono text-[12px] uppercase tabular-nums"
            style={{
              color: "rgba(255,255,255,0.36)",
              letterSpacing: "0.18em",
            }}
          >
            6 of 27 available · connect more from{" "}
            <span style={{ color: "rgba(255,255,255,0.58)" }}>
              Settings → Catalog
            </span>
          </span>
          <span
            className="text-[13px]"
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              color: "rgba(255,255,255,0.48)",
            }}
          >
            Last catalog sync · 2026-05-30 09:14 UTC
          </span>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// SourceProfileCard - one source memo. HeaderStrip + two-column canvas.
// ──────────────────────────────────────────────────────────────────────

function SourceProfileCard({ source }: { source: SourceProfile }) {
  return (
    <article
      style={{
        background: "oklch(0.135 0.006 75)",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 6,
        color: "rgba(255,255,255,0.92)",
        overflow: "hidden",
        boxShadow: "0 16px 40px rgba(0,0,0,0.30)",
      }}
    >
      <SourceHeaderStrip source={source} />
      <SourceCanvas source={source} />
    </article>
  );
}

// ──────────────────────────────────────────────────────────────────────
// SourceHeaderStrip - identity strip. Icon · NAME · italic category,
// right side: health word + "·" + sync stamp.
// ──────────────────────────────────────────────────────────────────────

function SourceHeaderStrip({ source }: { source: SourceProfile }) {
  const healthColor =
    source.health === "healthy"
      ? "var(--color-accent, #56cf83)"
      : source.health === "degraded"
      ? "rgba(255,182,77,0.92)"
      : "rgba(255,107,107,0.92)";

  return (
    <header
      className="flex items-center px-9 shrink-0"
      style={{
        height: 56,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        background: "oklch(0.135 0.006 75)",
      }}
    >
      {/* Source icon - 24px tinted glyph, baseline-aligned with mono. */}
      <span
        aria-hidden
        className="inline-flex items-center justify-center mr-4"
        style={{ width: 24, height: 24 }}
      >
        <SourceIcon id={source.id} size={24} tinted />
      </span>

      {/* Name - big mono uppercase, the editorial "byline." */}
      <span
        className="font-mono text-[16px] uppercase tabular-nums"
        style={{
          color: "rgba(255,255,255,0.92)",
          letterSpacing: "0.16em",
          fontWeight: 500,
        }}
      >
        {source.name}
      </span>

      <span
        className="mx-4"
        style={{ color: "rgba(255,255,255,0.20)" }}
        aria-hidden
      >
        ·
      </span>

      {/* Category - Spectral italic, the editorial "section." */}
      <span
        className="text-[14px]"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          color: "rgba(255,255,255,0.58)",
          letterSpacing: "-0.003em",
        }}
      >
        {source.category}
      </span>

      {/* Right side - health (color on text) · sync stamp (mono muted). */}
      <div className="ml-auto inline-flex items-baseline gap-3">
        <span
          className="text-[12.5px] uppercase"
          style={{
            color: healthColor,
            letterSpacing: "0.22em",
            fontWeight: 500,
          }}
        >
          {source.health}
        </span>
        <span
          style={{ color: "rgba(255,255,255,0.20)" }}
          aria-hidden
        >
          ·
        </span>
        <span
          className="font-mono text-[12px] tabular-nums"
          style={{
            color: "rgba(255,255,255,0.50)",
            letterSpacing: "0.04em",
          }}
        >
          last sync {source.lastSync}
        </span>
      </div>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// SourceCanvas - left (capabilities) | right (recent activity).
// ──────────────────────────────────────────────────────────────────────

function SourceCanvas({ source }: { source: SourceProfile }) {
  return (
    <div
      className="grid"
      style={{
        gridTemplateColumns: "minmax(0, 1.3fr) minmax(0, 1fr)",
      }}
    >
      {/* LEFT - what Manthan can do here */}
      <div className="px-9 pt-7 pb-7 flex flex-col gap-5">
        <Eyebrow>What Manthan can do here</Eyebrow>

        <div className="flex flex-col gap-3">
          {/* Reads row */}
          <div className="flex items-baseline gap-3">
            <span
              className="text-[12.5px] tabular-nums shrink-0"
              style={{
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
                color: "rgba(255,255,255,0.42)",
                letterSpacing: "0.04em",
                width: 50,
              }}
            >
              Reads
            </span>
            <p
              className="text-[15px] leading-[1.55]"
              style={{ color: "rgba(255,255,255,0.88)" }}
            >
              {source.reads.map((r, i) => (
                <span key={r}>
                  <span
                    className="font-mono text-[13.5px]"
                    style={{
                      color: "rgba(255,255,255,0.85)",
                      letterSpacing: "0.01em",
                    }}
                  >
                    {r}
                  </span>
                  {i < source.reads.length - 1 && (
                    <span style={{ color: "rgba(255,255,255,0.32)" }}>
                      , {" "}
                    </span>
                  )}
                </span>
              ))}
            </p>
          </div>

          {/* Writes row - suppressed entirely for read-only sources. */}
          {source.writes.length > 0 && (
            <div className="flex items-baseline gap-3">
              <span
                className="text-[12.5px] tabular-nums shrink-0"
                style={{
                  fontFamily: "Spectral, serif",
                  fontStyle: "italic",
                  color: "rgba(255,255,255,0.42)",
                  letterSpacing: "0.04em",
                  width: 50,
                }}
              >
                Writes
              </span>
              <p
                className="text-[15px] leading-[1.55]"
                style={{ color: "rgba(255,255,255,0.88)" }}
              >
                {source.writes.map((w, i) => (
                  <span key={w}>
                    <span
                      className="font-mono text-[13.5px]"
                      style={{
                        color: "rgba(255,255,255,0.85)",
                        letterSpacing: "0.01em",
                      }}
                    >
                      {w}
                    </span>
                    {i < source.writes.length - 1 && (
                      <span style={{ color: "rgba(255,255,255,0.32)" }}>
                        , {" "}
                      </span>
                    )}
                  </span>
                ))}
              </p>
            </div>
          )}
        </div>

        {/* Capabilities meta - hairline above, mono muted line. */}
        <div
          className="pt-4 mt-1"
          style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
        >
          <span
            className="font-mono text-[12.5px] tabular-nums"
            style={{
              color: "rgba(255,255,255,0.48)",
              letterSpacing: "0.04em",
            }}
          >
            {source.capCount} {source.capCount === 1 ? "capability" : "capabilities"}
            <Sep />
            {source.authMethod}
            <Sep />
            {source.scopeNote}
          </span>
        </div>
      </div>

      {/* RIGHT - recent activity */}
      <div
        className="px-9 pt-7 pb-7 flex flex-col gap-5"
        style={{ borderLeft: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Eyebrow>Recent activity</Eyebrow>

        <ol className="flex flex-col gap-3.5">
          {source.activity.map((e, i) => (
            <li
              key={i}
              className="flex items-baseline gap-3"
              style={{
                color: "rgba(255,255,255,0.88)",
              }}
            >
              <span
                className="font-mono text-[12px] tabular-nums shrink-0"
                style={{
                  color: "rgba(255,255,255,0.42)",
                  letterSpacing: "0.04em",
                  minWidth: 32,
                  textAlign: "right",
                }}
              >
                {e.age}
              </span>
              <span style={{ color: "rgba(255,255,255,0.22)" }} aria-hidden>
                ·
              </span>
              <p
                className="text-[13.5px] leading-[1.5]"
                style={{ color: "rgba(255,255,255,0.86)" }}
              >
                <span style={{ color: "rgba(255,255,255,0.55)" }}>
                  {e.verb}
                </span>{" "}
                <span style={{ color: "rgba(255,255,255,0.88)" }}>
                  {e.object}
                </span>
              </p>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Editorial primitives - Eyebrow + inline Mono helper.
// Mirrors the WorkspaceMemo / LandingHeroDemo primitives.
// ──────────────────────────────────────────────────────────────────────

function Eyebrow({
  children,
  accent,
}: {
  children: ReactNode;
  accent?: boolean;
}) {
  return (
    <span
      className="text-[12.5px] uppercase"
      style={{
        color: accent
          ? "var(--color-accent, #56cf83)"
          : "rgba(255,255,255,0.50)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}

/** Inline mono span - used to wrap ids, amounts, codes in activity lines. */
function Mono({ children }: { children: ReactNode }) {
  return (
    <span
      className="font-mono tabular-nums"
      style={{
        color: "rgba(255,255,255,0.86)",
        fontSize: 12.5,
        letterSpacing: "0.02em",
      }}
    >
      {children}
    </span>
  );
}

/** Small middle-dot separator for the mono meta line. */
function Sep() {
  return (
    <span
      className="mx-2.5"
      style={{ color: "rgba(255,255,255,0.22)" }}
      aria-hidden
    >
      ·
    </span>
  );
}
