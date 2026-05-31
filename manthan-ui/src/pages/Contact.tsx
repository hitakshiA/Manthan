/**
 * Contact - direct lines to the Manthan team.
 * Three columns: design partners / sales / security & legal.
 * Plus the founder's socials at the bottom.
 */

import { MarketingShell } from "@/components/marketing/MarketingShell";
import { ArrowRight } from "lucide-react";

const LINES: {
  label: string;
  who: string;
  detail: string;
  email: string;
  blurb: string;
}[] = [
  {
    label: "Product & design partners",
    who: "Hitakshi",
    detail: "Founder · product",
    email: "hitakshi@miny-labs.com",
    blurb:
      "Replace humans in your dispute queue? Want early access? Product questions, design-partner intake. Reply within 24h.",
  },
  {
    label: "Sales, security & legal",
    who: "Akash",
    detail: "Founder · operations",
    email: "akash@miny-labs.com",
    blurb:
      "Annual contracts, procurement docs, security questionnaires, DPA / SOC 2 packets, audit requests. Triaged within one business day.",
  },
];

const SOCIALS: { label: string; href: string; handle: string }[] = [
  { label: "X", href: "https://x.com/hitakshi_exe", handle: "@hitakshi_exe" },
  {
    label: "LinkedIn",
    href: "https://www.linkedin.com/in/hitakshiaroraa/",
    handle: "hitakshiaroraa",
  },
  { label: "GitHub", href: "https://github.com/hitakshiA", handle: "hitakshiA" },
];

export default function Contact() {
  return (
    <MarketingShell
      eyebrow="Contact"
      title={
        <>
          Talk to us, <em className="font-serif italic font-normal">directly.</em>
        </>
      }
      intro="No support queue, no chatbot. The right person reads your email and replies."
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {LINES.map((line) => (
          <a
            key={line.label}
            href={`mailto:${line.email}`}
            className="group block rounded-lg p-6 transition-all"
            style={{
              background: "oklch(0.10 0.005 75)",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = "oklch(0.62 0.15 150 / 0.45)";
              e.currentTarget.style.background = "oklch(0.12 0.005 75)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)";
              e.currentTarget.style.background = "oklch(0.10 0.005 75)";
            }}
          >
            <div
              className="font-mono uppercase"
              style={{
                fontSize: 10.5,
                color: "oklch(0.55 0.006 75)",
                letterSpacing: "0.16em",
                marginBottom: 16,
              }}
            >
              {line.label}
            </div>
            <div
              style={{
                fontSize: 18,
                color: "oklch(0.96 0.004 75)",
                fontWeight: 600,
                letterSpacing: "-0.01em",
              }}
            >
              {line.email}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "oklch(0.55 0.006 75)",
                marginTop: 4,
                fontFamily: "Geist Mono, ui-monospace, monospace",
              }}
            >
              {line.detail}
            </div>
            <p
              className="mt-5 text-[14px] leading-[1.6]"
              style={{ color: "oklch(0.75 0.006 75)" }}
            >
              {line.blurb}
            </p>
            <div
              className="mt-6 inline-flex items-center gap-1.5 transition-opacity"
              style={{
                color: "oklch(0.62 0.15 150)",
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 12,
                fontWeight: 600,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
              }}
            >
              Send email
              <ArrowRight className="h-3.5 w-3.5" />
            </div>
          </a>
        ))}
      </div>

      {/* Founders */}
      <div
        className="mt-16 pt-10 border-t"
        style={{ borderColor: "rgba(255,255,255,0.08)" }}
      >
        <div
          className="font-mono uppercase mb-6"
          style={{
            fontSize: 10.5,
            color: "oklch(0.55 0.006 75)",
            letterSpacing: "0.16em",
          }}
        >
          Founders
        </div>
        <div
          style={{
            fontSize: 22,
            color: "oklch(0.96 0.004 75)",
            fontWeight: 600,
            letterSpacing: "-0.015em",
          }}
        >
          Hitakshi Arora · Akash Mondal
        </div>
        <div
          className="display-italic"
          style={{ fontSize: 18, color: "oklch(0.65 0.006 75)", marginTop: 2 }}
        >
          Building Manthan out of Miny Labs.
        </div>
        <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2">
          {SOCIALS.map((s) => (
            <a
              key={s.label}
              href={s.href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-baseline gap-2 transition-colors"
              style={{
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 13,
                color: "oklch(0.85 0.005 75)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = "oklch(0.62 0.15 150)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = "oklch(0.85 0.005 75)";
              }}
            >
              <span style={{ color: "oklch(0.50 0.006 75)" }}>{s.label}</span>
              <span>{s.handle}</span>
            </a>
          ))}
        </div>
      </div>
    </MarketingShell>
  );
}
