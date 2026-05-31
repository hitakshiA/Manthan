/**
 * Changelog - release notes for Manthan.
 * Editorial timeline layout, newest first. Each entry has a date, a
 * version, a one-line headline, and bulleted items grouped by Added /
 * Changed / Fixed.
 */

import { MarketingShell } from "@/components/marketing/MarketingShell";

type EntryGroup = "Added" | "Changed" | "Fixed";

type Entry = {
  date: string;
  version: string;
  headline: string;
  groups: Partial<Record<EntryGroup, string[]>>;
};

const ENTRIES: Entry[] = [
  {
    date: "2026-05-25",
    version: "v0.1.0",
    headline: "Manthan v1 closed beta. First design partners onboarding.",
    groups: {
      Added: [
        "Hosted case workspace, approval ledger, and policy guardrail.",
        "Cross-source investigations across Stripe, Salesforce, Zendesk, Notion, Slack, Gmail.",
        "Outcome-based pricing. First 50 closed cases each month are free.",
        "Cited briefs with one-click traceability to the source record.",
        "Approval gates per action class (auto-resolve under threshold, one-click in band, two-person above).",
      ],
      Changed: [
        "Repositioned from open-source AI data analyst to hosted operations layer for revenue disputes.",
        "Migrated agent core, citation graph, and policy execution from the analyst stack.",
      ],
    },
  },
];

export default function Changelog() {
  return (
    <MarketingShell
      eyebrow="Changelog"
      title={
        <>
          What's <em className="font-serif italic font-normal">shipped.</em>
        </>
      }
      intro="Every release that touched product. Tight notes, dated, never marketing fluff."
    >
      <div className="space-y-14">
        {ENTRIES.map((entry) => (
          <article
            key={entry.version}
            className="grid grid-cols-1 md:grid-cols-[160px_1fr] gap-6 md:gap-10"
          >
            <div>
              <div
                className="font-mono"
                style={{
                  fontSize: 12,
                  color: "oklch(0.55 0.006 75)",
                  letterSpacing: "0.08em",
                }}
              >
                {entry.date}
              </div>
              <div
                className="mt-1 font-mono tabular-nums"
                style={{
                  fontSize: 14,
                  color: "oklch(0.62 0.15 150)",
                  fontWeight: 600,
                }}
              >
                {entry.version}
              </div>
            </div>
            <div>
              <h3
                className="text-xl md:text-2xl tracking-[-0.015em]"
                style={{
                  color: "oklch(0.96 0.004 75)",
                  fontWeight: 500,
                  lineHeight: 1.25,
                }}
              >
                {entry.headline}
              </h3>
              <div className="mt-5 space-y-5">
                {(["Added", "Changed", "Fixed"] as EntryGroup[]).map((group) =>
                  entry.groups[group]?.length ? (
                    <div key={group}>
                      <div
                        className="font-mono uppercase"
                        style={{
                          fontSize: 10.5,
                          color:
                            group === "Added"
                              ? "oklch(0.62 0.15 150)"
                              : group === "Changed"
                              ? "oklch(0.78 0.13 75)"
                              : "oklch(0.55 0.006 75)",
                          letterSpacing: "0.16em",
                          marginBottom: 8,
                          fontWeight: 600,
                        }}
                      >
                        {group}
                      </div>
                      <ul className="space-y-2">
                        {entry.groups[group]!.map((item, i) => (
                          <li
                            key={i}
                            className="flex gap-3"
                            style={{
                              fontSize: 15,
                              lineHeight: 1.6,
                              color: "oklch(0.82 0.005 75)",
                            }}
                          >
                            <span style={{ color: "oklch(0.40 0.005 75)" }}>·</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null,
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </MarketingShell>
  );
}
