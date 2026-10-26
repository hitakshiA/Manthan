/**
 * SourceHealth - uptime ledger for every connected source.
 *
 * Editorial form: one row per source on a hairline. The "health" indicator
 * is a single colored dot in the gutter - no chips, no card boxes. Last
 * query time + query volume live as tabular numerals on the right.
 */

import { useEffect, useState } from "react";

import {
  ErrorRow,
  LoadingRow,
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { listSources, type ApiSource } from "@/lib/api";

type Health = "live" | "idle" | "ready" | "missing";

const HEALTH_COLOR: Record<Health, string> = {
  live: "var(--color-accent)",
  idle: "var(--color-amber)",
  ready: "var(--color-ink-faint)",
  missing: "var(--color-ink-ghost)",
};

const HEALTH_LABEL: Record<Health, string> = {
  live: "live",
  idle: "idle > 24h",
  ready: "ready",
  missing: "missing",
};

export default function SourceHealth() {
  const [sources, setSources] = useState<ApiSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSources()
      .then((r) => setSources(r.sources))
      .catch((e: Error) => setError(e.message));
  }, []);

  const counts = sources
    ? sources.reduce<Record<Health, number>>(
        (acc, s) => {
          acc[healthFor(s)]++;
          return acc;
        },
        { live: 0, idle: 0, ready: 0, missing: 0 },
      )
    : null;

  return (
    <PageBody>
      <PageHeader
        eyebrow="Source health"
        title="Are the pipes flowing?"
        meta={
          counts ? (
            <span className="tabular-nums">
              {counts.live} live · {counts.idle} idle · {counts.ready} ready · {counts.missing} not configured
            </span>
          ) : null
        }
      />

      {error && <ErrorRow>{error}</ErrorRow>}
      {sources === null && !error && <LoadingRow />}

      {sources && (
        <Section>
          <ul className="divide-y" style={{ borderColor: "var(--color-rule-soft)" }}>
            {sources.map((s) => {
              const h = healthFor(s);
              return (
                <li
                  key={s.id}
                  style={{ borderColor: "var(--color-rule-soft)" }}
                  className="first:border-t"
                >
                  <div className="grid grid-cols-[auto_auto_1fr_auto] items-center gap-4 py-3.5">
                    <span
                      className="h-[7px] w-[7px] rounded-full self-center"
                      style={{ background: HEALTH_COLOR[h] }}
                    />
                    <div className="h-7 w-7 inline-flex items-center justify-center">
                      <SourceIcon id={s.id} size={16} tinted />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-baseline gap-3 flex-wrap">
                        <span
                          className="text-[13.5px]"
                          style={{ color: "var(--color-ink-strong)" }}
                        >
                          {s.name}
                        </span>
                        <span
                          className="text-[10.5px] uppercase tracking-[0.13em]"
                          style={{ color: HEALTH_COLOR[h] }}
                        >
                          {HEALTH_LABEL[h]}
                        </span>
                      </div>
                      <div
                        className="text-[11.5px] tabular-nums mt-0.5"
                        style={{ color: "var(--color-ink-muted)" }}
                      >
                        {s.last_query_at
                          ? `last query ${formatAge(s.last_query_at)} ago`
                          : "never queried"}
                        {" · "}
                        {s.queries_total.toLocaleString()} total
                      </div>
                    </div>
                    <span
                      className="text-[11px] capitalize"
                      style={{ color: "var(--color-ink-ghost)" }}
                    >
                      {s.category}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </Section>
      )}
    </PageBody>
  );
}

function healthFor(s: ApiSource): Health {
  if (s.status !== "connected") return "missing";
  if (!s.last_query_at) return "ready";
  const ageH = (Date.now() - new Date(s.last_query_at).getTime()) / 36e5;
  if (ageH > 24) return "idle";
  return "live";
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
