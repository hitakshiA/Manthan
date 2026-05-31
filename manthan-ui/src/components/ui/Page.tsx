/**
 * Page primitives - unify every dashboard route's header, section headers,
 * and load/empty states so we stop reinventing them per page.
 *
 * Editorial direction: hairline rules over card chrome. The `PageHeader`
 * sits on a single bottom hairline, not in a card. Sections use small-caps
 * eyebrows aligned to the same rule grid.
 */

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/cn";

// ──────────────────────────────────────────────────────────────────────
// PageHeader - title, optional sublabel and meta line, optional actions.
// Lives on a bottom hairline (no card). Replaces the per-page <motion.header>
// + <h1> + <p> dance.
// ──────────────────────────────────────────────────────────────────────

export function PageHeader({
  eyebrow,
  title,
  meta,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <motion.header
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="flex items-end justify-between gap-6 pb-5 border-b"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <div className="min-w-0">
        {eyebrow && (
          <div className="eyebrow mb-2" style={{ color: "var(--color-ink-faint)" }}>
            {eyebrow}
          </div>
        )}
        <h1
          className="font-display text-[clamp(1.85rem,1.5rem+1vw,2.6rem)] leading-[1.05] tracking-[-0.012em]"
          style={{ color: "var(--color-ink-strong)" }}
        >
          {title}
        </h1>
        {meta && (
          <div
            className="mt-2 text-[12.5px] leading-relaxed max-w-prose"
            style={{ color: "var(--color-ink-muted)" }}
          >
            {meta}
          </div>
        )}
      </div>
      {actions && <div className="shrink-0 flex items-center gap-2">{actions}</div>}
    </motion.header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// PageBody - consistent outer padding + max-width + vertical rhythm.
// Use this as the root wrapper for every page in /app/*.
// ──────────────────────────────────────────────────────────────────────

export function PageBody({
  children,
  className,
  width = "default",
}: {
  children: ReactNode;
  className?: string;
  width?: "default" | "narrow" | "wide" | "full";
}) {
  const widthClass =
    width === "narrow"
      ? "max-w-3xl"
      : width === "wide"
        ? "max-w-6xl"
        : width === "full"
          ? "max-w-none"
          : "max-w-5xl";
  return (
    <div
      className={cn("mx-auto px-6 md:px-8 py-7 md:py-9 space-y-7", widthClass, className)}
    >
      {children}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Section - eyebrow + content. Replaces the inline "uppercase tracking
// text-white/45" pattern that was being copy-pasted across pages.
// ──────────────────────────────────────────────────────────────────────

export function Section({
  eyebrow,
  trailing,
  children,
  className,
}: {
  eyebrow?: ReactNode;
  trailing?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-3", className)}>
      {(eyebrow || trailing) && (
        <div className="flex items-baseline justify-between">
          {eyebrow && (
            <div className="eyebrow" style={{ color: "var(--color-ink-faint)" }}>
              {eyebrow}
            </div>
          )}
          {trailing && (
            <div className="text-[11.5px]" style={{ color: "var(--color-ink-ghost)" }}>
              {trailing}
            </div>
          )}
        </div>
      )}
      {children}
    </section>
  );
}

// ──────────────────────────────────────────────────────────────────────
// LoadingRow - inline "…" loader. No spinning circle, no whole-page lock.
// Reads as text, doesn't shout.
// ──────────────────────────────────────────────────────────────────────

export function LoadingRow({
  label = "Loading",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "py-3 text-[12.5px] tracking-[0.02em]",
        className,
      )}
      style={{ color: "var(--color-ink-faint)" }}
    >
      {label}
      <span className="animate-pulse-dot inline-block ml-[2px]">…</span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// EmptyRow - hairline-bordered empty state with a single line of useful
// copy. Replaces the "Inbox zero. Manthan is idle." card pattern.
// ──────────────────────────────────────────────────────────────────────

export function EmptyRow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "py-10 text-center text-[12.5px] italic font-display",
        className,
      )}
      style={{ color: "var(--color-ink-muted)" }}
    >
      {children}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// ErrorRow - same shape as LoadingRow but in danger tone.
// ──────────────────────────────────────────────────────────────────────

export function ErrorRow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn("py-3 text-[12.5px]", className)}
      style={{ color: "var(--color-danger)" }}
    >
      {children}
    </div>
  );
}
