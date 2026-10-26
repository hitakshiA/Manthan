/**
 * MarketingShell - minimal nav + footer wrapper for marketing pages
 * other than the landing page (Changelog, Contact, Privacy, Terms, DPA).
 *
 * Same brand voice as the landing - pure black, Geist + Instrument Serif,
 * single Sign in pill in the nav, quiet footer with brand + legal links.
 */

import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { motion } from "motion/react";
import { Logo } from "@/components/Logo";

interface MarketingShellProps {
  eyebrow?: string;
  title: ReactNode;
  intro?: ReactNode;
  lastUpdated?: string;
  children: ReactNode;
}

export function MarketingShell({
  eyebrow,
  title,
  intro,
  lastUpdated,
  children,
}: MarketingShellProps) {
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: "#000", color: "oklch(0.95 0.004 75)" }}
    >
      {/* ── Nav ─────────────────────────────────────────────────────────── */}
      <nav className="relative z-30 px-6 md:px-12 lg:px-20 py-5 flex items-center justify-between">
        <Link
          to="/"
          className="flex items-center gap-2.5 hover:opacity-90 transition-opacity"
        >
          <Logo size={26} showWordmark={false} className="text-white" />
          <span className="text-lg font-semibold tracking-tight text-white">
            Manthan
          </span>
        </Link>
        <Link to="/login">
          <button
            className="rounded-lg text-sm font-semibold px-4 py-2 hover:opacity-90 transition-opacity"
            style={{ background: "#fff", color: "#000" }}
          >
            Sign in
          </button>
        </Link>
      </nav>

      {/* ── Content ─────────────────────────────────────────────────────── */}
      <main className="flex-1 w-full px-6 md:px-12 lg:px-20 pt-12 md:pt-20 pb-24 md:pb-32">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.25, 1, 0.5, 1] }}
          className="max-w-3xl mx-auto"
        >
          {eyebrow && (
            <div
              style={{
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 11,
                color: "oklch(0.55 0.006 75)",
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                marginBottom: 16,
              }}
            >
              {eyebrow}
            </div>
          )}

          <h1
            className="text-4xl md:text-5xl tracking-[-0.025em] font-medium leading-[1.05]"
            style={{ color: "oklch(0.98 0.003 75)" }}
          >
            {title}
          </h1>

          {intro && (
            <p
              className="mt-6 text-lg md:text-[20px] leading-relaxed"
              style={{ color: "oklch(0.78 0.006 75)" }}
            >
              {intro}
            </p>
          )}

          {lastUpdated && (
            <div
              className="mt-8 font-mono text-sm"
              style={{ color: "oklch(0.50 0.006 75)" }}
            >
              Last updated · {lastUpdated}
            </div>
          )}

          <div
            className="mt-10 md:mt-14 h-px"
            style={{ background: "rgba(255,255,255,0.10)" }}
          />

          <div className="mt-10 md:mt-14 space-y-10 prose-manthan">
            {children}
          </div>
        </motion.div>
      </main>

      {/* ── Quiet footer ────────────────────────────────────────────────── */}
      <footer
        className="px-6 md:px-12 lg:px-20 py-10 border-t flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
        style={{ borderColor: "rgba(255,255,255,0.08)" }}
      >
        <div className="flex items-center gap-2.5">
          <Logo size={20} showWordmark={false} className="text-white" />
          <span
            className="font-mono"
            style={{ fontSize: 12, color: "oklch(0.55 0.006 75)" }}
          >
            © {new Date().getFullYear()} Manthan. All rights reserved.
          </span>
        </div>
        <div className="flex items-center gap-5 text-sm">
          {[
            { label: "Blog", to: "/blog" },
            { label: "Privacy", to: "/privacy" },
            { label: "Terms", to: "/terms" },
            { label: "DPA", to: "/dpa" },
            { label: "Contact", to: "/contact" },
          ].map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className="transition-colors"
              style={{ color: "oklch(0.65 0.006 75)" }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = "oklch(0.96 0.004 75)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = "oklch(0.65 0.006 75)";
              }}
            >
              {l.label}
            </Link>
          ))}
        </div>
      </footer>
    </div>
  );
}

/* ─── Helper components for content sections ─────────────────────────── */

export function Section({
  heading,
  children,
}: {
  heading: ReactNode;
  children: ReactNode;
}) {
  return (
    <section>
      <h2
        className="text-2xl md:text-3xl tracking-[-0.02em] font-medium"
        style={{ color: "oklch(0.96 0.004 75)" }}
      >
        {heading}
      </h2>
      <div
        className="mt-4 text-[15.5px] leading-[1.7] space-y-4"
        style={{ color: "oklch(0.78 0.006 75)" }}
      >
        {children}
      </div>
    </section>
  );
}

export function DefList({
  items,
}: {
  items: { term: ReactNode; def: ReactNode }[];
}) {
  return (
    <dl className="space-y-5">
      {items.map((item, i) => (
        <div key={i} className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-2 md:gap-6">
          <dt
            className="font-mono uppercase"
            style={{
              fontSize: 11,
              color: "oklch(0.55 0.006 75)",
              letterSpacing: "0.12em",
              paddingTop: 4,
            }}
          >
            {item.term}
          </dt>
          <dd
            style={{
              fontSize: 15.5,
              lineHeight: 1.65,
              color: "oklch(0.85 0.005 75)",
            }}
          >
            {item.def}
          </dd>
        </div>
      ))}
    </dl>
  );
}
