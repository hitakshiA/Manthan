/**
 * Atomic styling helpers for the case workspace.
 * Mirrors the helpers in HeroShowcase so visual treatment stays consistent.
 */

import type { ReactNode, CSSProperties } from "react";
import { Check } from "lucide-react";
import type { CaseStatus, Tone } from "./types";

export function Money({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        color: "var(--color-ink-strong)",
        fontVariantNumeric: "tabular-nums",
        fontWeight: 600,
      }}
    >
      {children}
    </span>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return (
    <span
      className="font-mono"
      style={{ color: "var(--color-ink-strong)", fontSize: "0.94em" }}
    >
      {children}
    </span>
  );
}

export function Strong({
  children,
  className,
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      className={className}
      style={{
        color: "var(--color-ink-strong)",
        fontWeight: 600,
        fontVariantNumeric: "tabular-nums",
        ...style,
      }}
    >
      {children}
    </span>
  );
}

export function Muted({ children }: { children: ReactNode }) {
  return <span style={{ color: "var(--color-ink-faint)" }}>{children}</span>;
}

export function Italic({ children }: { children: ReactNode }) {
  return (
    <em className="display-italic" style={{ color: "var(--color-ink-strong)" }}>
      {children}
    </em>
  );
}

export function Amber({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        color: "var(--color-amber)",
        fontVariantNumeric: "tabular-nums",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="eyebrow">{children}</div>;
}

export function Rule() {
  return (
    <div
      className="rule"
      style={{ height: 1, background: "var(--color-rule-soft)" }}
    />
  );
}

export function Ref({ n }: { n: number }) {
  return (
    <sup className="ref" style={{ color: "var(--color-accent)" }}>
      [{n}]
    </sup>
  );
}

export function StatusBadge({ status }: { status: CaseStatus }) {
  if (status === "approved") {
    return (
      <div
        className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase"
        style={{
          color: "var(--color-accent)",
          letterSpacing: "0.09em",
          fontWeight: 600,
        }}
      >
        <Check className="h-3 w-3" strokeWidth={3} />
        Resolved
      </div>
    );
  }
  if (status === "approving") {
    return (
      <div
        className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase"
        style={{
          color: "var(--color-accent)",
          letterSpacing: "0.09em",
          fontWeight: 600,
        }}
      >
        <span
          className="h-1.5 w-1.5 rounded-full animate-pulse-dot"
          style={{ background: "var(--color-accent)" }}
        />
        Approving
      </div>
    );
  }
  if (status === "held") {
    return (
      <div
        className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase"
        style={{
          color: "var(--color-ink-muted)",
          letterSpacing: "0.09em",
          fontWeight: 600,
        }}
      >
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: "var(--color-ink-muted)" }}
        />
        On hold
      </div>
    );
  }
  return (
    <div
      className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase"
      style={{
        color: "var(--color-amber)",
        letterSpacing: "0.09em",
        fontWeight: 600,
      }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full animate-pulse-dot"
        style={{ background: "var(--color-amber)" }}
      />
      Awaiting nod
    </div>
  );
}

export function StatusDot({ tone, subtle }: { tone: Tone; subtle?: boolean }) {
  const palette: Record<Tone, { color: string; label: string; pulse?: boolean }> = {
    awaiting:      { color: "var(--color-amber)",  label: "awaiting",      pulse: true },
    drafted:       { color: "var(--color-info)",   label: "drafted" },
    investigating: { color: "var(--color-info)",   label: "investigating" },
    executing:     { color: "var(--color-accent)", label: "executing",     pulse: true },
    resolved:      { color: "var(--color-accent)", label: "resolved" },
  };
  const p = palette[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 ${
        subtle ? "text-[10px]" : "text-[10.5px]"
      } uppercase`}
      style={{
        color: subtle ? "var(--color-ink-faint)" : p.color,
        letterSpacing: "0.09em",
        fontWeight: 600,
      }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${p.pulse ? "animate-pulse-dot" : ""}`}
        style={{ background: p.color }}
      />
      {p.label}
    </span>
  );
}
